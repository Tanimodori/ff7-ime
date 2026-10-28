-- user_data_dir/rime.lua
-- librime-lua 在初始化时会自动执行它（用户目录优先，共享目录兜底）。
log.info("[mgjy_probe] rime.lua loaded from user data dir")
MGJY_RIME_LUA_LOADED = true

-- 演示“不带 * 的 lua_translator@名字”写法：
--   该写法不做 require，而是直接查找全局变量 mgjy_global。
mgjy_global = {
  init = function(env)
    log.info("[mgjy_global] init name_space=" .. tostring(env.name_space))
  end,
  func = function(input, seg, env)
    log.info(string.format("[mgjy_global] translate input=%q start=%d end=%d",
      input, seg.start, seg._end))
    yield(Candidate("mgjy_global", seg.start, seg._end,
      "GLOBAL:" .. input, "defined as global in rime.lua"))
  end,
}
