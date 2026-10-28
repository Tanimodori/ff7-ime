#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a broad evaluation corpus from data/phrases.json.

Categories:
  exact      every phrase's full pinyin -> expect top1
  fuzzy      canonicalized full pinyin (zh/ch/sh->z/c/s, ng->n) -> top1
  initial    full initials -> top1 when unambiguous, else in top3
  typo       delete / duplicate / transpose a middle letter -> in top3
  keyword    a subsequence of a long phrase's initials -> in top5
  fallback   garbage inputs -> exactly N non-empty candidates
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re


def canon_syl(s: str) -> str:
    s = s.replace("zh", "z").replace("ch", "c").replace("sh", "s")
    s = s.replace("ng", "n").replace("v", "u")
    return s


def initial(s: str) -> str:
    for p in ("zh", "ch", "sh"):
        if s.startswith(p):
            return p
    return s[:1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/phrases.json")
    ap.add_argument("--out", default="tests/cases/eval_cases.json")
    ap.add_argument("--seed", type=int, default=20261028)
    args = ap.parse_args()

    rows = json.load(open(args.data, encoding="utf-8"))
    rng = random.Random(args.seed)

    full_to_text = {}
    for r in rows:
        full_to_text.setdefault("".join(r["syls"]), []).append(r["text"])

    cases = []

    # exact
    for r in rows:
        cases.append({
            "category": "exact",
            "input": "".join(r["syls"]),
            "expect_top1": r["text"],
        })

    # fuzzy
    for r in rows:
        raw = "".join(r["syls"])
        can = "".join(canon_syl(s) for s in r["syls"])
        if can == raw:
            continue
        # If canonical input happens to be another phrase's exact full,
        # that phrase legitimately wins; only require top3.
        if can in full_to_text and r["text"] not in full_to_text[can]:
            cases.append({"category": "fuzzy", "input": can, "expect_in_top": 3,
                          "expect_text": r["text"]})
        else:
            cases.append({"category": "fuzzy", "input": can, "expect_top1": r["text"]})

    # initials
    groups = {}
    for r in rows:
        ini = "".join(initial(s) for s in r["syls"])
        groups.setdefault(ini, []).append(r["text"])
    for r in rows:
        ini = "".join(initial(s) for s in r["syls"])
        if len(groups[ini]) == 1:
            cases.append({"category": "initial", "input": ini, "expect_top1": r["text"]})
        elif len(groups[ini]) <= 3:
            cases.append({"category": "initial", "input": ini, "expect_in_top": 3,
                          "expect_text": r["text"]})

    # typo: deterministic edits, then sample
    typos = []
    for r in rows:
        full = "".join(r["syls"])
        if len(full) < 4:
            continue
        mid = len(full) // 2
        # deletion
        q = full[:mid] + full[mid + 1:]
        typos.append((q, r["text"]))
        # duplication
        q = full[:mid] + full[mid] + full[mid:]
        typos.append((q, r["text"]))
        # transposition
        if mid + 1 < len(full) and full[mid] != full[mid + 1]:
            q = full[:mid] + full[mid + 1] + full[mid] + full[mid + 2:]
            typos.append((q, r["text"]))
    rng.shuffle(typos)
    for q, text in typos[:600]:
        if q in full_to_text and text not in full_to_text[q]:
            cases.append({"category": "typo", "input": q, "expect_in_top": 3,
                          "expect_text": text})
        else:
            cases.append({"category": "typo", "input": q, "expect_in_top": 3,
                          "expect_text": text})

    # keyword: sparse subsequence of initials for long phrases
    kws = []
    for r in rows:
        tokens = [initial(s) for s in r["syls"]]
        if len(tokens) < 6:
            continue
        sub = "".join(tokens[::2])
        if len(sub) >= 3:
            kws.append((sub, r["text"]))
    rng.shuffle(kws)
    for q, text in kws[:300]:
        cases.append({"category": "keyword", "input": q, "expect_in_top": 5,
                      "expect_text": text})
    for q, text in [("lkcc", "我们会立刻彻底铲除你们！"),
                    ("wmhlkcdccnm", "我们会立刻彻底铲除你们！")]:
        cases.append({"category": "keyword", "input": q, "expect_top1": text})

    # fallback
    for q in ["zzzzzz", "qqqq", "xyzxyz", "a", "abc", "vvvvvv", "lkccx"]:
        cases.append({"category": "fallback", "input": q, "expect_nonempty": 9})

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cases, f, ensure_ascii=False, indent=0)
    counts = {}
    for c in cases:
        counts[c["category"]] = counts.get(c["category"], 0) + 1
    print(f"wrote {len(cases)} cases: {counts}")


if __name__ == "__main__":
    main()
