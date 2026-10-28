#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the final Lua phrase table from the curated pinyin TSV.

Input:
  experiments/pinyin-data/phrases.tsv   (id, phrase, primary_pinyin, ...)
  experiments/pinyin-data/override.yaml (misread_candidates, ...)

Model:
  - primary reading comes from the curated TSV;
  - alternatives = readings this character actually takes elsewhere in the
    1212-entry lexicon (weight 0.97) + explicitly allowed misreadings
    (weight 0.90).  This keeps the index compact and avoids importing every
    obscure pypinyin heteronym.
  - full variants are capped (default 8) and weighted by the product of the
    alternative weights used.

Usage:
  python tools/build_from_pinyin_data.py
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import re
import sys
from collections import Counter, defaultdict

import yaml

HAN = range(0x4E00, 0xA000)

# Colloquial / common misreadings not present in the override file.
EXTRA_MISREAD = {
    "骰": ["shai3"],   # 骰子 shǎi zi（口语）
    "乐": ["yue4"],    # 音乐/乐章的 yuè
}


def is_han(ch: str) -> bool:
    return ord(ch) in HAN


def tone_less(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[1-5]$", "", s)
    return s.replace("ü", "v")


def lua_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'


def lua_list(items) -> str:
    return "{" + ", ".join(items) + "}"


def load_rows(path: str):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    out = []
    for row in rows:
        phrase = row["phrase"]
        han = [c for c in phrase if is_han(c)]
        syls = [tone_less(x) for x in row["primary_pinyin"].split()]
        if len(han) != len(syls):
            raise SystemExit(
                f"length mismatch for {phrase!r}: {len(han)} Han chars, {len(syls)} syllables"
            )
        if any(not s for s in syls):
            raise SystemExit(f"empty syllable for {phrase!r}: {syls}")
        out.append({
            "id": int(row["id"]),
            "phrase": phrase,
            "han": han,
            "syls": syls,
        })
    return out


def load_misreads(path: str):
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("misread_candidates", {}) or {}
    result = {}
    for ch, values in raw.items():
        if not isinstance(values, list):
            values = [values]
        readings = []
        for v in values:
            s = tone_less(str(v))
            if s:
                readings.append(s)
        result[ch] = readings
    for ch, values in EXTRA_MISREAD.items():
        result.setdefault(ch, [])
        for v in values:
            s = tone_less(v)
            if s and s not in result[ch]:
                result[ch].append(s)
    return result


def build_readings(rows, misreads):
    # Readings this character takes as a primary somewhere in the lexicon.
    contextual = defaultdict(Counter)
    for row in rows:
        for ch, syl in zip(row["han"], row["syls"]):
            contextual[ch][syl] += 1

    phrases = []
    for row in rows:
        alts = []
        for ch, primary in zip(row["han"], row["syls"]):
            ordered = []
            seen = {primary}

            # Contextual readings first (they are attested in this lexicon).
            for syl, _freq in contextual[ch].most_common():
                if syl not in seen:
                    seen.add(syl)
                    ordered.append((syl, 0.97))

            # Then explicitly allowed misreadings.
            for syl in misreads.get(ch, []):
                if syl not in seen:
                    seen.add(syl)
                    ordered.append((syl, 0.90))

            alts.append(ordered)

        phrases.append({
            "id": row["id"],
            "order": row["id"],
            "text": row["phrase"],
            "syls": row["syls"],
            "alts": alts,
            "w": 1.0,
        })
    return phrases


def make_variants(phrase, cap=8):
    primary = phrase["syls"]
    alts = phrase["alts"]
    variants = [(primary, 1.0)]
    seen = {tuple(primary)}

    # Single-character substitutions, contextual before misread.
    choices = []
    for j, alt_list in enumerate(alts):
        for alt, w in alt_list:
            choices.append((j, alt, w))
    for j, alt, w in choices:
        v = primary.copy()
        v[j] = alt
        key = tuple(v)
        if key not in seen:
            seen.add(key)
            variants.append((v, w))
            if len(variants) >= cap:
                return variants

    # Two-character combinations if there is still room.
    for (j1, a1, w1), (j2, a2, w2) in itertools.combinations(choices, 2):
        if j1 == j2:
            continue
        v = primary.copy()
        v[j1] = a1
        v[j2] = a2
        key = tuple(v)
        if key not in seen:
            seen.add(key)
            variants.append((v, round(w1 * w2, 4)))
            if len(variants) >= cap:
                break
    return variants


def initial_token(syllable: str) -> str:
    for p in ("zh", "ch", "sh"):
        if syllable.startswith(p):
            return p
    return syllable[:1]


def enrich(phrases, cap=8):
    for p in phrases:
        variants = make_variants(p, cap)
        p["fulls"] = []
        seen_full = set()
        for syls, w in variants:
            full = "".join(syls)
            if full not in seen_full:
                seen_full.add(full)
                p["fulls"].append((full, w))

        p["init_variants"] = []
        seen_init = set()
        for syls, w in variants:
            tokens = tuple(initial_token(s) for s in syls)
            if tokens not in seen_init:
                seen_init.add(tokens)
                p["init_variants"].append((tokens, w))

        p["swaps"] = []
        if len(p["syls"]) >= 2:
            for j in range(len(p["syls"]) - 1):
                v = p["syls"].copy()
                v[j], v[j + 1] = v[j + 1], v[j]
                p["swaps"].append("".join(v))
    return phrases


def to_lua(phrases) -> str:
    lines = ["-- Generated by tools/build_from_pinyin_data.py; do not edit by hand.", "return {"]
    for p in phrases:
        parts = [
            f"text = {lua_str(p['text'])}",
            f"syls = {lua_list(lua_str(s) for s in p['syls'])}",
        ]
        if any(p["alts"]):
            alt_parts = []
            for alt_list in p["alts"]:
                alt_parts.append(lua_list(
                    "{ s = %s, w = %s }" % (lua_str(s), w) for s, w in alt_list
                ))
            parts.append("alts = " + lua_list(alt_parts))
        parts.append("fulls = " + lua_list(
            "{ s = %s, w = %s }" % (lua_str(s), w) for s, w in p["fulls"]
        ))
        parts.append("init_variants = " + lua_list(
            "{ tokens = %s, w = %s }" % (lua_list(lua_str(t) for t in toks), w)
            for toks, w in p["init_variants"]
        ))
        if p["swaps"]:
            parts.append("swaps = " + lua_list(lua_str(s) for s in p["swaps"]))
        parts.append("w = 1.0")
        parts.append(f"order = {p['order']}")
        lines.append("  { " + ", ".join(parts) + " },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def to_json(phrases):
    out = []
    for p in phrases:
        out.append({
            "order": p["order"],
            "text": p["text"],
            "syls": p["syls"],
            "alts": [[{"s": s, "w": w} for s, w in a] for a in p["alts"]],
            "fulls": [{"s": s, "w": w} for s, w in p["fulls"]],
            "init_variants": [{"tokens": list(t), "w": w} for t, w in p["init_variants"]],
            "swaps": p["swaps"],
            "w": 1.0,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="experiments/pinyin-data/phrases.tsv")
    ap.add_argument("--override", default="experiments/pinyin-data/override.yaml")
    ap.add_argument("--lua", default="src/lua/mgjy_data.lua")
    ap.add_argument("--json", default="data/phrases.json")
    ap.add_argument("--cap", type=int, default=8)
    args = ap.parse_args()

    rows = load_rows(args.input)
    misreads = load_misreads(args.override)
    phrases = enrich(build_readings(rows, misreads), args.cap)

    os.makedirs(os.path.dirname(os.path.abspath(args.lua)), exist_ok=True)
    with open(args.lua, "w", encoding="utf-8", newline="\n") as f:
        f.write(to_lua(phrases))
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(to_json(phrases), f, ensure_ascii=False, indent=1)

    # Stats
    n_alt = sum(1 for p in phrases for a in p["alts"] if a)
    n_var = sum(len(p["fulls"]) for p in phrases)
    n_init = sum(len(p["init_variants"]) for p in phrases)
    print(f"phrases={len(phrases)} alt-slots={n_alt} full-variants={n_var} init-variants={n_init}")
    print(f"wrote {args.lua}")


if __name__ == "__main__":
    main()
