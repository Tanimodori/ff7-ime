#!/usr/bin/env python3
"""
验证“共享数据目录 data/lua/ 是否也参与 require 搜索”。

做法：把安装目录的 data 完整复制到临时目录，在副本里新建 shared/lua/mgjy_shared_data.lua；
用户目录里的 translator 只 require 这个模块（用户目录没有该文件）。
如果候选里出现 MGJY-SHARED-OK，就说明 require 确实回退到了 shared_data_dir/lua。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import harness as H

ROOT = Path(tempfile.gettempdir()) / "mgjy-lua-probe-shared"
SHARED = ROOT / "shared"
USER = ROOT / "user"
LOGS = ROOT / "logs"

SCHEMA = """\
schema:
  schema_id: mgjy_probe_shared
  name: "MGJY shared-lua probe"
  version: "0.1.0"
speller:
  alphabet: "zyxwvutsrqponmlkjihgfedcba"
  initials: "zyxwvutsrqponmlkjihgfedcba"
  delimiter: ""
engine:
  processors:
    - ascii_composer
    - speller
    - selector
    - navigator
    - express_editor
  segmentors:
    - abc_segmentor
    - fallback_segmentor
  translators:
    - lua_translator@*mgjy_shared_probe
"""

TRANSLATOR = """\
local M = {}
function M.init(env)
  log.info("[mgjy_shared_probe] init name_space=" .. tostring(env.name_space))
end
function M.func(input, seg, env)
  local ok, d = pcall(require, "mgjy_shared_data")
  log.info(string.format("[mgjy_shared_probe] require mgjy_shared_data ok=%s magic=%s",
    tostring(ok), tostring(ok and d.magic or d)))
  yield(Candidate("mgjy_shared_probe", seg.start, seg._end,
    (ok and d.magic or "REQUIRE-FAILED") .. ":" .. input,
    "loaded from shared_data_dir/lua"))
end
return M
"""


def main():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    USER.mkdir(parents=True)
    LOGS.mkdir(parents=True)
    print(f"copying shared data -> {SHARED}")
    shutil.copytree(H.SHARED_DATA, SHARED)
    (SHARED / "lua").mkdir(exist_ok=True)
    (SHARED / "lua" / "mgjy_shared_data.lua").write_text(
        'return { magic = "MGJY-SHARED-OK" }\n', encoding="utf-8")
    (USER / "lua").mkdir()
    (USER / "lua" / "mgjy_shared_probe.lua").write_text(TRANSLATOR, encoding="utf-8")
    (USER / "mgjy_probe_shared.schema.yaml").write_text(SCHEMA, encoding="utf-8")
    (USER / "default.custom.yaml").write_text(
        "patch:\n  schema_list:\n    - schema: mgjy_probe_shared\n", encoding="utf-8")
    (USER / "rime.lua").write_text('log.info("[shared_test] user rime.lua")\n',
                                   encoding="utf-8")

    # 让 harness.Rime 使用这套临时目录
    H.SHARED_DATA = SHARED
    H.USER_DATA = USER
    H.LOG_DIR = LOGS

    lib = H.load_rime()
    r = H.Rime(lib)
    try:
        r.initialize()
        r.create_session()
        r.select_schema("mgjy_probe_shared")
        r.keys("lkcc")
        ctx = r.context("shared-dir require test")
        print("\nRESULT:", ctx["candidates"][:1] if ctx else None)
        assert ctx and ctx["candidates"], "no candidate produced"
        text = ctx["candidates"][0]["text"]
        assert text.startswith("MGJY-SHARED-OK"), f"unexpected text: {text}"
        print("\nPASS: shared_data_dir/lua is searched by require")
    finally:
        r.destroy()


if __name__ == "__main__":
    main()
