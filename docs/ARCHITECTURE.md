# 架构设计

> 本文描述 1.0.0 的实际架构：Rime 负责按键/分词/候选窗口，Lua 负责全部匹配与排序，数据在构建期固化。

---

## 1. 总览

```
┌──────────────────────────────────────────────────────────────────┐
│                          Weasel 0.17.4                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ rime.dll (librime 1.13.1 + Lua 5.4.7)                     │  │
│  │                                                            │  │
│  │  键盘 → processors → segmentors → translators → filters   │  │
│  │                          │                                 │  │
│  │                          ▼                                 │  │
│  │              lua_translator@*ff7-ime                          │  │
│  │                          │                                 │  │
│  │            ┌─────────────┴─────────────┐                   │  │
│  │            ▼                           ▼                   │  │
│  │      ff7-ime.lua                    ff7-ime_data.lua             │  │
│  │  （配置/开关/适配）              （1212 条 + 变体/索引数据）│  │
│  │            │                                               │  │
│  │            ▼                                               │  │
│  │      ff7-ime_matcher.lua                                      │  │
│  │  （规范化 → 多通道 → 索引召回 → DP → 排序 → Top-N）        │  │
│  │            │                                               │  │
│  │            ▼                                               │  │
│  │   yield Candidate(type, start, end, text, comment)         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                          │                                       │
│                          ▼                                       │
│                  候选窗口 / 提交文本                              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. 分层与职责

| 层 | 文件 | 职责 | 不做什么 |
|---|---|---|---|
| Rime 方案 | `ff7-ime.schema.yaml` | schema 元信息、switches、engine 组件、speller、配置块 | 不写匹配逻辑 |
| 用户配置 | `ff7-ime.custom.yaml` | 覆盖 top_n/注释/模糊/容错/权重 | 不写代码 |
| Rime 适配 | `lua/ff7-ime.lua` | 读配置与开关、加载数据、调用 matcher、yield、异常回退 | 不实现匹配 |
| 匹配引擎 | `lua/ff7-ime_matcher.lua` | 规范化、八类通道、索引、DP、排序、Top-N | 不依赖 Rime |
| 数据 | `lua/ff7-ime_data.lua` | 1212 条词条、读音、变体、声母、换位、权重 | 不手改（构建生成） |
| 构建 | `tools/build_from_pinyin_data.py` | `phrases.tsv + override.yaml → ff7-ime_data.lua` | 不部署 |
| 安装 | `recipe.yaml` + Plum | 克隆仓库、复制 4 个运行时文件、官方选单启用 | 不改用户其他方案 |
| 测试 | `tests/`、`experiments/rime-harness/` | Lua 沙箱、全量评估、Rime C API、GUI | 不参与运行时 |

---

## 3. Rime 接线

### 3.1 Engine 组件

```yaml
engine:
  processors:
    - ascii_composer
    - key_binder
    - speller
    - punctuator
    - selector
    - navigator
    - express_editor
  segmentors:
    - ascii_segmentor
    - abc_segmentor
    - fallback_segmentor
  translators:
    - lua_translator@*ff7-ime
  filters:
    - uniquifier
```

- **没有** `script_translator` / `table_translator`：因此不会造句、不会产生词库外候选、不会创建用户词典。
- **没有** `simplifier`：输出词条就是 `data/dict.txt` 的简体原文（含标点），不做简繁转换。
- **只有一个 translator**：候选顺序完全由 Lua 的 yield 顺序决定。
- `uniquifier`：去重；1212 条文本本身唯一，不影响顺序。
- `punctuator`：保留标点键行为；词条内部的标点由 Lua 原样输出，不经过 punctuator。
- `key_binder`：在 preset 基础上追加 `Return`/`KP_Enter → space`，让回车和小键盘回车确认高亮候选。
- `style/inline_preedit: true`：写在 schema 顶层；Weasel 会从 schema 读取该值，把预编辑串内嵌到输入框。

### 3.2 Speller 与 segment

```yaml
speller:
  alphabet: zyxwvutsrqponmlkjihgfedcba
  initials: zyxwvutsrqponmlkjihgfedcba
  delimiter: "'"
  use_space: false
```

- `abc_segmentor` 会把连续的字母（含 `'`）识别为一个 `abc` segment；
- `initials = alphabet`、`finals` 为空、无 `algebra`，保证 `lkcc` 这类非法拼音串不会被拆成多个 segment；
- `lua_translator` 收到的是当前 segment 的原始子串，不是整条 composition；
- 输入 `lei'nuo` 时 `'` 保留在 input 中，`matcher.normalize` 去掉后再匹配。

### 3.3 Lua translator 契约（实测）

| 项 | 结论 |
|---|---|
| 注册 | `lua_translator@*ff7-ime` → `require("ff7-ime")` |
| 入口 | 模块返回表，字段 `init(env)` / `func(input, seg, env)` / `fini` |
| 候选 | `Candidate(type, start, end, text, comment)`，第一参是 type；`cand.preedit` 控制输入框内的预编辑串 |
| 偏移 | `seg.start` / `seg._end`，0-based 字节偏移 |
| 配置 | `env.engine.schema.config:get_int/get_bool/get_double/get_string`，缺失返回 nil |
| 开关 | `env.engine.context:get_option(name)`，实时反映 switches |
| 模块路径 | `<user_data_dir>/lua/?.lua`；共享目录 `data/lua/?.lua` 也搜索 |
| 标准库 | `luaL_openlibs`，`io/os/string/table/math/utf8` 可用 |
| 日志 | `log.info/warning/error` 可用；`print` 不可依赖 |
| 排序 | 同 segment 内按 `start`、`end`、`quality` 排序；本方案显式设置 `quality` |

> 不要使用 `seg:get_text()` / `seg:active_text()`（不存在或对 const Segment 不可用）；不要依赖 `seg.length`；不要使用 `gen_type`。

---

## 4. 数据流

### 4.1 构建期

```
data/dict.txt (UTF-16 LE BOM, 1212)
   │
   ├─ experiments/pinyin-data/extract.py
   │     pypinyin + luna_pinyin + terra_pinyin + override.yaml
   ▼
experiments/pinyin-data/phrases.tsv
   │  id, line_no, phrase, han_chars,
   │  primary_pinyin, per_char_readings, alt_readings, ...
   │
   ├─ tools/build_from_pinyin_data.py
   │     语料内上下文读音 + misread_candidates
   │     单字/双字组合 → fulls（最多 8）
   │     声母变体、相邻换位
   ▼
lua/ff7-ime_data.lua (416 KB)
   │
   ├─ recipe.yaml → Plum → Rime 用户目录（只装 schema + 3 个 Lua）
   └─ tests/lua/bulk_eval.js / run_cases.js
```

### 4.2 运行期（每次按键）

```
input (segment 原始串)
  │
  ▼
normalize: lower + 去非字母
  │
  ├─ canon_input（安全规则：zh/ch/sh、v/u）
  │
  ▼
build_index（首次/模糊开关变化时）
  │  by_first / by_init_letter / by_full / by_canon
  │  by_bigram / by_trigram / by_canon_bigram / by_canon_trigram
  │  by_syl_prefix / static_top
  ▼
阶段 1：廉价通道（无 DP）
  │  候选：by_first[首字母] 或 initial_mode 的声母字母并集
  │  精确/前缀/模糊/声母/换位
  ▼
若 best_cheap_raw < 0.93 且非 initial_mode：
  │  阶段 2：双/三字母重叠度排序 → Top-K(56) → 完整 score（含音节 DP）
  ▼
阶段 3：by_syl_prefix 召回 → 音节前缀子序列（meishao 等中段关键词）
  ▼
排序（score → channel_rank → 长度 → 权重 → 词典序）
  │
  ├─ 不足 N：bigram/trigram 回退池 + Damerau/Dice-LCS；static 兜底
  │
  ├─ preview：预测音节边界（diou -> di'ou），写入 cand.preedit
  ▼
yield N 个 Candidate（quality 递减）
```

---

## 5. 索引与缓存

### 5.1 索引构建

`build_index` 在第一次 `rank` 或 `init` 时构建，挂在数据表 `_ff7-ime_index` 上：

- `by_first`：每个 `fulls`/`swaps` 变体首字母 → id；
- `by_init_letter`：每个声母 token 首字母 → id；
- `by_full`：全拼变体 → id；
- `by_canon`：安全 canon 全拼 → id；
- `by_bigram` / `by_trigram`：原始全拼的双/三字母；
- `by_canon_bigram` / `by_canon_trigram`：逐音节模糊规范化全拼的双/三字母（DP 召回关键）；
- `by_syl_prefix`：每个音节读音的 1–3 字母前缀（原始 + 规范化），用于中段关键词召回；
- `syllables` / `syllable_prefixes` / `max_syllable`：预编辑分词用的合法音节及前缀集合；
- `static_top`：按权重/长度/order 的静态优先序。

### 5.2 重建条件

`build_index` 计算 `fuzzy_key`（12 个模糊开关的位串）：

- 与当前 `_ff7-ime_index_key` 相同：直接复用；
- 不同：清空每条词条的 `_ff7-ime_prepared` 与索引，重建 canons 和全部索引。

这样 F4 开关或 `ff7-ime/use_switches` 切换模糊音后，canons/索引不会过期。

### 5.3 缓存

- `prepare_phrase` 缓存每条词条的 `readings/fulls/canons/init_variants/init_flats/swaps/_firsts/_lasts/canon_full`；
- 每次 `rank` 共享 `cache[chunk.."\0"..reading]`，避免跨词条重复 Damerau 计算；
- 不对输入结果做全局 LRU；逐键输入本身就是新串，缓存收益有限。

---

## 6. 配置与开关

### 6.1 配置优先级

`ff7-ime.lua` 的 `build_options`：

1. `ff7-ime/use_switches: true` 时，F4 开关优先（`context:get_option`）；
2. 否则读 `ff7-ime/fuzzy/*` / `ff7-ime/typo/*` / `ff7-ime/initial/*`；
3. 都没有用 `ff7-ime_matcher.defaults`。

默认 `ff7-ime/use_switches: false`，即 **`*.custom.yaml` 是权威配置**；需要 F4 实时切换时改为 `true`。

### 6.2 关键配置

| 路径 | 类型 | 默认 | 说明 |
|---|---|---:|---|
| `ff7-ime/top_n` | int | 9 | 候选数 N |
| `ff7-ime/dp_max_candidates` | int | 56 | DP 短名单上限 |
| `ff7-ime/show_comment` | bool | true | 显示通道/拼音注释 |
| `ff7-ime/show_score` | bool | false | 注释显示分数（调试） |
| `ff7-ime/use_switches` | bool | false | true=F4 开关优先 |
| `ff7-ime/fuzzy/zh_z` … | bool | 见 schema | 12 个模糊规则 |
| `ff7-ime/typo/enabled` | bool | true | false=严格模式（只精确/模糊） |
| `ff7-ime/typo/max_edit` | int | 2 | Damerau 上限 0–4 |
| `ff7-ime/typo/transposition` | bool | true | 相邻字母换位 |
| `ff7-ime/typo/syllable_swap` | bool | true | 相邻音节换位 |
| `ff7-ime/initial/enabled` | bool | true | 声母/关键词通道 |
| `ff7-ime/keyword/gap_penalty` | double | 0.02 | 关键词跳跃惩罚 |
| `ff7-ime/keyword/syllable_subsequence` | bool | true | 中段音节前缀子序列（meishao） |
| `ff7-ime/fallback/use_lcs` | bool | true | 回退排序是否融合 Dice-LCS |
| `ff7-ime/fallback/dp_min_raw` | double | 0.65 | DP 低置信度门槛 |
| `ff7-ime/fallback/strong_raw` | double | 0.70 | 有强命中时改用小池 |
| `ff7-ime/fallback/fast_max_candidates` | int | 16 | 强命中时回退池上限 |
| `ff7-ime/fallback/max_candidates` | int | 96 | 无强命中时回退池上限 |
| `ff7-ime/preedit/enabled` | bool | true | 预测预编辑音节分隔符 |
| `ff7-ime/preedit/separator` | string | `'` | 预编辑分隔符（可改为空格） |
| `style/inline_preedit` | bool | true | Weasel 从 schema 读取，内嵌显示预编辑 |
| `ff7-ime/weights/*` | double | 见 schema | 通道权重 |

### 6.3 Switches

schema 定义 3 个标准开关 + 12 个模糊开关 + 2 个模式开关：

```
ascii_mode, full_shape, ascii_punct,
ff7-ime_fuzzy_zh_z … ff7-ime_fuzzy_v_u,
ff7-ime_initial, ff7-ime_typo
```

> **坑**：Rime 的 `switches` 是列表，按名字 patch 会被解析成数字索引 0，改错开关。若要 patch 开关默认值，使用 `switches/@<数字>/reset`，并数清顺序；日常建议直接改 `ff7-ime/fuzzy/*` 配置。

---

## 7. 错误处理与回退

- `ff7-ime.lua` 的 `init` 用 `pcall` 包住 `prepare_all`；失败时用默认配置再试。
- `func` 用 `pcall` 包住 `matcher.rank`；失败或空结果时 `fallback_results(top_n)` 用预构建顺序产出 N 个候选。
- `matcher.rank` 结果不足 N 时先 `fill_fallback`（n-gram 召回 + Damerau/Dice-LCS），仍不足才 `fill_static`。
- `format_comment` 对 `show_comment=false` 返回空串；`show_score=true` 才显示分数。
- `Candidate` 的 `quality` 设置包在 `pcall` 中，旧版本不支持的字段不会中断输入。
- 配置读取全部 `pcall` 包裹；缺失路径返回 nil，不抛错。

---

## 8. 部署架构

### 8.1 文件放置

```
%APPDATA%\Rime\
  ff7-ime.schema.yaml
  ff7-ime.custom.yaml
  lua\
    ff7-ime.lua
    ff7-ime_matcher.lua
    ff7-ime_data.lua
  default.custom.yaml        # schema_list 加入本方案
  build\                     # 部署生成
```

### 8.2 安装流程

安装由小狼毫官方入口完成，不依赖项目自带脚本：

1. 用户在 **方案选单设定 → 获取更多输入方案** 中输入 `Tanimodori/ff7-ime`；
2. `rime-install.bat` 检测到 Git Bash 后交给 Plum；
3. Plum 浅克隆整个仓库到 `%APPDATA%\plum\package\Tanimodori\ff7-ime`；
4. Plum 读取根 `recipe.yaml`，只复制 4 个文件到 Rime 用户目录：
   `ff7-ime.schema.yaml`、`lua/ff7-ime.lua`、`lua/ff7-ime_matcher.lua`、`lua/ff7-ime_data.lua`；
5. 安装器**不修改** `default.custom.yaml`；
6. 控制台关闭后，方案选单自动刷新；用户勾选“魔光键影”并确认，Weasel 自己写入
   `schema_list`；
7. Weasel 部署，生成 `build/ff7-ime.schema.yaml` 与 `build/default.yaml` 条目。

### 8.3 卸载流程

1. 在 **方案选单设定** 中取消勾选“魔光键影”，点击 **中**；
2. 删除用户目录中的 `ff7-ime.schema.yaml` 与 `lua/ff7-ime*.lua`（以及可选的
   `ff7-ime.custom.yaml`）；
3. 重新部署；
4. 其他方案（luna）保持可用。

---

## 9. 性能设计

| 措施 | 效果 |
|---|---|
| 两阶段：廉价通道优先 | 精确/前缀输入完全跳过 DP，约 5–10 ms/键 |
| 首字母/声母/双三字母索引 | 避免全量 1212 条扫描 |
| canonical 双三字母索引 | `ng→n` 模糊输入也能进入 DP 短名单 |
| DP 短名单 K=56 | 最坏延迟约 65 ms/键 |
| 扁平 DP 数组 | 避免每条词条分配二维表 |
| chunk/reading 缓存 | 跨词条复用 Damerau 结果 |
| 严格模式（typo 关闭） | 只做整音节匹配，更快 |
| 回退池上限 16/96 | 有强命中只算 16 条，无强命中最多 96 条 |
| 静态兜底 | 保证 N，不因无匹配卡死 |

---

## 10. 版本与兼容

- 目标：Weasel 0.17.4 / librime 1.13.1 / Windows x64；Lua 5.4.7 内嵌。
- 依赖：`lua_translator`、`luaL_openlibs`、`Candidate`、`schema.config`、`context:get_option`；这些在本机已实测。
- 理论兼容其他带 librime-lua 的 Rime 前端，但需确认：
  - `lua_translator@*模块` 语法；
  - `schema.config:get_double`；
  - `seg._end` 字段；
  - 候选 `quality` 排序。
- 不依赖任何外部 Python/Node 运行时；构建期工具除外。
