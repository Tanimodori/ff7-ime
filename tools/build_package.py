#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the distributable 魔光键影 portable archive.

In this project "portable" means a self-contained distribution archive, not a
Weasel portable runtime: the zip carries the complete Rime user-directory
overlay (``rime/``), install/uninstall/verify scripts, documentation and the
source data needed to rebuild the Lua tables.  It is the artifact that can be
handed to another Windows machine and installed offline.

Layout:
  dist/moguang_jianying-portable/
    README.md, VERSION, MANIFEST.txt, SHA256SUMS
    install.ps1/.cmd, uninstall.ps1/.cmd, verify.ps1/.cmd
    deploy-rime.ps1
    rime/moguang_jianying.schema.yaml
    rime/moguang_jianying.custom.yaml
    rime/lua/mgjy.lua, mgjy_matcher.lua, mgjy_data.lua
    docs/...
    source/... (dict.txt, pinyin TSV, override, build scripts)
    tools/rime_harness.py
  dist/moguang_jianying-portable.zip
  dist/moguang_jianying-portable.zip.sha256
"""
from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "moguang_jianying-portable"
ZIP = ROOT / "dist" / "moguang_jianying-portable.zip"
ZIP_SUM = Path(str(ZIP) + ".sha256")
VERSION = "1.0.0"
SCHEMA_ID = "moguang_jianying"


def copy_file(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path, ignore=None):
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest() -> str:
    return f"""魔光键影 (Moguang Jianying) — Rime 方案分发包
schema: {SCHEMA_ID}
version: {VERSION}
format: portable distribution archive（可分发档案，不是 Weasel 便携运行时）
payload: rime/  — Rime 用户目录覆盖层
target: Weasel 0.17.4 x64 / librime 1.13.1 / Windows 10+
contents:
  rime/          方案源文件（*.schema.yaml、*.custom.yaml、lua/）
  install.*      安装：复制 rime/、patch schema_list、无头部署
  uninstall.*    卸载：只移除本方案并可选恢复备份
  verify.*       只读校验已安装文件
  deploy-rime.ps1 直接调用 rime.dll 的无头部署
  docs/          安装、算法、架构、使用、构建、维护、测试文档
  source/        词表、拼音数据、override 与重建脚本
  tools/         librime 测试 harness
install:
  A. install.cmd（推荐）
  B. 将 rime/ 下的文件复制到 Rime 用户目录，然后重新部署
integrity: SHA256SUMS（包内文件）；zip 旁另有 .sha256（压缩包本身）
docs: docs/INSTALL.md
"""


def write_checksums():
    lines = []
    for path in sorted(DIST.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            rel = path.relative_to(DIST).as_posix()
            lines.append(f"{sha256(path)}  {rel}")
    (DIST / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_zip():
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(DIST.rglob("*")):
            if path.is_file():
                arcname = (Path(DIST.name) / path.relative_to(DIST)).as_posix()
                zf.write(path, arcname)

    with zipfile.ZipFile(ZIP) as zf:
        bad = zf.testzip()
        names = zf.namelist()
    if bad is not None:
        raise SystemExit(f"corrupt zip member: {bad}")
    if not names:
        raise SystemExit("empty zip")
    if any("\\" in name or name.startswith("/") or ".." in Path(name).parts for name in names):
        raise SystemExit("zip contains unsafe member names")
    roots = {name.split("/", 1)[0] for name in names}
    if roots != {DIST.name}:
        raise SystemExit(f"zip must contain exactly one top-level directory, got {sorted(roots)}")

    ZIP_SUM.write_text(f"{sha256(ZIP)} *{ZIP.name}\n", encoding="utf-8", newline="\n")


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    # Runtime: rime/ is the Rime user-directory overlay.
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

    (DIST / "VERSION").write_text(VERSION + "\n", encoding="utf-8", newline="\n")
    (DIST / "MANIFEST.txt").write_text(build_manifest(), encoding="utf-8", newline="\n")

    if not (DIST / "README.md").exists():
        (DIST / "README.md").write_text(
            "# 魔光键影 portable 分发包\n\n"
            "本包是自包含的 Rime 方案分发包：`rime/` 目录可直接复制到 Rime 用户目录，"
            "也可运行 `install.cmd` 自动安装。\n\n"
            "1. 解压到任意可写目录。\n"
            "2. 双击 `install.cmd`（或运行 `install.ps1`）。\n"
            "3. 部署完成后按 F4 / Ctrl+` 选择“魔光键影”。\n"
            "4. 卸载：双击 `uninstall.cmd`。\n\n"
            "完整性：`SHA256SUMS` 列出包内文件；压缩包本身的哈希在 `.zip.sha256`。\n",
            encoding="utf-8",
            newline="\n",
        )

    write_checksums()
    write_zip()

    total = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"built {DIST} ({total/1024/1024:.2f} MB)")
    print(f"zip   {ZIP} ({ZIP.stat().st_size/1024/1024:.2f} MB)")
    print(f"sha256 {sha256(ZIP)}  {ZIP.name}")


if __name__ == "__main__":
    main()
