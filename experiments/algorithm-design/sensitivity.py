#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parameter sensitivity / ablation helper for prototype.py.

Channel scores are independent of the fusion weights, so for weight sweeps we
compute every channel score once per test query and only re-run the noisy-OR
fusion + ranking.  Structural parameters (segmentation, length prior, fuzzy
flags) change channel scores and therefore use a full re-score.

Usage:
    python sensitivity.py
    python sensitivity.py --phrases phrases.tsv --cases test_cases.json
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Optional

import prototype as P

HERE = os.path.dirname(os.path.abspath(__file__))


def deep_copy(cfg: dict) -> dict:
    return json.loads(json.dumps(cfg))


def precompute(matcher: P.Matcher, cases: list[dict]) -> list[dict]:
    out = []
    fallback = [e.text for e in sorted(matcher.entries, key=lambda e: (e.length, -e.weight, e.idx))]
    for case in cases:
        text = case.get("input", "")
        q, boundaries = P.normalize_input(text)
        segments = P.segment_input(q, boundaries, matcher.cfg) if q else []
        rows = []
        if q:
            for e in matcher.entries:
                final, channels = matcher.score_entry(q, segments, e)
                rows.append((e, channels))
        out.append({"case": case, "q": q, "rows": rows, "fallback": fallback})
    return out


def rank_precomputed(rows, cfg: dict, top_n: int):
    scored = []
    for e, channels in rows:
        final = P.fuse_channels(channels, cfg)
        scored.append((final, e, channels))
    scored.sort(key=lambda item: (
        -item[0],
        P._best_channel_rank(item[2]),
        item[1].length,
        -item[1].weight,
        item[1].idx,
    ))
    return [e.text for _, e, _ in scored[:top_n]]


def eval_precomputed(precomputed, cfg: dict, default_top: int) -> dict:
    total = passed = top1_total = top1_passed = contains_total = contains_passed = 0
    failures = []
    for item in precomputed:
        case = item["case"]
        total += 1
        top_n = int(case.get("top", default_top))
        if item["rows"]:
            texts = rank_precomputed(item["rows"], cfg, top_n)
        else:
            texts = item["fallback"][:top_n]
        ok = True
        note = ""
        expect_top1 = case.get("expect_top1")
        expect_in = case.get("expect_in_top")
        expect_count = case.get("expect_count")
        if expect_top1 is not None:
            top1_total += 1
            if texts and texts[0] == expect_top1:
                top1_passed += 1
            else:
                ok = False
                note += f" top1={texts[0] if texts else None!r}"
        if expect_in is not None:
            contains_total += 1
            missing = [x for x in expect_in if x not in texts]
            if missing:
                ok = False
                note += f" missing={missing}"
            else:
                contains_passed += 1
        if expect_count is not None and len(texts) != int(expect_count):
            ok = False
            note += f" count={len(texts)}"
        if ok:
            passed += 1
        else:
            failures.append({"id": case.get("id"), "note": note, "top": texts[:top_n]})
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "top1_total": top1_total,
        "top1_passed": top1_passed,
        "top1_rate": round(top1_passed / top1_total, 4) if top1_total else 0.0,
        "contains_total": contains_total,
        "contains_passed": contains_passed,
        "contains_rate": round(contains_passed / contains_total, 4) if contains_total else 0.0,
        "failures": failures,
    }


def full_eval(entries, base_cfg: dict, cases_path: str, mutate) -> dict:
    cfg = deep_copy(base_cfg)
    mutate(cfg)
    m = P.Matcher(entries, cfg)
    return P.run_eval(m, cases_path)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phrases", default=P.DEFAULT_PHRASES)
    ap.add_argument("--cases", default=P.DEFAULT_TEST_CASES)
    ap.add_argument("--out", default=os.path.join(HERE, "sensitivity_results.json"))
    args = ap.parse_args(argv)

    base_cfg = deep_copy(P.DEFAULT_CONFIG)
    entries = P.load_entries(args.phrases, base_cfg)
    matcher = P.Matcher(entries, base_cfg)
    with open(args.cases, encoding="utf-8") as f:
        case_data = json.load(f)
    cases = case_data.get("cases", case_data if isinstance(case_data, list) else [])

    print("precomputing channel scores ...", file=sys.stderr)
    pre = precompute(matcher, cases)

    rows = []

    def add_weight_sweep(param: str, values: list[float]):
        for value in values:
            cfg = deep_copy(base_cfg)
            cfg["channel_weights"][param] = value
            res = eval_precomputed(pre, cfg, int(base_cfg["top_n"]))
            rows.append({
                "kind": "channel_weight",
                "parameter": param,
                "value": value,
                "pass_rate": res["pass_rate"],
                "top1_rate": res["top1_rate"],
                "contains_rate": res["contains_rate"],
                "failures": res["failures"],
            })
            print(f"{param}={value:<5} pass={res['pass_rate']:.3f} top1={res['top1_rate']:.3f}", file=sys.stderr)

    add_weight_sweep("initial_subseq", [0.8, 1.2, 1.7, 2.2, 2.6])
    add_weight_sweep("syllable", [0.4, 0.8, 1.1, 1.5, 2.0])
    add_weight_sweep("edit", [0.3, 0.6, 0.9, 1.3, 1.8])
    add_weight_sweep("fuzzy_exact", [0.3, 0.6, 1.0, 1.5])
    add_weight_sweep("bigram", [0.0, 0.15, 0.25, 0.5])

    # Structural parameters require a full re-score.
    for value in [0.0, 0.02, 0.05, 0.08, 0.12]:
        res = full_eval(entries, base_cfg, args.cases, lambda c, v=value: c.update({"length_penalty": v}))
        rows.append({"kind": "structural", "parameter": "length_penalty", "value": value,
                     "pass_rate": res["pass_rate"], "top1_rate": res["top1_rate"],
                     "contains_rate": res["contains_rate"], "failures": res["failures"]})
        print(f"length_penalty={value:<5} pass={res['pass_rate']:.3f} top1={res['top1_rate']:.3f}", file=sys.stderr)

    for value in [3, 6, 12]:
        res = full_eval(entries, base_cfg, args.cases, lambda c, v=value: c.update({"max_segmentations": v}))
        rows.append({"kind": "structural", "parameter": "max_segmentations", "value": value,
                     "pass_rate": res["pass_rate"], "top1_rate": res["top1_rate"],
                     "contains_rate": res["contains_rate"], "failures": res["failures"]})
        print(f"max_segmentations={value:<3} pass={res['pass_rate']:.3f} top1={res['top1_rate']:.3f}", file=sys.stderr)

    def no_fuzzy(cfg):
        cfg["channel_weights"].update({"fuzzy_exact": 0.0, "fuzzy_prefix": 0.0, "edit_fuzzy": 0.0})
        cfg["fuzzy"].update({k: False for k in cfg["fuzzy"]})

    res = full_eval(entries, base_cfg, args.cases, no_fuzzy)
    rows.append({"kind": "structural", "parameter": "fuzzy_enabled", "value": 0,
                 "pass_rate": res["pass_rate"], "top1_rate": res["top1_rate"],
                 "contains_rate": res["contains_rate"], "failures": res["failures"]})

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"defaults": base_cfg, "rows": rows}, f, ensure_ascii=False, indent=2)

    print("\nparameter        value  pass   top1   inTopN")
    for row in rows:
        print(f"{row['parameter']:<16} {str(row['value']):<6} {row['pass_rate']:.3f}  "
              f"{row['top1_rate']:.3f}  {row['contains_rate']:.3f}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
