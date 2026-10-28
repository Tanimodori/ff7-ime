#!/usr/bin/env node
// Broad evaluation of the pure-Lua matcher.
// Usage: node tests/lua/bulk_eval.js [cases.json]

const fs = require("fs");
const path = require("path");
const { LuaFactory } = require("wasmoon");

const root = path.resolve(__dirname, "../..");
const casesPath = process.argv[2] || path.join(root, "tests/cases/eval_cases.json");
const matcherSrc = fs.readFileSync(path.join(root, "src/lua/mgjy_matcher.lua"), "utf8");
const dataSrc = fs.readFileSync(path.join(root, "src/lua/mgjy_data.lua"), "utf8");
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));

(async () => {
  const lua = await new LuaFactory().createEngine();
  const chunk = `
local M = (function()
${matcherSrc}
end)()
local P = (function()
${dataSrc}
end)()
return function(q, topn)
  local r = M.rank(q, P, { top_n = topn or 9 })
  local o = {}
  for i, v in ipairs(r) do
    o[i] = { text = v.phrase.text, score = v.score, channel = v.channel }
  end
  return o
end
`;
  const run = await lua.doString(chunk);

  const stats = {};
  const failures = {};
  let totalMs = 0;

  for (const c of cases) {
    const cat = c.category || "unknown";
    if (!stats[cat]) {
      stats[cat] = { total: 0, pass: 0, top1: 0, ms: 0 };
      failures[cat] = [];
    }
    const topn = Math.max(
      9,
      c.expect_in_top || 0,
      c.expect_nonempty || 0
    );
    const t0 = Date.now();
    const res = await run(c.input, topn);
    const dt = Date.now() - t0;
    stats[cat].total++;
    stats[cat].ms += dt;
    totalMs += dt;

    const expected = c.expect_top1 || c.expect_text || null;
    const top = res[0] ? res[0].text : null;
    if (expected && top === expected) stats[cat].top1++;

    let ok = true;
    if (c.expect_top1 !== undefined) {
      ok = top === c.expect_top1;
    } else if (c.expect_in_top !== undefined) {
      const inTop = res.slice(0, c.expect_in_top).some((r) => r.text === c.expect_text);
      ok = inTop;
    } else if (c.expect_nonempty !== undefined) {
      ok = res.length >= c.expect_nonempty;
    }
    if (ok) {
      stats[cat].pass++;
    } else if (failures[cat].length < 12) {
      failures[cat].push({
        input: c.input,
        expected: c.expect_top1 || c.expect_text,
        got: top,
        top: res.slice(0, 5).map((r) => `${r.text}(${r.channel})`),
      });
    }
  }

  console.log("category      total   pass   fail  top1-rate  ms/query");
  let hardFail = 0;
  for (const cat of Object.keys(stats)) {
    const s = stats[cat];
    hardFail += s.total - s.pass;
    console.log(
      `${cat.padEnd(12)} ${String(s.total).padStart(6)} ${String(s.pass).padStart(6)} ` +
        `${String(s.total - s.pass).padStart(5)} ${(100 * s.top1 / s.total).toFixed(1).padStart(9)}% ` +
        `${(s.ms / s.total).toFixed(2).padStart(8)}`
    );
  }
  for (const cat of Object.keys(failures)) {
    if (!failures[cat].length) continue;
    console.log(`\n--- ${cat} failures (first ${failures[cat].length}) ---`);
    for (const f of failures[cat]) {
      console.log(
        `  ${JSON.stringify(f.input)} expected=${f.expected} got=${f.got} top=${f.top.join(", ")}`
      );
    }
  }
  console.log(`\ntotal ${cases.length} cases, ${totalMs} ms, hard failures ${hardFail}`);
  process.exitCode = hardFail ? 1 : 0;
})();
