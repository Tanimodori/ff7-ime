#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the packaging layout of this repository.

There are two installation routes and they must not drift apart:

  1. the self-contained Windows installer — ``install.cmd`` driving
     ``packaging/ff7-ime.ps1``, which copies the files listed in
     ``packaging/manifest.txt`` into the Rime user directory;
  2. the optional rime/plum recipe — ``recipe.yaml``.

Checks:
  * recipe.yaml parses and declares a recipe and a non-empty install_files list;
  * every pattern matches at least one regular file;
  * no absolute paths or parent-directory traversal;
  * recipe.yaml's install_files and packaging/manifest.txt list exactly the same
    files, so the installer and Plum install the same thing;
  * the simulated install contains the schema and all Lua modules at the paths
    Rime expects (``ff7-ime.schema.yaml``, ``lua/*.lua``);
  * user config files are not installed (they would overwrite user patches);
  * the schema references ``lua_translator@*ff7-ime``;
  * the schema loads ``lua_processor@*ff7-ime_filter`` before ``speller``;
  * the installer entry points exist, never shell out to bash or pwsh, and
    ``packaging/ff7-ime.ps1`` is UTF-8 with BOM (PowerShell 5.1 reads a BOM-less
    script in the system ANSI codepage and would garble every Chinese message);
  * with ``--zip PATH``, a built release archive is validated too.

Usage::

    python tools/check_package.py
    python tools/check_package.py --zip dist/ff7-ime-1.0.0.zip
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parent.parent
RECIPE = ROOT / "recipe.yaml"
MANIFEST = ROOT / "packaging" / "manifest.txt"
INSTALLER_PS1 = ROOT / "packaging" / "ff7-ime.ps1"
WRAPPERS = ("install.cmd", "uninstall.cmd", "verify.cmd")
SCHEMA_ID = "ff7-ime"
REQUIRED_FILES = {
    f"{SCHEMA_ID}.schema.yaml",
    "lua/ff7-ime.lua",
    "lua/ff7-ime_matcher.lua",
    "lua/ff7-ime_data.lua",
    "lua/ff7-ime_filter.lua",
}
FORBIDDEN_SUFFIXES = (".custom.yaml",)
EXPECTED_DESCRIPTION = "魔光键影专属拼音输入方案"
EXPECTED_AUTHOR = "Tanimodori"
UTF8_BOM = b"\xef\xbb\xbf"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_recipe() -> dict:
    if not RECIPE.is_file():
        fail("recipe.yaml is missing")
    try:
        data = yaml.safe_load(RECIPE.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        fail(f"recipe.yaml is not valid YAML: {exc}")
    if not isinstance(data, dict):
        fail("recipe.yaml must contain a mapping")
    if not isinstance(data.get("recipe"), dict):
        fail("recipe.yaml is missing the 'recipe' mapping")
    patterns = data.get("install_files")
    if not isinstance(patterns, list) or not patterns:
        fail("recipe.yaml is missing a non-empty 'install_files' list")
    if any(not isinstance(item, str) or not item.strip() for item in patterns):
        fail("install_files must contain non-empty strings")
    return data


def load_manifest() -> list[str]:
    if not MANIFEST.is_file():
        fail("packaging/manifest.txt is missing")
    entries: list[str] = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        safe_relative(text)
        if text in entries:
            fail(f"packaging/manifest.txt lists {text!r} twice")
        entries.append(text)
    if not entries:
        fail("packaging/manifest.txt lists no files")
    return entries


def safe_relative(pattern: str) -> PurePosixPath:
    path = PurePosixPath(pattern)
    if path.is_absolute() or ".." in path.parts:
        fail(f"unsafe install path: {pattern!r}")
    return path


def expand(patterns: list[str]) -> list[Path]:
    selected: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        safe_relative(pattern)
        matches = [Path(p) for p in glob.glob(str(ROOT / pattern)) if Path(p).is_file()]
        matches = [p for p in matches if p.is_relative_to(ROOT)]
        if not matches:
            fail(f"install pattern matched no files: {pattern!r}")
        for path in sorted(matches):
            rel = path.relative_to(ROOT)
            if rel in seen:
                continue
            seen.add(rel)
            selected.append(path)
    return selected


def simulate(files: list[Path], dest: Path) -> None:
    for src in files:
        rel = src.relative_to(ROOT)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def validate_schema(schema_path: Path) -> dict:
    try:
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        fail(f"{schema_path.name} is not valid YAML: {exc}")
    if schema.get("schema", {}).get("schema_id") != SCHEMA_ID:
        fail(f"{schema_path.name} does not declare schema_id {SCHEMA_ID}")
    if schema.get("schema", {}).get("description") != EXPECTED_DESCRIPTION:
        fail(f"{schema_path.name} description must be {EXPECTED_DESCRIPTION!r}")
    authors = schema.get("schema", {}).get("author") or []
    if EXPECTED_AUTHOR not in authors:
        fail(f"{schema_path.name} author must include {EXPECTED_AUTHOR!r}")
    translators = schema.get("engine", {}).get("translators") or []
    if f"lua_translator@*{SCHEMA_ID}" not in translators:
        fail(f"{schema_path.name} does not load lua_translator@*{SCHEMA_ID}")
    processors = schema.get("engine", {}).get("processors") or []
    filter_name = f"lua_processor@*{SCHEMA_ID}_filter"
    if filter_name not in processors:
        fail(f"{schema_path.name} does not load {filter_name}")
    if "speller" in processors and processors.index(filter_name) > processors.index("speller"):
        fail(f"{schema_path.name} must load {filter_name} before speller")
    return schema


def strip_comments(text: str, kind: str) -> str:
    """Drop comments so a mention of bash/pwsh in prose is not a false positive."""
    if kind == "ps1":
        text = re.sub(r"<#.*?#>", "", text, flags=re.S)
        return "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
    kept = []
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("rem ") or stripped == "rem" or stripped.startswith("::"):
            continue
        kept.append(line)
    return "\n".join(kept)


def validate_installer() -> None:
    if not INSTALLER_PS1.is_file():
        fail("packaging/ff7-ime.ps1 is missing")
    raw = INSTALLER_PS1.read_bytes()
    if not raw.startswith(UTF8_BOM):
        fail("packaging/ff7-ime.ps1 must be UTF-8 with BOM for PowerShell 5.1")
    try:
        ps1_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        fail(f"packaging/ff7-ime.ps1 is not valid UTF-8: {exc}")

    code = strip_comments(ps1_text, "ps1")
    if re.search(r"\bbash\b", code):
        fail("packaging/ff7-ime.ps1 must not depend on bash")
    if re.search(r"\bpwsh\b", code):
        fail("packaging/ff7-ime.ps1 must not depend on PowerShell 7 (pwsh)")
    for token in ("packaging\\manifest.txt", "-Action", "WeaselDeployer.exe", "rime.dll"):
        if token not in ps1_text:
            fail(f"packaging/ff7-ime.ps1 does not mention {token!r}")

    for name in WRAPPERS:
        path = ROOT / name
        if not path.is_file():
            fail(f"{name} is missing")
        data = path.read_bytes()
        try:
            text = data.decode("ascii")
        except UnicodeDecodeError:
            fail(f"{name} must be pure ASCII (cmd.exe reads it in the console codepage)")
        if b"\r\n" not in data:
            fail(f"{name} must use CRLF line endings")
        code = strip_comments(text, "cmd")
        if re.search(r"\bbash\b", code) or re.search(r"\bpwsh\b", code):
            fail(f"{name} must not depend on bash or PowerShell 7")
        if "-ExecutionPolicy Bypass" not in code or "-File" not in code:
            fail(f"{name} must invoke the PowerShell script with -File -ExecutionPolicy Bypass")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_zip(zip_path: Path, runtime: list[str]) -> None:
    if not zip_path.is_file():
        fail(f"release archive not found: {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad is not None:
            fail(f"corrupt zip member: {bad}")
        names = zf.namelist()
        if not names:
            fail("release archive is empty")
        for name in names:
            posix = PurePosixPath(name)
            if "\\" in name or posix.is_absolute() or ".." in posix.parts:
                fail(f"unsafe zip member: {name!r}")
        roots = {name.split("/", 1)[0] for name in names}
        if len(roots) != 1:
            fail(f"release archive must have exactly one top-level directory, got {sorted(roots)}")
        root = roots.pop()

        for rel in runtime:
            member = f"{root}/{PurePosixPath(rel).as_posix()}"
            if member not in names:
                fail(f"release archive is missing runtime file {rel}")
            if zf.getinfo(member).file_size == 0:
                fail(f"release archive contains an empty runtime file {rel}")

        for required in ("install.cmd", "uninstall.cmd", "verify.cmd",
                         "packaging/ff7-ime.ps1", "packaging/manifest.txt"):
            if f"{root}/{required}" not in names:
                fail(f"release archive is missing {required}")

        ps1 = zf.read(f"{root}/packaging/ff7-ime.ps1")
        if not ps1.startswith(UTF8_BOM):
            fail("release archive's packaging/ff7-ime.ps1 lost its UTF-8 BOM")

        inner_manifest = zf.read(f"{root}/packaging/manifest.txt").decode("utf-8")
        listed = sorted(
            line.strip() for line in inner_manifest.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        if listed != sorted(runtime):
            fail("release archive's packaging/manifest.txt disagrees with the repository copy")

    sidecar = Path(str(zip_path) + ".sha256")
    if not sidecar.is_file():
        fail(f"checksum sidecar is missing: {sidecar}")
    recorded = sidecar.read_text(encoding="utf-8").split()[0].strip()
    actual = sha256_file(zip_path)
    if recorded != actual:
        fail(f"{sidecar.name} says {recorded} but the archive hashes to {actual}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the ff7-ime packaging layout.")
    parser.add_argument(
        "--zip",
        metavar="PATH",
        help="also validate a built release archive (dist/ff7-ime-<version>.zip)",
    )
    args = parser.parse_args()

    recipe = load_recipe()
    manifest = load_manifest()
    files = expand(recipe["install_files"])
    installed = {path.relative_to(ROOT).as_posix() for path in files}

    if installed != REQUIRED_FILES:
        extra = sorted(installed - REQUIRED_FILES)
        missing = sorted(REQUIRED_FILES - installed)
        fail(f"recipe must install exactly {sorted(REQUIRED_FILES)}; extra={extra}, missing={missing}")

    if sorted(manifest) != sorted(installed):
        fail(
            "packaging/manifest.txt and recipe.yaml install_files disagree: "
            f"manifest={sorted(manifest)}, recipe={sorted(installed)}"
        )

    if recipe["recipe"].get("description") != EXPECTED_DESCRIPTION:
        fail(f"recipe description must be {EXPECTED_DESCRIPTION!r}")

    forbidden = sorted(name for name in installed if name.endswith(FORBIDDEN_SUFFIXES))
    if forbidden:
        fail(f"recipe must not install user config files: {', '.join(forbidden)}")

    validate_installer()

    with tempfile.TemporaryDirectory(prefix="ff7-ime-package-") as tmp:
        dest = Path(tmp)
        simulate(files, dest)
        for name in sorted(installed):
            target = dest / name
            if not target.is_file() or target.stat().st_size == 0:
                fail(f"simulated install produced a missing/empty file: {name}")
        schema = validate_schema(dest / f"{SCHEMA_ID}.schema.yaml")

    recipe_version = str(recipe["recipe"].get("version", ""))
    schema_version = str(schema.get("schema", {}).get("version", ""))
    if recipe_version != schema_version:
        fail(f"recipe version {recipe_version!r} != schema version {schema_version!r}")

    if args.zip:
        validate_zip(Path(args.zip).resolve(), manifest)

    print(f"recipe: {recipe['recipe'].get('Rx', '')} {recipe_version}")
    print(f"installed files ({len(installed)}), listed by recipe.yaml and packaging/manifest.txt:")
    for name in sorted(installed):
        print(f"  {name}")
    print("installer: " + ", ".join(WRAPPERS) + " + packaging/ff7-ime.ps1 (no bash, no pwsh)")
    if args.zip:
        print(f"release archive: {args.zip} OK")
    print("package layout OK")


if __name__ == "__main__":
    main()
