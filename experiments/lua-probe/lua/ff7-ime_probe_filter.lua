-- 透传型 lua_filter：只记录候选并原样 yield，用来观察 filter 与 translator/uniquifier 的顺序。
-- schema 写法：- lua_filter@*ff7-ime_probe_filter
local M = {}
local TAG = "[ff7-ime_filter]"

function M.init(env)
  log.info(string.format("%s init name_space=%s", TAG, tostring(env.name_space)))
end

function M.func(translation, env, candidates)
  local ctx = env.engine.context
  local n = 0
  log.info(string.format("%s apply input=%q", TAG, tostring(ctx.input)))
  for cand in translation:iter() do
    n = n + 1
    log.info(string.format("%s cand#%d type=%s text=%q comment=%q",
      TAG, n, tostring(cand.type), tostring(cand.text), tostring(cand.comment)))
    yield(cand)
  end
  log.info(string.format("%s passed %d candidates", TAG, n))
end

return M
