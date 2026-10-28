-- ff7-ime_matcher.lua
-- 魔光键影 · 纯 Lua 匹配与排序核心。
--
-- 本文件不依赖 Rime / Lua 标准库之外的任何东西，便于用独立 Lua 5.4 沙箱做回归。
-- 输入：无调全拼字母串；输出：按匹配度排序的候选（含通道与分数）。
--
-- 设计要点：
--   1. 精确全拼 > 模糊全拼 > 前缀 > 音节对齐 > 声母 > 关键词 > 最近邻回退。
--   2. 音节级对齐 DP 负责漏字、多字、相邻换位、音节前缀；
--      声母子序列负责 lkcc 这类缩写，音节前缀子序列负责 meishao
--      这类词条中段关键词（如“有时是出手相助的美少女忍者！”）。
--   3. 任何输入都返回 top_n 个候选，绝不空输出。

local M = {}

M.defaults = {
  top_n = 9,
  -- 需要 DP 时，只对双/三字母重叠度最高的 K 个候选跑音节对齐。
  dp_max_candidates = 56,
  fuzzy = {
    zh_z = true,
    ch_c = true,
    sh_s = true,
    ng_n = true,
    n_l = false,
    r_l = false,
    f_h = false,
    en_eng = false,
    in_ing = false,
    an_ang = false,
    uan_uang = false,
    v_u = true,
  },
  weights = {
    exact = 1.00,
    fuzzy = 0.97,
    fuzzy_prefix = 0.95,
    prefix = 0.96,
    swap = 0.93,
    dp = 0.94,
    initial_exact = 0.96,
    initial = 0.86,
    keyword = 0.80,
    fallback = 0.55,
  },
  typo = {
    enabled = true,
    strict = false,
    max_edit = 2,
    transposition = true,
    syllable_swap = true,
  },
  initial = {
    enabled = true,
  },
  keyword = {
    enabled = true,
    gap_penalty = 0.02,
    -- 词条中段的音节前缀子序列（meishao -> 美少女）。
    syllable_subsequence = true,
  },
  -- 最后一级回退：按 bigram/trigram 召回候选，再用 Damerau/LCS 排序。
  fallback = {
    use_lcs = true,
    -- DP 是近似对齐；低于该 raw 的结果不作为强候选，交给回退。
    dp_min_raw = 0.65,
    -- 已有该 raw 以上的强命中时，只做小池回退，避免拖慢正常输入。
    strong_raw = 0.70,
    fast_max_candidates = 16,
    -- 无强命中时，回退池按重叠度预排序后实际计算相似度的候选数上限。
    max_candidates = 96,
  },
  -- 仅影响 preedit 显示，不影响匹配与候选排序。
  preedit = {
    enabled = true,
    separator = "'",
  },
  score_epsilon = 1e-9,
}

local CHANNEL_RANK = {
  exact = 0,
  fuzzy = 1,
  prefix = 2,
  fuzzy_prefix = 3,
  swap = 4,
  dp = 5,
  initial_exact = 6,
  initial = 7,
  keyword = 8,
  fallback = 9,
}

local function copy_table(t)
  local r = {}
  for k, v in pairs(t) do
    if type(v) == "table" then
      r[k] = copy_table(v)
    else
      r[k] = v
    end
  end
  return r
end

local function merge_into(dst, src)
  if not src then
    return dst
  end
  for k, v in pairs(src) do
    if type(v) == "table" and type(dst[k]) == "table" then
      merge_into(dst[k], v)
    else
      dst[k] = v
    end
  end
  return dst
end

function M.options(overrides)
  local opts = copy_table(M.defaults)
  merge_into(opts, overrides)
  return opts
end

-- 规范化：小写；只保留 a-z（ü 由数据层统一写成 v）。
function M.normalize(input)
  local s = string.lower(input or "")
  s = s:gsub("[^a-z]", "")
  return s
end

local function count_vowels(s)
  local _, n = s:gsub("[aeiouv]", "")
  return n
end

-- 音节的模糊规范化（可处理 n/l、r/l、f/h 等只在音节首生效的规则）。
local function canon_syllable(s, fuzzy)
  if fuzzy.zh_z then s = s:gsub("^zh", "z") end
  if fuzzy.ch_c then s = s:gsub("^ch", "c") end
  if fuzzy.sh_s then s = s:gsub("^sh", "s") end
  if fuzzy.ng_n then s = s:gsub("ng$", "n") end
  if fuzzy.en_eng then s = s:gsub("eng$", "en") end
  if fuzzy.in_ing then s = s:gsub("ing$", "in") end
  if fuzzy.an_ang then s = s:gsub("ang$", "an") end
  if fuzzy.uan_uang then s = s:gsub("uang$", "uan") end
  if fuzzy.n_l then s = s:gsub("^n", "l") end
  if fuzzy.r_l then s = s:gsub("^r", "l") end
  if fuzzy.f_h then s = s:gsub("^f", "h") end
  if fuzzy.v_u then s = s:gsub("v", "u") end
  return s
end

-- 连续输入串的规范化。只做不会跨音节边界误伤的规则：
-- 拼音音节不会以 z/c/s 结尾，因此 zh/ch/sh 的全局替换是安全的；
-- ng→n、n/l、r/l、f/h 等必须放在音节级 syl_match/DP 中处理。
local function canon_input(input, fuzzy)
  local s = input
  if fuzzy.zh_z then s = s:gsub("zh", "z") end
  if fuzzy.ch_c then s = s:gsub("ch", "c") end
  if fuzzy.sh_s then s = s:gsub("sh", "s") end
  if fuzzy.v_u then s = s:gsub("v", "u") end
  return s
end

local function initial_of(syllable)
  if syllable:sub(1, 2) == "zh" or syllable:sub(1, 2) == "ch"
      or syllable:sub(1, 2) == "sh" then
    return syllable:sub(1, 2)
  end
  return syllable:sub(1, 1)
end

-- Damerau-Levenshtein（相邻换位算 1 次操作）。
-- 使用三行滚动数组，避免为每个候选分配二维表。
local function edit_distance(a, b, transposition)
  local la, lb = #a, #b
  if la == 0 then return lb end
  if lb == 0 then return la end
  if la > lb then
    a, b = b, a
    la, lb = lb, la
  end

  local prev2, prev, cur = {}, {}, {}
  local ba, bb = {}, {}
  for i = 1, la do ba[i] = string.byte(a, i) end
  for j = 1, lb do bb[j] = string.byte(b, j) end
  for j = 0, lb do
    prev[j] = j
  end

  for i = 1, la do
    cur[0] = i
    local ca = ba[i]
    local ca_prev = ba[i - 1]
    for j = 1, lb do
      local cb = bb[j]
      local cost = (ca == cb) and 0 or 1
      local v = math.min(
        prev[j] + 1,
        cur[j - 1] + 1,
        prev[j - 1] + cost
      )
      if transposition and i > 1 and j > 1
          and ca == bb[j - 1]
          and ca_prev == cb then
        v = math.min(v, prev2[j - 2] + 1)
      end
      cur[j] = v
    end
    prev2, prev, cur = prev, cur, prev2
  end
  return prev[lb]
end
M.edit_distance = edit_distance

-- 一个输入块与一个候选音节的匹配。
-- 返回 { score, kind, penalty }，score 为 0 表示不匹配。
-- cache 为可选的每次查询共享缓存，避免重复计算相同的 chunk/reading 组合。
local function syllable_match(chunk, reading, fuzzy, max_edit, transposition, cache, strict)
  if chunk == reading then
    return { score = 1.0, kind = "full", penalty = 0 }
  end

  local key
  if cache then
    key = chunk .. "\0" .. reading
    local hit = cache[key]
    if hit then
      return hit
    end
  end

  local cc = canon_syllable(chunk, fuzzy)
  local cr = canon_syllable(reading, fuzzy)

  if strict then
    -- 严格模式：只接受精确或规范模糊相等，不允许前缀/编辑距离。
    local res
    if cc == cr then
      res = { score = 0.96, kind = "fuzzy", penalty = 0.02 }
    else
      res = { score = 0, kind = nil, penalty = 0 }
    end
    if cache then
      cache[key] = res
    end
    return res
  end

  local best = { score = 0, kind = nil, penalty = 0 }

  if #chunk < #reading and reading:sub(1, #chunk) == chunk then
    local s = 0.55 + 0.40 * (#chunk / #reading)
    if s > best.score then
      best = { score = s, kind = "partial", penalty = 0 }
    end
  end

  if cc == cr then
    local s = 0.96
    if s > best.score then
      best = { score = s, kind = "fuzzy", penalty = 0.02 }
    end
  elseif #cc < #cr and cr:sub(1, #cc) == cc then
    local s = 0.55 + 0.40 * (#cc / #cr)
    if s > best.score then
      best = { score = s, kind = "fuzzy_partial", penalty = 0.02 }
    end
  end

  if max_edit > 0 and #chunk > 0 and #reading > 0 then
    local pairs_to_try = { { chunk, reading } }
    if cc ~= chunk or cr ~= reading then
      pairs_to_try[2] = { cc, cr }
    end
    for _, pair in ipairs(pairs_to_try) do
      local a, b = pair[1], pair[2]
      if math.abs(#a - #b) <= max_edit then
        local dist = edit_distance(a, b, transposition)
        if dist > 0 and dist <= max_edit then
          local s = 0.95 - 0.15 * dist
          if s > best.score then
            best = { score = s, kind = "typo", penalty = 0.05 * dist }
          end
        end
      end
    end
  end

  if cache then
    cache[key] = best
  end
  return best
end

local function as_list_item(v)
  if type(v) == "table" then
    return v.s or v[1], v.w or v.weight or 1.0
  end
  return v, 1.0
end

-- 预计算一条词条的运行时索引。可重复调用。
local function prepare_phrase(p, fuzzy, typo)
  if p._ff7_ime_prepared then
    return p
  end

  p.order = p.order or p.id or 0
  p.w = p.w or p.weight or 1.0
  p.syls = p.syls or {}
  p.n = #p.syls

  -- 每个音节的候选读音：主读音 + 备选读音（多音字/允许误读）。
  p.readings = {}
  for j = 1, p.n do
    local primary = p.syls[j]
    local list = { { s = primary, w = 1.0 } }
    local alts = p.alts and p.alts[j]
    if alts then
      for _, alt in ipairs(alts) do
        local text, weight = as_list_item(alt)
        if text and text ~= primary then
          list[#list + 1] = { s = text, w = weight }
        end
      end
    end
    p.readings[j] = list
  end

  -- 全拼变体（生成期通常已提供；这里兜底为主读音）。
  if not p.fulls or #p.fulls == 0 then
    p.fulls = { { s = table.concat(p.syls), w = 1.0 } }
  else
    local normalized = {}
    for _, f in ipairs(p.fulls) do
      local text, weight = as_list_item(f)
      if text then
        normalized[#normalized + 1] = { s = text, w = weight }
      end
    end
    p.fulls = normalized
  end
  p.primary_full = table.concat(p.syls)

  -- 主读音的逐音节模糊规范化全拼（用于 DP 候选的重叠度排序）。
  local canon_syls = {}
  for j = 1, p.n do
    canon_syls[j] = canon_syllable(p.syls[j], fuzzy)
  end
  p.canon_full = table.concat(canon_syls)

  -- 模糊规范化后的全拼变体。
  p.canons = {}
  for _, f in ipairs(p.fulls) do
    p.canons[#p.canons + 1] = { s = canon_input(f.s, fuzzy), w = f.w, raw = f.s }
  end

  -- 声母变体：优先使用生成期数据，否则从主读音推导。
  if not p.init_variants or #p.init_variants == 0 then
    local tokens = {}
    for j = 1, p.n do
      tokens[j] = initial_of(p.syls[j])
    end
    p.init_variants = { { tokens = tokens, w = 1.0 } }
  else
    local normalized = {}
    for _, v in ipairs(p.init_variants) do
      local tokens = v.tokens or v
      if tokens then
        normalized[#normalized + 1] = { tokens = tokens, w = v.w or 1.0 }
      end
    end
    p.init_variants = normalized
  end

  -- 回退相似度会反复用到声母串，预计算一次。
  p.init_flats = {}
  for _, v in ipairs(p.init_variants) do
    local flat = {}
    for i, tok in ipairs(v.tokens) do
      local text = type(tok) == "table" and (tok.s or tok[1]) or tok
      flat[i] = initial_of(text)
    end
    p.init_flats[#p.init_flats + 1] = table.concat(flat)
  end

  -- 相邻音节换位变体（nuolei -> 雷诺）。
  if not p.swaps or #p.swaps == 0 then
    p.swaps = {}
    if p.n >= 2 then
      for j = 1, p.n - 1 do
        local t = {}
        for k = 1, p.n do t[k] = p.syls[k] end
        t[j], t[j + 1] = t[j + 1], t[j]
        p.swaps[#p.swaps + 1] = { s = table.concat(t), w = 1.0 }
      end
    end
  else
    local normalized = {}
    for _, sw in ipairs(p.swaps) do
      local text, weight = as_list_item(sw)
      if text then
        normalized[#normalized + 1] = { s = text, w = weight }
      end
    end
    p.swaps = normalized
  end

  -- DP 前的快速过滤：首字母/末字母是否可能匹配。
  p._firsts = {}
  p._lasts = {}
  for _, f in ipairs(p.fulls) do
    p._firsts[f.s:sub(1, 1)] = true
    p._lasts[f.s:sub(-1)] = true
  end
  for _, sw in ipairs(p.swaps) do
    p._firsts[sw.s:sub(1, 1)] = true
    p._lasts[sw.s:sub(-1)] = true
  end
  for _, v in ipairs(p.init_variants) do
    local t = v.tokens
    if t and t[1] then
      p._firsts[(t[1].s or t[1]):sub(1, 1)] = true
    end
  end

  -- 模糊规则会改变音节的首/末字母（ng→n、n→l 等），把规范化后的
  -- 首/末字母也加入快速过滤集合，避免 DP 被错误地提前拒绝。
  for j = 1, p.n do
    for _, r in ipairs(p.readings[j]) do
      local c = canon_syllable(r.s, fuzzy)
      p._firsts[c:sub(1, 1)] = true
      p._lasts[c:sub(-1)] = true
    end
  end

  p._ff7_ime_prepared = true
  return p
end

-- 声母/关键词子序列匹配。
-- 返回 score, is_exact_initials。
local function keyword_score(input, tokens, fuzzy, cfg)
  if #input == 0 or #tokens == 0 then
    return 0, false
  end

  local t = {}
  for i, tok in ipairs(tokens) do
    local text = type(tok) == "table" and (tok.s or tok[1]) or tok
    if not text or text == "" then
      return 0, false
    end
    local c = initial_of(text)
    if c == "zh" then
      c = fuzzy.zh_z and "z" or "z"
    elseif c == "ch" then
      c = fuzzy.ch_c and "c" or "c"
    elseif c == "sh" then
      c = fuzzy.sh_s and "s" or "s"
    else
      c = c:sub(1, 1)
    end
    if fuzzy.n_l and c == "n" then c = "l" end
    if fuzzy.r_l and c == "r" then c = "l" end
    if fuzzy.f_h and c == "f" then c = "h" end
    t[i] = c
  end

  local q = input
  if fuzzy.zh_z then q = q:gsub("zh", "z") end
  if fuzzy.ch_c then q = q:gsub("ch", "c") end
  if fuzzy.sh_s then q = q:gsub("sh", "s") end
  if fuzzy.n_l then q = q:gsub("n", "l") end
  if fuzzy.r_l then q = q:gsub("r", "l") end
  if fuzzy.f_h then q = q:gsub("f", "h") end
  if #q == 0 then
    return 0, false
  end

  local best = 0
  local best_exact = false
  local gap_penalty = cfg.keyword.gap_penalty

  for start = 1, #t do
    local pos = start
    local last = start
    local matched = 0
    local ok = true
    for i = 1, #q do
      local ch = q:sub(i, i)
      local found = nil
      for j = pos, #t do
        if t[j] == ch then
          found = j
          break
        end
      end
      if not found then
        ok = false
        break
      end
      matched = matched + 1
      last = found
      pos = found + 1
    end
    if ok and matched == #q then
      local phrase_cov = #q / #t
      local span = last - start + 1
      local compact = #q / span
      local start_pen = (start - 1) / #t
      local gap = span - #q
      local score = 0.45
        + 0.25 * phrase_cov
        + 0.20 * compact
        + 0.10 * (1 - start_pen)
        - gap_penalty * gap
      if score > best then
        best = score
        best_exact = (#q == #t and start == 1 and span == #t)
      end
    end
  end

  if best < 0 then best = 0 end
  return best, best_exact
end

-- 音节前缀子序列：把输入切成若干块，每块是某个音节读音的前缀，
-- 允许跳过中间音节。用于命中词条中段的关键词：
--   meishao     -> 有时是出手相助的【美少】女忍者！
--   chushou     -> 有时是【出手】相助的美少女忍者！
--   shouxiang   -> 有时是出手【相助】的美少女忍者！
-- 只比较前缀/精确读音，不做编辑距离；错字仍由 DP 通道负责。
local function syllable_keyword_score(input, p, fuzzy, cfg)
  local L = #input
  if L < 2 or p.n < 1 then
    return 0
  end

  local best = 0
  local W = p.n + 1
  local gap_penalty = cfg.keyword.gap_penalty or 0.02
  local first = input:sub(1, 1)

  for start = 1, p.n do
    -- 起始音节必须能承接输入首字母（原始或模糊规范化后），否则整条 DP 必空。
    local start_ok = false
    for _, r in ipairs(p.readings[start]) do
      if r.s:sub(1, 1) == first
          or canon_syllable(r.s, fuzzy):sub(1, 1) == first then
        start_ok = true
        break
      end
    end

    if start_ok then
      -- dp[i * W + j]：消耗 i 个输入字母、处理到第 j 个音节后的最优块状态。
      -- j 从 start-1 开始，因此第一块落在 start 音节的任意前缀上。
      local dp = {}
      local init_j = start - 1
      dp[init_j] = { q = 0, c = 0, has2 = false }

      local function better(prev, qsum, chunks, has2)
        return not prev
          or qsum > prev.q
          or (qsum == prev.q and chunks > prev.c)
          or (qsum == prev.q and chunks == prev.c and has2 and not prev.has2)
      end

      for i = 0, L do
        local base = i * W
        for j = init_j, p.n do
          local cur = dp[base + j]
          if cur then
            -- 跳过下一个音节（允许关键词出现在词条中段）。
            if j < p.n then
              local at = base + j + 1
              if better(dp[at], cur.q, cur.c, cur.has2) then
                dp[at] = cur
              end
            end

            -- 用当前音节的一个前缀消耗输入块。
            if i < L and j < p.n then
              local readings = p.readings[j + 1]
              for _, r in ipairs(readings) do
                local forms = { r.s }
                local cr = canon_syllable(r.s, fuzzy)
                if cr ~= r.s then
                  forms[2] = cr
                end
                for _, syl in ipairs(forms) do
                  local maxk = math.min(#syl, L - i)
                  for k = 1, maxk do
                    local chunk = input:sub(i + 1, i + k)
                    if chunk == syl:sub(1, k) then
                      local at = (i + k) * W + (j + 1)
                      local qsum = cur.q + k / #syl
                      local chunks = cur.c + 1
                      local has2 = cur.has2 or (k >= 2)
                      if better(dp[at], qsum, chunks, has2) then
                        dp[at] = {
                          q = qsum,
                          c = chunks,
                          has2 = has2,
                        }
                      end
                    end
                  end
                end
              end
            end
          end
        end
      end

      for j = start, p.n do
        local cur = dp[L * W + j]
        if cur and cur.has2 and cur.c > 0 then
          local span = j - start + 1
          local chunk_quality = cur.q / cur.c
          local compact = cur.c / span
          local phrase_cov = L / math.max(1, #p.primary_full)
          local start_pen = (start - 1) / p.n
          local gap = span - cur.c
          local s = 0.50
            + 0.25 * chunk_quality
            + 0.15 * compact
            + 0.10 * (1 - start_pen)
            + 0.05 * phrase_cov
            - gap_penalty * gap
          if s > best then
            best = s
          end
        end
      end
    end
  end

  if best < 0 then
    best = 0
  elseif best > 1 then
    best = 1
  end
  return best
end

-- 音节级对齐 DP：允许整音节/前缀/近似匹配、漏音节、多字母、相邻换位。
local function dp_score(input, p, fuzzy, cfg, cache, strict)
  local L, n = #input, p.n
  if L == 0 or n == 0 then
    return 0
  end

  local max_edit = cfg.typo.max_edit or 2
  local transposition = cfg.typo.transposition ~= false
  local skip_penalty = 0.12
  local extra_penalty = 0.20
  local trailing_penalty = 0.04

  -- 扁平数组：dp[i * W + j + 1] 表示消耗 i 个输入字母、j 个音节后的最高分。
  local W = n + 1
  local dp = {}
  dp[1] = 0

  local best = -1e9

  if strict then
    -- 严格模式：每个音节都必须精确/模糊匹配，不允许漏字、多字、前缀或换位。
    for i = 0, L do
      local base = i * W
      for j = 0, n do
        local cur = dp[base + j + 1]
        if cur and j < n then
          local readings = p.readings[j + 1]
          for ri, r in ipairs(readings) do
            local cr = canon_syllable(r.s, fuzzy)
            local lengths = { #r.s }
            if #cr ~= #r.s then
              lengths[2] = #cr
            end
            for _, k in ipairs(lengths) do
              if i + k <= L then
                local chunk = input:sub(i + 1, i + k)
                local m = syllable_match(chunk, r.s, fuzzy, 0, false, cache, true)
                if m.score > 0 then
                  local at = (i + k) * W + j + 2
                  local v = cur
                    + m.score * (r.w or 1.0)
                    - (m.penalty or 0)
                    - (ri > 1 and 0.02 or 0)
                  if not dp[at] or v > dp[at] then
                    dp[at] = v
                  end
                end
              end
            end
          end
        end
      end
    end
    local final = dp[L * W + n + 1]
    if not final or final <= 0 then
      return 0
    end
    local s = final / n
    if s > 1 then s = 1 end
    return s
  end

  for i = 0, L do
    local base = i * W
    for j = 0, n do
      local cur = dp[base + j + 1]
      if cur then
        if j < n then
          local at = base + j + 2
          local v = cur - skip_penalty
          if not dp[at] or v > dp[at] then
            dp[at] = v
          end
        end

        if i < L then
          local at = base + W + j + 1
          local v = cur - extra_penalty
          if not dp[at] or v > dp[at] then
            dp[at] = v
          end
        end

        if j < n and i < L then
          local readings = p.readings[j + 1]
          for ri, r in ipairs(readings) do
            local maxk = math.min(#r.s + max_edit, L - i)
            for k = 1, maxk do
              local chunk = input:sub(i + 1, i + k)
              local m = syllable_match(chunk, r.s, fuzzy, max_edit, transposition, cache)
              if m.score > 0 then
                local at = (i + k) * W + j + 2
                local v = cur
                  + m.score * (r.w or 1.0)
                  - (m.penalty or 0)
                  - (ri > 1 and 0.02 or 0)
                if not dp[at] or v > dp[at] then
                  dp[at] = v
                end
              end
            end
          end
        end

        if i == L then
          local v = cur - trailing_penalty * (n - j)
          if v > best then
            best = v
          end
        end
      end
    end
  end

  if best <= 0 then
    return 0
  end
  local s = best / n
  if s < 0 then s = 0 elseif s > 1 then s = 1 end
  return s
end

local function dp_allowed(input, p, fuzzy, cfg, relaxed)
  local L, full_len = #input, #p.primary_full
  if L == 0 or full_len == 0 then
    return false
  end
  if L < 0.25 * full_len or L > 2.5 * full_len then
    return false
  end

  if relaxed then
    -- 二次召回已经用双字母索引过滤过；仍要求末字母合理，避免大量噪声。
    local last = input:sub(-1)
    local clast = canon_input(last, fuzzy):sub(-1)
    return p._lasts[last] or p._lasts[clast] or math.abs(L - full_len) <= 1
  end

  -- 末字母不同且长度差较大时，音节对齐几乎不可能命中，直接跳过。
  local last = input:sub(-1)
  local clast = canon_input(last, fuzzy):sub(-1)
  if not p._lasts[last] and not p._lasts[clast] then
    if math.abs(L - full_len) > 1 then
      return false
    end
  end

  local first = input:sub(1, 1)
  if p._firsts[first] then
    return true
  end
  local cfirst = canon_input(first, fuzzy):sub(1, 1)
  if p._firsts[cfirst] then
    return true
  end
  -- 允许首字母本身就被打错：短输入时放宽。
  return L <= 3
end

local function fallback_score(input, p, fuzzy)
  local best = 0
  for _, f in ipairs(p.fulls) do
    local d = edit_distance(input, f.s, true)
    local s = 1 - d / math.max(#input, #f.s)
    if s > best then best = s end
  end
  for _, s0 in ipairs(p.init_flats or {}) do
    local d = edit_distance(input, s0, true)
    local s = 0.88 * (1 - d / math.max(#input, #s0))
    if s > best then best = s end
  end
  if best < 0 then best = 0 end
  return best
end

-- 最长公共子序列长度。回退排序用，不参与强通道打分。
local function lcs_length(a, b)
  local la, lb = #a, #b
  if la == 0 or lb == 0 then
    return 0
  end
  if la < lb then
    a, b = b, a
    la, lb = lb, la
  end
  local ba, bb = {}, {}
  for i = 1, la do ba[i] = string.byte(a, i) end
  for j = 1, lb do bb[j] = string.byte(b, j) end
  local prev, cur = {}, {}
  for j = 0, lb do prev[j] = 0 end
  for i = 1, la do
    cur[0] = 0
    local ca = ba[i]
    for j = 1, lb do
      if ca == bb[j] then
        cur[j] = prev[j - 1] + 1
      elseif prev[j] >= cur[j - 1] then
        cur[j] = prev[j]
      else
        cur[j] = cur[j - 1]
      end
    end
    prev, cur = cur, prev
  end
  return prev[lb]
end

-- Dice 归一化的 LCS：2*LCS/(len(q)+len(full))，再对长度差收一点惩罚。
-- 原始 LCS 长度会系统性偏向长句，不能直接拿来排序。
local function lcs_similarity(input, p)
  local best = 0
  for _, f in ipairs(p.fulls) do
    local denom = #input + #f.s
    if denom > 0 then
      local l = lcs_length(input, f.s)
      local s = (2 * l) / denom
      local maxlen = math.max(#input, #f.s)
      s = s - 0.05 * math.abs(#input - #f.s) / maxlen
      if s > best then
        best = s
      end
    end
  end
  if best < 0 then best = 0 end
  return best
end

local function fallback_similarity(input, p, fuzzy, cfg, fast)
  local use_lcs = not cfg.fallback or cfg.fallback.use_lcs ~= false
  local best = 0
  if not fast or not use_lcs then
    best = fallback_score(input, p, fuzzy)
  end
  if use_lcs then
    local l = lcs_similarity(input, p)
    if l > best then
      best = l
    end
  end
  return best
end

local function compare_results(a, b, eps)
  if math.abs(a.score - b.score) > eps then
    return a.score > b.score
  end
  local ra = CHANNEL_RANK[a.channel] or 99
  local rb = CHANNEL_RANK[b.channel] or 99
  if ra ~= rb then
    return ra < rb
  end
  local na = a.phrase.n or 0
  local nb = b.phrase.n or 0
  if na ~= nb then
    return na < nb
  end
  local wa = a.phrase.w or 1.0
  local wb = b.phrase.w or 1.0
  if math.abs(wa - wb) > 1e-9 then
    return wa > wb
  end
  return (a.phrase.order or a.index) < (b.phrase.order or b.index)
end

local EMPTY = {}

local function channel_weight(cfg, channel, initial_mode)
  local w = cfg.weights[channel] or cfg.weights.fallback or 0.55
  if initial_mode then
    if channel == "keyword" then
      w = math.max(w, 0.90)
    elseif channel == "initial" then
      w = math.max(w, 0.92)
    end
  end
  return w
end

-- 对单条词条打分。返回 nil 表示所有强通道都没有命中（留给二次召回/回退）。
local function score_phrase(q, qcanon, p, cfg, initial_mode, relaxed, allow_dp, cache)
  local fuzzy = cfg.fuzzy
  local best_weighted, best_raw = 0, 0
  local best_channel, best_detail = nil, nil

  local function consider(raw, channel, detail)
    if raw <= 0 then
      return
    end
    local weighted = raw * channel_weight(cfg, channel, initial_mode)
    if weighted > best_weighted then
      best_weighted, best_raw = weighted, raw
      best_channel, best_detail = channel, detail
    end
  end

  -- 1) 精确全拼 / 全拼前缀
  for _, f in ipairs(p.fulls) do
    if q == f.s then
      consider(f.w or 1.0, "exact", f.s)
    elseif #q < #f.s and f.s:sub(1, #q) == q then
      consider((0.90 + 0.09 * (#q / #f.s)) * (f.w or 1.0), "prefix", f.s)
    end
  end

  -- 2) 模糊全拼 / 模糊前缀
  for _, c in ipairs(p.canons) do
    if qcanon == c.s then
      consider(0.965 * (c.w or 1.0), "fuzzy", c.s)
    elseif #qcanon < #c.s and c.s:sub(1, #qcanon) == qcanon then
      consider((0.88 + 0.08 * (#qcanon / #c.s)) * (c.w or 1.0), "fuzzy_prefix", c.s)
    end
  end

  local qlen = #q
  local full_len = #p.primary_full

  -- 3) 声母 / 关键词子序列。输入明显长于全拼时不可能只是声母，跳过。
  if cfg.initial.enabled ~= false and best_raw < 0.97 and qlen <= full_len + 2 then
    for _, v in ipairs(p.init_variants) do
      local ks, is_exact = keyword_score(q, v.tokens, fuzzy, cfg)
      if ks > 0 then
        local raw_parts = {}
        for i, tok in ipairs(v.tokens) do
          raw_parts[i] = type(tok) == "table" and (tok.s or tok[1]) or tok
        end
        local raw_exact = (q == table.concat(raw_parts))
        if raw_exact then
          consider(1.0 * (v.w or 1.0), "initial_exact", #v.tokens)
        else
          consider(ks * (v.w or 1.0), is_exact and "initial" or "keyword", #v.tokens)
        end
      end
    end
  end

  -- 4) 相邻音节换位
  if cfg.typo.syllable_swap ~= false and qlen <= full_len + 2 then
    for _, sw in ipairs(p.swaps) do
      if q == sw.s then
        consider(0.93 * (sw.w or 1.0), "swap", sw.s)
      end
    end
  end

  -- 5) 音节级对齐（漏、多、错、换位、部分输入）。
  -- 纯声母输入（无元音）不跑 DP：用户意图是缩写，不是全拼笔误。
  if allow_dp and not initial_mode and best_raw < 0.90
      and dp_allowed(q, p, fuzzy, cfg, relaxed) then
    local dp_raw = dp_score(q, p, fuzzy, cfg, cache, cfg.typo.strict == true or cfg.typo.enabled == false)
    local dp_min_raw = cfg.fallback and cfg.fallback.dp_min_raw or 0
    if dp_raw > 0 and dp_raw >= dp_min_raw then
      consider(dp_raw, "dp", "align")
    end
  end

  if not best_channel then
    return nil
  end
  return {
    score = best_weighted + 0.0001 * (p.w or 1.0),
    raw = best_raw,
    channel = best_channel,
    detail = best_detail,
  }
end

-- 测试/诊断钩子：不参与正式调用。
M._score_phrase = score_phrase
M._canon_input = canon_input

local function add_index(map, key, id)
  local list = map[key]
  if not list then
    list = {}
    map[key] = list
  end
  list[#list + 1] = id
end

local function fuzzy_key(fuzzy)
  return table.concat({
    fuzzy.zh_z and "1" or "0",
    fuzzy.ch_c and "1" or "0",
    fuzzy.sh_s and "1" or "0",
    fuzzy.ng_n and "1" or "0",
    fuzzy.n_l and "1" or "0",
    fuzzy.r_l and "1" or "0",
    fuzzy.f_h and "1" or "0",
    fuzzy.en_eng and "1" or "0",
    fuzzy.in_ing and "1" or "0",
    fuzzy.an_ang and "1" or "0",
    fuzzy.uan_uang and "1" or "0",
    fuzzy.v_u and "1" or "0",
  }, "")
end

-- 建立首字母 / 声母字母 / 双字母 / 三字母 / 静态优先索引。只做一次；
-- 模糊音开关变化时自动重建（会重置缓存的 canons）。
local function build_index(phrases, cfg)
  local key = fuzzy_key(cfg.fuzzy)
  if phrases._ff7_ime_index and phrases._ff7_ime_index_key == key then
    return phrases._ff7_ime_index
  end
  if phrases._ff7_ime_index_key and phrases._ff7_ime_index_key ~= key then
    for _, p in ipairs(phrases) do
      p._ff7_ime_prepared = nil
    end
    phrases._ff7_ime_index = nil
  end

  local idx = {
    by_first = {},
    by_init_letter = {},
    by_bigram = {},
    by_trigram = {},
    by_canon_bigram = {},
    by_canon_trigram = {},
    by_syl_prefix = {},
    by_full = {},
    by_canon = {},
    static_top = {},
    syllables = {},
    syllable_prefixes = {},
    max_syllable = 0,
  }

  for id, p in ipairs(phrases) do
    prepare_phrase(p, cfg.fuzzy, cfg.typo)

    for _, readings in ipairs(p.readings) do
      for _, r in ipairs(readings) do
        local forms = { r.s }
        local cr = canon_syllable(r.s, cfg.fuzzy)
        if cr ~= r.s then forms[2] = cr end
        for _, syl in ipairs(forms) do
          if syl ~= "" then
            idx.syllables[syl] = true
            if #syl > idx.max_syllable then idx.max_syllable = #syl end
            for k = 1, #syl do
              idx.syllable_prefixes[syl:sub(1, k)] = true
            end
          end
        end
      end
    end

    local seen_first, seen_init, seen_bg, seen_tg = {}, {}, {}, {}

    local function add_full(s)
      if not s or s == "" then
        return
      end
      local c = s:sub(1, 1)
      if not seen_first[c] then
        seen_first[c] = true
        add_index(idx.by_first, c, id)
      end
      for k = 1, #s - 1 do
        local bg = s:sub(k, k + 1)
        if not seen_bg[bg] then
          seen_bg[bg] = true
          add_index(idx.by_bigram, bg, id)
        end
      end
      for k = 1, #s - 2 do
        local tg = s:sub(k, k + 2)
        if not seen_tg[tg] then
          seen_tg[tg] = true
          add_index(idx.by_trigram, tg, id)
        end
      end
    end

    for _, f in ipairs(p.fulls) do add_full(f.s) end
    for _, sw in ipairs(p.swaps) do add_full(sw.s) end

    -- 模糊规范化后的双/三字母索引：DP 候选排序用，能正确覆盖 ng→n、zh→z。
    local cs = p.canon_full or ""
    local seen_cbg, seen_ctg = {}, {}
    for k = 1, #cs - 1 do
      local bg = cs:sub(k, k + 1)
      if not seen_cbg[bg] then
        seen_cbg[bg] = true
        add_index(idx.by_canon_bigram, bg, id)
      end
    end
    for k = 1, #cs - 2 do
      local tg = cs:sub(k, k + 2)
      if not seen_ctg[tg] then
        seen_ctg[tg] = true
        add_index(idx.by_canon_trigram, tg, id)
      end
    end

    for _, f in ipairs(p.fulls) do add_index(idx.by_full, f.s, id) end
    for _, c in ipairs(p.canons) do add_index(idx.by_canon, c.s, id) end

    for _, v in ipairs(p.init_variants) do
      for _, tok in ipairs(v.tokens) do
        local text = type(tok) == "table" and (tok.s or tok[1]) or tok
        local c = initial_of(text):sub(1, 1)
        if not seen_init[c] then
          seen_init[c] = true
          add_index(idx.by_init_letter, c, id)
        end
      end
    end

    -- 音节前缀召回索引（1..3 字母）：中段关键词的第一块召回。
    -- 只索引每个读音的前缀，完整匹配仍由 syllable_keyword_score 校验。
    local seen_sp = {}
    for j = 1, p.n do
      for _, r in ipairs(p.readings[j]) do
        local forms = { r.s }
        local cr = canon_syllable(r.s, cfg.fuzzy)
        if cr ~= r.s then
          forms[2] = cr
        end
        for _, syl in ipairs(forms) do
          local maxk = math.min(3, #syl)
          for k = 1, maxk do
            local key = syl:sub(1, k)
            if not seen_sp[key] then
              seen_sp[key] = true
              add_index(idx.by_syl_prefix, key, id)
            end
          end
        end
      end
    end

    idx.static_top[#idx.static_top + 1] = id
  end

  table.sort(idx.static_top, function(a, b)
    local pa, pb = phrases[a], phrases[b]
    local wa, wb = pa.w or 1.0, pb.w or 1.0
    if math.abs(wa - wb) > 1e-9 then
      return wa > wb
    end
    if pa.n ~= pb.n then
      return pa.n < pb.n
    end
    return (pa.order or a) < (pb.order or b)
  end)

  phrases._ff7_ime_index = idx
  phrases._ff7_ime_index_key = key
  return idx
end

local function collect_primary(q, idx, cfg, initial_mode)
  local cand = {}
  if initial_mode then
    for i = 1, #q do
      local ch = q:sub(i, i)
      local list = idx.by_init_letter[ch]
      if list then
        for _, id in ipairs(list) do cand[id] = true end
      end
    end
    local first = q:sub(1, 1)
    local list = idx.by_first[first]
    if list then
      for _, id in ipairs(list) do cand[id] = true end
    end
  else
    local first = q:sub(1, 1)
    local list = idx.by_first[first]
    if list then
      for _, id in ipairs(list) do cand[id] = true end
    end
    local cf = canon_input(first, cfg.fuzzy):sub(1, 1)
    if cf ~= first then
      list = idx.by_first[cf]
      if list then
        for _, id in ipairs(list) do cand[id] = true end
      end
    end
  end
  return cand
end

-- 中段关键词召回：用输入首块的 3/2 字母前缀查 by_syl_prefix。
-- 单字母音节只有 a/e/o；若首字母是它们，或 2/3 字母键没有召回，
-- 再补 1 字母键（如 aan -> a + an）。
local function collect_syllable_keyword(q, idx)
  local cand = {}
  local maxk = math.min(3, #q)
  for k = maxk, 2, -1 do
    local list = idx.by_syl_prefix[q:sub(1, k)]
    if list then
      for _, id in ipairs(list) do
        cand[id] = true
      end
    end
  end

  local first = q:sub(1, 1)
  local add_one = (first == "a" or first == "e" or first == "o")
    or next(cand) == nil
  if add_one then
    local list = idx.by_syl_prefix[first]
    if list then
      for _, id in ipairs(list) do
        cand[id] = true
      end
    end
  end
  return cand
end

local function add_result(results, pos, id, p, r)
  local at = pos[id]
  if at then
    if r.score > results[at].score then
      results[at] = r
    end
  else
    results[#results + 1] = r
    pos[id] = #results
  end
end

-- 统计输入与全库共享的双字母/三字母数量，用于 DP 前的候选排序。
-- 使用逐音节模糊规范化后的索引，ng→n、zh→z 等才能正确计分。
local function build_hit_maps(q, idx)
  local bg, tg = {}, {}
  local bmap = idx.by_canon_bigram or idx.by_bigram
  local tmap = idx.by_canon_trigram or idx.by_trigram
  for k = 1, #q - 1 do
    local list = bmap[q:sub(k, k + 1)]
    if list then
      for _, id in ipairs(list) do
        bg[id] = (bg[id] or 0) + 1
      end
    end
  end
  for k = 1, #q - 2 do
    local list = tmap[q:sub(k, k + 2)]
    if list then
      for _, id in ipairs(list) do
        tg[id] = (tg[id] or 0) + 1
      end
    end
  end
  return bg, tg
end

local function overlap_score(id, p, bg, tg, qfirst, qlast, qlen)
  local s = (bg[id] or 0) * 2 + (tg[id] or 0) * 4
  if p._firsts[qfirst] then s = s + 2 end
  if p._lasts[qlast] then s = s + 2 end
  return s - 0.10 * math.abs(qlen - #p.primary_full)
end

local function fill_static(results, pos, phrases, idx, q, cfg, top_n)
  local need = top_n - #results
  if need <= 0 then
    return
  end
  local fuzzy = cfg.fuzzy
  for _, id in ipairs(idx.static_top) do
    if not pos[id] then
      local p = phrases[id]
      local fs = fallback_similarity(q, p, fuzzy, cfg)
      results[#results + 1] = {
        index = id,
        phrase = p,
        score = fs * (cfg.weights.fallback or 0.55) + 0.0001 * (p.w or 1.0),
        raw = fs,
        channel = "fallback",
        detail = "static",
      }
      pos[id] = #results
      need = need - 1
      if need <= 0 then
        break
      end
    end
  end
end

-- 最后一级回退：先用 canonical bigram/trigram 和首字母召回候选，
-- 按重叠度取短名单，再用 Damerau + Dice-LCS 排序。
-- 不再按 static_top 的固定顺序取前 N 个；静态顺序只作为兜底。
local function fill_fallback(results, pos, phrases, idx, q, cfg, top_n, bg, tg)
  local need = top_n - #results
  if need <= 0 then
    return
  end
  if #q == 0 then
    fill_static(results, pos, phrases, idx, q, cfg, top_n)
    return
  end

  local fuzzy = cfg.fuzzy

  -- 已有强命中时只做小池，避免为补足 9 个候选拖慢每一次正常按键。
  local strong_raw = (cfg.fallback and cfg.fallback.strong_raw) or 0.70
  local strong = false
  for i = 1, #results do
    local r = results[i]
    if r.channel ~= "fallback" and (r.raw or 0) >= strong_raw then
      strong = true
      break
    end
  end

  local have_ngram = (not strong) and bg and tg
  if not have_ngram and not strong and #q >= 2 then
    bg, tg = build_hit_maps(q, idx)
    have_ngram = true
  end
  if not have_ngram then
    bg, tg = EMPTY, EMPTY
  end

  local qfirst, qlast, qlen = q:sub(1, 1), q:sub(-1), #q
  local ids = {}
  for id in pairs(bg) do
    if not pos[id] then ids[id] = true end
  end
  for id in pairs(tg) do
    if not pos[id] then ids[id] = true end
  end

  local first = qfirst
  local list = idx.by_first[first]
  if list then
    for _, id in ipairs(list) do
      if not pos[id] then ids[id] = true end
    end
  end
  local cfirst = canon_input(first, fuzzy):sub(1, 1)
  if cfirst ~= first then
    list = idx.by_first[cfirst]
    if list then
      for _, id in ipairs(list) do
        if not pos[id] then ids[id] = true end
      end
    end
  end

  if next(ids) == nil then
    fill_static(results, pos, phrases, idx, q, cfg, top_n)
    return
  end

  -- 先用双/三字母重叠度把池子压到 max_candidates，再算较贵的相似度。
  local ranked = {}
  for id in pairs(ids) do
    ranked[#ranked + 1] = {
      id = id,
      hint = overlap_score(id, phrases[id], bg, tg, qfirst, qlast, qlen),
    }
  end
  table.sort(ranked, function(a, b)
    if math.abs(a.hint - b.hint) > 1e-9 then
      return a.hint > b.hint
    end
    return a.id < b.id
  end)

  local limit
  if strong then
    limit = (cfg.fallback and cfg.fallback.fast_max_candidates) or 16
  else
    limit = (cfg.fallback and cfg.fallback.max_candidates) or 96
  end
  if limit < 8 then limit = 8 end
  if limit > 500 then limit = 500 end

  local scored = {}
  for i = 1, math.min(limit, #ranked) do
    local id = ranked[i].id
    local p = phrases[id]
    local fs = fallback_similarity(q, p, fuzzy, cfg, strong)
    scored[#scored + 1] = {
      index = id,
      phrase = p,
      score = fs * (cfg.weights.fallback or 0.55) + 0.0001 * (p.w or 1.0),
      raw = fs,
      channel = "fallback",
      detail = "neighbor",
    }
  end
  table.sort(scored, function(a, b)
    return compare_results(a, b, cfg.score_epsilon)
  end)

  for i = 1, math.min(need, #scored) do
    local r = scored[i]
    add_result(results, pos, r.index, r.phrase, r)
  end

  if #results < top_n then
    fill_static(results, pos, phrases, idx, q, cfg, top_n)
  end
end

-- 主入口：input 为原始输入串，phrases 为数据表，opts 为配置覆盖。
function M.rank(input, phrases, opts)
  local cfg = M.options(opts)
  local q = M.normalize(input)
  local top_n = math.max(1, cfg.top_n or 9)
  local idx = build_index(phrases, cfg)

  -- 空输入：静态优先序，保证仍然有 N 个候选。
  if #q == 0 then
    local out = {}
    for i = 1, math.min(top_n, #idx.static_top) do
      local id = idx.static_top[i]
      local p = phrases[id]
      out[i] = {
        index = id,
        phrase = p,
        score = p.w or 1.0,
        raw = 0,
        channel = "fallback",
        detail = "empty",
      }
    end
    return out
  end

  local fuzzy = cfg.fuzzy
  local qcanon = canon_input(q, fuzzy)
  -- 声母/关键词模式：全无元音，或很短的输入里最多一个元音。
  -- 不用“元音占比”判断，避免把 xingyun / zhongguo 这类正常全拼误判为缩写。
  local vowel_count = count_vowels(q)
  local initial_mode = (#q >= 2 and (vowel_count == 0 or (#q <= 6 and vowel_count <= 1)))
  local cache = {}
  local results = {}
  local pos = {}
  local bg, tg

  -- 阶段 1：廉价通道（精确/前缀/模糊/声母/换位），不跑 DP。
  local primary = collect_primary(q, idx, cfg, initial_mode)
  local best_cheap_raw = 0
  for id in pairs(primary) do
    local p = phrases[id]
    local r = score_phrase(q, qcanon, p, cfg, initial_mode, false, false, cache)
    if r then
      r.index = id
      r.phrase = p
      add_result(results, pos, id, p, r)
      if r.raw > best_cheap_raw then
        best_cheap_raw = r.raw
      end
    end
  end

  -- 阶段 2：只有廉价通道没有足够强的结果时才跑 DP。
  -- 候选先用双/三字母重叠度排序，只对 Top-K 做音节对齐。
  local need_dp = (not initial_mode) and best_cheap_raw < 0.93 and #q >= 2
  if need_dp then
    bg, tg = build_hit_maps(q, idx)
    local cand = {}
    for id in pairs(primary) do cand[id] = true end
    for id in pairs(bg) do cand[id] = true end
    for id in pairs(tg) do cand[id] = true end

    local qfirst, qlast = q:sub(1, 1), q:sub(-1)
    local ranked = {}
    for id in pairs(cand) do
      ranked[#ranked + 1] = {
        id = id,
        ov = overlap_score(id, phrases[id], bg, tg, qfirst, qlast, #q),
      }
    end
    table.sort(ranked, function(a, b)
      if math.abs(a.ov - b.ov) > 1e-9 then
        return a.ov > b.ov
      end
      return a.id < b.id
    end)

    local limit = math.min(cfg.dp_max_candidates or 64, #ranked)
    for i = 1, limit do
      local id = ranked[i].id
      local p = phrases[id]
      local r = score_phrase(q, qcanon, p, cfg, initial_mode, true, true, cache)
      if r then
        r.index = id
        r.phrase = p
        add_result(results, pos, id, p, r)
      end
    end
  end

  -- 阶段 3：音节前缀子序列（词条中段关键词）。
  -- 独立于 DP 短名单和“廉价通道是否足够强”的判断：高 raw/低权重的
  -- 关键词不应阻断 DP，也不应因为没有走 DP 而漏掉中段命中。
  if cfg.keyword.syllable_subsequence ~= false and not initial_mode
      and #q >= 2 and best_cheap_raw < 0.99 then
    local kw_cand = collect_syllable_keyword(q, idx)
    local kw_weight = channel_weight(cfg, "keyword", initial_mode)
    for id in pairs(kw_cand) do
      local p = phrases[id]
      local raw = syllable_keyword_score(q, p, fuzzy, cfg)
      if raw > 0 then
        add_result(results, pos, id, p, {
          index = id,
          phrase = p,
          score = raw * kw_weight + 0.0001 * (p.w or 1.0),
          raw = raw,
          channel = "keyword",
          detail = "syllable",
        })
      end
    end
  end

  if #results < top_n then
    fill_fallback(results, pos, phrases, idx, q, cfg, top_n, bg, tg)
  end

  table.sort(results, function(a, b)
    return compare_results(a, b, cfg.score_epsilon)
  end)

  local out = {}
  for i = 1, math.min(top_n, #results) do
    out[i] = results[i]
  end
  return out
end

-- 预编辑缩写回退用：合法拼音声母（含双字母声母）。
local PREEDIT_INITIALS = {
  b = true, p = true, m = true, f = true, d = true, t = true,
  n = true, l = true, g = true, k = true, h = true, j = true,
  q = true, x = true, zh = true, ch = true, sh = true,
  r = true, z = true, c = true, s = true, y = true, w = true,
}

-- 把纯声母串切成声母序列（zh/ch/sh 优先）；含非声母字符时返回 nil。
local function split_initials(s)
  local out = {}
  local i = 1
  while i <= #s do
    local two = s:sub(i, i + 1)
    if PREEDIT_INITIALS[two] then
      out[#out + 1] = two
      i = i + 2
    else
      local one = s:sub(i, i)
      if not PREEDIT_INITIALS[one] then
        return nil
      end
      out[#out + 1] = one
      i = i + 1
    end
  end
  if #out < 2 then
    return nil
  end
  return out
end

-- 预测输入的音节边界，只用于 preedit 显示。
-- 例：diou -> di'ou，shenluo -> shen'luo，nd -> n'd，lkcc -> l'k'c'c。
-- 若首个候选的完整读音恰好等于输入，优先采用它的音节切分。
function M.preview(input, phrases, opts, hint)
  local cfg = M.options(opts)
  local s = M.normalize(input)
  local L = #s
  if L == 0 then
    return ""
  end
  if not cfg.preedit or cfg.preedit.enabled == false then
    return s
  end
  local sep = cfg.preedit.separator or "'"

  local hint_phrase = hint
  local hint_channel = nil
  if type(hint) == "table" and hint.phrase then
    hint_phrase = hint.phrase
    hint_channel = hint.channel
  end

  if hint_phrase and hint_phrase.syls and #hint_phrase.syls > 0 then
    local full = table.concat(hint_phrase.syls)
    if full == s then
      return table.concat(hint_phrase.syls, sep)
    end
  end

  local idx = build_index(phrases, cfg)
  local syllables, maxlen = idx.syllables, idx.max_syllable
  if not syllables or maxlen < 1 then
    return s
  end

  -- best[i]：覆盖前 i 个字符的最优切分；先最大化覆盖，再最小化音节数。
  local best = { [0] = { pieces = 0, prev = -1, take = 0 } }
  for i = 0, L - 1 do
    local cur = best[i]
    if cur then
      for k = 1, math.min(maxlen, L - i) do
        local sub = s:sub(i + 1, i + k)
        if syllables[sub] or syllables[canon_syllable(sub, cfg.fuzzy)] then
          local j = i + k
          local cand = { pieces = cur.pieces + 1, prev = i, take = k }
          local prev = best[j]
          if not prev
              or cand.pieces < prev.pieces
              or (cand.pieces == prev.pieces and k > prev.take) then
            best[j] = cand
          end
        end
      end
    end
  end

  -- 输入可能还没打完（shenl / shenlu）。允许最后一个未完成音节作为尾巴，
  -- 只要它是某个合法音节的前缀；否则如果剩余部分全是声母（nd / lkcc），
  -- 按声母逐个分段。两者都不成立时保持原样。
  local end_pos = L
  local tail = nil
  -- 只有输入命中了非 fallback 候选时才启用声母缩写分段，避免把
  -- asdfghjkl / zzzzzz 这类噪声也切成一个个字母。
  local allow_initials = hint_channel ~= "fallback"
  if not best[L] then
    for i = L - 1, 0, -1 do
      local suffix = s:sub(i + 1)
      if best[i] then
        if idx.syllable_prefixes[suffix] then
          end_pos = i
          tail = suffix
          break
        end
        local initials = allow_initials and split_initials(suffix) or nil
        if initials then
          end_pos = i
          tail = table.concat(initials, sep)
          break
        end
      end
    end
    if not tail then
      return s
    end
  end

  local parts = {}
  local pos = end_pos
  while pos and pos > 0 do
    local node = best[pos]
    parts[#parts + 1] = s:sub(node.prev + 1, pos)
    pos = node.prev
  end
  local out = {}
  for i = #parts, 1, -1 do
    out[#out + 1] = parts[i]
  end
  if tail then
    out[#out + 1] = tail
  end
  return table.concat(out, sep)
end

-- 为整张表做一次预计算并建立索引。返回 phrases 便于链式调用。
function M.prepare_all(phrases, opts)
  local cfg = M.options(opts)
  build_index(phrases, cfg)
  return phrases
end

-- 测试/诊断钩子：不参与正式调用。
M._build_hit_maps = build_hit_maps
M._overlap_score = overlap_score
M._collect_primary = collect_primary

return M
