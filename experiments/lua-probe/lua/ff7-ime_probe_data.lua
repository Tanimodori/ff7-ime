-- 构建期把数据嵌进 Lua 表的最小示例（不依赖 io / 外部文件）。
return {
  magic = "FF7-IME-DATA-OK",
  values = { "alpha", "beta", "gamma" },
  map = { nihao = "你好", lkcc = "力克兮兮" },
}
