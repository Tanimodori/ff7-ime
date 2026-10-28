-- mgjy_matcher.lua
-- 魔光键影 · 纯 Lua 匹配与排序核心。
--
-- 本文件不依赖 Rime / Lua 标准库之外的任何东西，便于用独立 Lua 5.4 沙箱做回归。
-- 输入：无调全拼字母串；输出：按匹配度排序的候选（含通道与分数）。
--
-- 设计要点：
--   1. 精确全拼 > 模糊全拼 > 前缀 > 音节对齐 > 声母 > 关键词 > 最近邻回退。
--   2. 音节级对齐 DP 负责漏字、多字、相邻换位、音节前缀；
--      声母子序列负责 lkcc 这类关键词缩写。
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
  for j = 0, lb do
    prev[j] = j
  end

  for i = 1, la do
    cur[0] = i
    local ca = a:sub(i, i)
    local ca_prev = a:sub(i - 1, i - 1)
    for j = 1, lb do
      local cb = b:sub(j, j)
      local cost = (ca == cb) and 0 or 1
      local v = math.min(
        prev[j] + 1,
        cur[j - 1] + 1,
        prev[j - 1] + cost
      )
      if transposition and i > 1 and j > 1
          and ca == b:sub(j - 1, j - 1)
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
  if p._mgjy_prepared then
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

  p._mgjy_prepared = true
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
  for _, v in ipairs(p.init_variants) do
    local flat = {}
    for i, tok in ipairs(v.tokens) do
      local text = type(tok) == "table" and (tok.s or tok[1]) or tok
      flat[i] = initial_of(text)
    end
    local s0 = table.concat(flat)
    local d = edit_distance(input, s0, true)
    local s = 0.88 * (1 - d / math.max(#input, #s0))
    if s > best then best = s end
  end
  if best < 0 then best = 0 end
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
    consider(dp_score(q, p, fuzzy, cfg, cache, cfg.typo.strict == true or cfg.typo.enabled == false), "dp", "align")
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
  if phrases._mgjy_index and phrases._mgjy_index_key == key then
    return phrases._mgjy_index
  end
  if phrases._mgjy_index_key and phrases._mgjy_index_key ~= key then
    for _, p in ipairs(phrases) do
      p._mgjy_prepared = nil
    end
    phrases._mgjy_index = nil
  end

  local idx = {
    by_first = {},
    by_init_letter = {},
    by_bigram = {},
    by_trigram = {},
    by_canon_bigram = {},
    by_canon_trigram = {},
    by_full = {},
    by_canon = {},
    static_top = {},
  }

  for id, p in ipairs(phrases) do
    prepare_phrase(p, cfg.fuzzy, cfg.typo)

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

  phrases._mgjy_index = idx
  phrases._mgjy_index_key = key
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

local function collect_second(q, idx, scored)
  local cand = {}
  if #q < 2 then
    return cand
  end

  -- 统计每个候选与输入的共享双字母/三字母数。
  -- 双字母至少 2 个；输入 >=4 时还要求至少 1 个三字母，进一步压低噪声。
  local hits = {}
  for k = 1, #q - 1 do
    local bg = q:sub(k, k + 1)
    local list = idx.by_bigram[bg]
    if list then
      for _, id in ipairs(list) do
        if not scored[id] then
          hits[id] = (hits[id] or 0) + 1
        end
      end
    end
  end

  local tri = {}
  if #q >= 4 then
    for k = 1, #q - 2 do
      local tg = q:sub(k, k + 2)
      local list = idx.by_trigram[tg]
      if list then
        for _, id in ipairs(list) do
          if not scored[id] then
            tri[id] = (tri[id] or 0) + 1
          end
        end
      end
    end
  end

  local min_hits = (#q >= 4) and 2 or 1
  for id, n in pairs(hits) do
    if n >= min_hits and (#q < 4 or (tri[id] or 0) >= 1) then
      cand[id] = true
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
      local fs = fallback_score(q, p, fuzzy)
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
    local bg, tg = build_hit_maps(q, idx)
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

  if #results < top_n then
    fill_static(results, pos, phrases, idx, q, cfg, top_n)
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
