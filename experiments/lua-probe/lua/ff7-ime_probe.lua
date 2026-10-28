-- ff7-ime_probe.lua
-- 魔光键影 librime-lua 运行时探针（主 translator）
--
-- 部署位置：<user_data_dir>/lua/ff7-ime_probe.lua
-- schema 写法：- lua_translator@*ff7-ime_probe
--   * 前缀 = require("ff7-ime_probe")；不带 * 则查找全局变量 ff7-ime_probe。

local M = {}
local TAG = "[ff7-ime_probe]"

local function logf(fmt, ...)
  local ok, s = pcall(string.format, fmt, ...)
  if not ok then s = tostring(fmt) end
  log.info(TAG .. " " .. s)
end

-- 只用于诊断，不包含 yield
local function try(label, fn)
  local ok, a, b = pcall(fn)
  if ok then
    logf("%s => ok | %s | %s", label, tostring(a), tostring(b))
  else
    logf("%s => ERROR | %s", label, tostring(a))
  end
  return ok, a, b
end

function M.init(env)
  logf("================ init ================")
  logf("env.name_space=%s", tostring(env.name_space))
  logf("env.engine=%s env.engine.schema=%s", type(env.engine), type(env.engine.schema))

  logf("package.path=%s", tostring(package.path))
  logf("package.cpath=%s", tostring(package.cpath))

  logf("rime_api.get_rime_version()=%s", tostring(rime_api.get_rime_version()))
  logf("rime_api.get_user_data_dir()=%s", tostring(rime_api.get_user_data_dir()))
  logf("rime_api.get_shared_data_dir()=%s", tostring(rime_api.get_shared_data_dir()))

  -- require 是否走 user_data_dir/lua/?.lua
  try('require("ff7-ime_probe_data")', function()
    local d = require("ff7-ime_probe_data")
    return type(d) .. " magic=" .. tostring(d and d.magic) ..
           " values=" .. tostring(d and d.values and #d.values)
  end)
  try('package.searchpath("ff7-ime_probe_data")', function()
    return package.searchpath("ff7-ime_probe_data", package.path)
  end)

  -- 沙箱：io / os
  try("type(io), type(os), type(debug), type(require)", function()
    return type(io) .. "," .. type(os) .. "," .. type(debug) .. "," .. type(require)
  end)
  try("io.open(user_data_dir/probe_data.txt)", function()
    local f = assert(io.open(rime_api.get_user_data_dir() .. "/probe_data.txt", "r"))
    local line = f:read("l")
    f:close()
    return line
  end)
  try("os.getenv(TEMP)", function() return os.getenv("TEMP") end)
  try("os.date()", function() return os.date("%Y-%m-%d %H:%M:%S") end)

  -- 标准输出（Weasel 服务里没有控制台，正式代码不要依赖它）
  print(TAG .. " print() from Lua: hello")
  io.stdout:flush()

  local cfg = env.engine.schema and env.engine.schema.config
  if cfg then
    logf("init config schema/name=%q menu/page_size=%s",
      tostring(cfg:get_string("schema/name")), tostring(cfg:get_int("menu/page_size")))
  end
  logf("================ init done ================")
end

function M.func(input, seg, env)
  local ctx = env.engine.context
  local schema = env.engine.schema
  local cfg = schema and schema.config

  logf("---- translate called ----")
  logf("input=%q #bytes=%d seg.start=%s seg._start=%s seg._end=%s seg.length=%s",
    input, #input, tostring(seg.start), tostring(seg._start),
    tostring(seg._end), tostring(seg.length))
  logf("seg.status=%s seg.tags.type=%s seg.selected_index=%s",
    tostring(seg.status), type(seg.tags), tostring(seg.selected_index))
  logf("ctx.input=%q ctx.caret_pos=%s ctx:is_composing()=%s",
    tostring(ctx.input), tostring(ctx.caret_pos), tostring(ctx:is_composing()))

  try("seg:active_text(input)", function() return seg:active_text(input) end)
  try("seg.active_text(seg, input)", function() return seg.active_text(seg, input) end)
  try("seg.active_text(input, seg)", function() return seg.active_text(input, seg) end)
  logf("type(seg.get_text)=%s", type(seg.get_text))
  try("seg:get_text()", function() return seg:get_text() end)
  -- 不依赖 active_text 的安全写法：位置是 0-based 字节偏移
  logf("input:sub(seg.start+1, seg._end)=%q", input:sub(seg.start + 1, seg._end))

  -- 开关读取
  logf("option ff7-ime_probe_enabled=%s ff7-ime_probe_extra=%s",
    tostring(ctx:get_option("ff7-ime_probe_enabled")),
    tostring(ctx:get_option("ff7-ime_probe_extra")))
  logf("option ascii_mode=%s (not declared in switches)", tostring(ctx:get_option("ascii_mode")))

  -- 配置读取
  if cfg then
    logf("schema id=%s name=%s page_size=%s",
      tostring(schema.schema_id), tostring(schema.schema_name), tostring(schema.page_size))
    logf("get_int(menu/page_size)=%s (%s)", tostring(cfg:get_int("menu/page_size")), type(cfg:get_int("menu/page_size")))
    logf("get_int(/menu/page_size) leading slash=%s", tostring(cfg:get_int("/menu/page_size")))
    logf("get_string(schema/name)=%q (%s)", tostring(cfg:get_string("schema/name")), type(cfg:get_string("schema/name")))
    logf("get_bool(ff7-ime_probe/flag)=%s (%s)", tostring(cfg:get_bool("ff7-ime_probe/flag")), type(cfg:get_bool("ff7-ime_probe/flag")))
    logf("get_int(ff7-ime_probe/number)=%s", tostring(cfg:get_int("ff7-ime_probe/number")))
    logf("get_string(ff7-ime_probe/name)=%q", tostring(cfg:get_string("ff7-ime_probe/name")))

    -- 缺省值行为：不存在的路径 -> nil
    logf("missing get_int=%s (%s)", tostring(cfg:get_int("no/such/int")), type(cfg:get_int("no/such/int")))
    logf("missing get_string=%s (%s)", tostring(cfg:get_string("no/such/string")), type(cfg:get_string("no/such/string")))
    logf("missing get_bool=%s (%s)", tostring(cfg:get_bool("no/such/bool")), type(cfg:get_bool("no/such/bool")))

    local list = cfg:get_list("ff7-ime_probe/list")
    logf("get_list(ff7-ime_probe/list)=%s type=%s", tostring(list), type(list))
    if list then
      logf("list.size=%s list.type=%s", tostring(list.size), tostring(list.type))
      for i = 0, list.size - 1 do
        local item = list:get_value_at(i)
        logf("list[%d] type=%s value=%q", i, tostring(item.type), tostring(item:get_string()))
      end
    end
    logf("missing get_list=%s (%s)", tostring(cfg:get_list("no/such/list")), type(cfg:get_list("no/such/list")))

    local map = cfg:get_map("ff7-ime_probe")
    logf("get_map(ff7-ime_probe)=%s type=%s", tostring(map), type(map))
    if map then
      logf("map.size=%s map.type=%s keys=%s", tostring(map.size), tostring(map.type),
        table.concat(map:keys(), ","))
      local number = map:get_value("number")
      local list2 = map:get("list")
      logf("map:get_value(number)=%s map:get(list) type=%s", tostring(number and number:get_int()), type(list2))
    end
  end

  -- Candidate 参数顺序：Candidate(type, start, end, text, comment)
  local c = Candidate("ff7-ime_probe", seg.start, seg._end, "TEXT-" .. input, "COMMENT-" .. input)
  logf("Candidate(type,start,end,text,comment): type=%s start=%s _end=%s text=%q comment=%q dyn=%s",
    tostring(c.type), tostring(c.start), tostring(c._end),
    tostring(c.text), tostring(c.comment), tostring(c:get_dynamic_type()))

  -- 反例：若把 text 放第一位，会变成 type
  local wrong = Candidate("TEXT-" .. input, seg.start, seg._end, "ff7-ime_probe", "COMMENT-" .. input)
  logf("swapped-args candidate: type=%s text=%q comment=%q", tostring(wrong.type), tostring(wrong.text), tostring(wrong.comment))

  -- type / quality 是否可写
  c.type = "ff7-ime_probe_typed"
  c.quality = 0.0
  logf("after write: type=%s quality=%s; gen_type field type=%s", tostring(c.type), tostring(c.quality), type(c.gen_type))

  -- 正常候选：任意输入都至少 1 个
  local text, comment
  if input == "nihao" then
    text, comment = "你好", "custom: nihao"
  elseif input == "lkcc" then
    text, comment = "力克兮兮", "custom: illegal pinyin lkcc"
  else
    text, comment = "探针:" .. input, "probe: " .. input
  end
  yield(Candidate("ff7-ime_probe", seg.start, seg._end, text, comment))

  -- 开关 ff7-ime_probe_extra 控制额外候选
  if ctx:get_option("ff7-ime_probe_extra") then
    yield(Candidate("ff7-ime_probe", seg.start, seg._end, "EXTRA-ON:" .. input,
      "switch ff7-ime_probe_extra is ON"))
  end

  -- 任意数量候选（这里 7 个），用于观察 page_size / 分页 / 截断
  for i = 1, 7 do
    yield(Candidate("ff7-ime_probe", seg.start, seg._end,
      string.format("%s#%02d", input, i),
      string.format("seq %d for %q", i, input)))
  end
  logf("---- translate yielded 1 primary + extras for input=%q ----", input)
end

return M
