-- moguang_jianying.lua
-- 魔光键影 / moguang_jianying 的 Lua translator 骨架。
--
-- 放置位置：
--   %APPDATA%\Rime\lua\moguang_jianying.lua
--
-- schema 中通过 lua_translator@*moguang_jianying 自动 require 本文件。
-- 本文件返回一个 table：{ init = init, func = translate }。
--
-- 设计约束（与 schema 配套）：
--   * 只有 tag 为 abc 的 segment 才处理；punct/raw/uppercase 等直接跳过。
--   * 不写用户词典、不造句、不做简繁转换；只从数据文件读取固定词条。
--   * 词条文本原样输出，包含 ！，·…… 等标点。
--
-- 数据文件格式（UTF-8，Tab 分隔，一行一条，空行和 # 开头行忽略）：
--   code <TAB> text <TAB> comment <TAB> initials <TAB> keywords
-- 其中 comment / initials / keywords 可省略。keywords 用英文逗号分隔，
-- 建议写拉丁字母别名（例如 cloud），因为输入始终是纯字母。
-- 例：
--   luokekelao	洛克克劳德	luo ke ke lao de	lkld	cloud
--
-- 本文件只实现“结构验证级”的匹配（全拼/简拼/关键词/一次编辑距离）。
-- 正式算法请替换 match_entries()，保持 init/translate 接口不变即可。

local M = {}

-- ---------------------------------------------------------------------------
-- 小工具
-- ---------------------------------------------------------------------------

local function cfg_int(config, key, default)
  local v = config:get_int("moguang_jianying/" .. key)
  if v == nil then return default end
  return v
end

local function cfg_bool(config, key, default)
  local v = config:get_bool("moguang_jianying/" .. key)
  if v == nil then return default end
  return v
end

local function cfg_str(config, key, default)
  local v = config:get_string("moguang_jianying/" .. key)
  if v == nil or v == "" then return default end
  return v
end

local function split_tab(line)
  local fields = {}
  local start = 1
  while true do
    local pos = string.find(line, "\t", start, true)
    if not pos then
      fields[#fields + 1] = string.sub(line, start)
      break
    end
    fields[#fields + 1] = string.sub(line, start, pos - 1)
    start = pos + 1
  end
  return fields
end

local function strip_bom(s)
  if string.sub(s, 1, 3) == "\239\187\191" then
    return string.sub(s, 4)
  end
  return s
end

-- 把输入和词条 code 归一化到同一个“模糊等价类”。
-- 注意：这是骨架级实现，按字符串替换处理，不理解音节边界；
-- 正式算法应当按音节/声母韵母展开，而不是无脑 gsub。
local function canonical(s, opt)
  s = string.lower(s)
  if opt.fuzzy_zh_z then s = string.gsub(s, "zh", "z") end
  if opt.fuzzy_ch_c then s = string.gsub(s, "ch", "c") end
  if opt.fuzzy_sh_s then s = string.gsub(s, "sh", "s") end
  if opt.fuzzy_en_eng then s = string.gsub(s, "eng", "en") end
  if opt.fuzzy_in_ing then s = string.gsub(s, "ing", "in") end
  if opt.fuzzy_ng_n then s = string.gsub(s, "ng", "n") end
  if opt.fuzzy_r_l then s = string.gsub(s, "r", "l") end
  if opt.fuzzy_n_l then s = string.gsub(s, "l", "n") end
  if opt.fuzzy_f_h then s = string.gsub(s, "f", "h") end
  return s
end

-- 只允许编辑距离 0 或 1，避免引入明显的噪声。
local function within_one_edit(a, b)
  local la, lb = #a, #b
  if math.abs(la - lb) > 1 then return false end
  if la == lb then
    local diff = 0
    for i = 1, la do
      if string.sub(a, i, i) ~= string.sub(b, i, i) then
        diff = diff + 1
        if diff > 1 then return false end
      end
    end
    return true
  end
  local longer, shorter = a, b
  if la < lb then longer, shorter = b, a end
  local i, j, skipped = 1, 1, false
  while i <= #shorter and j <= #longer do
    if string.sub(shorter, i, i) == string.sub(longer, j, j) then
      i = i + 1
      j = j + 1
    else
      if skipped then return false end
      skipped = true
      j = j + 1
    end
  end
  return true
end

local function read_options(ctx)
  return {
    fuzzy_zh_z   = ctx:get_option("fuzzy_zh_z"),
    fuzzy_ch_c   = ctx:get_option("fuzzy_ch_c"),
    fuzzy_sh_s   = ctx:get_option("fuzzy_sh_s"),
    fuzzy_ng_n   = ctx:get_option("fuzzy_ng_n"),
    fuzzy_n_l    = ctx:get_option("fuzzy_n_l"),
    fuzzy_r_l    = ctx:get_option("fuzzy_r_l"),
    fuzzy_f_h    = ctx:get_option("fuzzy_f_h"),
    fuzzy_en_eng = ctx:get_option("fuzzy_en_eng"),
    fuzzy_in_ing = ctx:get_option("fuzzy_in_ing"),
    keyword_mode = ctx:get_option("keyword_mode"),
    initial_mode = ctx:get_option("initial_mode"),
    typo_mode    = ctx:get_option("typo_mode"),
  }
end

-- ---------------------------------------------------------------------------
-- 数据加载
-- ---------------------------------------------------------------------------

local function load_tsv(path)
  local f, err = io.open(path, "r")
  if not f then
    return nil, err
  end
  local entries = {}
  local line_no = 0
  for line in f:lines() do
    line_no = line_no + 1
    if line_no == 1 then line = strip_bom(line) end
    if line ~= "" and string.sub(line, 1, 1) ~= "#" then
      local fields = split_tab(line)
      local code = fields[1]
      local text = fields[2]
      if code and text and code ~= "" and text ~= "" then
        entries[#entries + 1] = {
          code = string.lower(code),
          text = text,
          comment = fields[3] or "",
          initials = string.lower(fields[4] or ""),
          keywords = fields[5] or "",
        }
      end
    end
  end
  f:close()
  return entries
end

local function load_entries(env, config)
  local data_file = cfg_str(config, "data_file", "moguang_jianying_data.tsv")
  local path = data_file
  local third = string.sub(data_file, 3, 3)
  local is_absolute = (string.sub(data_file, 2, 2) == ":" and
                       (third == "/" or third == "\\")) or
                      string.sub(data_file, 1, 1) == "/"
  if not is_absolute then
    local dir = rime_api.get_user_data_dir()
    path = dir .. "/" .. data_file
  end
  local entries, err = load_tsv(path)
  if not entries then
    log.error("moguang_jianying: cannot open data file '" .. path .. "': " .. tostring(err))
    return {}
  end
  log.info("moguang_jianying: loaded " .. tostring(#entries) .. " entries from " .. path)
  return entries
end

-- ---------------------------------------------------------------------------
-- 匹配
-- ---------------------------------------------------------------------------

-- 返回若干 { entry = e, rank = n, order = i }。
-- rank 越小越靠前：0 全拼精确，1 简拼，2 关键词，3 容错。
local function match_entries(input, entries, opt)
  local key = canonical(input, opt)
  local results = {}

  for i, e in ipairs(entries) do
    local code = canonical(e.code, opt)
    local rank = nil

    if code == key then
      rank = 0
    elseif opt.initial_mode and e.initials ~= "" and
           canonical(e.initials, opt) == key then
      rank = 1
    elseif opt.keyword_mode and e.keywords ~= "" then
      for kw in string.gmatch(e.keywords, "[^,]+") do
        local k = canonical(kw, opt)
        if k == key then
          rank = 2
          break
        end
      end
    end

    if rank == nil and opt.typo_mode and #key >= 3 then
      if within_one_edit(code, key) then
        rank = 3
      end
    end

    if rank ~= nil then
      results[#results + 1] = { entry = e, rank = rank, order = i }
    end
  end

  table.sort(results, function(a, b)
    if a.rank ~= b.rank then return a.rank < b.rank end
    return a.order < b.order
  end)

  return results
end

-- ---------------------------------------------------------------------------
-- 生命周期
-- ---------------------------------------------------------------------------

local function init(env)
  local config = env.engine.schema.config
  env.cfg = {
    top_n = math.max(1, math.min(cfg_int(config, "top_n", 10), 100)),
    show_comment = cfg_bool(config, "show_comment", true),
    min_input_length = cfg_int(config, "min_input_length", 1),
    max_input_length = cfg_int(config, "max_input_length", 32),
  }
  env.entries = load_entries(env, config)
end

local function translate(input, seg, env)
  -- 关键过滤：Rime 会对每个 segment 调用所有 translator，tag 过滤必须自己做。
  if not seg:has_tag("abc") then
    return
  end
  -- 纯字母保护（speller 已经做了，但这里再兜一层）。
  if not string.match(input, "^[A-Za-z]+$") then
    return
  end
  local ctx = env.engine.context
  if ctx:get_option("ascii_mode") then
    return
  end
  if #input < env.cfg.min_input_length or #input > env.cfg.max_input_length then
    return
  end

  local opt = read_options(ctx)
  local results = match_entries(input, env.entries, opt)
  if #results == 0 then
    return
  end

  local shown = {}
  local count = 0
  for _, r in ipairs(results) do
    local e = r.entry
    -- 不用 uniquifier，这里自己按文本去重，保留第一次出现的注释。
    if not shown[e.text] then
      shown[e.text] = true
      local comment = ""
      if env.cfg.show_comment then comment = e.comment end
      yield(Candidate("moguang", seg.start, seg._end, e.text, comment))
      count = count + 1
      if count >= env.cfg.top_n then break end
    end
  end
end

M.init = init
M.func = translate

return M
