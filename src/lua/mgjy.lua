-- mgjy.lua
-- 魔光键影 · Rime Lua translator 适配层。
--
-- 职责：
--   1. 加载构建期生成的 mgjy_data.lua；
--   2. 从 schema 配置与 switches 读取 top_n / 模糊音 / 权重 / 容错开关；
--   3. 调用 mgjy_matcher.lua 得到 Top-N，并 yield 为 Rime Candidate。
--
-- 约定：lua_translator@*mgjy 会 require 本文件；本文件返回带 init/func 的表。

local matcher = require("mgjy_matcher")
local data = require("mgjy_data")

local M = {}

local CHANNEL_LABEL = {
  exact = "全拼",
  fuzzy = "模糊",
  prefix = "前缀",
  fuzzy_prefix = "模糊前缀",
  swap = "换位",
  dp = "容错",
  initial_exact = "声母",
  initial = "声母",
  keyword = "关键词",
  fallback = "回退",
}

local FUZZY_KEYS = {
  { key = "zh_z", switch = "mgjy_fuzzy_zh_z" },
  { key = "ch_c", switch = "mgjy_fuzzy_ch_c" },
  { key = "sh_s", switch = "mgjy_fuzzy_sh_s" },
  { key = "ng_n", switch = "mgjy_fuzzy_ng_n" },
  { key = "n_l", switch = "mgjy_fuzzy_n_l" },
  { key = "r_l", switch = "mgjy_fuzzy_r_l" },
  { key = "f_h", switch = "mgjy_fuzzy_f_h" },
  { key = "en_eng", switch = "mgjy_fuzzy_en_eng" },
  { key = "in_ing", switch = "mgjy_fuzzy_in_ing" },
  { key = "an_ang", switch = "mgjy_fuzzy_an_ang" },
  { key = "uan_uang", switch = "mgjy_fuzzy_uan_uang" },
  { key = "v_u", switch = "mgjy_fuzzy_v_u" },
}

local WEIGHT_KEYS = {
  "exact", "fuzzy", "fuzzy_prefix", "prefix", "swap",
  "dp", "initial_exact", "initial", "keyword", "fallback",
}

local fallback_order = {}

local function config_of(env)
  local engine = env and env.engine
  local schema = engine and engine.schema
  return schema and schema.config or nil
end

local function context_of(env)
  local engine = env and env.engine
  return engine and engine.context or nil
end

local function cfg_bool(config, path)
  if not config then return nil end
  local ok, v = pcall(function() return config:get_bool(path) end)
  if ok then return v end
  return nil
end

local function cfg_int(config, path)
  if not config then return nil end
  local ok, v = pcall(function() return config:get_int(path) end)
  if ok then return v end
  return nil
end

local function cfg_double(config, path)
  if not config then return nil end
  local ok, v = pcall(function() return config:get_double(path) end)
  if ok then return v end
  return nil
end

local function switch_value(env, name, enabled)
  if not enabled then return nil end
  local ctx = context_of(env)
  if not ctx then return nil end
  local ok, v = pcall(function() return ctx:get_option(name) end)
  if ok then return v end
  return nil
end

local function build_options(env)
  local config = config_of(env)
  local defaults = matcher.defaults

  local use_switches = cfg_bool(config, "mgjy/use_switches")
  if use_switches == nil then use_switches = false end

  local top_n = cfg_int(config, "mgjy/top_n") or defaults.top_n
  if top_n < 1 then top_n = 1 end
  if top_n > 64 then top_n = 64 end

  local dp_max = cfg_int(config, "mgjy/dp_max_candidates") or defaults.dp_max_candidates
  if dp_max < 8 then dp_max = 8 end
  if dp_max > 500 then dp_max = 500 end

  local fuzzy = {}
  for _, item in ipairs(FUZZY_KEYS) do
    -- use_switches=true 时 F4 开关优先；否则以 mgjy/fuzzy/* 配置为准。
    local v = switch_value(env, item.switch, use_switches)
    if v == nil then
      v = cfg_bool(config, "mgjy/fuzzy/" .. item.key)
    end
    if v == nil then
      v = defaults.fuzzy[item.key]
    end
    fuzzy[item.key] = v
  end

  local weights = {}
  for _, key in ipairs(WEIGHT_KEYS) do
    local v = cfg_double(config, "mgjy/weights/" .. key)
    if v == nil then
      v = defaults.weights[key]
    end
    weights[key] = v
  end

  local typo_enabled = nil
  if use_switches then
    typo_enabled = switch_value(env, "mgjy_typo", true)
  end
  if typo_enabled == nil then
    typo_enabled = cfg_bool(config, "mgjy/typo/enabled")
  end
  if typo_enabled == nil then typo_enabled = true end
  local max_edit = cfg_int(config, "mgjy/typo/max_edit")
  if max_edit == nil then max_edit = defaults.typo.max_edit end
  if max_edit < 0 then max_edit = 0 end
  if max_edit > 4 then max_edit = 4 end
  if not typo_enabled then max_edit = 0 end

  local transposition = cfg_bool(config, "mgjy/typo/transposition")
  if transposition == nil then transposition = defaults.typo.transposition end
  if not typo_enabled then transposition = false end

  local syllable_swap = cfg_bool(config, "mgjy/typo/syllable_swap")
  if syllable_swap == nil then syllable_swap = defaults.typo.syllable_swap end
  if not typo_enabled then syllable_swap = false end

  local initial_enabled = nil
  if use_switches then
    initial_enabled = switch_value(env, "mgjy_initial", true)
  end
  if initial_enabled == nil then
    initial_enabled = cfg_bool(config, "mgjy/initial/enabled")
  end
  if initial_enabled == nil then initial_enabled = true end

  local gap_penalty = cfg_double(config, "mgjy/keyword/gap_penalty")
  if gap_penalty == nil then gap_penalty = defaults.keyword.gap_penalty end

  local syllable_subsequence = cfg_bool(config, "mgjy/keyword/syllable_subsequence")
  if syllable_subsequence == nil then
    syllable_subsequence = defaults.keyword.syllable_subsequence
  end

  local show_comment = cfg_bool(config, "mgjy/show_comment")
  if show_comment == nil then show_comment = true end

  local show_score = cfg_bool(config, "mgjy/show_score")
  if show_score == nil then show_score = false end

  local debug = cfg_bool(config, "mgjy/debug")
  if debug == nil then debug = false end

  return {
    top_n = top_n,
    dp_max_candidates = dp_max,
    fuzzy = fuzzy,
    weights = weights,
    typo = {
      enabled = typo_enabled,
      strict = not typo_enabled,
      max_edit = max_edit,
      transposition = transposition,
      syllable_swap = syllable_swap,
    },
    initial = { enabled = initial_enabled },
    keyword = {
      gap_penalty = gap_penalty,
      syllable_subsequence = syllable_subsequence,
    },
    show_comment = show_comment,
    show_score = show_score,
    debug = debug,
  }
end

local function build_fallback_order(phrases)
  local order = {}
  for i, p in ipairs(phrases) do
    order[#order + 1] = i
  end
  table.sort(order, function(a, b)
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
  return order
end

local function fallback_results(top_n)
  local out = {}
  local n = math.min(top_n, #fallback_order)
  for i = 1, n do
    local p = data[fallback_order[i]]
    out[i] = {
      phrase = p,
      score = 0,
      raw = 0,
      channel = "fallback",
      detail = "error",
    }
  end
  return out
end

local function truncate_pinyin(syls, max_len)
  local out = {}
  local n = 0
  for _, s in ipairs(syls) do
    if n > 0 and n + #s + 1 > max_len then
      break
    end
    out[#out + 1] = s
    n = n + #s + 1
  end
  local text = table.concat(out, " ")
  if #out < #syls then
    text = text .. "…"
  end
  return text
end

local function format_comment(result, opts)
  if not opts.show_comment then
    return ""
  end
  local label = CHANNEL_LABEL[result.channel] or result.channel or ""
  local p = result.phrase
  -- 命中非主读音（多音字/允许误读）时给出提示，避免“输入 chongli 却显示 zhong li”的困惑。
  if result.channel == "exact" and result.detail
      and result.detail ~= p.primary_full then
    label = label .. "·异读"
  end
  local py = truncate_pinyin(p.syls or {}, 28)
  if opts.show_score then
    return string.format("%s · %s · %.2f", label, py, result.score or 0)
  end
  return label .. " · " .. py
end

function M.init(env)
  local opts = build_options(env)
  local ok = pcall(matcher.prepare_all, data, opts)
  if not ok then
    -- 配置异常不应让方案完全不可用；用默认配置再试一次。
    pcall(matcher.prepare_all, data, matcher.defaults)
  end
  fallback_order = build_fallback_order(data)
end

function M.func(input, seg, env)
  local opts = build_options(env)
  local ok, results = pcall(matcher.rank, input, data, opts)
  if not ok or not results or #results == 0 then
    results = fallback_results(opts.top_n)
  end

  local start_pos = seg.start or 0
  local end_pos = seg._end
  if not end_pos then
    end_pos = start_pos + #input
  end

  local total = #results
  for i = 1, total do
    local r = results[i]
    local cand = Candidate("mgjy", start_pos, end_pos, r.phrase.text, format_comment(r, opts))
    -- 同一 segment 内按 yield 顺序稳定排序：quality 越高越靠前。
    pcall(function()
      cand.quality = (total - i + 1) * 0.001
    end)
    yield(cand)
  end
end

return M
