-- 第二个 lua_translator：用于验证多 translator 的顺序与 uniquifier 去重。
local M = {}
local TAG = "[ff7-ime_probe_b]"

function M.init(env)
  log.info(string.format("%s init name_space=%s", TAG, tostring(env.name_space)))
end

function M.func(input, seg, env)
  log.info(string.format("%s translate input=%q start=%d end=%d",
    TAG, input, seg.start, seg._end))

  local dup
  if input == "nihao" then
    dup = "你好"
  elseif input == "lkcc" then
    dup = "力克兮兮"
  else
    dup = "探针:" .. input
  end

  -- 与 ff7-ime_probe 的首候选同 text，uniquifier 会把它合并掉。
  yield(Candidate("ff7-ime_probe_b", seg.start, seg._end, dup, "B duplicate comment"))
  -- 独有候选，用来观察 translator 顺序。
  yield(Candidate("ff7-ime_probe_b", seg.start, seg._end, "B:" .. input, "B distinct comment"))
end

return M
