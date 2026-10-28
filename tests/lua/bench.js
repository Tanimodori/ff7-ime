#!/usr/bin/env node
// Benchmark the pure-Lua matcher with the full 1212-entry data table.
// Usage: node tests/lua/bench.js [limit]

const fs = require("fs");
const path = require("path");
const { LuaFactory } = require("wasmoon");

const root = path.resolve(__dirname, "../..");
const matcherSrc = fs.readFileSync(path.join(root, "src/lua/mgjy_matcher.lua"), "utf8");
const dataSrc = fs.readFileSync(path.join(root, "tests/lua/full_data.lua"), "utf8");
const all = JSON.parse(fs.readFileSync(path.join(root, "tests/lua/full_data.json"), "utf8"));
const limit = parseInt(process.argv[2] || "40", 10);

const exact = all.slice(0, limit).map((p) => ({
  input: p.syls.join(""),
  expected: p.text,
}));

// A few fuzzy / typo / keyword inputs.
const probes = [
  ["shenluo", "神罗"],
  ["senluo", "神罗"],
  ["leinuo", "雷诺"],
  ["lienuo", "雷诺"],
  ["leino", "雷诺"],
  ["leiknuo", "雷诺"],
  ["nuolei", "雷诺"],
  ["lkcc", "我们会立刻彻底铲除你们！"],
  ["wmhlkcdccnm", "我们会立刻彻底铲除你们！"],
  ["shenl", "神罗"],
  ["zhongli", "重力"],
  ["chongli", "重力"],
  ["ceng", "曾"],
  ["zeng", "曾"],
].map(([input, expected]) => ({ input, expected }));

(async () => {
  const lua = await new LuaFactory().createEngine();
  const chunk = `
local M = (function()
${matcherSrc}
end)()
local PHRASES = (function()
${dataSrc}
end)()
return function(q, topn)
  local r = M.rank(q, PHRASES, { top_n = topn or 9 })
  local o = {}
  for i, v in ipairs(r) do
    o[i] = { text = v.phrase.text, score = v.score, channel = v.channel }
  end
  return o
end
`;
  const run = await lua.doString(chunk);

  const cases = exact.concat(probes);
  let failures = 0;
  const t0 = Date.now();
  for (const c of cases) {
    const res = await run(c.input, 9);
    if (!res[0] || res[0].text !== c.expected) {
      failures++;
      console.log(
        `FAIL ${JSON.stringify(c.input)} expected=${c.expected} got=${res[0] ? res[0].text : "nil"}`
      );
    }
  }
  const dt = Date.now() - t0;
  console.log(
    `\n${cases.length} queries, ${failures} failures, ${dt} ms total, ${(dt / cases.length).toFixed(2)} ms/query`
  );
})();
