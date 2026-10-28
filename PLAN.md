# 魔光键影 · 总体方案与执行计划

> 目标平台：小狼毫 Weasel 0.17.4（Windows x64，librime 1.13.1，内嵌 Lua 5.4.7）
> 数据源：本仓库 `data/dict.txt`（1212 条《最终幻想7》相关词条/短句，UTF-16 LE BOM + CRLF）
> 方案 ID：`ff7-ime`；显示名：**魔光键影**
>
> **2026-10-29 修订**：分发方式改为“整仓适配 Plum”：根目录 `ff7-ime.schema.yaml` +
> `lua/ff7-ime*.lua` + `recipe.yaml`；用户在小狼毫“获取更多输入方案”中输入
> `Tanimodori/ff7-ime`。不再生成 portable zip，不再提供 install/uninstall/verify/deploy
> 脚本；`dict.txt` 移到 `data/dict.txt`；代码采用 MIT。下文提到 portable/安装脚本的
> 历史段落仅作为当时的执行记录，已被本节取代。

---

## 1. 目标与非目标

### 1.1 目标

1. 只输出 `data/dict.txt` 中的 1212 条词条，每条作为一个完整候选，不造句、不联想用户词、不输出词库外内容。
2. 用户输入中国大陆普通话**无调全拼**；候选文本保留词条中的中文标点（`！，·……？、`）。
3. 支持四类容错：
   - **A 模糊音**：`zh/ch/sh → z/c/s`、`ng → n`，并预留 `n/l`、`r/l`、`f/h`、`en/eng`、`in/ing`、`an/ang` 等可配置模糊。
   - **B 多音字与允许误读**：词条内多音字全部读音可匹配；“有边读边”等常见误读可匹配，但权重低于规范读音。
   - **C 部分输入 / 声母 / 关键词**：全声母（如 `wmhlkcdccnm`）、声母子序列（如 `lkcc` 命中“我们会立刻彻底铲除你们”）、前缀/不完整音节。
   - **D 漏输、错输、顺序错**：漏字母、多字母、相邻换位、音节换位（如 `lienuo`、`leino`、`leiknuo` → 雷诺）。
4. **永远输出 N 个候选**（默认 N=9，可配置），任何输入（包括乱码）都不空输出。
5. 精确全拼必须稳定排第一；短词与长句之间有良好区分度。
6. 候选数量、权重、阈值、各模糊音开关均可通过 YAML 配置修改。
7. 交付可安装的 Plum 包（整仓克隆 + `recipe.yaml`），并部署到本机小狼毫；提供完整 README / DOCS 与 MIT 许可。

### 1.2 非目标

- 不做整句输入、云输入、用户自造词、简繁转换、英文/数字输入法。
- 不修改或替换用户现有的 `luna_pinyin_simp` 方案；只新增方案并加入方案列表。
- 不依赖外部服务、网络、Python 运行时（Python 仅用于构建期）。
- 不保证对 `data/dict.txt` 之外词条的输入效果；词库外输入只做 n-gram + Damerau/Dice-LCS 回退。

---

## 2. 关键结论与架构选择

### 2.1 为什么不用 Rime 原生 `script_translator` + 模糊 algebra

Rime 原生方案可以处理全拼、简拼和部分模糊音，但：

- `speller/algebra` 是**编译期**规则，运行时切换模糊音需要多套 schema 或重新部署；
- 原生引擎没有“声母子序列/关键词模式”（`lkcc` → 长句）；
- 原生引擎没有通用编辑距离/音节换位容错；
- 原生词典会引入词库外候选、造句、用户词频，违背“只输出 1212 条”。

因此采用 **Rime + 嵌入式 Lua translator**：由 Lua 全量载入 1212 条索引，在每次按键时执行自定义匹配与排序，只 `yield` 我们的候选。

### 2.2 总体数据流

```
键盘按键
  → Rime speller（收集纯字母输入）
  → segmentor（保证整段字母进入同一 segment）
  → lua_translator@*ff7-ime（读取 raw input）
      → 规范化（小写、去分隔符、v/ü）
      → 多通道匹配 + 打分（全拼/模糊/多音/误读/声母/关键词/前缀/编辑距离/音节换位）
      → Top-N 排序（精确优先、长度归一、稳定 tie-break）
      → yield N 个 Candidate（text=原始词条，comment=拼音/通道/分数）
  → Rime menu（候选窗口，默认每页 9）
  → 用户选择 / 空格提交
```

### 2.3 文件与组件

| 层 | 文件 | 职责 |
|---|---|---|
| Rime 方案 | `ff7-ime.schema.yaml` | schema 元信息、switches、engine 组件、speller、Lua translator 引用 |
| 用户覆盖 | `ff7-ime.custom.yaml` | 模糊开关、Top-N、权重、分页等用户配置 |
| Lua 引擎 | `lua/ff7-ime.lua` | translator 入口、输入规范化、匹配调度、候选生成 |
| Lua 算法 | `lua/ff7-ime_matcher.lua` | 音节对齐 DP、编辑距离、子序列、打分 |
| Lua 数据 | `lua/ff7-ime_data.lua` | 构建期生成的 1212 条词条、读音、权重 |
| 构建脚本 | `tools/build_from_pinyin_data.py`、`tools/check_package.py` | data/dict.txt + 拼音数据 → Lua 数据 / 包布局校验 |
| 测试 | `experiments/rime-harness/rime_harness.py`、`tests/` | Rime C API 自动化回归；算法单元测试 |
| 文档 | `README.md`、`docs/*.md` | 安装、使用、算法、架构、构建、维护 |
| 发布 | `recipe.yaml` + `Tanimodori/ff7-ime` | 整仓 Plum 包：用户输入仓库标识安装 |

---

## 3. 核心算法（设计基线，详见 docs/ALGORITHM.md）

### 3.1 词条表示

每条词条预计算：

- `text`：原始文本（含标点）；
- `syllables[i]`：第 i 个汉字的**主读音**（无调、`ü→v`）；
- `readings[i]`：该字所有允许读音（规范多音字 + 允许误读），带权重；
- `initials`：主读音声母序列（`zh/ch/sh` 视为一个声母 token）；
- `full`：主读音拼接串；
- `n`：汉字数；`weight`：词条权重（默认 1.0，可配置）。

### 3.2 输入规范化

1. 转小写；
2. `ü → v`；`j/q/x/y + u` 保留标准拼写，同时生成 `v` 变体；
3. 去除非 `[a-z]` 字符（分隔符 `'`、空格、数字等）；
4. 记录原始串用于调试/注释。

### 3.3 多通道匹配

对每个词条计算以下通道得分，取加权融合：

1. **全拼精确**：`input == full` → 1.0（最高优先级）。
2. **全拼前缀/部分输入**：`full` 以 `input` 开头 → 按覆盖比例给高分；短词优先。
3. **字母级近似全拼**：加权 Damerau-Levenshtein（替换/插入/删除/相邻换位），处理漏、多、错、相邻换位。
4. **音节级对齐 DP**：输入切块与候选音节序列对齐，允许：
   - 整音节精确/模糊/近似匹配；
   - 音节前缀（部分输入）；
   - 跳过候选音节（漏输）；
   - 多余输入块（多输）；
   - 相邻音节交换（顺序错）。
5. **声母精确/前缀/子序列**：
   - 全声母：`input == initials`；
   - 声母前缀：`initials` 以 `input` 开头；
   - 声母子序列：`input` 是 `initials` 的子序列（`lkcc` 命中长句），带覆盖率、紧凑度、起始偏移惩罚。
6. **音节前缀子序列（关键词模式）**：输入块可匹配任意音节的前缀并跳过中间音节，覆盖部分输入与关键词。
7. **多音/误读通道**：对每个字尝试备选读音，规范读音权重最高，误读按来源打折。

### 3.4 打分融合（基线）

```
score = w_exact   * exact_full
      + w_prefix  * prefix_quality
      + w_syl     * syllable_alignment_quality
      + w_initial * initial_subsequence_quality
      + w_keyword * keyword_subsequence_quality
      - penalty_fuzzy
      - penalty_misread
      - penalty_typo
      - penalty_skip
      + prior_weight
```

- 所有通道得分归一到 `[0,1]`；精确全拼固定为最高档。
- `syllable_coverage`、`compactness`、`prefix_quality` 用于区分短词/长句，防止长句靠“字多”压过短词。
- 同分 tie-break：精确通道 > 规范读音 > 短词 > 更紧凑 > 词典顺序。
- 无任何通道命中时，用双/三字母 n-gram 召回 + Damerau/Dice-LCS 做最近邻回退，保证 N 个候选；DP 低于置信度门槛时不作为强候选。

### 3.5 性能预算

- 1212 条词条 × 平均 4.6 字，单次全量扫描 + DP 应在 **< 30 ms**（Lua 5.4，目标 < 15 ms）。
- 优化：精确/前缀/声母快速路径；首字母倒排索引；DP 只对候选子集运行；输入结果缓存。
- 若超预算，退化为“快速通道 + 只对前 K 个候选跑完整 DP”的两阶段策略。

---

## 4. 拼音数据管线

1. 解析 `data/dict.txt`（UTF-16 LE BOM、CRLF），得到 1212 条、1326 个唯一汉字、最长 14 字。
2. 注音来源：
   - `pypinyin`（主，`heteronym=True` 取多音）；
   - `luna_pinyin.dict.yaml`（交叉校验/补充）；
   - 人工覆盖表（FF7 译名、生僻字、有边读边误读）。
3. 产出：
   - `data/phrases.tsv`：词条、主读音、逐字读音、备选读音、备注；
   - `data/chars.tsv`：汉字、规范读音、多音、来源；
   - `data/overrides.yaml`：人工覆盖；
   - `lua/ff7-ime_data.lua`：构建期生成，嵌入 Lua。
4. 验收：1212/1212 覆盖；生僻字缺失 0；抽查 ≥ 100 条读音；多音/误读结构化。

---

## 5. Rime 集成与配置

### 5.1 Engine 组件（基线）

```yaml
engine:
  processors:
    - ascii_composer
    - recognizer
    - key_binder
    - speller
    - punctuator
    - selector
    - navigator
    - express_editor
  segmentors:
    - ascii_segmentor
    - matcher
    - abc_segmentor
    - punct_segmentor
    - fallback_segmentor
  translators:
    - punct_translator
    - lua_translator@ff7-ime
  filters:
    - uniquifier
```

- 不加载 `script_translator`、`simplifier`、用户词典、造句组件。
- 用 `lua_segmentor`/`matcher` 保证 `lkcc` 等任意字母串作为**一个** segment 进入 Lua（待探针确认最佳方式）。

### 5.2 配置项（基线）

```yaml
ff7-ime:
  top_n: 9
  page_size: 9
  debug: false
  weights: { exact: 1.0, prefix: 0.86, syllable: 0.82, initial: 0.78, keyword: 0.72 }
  fuzzy:
    zh_z: true
    ch_c: true
    sh_s: true
    ng_n: true
    n_l: false
    r_l: false
    f_h: false
    en_eng: false
    in_ing: false
    an_ang: false
  misread: true
  typo:
    max_edit: 2
    transposition: true
    syllable_swap: true
```

用户通过 `ff7-ime.custom.yaml` 覆盖，例如：

```yaml
patch:
  ff7-ime/top_n: 12
  ff7-ime/fuzzy/n_l: true
  ff7-ime/fuzzy/zh_z: false
```

### 5.3 部署

- 用户目录：`%APPDATA%\Rime\`
- 通过小狼毫“方案选单设定 → 获取更多输入方案”输入 `Tanimodori/ff7-ime`；
  Plum 按根 `recipe.yaml` 只复制 schema + `lua/ff7-ime*.lua` 4 个文件。
- 安装器不改 `default.custom.yaml`；用户在方案选单勾选“魔光键影”后由 Weasel 写入
  `schema_list`，随后重新部署。
- 不覆盖 `luna_pinyin_simp`；卸载时在方案选单取消勾选并删除本方案文件。
- 不再生成 portable zip；仓库本身就是可分发的 Plum 包。

---

## 6. 测试与验收

### 6.1 测试层次

1. **算法单元测试（Python 原型）**：核心用例、参数敏感性、消融。
2. **Lua 引擎单元测试**：在独立 Lua 环境或 Rime 中跑同一测试集。
3. **Rime C API 集成测试**：`rime.dll` + 临时 user dir，逐键输入，读候选/commit，验证 Top-N。
4. **GUI 验收**：小狼毫实际输入到记事本，截图验证候选窗口、翻页、提交。
5. **回归/边界**：空输入、乱码、超长输入、标点、大小写、Caps Lock、删除键、翻页、空格提交、数字选择。

### 6.2 核心验收用例（必须通过）

| 类别 | 输入 | 期望 |
|---|---|---|
| 精确全拼 | `shenluo` | 神罗 top1 |
| 精确全拼 | `leinuo` | 雷诺 top1 |
| 模糊 zh/z | `senluo` | 神罗 top1 |
| 模糊 ch/c | `cang` 类 | 对应词条 top1（按词库） |
| 模糊 sh/s | `shenluo` / `senluo` | 神罗 |
| 模糊 ng/n | `shenluo` / `shenluon`? | 按实际音节 |
| 多音字 | 词条内含“重/长/行/乐/曾”等 | 规范读音 top1 |
| 误读 | 岑→qin（若词条含） | 对应词条进 topN |
| 全声母 | `wmhlkcdccnm` | 我们会立刻彻底铲除你们 top1 |
| 关键词 | `lkcc` | 我们会立刻彻底铲除你们 top1 |
| 部分输入 | `shenl` | 神罗类短词优先 |
| 漏字母 | `leino` | 雷诺 top1 |
| 换位 | `lienuo` | 雷诺 top1 |
| 多字母 | `leiknuo` | 雷诺 top1 |
| 音节换位 | `nuolei` | 雷诺 top1 |
| 乱码 | `zzzzzz` | 仍有 N 个候选 |
| 空/单字母 | `a` | 仍有 N 个候选 |
| 标点词条 | 对应拼音 | 输出含原标点 |
| 短词 vs 长句 | 精确短词输入 | 短词 top1，长句不压过 |

### 6.3 独立子代理验收门

| 阶段 | 验收内容 | 验收方式 |
|---|---|---|
| G0 环境 | Lua/Rime API/数据源可用性 | 独立代理复现探针，核对证据 |
| G1 数据 | 1212 条注音完整、读音正确、误读结构化 | 独立代理抽查 + 脚本校验 |
| G2 算法 | 核心用例 top1、Top-N、无空输出 | 独立代理用隐藏用例跑原型 |
| G3 引擎 | Lua 实现与原型一致、性能达标、Rime 中可运行 | 独立代理代码审查 + 集成测试 |
| G4 部署 | 真实小狼毫通过官方 Plum 安装/切换/输入/卸载；不影响现有方案 | 独立代理按文档从零安装验证 |
| G5 交付 | 整仓 Plum 包可由官方入口安装、包校验通过、文档完整可复现 | 独立代理在临时目录模拟全新安装 |

每个门禁不通过则回到对应阶段修复，重新验收；验收报告写入 `docs/acceptance/`。

---

## 7. 执行顺序

1. **G0 侦察**（进行中）：Lua 运行时、拼音数据、算法、Rime 部署、C API 夹具五路并行调查。
2. **G1 数据**：生成 `phrases.tsv` / `chars.tsv` / `overrides.yaml`，人工抽查，子代理验收。
3. **G2 算法**：Python 原型 + 测试集 + 参数调优，子代理验收。
4. **G3 引擎**：Lua 移植、Rime schema、配置、集成测试，子代理验收。
5. **G4 部署**：本机安装、GUI 实测、与现有方案共存验证，子代理验收。
6. **G5 交付**：整仓 Plum 包（`recipe.yaml` + schema + lua）、MIT、README/DOCS、包校验、最终验收。

---

## 8. 主要风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Lua translator 拿不到完整 `lkcc`（被拆段） | 关键词模式失效 | 用 `lua_segmentor`/`matcher` 强制整段；G0 探针先验证 |
| Lua 配置/开关 API 不存在 | 无法运行时配置 | 构建期生成多套数据/配置；或读 `schema.config`；G0 确认 |
| 1212 条全量 DP 每键过慢 | 输入卡顿 | 快速路径 + 首字母倒排 + 两阶段；基准测试 |
| 生僻字/多音字读音错误 | 候选不准 | 多源交叉 + 人工覆盖 + 抽查；误读集合兜底 |
| 长句关键词过度匹配 | 短词被长句压过 | 覆盖率/紧凑度/长度归一 + 精确优先 |
| 部署破坏现有方案 | 用户输入法异常 | 安装器只复制 4 个运行时文件、不改 default.custom.yaml；方案启用交给官方选单；独立验收 |
| Rime 版本差异 | 方案不可用 | 固定目标 0.17.4；文档注明兼容范围；G4 真机验证 |

---

## 9. 交付清单

- [x] 整仓 Plum 包：`recipe.yaml` + `ff7-ime.schema.yaml` + `lua/ff7-ime*.lua`（用户输入 `Tanimodori/ff7-ime` 安装）
- [x] MIT `LICENSE`（Copyright (c) 2026 Tanimodori）
- [x] 本机 `%APPDATA%\Rime` 已安装并部署，方案列表可见
- [x] `README.md`
- [x] `docs/ALGORITHM.md`
- [x] `docs/ARCHITECTURE.md`
- [x] `docs/INSTALL.md`
- [x] `docs/USAGE.md`
- [x] `docs/BUILD.md`
- [x] `docs/MAINTENANCE.md`
- [x] `docs/TEST_REPORT.md`
- [~] 独立子代理验收 G0..G5：按用户指示跳过（G1–G3 子代理因 ClinePass 周限额失败；改由实现者自动化测试 + 真机 GUI 实测覆盖，见 `docs/TEST_REPORT.md`）
- [x] 测试脚本与测试集（可复现）
- [x] 内嵌预编辑（预测音节分隔符，`diou` → `di'ou`）与回车/小键盘回车上屏
- [x] 构建脚本（data/dict.txt + 拼音数据 → Lua 数据 / 包）

### 实施结果摘要

- 方案已部署到本机 `%APPDATA%\Rime`，`luna_pinyin_simp` 与 `ff7-ime` 共存；
- 真实 Rime + GUI 实测通过（`lkcc`、`lienuo`、`senluo`、`zanguokuaigon`、`ren sheng...`）；
- 全量自动评估：exact 1212/1212、fuzzy 878/878、initial 1212/1212（top1 98.3%）、typo 600/600（top3）、keyword 233/238（top5）、mid_keyword 300/300、fallback 7/7；
- 内嵌预编辑：`diou` → `di'ou`、`meishao` → `mei'shao`；回车/小键盘回车提交高亮候选（GUI 实测）；
- 关键架构调整：
  1. 使用 `lua_translator@*ff7-ime` + 纯 Lua 匹配引擎，而不是 Rime 原生 `script_translator`；
  2. 连续串 canon 只做安全规则（zh/ch/sh、v/u），`ng→n` 放音节级 DP，避免跨音节误伤；
  3. 两阶段召回（廉价通道 + canonical 双/三字母重叠 Top-K DP），兼顾准确率与逐键延迟；
  4. 回退改为 bigram/trigram 召回 + Damerau/Dice-LCS 排序，并给 DP 加 0.65 置信度门槛；有强命中时只用 16 个小池，避免拖慢正常按键；
  5. 安装改为官方 Plum：整仓浅克隆 + 根 `recipe.yaml` 只复制 4 个运行时文件；安装器不改 `default.custom.yaml`。
- 已知限制：极稀疏关键词子序列存在天然歧义；整仓克隆需要公开仓库 + Git Bash；本地 ZIP 不复制 `lua/`；词库外输入只回退不造句。

---

## 10. 版本与兼容

- 方案版本：`1.0.0`
- 目标：Weasel 0.17.4 / librime 1.13.1 / Windows 10 19045 x64
- 理论兼容：Weasel 0.17.x（Lua 5.4）；其他 Rime 前端需确认 `lua_translator` 与中文路径支持。
- 数据版本：以 `data/dict.txt` 的 1212 条为准；更新词库后重新运行构建脚本并部署。
