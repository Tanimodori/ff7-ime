#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the portable 魔光键影 package and zip it.

Layout:
  dist/moguang_jianying-portable/
    README.md, VERSION
    install.ps1/.cmd, uninstall.ps1/.cmd, verify.ps1/.cmd
    rime/moguang_jianying.schema.yaml
    rime/moguang_jianying.custom.yaml
    rime/lua/mgjy.lua, mgjy_matcher.lua, mgjy_data.lua
    docs/...
    source/... (dict.txt, pinyin TSV, override, build scripts)
    tools/rime_harness.py
"""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "moguang_jianying-portable"
ZIP = ROOT / "dist" / "moguang_jianying-portable.zip"


def copy_file(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path, ignore=None):
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    # Runtime
    copy_file(ROOT / "src/moguang_jianying.schema.yaml", DIST / "rime/moguang_jianying.schema.yaml")
    copy_file(ROOT / "src/moguang_jianying.custom.yaml", DIST / "rime/moguang_jianying.custom.yaml")
    for name in ("mgjy.lua", "mgjy_matcher.lua", "mgjy_data.lua"):
        copy_file(ROOT / "src/lua" / name, DIST / "rime/lua" / name)

    # Installer
    for name in ("install.ps1", "install.cmd", "uninstall.ps1", "uninstall.cmd", "verify.ps1", "verify.cmd", "deploy-rime.ps1"):
        copy_file(ROOT / "packaging" / name, DIST / name)

    # Docs
    if (ROOT / "README.md").exists():
        copy_file(ROOT / "README.md", DIST / "README.md")
    copy_tree(ROOT / "docs", DIST / "docs")
    # Internal install logs are not part of the deliverable.
    for log in (DIST / "docs").glob("install-real*.log"):
        log.unlink()

    # Rebuild sources
    copy_file(ROOT / "dict.txt", DIST / "source/dict.txt")
    copy_file(ROOT / "experiments/pinyin-data/phrases.tsv", DIST / "source/phrases.tsv")
    copy_file(ROOT / "experiments/pinyin-data/override.yaml", DIST / "source/override.yaml")
    copy_file(ROOT / "tools/build_from_pinyin_data.py", DIST / "source/build_from_pinyin_data.py")
    copy_file(ROOT / "tools/tsv_to_lua_data.py", DIST / "source/tsv_to_lua_data.py")
    copy_file(ROOT / "experiments/pinyin-data/extract.py", DIST / "source/extract.py")
    copy_file(ROOT / "packaging/source-README-build.md", DIST / "source/README-build.md")

    # Verification harness
    copy_file(ROOT / "experiments/rime-harness/rime_harness.py", DIST / "tools/rime_harness.py")

    (DIST / "VERSION").write_text("1.0.0\n", encoding="utf-8", newline="\n")

    if not (DIST / "README.md").exists():
        (DIST / "README.md").write_text(
            "# 魔光键影 portable\n\n"
            "1. 双击 `install.cmd`（或以管理员/普通用户运行 `install.ps1`）。\n"
            "2. 部署完成后按 F4 / Ctrl+` 选择“魔光键影”。\n"
            "3. 输入示例：`shenluo` → 神罗；`lkcc` → 我们会立刻彻底铲除你们！；"
            "`leinuo`/`lienuo`/`leino`/`leiknuo` → 雷诺。\n"
            "4. 卸载：双击 `uninstall.cmd`。\n",
            encoding="utf-8",
            newline="\n",
        )

    # Zip
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(DIST.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(DIST.parent))

    total = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"built {DIST} ({total/1024/1024:.2f} MB)")
    print(f"zip   {ZIP} ({ZIP.stat().st_size/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()
