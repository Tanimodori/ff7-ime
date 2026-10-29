#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the offline distribution archive for 魔光键影 (ff7-ime).

The archive is the thing you hand to a Windows machine: unzip it, run
``install.cmd``, done.  It carries the installer, the runtime files Rime needs
and the documentation — but not the test corpus or the intermediate build data.

Layout::

    dist/ff7-ime-<version>/
        install.cmd, uninstall.cmd, verify.cmd
        packaging/ff7-ime.ps1, packaging/manifest.txt
        ff7-ime.schema.yaml
        lua/ff7-ime*.lua
        ff7-ime.custom.yaml          (reference only; the installer never installs it)
        recipe.yaml                  (kept so the optional Plum route still works)
        README.md, LICENSE, docs/*.md
        data/dict.txt
        tools/build_from_pinyin_data.py, tools/pinyin-data/{phrases.tsv,override.yaml}
        MANIFEST.txt, SHA256SUMS
    dist/ff7-ime-<version>.zip
    dist/ff7-ime-<version>.zip.sha256

The zip is validated after writing: single top-level directory, no unsafe member
names, and every runtime file from ``packaging/manifest.txt`` present and
non-empty — a downloaded archive must be installable on its own.

Usage::

    python tools/build_release_zip.py
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SCHEMA_ID = "ff7-ime"
SCHEMA_NAME = "魔光键影"
SCHEMA_FILE = f"{SCHEMA_ID}.schema.yaml"
MANIFEST_FILE = Path("packaging") / "manifest.txt"

# Extra files that ship in the archive, on top of the runtime manifest.
EXTRA_FILES = [
    "install.cmd",
    "uninstall.cmd",
    "verify.cmd",
    "packaging/ff7-ime.ps1",
    "packaging/manifest.txt",
    "recipe.yaml",
    "README.md",
    "LICENSE",
    f"{SCHEMA_ID}.custom.yaml",
    "data/dict.txt",
    "tools/build_from_pinyin_data.py",
    "tools/pinyin-data/phrases.tsv",
    "tools/pinyin-data/override.yaml",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest() -> list[str]:
    path = ROOT / MANIFEST_FILE
    if not path.is_file():
        fail(f"{MANIFEST_FILE.as_posix()} is missing")
    entries: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        entries.append(text)
    if not entries:
        fail(f"{MANIFEST_FILE.as_posix()} lists no files")
    return entries


def read_versions() -> str:
    schema_path = ROOT / SCHEMA_FILE
    recipe_path = ROOT / "recipe.yaml"
    try:
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        recipe = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        fail(f"cannot parse YAML: {exc}")

    schema_version = str(schema.get("schema", {}).get("version", "")).strip()
    recipe_version = str(recipe.get("recipe", {}).get("version", "")).strip()
    if not schema_version:
        fail(f"{SCHEMA_FILE} has no schema.version")
    if schema_version != recipe_version:
        fail(
            f"version mismatch: {SCHEMA_FILE} has {schema_version!r}, "
            f"recipe.yaml has {recipe_version!r}"
        )

    recipe_files = sorted(str(item) for item in (recipe.get("install_files") or []))
    manifest_files = sorted(read_manifest())
    if recipe_files != manifest_files:
        fail(
            "packaging/manifest.txt and recipe.yaml install_files disagree: "
            f"manifest={manifest_files}, recipe={recipe_files}"
        )
    return schema_version


def collect(runtime: list[str]) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for name in runtime + EXTRA_FILES:
        posix = PurePosixPath(name)
        if posix.is_absolute() or ".." in posix.parts:
            fail(f"unsafe path in file list: {name!r}")
        key = posix.as_posix()
        if key in seen:
            continue
        seen.add(key)
        if not (ROOT / posix).is_file():
            fail(f"missing file: {key}")
        files.append(key)
    for path in sorted((ROOT / "docs").glob("*.md")):
        files.append(f"docs/{path.name}")
    return files


def build_tree(stage: Path, files: list[str], version: str, runtime: list[str]) -> None:
    if stage.exists():
        shutil.rmtree(stage)
    for name in files:
        src = ROOT / PurePosixPath(name)
        dst = stage / PurePosixPath(name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # The installer must be readable by Windows PowerShell 5.1, which assumes the
    # system ANSI codepage unless the file starts with a UTF-8 BOM.
    ps1 = stage / "packaging" / "ff7-ime.ps1"
    if not ps1.read_bytes().startswith(b"\xef\xbb\xbf"):
        fail("packaging/ff7-ime.ps1 is not UTF-8 with BOM; PowerShell 5.1 would garble it")

    lines = [
        f"{SCHEMA_NAME} · {SCHEMA_ID} — 离线安装包",
        f"schema: {SCHEMA_ID}",
        f"version: {version}",
        "target: Windows 10/11 x64，小狼毫 Weasel（librime 1.13.1）",
        "install: 解压后双击 install.cmd（详见 docs/INSTALL.md）",
        "uninstall: 双击 uninstall.cmd",
        "verify: 双击 verify.cmd（只读）",
        "",
        "运行时文件（install.cmd 会把这 5 个文件复制到 Rime 用户目录）：",
    ]
    lines += [f"  {name}" for name in runtime]
    lines += [
        "",
        f"注意：{SCHEMA_ID}.custom.yaml 是用户配置示例，安装器不会安装它。",
        "注意：data/ 与 tools/ 只用于重建词条数据，运行时不需要。",
        "",
        "文件清单（SHA256）：",
    ]
    for name in sorted(files):
        digest = sha256_file(stage / PurePosixPath(name))
        lines.append(f"  {digest}  {name}")
    (stage / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    sums = []
    for name in sorted(files):
        digest = sha256_file(stage / PurePosixPath(name))
        sums.append(f"{digest}  {name}")
    (stage / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")


def write_zip(stage: Path, zip_path: Path, version: str, runtime: list[str]) -> str:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                arcname = (PurePosixPath(stage.name) / path.relative_to(stage).as_posix()).as_posix()
                zf.write(path, arcname)

    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad is not None:
            fail(f"corrupt zip member: {bad}")
        names = zf.namelist()
        if not names:
            fail("empty zip")
        for name in names:
            posix = PurePosixPath(name)
            if "\\" in name or posix.is_absolute() or ".." in posix.parts:
                fail(f"unsafe zip member: {name!r}")
        roots = {name.split("/", 1)[0] for name in names}
        if roots != {stage.name}:
            fail(f"zip must contain exactly one top-level directory, got {sorted(roots)}")
        if stage.name != f"{SCHEMA_ID}-{version}":
            fail(f"unexpected staging directory name: {stage.name}")
        for rel in runtime:
            member = f"{stage.name}/{PurePosixPath(rel).as_posix()}"
            if member not in names:
                fail(f"zip is missing runtime file {rel}")
            if zf.getinfo(member).file_size == 0:
                fail(f"zip contains an empty runtime file {rel}")

    digest = sha256_file(zip_path)
    Path(str(zip_path) + ".sha256").write_text(
        f"{digest} *{zip_path.name}\n", encoding="utf-8", newline="\n"
    )
    return digest


def main() -> None:
    version = read_versions()
    if not re.fullmatch(r"[0-9A-Za-z._-]+", version):
        fail(f"version {version!r} is not safe for a file name")
    runtime = read_manifest()
    files = collect(runtime)

    stage = DIST / f"{SCHEMA_ID}-{version}"
    zip_path = DIST / f"{SCHEMA_ID}-{version}.zip"
    DIST.mkdir(parents=True, exist_ok=True)

    build_tree(stage, files, version, runtime)
    digest = write_zip(stage, zip_path, version, runtime)

    total = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())
    print(f"version    {version}")
    print(f"stage      {stage}  ({total / 1024:.0f} KiB, {len(files)} files)")
    print(f"zip        {zip_path}  ({zip_path.stat().st_size / 1024:.0f} KiB)")
    print(f"sha256     {digest}")
    print(f"sha256file {zip_path}.sha256")
    print("release zip OK")


if __name__ == "__main__":
    main()
