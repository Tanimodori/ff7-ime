#!/usr/bin/env node
// Run the pure-Lua matcher against core cases using wasmoon (Lua 5.4).
// Usage: node tests/lua/run_cases.js [cases.json] [data.lua]

const fs = require("fs");
const path = require("path");
const { LuaFactory } = require("wasmoon");

const root = path.resolve(__dirname, "../..");
const casesPath = process.argv[2] || path.join(root, "tests/lua/core_cases.json");
const dataPath = process.argv[3] || path.join(root, "lua/ff7-ime_data.lua");

const matcherSrc = fs.readFileSync(path.join(root, "lua/ff7-ime_matcher.lua"), "utf8");
const dataSrc = fs.readFileSync(dataPath, "utf8");
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));

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
  local opts = { top_n = topn or 9, preedit = { enabled = true, separator = "'" } }
  local r = M.rank(q, PHRASES, opts)
  local o = {}
  for i, v in ipairs(r) do
    o[i] = {
      text = v.phrase.text,
      score = v.score,
      raw = v.raw,
      channel = v.channel,
      detail = v.detail,
    }
  end
  local pv = M.preview(q, PHRASES, opts, r[1])
  return { candidates = o, preedit = pv }
end
`;
  const run = await lua.doString(chunk);

  let pass = 0;
  let fail = 0;
  for (const c of cases) {
    const topn = Math.max(9, c.expect_nonempty || 0, c.expect_in_top || 0);
    const out = await run(c.input, topn);
    const res = out.candidates;
    const preedit = out.preedit;
    const top = res[0] ? res[0].text : null;
    let ok = true;
    let why = "";
    if (c.expect_top1 !== undefined && top !== c.expect_top1) {
      ok = false;
      why = `top1=${top} expected=${c.expect_top1}`;
    }
    if (c.expect_top1_channel !== undefined
        && (!res[0] || res[0].channel !== c.expect_top1_channel)) {
      ok = false;
      why = `top1 channel=${res[0] && res[0].channel} expected=${c.expect_top1_channel}`;
    }
    if (c.expect_not_channel !== undefined) {
      const bad = res.find((r) => r.channel === c.expect_not_channel);
      if (bad) {
        ok = false;
        why = `unexpected ${c.expect_not_channel} candidate: ${bad.text}`;
      }
    }
    if (c.expect_in_top !== undefined) {
      const inTop = res
        .slice(0, c.expect_in_top)
        .some((r) => r.text === c.expect_text);
      if (!inTop) {
        ok = false;
        why = `"${c.expect_text}" not in top ${c.expect_in_top}`;
      }
    }
    if (c.expect_nonempty !== undefined && res.length < c.expect_nonempty) {
      ok = false;
      why = `only ${res.length} candidates, expected >= ${c.expect_nonempty}`;
    }
    if (c.expect_preedit !== undefined && preedit !== c.expect_preedit) {
      ok = false;
      why = `preedit=${JSON.stringify(preedit)} expected=${JSON.stringify(c.expect_preedit)}`;
    }
    if (ok) {
      pass++;
      const pv = c.expect_preedit !== undefined ? ` preedit=${JSON.stringify(preedit)}` : "";
      console.log(`OK   ${JSON.stringify(c.input)} -> ${top} (${res.length})${pv}`);
    } else {
      fail++;
      console.log(`FAIL ${JSON.stringify(c.input)}: ${why}`);
      for (let i = 0; i < Math.min(res.length, 5); i++) {
        const r = res[i];
        console.log(
          `     ${i + 1}. ${r.text}  score=${r.score.toFixed(4)} raw=${r.raw.toFixed(4)} ${r.channel} ${r.detail}`
        );
      }
    }
  }
  console.log(`\n${pass} passed, ${fail} failed, ${cases.length} total`);
  process.exitCode = fail ? 1 : 0;
})();
