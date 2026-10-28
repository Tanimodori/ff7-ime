#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the Rime/Plum package layout of this repository.

The repository is installed by rime/plum, which reads ``recipe.yaml`` and copies
the listed files into the Rime user directory.  This script mirrors that step in
a temporary directory so packaging errors are caught before pushing.

Checks:
  * recipe.yaml parses and declares a recipe and install_files;
  * every pattern matches at least one regular file;
  * no absolute paths or parent-directory traversal;
  * the simulated install contains the schema and all Lua modules at the paths
    Rime expects (``ff7-ime.schema.yaml``, ``lua/*.lua``);
  * the schema references ``lua_translator@*ff7-ime``;
  * the schema loads ``lua_processor@*ff7-ime_filter`` before ``speller``;
  * user config files are not installed (they would overwrite user patches).
"""
from __future__ import annotations

import glob
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parent.parent
RECIPE = ROOT / "recipe.yaml"
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


def main() -> None:
    recipe = load_recipe()
    files = expand(recipe["install_files"])
    installed = {path.relative_to(ROOT).as_posix() for path in files}

    if installed != REQUIRED_FILES:
        extra = sorted(installed - REQUIRED_FILES)
        missing = sorted(REQUIRED_FILES - installed)
        fail(f"recipe must install exactly {sorted(REQUIRED_FILES)}; extra={extra}, missing={missing}")

    if recipe["recipe"].get("description") != EXPECTED_DESCRIPTION:
        fail(f"recipe description must be {EXPECTED_DESCRIPTION!r}")

    forbidden = sorted(
        name for name in installed if name.endswith(FORBIDDEN_SUFFIXES)
    )
    if forbidden:
        fail(f"recipe must not install user config files: {', '.join(forbidden)}")

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

    print(f"recipe: {recipe['recipe'].get('Rx', '')} {recipe_version}")
    print(f"installed files ({len(installed)}):")
    for name in sorted(installed):
        print(f"  {name}")
    print("package layout OK")


if __name__ == "__main__":
    main()
