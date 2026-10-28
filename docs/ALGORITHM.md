# 算法设计

> 本文描述 `lua/ff7-ime_matcher.lua` 的实际算法，不是概念草案。所有公式、权重、阈值均与 1.0.0 代码一致。

---

## 1. 问题定义

给定：

- 固定词库 \(D=\{p_1,\dots,p_{1212}\}\)，每条 \(p_i\) 是含标点的中文词条；
- 每条词条的汉字读音序列（主读音 + 允许的备选读音）；
- 用户输入 \(q\)：无调全拼字母串（可能含分隔符、大小写、错漏多字、音节换位、缩写）。

要求：

1. 只输出 \(D\) 中的词条，每条作为完整候选；
2. 对任意 \(q\) 返回恰好 \(N\) 个候选（默认 9），不空输出；
3. 精确全拼稳定 top1；
4. 支持模糊音、多音/误读、前缀、全声母、关键词子序列、漏/多/错/换位；
5. 短词与长句有区分度，长句不能仅靠“字多”压过短词；
6. 逐键延迟可接受（目标单键 <50 ms，最坏 <100 ms）。

---

## 2. 词条表示

对每条词条预计算：

| 字段 | 含义 |
|---|---|
| `text` | 原始词条，含标点，提交时原样输出 |
| `syls[j]` | 第 j 个汉字的主读音（无调，`ü→v`） |
| `alts[j]` | 第 j 个字的备选读音列表 `{s, w}`，主读音不在其中 |
| `readings[j]` | `{主读音 w=1.0} ∪ alts[j]`，DP 用 |
| `fulls` | 主读音/备选读音组合出的全拼变体 `{s, w}`，最多 8 个 |
| `canon_full` | 主读音逐音节模糊规范化后的全拼 |
| `init_variants` | 声母 token 序列变体 `{tokens, w}` |
| `swaps` | 相邻音节交换后的全拼（`nuolei` ← 雷诺） |
| `n` | 汉字数 |
| `w` | 词条权重（默认 1.0，可配置 boost） |
| `order` | 词典顺序，稳定 tie-break |

### 2.1 备选读音的来源

只用两类，避免把 pypinyin 的全部生僻异读塞进来：

1. **语料内上下文读音**（权重 0.97）：同一个字在 1212 条词条中作为主读音出现过的所有音节。
   - 例：“长”在“长杖/长靴/长矛/长石”读 `chang`，在“市长/村长/部长/成长”读 `zhang`，两者都进入备选；
   - 例：“重” `zhong` / `chong`，“行” `xing` / `hang`，“得” `de` / `dei`，“地” `di` / `de`，“了” `le` / `liao`。
2. **允许误读**（权重 0.90）：`experiments/pinyin-data/override.yaml` 的 `misread_candidates`，再加少量补充（如“骰” `shai`、“乐” `yue`）。
   - 例：“梣” `cen`（规范）/ `qin`、`chen`（有边读边）；“曾” `zeng` / `ceng`；“血” `xue` / `xie`。

权重在 DP 中按 `alt.w` 缩放；在 `fulls` 变体中按替换字权重乘积缩放。主读音永远优先。

---

## 3. 输入规范化

```lua
q = lower(input)
q = q:gsub("[^a-z]", "")   -- 去掉分隔符、数字、空格、标点
```

- `ü` 在数据中写作 `v`；输入 `v` 与 `u` 通过 `v_u` 模糊规则视为互通（默认开）。
- 输入中的 `'` 用于分隔音节，但规范化时去掉；`abc_segmentor` 会把整段字母（含 `'`）作为一个 segment 交给 Lua。
- 空输入（无字母）走静态 Top-N，不进入匹配。

---

## 4. 模糊音：两级规范化

### 4.1 音节级规范化 `canon_syllable`

只对单个音节应用，规则可配置：

| 规则 | 默认 | 作用 |
|---|---|---|
| `zh_z` | 开 | `zh...` → `z...` |
| `ch_c` | 开 | `ch...` → `c...` |
| `sh_s` | 开 | `sh...` → `s...` |
| `ng_n` | 开 | `...ng` → `...n` |
| `n_l` | 关 | 音节首 `n` → `l` |
| `r_l` | 关 | 音节首 `r` → `l` |
| `f_h` | 关 | 音节首 `f` → `h` |
| `en_eng` | 关 | `eng` → `en` |
| `in_ing` | 关 | `ing` → `in` |
| `an_ang` | 关 | `ang` → `an` |
| `uan_uang` | 关 | `uang` → `uan` |
| `v_u` | 开 | `v` → `u` |

### 4.2 连续串规范化 `canon_input`：只做安全规则

精确/前缀/换位通道需要比较连续字符串，但 **不能** 对连续串全局应用 `ng→n`：它会跨音节边界误伤。

反例（真实 bug）：

```
输入 senguilon（sheng gui long 的模糊串）
全局 gsub("ng","n") → senuilon   -- 把 "sen"+"gui" 边界的 n+g 也替换了
数据 canon         → senguilon
```

因此 `canon_input` 只应用 **不会跨音节误伤** 的规则：

- `zh/ch/sh → z/c/s`：拼音音节不会以 z/c/s 结尾，安全；
- `v → u`：安全。

`ng→n`、`n/l`、`r/l`、`f/h` 等只在 **音节级** `syllable_match` / DP 中应用。这样：

- `senluo` 与 `shenluo` 仍可通过 `sh→s` 在连续串通道命中；
- `senguilon`、`zanguokuaigon` 这类 `ng→n` 输入由音节 DP 正确对齐，不会因全局替换错位。

---

## 5. 多通道匹配

对每个词条分别计算通道得分，最后按通道权重取最优。所有通道得分归一到 `[0,1]`。

### 5.1 精确全拼

若 `q == full`（`fulls` 中任一变体，含多音/误读变体）：

```
raw = variant_weight          -- 主读音 1.0，变体 0.97/0.90/...
channel = "exact"
```

精确全拼权重 1.0，是唯一能达到 1.0 的通道；任何近似通道都严格低于它。

### 5.2 全拼前缀

若 `full` 以 `q` 开头且 `#q < #full`：

```
raw = (0.90 + 0.09 * #q/#full) * variant_weight
channel = "prefix"
```

前缀越长、覆盖率越高，得分越高；短词因 `#full` 小通常比长句得分高，避免长句压过短词。

### 5.3 模糊全拼 / 模糊前缀

`qcanon = canon_input(q)`，与 `p.canons`（安全规则规范化后的全拼变体）比较：

```
相等:     raw = 0.965 * variant_weight
前缀:     raw = (0.88 + 0.08 * #qcanon/#canon_full) * variant_weight
```

`ng→n` 等更强模糊不在此通道，交给 DP；因此模糊全拼通道不会出现跨音节误伤。

### 5.4 相邻音节换位

数据预计算 `swaps`：交换相邻两个音节后的全拼。

```
若 q == swap: raw = 0.93 * swap_weight
channel = "swap"
```

例：`nuolei` = 雷诺的 `lei`/`nuo` 交换。

### 5.5 音节级对齐 DP（核心容错）

对输入 \(q\) 和词条音节序列 \(S[1..n]\) 做带权对齐。

#### 5.5.1 状态

`dp[i][j]`：消耗前 \(i\) 个输入字母、前 \(j\) 个音节后的最高分。实现用扁平数组 `dp[i*W + j + 1]`，`W=n+1`。

#### 5.5.2 转移

1. **跳过音节**（漏输）：
   `dp[i][j+1] = max(dp[i][j+1], dp[i][j] - 0.12)`
2. **多输一个字母**：
   `dp[i+1][j] = max(dp[i+1][j], dp[i][j] - 0.20)`
3. **匹配音节**：对第 \(j+1\) 个音节的每个读音 \(r\)（主读音/备选），取输入块 `q[i+1 .. i+k]`，\(k\) 从 1 到 `#r + max_edit`：
   - `syllable_match(chunk, r)` 返回匹配分与惩罚；
   - 转移：
     ```
     v = dp[i][j] + match.score * r.w - match.penalty - (alt ? 0.02 : 0)
     dp[i+k][j+1] = max(..., v)
     ```
4. **结束**：在 `i==L` 时减去尾部未匹配音节惩罚：
   `final = dp[L][j] - 0.04 * (n-j)`；取最大，再除以 `n` 归一到 `[0,1]`。

#### 5.5.3 `syllable_match`

| 情况 | 得分 | 惩罚 |
|---|---|---|
| `chunk == reading` | 1.00 | 0 |
| `chunk` 是 `reading` 前缀 | `0.55 + 0.40*(#chunk/#reading)` | 0 |
| 音节级 canon 相等（模糊） | 0.96 | 0.02 |
| canon 前缀 | `0.55 + 0.40*(#cc/#cr)` | 0.02 |
| Damerau 距离 \(d≤max\_edit\) | `0.95 - 0.15*d` | `0.05*d` |

- Damerau-Levenshtein（相邻换位算 1 次）用于 `lie` vs `lei`、`no` vs `nuo`、`ano` vs `nao` 等；
- 每个查询共享 `cache[chunk.."\0"..reading]`，避免跨词条重复计算；
- `max_edit` 默认 2，可配置 0–4；`transposition` 可关。

#### 5.5.4 严格模式

当 `ff7-ime/typo/enabled: false` 时，DP 进入 strict 模式：

- 只接受整音节精确或音节级模糊相等；
- 不允许前缀、漏字、多字、编辑距离、换位；
- 因此 `lienuo` 不再命中雷诺，但 `senguilon`（纯 ng→n 模糊）仍可命中圣柜龙。

### 5.6 全声母

`init_variants` 是声母 token 序列，如：

```
我们会立刻彻底铲除你们！ → w m h l k c d c c n m
```

- 若输入去掉分隔符后 **精确等于** 原始声母串：`raw = 1.0`，通道 `initial_exact`；
- 若仅在 canon 后相等（如 `chm` vs `cm`）：走关键词评分，通道 `initial`；
- 输入长度明显长于全拼时不尝试声母通道（不可能只是声母）。

### 5.7 关键词子序列

输入 `q` 与声母 token 序列 `T[1..m]`：

- 对每个起始位置 `start`，贪心找 `q` 在 `T` 中的最早子序列出现；
- 若全部匹配，计算：

```
phrase_cov  = #q / m
span        = last - start + 1
compactness = #q / span
start_pen   = (start - 1) / m
gap         = span - #q

raw = 0.45
    + 0.25 * phrase_cov
    + 0.20 * compactness
    + 0.10 * (1 - start_pen)
    - 0.02 * gap
```

- 取所有 start 的最大值；
- 例 `lkcc` vs 11 个声母：`phrase_cov=4/11`、`span=6`、`compactness=4/6`，raw ≈ 0.707；
- 短词的精确声母（`initial_exact`）权重 0.96，高于关键词通道，因此“短词精确缩写”不会被长句关键词压过；
- `initial_mode` 下关键词权重提升到 0.90。

### 5.8 音节前缀子序列（中段关键词）

声母子序列只能匹配“每个音节的首字母”；`meishao` 这类带完整韵母的
缩写需要另一条通道。典型例子：

```
有时是出手相助的美少女忍者！
youshishichushouxiangzhudemeishaonvrenzhe
                        ^^^^^^^
meishao 从第 27 个字母开始，既不是全拼前缀，也不是声母子序列
```

`meishao` 可以切成 `mei` + `shao`，分别是第 9、10 个音节的前缀。因此新增：

- **召回索引 `by_syl_prefix`**：对每个音节的每个读音（含备选读音），
  索引原始前缀和音节级模糊规范化前缀（长度 1–3）→ 词条 id；
- **召回**：用输入首块的 3/2 字母键查询；若首字母是 `a/e/o`（单字母音节）
  或 2/3 字母键没有召回，再补 1 字母键（如 `aan` → `a` + `an`）；
- **校验 DP**：对每条召回词条，枚举起始音节 `start`，把输入切成若干块，
  每块必须是某个音节读音的前缀；允许跳过中间音节，但不做编辑距离。
  状态记录 `(消耗字母数, 音节数)` 的块质量、块数、是否含 ≥2 字母块。

评分（`L` 为输入长度，`span` 为命中音节跨度，`chunks` 为块数）：

```
chunk_quality = Σ(块长 / 音节长) / chunks
compactness   = chunks / span
phrase_cov    = L / #primary_full
start_pen     = (start - 1) / n
gap           = span - chunks

raw = 0.50
    + 0.25 * chunk_quality
    + 0.15 * compactness
    + 0.10 * (1 - start_pen)
    + 0.05 * phrase_cov
    - 0.02 * gap
```

示例（默认权重 `keyword=0.80`）：

| 输入 | 命中块 | raw | 加权 |
|---|---|---:|---:|
| `meishao` | mei + shao | 0.947 | 0.758 |
| `chushou` | chu + shou | 0.985 | 0.788 |
| `shouxiang` | shou + xiang | 0.980 | 0.784 |
| `zhiwen` | zhi + wen | 0.975 | 0.780 |

集成规则：

- 该通道放在 **阶段 3**，在 DP 之后运行，不参与 `best_cheap_raw` /
  `best_raw` 的门槛判断，避免“高 raw、低权重”的关键词结果阻断 DP；
- 独立于 DP 短名单召回，因此目标即使不在 Top-56 也能被评分；
- `initial_mode` 下跳过（声母子序列已覆盖纯缩写）；
- `best_cheap_raw >= 0.99`（已有精确全拼）时跳过；
- 通道名仍为 `keyword`，`detail = "syllable"`，权重沿用 `keyword`；
- 用 `ff7-ime/keyword/syllable_subsequence: false` 可关闭。

前缀优先仍然成立：`zhiwen` 的 `少女之吻` 加权 0.780，但
`直纹叶翼蜥` 的全拼前缀得分 0.907，仍排第一。

### 5.9 置信度门槛与最近邻回退

DP 是近似对齐，必须防止它在垃圾串上“硬凑”出低分候选。`dp_score` 的
归一化分数低于 `ff7-ime/fallback/dp_min_raw`（默认 0.65）时，该 DP 结果
不进入强通道；例如 `asdfghjkl` 对若干四音节词的 raw 约 0.55，会被丢弃，
而不是返回 9 个看似匹配的随机词。

回退不再按 `static_top` 的固定顺序取前 N 个，而是：

1. **候选池**：用 `by_canon_bigram` / `by_canon_trigram` 召回与输入共享
   双/三字母的词条，再并上 `by_first[首字母]`（含规范化首字母）。
2. **重叠度预排序**：

   ```
   overlap = 2 * bigram_hits + 4 * trigram_hits
           + 2 * (首字母匹配) + 2 * (末字母匹配)
           - 0.10 * |#q - #full|
   ```

   已有强命中（非回退结果 raw ≥ `strong_raw`，默认 0.70）时只取前
   `fast_max_candidates`（默认 16）个，避免拖慢正常按键；没有强命中时
   取前 `max_candidates`（默认 96）个。
3. **相似度**：对短名单计算

   ```
   Damerau:  sim = 1 - Damerau(q, full)/max(#q,#full)
             声母串再乘 0.88
   Dice-LCS: sim = 2*LCS(q, full)/(#q+#full)
             - 0.05 * |#q-#full|/max(#q,#full)
   取两者最大
   ```

   LCS 必须用 Dice 归一化；原始 LCS 长度会系统性偏向长句。
4. **权重**：回退通道权重 0.55，低于所有强通道。
5. **静态兜底**：只有候选池为空或仍不足 N 时，才从 `static_top` 补足。

例：`zzzzzz` 回退到共享 `z` 的词条（`刺针蜘蛛` 等），`qwxz` 回退到
`青蛙戒指` 等；`fangge` 的 exact 结果之后，补位候选也来自同首字母/
共享片段的短名单，而不是固定的静态前 9 条。

### 5.10 预编辑音节切分（仅显示）

`M.preview(input, phrases, opts, hint)` 只生成 `Candidate.preedit`，不参与打分：

1. 若首个候选的完整读音恰好等于输入（`diou` → 迪欧 `di`+`ou`），直接采用其音节边界；
2. 否则用数据中所有读音的原始/规范化形式建立音节集合与前缀集合，对输入做 DP：
   - 覆盖全部字符；音节数越少越好；同分时优先更长的音节；
   - 允许一个未完成的尾音节，只要它是合法音节的前缀（`shenl` → `shen'l`）；
   - 无法切分时原样返回（`lkcc` → `lkcc`）；
3. 用 `ff7-ime/preedit/separator`（默认 `'`）连接。

显示层写入 `cand.preedit`；Rime 的 composition preedit 使用该字段，Weasel 在 `style/inline_preedit: true` 时把它画进输入框。commit 文本仍是候选的 `text`，不受影响。

---

## 6. 候选召回与 DP 截断

全量 1212 条逐键扫描 + 对每条跑 DP 会超时。实际采用三个阶段，之后是
n-gram + Damerau/Dice-LCS 回退：

### 6.1 索引

`build_index` 建立：

| 索引 | 内容 |
|---|---|
| `by_first` | 每个全拼变体/换位变体的首字母 → 词条 id |
| `by_init_letter` | 每个声母 token 的首字母 → 词条 id |
| `by_full` | 全拼变体 → 词条 id |
| `by_canon` | 安全 canon 全拼 → 词条 id |
| `by_bigram` / `by_trigram` | 原始全拼的双/三字母 → 词条 id |
| `by_canon_bigram` / `by_canon_trigram` | **逐音节模糊规范化**全拼的双/三字母 → 词条 id |
| `by_syl_prefix` | 每个音节读音的 1–3 字母前缀（原始 + 规范化）→ 词条 id |
| `static_top` | 按权重/长度/词典序的静态优先序 |

canonical 双/三字母索引是关键：`ng→n` 后 `zonli` 与 `重力` 的 `zongli` 才能共享 `on`/`nl`/`li` 等片段，使正确候选进入 DP 短名单。

### 6.2 阶段 1：廉价通道

候选集：

- 普通输入：`by_first[首字母]`；
- `initial_mode`：输入每个字母的 `by_init_letter` 并集 + `by_first[首字母]`。

对候选跑 **不启用 DP** 的 `score_phrase`（精确/前缀/模糊/声母/换位），记录 `best_cheap_raw`。

### 6.3 阶段 2：DP 短名单

仅当：

- 非 `initial_mode`；
- `best_cheap_raw < 0.93`；
- `#q >= 2`

才跑 DP。候选集为阶段 1 候选 ∪ 输入双/三字母命中的词条；按重叠度排序：

```
overlap = 2 * bigram_hits + 4 * trigram_hits
        + 2 * (首字母匹配) + 2 * (末字母匹配)
        - 0.1 * |#q - #full|
```

只对前 `dp_max_candidates`（默认 56）跑完整 `score_phrase`（含 DP）。

- 精确/前缀/模糊/声母/换位已够强时完全跳过 DP，长句逐键约 5–10 ms；
- 纯声母/关键词输入跳过 DP，避免 DP 误抢关键词；
- DP 短名单既控制延迟，又通过 canonical 重叠度确保正确候选不被截掉；
- DP 的归一化 raw 低于 `ff7-ime/fallback/dp_min_raw`（默认 0.65）时丢弃，
  避免垃圾串被强行对齐成随机词。

### 6.4 阶段 3：中段关键词召回

仅当：

- `ff7-ime/keyword/syllable_subsequence` 未关闭；
- 非 `initial_mode`；
- `#q >= 2`；
- `best_cheap_raw < 0.99`（没有精确全拼命中）

时运行。候选集来自 `by_syl_prefix` 的首块前缀查询，不依赖阶段 2 的
Top-K；对每条候选调用 `syllable_keyword_score`，按 `keyword` 权重
（默认 0.80）加入结果。若同一词条已有更高的精确/前缀/DP 分数，
`add_result` 会保留更高者。

这一阶段与阶段 2 的门槛完全解耦：

- 不会因为关键词 raw 很高而把 `best_raw` 推到 0.90 以上、阻断 DP；
- 也不会因为 `best_cheap_raw >= 0.93` 跳过阶段 2 而漏掉中段关键词；
- 代价是每条输入多一次前缀索引查询和少量候选的 DP，实测真实
  librime 下 7–9 键输入总耗时约 61–141 ms（约 9–16 ms/键）。

---

## 7. 通道权重与融合

对每个词条，取所有命中通道中 **加权得分最高者**：

```
final = raw_channel * weight[channel] + 0.0001 * phrase_weight
```

默认权重：

| 通道 | 权重 | 说明 |
|---|---:|---|
| exact | 1.00 | 精确全拼 |
| fuzzy | 0.97 | 安全 canon 相等 |
| prefix | 0.96 | 全拼前缀 |
| initial_exact | 0.96 | 原始声母串精确 |
| fuzzy_prefix | 0.95 | canon 前缀 |
| dp | 0.94 | 音节对齐 |
| swap | 0.93 | 相邻音节换位 |
| initial | 0.86 | canon 声母相等 |
| keyword | 0.80 | 声母子序列 / 音节前缀子序列；`initial_mode` 下 0.90 |
| fallback | 0.55 | 最近邻（Damerau / Dice-LCS） |

### 7.1 `initial_mode`

```
vowel_count = q 中 a/e/i/o/u/v 的数量
initial_mode = #q >= 2 and (
    vowel_count == 0
    or (#q <= 6 and vowel_count <= 1)
)
```

- `lkcc`、`wmhlkcdccnm`、`jdzhyo` 等进入声母/关键词模式；
- `shenluo`（3 元音/7）、`xingyun`（2/7）、`zongguo`（3/8）不会被误判为缩写；
- `initial_mode` 下跳过 DP 和阶段 3，关键词/声母权重提升。

### 7.2 排序 tie-break

```
1. final score 降序
2. channel_rank 升序（exact < fuzzy < prefix < fuzzy_prefix < swap < dp < initial_exact < initial < keyword < fallback）
3. 词条汉字数 n 升序（同分短词优先）
4. 词条权重 w 降序
5. 词典顺序 order 升序
```

---

## 8. 永远 N 个候选

1. 强通道结果先进入 `results`；
2. 若不足 N，`fill_fallback` 先按双/三字母重叠度召回候选，再用
   Damerau/Dice-LCS 排序补足；已有强命中时只做 16 个候选的小池；
3. 候选池为空或仍不足 N 时，`fill_static` 才从 `static_top` 兜底；
4. 空输入直接取 `static_top` 前 N；
5. 若 `matcher.rank` 抛错，`ff7-ime.lua` 用预构建的 fallback 顺序产出 N 个候选；
6. `top_n` 默认 9，可配置 1–64；1212 条词条保证任何 N≤1212 都能填满。

---

## 9. 复杂度

设输入长度 \(L\)、音节数 \(n\)、候选短名单 \(K=56\)、每音节读音数 \(A\)（通常 1–4）、块长 \(k\)（≤6）：

- 阶段 1：索引并集大小 \(C\)（通常 50–500），每词条 O(#fulls + #inits + L)，约 \(O(C \cdot L)\)；
- 阶段 2：重叠度排序 \(O(C \log C)\)，DP \(O(K \cdot L \cdot n \cdot A \cdot k)\)；
- 阶段 3：前缀索引召回通常 10–100 条，每条 O(\(n \cdot L \cdot A \cdot 3\))；
- 阶段 4：回退池排序 \(O(C_{fb} \log C_{fb})\)；相似度计算只对
  `max_candidates=96`（无强命中）或 `fast_max_candidates=16`（有强命中）
  条候选，每条 O(\(L \cdot F\))，其中 \(F\) 为全拼/声母串长度；
- 预编辑：O(\(L \cdot k\)) 的音节集合查询，对逐键耗时影响可忽略；
- 实测本机（librime 1.13.1 原生 Lua 5.4）：
  - 精确/前缀：约 5–10 ms/键；
  - 模糊/容错：约 10–65 ms/键（`zanguokuaigon` 单键最大 64.9 ms）；
  - 中段关键词：约 9–16 ms/键（`meishao` 7 键总耗时 61 ms，
    `shouxiang` 9 键总耗时 141 ms）；
  - 20 键长句 `renshengjiushizhandou` 总耗时约 87 ms；
  - 回退：`zzzzzz` 总耗时 32 ms，`asdfghjkl` 70 ms。

`dp_max_candidates`、`max_edit`、`top_n`、`fallback/max_candidates`
均可调，用于性能/召回权衡。

---

## 10. 评估结果

本机 1212 条数据上的自动评估（wasmoon Lua 5.4，`tests/lua/bulk_eval.js`）：

| 类别 | 用例 | 通过标准 | 结果 |
|---|---:|---|---|
| exact | 1212 | top1 | 100% |
| fuzzy | 878 | top1 | 100% |
| initial | 1212 | top1 或 top3 | 100%（top1 98.3%） |
| typo | 600 | top3 | 100%（top1 99.7%） |
| keyword | 238 | top5 | 97.9%（233/238；top1 76.1%） |
| mid_keyword | 300 | top5 | 100%（top1 91.0%） |
| fallback | 7 | 返回 N | 100% |

`mid_keyword` 使用长句中段**唯一出现**的 2–3 音节串（排除另一个词条的
全拼前缀、精确全拼、以及跨词条共享的串），覆盖 `meishao` 这类输入。
`keyword` 的 5 个失败仍是极稀疏声母子序列的天然歧义（如 `mlh` 同时像
“墨绿海马”与“莫古力召唤术”）；需求示例 `lkcc` 稳定 top1。详见
`docs/TEST_REPORT.md`。

---

## 11. 为什么不用 Rime 原生 script_translator

| 需求 | 原生 script_translator | 本方案 |
|---|---|---|
| 只输出固定 1212 条 | 会引入词典外候选/造句 | Lua 只 yield 1212 条 |
| 运行时模糊开关 | `speller/algebra` 编译期固定 | DP/配置运行时读取 |
| 关键词 `lkcc` | 无此通道 | 声母子序列 |
| 中段关键词 `meishao` | 无此通道 | 音节前缀子序列 |
| 漏/多/换位 | 无通用编辑距离 | Damerau + 音节 DP |
| 多音/误读权重 | 词典多读音有限 | 上下文读音 + 误读表 |
| 永远 N | 可能空 | 回退候选池 + 静态兜底 |

---

## 12. Lua 实现注意事项

- 不使用 `io`/`os` 读外部数据；数据在构建期嵌入 `ff7-ime_data.lua`，加载即用。
- `require("ff7-ime_matcher")` / `require("ff7-ime_data")` 由 `lua_translator@*ff7-ime` 自动加载。
- 数据表与索引在 `ff7-ime.lua` 的 `init` 中预热；模糊开关变化时 `build_index` 自动重建。
- 字符串均为 ASCII 拼音；中文只作为 `text` 原样输出，不做 UTF-8 子串操作。
- Candidate 参数顺序：`Candidate(type, start, end, text, comment)`；`seg._end` 为 0-based 结束偏移。
- 候选 `quality` 按 yield 顺序递减，保证 Rime 菜单顺序与 `M.rank` 返回顺序一致。
