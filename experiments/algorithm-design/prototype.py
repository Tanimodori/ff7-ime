#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-channel matcher prototype for the FF7 Rime input scheme ("MoGuangJianYing").

The prototype is deliberately written with plain Python 3 stdlib only (plus the
data file prepared by build_phrases.py).  Every algorithm used here has a
straightforward Lua 5.4 translation: arrays/tables, numeric loops, no regex
backtracking, no third-party libraries.

Typical usage
-------------
    python prototype.py --input lkcc --top 5
    python prototype.py --input lienuo --top 5 --explain
    python prototype.py --input zzzz --top 9 --json
    python prototype.py --eval test_cases.json
    python prototype.py --eval test_cases.json --ablation

Data file
---------
phrases.tsv (UTF-8, tab separated):
    text<TAB>pinyin<TAB>readings<TAB>weight
    text     : original entry, punctuation retained
    pinyin   : primary toneless pinyin, one syllable per CJK character
    readings : per character alternatives, '|' inside a group, ';' between groups
    weight   : lexicon weight (uniform 1.0 in the current data)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PHRASES = os.path.join(HERE, "phrases.tsv")
DEFAULT_TEST_CASES = os.path.join(HERE, "test_cases.json")

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    "top_n": 5,
    "max_segmentations": 6,
    "max_variants": 24,
    "alt_reading_weight": 0.82,
    "misread_weight": 0.55,
    "reading_penalty": 0.12,
    "length_penalty": 0.02,
    "prefix_exponent": 0.6,
    "compact_exponent": 0.9,
    "fallback_threshold": 0.5,
    "fuzzy": {
        "zh_z": True,
        "ch_c": True,
        "sh_s": True,
        "ng_n": True,
        "n_l": False,
        "r_l": False,
        "f_h": False,
        "en_eng": True,
        "in_ing": True,
        "an_ang": True,
        "uan_uang": True,
    },
    "channel_weights": {
        "exact": 1.0,
        "fuzzy_exact": 1.0,
        "initial_exact": 1.0,
        "prefix": 1.0,
        "fuzzy_prefix": 0.9,
        "edit": 0.9,
        "edit_fuzzy": 0.7,
        "syllable": 1.1,
        "initial_prefix": 0.9,
        "initial_subseq": 1.7,
        "keyword_subseq": 0.5,
        "bigram": 0.25,
    },
}

# Curated "read the side / common misreading" table.  It is intentionally
# separate from standard pinyin data so that it can be switched off or edited
# without rebuilding phrases.tsv.  Weight is lower than any standard reading.
MISREADINGS: dict[str, list[str]] = {
    "蒂": ["ti"],      # dì -> tì, common in transliterated names; makes tifa hit 蒂法
    "诺": ["ruo"],     # nuò -> ruò, "read the side" (若)
    "岑": ["qin"],     # cén -> qín, classic "read the side" example; no entry here
}

# Channel order is also the tie-break order: earlier = more trustworthy.
CHANNEL_ORDER = [
    "exact",
    "fuzzy_exact",
    "initial_exact",
    "prefix",
    "initial_prefix",
    "initial_subseq",
    "keyword_subseq",
    "edit",
    "syllable",
    "fuzzy_prefix",
    "edit_fuzzy",
    "bigram",
]

# ---------------------------------------------------------------------------
# 2. Pinyin inventory / fuzzy normalisation
# ---------------------------------------------------------------------------

# Standard toneless Mandarin syllables (rare dialect/interjection forms removed
# on purpose: they create spurious segmentations and are not useful here).
_SYLLABLE_TEXT = """
a ai an ang ao ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
ca cai can cang cao ce cen ceng cha chai chan chang chao che chen cheng chi
chong chou chu chua chuai chuan chuang chui chun chuo ci cong cou cu cuan cui
cun cuo da dai dan dang dao de dei deng di dia dian diao die ding diu dong dou
du duan dui dun duo e ei en eng er fa fan fang fei fen feng fo fou fu ga gai
gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui gun guo ha hai
han hang hao he hei hen heng hong hou hu hua huai huan huang hui hun huo ji jia
jian jiang jiao jie jin jing jiong jiu ju juan jue jun ka kai kan kang kao ke
kei ken keng kong kou ku kua kuai kuan kuang kui kun kuo la lai lan lang lao le
lei leng li lia lian liang liao lie lin ling liu lo long lou lu luan lun luo lv
lve ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo mou mu
na nai nan nang nao ne nei nen neng ni nia nian niang niao nie nin ning niu
nong nou nu nuan nuo nv nve o ou pa pai pan pang pao pei pen peng pi pian piao
pie pin ping po pou pu qi qia qian qiang qiao qie qin qing qiong qiu qu quan que
qun ran rang rao re ren reng ri rong rou ru ruan rui run ruo sa sai san sang sao
se sen seng sha shai shan shang shao she shei shen sheng shi shou shu shua
shuai shuan shuang shui shun shuo si song sou su suan sui sun suo ta tai tan
tang tao te teng ti tian tiao tie ting tong tou tu tuan tui tun tuo wa wai wan
wang wei wen weng wo wu xi xia xian xiang xiao xie xin xing xiong xiu xu xuan
xue xun ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun za zai zan
zang zao ze zei zen zeng zha zhai zhan zhang zhao zhe zhei zhen zheng zhi zhong
zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo zi zong zou zu zuan zui zun zuo
"""

SYLLABLES: set[str] = set(_SYLLABLE_TEXT.split())
SYLLABLES.update({"lue", "nue"})  # common keyboard spelling of lüe/nüe
SYLLABLE_PREFIXES: set[str] = set()
for _s in SYLLABLES:
    for _i in range(1, len(_s) + 1):
        SYLLABLE_PREFIXES.add(_s[:_i])

SYLLABLE_ALIASES = {"lue": "lve", "nue": "nve"}
MAX_SYLLABLE_LEN = max(len(s) for s in SYLLABLES)

_SINGLE_FUZZY = {
    ("n", "l"), ("l", "n"),
    ("r", "l"), ("l", "r"),
    ("f", "h"), ("h", "f"),
}


def canon_syllable(s: str) -> str:
    return SYLLABLE_ALIASES.get(s, s)


def normalize_input(text: str) -> tuple[str, set[int]]:
    """Return (lowercase a-z letters, separator boundary positions).

    - ü/u: -> v
    - apostrophes, spaces, hyphens and punctuation become hard boundaries
    - everything outside a-z is dropped
    """
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = text.replace("ü", "v").replace("u:", "v").replace("ǖ", "v")
    text = text.replace("ǘ", "v").replace("ǚ", "v").replace("ǜ", "v")
    letters: list[str] = []
    boundaries: set[int] = set()
    for ch in text:
        if "a" <= ch <= "z":
            letters.append(ch)
        else:
            boundaries.add(len(letters))
    return "".join(letters), boundaries


def fuzzy_core(s: str, cfg: Optional[dict] = None) -> str:
    """zh/ch/sh -> z/c/s; final ng -> n.  Used for letter-level fuzzy channel.

    With cfg=None all core fuzziness is enabled.  With a cfg, each mapping
    respects its switch so that a user can disable e.g. only ng->n.
    """
    f = (cfg or {}).get("fuzzy", {}) if cfg is not None else {}
    if cfg is None or f.get("zh_z", True):
        s = s.replace("zh", "z")
    if cfg is None or f.get("ch_c", True):
        s = s.replace("ch", "c")
    if cfg is None or f.get("sh_s", True):
        s = s.replace("sh", "s")
    if cfg is None or f.get("ng_n", True):
        s = s.replace("ng", "n")
    else:
        # Independent final-equivalence switches; only needed when ng->n is off.
        if cfg is None or f.get("uan_uang", True):
            s = s.replace("uang", "uan")
        if cfg is None or f.get("an_ang", True):
            s = s.replace("ang", "an")
        if cfg is None or f.get("en_eng", True):
            s = s.replace("eng", "en")
        if cfg is None or f.get("in_ing", True):
            s = s.replace("ing", "in")
    return s


def fuzzy_initials_query(s: str, cfg: Optional[dict] = None) -> str:
    """Collapse zh/ch/sh for an initials-only query; do not touch ng."""
    f = (cfg or {}).get("fuzzy", {}) if cfg is not None else {}
    if cfg is None or f.get("zh_z", True):
        s = s.replace("zh", "z")
    if cfg is None or f.get("ch_c", True):
        s = s.replace("ch", "c")
    if cfg is None or f.get("sh_s", True):
        s = s.replace("sh", "s")
    return s


def split_initial(syllable: str) -> str:
    if syllable in ("ng", "hm", "hng", "m", "n"):
        return ""
    if syllable[:2] in ("zh", "ch", "sh"):
        return syllable[:2]
    if syllable[:1] in "bpmfdtnlgkhjqxrzcsyw":
        return syllable[:1]
    return ""


def fuzzy_syllable_key(syllable: str, cfg: dict) -> str:
    """Syllable-level fuzzy key; handles zh/ch/sh, ng, and optional n/l etc."""
    s = canon_syllable(syllable)
    ini = split_initial(s)
    fin = s[len(ini):]
    f = cfg["fuzzy"]
    ini_map = {}
    if f.get("zh_z", True):
        ini_map["zh"] = "z"
    if f.get("ch_c", True):
        ini_map["ch"] = "c"
    if f.get("sh_s", True):
        ini_map["sh"] = "s"
    if f.get("n_l", False):
        ini_map["n"] = "l"
    if f.get("r_l", False):
        ini_map["r"] = "l"
    if f.get("f_h", False):
        ini_map["f"] = "h"
    ini = ini_map.get(ini, ini)
    if f.get("ng_n", True) and fin.endswith("ng"):
        fin = fin[:-1]
    else:
        # Independent final equivalence switches (reserved/optional).
        if f.get("uan_uang", True) and fin == "uang":
            fin = "uan"
        if f.get("an_ang", True) and fin == "ang":
            fin = "an"
        if f.get("en_eng", True) and fin == "eng":
            fin = "en"
        if f.get("in_ing", True) and fin == "ing":
            fin = "in"
    # en/eng, in/ing, an/ang, uan/uang are all covered by ng -> n by default.
    return ini + fin


def fuzzy_initial_letter(syllable: str, cfg: dict) -> str:
    ini = split_initial(canon_syllable(syllable))
    f = cfg["fuzzy"]
    if ini in ("zh", "ch", "sh"):
        if f.get("zh_z", True) and ini == "zh":
            return "z"
        if f.get("ch_c", True) and ini == "ch":
            return "c"
        if f.get("sh_s", True) and ini == "sh":
            return "s"
    if ini == "n" and f.get("n_l", False):
        return "l"
    if ini == "r" and f.get("r_l", False):
        return "l"
    if ini == "f" and f.get("f_h", False):
        return "h"
    return ini


def letter_fuzzy_pair(a: str, b: str, cfg: dict) -> bool:
    if a == b:
        return True
    f = cfg["fuzzy"]
    if {a, b} == {"n", "l"}:
        return bool(f.get("n_l", False))
    if {a, b} == {"r", "l"}:
        return bool(f.get("r_l", False))
    if {a, b} == {"f", "h"}:
        return bool(f.get("f_h", False))
    return False


# ---------------------------------------------------------------------------
# 3. Lexicon representation
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    text: str
    kind: str          # valid | partial | unknown
    penalty: float


@dataclass
class Entry:
    idx: int
    text: str
    chars: list[str]
    primary: list[str]
    readings: list[list[tuple[str, float]]]
    weight: float
    primary_str: str
    variants: list[tuple[str, float]]
    initial_options: list[list[tuple[str, float]]]
    initial_variants: list[tuple[str, float]]
    initial_letter_set: set[str]
    bigrams: Counter
    syllable_starts: set[int]

    @property
    def length(self) -> int:
        return len(self.chars)


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (0x3400 <= cp <= 0x4DBF) or (0x4E00 <= cp <= 0x9FFF) or (0xF900 <= cp <= 0xFAFF)


def _unique_keep_order(items: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _beam_variants(readings: list[list[tuple[str, float]]], max_k: int) -> list[tuple[str, float]]:
    beam: list[tuple[str, float]] = [("", 1.0)]
    for opts in readings:
        merged: dict[str, float] = {}
        for prefix, pw in beam:
            for syl, sw in opts:
                s = prefix + syl
                w = pw * sw
                if w > merged.get(s, -1.0):
                    merged[s] = w
        beam = sorted(merged.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[:max_k]
    return beam


def _beam_initials(readings: list[list[tuple[str, float]]], cfg: dict, max_k: int) -> tuple[list[list[tuple[str, float]]], list[tuple[str, float]]]:
    options: list[list[tuple[str, float]]] = []
    for opts in readings:
        by_letter: dict[str, float] = {}
        for syl, w in opts:
            letter = fuzzy_initial_letter(syl, cfg)
            if letter and w > by_letter.get(letter, -1.0):
                by_letter[letter] = w
        options.append(sorted(by_letter.items(), key=lambda kv: (-kv[1], kv[0])))
    beam: list[tuple[str, float]] = [("", 1.0)]
    for opts in options:
        merged: dict[str, float] = {}
        for prefix, pw in beam:
            for letter, lw in opts:
                s = prefix + letter
                w = pw * lw
                if w > merged.get(s, -1.0):
                    merged[s] = w
        beam = sorted(merged.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[:max_k]
    return options, beam


def _bigrams(s: str) -> Counter:
    if len(s) < 2:
        return Counter({s: 1}) if s else Counter()
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


def load_entries(path: str, cfg: dict) -> list[Entry]:
    entries: list[Entry] = []
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        if header[:4] != ["text", "pinyin", "readings", "weight"]:
            raise ValueError(f"unexpected phrases.tsv header: {header}")
        for line_no, line in enumerate(f, 2):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != 4:
                raise ValueError(f"line {line_no}: expected 4 columns")
            text, pinyin, readings_s, weight_s = parts
            chars = [ch for ch in text if _is_cjk(ch)]
            sylls = pinyin.split()
            groups = readings_s.split(";")
            if not (len(chars) == len(sylls) == len(groups)):
                raise ValueError(f"line {line_no}: alignment mismatch for {text!r}")
            readings: list[list[tuple[str, float]]] = []
            for ch, group in zip(chars, groups):
                raw = _unique_keep_order(group.split("|"))
                if not raw:
                    raise ValueError(f"line {line_no}: no reading for {ch!r}")
                primary = raw[0]
                opts: list[tuple[str, float]] = [(primary, 1.0)]
                for k, syl in enumerate(raw[1:], 1):
                    w = max(0.62, cfg["alt_reading_weight"] - 0.06 * (k - 1))
                    opts.append((canon_syllable(syl), w))
                for syl in MISREADINGS.get(ch, []):
                    if syl not in raw:
                        opts.append((canon_syllable(syl), cfg["misread_weight"]))
                readings.append(opts)
            primary_list = [canon_syllable(x) for x in sylls]
            primary_str = "".join(primary_list)
            variants = _beam_variants(readings, cfg["max_variants"])
            initial_options, initial_variants = _beam_initials(readings, cfg, cfg["max_variants"])
            initial_letter_set = {letter for opts in initial_options for letter, _ in opts}
            starts = set()
            pos = 0
            for syl in primary_list:
                starts.add(pos)
                pos += len(syl)
            entries.append(Entry(
                idx=len(entries),
                text=text,
                chars=chars,
                primary=primary_list,
                readings=readings,
                weight=float(weight_s or 1.0),
                primary_str=primary_str,
                variants=variants,
                initial_options=initial_options,
                initial_variants=initial_variants,
                initial_letter_set=initial_letter_set,
                bigrams=_bigrams(primary_str),
                syllable_starts=starts,
            ))
    if not entries:
        raise ValueError(f"no entries loaded from {path}")
    return entries


# ---------------------------------------------------------------------------
# 4. Input segmentation
# ---------------------------------------------------------------------------

def segment_input(letters: str, boundaries: set[int], cfg: dict) -> list[list[Segment]]:
    """Return up to max_segmentations plausible segmentations, best first."""
    n = len(letters)
    if n == 0:
        return []
    max_k = int(cfg.get("max_segmentations", 12))

    def crosses_boundary(start: int, end: int) -> bool:
        for b in boundaries:
            if start < b < end:
                return True
        return False

    @lru_cache(maxsize=None)
    def rec(pos: int) -> tuple[tuple[tuple[Segment, ...], float, int], ...]:
        if pos >= n:
            return (((), 0.0, 0),)
        out: list[tuple[tuple[Segment, ...], float, int]] = []
        for length in range(1, MAX_SYLLABLE_LEN + 1):
            end = pos + length
            if end > n:
                break
            if crosses_boundary(pos, end):
                break
            chunk = letters[pos:end]
            option: Optional[tuple[str, float]] = None
            if chunk in SYLLABLES:
                option = ("valid", 0.0)
            elif chunk in SYLLABLE_PREFIXES:
                option = ("partial", 0.15 + 0.03 * (length - 1))
            elif length <= 4:
                option = ("unknown", 0.40 + 0.05 * (length - 1))
            if option is None:
                continue
            kind, pen = option
            for rest, rest_pen, rest_count in rec(end):
                out.append(((Segment(chunk, kind, pen),) + rest, pen + rest_pen, rest_count + 1))
        if not out:
            # Defensive fallback: consume one character as unknown.
            for rest, rest_pen, rest_count in rec(pos + 1):
                out.append(((Segment(letters[pos], "unknown", 0.6),) + rest, 0.6 + rest_pen, rest_count + 1))
        out.sort(key=lambda x: (x[1], x[2]))
        return tuple(out[:max_k])

    return [list(segs) for segs, _, _ in rec(0)]


# ---------------------------------------------------------------------------
# 5. Low-level string metrics
# ---------------------------------------------------------------------------

def osa_distance(a: str, b: str, sub_cost) -> float:
    """Optimal-string-alignment Damerau-Levenshtein with weighted costs."""
    la, lb = len(a), len(b)
    if la == 0:
        return float(lb)
    if lb == 0:
        return float(la)
    prev2 = None
    prev = [float(j) for j in range(lb + 1)]
    for i in range(1, la + 1):
        cur = [float(i)] + [0.0] * lb
        ai = a[i - 1]
        for j in range(1, lb + 1):
            bj = b[j - 1]
            cost = 0.0 if ai == bj else sub_cost(ai, bj)
            cur[j] = min(prev[j] + 1.0, cur[j - 1] + 1.0, prev[j - 1] + cost)
            if i > 1 and j > 1 and ai == b[j - 2] and a[i - 2] == bj:
                cur[j] = min(cur[j], prev2[j - 2] + 1.0)
        prev2, prev = prev, cur
    return prev[lb]


def dice_bigrams(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    inter = sum((a & b).values())
    total = sum(a.values()) + sum(b.values())
    return 2.0 * inter / total if total else 0.0


# ---------------------------------------------------------------------------
# 6. Channel scores
# ---------------------------------------------------------------------------

class Matcher:
    def __init__(self, entries: list[Entry], config: Optional[dict] = None):
        self.cfg = _deep_merge(DEFAULT_CONFIG, config or {})
        self.entries = entries
        self.top_n = int(self.cfg["top_n"])
        self._sub_cache: dict[tuple[str, str], float] = {}

    # -- exact / prefix ------------------------------------------------------
    def channel_exact(self, q: str, e: Entry) -> tuple[float, float]:
        """Return (exact score, fuzzy exact score)."""
        if not q:
            return 0.0, 0.0
        exact = 0.0
        for v, w in e.variants:
            if v == q:
                exact = max(exact, 0.85 + 0.15 * w)
                break
        fq = fuzzy_core(q, self.cfg)
        fuzzy = 0.0
        if exact == 0.0:
            for v, w in e.variants:
                if fuzzy_core(v, self.cfg) == fq:
                    fuzzy = max(fuzzy, 0.90 * (0.9 + 0.1 * w))
                    break
        return exact, fuzzy

    def channel_prefix(self, q: str, e: Entry) -> tuple[float, float]:
        if not q:
            return 0.0, 0.0
        exp = float(self.cfg["prefix_exponent"])
        raw = 0.0
        for v, w in e.variants:
            if len(q) < len(v) and v.startswith(q):
                cov = len(q) / len(v)
                raw = max(raw, (cov ** exp) * (0.85 + 0.15 * w))
        fq = fuzzy_core(q, self.cfg)
        fz = 0.0
        if raw == 0.0:
            for v, w in e.variants:
                fv = fuzzy_core(v, self.cfg)
                if len(fq) < len(fv) and fv.startswith(fq):
                    cov = len(fq) / len(fv)
                    fz = max(fz, 0.88 * (cov ** exp) * (0.9 + 0.1 * w))
        return raw, fz

    # -- initials ------------------------------------------------------------
    def channel_initial_exact(self, q: str, e: Entry) -> tuple[float, float]:
        if not q:
            return 0.0, 0.0
        qf = fuzzy_initials_query(q, self.cfg)
        if not qf:
            return 0.0, 0.0
        exact = 0.0
        for v, w in e.initial_variants:
            if v == qf:
                exact = max(exact, 0.95 * (0.9 + 0.1 * w))
                break
        prefix = 0.0
        if exact == 0.0:
            exp = float(self.cfg["prefix_exponent"])
            for v, w in e.initial_variants:
                if len(qf) < len(v) and v.startswith(qf):
                    cov = len(qf) / len(v)
                    prefix = max(prefix, 0.90 * (cov ** exp) * (0.9 + 0.1 * w))
        return exact, prefix

    def channel_initial_subseq(self, q: str, e: Entry) -> float:
        qf = fuzzy_initials_query(q, self.cfg)
        qn = len(qf)
        n = e.length
        if qn < 2 or qn > n:
            return 0.0
        if not all(
            any(letter == qc or letter_fuzzy_pair(letter, qc, self.cfg) for letter in e.initial_letter_set)
            for qc in set(qf)
        ):
            return 0.0
        best: Optional[tuple[float, int, int, float]] = None  # cost, start, end, wprod
        opts_list = e.initial_options
        for start in range(0, n - qn + 1):
            # First query letter must match at `start`.
            first_opts = opts_list[start]
            first_costs = []
            for letter, w in first_opts:
                if letter == qf[0]:
                    first_costs.append((0.0 + 0.05 * (1.0 - w), w))
                elif letter_fuzzy_pair(letter, qf[0], self.cfg):
                    first_costs.append((0.25 + 0.05 * (1.0 - w), w))
            if not first_costs:
                continue
            # dp[j] = (cost, last_index, weight_product) for matching qf[0:j]
            dp: list[Optional[tuple[float, int, float]]] = [None] * (qn + 1)
            for c0, w0 in first_costs:
                cur = dp[1]
                cand = (c0, start, w0)
                if cur is None or cand < cur:
                    dp[1] = cand
            for i in range(start + 1, n):
                for j in range(qn - 1, 0, -1):
                    state = dp[j]
                    if state is None:
                        continue
                    cost, _, wp = state
                    for letter, w in opts_list[i]:
                        c = None
                        if letter == qf[j]:
                            c = 0.0
                        elif letter_fuzzy_pair(letter, qf[j], self.cfg):
                            c = 0.25
                        if c is None:
                            continue
                        cand = (cost + c + 0.05 * (1.0 - w), i, wp * w)
                        cur = dp[j + 1]
                        if cur is None or cand[0] < cur[0]:
                            dp[j + 1] = cand
            end_state = dp[qn]
            if end_state is None:
                continue
            cost, end, wp = end_state
            span = end - start + 1
            cand4 = (cost, start, end, wp)
            if best is None:
                best = cand4
            else:
                # Prefer lower cost, then shorter span, then earlier start.
                bcost, bstart, bend, _ = best
                if (cost, span, start) < (bcost, bend - bstart + 1, bstart):
                    best = cand4
        if best is None:
            return 0.0
        cost, start, end, wp = best
        span = end - start + 1
        compact = qn / span
        phrase_cov = qn / n
        prior = 1.0 / (1.0 + float(self.cfg["length_penalty"]) * max(0, n - 6))
        score = (compact ** float(self.cfg["compact_exponent"]))
        score *= (0.55 + 0.45 * math.sqrt(phrase_cov))
        score *= prior
        score *= (max(0.0, wp) ** 0.25)
        score *= (1.0 - 0.15 * min(1.0, cost))
        return max(0.0, min(1.0, score))

    # -- syllable alignment --------------------------------------------------
    def channel_syllable(self, segments: list[Segment], e: Entry) -> float:
        m = len(segments)
        n = e.length
        if m == 0 or n == 0:
            return 0.0
        # Very short query against a very long phrase: initial/keyword channels
        # are the right tool, the syllable DP would only measure deletions.
        if m > n + 4 or n > m + 4:
            return 0.0
        Q = [canon_syllable(s.text) for s in segments]
        INF = 1e9
        # Precompute substitution costs for every (query segment, phrase char).
        sub: list[list[float]] = []
        for q in Q:
            row = []
            for opts in e.readings:
                best = INF
                for syl, rw in opts:
                    c = self._syllable_sub_cost(q, syl) + float(self.cfg["reading_penalty"]) * (1.0 - rw)
                    if c < best:
                        best = c
                row.append(best)
            sub.append(row)
        # Precompute adjacent-syllable transposition costs (one pair per cell).
        swap: list[list[float]] = [[INF] * max(0, n - 1) for _ in range(max(0, m - 1))]
        for j in range(m - 1):
            q0, q1 = Q[j], Q[j + 1]
            for i in range(n - 1):
                best_swap = INF
                for s1, w1 in e.readings[i]:
                    for s2, w2 in e.readings[i + 1]:
                        c = self._syllable_sub_cost(q0, s2) + self._syllable_sub_cost(q1, s1)
                        c += float(self.cfg["reading_penalty"]) * (2.0 - w1 - w2)
                        if c < best_swap:
                            best_swap = c
                swap[j][i] = best_swap

        dp = [[INF] * (m + 1) for _ in range(n + 1)]
        dp[0][0] = 0.0
        for i in range(n + 1):
            for j in range(m + 1):
                cur = dp[i][j]
                if cur >= INF:
                    continue
                if i < n and cur + 1.0 < dp[i + 1][j]:
                    dp[i + 1][j] = cur + 1.0       # skip phrase syllable
                if j < m and cur + 1.0 < dp[i][j + 1]:
                    dp[i][j + 1] = cur + 1.0       # extra input segment
                if i < n and j < m:
                    v = cur + sub[j][i]
                    if v < dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = v
                if i + 1 < n and j + 1 < m:
                    # Swap two adjacent phrase syllables to match two input segments.
                    v = cur + swap[j][i] + 0.35
                    if v < dp[i + 2][j + 2]:
                        dp[i + 2][j + 2] = v
        cost = dp[n][m]
        if cost >= INF:
            return 0.0
        sim = 1.0 - cost / max(m, n)
        return max(0.0, min(1.0, sim))

    def _syllable_sub_cost(self, q: str, r: str) -> float:
        q = canon_syllable(q)
        r = canon_syllable(r)
        key = (q, r)
        cached = self._sub_cache.get(key)
        if cached is not None:
            return cached
        if q == r:
            self._sub_cache[key] = 0.0
            return 0.0
        if fuzzy_syllable_key(q, self.cfg) == fuzzy_syllable_key(r, self.cfg):
            self._sub_cache[key] = 0.18
            return 0.18
        # Partial input: l vs luo, shen vs shengluo-like truncation.
        if len(q) < len(r) and r.startswith(q):
            ratio = len(q) / len(r)
            value = 0.30 + 0.25 * (1.0 - ratio)
            self._sub_cache[key] = value
            return value
        if len(r) < len(q) and q.startswith(r):
            ratio = len(r) / len(q)
            value = 0.42 + 0.25 * (1.0 - ratio)
            self._sub_cache[key] = value
            return value

        def sub_cost(a: str, b: str) -> float:
            return 0.25 if letter_fuzzy_pair(a, b, self.cfg) else 1.0

        d = osa_distance(q, r, sub_cost)
        value = min(1.0, 0.25 + 0.75 * d / max(len(q), len(r)))
        self._sub_cache[key] = value
        return value

    # -- keyword / letter subsequence ---------------------------------------
    def channel_keyword_subseq(self, q: str, e: Entry) -> float:
        if len(q) < 2 or not q:
            return 0.0
        # Use the primary string only; variants are covered by other channels.
        text = e.primary_str
        if not set(q).issubset(set(text)):
            return 0.0
        best: Optional[tuple[int, int, list[int]]] = None
        for start, ch in enumerate(text):
            if ch != q[0]:
                continue
            pos = start
            matched = [start]
            ok = True
            for c in q[1:]:
                pos = text.find(c, pos + 1)
                if pos < 0:
                    ok = False
                    break
                matched.append(pos)
            if not ok:
                continue
            span = pos - start + 1
            if best is None or span < best[0]:
                best = (span, start, matched)
        if best is None:
            return 0.0
        span, start, matched = best
        qn = len(q)
        boundary_hits = sum(1 for p in matched if p in e.syllable_starts)
        boundary_ratio = boundary_hits / qn
        compact = qn / span
        prior = 1.0 / (1.0 + float(self.cfg["length_penalty"]) * max(0, e.length - 6))
        score = (compact ** 1.1) * (0.55 + 0.45 * boundary_ratio) * prior
        return max(0.0, min(1.0, score))

    # -- edit / bigram -------------------------------------------------------
    def channel_edit(self, q: str, e: Entry) -> tuple[float, float]:
        if not q:
            return 0.0, 0.0

        def sub_cost(a: str, b: str) -> float:
            return 0.25 if letter_fuzzy_pair(a, b, self.cfg) else 1.0

        p = e.primary_str
        d = osa_distance(q, p, sub_cost)
        raw = max(0.0, 1.0 - d / max(len(q), len(p)))
        fq = fuzzy_core(q, self.cfg)
        fp = fuzzy_core(p, self.cfg)
        d2 = osa_distance(fq, fp, sub_cost)
        fz = 0.92 * max(0.0, 1.0 - d2 / max(len(fq), len(fp)))
        return raw, fz

    def channel_bigram(self, q: str, e: Entry) -> float:
        if not q:
            return 0.0
        return dice_bigrams(_bigrams(q), e.bigrams)

    # -- full scoring --------------------------------------------------------
    def score_entry(self, q: str, segmentations: list[list[Segment]], e: Entry) -> tuple[float, dict[str, float]]:
        exact, fuzzy_exact = self.channel_exact(q, e)
        if exact >= 1.0:
            channels = {name: 0.0 for name in CHANNEL_ORDER}
            channels["exact"] = 1.0
            return 1.0, channels
        prefix, fuzzy_prefix = self.channel_prefix(q, e)
        initial_exact, initial_prefix = self.channel_initial_exact(q, e)
        edit, edit_fuzzy = self.channel_edit(q, e)
        syl = 0.0
        for seg in segmentations:
            if abs(len(seg) - e.length) > 4:
                continue
            value = self.channel_syllable(seg, e)
            if value > syl:
                syl = value
        init_sub = self.channel_initial_subseq(q, e)
        kw_sub = self.channel_keyword_subseq(q, e)
        bigram = self.channel_bigram(q, e)
        channels = {
            "exact": exact,
            "fuzzy_exact": fuzzy_exact,
            "initial_exact": initial_exact,
            "prefix": prefix,
            "fuzzy_prefix": fuzzy_prefix,
            "edit": edit,
            "edit_fuzzy": edit_fuzzy,
            "syllable": syl,
            "initial_prefix": initial_prefix,
            "initial_subseq": init_sub,
            "keyword_subseq": kw_sub,
            "bigram": bigram,
        }
        final = fuse_channels(channels, self.cfg)
        return final, channels

    def search(self, text: str, top_n: Optional[int] = None) -> dict:
        n_out = int(top_n if top_n is not None else self.top_n)
        q, boundaries = normalize_input(text)
        if not q:
            ranked = sorted(self.entries, key=lambda e: (e.length, -e.weight, e.idx))[:n_out]
            return {
                "input": text,
                "normalized": q,
                "empty_input": True,
                "results": [{"text": e.text, "score": 0.0, "length": e.length,
                             "pinyin": e.primary_str, "channels": {}} for e in ranked],
            }
        segments = segment_input(q, boundaries, self.cfg)
        scored = []
        for e in self.entries:
            final, channels = self.score_entry(q, segments, e)
            scored.append((final, e, channels))
        scored.sort(key=lambda item: (
            -item[0],
            _best_channel_rank(item[2]),
            item[1].length,
            -item[1].weight,
            item[1].idx,
        ))
        results = []
        for final, e, channels in scored[:n_out]:
            top_channels = {
                k: round(v, 6)
                for k, v in sorted(channels.items(), key=lambda kv: -kv[1])
                if v > 1e-9
            }
            results.append({
                "text": e.text,
                "score": round(final, 6),
                "length": e.length,
                "pinyin": e.primary_str,
                "channels": top_channels,
            })
        best_channel = max(scored[0][2].values()) if scored and scored[0][2] else 0.0
        return {
            "input": text,
            "normalized": q,
            "segments": [[(s.text, s.kind) for s in seg] for seg in segments[:4]],
            "empty_input": False,
            "fallback": bool(scored and best_channel < float(self.cfg["fallback_threshold"])),
            "results": results,
        }


# ---------------------------------------------------------------------------
# 7. Fusion and ordering
# ---------------------------------------------------------------------------

def fuse_channels(channels: dict[str, float], cfg: dict) -> float:
    """Noisy-OR evidence fusion.

    S = 1 - Π_c (1 - s_c) ^ w_c

    Exact (=1) channels force S=1. Multiple weak, independent channels can
    support each other, but a single strong channel always dominates.
    """
    prod = 1.0
    weights = cfg["channel_weights"]
    for name, s in channels.items():
        if s <= 0.0:
            continue
        w = float(weights.get(name, 0.0))
        if w <= 0.0:
            continue
        s = max(0.0, min(1.0, s))
        prod *= (1.0 - s) ** w
    return max(0.0, min(1.0, 1.0 - prod))


def _best_channel_rank(channels: dict[str, float]) -> int:
    for i, name in enumerate(CHANNEL_ORDER):
        if channels.get(name, 0.0) > 1e-9:
            return i
    return len(CHANNEL_ORDER)


def _deep_merge(base: dict, override: dict) -> dict:
    out = {}
    for k, v in base.items():
        if isinstance(v, dict):
            out[k] = _deep_merge(v, override.get(k, {}) if isinstance(override.get(k), dict) else {})
        else:
            out[k] = override.get(k, v)
    # keep keys present only in override
    for k, v in override.items():
        if k not in out:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# 8. CLI / evaluation
# ---------------------------------------------------------------------------

def _fmt_result(i: int, r: dict, explain: bool) -> str:
    line = f"{i:>2}  {r['score']:.4f}  {r['text']}"
    if explain:
        ch = ", ".join(f"{k}={v:.3f}" for k, v in list(r["channels"].items())[:4])
        line += f"   [{r['pinyin']}]  {ch}"
    return line


def run_eval(matcher: Matcher, cases_path: str, verbose: bool = False, top_override: Optional[int] = None) -> dict:
    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)
    cases = data.get("cases", data if isinstance(data, list) else [])
    passed = 0
    top1_total = 0
    top1_passed = 0
    contains_total = 0
    contains_passed = 0
    failures = []
    details = []
    for case in cases:
        cid = case.get("id", "?")
        text = case.get("input", "")
        top_n = int(case.get("top", top_override if top_override is not None else matcher.top_n))
        result = matcher.search(text, top_n)
        texts = [r["text"] for r in result["results"]]
        expect_top1 = case.get("expect_top1")
        expect_in = case.get("expect_in_top")
        expect_count = case.get("expect_count")
        ok = True
        note = ""
        if expect_top1 is not None:
            top1_total += 1
            if texts and texts[0] == expect_top1:
                top1_passed += 1
            else:
                ok = False
                note = f"top1={texts[0] if texts else None!r}, expected {expect_top1!r}"
        if expect_in is not None:
            contains_total += 1
            missing = [x for x in expect_in if x not in texts]
            if missing:
                ok = False
                note += f" missing from top{top_n}: {missing}"
            else:
                contains_passed += 1
        if expect_count is not None and len(texts) != int(expect_count):
            ok = False
            note += f" returned {len(texts)}, expected {expect_count}"
        if ok:
            passed += 1
        else:
            failures.append({"id": cid, "input": text, "note": note, "top": texts[:top_n]})
        if verbose:
            details.append({"id": cid, "input": text, "ok": ok, "top": texts[:top_n], "note": note})
    total = len(cases)
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
        "details": details,
    }


def run_ablation(matcher: Matcher, cases_path: str) -> list[dict]:
    """Evaluate the full model and several ablations on the same test set."""
    base = matcher.cfg
    configs = []

    def add(name: str, description: str, mutate):
        cfg = json.loads(json.dumps(base))
        mutate(cfg)
        configs.append((name, description, cfg))

    add("full", "default configuration", lambda c: None)
    add("no_initial", "disable all initial channels", lambda c: c["channel_weights"].update(
        {"initial_exact": 0.0, "initial_prefix": 0.0, "initial_subseq": 0.0}))
    add("no_keyword", "disable initial-subsequence + keyword", lambda c: c["channel_weights"].update(
        {"initial_subseq": 0.0, "keyword_subseq": 0.0}))
    add("no_syllable", "disable syllable alignment", lambda c: c["channel_weights"].update(
        {"syllable": 0.0}))
    add("no_edit", "disable both letter edit channels", lambda c: c["channel_weights"].update(
        {"edit": 0.0, "edit_fuzzy": 0.0}))
    add("exact_only", "exact + prefix only", lambda c: c["channel_weights"].update(
        {k: 0.0 for k in c["channel_weights"] if k not in ("exact", "prefix")}))
    add("no_fuzzy", "disable all fuzzy behaviour", lambda c: (
        c["channel_weights"].update({"fuzzy_exact": 0.0, "fuzzy_prefix": 0.0, "edit_fuzzy": 0.0}),
        c["fuzzy"].update({k: False for k in c["fuzzy"]})))
    add("keyword_heavy", "initial_subseq weight 2.6", lambda c: c["channel_weights"].update(
        {"initial_subseq": 2.6}))
    add("edit_heavy", "edit weight 1.8", lambda c: c["channel_weights"].update({"edit": 1.8}))
    add("short_bias", "length penalty 0.08", lambda c: c.update({"length_penalty": 0.08}))

    out = []
    for name, desc, cfg in configs:
        m = Matcher(matcher.entries, cfg)
        res = run_eval(m, cases_path)
        out.append({
            "name": name,
            "description": desc,
            "pass_rate": res["pass_rate"],
            "top1_rate": res["top1_rate"],
            "contains_rate": res["contains_rate"],
            "failures": len(res["failures"]),
        })
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="FF7 Rime multi-channel matcher prototype")
    ap.add_argument("--input", "-i", help="pinyin input string")
    ap.add_argument("--top", "-n", type=int, default=None, help="number of candidates (default 5)")
    ap.add_argument("--phrases", default=DEFAULT_PHRASES, help="phrases.tsv path")
    ap.add_argument("--config", default=None, help="JSON file with configuration overrides")
    ap.add_argument("--json", action="store_true", help="print full JSON result")
    ap.add_argument("--explain", action="store_true", help="show pinyin and channel scores")
    ap.add_argument("--eval", metavar="TEST_CASES", help="run test_cases.json")
    ap.add_argument("--eval-verbose", action="store_true", help="include per-case details")
    ap.add_argument("--ablation", action="store_true", help="run ablation table (with --eval)")
    args = ap.parse_args(argv)

    cfg_override = {}
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg_override = json.load(f)
    entries = load_entries(args.phrases, _deep_merge(DEFAULT_CONFIG, cfg_override))
    matcher = Matcher(entries, cfg_override)
    if args.top is not None:
        matcher.top_n = args.top
        matcher.cfg["top_n"] = args.top

    if args.eval:
        if args.ablation:
            table = run_ablation(matcher, args.eval)
            print(f"{'config':<14} {'pass':>6} {'top1':>6} {'inTopN':>7}  description")
            for row in table:
                print(f"{row['name']:<14} {row['pass_rate']:>6.3f} {row['top1_rate']:>6.3f} "
                      f"{row['contains_rate']:>7.3f}  {row['description']}")
            return 0
        res = run_eval(matcher, args.eval, verbose=args.eval_verbose)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["passed"] == res["total"] else 1

    if args.input is None:
        ap.print_help()
        return 2
    result = matcher.search(args.input, args.top)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"input: {result['input']!r}  normalized: {result['normalized']!r}  "
          f"segments: {result.get('segments', [])[:3]}")
    if result.get("fallback"):
        print("(no strong match; nearest-neighbour fallback)")
    for i, r in enumerate(result["results"], 1):
        print(_fmt_result(i, r, args.explain))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
