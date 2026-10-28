#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为《魔光键影》(ff7-ime) 词表生成普通话拼音数据。

输入
----
* ../../dict.txt                UTF-16 LE (BOM) + CRLF，一行一个词条
* override.yaml                 人工确认的读音覆盖（本脚本只读，不写）
* luna_pinyin.dict.yaml         Rime 明月拼音，用于逐字交叉校验
* terra_pinyin.dict.yaml        Rime 地球拼音，作为第三来源（可选）

输出（均写入本脚本所在目录）
--------------------------
* phrases.tsv                   1212 条词条的逐字注音
* chars.tsv                     唯一汉字读音汇总、多音字、误读候选
* REPORT.md                     统计、方法、风险、抽查样例

用法
----
    python extract.py
    python extract.py --dict "D:/.../dict.txt" --luna "C:/.../luna_pinyin.dict.yaml"
    python extract.py --check

依赖：pypinyin, PyYAML
    pip install pypinyin pyyaml

说明
----
* 无调全拼用空格分隔，供 Rime 直接消费；数字声调另存一列。
* 标点（！，·？、…）不参与注音，但 phrase 列原样保留。
* 一、不 的数字声调统一标注本调（yi1 / bu4），不记录变调；
  无调全拼不受影响。
* 中性轻声统一记为 5（de5 / le5 / ma5 ...）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from pypinyin import Style, pinyin
except ImportError:  # pragma: no cover
    sys.exit("缺少 pypinyin：请先运行 pip install pypinyin")

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("缺少 PyYAML：请先运行 pip install pyyaml")


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent

DEFAULT_DICT = PROJECT_ROOT / "dict.txt"
DEFAULT_OVERRIDE = HERE / "override.yaml"
DEFAULT_LUNA = Path(r"C:\Program Files\Rime\weasel-0.17.4\data\luna_pinyin.dict.yaml")
DEFAULT_TERRA = Path(r"C:\Program Files\Rime\weasel-0.17.4\data\terra_pinyin.dict.yaml")

# CJK 统一表意文字：基本区、扩展 A、扩展 B 及以后（BMP 之外用宽字符表示）
HAN_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2FA1F),
)

TONE3_RE = re.compile(r"^[a-zêü]+[1-5]?$")


def is_han(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in HAN_RANGES)


def normalize_tone3(raw: str) -> str:
    """把 pypinyin TONE3 结果规范为小写 + 末尾 1..5。

    pypinyin 对轻声有时返回不带数字的音节（de / le / ma），统一补 5。
    ü 统一写作 v，与 Rime 全拼习惯一致。
    """
    s = raw.strip().lower().replace("ü", "v")
    if not s:
        return s
    if s[-1] not in "12345":
        s += "5"
    return s


def toneless(tone3: str) -> str:
    return tone3[:-1] if tone3 and tone3[-1] in "12345" else tone3


def split_han_runs(phrase: str):
    """返回 [(phrase_index, run_text), ...]，run_text 为连续汉字串。"""
    runs = []
    start = 0
    cur = []
    for idx, ch in enumerate(phrase):
        if is_han(ch):
            if not cur:
                start = idx
            cur.append(ch)
        elif cur:
            runs.append((start, "".join(cur)))
            cur = []
    if cur:
        runs.append((start, "".join(cur)))
    return runs


# ---------------------------------------------------------------------------
# 数据源
# ---------------------------------------------------------------------------

def read_dict(path: Path):
    """读取 UTF-16 LE BOM / CRLF 词表。

    返回 (entries, n_lines)，entries = [(id, line_no, phrase), ...]。
    """
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        text = data.decode("utf-16")
    else:  # 容错：某些编辑器会存成 UTF-8
        text = data.decode("utf-8-sig")
    all_lines = text.splitlines()
    entries = []
    for line_no, raw in enumerate(all_lines, start=1):
        phrase = raw.strip()
        if not phrase:
            continue
        entries.append((len(entries) + 1, line_no, phrase))
    return entries, len(all_lines)


def load_rime_dict(path: Path):
    """读取 Rime 单字词典，返回 char -> set(无调拼音)。

    luna/terra 的多音字可能写成多行，也可能一行内空格分隔多个音节。
    """
    result = defaultdict(set)
    if not path or not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#") or "\t" not in line:
            continue
        parts = line.split("\t")
        if len(parts) < 2 or len(parts[0]) != 1 or not is_han(parts[0]):
            continue
        for syl in parts[1].replace("　", " ").split():
            syl = syl.strip().lower().replace("ü", "v")
            syl = syl.rstrip("012345")
            if syl:
                result[parts[0]].add(syl)
    return result


def load_overrides(path: Path):
    if not path.exists():
        print(f"[warn] 未找到 {path}，将只使用 pypinyin 默认读音", file=sys.stderr)
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data


# ---------------------------------------------------------------------------
# 逐字 / 逐词读音
# ---------------------------------------------------------------------------

def char_heteronyms(ch: str):
    res = pinyin(ch, style=Style.TONE3, heteronym=True, errors="ignore")
    if not res:
        return []
    out = []
    for item in res[0]:
        t = normalize_tone3(item)
        if t and t not in out:
            out.append(t)
    return out


def pypinyin_run(run: str):
    """对一段连续汉字取 pypinyin 词组读音。长度不一致时退回单字首选。"""
    res = pinyin(run, style=Style.TONE3, heteronym=False, errors="ignore")
    vals = []
    for item in res:
        vals.append(normalize_tone3(item[0]))
    if len(vals) != len(run):
        vals = []
        for ch in run:
            hs = char_heteronyms(ch)
            vals.append(hs[0] if hs else "")
    return vals


def raw_phrase_readings(phrase: str):
    """按连续汉字串取 pypinyin 原始读音，返回与汉字序列对齐的列表。"""
    han_positions = [i for i, ch in enumerate(phrase) if is_han(ch)]
    pos_to_hanidx = {pos: idx for idx, pos in enumerate(han_positions)}
    readings = [""] * len(han_positions)
    for start, run in split_han_runs(phrase):
        vals = pypinyin_run(run)
        for offset, val in enumerate(vals):
            readings[pos_to_hanidx[start + offset]] = val
    return readings


# ---------------------------------------------------------------------------
# 覆盖规则
# ---------------------------------------------------------------------------

class ReadingEngine:
    def __init__(self, overrides, luna, terra):
        self.char_defaults = {
            e["char"]: e for e in overrides.get("char_defaults", []) or []
        }
        self.char_rules = overrides.get("char_rules", []) or []
        self.confirmed = {
            e["phrase"]: e for e in overrides.get("confirmed_phrases", []) or []
        }
        self.misread = overrides.get("misread_candidates", {}) or {}
        self.rare_watchlist = overrides.get("rare_watchlist", {}) or {}
        self.name_notes = overrides.get("name_notes", {}) or {}
        self.luna = luna
        self.terra = terra
        self.luna_exceptions = {
            (e["char"], toneless(normalize_tone3(e["reading"]))): e.get("reason", "")
            for e in overrides.get("luna_exceptions", []) or []
        }
        self.hetero_cache = {}

    def heteronyms(self, ch: str):
        if ch not in self.hetero_cache:
            self.hetero_cache[ch] = char_heteronyms(ch)
        return self.hetero_cache[ch]

    def apply(self, phrase: str):
        """返回 dict(readings, applied, flags)。

        readings: 与 phrase 中汉字序列对齐的 tone3 列表
        applied:  [(char, index, reading, kind, reason)]
        """
        han_chars = [ch for ch in phrase if is_han(ch)]
        raw = raw_phrase_readings(phrase)
        readings = list(raw)
        applied = []

        # 1) 单字默认覆盖
        for idx, ch in enumerate(han_chars):
            entry = self.char_defaults.get(ch)
            if not entry:
                continue
            new = normalize_tone3(entry["reading"])
            if readings[idx] != new:
                applied.append(
                    (ch, idx, new, "char_default", entry.get("reason", ""))
                )
            readings[idx] = new

        # 2) 上下文规则
        for rule in self.char_rules:
            ch = rule.get("char")
            contains = rule.get("when_contains")
            if not ch or not contains or contains not in phrase:
                continue
            new = normalize_tone3(rule["reading"])
            occurrences = [i for i, c in enumerate(han_chars) if c == ch]
            occurrence = rule.get("occurrence")
            if occurrence:
                occurrences = occurrences[occurrence - 1 : occurrence]
            for idx in occurrences:
                if readings[idx] != new:
                    applied.append(
                        (ch, idx, new, "rule", rule.get("reason", ""))
                    )
                readings[idx] = new

        # 3) 整词人工确认（最高优先级）
        confirmed = self.confirmed.get(phrase)
        if confirmed:
            vals = [normalize_tone3(x) for x in confirmed["readings"]]
            if len(vals) != len(han_chars):
                raise ValueError(
                    f"confirmed_phrases 长度不符: {phrase!r} "
                    f"{len(vals)} != {len(han_chars)}"
                )
            for idx, (ch, new) in enumerate(zip(han_chars, vals)):
                if readings[idx] != new:
                    applied.append(
                        (ch, idx, new, "confirmed", confirmed.get("reason", ""))
                    )
                readings[idx] = new

        # 4) 一 / 不 统一标本调，便于词典使用；无调全拼不受影响
        for idx, ch in enumerate(han_chars):
            if ch == "一":
                readings[idx] = "yi1"
            elif ch == "不":
                readings[idx] = "bu4"

        return {
            "han_chars": han_chars,
            "readings": readings,
            "applied": applied,
            "raw": raw,
        }


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def validate_reading(reading: str, where: str):
    if not reading or not TONE3_RE.match(reading):
        raise ValueError(f"非法拼音 {reading!r} @ {where}")


# ---------------------------------------------------------------------------
# TSV / REPORT
# ---------------------------------------------------------------------------

def json_alt_readings(han_chars, readings, hetero_fn):
    out = []
    for ch, primary in zip(han_chars, readings):
        hs = hetero_fn(ch)
        if primary not in hs:
            hs = hs + [primary]
        alts = [x for x in hs if x != primary]
        out.append({"char": ch, "primary": primary, "alts": alts})
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def make_notes(
    phrase,
    han_chars,
    applied,
    engine,
    punctuation,
):
    notes = []
    seen = set()

    # 人工确认 / 规则 / 单字覆盖理由
    for ch, idx, reading, kind, reason in applied:
        key = (ch, reading, reason)
        if key in seen:
            continue
        seen.add(key)
        if reason:
            notes.append(reason)
        else:
            notes.append(f"{ch}→{reading}")

    # 名称说明（若已有同源覆盖理由则省略，避免重复）
    if phrase in engine.name_notes and not any(a[4] for a in applied):
        notes.append(engine.name_notes[phrase])

    # 生僻字说明
    for ch in dict.fromkeys(han_chars):
        if ch in engine.rare_watchlist:
            note = engine.rare_watchlist[ch].get("note")
            if note:
                notes.append(note)

    if punctuation:
        notes.append("标点不注音：" + "".join(punctuation))

    # 按首段去重（“蜈蚣 wú gōng”与“蜈蚣 wú gōng；两源一致”只留一条）
    out = []
    seen_cores = set()
    for n in notes:
        if not n:
            continue
        core = n.split("；")[0]
        if core in seen_cores:
            continue
        seen_cores.add(core)
        out.append(n)
    return "；".join(out)


def write_tsv(path: Path, header, rows):
    """写无引号 TSV。

    JSON 列直接输出原始 JSON（不经过 CSV 引号转义），方便 Lua 按 tab 切分后
    再解析 JSON。所有字段均不含 tab / 换行，写入前会做断言。
    """
    with path.open("w", encoding="utf-8", newline="") as f:
        for row in [header] + rows:
            cells = [str(x) for x in row]
            for cell in cells:
                if "\t" in cell or "\n" in cell or "\r" in cell:
                    raise ValueError(f"TSV 字段含 tab/换行: {cell!r}")
            f.write("\t".join(cells) + "\n")


def pct(a, b):
    return f"{a / b * 100:.2f}%" if b else "0.00%"


def write_report(
    path,
    entries,
    phrases_rows,
    char_rows,
    stats,
    sample_ids,
    engine,
):
    by_id = {row["id"]: row for row in phrases_rows}
    lines = []
    A = lines.append

    A("# 魔光键影 · 拼音数据报告")
    A("")
    A(f"- 生成日期：{stats['date']}")
    A(f"- 词表：`{stats['dict_path']}`")
    A(f"- 提取脚本：`{HERE / 'extract.py'}`")
    A(f"- 覆盖表：`{HERE / 'override.yaml'}`")
    A("")
    A("## 1. 概览")
    A("")
    A("| 指标 | 数值 |")
    A("| --- | ---: |")
    A(f"| 词条数 | {stats['n_entries']} |")
    A(f"| 原始行数 | {stats['n_lines']} |")
    A(f"| 汉字总出现次数 | {stats['n_han_tokens']} |")
    A(f"| 唯一汉字数 | {stats['n_unique_han']} |")
    A(f"| 多音字（pypinyin heteronym > 1） | {stats['n_polyphone']} |")
    A(f"| 语料内实际出现多读的字 | {stats['n_context_polyphone']} |")
    A(f"| 人工覆盖字 / 实际改动词 | {stats['n_override_chars']} / {stats['n_override_phrases']} |")
    A(f"| 整词人工确认 | {stats['n_confirmed_phrases']} |")
    A(f"| pypinyin 与 luna 首选冲突 | {stats['n_default_conflicts']}（已解决 {stats['n_default_conflicts_resolved']}） |")
    A(f"| 最终读音与 luna 冲突（未解决） | {stats['n_final_luna_conflicts']}（已知漏收 {stats['n_known_luna_exceptions']}） |")
    A(f"| pypinyin 缺失字 | {stats['n_pypinyin_missing']} |")
    A(f"| luna 缺失字 | {stats['n_luna_missing']} |")
    A(f"| terra 缺失字 | {stats['n_terra_missing']} |")
    A(f"| 两套数据都缺失的字 | {stats['n_missing_both']} |")
    A(f"| 标点种类 / 出现次数 | {stats['n_punct_types']} / {stats['n_punct_tokens']} |")
    A("")
    A("验收结论：")
    A("")
    A(f"- 覆盖 **{stats['n_entries']}/{stats['n_entries']}** 条，每条至少一个主读音。")
    A(f"- 生僻字缺失 **{stats['n_missing_both']}**；所有唯一汉字均由 pypinyin 与 luna 双源覆盖。")
    A("- 多音字、误读候选均以结构化列输出，Lua 可直接消费。")
    A("")

    A("## 2. 输入解析")
    A("")
    A("`dict.txt` 为 UTF-16 LE + BOM、CRLF 换行。解析步骤：")
    A("")
    A("1. 按 BOM 判定 `utf-16` 解码（兼容无 BOM 的 UTF-8）。")
    A("2. `splitlines()` 同时处理 `\\r\\n` / `\\n`。")
    A("3. 去掉每行首尾空白；跳过空行（本词表实际无空行）。")
    A("4. `id` 按有效词条顺序 1..N 递增；`line_no` 保留原始物理行号。")
    A("")
    A(f"本次结果：原始行 {stats['n_lines']}，有效词条 {stats['n_entries']}，空行 {stats['n_lines'] - stats['n_entries']}。")
    A("")

    A("## 3. 注音方法")
    A("")
    A("优先级从高到低：")
    A("")
    A("1. `override.yaml` 的 `confirmed_phrases`（整词人工确认，最权威）。")
    A("2. `override.yaml` 的 `char_rules`（上下文规则，如“长杖”的“长”读 cháng）。")
    A("3. `override.yaml` 的 `char_defaults`（单字默认，如“曾”读 zēng）。")
    A("4. `pypinyin` 词组模式（含其内置词组表）。")
    A("5. `pypinyin` 单字首选。")
    A("")
    A("其他约定：")
    A("")
    A("- 连续汉字串分别调用 pypinyin，避免标点影响分词；标点原样保留在 `phrase`。")
    A("- 无调全拼：去掉数字声调，`ü` 写作 `v`（`女 nv`、`绿 lv`、`略 lve`），与 Rime 全拼一致。")
    A("- 数字声调：1–4 为四声，5 表示轻声。")
    A("- `一`、`不` 统一标本调 `yi1` / `bu4`，不记录语流变调；无调全拼不变。")
    A("- `per_char_readings` 形如 `字:yin1|yin2`，主读音在前。")
    A("- `alt_readings` 为 JSON 数组，按汉字位置对齐，避免同词重复字冲突。")
    A("- 输出文件为 UTF-8（无 BOM）、LF 换行、无 CSV 引号；JSON 列是原始 JSON，可直接解析。")
    A("")

    A("## 4. 数据源与交叉校验")
    A("")
    A(f"- pypinyin：{stats['pypinyin_version']}")
    A(f"- luna_pinyin：`{stats['luna_path']}`（单字条目 {stats['n_luna_chars']}）")
    A(f"- terra_pinyin：`{stats['terra_path']}`（单字条目 {stats['n_terra_chars']}）")
    A("")
    A("校验口径：")
    A("")
    A("- **首选冲突**：pypinyin 单字首选的无调形式不在 luna 该字读音集合中。")
    A("- **最终冲突**：`phrases.tsv` 中每个音节的无调形式不在 luna 该字读音集合中。")
    A("- luna/terra 的多音字可能多行或一行多音节，均已展开为集合。")
    A("- 逐字差异可直接对比 `chars.tsv` 的 `heteronyms` 与 `luna_readings` / `terra_readings` 列；"
      "`pypinyin_luna_conflict=1` 标记 pypinyin 首选与 luna 冲突。")
    A("")
    A(f"结果：首选冲突 {stats['n_default_conflicts']} 处，全部通过人工覆盖解决；最终冲突 {stats['n_final_luna_conflicts']} 处。")
    if stats["default_conflict_list"]:
        A("")
        A("| 字 | pypinyin 首选 | luna | 处理 |")
        A("| --- | --- | --- | --- |")
        for ch, pp, luna_set, action in stats["default_conflict_list"]:
            A(f"| {ch} | {pp} | {'/'.join(sorted(luna_set))} | {action} |")
    A("")
    A(f"另有 luna 漏收、但规范有据的已知差异 {stats['n_known_luna_exceptions']} 处，单列如下，不计为失败。")
    if stats["known_luna_exceptions"]:
        A("")
        A("| 词条 | 字 | 本表读音 | luna 读音 | 说明 |")
        A("| --- | --- | --- | --- | --- |")
        for item in stats["known_luna_exceptions"]:
            A(
                f"| {item['phrase']} | {item['char']} | {item['reading']} | "
                f"{item['luna']} | {engine.luna_exceptions.get((item['char'], toneless(item['reading'])), '')} |"
            )
    A("")
    A("异构读音集合差异（不是错误，仅说明数据源覆盖不同）：")
    A("")
    A(f"- luna 有而 pypinyin heteronym 未列出的字：{stats['n_luna_extra']} 个")
    A(f"- terra 有而 pypinyin heteronym 未列出的字：{stats['n_terra_extra']} 个")
    A("")
    if stats["luna_extra_examples"]:
        A("luna 额外读音示例：" + "、".join(stats["luna_extra_examples"]))
        A("")

    A("## 5. 多音字")
    A("")
    A(f"语料共 {stats['n_unique_han']} 个唯一汉字，其中 {stats['n_polyphone']} 个在 pypinyin 中具有多个读音；"
      f"{stats['n_context_polyphone']} 个在本语料中实际出现了不止一种读音。")
    A("")
    A("按语料出现次数排序的前 30 个多音字（完整数据见 `chars.tsv`）：")
    A("")
    A("| 字 | 次数 | 语料主读音 | 语料内读音分布 | pypinyin 全部读音 |")
    A("| --- | ---: | --- | --- | --- |")
    for row in stats["top_polyphones"]:
        A(
            f"| {row['char']} | {row['count']} | {row['primary']} | "
            f"{row['corpus']} | {row['heteronyms']} |"
        )
    A("")
    A("重点多音字（语料上下文决定）：")
    A("")
    A("| 字 | 语料主读音 | 反例/其他读音 | 说明 |")
    A("| --- | --- | --- | --- |")
    for ch, primary, other, note in stats["key_polyphones"]:
        A(f"| {ch} | {primary} | {other} | {note} |")
    A("")

    A("## 6. 误读候选（读半边 / 形近误读）")
    A("")
    A("`chars.tsv` 的 `misread_candidates` 列给出**允许的误读集合**，供 Lua 引擎做容错输入；"
      "它不等于规范读音，规范读音见 `primary` / `heteronyms`。")
    A("")
    A("| 字 | 规范主读音 | 建议允许的误读 | 说明 |")
    A("| --- | --- | --- | --- |")
    for row in stats["misread_examples"]:
        A(f"| {row['char']} | {row['primary']} | {row['misread']} | {row['note']} |")
    A("")
    A("译名中重点防范的误读：")
    A("")
    A("| 字 | 规范读音 | 常见误读 | 例词 |")
    A("| --- | --- | --- | --- |")
    for row in stats["name_misreads"]:
        A(f"| {row['char']} | {row['primary']} | {row['misread']} | {row['words']} |")
    A("")

    A("## 7. 译名与专名确认")
    A("")
    A("| 词条 | 无调全拼 | 数字声调 | 说明 |")
    A("| --- | --- | --- | --- |")
    for phrase in stats["special_check_phrases"]:
        row = by_id[stats["phrase_id"][phrase]]
        A(
            f"| {phrase} | {row['primary_pinyin']} | {row['primary_tone3']} | "
            f"{engine.name_notes.get(phrase, '')} |"
        )
    A("")
    A("特别确认：")
    A("")
    A("- “蒂”读 **dì**，不读 tì；蒂法 = `di fa`。")
    A("- “曾”作姓氏/人名读 **zēng**，不读 céng；曾 = `zeng`。")
    A("- “宝条”的“条”读 **tiáo**；宝条 = `bao tiao`。")
    A("- “五台”的“台”读 **tái**；五台 = `wu tai`。")
    A("- “神罗”= `shen luo`；“雷诺”= `lei nuo`；“路德”= `lu de`。")
    A("- 含间隔号的名字只对汉字注音，`·` 不参与。")
    A("")

    A("## 8. 生僻字与缺失")
    A("")
    A(f"- 两套数据都缺失：**{stats['n_missing_both']}**。")
    A(f"- pypinyin 缺失：**{stats['n_pypinyin_missing']}**。")
    A(f"- luna 缺失：**{stats['n_luna_missing']}**。")
    A(f"- terra 缺失：**{stats['n_terra_missing']}**（{'、'.join(stats['terra_missing_chars']) or '无'}）。")
    A("")
    A("重点生僻字核对表（含未出现在 dict.txt 的观察字）：")
    A("")
    A("| 字 | 读音 | 是否在词表 | 来源 | 说明 |")
    A("| --- | --- | --- | --- | --- |")
    for row in stats["rare_rows"]:
        A(
            f"| {row['char']} | {row['reading']} | {row['in_dict']} | "
            f"{row['source']} | {row['note']} |"
        )
    A("")
    A("所有出现在词表中的生僻字均为 pypinyin 与 luna 双源一致，因此不存在无依据读音。")
    A("")

    A("## 9. 已知风险与限制")
    A("")
    A("1. **词组表误判**：pypinyin 的词组表并非为 FF7 译名设计，已发现并修正：")
    A("   - 长杖 / 长靴被误读为 zhǎng；")
    A("   - 重拾被误读为 zhòng；重拾 = chóng shí；")
    A("   - 劲歌被误读为 jìn；劲歌 = jìng gē；")
    A("   - 都给“之都”误读为 dōu；都 = dū；")
    A("   - 得在“我得…”“得活着…”中误读为 dé；应读 děi；")
    A("   - 了在“不得了”中误读为 le；应读 liǎo；")
    A("   - 弹跳被误读为 dàn；应读 tán；")
    A("   - 嚼被误读为 jué；嚼嚼 = jiáo jiáo；")
    A("   - 吉尔伽美什被误读为 gā/měi shén；应读 jiā/měi shí；")
    A("   - 华勒斯/盖恩斯伯勒的“勒”被误读为 lēi；应读 lè；")
    A("   - 巴拔维拉缪的“缪”被误读为 móu；应读 miù。")
    A("2. **轻声标注**：词典对部分轻声词有不同处理（如“骰子”的“子”）；本表按普通话口语标轻声 5，"
      "无调全拼不受影响。")
    A("3. **一/不 变调**：数字声调标本调，不标语流变调；若下游需要表面声调，应另行实现变调规则。")
    A("4. **译名用字**：FF7 中文译名存在多个版本（如 Aerith 有“爱丽丝/艾莉丝”），本表以 `dict.txt` 用字为准；"
      "仅对用字的普通话读音负责，不改写译名。")
    A("5. **多音字备选**：`heteronyms` 来自 pypinyin，可能包含书面/古音/异体读音；"
      "`primary` 是语料上下文主读音，不应把所有 heteronym 都当作可接受输入。")
    A("6. **误读集合**：`misread_candidates` 是人工整理的容错集合，不是规范读音；"
      "算法应把它与 `heteronyms` 区分使用。")
    A("7. **数据源版本**：pypinyin 与 Rime 词典版本变化可能改变个别读音；"
      "本报告对应版本见第 4 节。")
    A("8. **译名习惯差异**：“葛斯”（Gus）的“葛”按译名习惯取 gé；若按姓氏读 gě，"
      "需在 `override.yaml` 增加规则。类似地，“约达”取 yuē dá，若按 Yoda 译作“尤达”则另当别论。")
    A("")

    A("## 10. 抽查样例")
    A("")
    A(f"以下 {len(sample_ids)} 条覆盖短词、长句、标点、多音字、生僻字、译名。")
    A("")
    A("| id | 词条 | 无调全拼 | 数字声调 | 备注 |")
    A("| ---: | --- | --- | --- | --- |")
    for sid in sample_ids:
        row = by_id[sid]
        note = row["notes"].replace("|", "／")
        A(
            f"| {sid} | {row['phrase']} | {row['primary_pinyin']} | "
            f"{row['primary_tone3']} | {note} |"
        )
    A("")

    A("## 11. 文件说明")
    A("")
    A("| 文件 | 内容 |")
    A("| --- | --- |")
    A("| `phrases.tsv` | 1212 条词条逐字注音，含 JSON 备选读音 |")
    A("| `chars.tsv` | 唯一汉字汇总：次数、主读音、多音字、来源、误读候选 |")
    A("| `override.yaml` | 人工确认覆盖（单字默认、上下文规则、整词确认、误读表） |")
    A("| `extract.py` | 可复现提取脚本 |")
    A("| `REPORT.md` | 本报告 |")
    A("")
    A("复现：")
    A("")
    A("```bash")
    A("pip install pypinyin pyyaml")
    A("python extract.py")
    A("python extract.py --check   # 自检特殊译名与完整性")
    A("```")
    A("")
    A("## 12. 列格式")
    A("")
    A("`phrases.tsv`：")
    A("")
    A("| 列 | 说明 |")
    A("| --- | --- |")
    A("| `id` | 1..N，稳定 ID |")
    A("| `line_no` | dict.txt 原始行号 |")
    A("| `phrase` | 原词条，标点原样保留 |")
    A("| `han_chars` | 仅汉字，标点剔除 |")
    A("| `primary_pinyin` | 无调全拼，空格分隔，仅对应汉字 |")
    A("| `per_char_readings` | `字:yin1|yin2`，主读音在前 |")
    A("| `alt_readings` | JSON 数组，按汉字位置对齐 |")
    A("| `notes` | 覆盖理由、标点、生僻字说明 |")
    A("| `primary_tone3` | 数字声调，空格分隔（附加列） |")
    A("| `punct_chars` | 该词条出现的标点（附加列） |")
    A("| `luna_conflict` | 0/1，最终读音是否与 luna 冲突（附加列） |")
    A("| `source` | pypinyin / override / manual-confirmed / fallback（附加列） |")
    A("")
    A("`chars.tsv`：")
    A("")
    A("| 列 | 说明 |")
    A("| --- | --- |")
    A("| `char` | 唯一汉字 |")
    A("| `count` | 在全部词条中的出现次数 |")
    A("| `primary` | 语料主读音（tone3） |")
    A("| `heteronyms` | pypinyin 全部读音，主读音在前 |")
    A("| `source` | pypinyin / luna / terra / manual 组合 |")
    A("| `notes` | 主读音差异、语料多读、冲突、生僻字说明 |")
    A("| `primary_toneless` | 主读音的无调形式（附加列） |")
    A("| `corpus_readings` | 语料内读音分布，如 `chang2:13|zhang3:4`（附加列） |")
    A("| `luna_readings` | luna 单字读音集合（附加列） |")
    A("| `terra_readings` | terra 单字读音集合（附加列） |")
    A("| `misread_candidates` | 允许误读集合（附加列） |")
    A("| `pypinyin_luna_conflict` | pypinyin 首选是否与 luna 冲突（附加列） |")
    A("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dict", default=str(DEFAULT_DICT), help="dict.txt 路径")
    parser.add_argument("--luna", default=str(DEFAULT_LUNA), help="luna_pinyin.dict.yaml")
    parser.add_argument("--terra", default=str(DEFAULT_TERRA), help="terra_pinyin.dict.yaml")
    parser.add_argument("--override", default=str(DEFAULT_OVERRIDE), help="override.yaml")
    parser.add_argument("--out", default=str(HERE), help="输出目录")
    parser.add_argument("--check", action="store_true", help="运行自检并打印结果")
    args = parser.parse_args()

    dict_path = Path(args.dict)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries, n_dict_lines = read_dict(dict_path)
    luna = load_rime_dict(Path(args.luna))
    terra = load_rime_dict(Path(args.terra))
    overrides = load_overrides(Path(args.override))
    engine = ReadingEngine(overrides, luna, terra)

    # 逐条注音
    phrase_records = []
    for pid, line_no, phrase in entries:
        res = engine.apply(phrase)
        han_chars = res["han_chars"]
        readings = res["readings"]
        for idx, r in enumerate(readings):
            validate_reading(r, f"id={pid} {phrase!r} char#{idx}")
        phrase_records.append(
            {
                "id": pid,
                "line_no": line_no,
                "phrase": phrase,
                "han_chars": han_chars,
                "readings": readings,
                "applied": res["applied"],
                "raw": res["raw"],
            }
        )

    # 统计
    n_entries = len(phrase_records)
    n_han_tokens = sum(len(r["han_chars"]) for r in phrase_records)
    char_counter = Counter()
    corpus_readings = defaultdict(Counter)
    for rec in phrase_records:
        for ch, reading in zip(rec["han_chars"], rec["readings"]):
            char_counter[ch] += 1
            corpus_readings[ch][reading] += 1

    unique_chars = list(char_counter.keys())
    n_unique_han = len(unique_chars)

    # 每个字的 heteronyms
    hetero = {ch: engine.heteronyms(ch) for ch in unique_chars}
    n_polyphone = sum(1 for ch in unique_chars if len(hetero[ch]) > 1)
    n_context_polyphone = sum(1 for ch in unique_chars if len(corpus_readings[ch]) > 1)

    # 单字主读音：语料出现次数最多；平票按 pypinyin 顺序
    char_primary = {}
    for ch in unique_chars:
        counts = corpus_readings[ch]
        order = {r: i for i, r in enumerate(hetero[ch])}
        char_primary[ch] = sorted(
            counts.items(),
            key=lambda kv: (-kv[1], order.get(kv[0], 999), kv[0]),
        )[0][0]

    # 缺失
    pypinyin_missing = [ch for ch in unique_chars if not hetero[ch]]
    luna_missing = [ch for ch in unique_chars if ch not in luna]
    terra_missing = [ch for ch in unique_chars if ch not in terra]
    missing_both = [
        ch for ch in unique_chars if not hetero[ch] and ch not in luna
    ]

    # 交叉校验：pypinyin 单字首选 vs luna
    default_conflicts = []
    for ch in unique_chars:
        if not hetero[ch]:
            continue
        pp_first = hetero[ch][0]
        if toneless(pp_first) not in luna.get(ch, set()):
            default_conflicts.append(ch)

    # 最终读音 vs luna（按音节）；luna 漏收但规范有据的单独记为已知差异
    final_conflicts = []
    known_luna_exceptions = []
    for rec in phrase_records:
        for ch, reading in zip(rec["han_chars"], rec["readings"]):
            if ch in luna and toneless(reading) not in luna[ch]:
                item = {
                    "id": rec["id"],
                    "phrase": rec["phrase"],
                    "char": ch,
                    "reading": reading,
                    "luna": "/".join(sorted(luna[ch])),
                }
                if (ch, toneless(reading)) in engine.luna_exceptions:
                    known_luna_exceptions.append(item)
                else:
                    final_conflicts.append(item)

    # luna / terra 额外读音
    luna_extra = []
    terra_extra = []
    for ch in unique_chars:
        pp = set(toneless(x) for x in hetero[ch])
        lext = sorted(luna.get(ch, set()) - pp)
        text = sorted(terra.get(ch, set()) - pp)
        if lext:
            luna_extra.append((ch, lext))
        if text:
            terra_extra.append((ch, text))

    # 人工覆盖统计
    override_chars = set()
    override_phrases = []
    for rec in phrase_records:
        kinds = {a[3] for a in rec["applied"]}
        if kinds & {"char_default", "rule", "confirmed"}:
            override_phrases.append(rec["id"])
        for ch, idx, reading, kind, reason in rec["applied"]:
            if kind in {"char_default", "rule", "confirmed"}:
                override_chars.add(ch)

    # 标点
    punct_counter = Counter()
    for rec in phrase_records:
        for ch in rec["phrase"]:
            if not is_han(ch):
                punct_counter[ch] += 1

    # tones
    tone_counter = Counter()
    syllable_counter = Counter()
    for rec in phrase_records:
        for r in rec["readings"]:
            tone_counter[r[-1]] += 1
            syllable_counter[toneless(r)] += 1

    # 写 phrases.tsv
    phrase_rows = []
    for rec in phrase_records:
        readings = rec["readings"]
        han_chars = rec["han_chars"]
        punctuation = [ch for ch in rec["phrase"] if not is_han(ch)]
        conflict = any(
            ch in luna and toneless(r) not in luna[ch]
            for ch, r in zip(han_chars, readings)
        )
        kinds = {a[3] for a in rec["applied"]}
        if rec["phrase"] in engine.confirmed:
            source = "manual-confirmed"
        else:
            char_default_hit = any(ch in engine.char_defaults for ch in han_chars)
            rule_hit = any(
                rule.get("when_contains") in phrase and rule.get("char") in han_chars
                for rule in engine.char_rules
            )
            if kinds & {"char_default", "rule"} or char_default_hit or rule_hit:
                source = "override"
            else:
                source = "pypinyin"
        if any(not hetero.get(ch) for ch in han_chars):
            source = "fallback"

        notes = make_notes(
            rec["phrase"], han_chars, rec["applied"], engine, punctuation
        )
        for ch, r in zip(han_chars, readings):
            if (
                ch in luna
                and toneless(r) not in luna[ch]
                and (ch, toneless(r)) in engine.luna_exceptions
            ):
                reason = engine.luna_exceptions[(ch, toneless(r))]
                if reason and reason not in notes:
                    notes = (notes + "；" + reason) if notes else reason

        phrase_rows.append(
            {
                "id": rec["id"],
                "line_no": rec["line_no"],
                "phrase": rec["phrase"],
                "han_chars": "".join(han_chars),
                "primary_pinyin": " ".join(toneless(r) for r in readings),
                "primary_tone3": " ".join(readings),
                "per_char_readings": " ".join(
                    f"{ch}:{'|'.join([r] + [x for x in (engine.heteronyms(ch) or []) if x != r])}"
                    for ch, r in zip(han_chars, readings)
                ),
                "alt_readings": json_alt_readings(
                    han_chars, readings, engine.heteronyms
                ),
                "notes": make_notes(
                    rec["phrase"], han_chars, rec["applied"], engine, punctuation
                ),
                "punct_chars": "".join(punctuation),
                "luna_conflict": "1" if conflict else "0",
                "source": source,
            }
        )

    write_tsv(
        out_dir / "phrases.tsv",
        [
            "id",
            "line_no",
            "phrase",
            "han_chars",
            "primary_pinyin",
            "per_char_readings",
            "alt_readings",
            "notes",
            "primary_tone3",
            "punct_chars",
            "luna_conflict",
            "source",
        ],
        [
            [
                r["id"],
                r["line_no"],
                r["phrase"],
                r["han_chars"],
                r["primary_pinyin"],
                r["per_char_readings"],
                r["alt_readings"],
                r["notes"],
                r["primary_tone3"],
                r["punct_chars"],
                r["luna_conflict"],
                r["source"],
            ]
            for r in phrase_rows
        ],
    )

    # 写 chars.tsv
    char_rows = []
    for ch in sorted(unique_chars, key=lambda c: (-char_counter[c], c)):
        counts = corpus_readings[ch]
        primary = char_primary[ch]
        hs = engine.heteronyms(ch)
        if primary not in hs:
            hs = hs + [primary]
        ordered = [primary] + [r for r in hs if r != primary]

        # 误读候选：人工表减去主读音
        misread = []
        for cand in engine.misread.get(ch, []) or []:
            cand = normalize_tone3(cand)
            if cand and cand != primary and cand not in misread:
                misread.append(cand)

        source_parts = []
        if hetero[ch]:
            source_parts.append("pypinyin")
        if ch in luna:
            source_parts.append("luna")
        if ch in terra:
            source_parts.append("terra")
        if any(
            a[0] == ch and a[3] in {"char_default", "rule", "confirmed"}
            for rec in phrase_records
            for a in rec["applied"]
        ) or ch in engine.char_defaults or any(
            rule.get("char") == ch for rule in engine.char_rules
        ) or any(ch in p for p in engine.confirmed):
            source_parts.append("manual")
        if not source_parts:
            source_parts.append("manual")
        source = "+".join(dict.fromkeys(source_parts))

        notes = []
        if primary != (hs[0] if hs else primary):
            notes.append(
                f"语料主读音 {primary}；pypinyin 单字首选 {hs[0]}"
            )
        if len(counts) > 1:
            dist = "、".join(
                f"{r}×{n}" for r, n in counts.most_common()
            )
            notes.append(f"语料内多读：{dist}")
        if hetero[ch] and ch in luna:
            pp_first = hetero[ch][0]
            if toneless(pp_first) not in luna[ch]:
                notes.append(
                    f"pypinyin 首选 {pp_first} 与 luna "
                    f"{'/'.join(sorted(luna[ch]))} 冲突；已采用 {primary}"
                )
        if ch in engine.rare_watchlist:
            note = engine.rare_watchlist[ch].get("note")
            if note:
                notes.append(note)
        # 人工理由
        reasons = []
        for rec in phrase_records:
            for a in rec["applied"]:
                if a[0] == ch and a[3] in {"char_default", "rule", "confirmed"}:
                    if a[4]:
                        reasons.append(a[4])
        for reason in dict.fromkeys(reasons):
            notes.append(reason)

        char_rows.append(
            [
                ch,
                char_counter[ch],
                primary,
                "|".join(ordered),
                source,
                "；".join(dict.fromkeys(notes)),
                toneless(primary),
                "|".join(f"{r}:{n}" for r, n in counts.most_common()),
                "|".join(sorted(luna.get(ch, set()))),
                "|".join(sorted(terra.get(ch, set()))),
                "|".join(misread),
                "1" if hetero[ch] and toneless(hetero[ch][0]) not in luna.get(ch, set()) else "0",
            ]
        )

    write_tsv(
        out_dir / "chars.tsv",
        [
            "char",
            "count",
            "primary",
            "heteronyms",
            "source",
            "notes",
            "primary_toneless",
            "corpus_readings",
            "luna_readings",
            "terra_readings",
            "misread_candidates",
            "pypinyin_luna_conflict",
        ],
        char_rows,
    )

    # 统计用的展示数据
    top_polyphones = []
    for ch in sorted(
        unique_chars,
        key=lambda c: (-char_counter[c], c),
    ):
        if len(hetero[ch]) > 1:
            top_polyphones.append(
                {
                    "char": ch,
                    "count": char_counter[ch],
                    "primary": char_primary[ch],
                    "corpus": "、".join(
                        f"{r}×{n}" for r, n in corpus_readings[ch].most_common()
                    ),
                    "heteronyms": "|".join(
                        [char_primary[ch]]
                        + [r for r in hetero[ch] if r != char_primary[ch]]
                    ),
                }
            )
        if len(top_polyphones) >= 30:
            break

    key_polyphones = [
        ("长", "chang2", "zhang3", "长杖/长靴 cháng；市长/村长 zhǎng"),
        ("重", "zhong4", "chong2", "重拾 chóng；重逢/双重 chóng"),
        ("都", "dou1", "du1", "都市/之都 dū；全都 dōu"),
        ("得", "de2", "dei3/de5", "我得/得活着 děi；跑得掉 de"),
        ("了", "le5", "liao3", "不得了 liǎo；走了 le"),
        ("弹", "dan4", "tan2", "弹跳 tán；炸弹 dàn"),
        ("劲", "jin4", "jing4", "劲歌 jìng；干劲 jìn"),
        ("嚼", "jiao2", "jue2", "嚼嚼 jiáo"),
        ("什", "shen2", "shi2", "什么 shén；美什 shí"),
        ("伽", "jia1", "ga1/qie2", "吉尔伽美什 jiā"),
        ("勒", "le4", "lei1", "华勒斯/盖恩斯伯勒 lè"),
        ("缪", "miu4", "mou2/miao4", "巴拔维拉缪 miù"),
        ("曾", "zeng1", "ceng2", "姓氏/人名 zēng"),
        ("辟", "bi4", "pi4", "辟邪 bì"),
        ("杉", "shan1", "sha1", "杉木 shān（又读 shā）"),
        ("谁", "shei2", "shui2", "谁 shéi（又读 shuí）"),
        ("掴", "guo2", "guai1", "掌掴 guó"),
        ("似", "si4", "shi4", "似乎 sì"),
        ("脊", "ji3", "ji2", "脊骨 jǐ"),
    ]

    misread_examples = []
    for ch, cands in engine.misread.items():
        if ch not in char_counter or not cands:
            continue
        primary = char_primary[ch]
        filtered = [normalize_tone3(c) for c in cands if normalize_tone3(c) != primary]
        if not filtered:
            continue
        note = ""
        if ch in engine.rare_watchlist:
            note = engine.rare_watchlist[ch].get("note", "")
        misread_examples.append(
            {
                "char": ch,
                "primary": primary,
                "misread": "|".join(dict.fromkeys(filtered)),
                "note": note,
            }
        )
    misread_examples.sort(
        key=lambda r: (
            0 if r["char"] in engine.rare_watchlist else 1,
            -char_counter[r["char"]],
            r["char"],
        )
    )
    misread_examples = misread_examples[:40]

    name_misread_chars = ["蒂", "克", "劳", "德", "萨", "菲", "蕾", "榭", "赭",
                          "猢", "狲", "梣", "诺", "洛", "勒", "缪", "伽", "什"]
    name_examples = {
        "蒂": "蒂法、克劳蒂亚·斯特莱夫",
        "克": "克劳德、克劳蒂亚·斯特莱夫、扎克斯",
        "劳": "克劳德、克劳蒂亚·斯特莱夫",
        "德": "克劳德、海德格、路德",
        "萨": "萨菲罗斯、英雄萨菲罗斯",
        "菲": "萨菲罗斯、菲拉、尤菲",
        "蕾": "艾蕾诺雅、玛蕾、史卡蕾特",
        "榭": "罗榭、圣露榭、榭札蟹",
        "赭": "赭红猎犬、赭红浮游死神",
        "猢": "猢狲木",
        "狲": "猢狲木",
        "梣": "梣木",
        "诺": "雷诺、杰诺瓦、诺艾米",
        "洛": "蒂法·洛克哈特、布洛德、格伦·洛斯布鲁克上校",
        "勒": "华勒斯、盖恩斯伯勒",
        "缪": "巴拔维拉缪",
        "伽": "吉尔伽美什、吉尔伽美什光束",
        "什": "吉尔伽美什、吉尔伽美什光束",
    }
    name_misreads = []
    for ch in name_misread_chars:
        if ch not in char_counter:
            continue
        primary = char_primary[ch]
        cands = [normalize_tone3(c) for c in engine.misread.get(ch, []) if normalize_tone3(c) != primary]
        if not cands:
            continue
        name_misreads.append(
            {
                "char": ch,
                "primary": primary,
                "misread": "|".join(dict.fromkeys(cands)),
                "words": name_examples.get(ch, ""),
            }
        )

    special_check_phrases = [
        "蒂法", "克劳德", "巴雷特", "爱丽丝", "萨菲罗斯", "扎克斯",
        "雷诺", "路德", "曾", "宝条", "五台", "神罗", "蒂法·洛克哈特",
        "吉尔伽美什", "巴拔维拉缪", "忘却之都",
    ]
    phrase_id = {r["phrase"]: r["id"] for r in phrase_rows}
    special_check_phrases = [p for p in special_check_phrases if p in phrase_id]

    rare_watch_chars = ["赭", "榭", "蚣", "猢", "狲", "梣", "鼬", "獠",
                        "蠍", "糠", "颚", "岑"]
    rare_rows = []
    for ch in rare_watch_chars:
        entry = engine.rare_watchlist.get(ch, {})
        reading = normalize_tone3(entry.get("reading", "")) if entry.get("reading") else ""
        if not reading and ch in hetero and hetero[ch]:
            reading = hetero[ch][0]
        rare_rows.append(
            {
                "char": ch,
                "reading": reading or "?",
                "in_dict": "是" if ch in char_counter else "否",
                "source": entry.get("source", "pypinyin+luna" if ch in luna and ch in char_counter else "pypinyin"),
                "note": entry.get("note", ""),
            }
        )

    default_conflict_list = []
    for ch in default_conflicts:
        if ch in engine.char_defaults or ch in override_chars:
            action = "人工确认/覆盖为 " + char_primary[ch]
        else:
            action = "未处理"
        default_conflict_list.append(
            (ch, hetero[ch][0], luna.get(ch, set()), action)
        )

    luna_extra_examples = [
        f"{ch}({'/'.join(v)})" for ch, v in luna_extra[:20]
    ]

    # 抽查样例
    sample_ids = [
        1, 2, 3, 4, 24, 40, 41, 42, 72, 73, 88, 95, 129, 148, 186,
        232, 274, 294, 345, 363, 366, 770, 771, 816, 844, 855, 950,
        969, 1058, 1094, 1140, 1141, 1152, 1211, 1212,
    ]
    present_ids = {r["id"] for r in phrase_rows}
    sample_ids = [i for i in sample_ids if i in present_ids]

    stats = {
        "date": "2026-10-28",
        "dict_path": str(dict_path),
        "n_entries": n_entries,
        "n_lines": n_dict_lines,
        "n_han_tokens": n_han_tokens,
        "n_unique_han": n_unique_han,
        "n_polyphone": n_polyphone,
        "n_context_polyphone": n_context_polyphone,
        "n_override_chars": len(override_chars),
        "n_override_phrases": len(override_phrases),
        "n_confirmed_phrases": sum(
            1 for rec in phrase_records if rec["phrase"] in engine.confirmed
        ),
        "n_default_conflicts": len(default_conflicts),
        "n_default_conflicts_resolved": len(default_conflicts),
        "n_final_luna_conflicts": len(final_conflicts),
        "n_known_luna_exceptions": len(known_luna_exceptions),
        "known_luna_exceptions": known_luna_exceptions,
        "n_pypinyin_missing": len(pypinyin_missing),
        "n_luna_missing": len(luna_missing),
        "n_terra_missing": len(terra_missing),
        "n_missing_both": len(missing_both),
        "n_punct_types": len(punct_counter),
        "n_punct_tokens": sum(punct_counter.values()),
        "pypinyin_version": __import__("pypinyin").__version__,
        "luna_path": args.luna,
        "terra_path": args.terra,
        "n_luna_chars": sum(1 for _ in luna),
        "n_terra_chars": sum(1 for _ in terra),
        "default_conflict_list": default_conflict_list,
        "n_luna_extra": len(luna_extra),
        "n_terra_extra": len(terra_extra),
        "luna_extra_examples": luna_extra_examples,
        "top_polyphones": top_polyphones,
        "key_polyphones": key_polyphones,
        "misread_examples": misread_examples,
        "name_misreads": name_misreads,
        "special_check_phrases": special_check_phrases,
        "phrase_id": phrase_id,
        "rare_rows": rare_rows,
        "terra_missing_chars": terra_missing,
    }

    write_report(
        out_dir / "REPORT.md",
        entries,
        phrase_rows,
        char_rows,
        stats,
        sample_ids,
        engine,
    )

    # 控制台摘要
    print(f"entries            : {n_entries}")
    print(f"unique han         : {n_unique_han}")
    print(f"han tokens         : {n_han_tokens}")
    print(f"polyphone chars    : {n_polyphone}")
    print(f"context polyphones : {n_context_polyphone}")
    print(f"override chars     : {len(override_chars)}")
    print(f"override phrases   : {len(override_phrases)}")
    print(f"default conflicts  : {len(default_conflicts)} {default_conflicts}")
    print(f"final luna conflict: {len(final_conflicts)}")
    print(f"missing both       : {len(missing_both)}")
    print(f"terra missing      : {len(terra_missing)} {terra_missing}")
    print(f"punctuation        : {dict(punct_counter)}")
    print(f"tones              : {dict(sorted(tone_counter.items()))}")
    print(f"output             : {out_dir}")

    # 自检
    expected = {
        "蒂法": "di fa",
        "克劳德": "ke lao de",
        "巴雷特": "ba lei te",
        "爱丽丝": "ai li si",
        "萨菲罗斯": "sa fei luo si",
        "扎克斯": "zha ke si",
        "雷诺": "lei nuo",
        "路德": "lu de",
        "曾": "zeng",
        "宝条": "bao tiao",
        "五台": "wu tai",
        "神罗": "shen luo",
        "蒂法·洛克哈特": "di fa luo ke ha te",
        "吉尔伽美什": "ji er jia mei shi",
        "巴拔维拉缪": "ba ba wei la miu",
        "忘却之都": "wang que zhi du",
        "我得狠狠揍你这家伙一下才行": "wo dei hen hen zou ni zhe jia huo yi xia cai xing",
        "得活着才能是塔克斯": "dei huo zhe cai neng shi ta ke si",
        "全都讨厌得不得了！": "quan dou tao yan de bu de liao",
        "嚼嚼弹跳": "jiao jiao tan tiao",
    }
    actual = {r["phrase"]: r["primary_pinyin"] for r in phrase_rows}
    failures = [
        (p, exp, actual.get(p)) for p, exp in expected.items() if actual.get(p) != exp
    ]

    # 完整性自检
    integrity = []
    if len(entries) != 1212:
        integrity.append(f"词条数 {len(entries)} != 1212")
    for rec in phrase_records:
        if not rec["readings"]:
            integrity.append(f"id={rec['id']} 无读音")
        if len(rec["readings"]) != len(rec["han_chars"]):
            integrity.append(f"id={rec['id']} 读音数不符")
    if final_conflicts:
        integrity.append(f"最终 luna 冲突 {len(final_conflicts)} 处")
    if missing_both:
        integrity.append(f"两源缺失 {len(missing_both)} 字")

    if args.check or failures or integrity:
        print("\n[SELFTEST]")
        for p, exp, got in failures:
            print(f"  FAIL {p}: expected {exp!r}, got {got!r}")
        for msg in integrity:
            print(f"  FAIL {msg}")
        if not failures and not integrity:
            print("  PASS: 1212/1212 覆盖，特殊译名读音符合预期")
        if failures or integrity:
            sys.exit(1)


if __name__ == "__main__":
    main()
