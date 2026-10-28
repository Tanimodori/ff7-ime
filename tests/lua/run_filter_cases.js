#!/usr/bin/env node
// Run the pure-Lua key filter against cases using wasmoon (Lua 5.4).
// Usage: node tests/lua/run_filter_cases.js [cases.json]

const fs = require("fs");
const path = require("path");
const { LuaFactory } = require("wasmoon");

const root = path.resolve(__dirname, "../..");
const casesPath = process.argv[2] || path.join(root, "tests/lua/filter_cases.json");
const filterSrc = fs.readFileSync(path.join(root, "lua/ff7-ime_filter.lua"), "utf8");
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));

(async () => {
  const lua = await new LuaFactory().createEngine();
  const chunk = `
local M = (function()
${filterSrc}
end)()
local function make_key(k)
  local key = { keycode = k.keycode }
  function key:release() return k.release == true end
  function key:ctrl() return k.ctrl == true end
  function key:alt() return k.alt == true end
  function key:super() return k.super == true end
  return key
end
local function make_env(k)
  local ctx = { input = k.input or "" }
  function ctx:is_composing() return k.composing == true end
  function ctx:has_menu() return k.has_menu == true end
  return { engine = { context = ctx } }
end
return function(k)
  return M.func(make_key(k), make_env(k))
end
`;
  const run = await lua.doString(chunk);

  let pass = 0;
  let fail = 0;
  for (const c of cases) {
    const got = await run(c);
    if (got === c.expect) {
      pass++;
      console.log(`OK   ${c.name}`);
    } else {
      fail++;
      console.log(`FAIL ${c.name}: got ${got}, expected ${c.expect}`);
    }
  }
  console.log(`\n${pass} passed, ${fail} failed, ${cases.length} total`);
  process.exitCode = fail ? 1 : 0;
})();
