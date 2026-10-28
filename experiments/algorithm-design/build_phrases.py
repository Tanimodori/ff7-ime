#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build phrases.tsv from ../data/dict.txt.

This is a *data preparation* helper, not part of the runtime matcher.
The runtime/prototype only consumes phrases.tsv, so the pinyin data can be
replaced by another producer without touching prototype.py.

TSV columns
-----------
text      : original dictionary entry, punctuation preserved, exactly as output
pinyin    : primary reading, one toneless syllable per CJK char, space separated
readings  : alternative readings, one group per CJK char, '|' separated,
            groups separated by ';'.  The primary reading is always first.
weight    : lexicon weight (currently uniform 1.0)

Usage:
    python build_phrases.py            # writes phrases.tsv in this directory
    python build_phrases.py --check    # validate an existing phrases.tsv
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from typing import Iterable

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DICT_PATH = os.path.join(PROJECT_ROOT, "data/dict.txt")
OUT_PATH = os.path.join(HERE, "phrases.tsv")

CJK_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2FA1F),
)


def is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in CJK_RANGES)


def cjk_chars(text: str) -> list[str]:
    return [ch for ch in text if is_cjk(ch)]


def unique(seq: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        return check()

    try:
        from pypinyin import Style, pinyin
    except ImportError:
        print("pypinyin is required only for rebuilding phrases.tsv: pip install pypinyin", file=sys.stderr)
        return 2

    raw = open(DICT_PATH, "rb").read()
    text_data = raw.decode("utf-16")
    lines = [ln.strip() for ln in text_data.splitlines() if ln.strip()]

    rows: list[tuple[str, str, str, str]] = []
    for text in lines:
        chars = cjk_chars(text)
        if not chars:
            continue
        # Phrase-level pass: context disambiguates the primary reading.
        phrase_all = pinyin(text, heteronym=True, style=Style.NORMAL, errors="ignore")
        phrase_one = pinyin(text, heteronym=False, style=Style.NORMAL, errors="ignore")
        if len(phrase_all) != len(chars) or len(phrase_one) != len(chars):
            raise RuntimeError(f"alignment failure: {text!r} {phrase_all!r} {phrase_one!r}")

        primary: list[str] = []
        groups: list[str] = []
        for ch, all_readings, one in zip(chars, phrase_all, phrase_one):
            p = one[0] if one else (all_readings[0] if all_readings else "")
            if not p:
                raise RuntimeError(f"no reading for {ch!r} in {text!r}")
            # Union of context readings and character-level heteronyms.
            char_level = pinyin(ch, heteronym=True, style=Style.NORMAL) or []
            flat_char = [x for group in char_level for x in group]
            readings = unique([p] + list(all_readings) + flat_char)
            primary.append(p)
            groups.append("|".join(readings))
        rows.append((text, " ".join(primary), ";".join(groups), "1.0"))

    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write("text\tpinyin\treadings\tweight\n")
        for row in rows:
            f.write("\t".join(row) + "\n")
    print(f"wrote {OUT_PATH}: {len(rows)} entries")
    return check()


def check() -> int:
    if not os.path.exists(OUT_PATH):
        print("phrases.tsv missing", file=sys.stderr)
        return 1
    n = 0
    with open(OUT_PATH, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        if header[:4] != ["text", "pinyin", "readings", "weight"]:
            print(f"bad header: {header}", file=sys.stderr)
            return 1
        for ln, line in enumerate(f, 2):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                print(f"line {ln}: expected 4 columns", file=sys.stderr)
                return 1
            text, py, readings, weight = parts
            chars = cjk_chars(text)
            sylls = py.split()
            groups = readings.split(";")
            if not (len(chars) == len(sylls) == len(groups)):
                print(f"line {ln}: alignment {len(chars)}/{len(sylls)}/{len(groups)}: {text!r}", file=sys.stderr)
                return 1
            if any(sylls[i] != groups[i].split("|")[0] for i in range(len(chars))):
                print(f"line {ln}: primary not first: {text!r}", file=sys.stderr)
                return 1
            n += 1
    print(f"checked {OUT_PATH}: {n} valid entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
