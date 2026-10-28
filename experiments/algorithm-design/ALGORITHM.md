# 魔光键影：匹配与排序算法设计

本文件描述 FF7 中文词条输入方案（小狼毫 Weasel 0.17.4 / librime 1.13.1 / Lua 5.4）的匹配与排序算法。目标是在 **只输出 `dict.txt` 的 1212 条词条** 的前提下，把无调全拼、模糊音、多音字、声母串、关键词子序列、部分输入以及各种漏/多/换位错误统一成一个稳定、可解释、可翻译为 Lua 的排序问题。

配套文件：

| 文件 | 作用 |
|---|---|
| `ALGORITHM.md` | 本设计文档 |
| `build_phrases.py` | 从 `../dict.txt` 生成 `phrases.tsv`（数据准备，运行时不需要） |
| `phrases.tsv` | 运行时词典数据（1212 条，UTF-8，Tab 分隔） |
| `prototype.py` | Python 原型的匹配、排序、CLI、测试与消融 |
| `test_cases.json` | 55 条验收用例 |
| `RESULTS.md` | 可复现实验结果、敏感性/消融、失败案例 |
| `sensitivity.py` | 参数敏感性脚本 |

---

## 1. 目标、约束与总体思路

### 1.1 硬约束

1. 词典固定为 1212 条，每条作为一个整体候选输出；候选文本保留原文标点、间隔号、感叹号等。
2. 输入为中国大陆普通话无调全拼，小写字母，可能含 `'`、空格、连字符、标点；`ü` 可能写作 `v` 或 `u:`。
3. 平台为 librime 1.13.1 内嵌 Lua 5.4.7；Lua 侧没有第三方库，不能依赖 Python 的 `json`、`re`、`unicodedata`。
4. 逐键响应；1212 条数据可以全量常驻内存。

### 1.2 为什么不能只做“全拼编辑距离”

只做全拼编辑距离会出现三类无法修复的问题：

- `lkcc` 与“我们会立刻彻底铲除你们”的全拼 `womenhuilikechedichanchunimen` 编辑距离极大，但它是合法的声母子序列；必须显式建模“声母序列/子序列”。
- `lienuo` 对“雷诺” `leinuo` 是韵母内部换位；`lie` 本身是合法音节，单纯按音节切分会把输入切成 `lie + nuo`，必须保留字母级近似与音节级对齐两条通道。
- 长句字多，若按字符数或匹配字符数累加分数，长句会天然压过短词；必须把覆盖率、紧凑度、长度先验拆开，分别放进不同通道。

因此本设计采用 **多通道独立打分 + 噪声或融合（noisy-OR）**：

1. 每个通道只回答一种“证据”（精确、模糊、声母、关键词、音节对齐、字母编辑、二元组）。
2. 每个通道输出 `[0,1]` 的归一化分数。
3. 融合公式保证“精确匹配”必然为 1，多个弱证据可以互相加分，但单个强证据不会被弱证据淹没。
4. 排序时再用通道等级、词条长度、词条权重和原始下标做稳定的并列打破。

### 1.3 需求到通道的映射

| 需求 | 主要通道 |
|---|---|
| A 模糊音 zh/ch/sh→z/c/s、ng→n、可配置 n/l 等 | `fuzzy_exact`、`fuzzy_prefix`、`edit_fuzzy`、音节对齐中的模糊等价 |
| B 多音字、允许错读 | 每字读音集合 + 读音权重；`exact`/`syllable`/`initial_subseq` 都按读音集合取最优 |
| C 声母模式、关键词子序列、部分输入 | `initial_exact`、`initial_prefix`、`initial_subseq`、`keyword_subseq`、`prefix` |
| D 漏/多/错/相邻换位/音节换位 | 加权 Damerau-Levenshtein（OSA）+ 音节级 DP 的插入/删除/替换/换位 |
| E 永远返回 N 个候选 | 不对候选做阈值过滤；所有词条都有分数；Top-N 直接截断；空输入走最近邻回退 |
| F 短词/长句区分度、精确全拼稳定第一 | 精确通道权重最高；前缀/关键词通道带覆盖率与长度先验；并列时短词优先 |

---

## 2. 数据表示

### 2.1 `phrases.tsv` 接口

`build_phrases.py` 读取 `../dict.txt`（UTF-16 LE BOM、CRLF），用 `pypinyin` 生成：

```
text<TAB>pinyin<TAB>readings<TAB>weight
```

- `text`：原始词条，标点、间隔号、感叹号全部保留。
- `pinyin`：主读音，每个汉字一个无调音节，空格分隔；标点不占位。
- `readings`：每个汉字的候选读音，组内用 `|`，组间用 `;`。第一个永远是主读音。
- `weight`：词条权重，目前统一 `1.0`；预留给人工词频。

例：

```
雷诺	lei nuo	lei;nuo	1.0
陆行鸟	lu xing niao	lu|liu;xing|hang|heng;niao|diao	1.0
多米诺市长	duo mi nuo shi zhang	duo;mi;nuo;shi|fu;zhang|chang	1.0
```

生成规则：

1. 先对整条词条调用 `pypinyin.pinyin(text, heteronym=True, errors="ignore")`，得到上下文相关的读音。
2. 再对每个汉字单独取字符级异读，取并集；主读音始终排第一。
3. 标点被过滤，但 `text` 原样保留。

> 接口是稳定的：如果拼音数据子代理后续产出自己的 `phrases.tsv`，只要四列语义不变，`prototype.py` 不需要改。Lua 侧也可以把同一份数据预编译成 Lua 表。

### 2.2 词条内部字段

对每条词条 `e` 预计算：

| 字段 | 含义 |
|---|---|
| `chars` | 非标点汉字序列，长度 `n` |
| `primary` | 主读音音节序列 |
| `readings[i]` | 第 `i` 个字的 `(音节, 权重)` 列表 |
| `primary_str` | 主读音拼接串（无分隔） |
| `variants` | 读音组合的 beam，最多 24 个 `(拼接串, 组合权重)` |
| `initial_options[i]` | 第 `i` 个字的候选模糊声母字母及权重 |
| `initial_variants` | 声母串的 beam，最多 24 个 |
| `bigrams` | `primary_str` 的字符二元组多重集 |
| `syllable_starts` | `primary_str` 中每个音节起始下标集合 |
| `weight` | 词条权重 |

### 2.3 读音权重

对第 `i` 个字的读音列表：

- 主读音：`1.0`
- 第 `k` 个标准异读（`k = 1,2,...`）：
  `w_k = max(0.62, 0.82 - 0.06*(k-1))`
- 人工误读表 `MISREADINGS`：`0.55`

当前误读表：

```python
MISREADINGS = {
    "蒂": ["ti"],   # dì -> tì，tifa 命中 蒂法
    "诺": ["ruo"],  # nuò -> ruò，读半边
    "岑": ["qin"],  # cén -> qín，经典“有边读边”示例（当前词典无“岑”）
}
```

误读表与标准拼音数据分离，可以在 Lua 配置中开关或增删，不需要重建 `phrases.tsv`。

### 2.4 读音组合 beam

每个字有多个读音，长词条的组合数可能指数增长。用 beam 保留最多 24 个组合：

```
beam = [("", 1.0)]
for opts in readings:
    merged = {}
    for prefix, pw in beam:
        for syl, sw in opts:
            s = prefix + syl
            merged[s] = max(merged.get(s, 0), pw * sw)
    beam = top 24 of merged by (-weight, length, string)
```

主读音组合权重为 1；异读组合权重为各字权重乘积。`variants` 用于：

- 全拼精确/前缀；
- 模糊全拼精确/前缀；
- 词条展示。

它不用于逐字对齐（逐字对齐直接读 `readings`，避免组合爆炸）。

---

## 3. 输入规范化

输入 `raw` 处理为 `(letters, boundaries)`：

1. Unicode NFKC、转小写。
2. `ü`、`ǖǘǚǜ`、`u:` → `v`。
3. 只保留 `a-z`；其他字符丢弃。
4. 撇号 `'`、空格、连字符、逗号、句号、感叹号等的位置记录为 **硬边界** `boundaries`（在 `letters` 中的下标）。
5. 空串返回空。

例：

| 输入 | letters | boundaries |
|---|---|---|
| `di'baqu` | `dibaqu` | `{2}` |
| `KeLaoDiYaSiTeLaiFu` | `kelaodiyasitelaifu` | `{}` |
| `shenluo!` | `shenluo` | `{7}` |
| `fuqiuzhilüqicheng` | `fuqiuzhilvqicheng` | `{}` |

硬边界只影响音节切分：切分片段不得跨过边界。因此 `xi'an` 不会被切成 `xian`，而 `xian` 仍然同时保留 `xian` 和 `xi'an` 两种切分。

### 3.1 音节表

使用约 400 个标准无调音节，另加键盘写法 `lue`、`nue`（分别规范化为 `lve`、`nve`）。刻意剔除 `biang`、`bong`、`cei`、`den`、`din`、`fiao`、`hm`、`hng`、`len`、`m`、`n`、`ng`、`nun`、`rua`、`tei`、`wong` 等罕用/叹词形式，减少切分歧义。

同时预计算所有音节前缀集合 `SYLLABLE_PREFIXES`，用于识别“半个音节”。

---

## 4. 输入音节切分

### 4.1 目标

给定 `letters` 和硬边界，输出最多 `K = 6` 个候选切分。每个片段有三类：

| 类型 | 含义 | 惩罚 |
|---|---|---|
| `valid` | 完整合法音节 | `0` |
| `partial` | 某合法音节的前缀，但不是完整音节（如 `l`、`shenl` 中的 `l`） | `0.15 + 0.03*(len-1)` |
| `unknown` | 既非合法音节也非前缀的字母块（如 `leiknuo` 中的 `k`） | `0.40 + 0.05*(len-1)`，长度上限 4 |

### 4.2 递归 + beam 伪代码

```
seg(pos):
    if pos == len: return [([], 0, 0)]
    out = []
    for L in 1..MAX_SYL_LEN:
        end = pos + L
        if end > len: break
        if any boundary b with pos < b < end: break
        chunk = letters[pos:end]
        if chunk in SYLLABLES:      kind, pen = valid, 0
        elif chunk in PREFIXES:     kind, pen = partial, 0.15+0.03*(L-1)
        elif L <= 4:                kind, pen = unknown, 0.40+0.05*(L-1)
        else: continue
        for (rest, rpen, rcount) in seg(end):
            out.append(([Segment(chunk,kind,pen)] + rest, pen+rpen, rcount+1))
    sort out by (total_penalty, segment_count)
    return first K
```

### 4.3 歧义保留

- `xian`：`xian`（1 段）和 `xi + an`（2 段）都保留；前者段数少排前，但后者仍参与打分。
- `lienuo`：`lie + nuo`、`li + e + nuo`、`lie + nu + o` 都保留；`lie` 是合法音节，但“雷诺”需要 `lei`，因此不能只靠切分，必须让音节 DP 的替换代价和字母编辑通道同时工作。
- `leino`：`lei + n + o`、`lei + no`（unknown/partial）等保留；`no` 虽不合法，但作为 2 字母块与 `nuo` 的替换代价更低，最终由 DP 选择。
- `leiknuo`：`lei + k + nuo`、`lei + k + nu + o` 等保留；字母编辑通道同时给出 `leiknuo` vs `leinuo` 的 1 次插入分数。

`K=6` 是性能与召回的折中；`RESULTS.md` 给出 `K=3/6/12` 的敏感性。

---

## 5. 多通道匹配

记：

- 输入规范化串 `q`，长度 `Q = |q|`。
- 输入切分 `seg`，片段序列 `s_1..s_m`。
- 词条 `e`，汉字数 `n`，主读音 `p_1..p_n`，读音集合 `R_i`。

所有通道输出 `[0,1]`；`score_entry` 对每个通道取“该词条所有切分/所有读音组合中的最大值”。

### 5.1 全拼精确通道 `exact`

对 `e.variants` 中每个 `(v, w)`：

- 若 `v == q`：`S_exact = 0.85 + 0.15*w`。

主读音组合 `w=1` 时 `S_exact=1.0`；异读精确匹配时 `S_exact≈0.97`；误读精确匹配时 `≈0.93`。若命中 `1.0`，`score_entry` 直接返回 1.0（精确匹配不可能被其他通道超过），同时省掉后续计算。

### 5.2 模糊全拼通道 `fuzzy_exact`

核心模糊变换：

```
fuzzy_core(s):
    s = s.replace("zh","z").replace("ch","c").replace("sh","s")
    s = s.replace("ng","n")
    return s
```

- `zh/ch/sh → z/c/s`
- `ng → n`，同时覆盖 `ang→an`、`eng→en`、`ing→in`、`uang→uan`
- 不在这里做 `n/l`、`r/l`、`f/h` 的全局替换，因为这些字母也可能出现在韵母里；它们在音节级模糊键和字母代价中处理。

若不存在精确匹配，且存在 `fuzzy_core(v) == fuzzy_core(q)`：

```
S_fuzzy_exact = 0.90 * (0.90 + 0.10*w)
```

主读音模糊精确为 `0.90`，严格低于精确的 `1.0`。

### 5.3 前缀通道 `prefix` / `fuzzy_prefix`

对每个 `(v,w)`，若 `len(q) < len(v)` 且 `v.startswith(q)`：

```
cov = len(q) / len(v)
S_prefix = cov^0.6 * (0.85 + 0.15*w)
```

`S_prefix` 取所有变体最大值。`cov^0.6` 让“输入了词条的大部分”得分更高，同时不因长词条长度直接归零。

模糊前缀同理：

```
S_fuzzy_prefix = 0.88 * (len(fq)/len(fv))^0.6 * (0.90 + 0.10*w)
```

其中 `fq=fuzzy_core(q)`、`fv=fuzzy_core(v)`。

例：

- `shenl` vs `神罗`：`5/7`，`S_prefix≈0.82`。
- `shen` vs `神罗`：`4/7`，`S_prefix≈0.72`。
- `shen` vs `神罗战士`：`4/9`，`S_prefix≈0.58`；短词自然胜出。

### 5.4 加权字母 Damerau-Levenshtein 通道 `edit` / `edit_fuzzy`

使用 OSA（Optimal String Alignment）版本，只允许相邻换位：

```
D[0][j] = j
D[i][0] = i
D[i][j] = min(
    D[i-1][j] + 1,                  # 删除
    D[i][j-1] + 1,                  # 插入
    D[i-1][j-1] + c_sub(a_i, b_j)   # 替换
)
if i>1 and j>1 and a_i == b_{j-1} and a_{i-1} == b_j:
    D[i][j] = min(D[i][j], D[i-2][j-2] + 1)   # 相邻换位 = 1 次操作
```

替换代价：

```
c_sub(a,b) = 0.25   if (a,b) in {(n,l),(l,n),(r,l),(l,r),(f,h),(h,f)} 且对应模糊开关开启
           = 1.0    otherwise
```

- 漏字母、多字母、错字母：各 1。
- 相邻字母换位：1。
- 可配置的单字母模糊（n/l、r/l、f/h）：0.25。
- `zh/ch/sh`、`ng` 的长度差由 `edit_fuzzy` 处理：把两边都做 `fuzzy_core` 后再算 OSA。

归一化：

```
S_edit      = max(0, 1 - D(q, primary_str) / max(Q, len(primary_str)))
S_edit_fuzzy= 0.92 * max(0, 1 - D(fuzzy_core(q), fuzzy_core(primary_str)) / max(...))
```

例：

| 输入 | 目标 | D | 长度 | `S_edit` |
|---|---|---|---|---|
| `lienuo` | `leinuo` | 1（i/e 换位） | 6 | 0.833 |
| `leino` | `leinuo` | 1（漏 u） | 6 | 0.833 |
| `leiknuo` | `leinuo` | 1（多 k） | 7 | 0.857 |
| `leinou` | `leinuo` | 1（u/o 换位） | 6 | 0.833 |
| `nuolei` | `leinuo` | 4（块换位） | 6 | 0.333 |

`nuolei` 的块换位不靠字母通道，靠 5.5 的音节换位。

### 5.5 音节级对齐 DP 通道 `syllable`

这是处理“音节漏/多/错/换位”和“半个音节”的核心。

#### 状态

```
D[i][j] = 将词条前 i 个汉字与输入前 j 个片段对齐的最小代价
i = 0..n, j = 0..m
```

#### 转移

1. **跳过词条音节**（输入少了一个音节）：
   `D[i+1][j] = min(D[i+1][j], D[i][j] + 1)`
2. **输入多一个片段**：
   `D[i][j+1] = min(D[i][j+1], D[i][j] + 1)`
3. **匹配/替换**：对第 `i` 个字的每个读音 `r`、权重 `w`：
   `D[i+1][j+1] = min(D[i+1][j+1], D[i][j] + c_sub(seg_j, r) + λ_r*(1-w))`
   其中 `λ_r = 0.12`。
4. **相邻音节换位**：
   `D[i+2][j+2] = min(D[i+2][j+2], D[i][j] + c_sub(seg_j, r_{i+1}) + c_sub(seg_{j+1}, r_i) + λ_t + 读音惩罚)`
   其中 `λ_t = 0.35`。

#### 音节替换代价 `c_sub`

```
c_sub(q, r):
    q, r = canon(q), canon(r)
    if q == r:                          return 0
    if fuzzy_key(q) == fuzzy_key(r):    return 0.18
    if len(q) < len(r) and r.startswith(q):
        return 0.30 + 0.25*(1 - len(q)/len(r))      # 半个音节：l vs luo
    if len(r) < len(q) and q.startswith(r):
        return 0.42 + 0.25*(1 - len(r)/len(q))
    d = OSA(q, r)  # 单字母模糊代价 0.25
    return min(1.0, 0.25 + 0.75*d/max(len(q),len(r)))
```

`fuzzy_key` 是音节级模糊键：

- 声母：`zh→z, ch→c, sh→s`；可选 `n→l, r→l, f→h`（默认关闭）。
- 韵母：结尾 `ng→n`。
- 这样 `zhong` 与 `zong` 都变 `zon`；`shen` 与 `sheng` 都变 `sen`；`ni` 与 `li`（开启 n/l 时）都变 `li`。

#### 归一化

```
S_syllable = max(0, 1 - D[n][m] / max(n, m))
```

若 `|n-m| > 4`，该通道直接返回 0：极短查询对极长词条的“删光”代价没有区分度，应交给声母/关键词通道。

例：

- `lienuo` 的 `lie+nuo` vs `lei+nuo`：`c_sub(lie,lei) = 0.25 + 0.75*(1/3) = 0.5`，`S=0.75`。
- `leino` 的 `lei+no` vs `lei+nuo`：`c_sub(no,nuo)=0.5`，`S=0.75`。
- `leiknuo` 的 `leik+nuo`（若切分被保留）vs `lei+nuo`：`c_sub(leik,lei)=0.4375`，`S≈0.78`。
- `nuolei` vs `lei+nuo`：换位 `0.35`，`S=0.825`。
- `shenl` 的 `shen+l` vs `shen+luo`：`c_sub(l,luo)=0.30+0.25*(1-1/3)=0.467`，`S≈0.77`。

### 5.6 声母精确/前缀通道 `initial_exact` / `initial_prefix`

对每个字取所有读音的 **模糊声母字母**：

```
initial_letter(zh/ch/sh) = z/c/s
initial_letter(n) = l  (若 n/l 开启)
initial_letter(r) = l  (若 r/l 开启)
initial_letter(f) = h  (若 f/h 开启)
其他声母原样；零声母（a/e/o/er）为空
```

预计算 `initial_variants`（最多 24 个声母串 + 组合权重）。

- 若 `q_init == v`：`S_initial_exact = 0.95 * (0.90 + 0.10*w)`。
- 若 `q_init` 是 `v` 的严格前缀：
  `S_initial_prefix = 0.90 * (len(q_init)/len(v))^0.6 * (0.90+0.10*w)`。

`q_init = fuzzy_initials_query(q)` 只折叠 `zh/ch/sh`，**不折叠 `ng`**，因为 `n` 和 `g` 可能是两个相邻声母。

可选 `n/l`、`r/l`、`f/h` 的处理分两层：

- 词条侧 `initial_letter` 会按配置映射为 `l/l/h`；
- 查询侧 `initial_exact` 不做单字母映射，避免把 `ng` 里的 `n` 误映射；`initial_subseq` 用 `letter_fuzzy_pair` 在匹配时以 0.25 代价接受 `n↔l`、`r↔l`、`f↔h`。
- 音节级和字母级通道同样使用 `letter_fuzzy_pair` / `fuzzy_syllable_key`，因此可选模糊在三条路径上都可用；默认关闭。

### 5.7 声母子序列通道 `initial_subseq`

用于 `lkcc`、`wmhlkcd` 这类查询。

输入预处理后为 `q_init`（长度 `qn`）。对每个起始位置 `s`，要求：

- 第 `s` 个字能匹配 `q_init[0]`（精确代价 0，模糊声母代价 0.25）；
- 依次在 `s+1..` 中找后续查询字母；
- 允许跳过任意多个字，但记录跨度 `span = end - s + 1`。

DP 形式（对每个 `s`）：

```
dp[0] = (cost=0, last=s-1)
for i = s..n-1:
    for j = qn-1 down to 0:
        for each (letter, w) in initial_options[i]:
            c = 0        if letter == q_init[j]
              = 0.25     if fuzzy_initial_pair(letter, q_init[j])
              = None     otherwise
            dp[j+1] = min(dp[j+1], (dp[j].cost + c + 0.05*(1-w), i))
```

取所有 `s` 中 `dp[qn]` 可达的最优（代价低优先，其次跨度短）。

打分：

```
compact   = qn / span
phrase_cov= qn / n
prior     = 1 / (1 + λ_len * max(0, n - 6)),   λ_len = 0.02
S_init_sub = compact^0.9
           * (0.55 + 0.45*sqrt(phrase_cov))
           * prior
           * w_prod^0.25
           * (1 - 0.15*min(1, cost))
```

解释：

- `compact`：查询字母在词条声母串中越紧凑越好；`lkcc` 在 11 字长句中跨 5 个音节，`compact=4/5=0.8`。
- `phrase_cov`：匹配到的声母占词条总音节比例；长句比例低，用 `sqrt` 缓和对数惩罚，防止长句无条件占优。
- `prior`：对 6 音节以上的词条轻微降权；不是硬长度惩罚。
- `w_prod`：使用异读/误读声母时降权。
- `cost`：模糊声母匹配的代价。

例：`lkcc` vs “我们会立刻彻底铲除你们”：

- 声母 `w m h l k c d c c n m`，`l k c c` 匹配位置 3,4,5,7（0 基），`span=5`；
- `compact=0.8`，`phrase_cov=4/11=0.364`；
- `S_init_sub ≈ 0.8^0.9 * (0.55+0.45*0.603) * 0.909 ≈ 0.61`。

### 5.8 关键词字母子序列通道 `keyword_subseq`

用于更一般的“关键词”输入（不一定是声母）。对 `primary_str`：

- 对每个起始位置 `s`，贪心找 `q` 的后续字母，得到最短跨度 `span`；
- `boundary_ratio` = 匹配位置中落在音节起始位置的比例；
- `compact = qn/span`。

```
S_keyword = compact^1.1
          * (0.55 + 0.45*boundary_ratio)
          * prior
```

该通道权重较低（0.5），主要作为辅助证据；声母子序列通道对 `lkcc` 这类输入更可靠。

### 5.9 二元组通道 `bigram`

主读音串的字符二元组多重集，与查询的二元组做 Dice 系数：

```
S_bigram = 2*|A ∩ B| / (|A| + |B|)
```

作用：

- 为乱码输入提供“最近邻”排序，保证 Top-N 不空；
- 对短查询（长度 < 2）用单字符集合代替。

### 5.10 通道汇总

`score_entry` 计算：

```
exact, fuzzy_exact
prefix, fuzzy_prefix
initial_exact, initial_prefix
edit, edit_fuzzy
syllable = max over segmentations
initial_subseq
keyword_subseq
bigram
```

然后交给融合。

---

## 6. 打分融合

### 6.1 噪声或（noisy-OR）

```
S_final = 1 - Π_c (1 - s_c)^{w_c}
```

- `s_c ∈ [0,1]` 是通道分数；
- `w_c ≥ 0` 是通道权重（指数）；
- 若任一通道 `s_c=1`，则 `S_final=1`（精确匹配覆盖一切）；
- 多个弱证据可以累加，但不会把单个强证据淹没；
- 结果天然在 `[0,1]`。

默认权重：

| 通道 | 权重 | 说明 |
|---|---:|---|
| `exact` | 1.0 | 精确全拼，最高可信 |
| `fuzzy_exact` | 1.0 | 模糊全拼精确 |
| `initial_exact` | 1.0 | 全声母精确 |
| `prefix` | 1.0 | 前缀/部分输入 |
| `fuzzy_prefix` | 0.9 | 模糊前缀 |
| `edit` | 0.9 | 字母编辑 |
| `edit_fuzzy` | 0.7 | 模糊字母编辑 |
| `syllable` | 1.1 | 音节对齐 |
| `initial_prefix` | 0.9 | 声母前缀 |
| `initial_subseq` | 1.7 | 声母子序列（关键词） |
| `keyword_subseq` | 0.5 | 字母关键词子序列 |
| `bigram` | 0.25 | 回退/最近邻 |

### 6.2 分数解释与饱和

噪声或会让多个通道同时给出中等分数时快速接近 1。例如“雷诺”的四个错误输入会同时得到 `edit≈0.83`、`edit_fuzzy≈0.77`、`syllable≈0.75`、`bigram≈0.4~0.73`，融合后约 `0.99`。这符合“多个独立证据都指向同一词条”的直觉，但也意味着 **高分区排名差距会变小**；因此并列打破规则必须稳定。

如果需要更“可读”的分数，可对最终分数做单调变换（如 `S^1.2`），不改变排序；原型保留原始值。

### 6.3 长度、覆盖率、紧凑度

本设计不设全局长度惩罚，而是把长度因素放进各自通道：

- 精确/模糊全拼：不惩罚，精确就是精确；
- 前缀：`len(q)/len(v)` 覆盖率，长词条自然低；
- 音节对齐：按 `max(n,m)` 归一化，长短差异体现在代价上；
- 声母子序列：`compact` + `sqrt(phrase_cov)` + 轻微 `prior`；
- 关键词：`compact` + `boundary_ratio` + `prior`。

这样 `shenluo` 精确命中“神罗”时得 1.0，而“神罗兵”只有 `prefix≈0.76`；同时 `lkcc` 仍能让 11 字长句得到约 0.87 的总分。

### 6.4 Top-N、回退与去重

- 对全部 1212 条词条打分并排序，直接取前 `N`；**不设阈值过滤**，因此永远返回 `N` 个（`N > 1212` 时返回全部）。
- 词条文本本身唯一（已检查 1212 条无重复）；若未来有重复，按 `text` 去重，保留分数最高者。
- 记录 `fallback = (max_channel_score < 0.5)`，仅用于 UI 提示“没有强证据，以下为最近邻”，不影响输出。
- 空输入（纯标点/数字）返回按 `(长度, -权重, 原始下标)` 排序的前 `N` 条，分数 0。

### 6.5 并列打破规则

排序键：

```
(-S_final, channel_rank, len(chars), -weight, idx)
```

`channel_rank` 按通道可信度：

```
exact < fuzzy_exact < initial_exact < prefix < initial_prefix
      < initial_subseq < keyword_subseq
      < edit < syllable < fuzzy_prefix < edit_fuzzy < bigram
```

即：

1. 精确 > 模糊精确 > 全声母 > 前缀 > 声母前缀 > 声母子序列 > 字母关键词 > 编辑 > 音节 > 模糊前缀 > 模糊编辑 > 二元组；
2. 同分短词优先；
3. 同分高词条权重优先；
4. 最后按原始下标，保证稳定。

---

## 7. 参数表

| 参数 | 默认 | 范围/说明 |
|---|---:|---|
| `top_n` | 5 | 建议 5 或 9 |
| `max_segmentations` | 6 | 3–12；越大召回越高、越慢 |
| `max_variants` | 24 | 16–32；读音组合 beam |
| `alt_reading_weight` | 0.82 | 第 2 读音；之后每项 −0.06，下限 0.62 |
| `misread_weight` | 0.55 | 人工误读 |
| `reading_penalty` | 0.12 | 音节 DP 中使用非主读音的代价系数 |
| `length_penalty` | 0.02 | 声母/关键词通道对 6 音节以上词条的轻微降权 |
| `prefix_exponent` | 0.6 | 前缀覆盖率指数 |
| `compact_exponent` | 0.9 | 声母子序列紧凑度指数 |
| `fallback_threshold` | 0.5 | 最大通道分数低于此值标记“无强证据”（仅 UI 提示） |
| `fuzzy.zh_z` | true | zh→z |
| `fuzzy.ch_c` | true | ch→c |
| `fuzzy.sh_s` | true | sh→s |
| `fuzzy.ng_n` | true | ng→n（含 an/ang、en/eng、in/ing、uan/uang） |
| `fuzzy.n_l` | false | 预留 |
| `fuzzy.r_l` | false | 预留 |
| `fuzzy.f_h` | false | 预留 |
| `fuzzy.en_eng` | true | 由 ng→n 覆盖 |
| `fuzzy.in_ing` | true | 由 ng→n 覆盖 |
| `fuzzy.an_ang` | true | 由 ng→n 覆盖 |
| `fuzzy.uan_uang` | true | 由 ng→n 覆盖 |

完整敏感性结果见 `RESULTS.md`。

---

## 8. 复杂度

记词条数 `E = 1212`，词条平均音节数 `n ≤ 15`，读音组合 beam `V ≤ 24`，切分数 `K ≤ 6`，查询长度 `Q ≤ 24`。

单次查询：

| 步骤 | 复杂度 |
|---|---|
| 规范化 + 切分 | `O(Q * MAX_SYL_LEN * K)` |
| 每词条 exact/prefix | `O(V * n)` |
| 每词条 OSA | `O(Q * n)` |
| 每词条音节 DP | `O(K * (n*Q*R + n*Q))`，`R` 为平均异读数 |
| 每词条声母子序列 | `O(n^2 * Q)`（仅当查询字母可作声母时） |
| 每词条关键词 | `O(n * Q^2)` 最坏，实际 `n,Q` 很小 |
| 排序 | `O(E log E)` |

总体约 `O(E * (V*n + Q*n + K*n*Q*R + n^2*Q))`。Python 原型在本机约 **0.4–0.5 秒/查询**（1212 条，含全部通道与解释信息）；Lua 5.4 使用平坦数组、预计算和复用缓冲区后预计显著更快，但仍应在 `experiments/lua-probe` 实测逐键延迟。

优化点（已在原型中实现）：

- 音节替换代价 `_sub_cache` 缓存；
- 音节换位代价矩阵预计算；
- 精确命中直接返回 1.0；
- `|n-m| > 4` 时跳过音节 DP；
- 切分数限制为 6；
- 预计算 variants、声母 variants、bigram、syllable starts。

---

## 9. Lua 5.4 实现建议

### 9.1 数据加载

不要把 TSV 解析放在每次按键的路径上。推荐在 `translator` 模块初始化时加载一次：

```
local entries = {}
for line in io.lines("phrases.tsv") do
    local text, py, readings, weight = line:match("^(.-)\t(.-)\t(.-)\t(.-)$")
    ...
end
```

更稳妥的做法是用构建脚本预生成 `phrases.lua`：

```lua
return {
  { text="神罗", py={"shen","luo"}, readings={{"shen"},{"luo"}}, weight=1.0 },
  ...
}
```

Lua 侧不要在热路径使用 JSON；`phrases.lua` 直接 `require` 或 `dofile` 一次。

### 9.2 表与数组

- Lua 表从 1 开始；DP 数组用 `dp[i][j]` 或一维展开 `dp[(i-1)*(m+1)+j]`。
- 不要对含 `nil` 的稀疏表用 `#`；所有数组保持连续。
- 预计算并缓存：
  - `fuzzy_key[syllable]`
  - `initial_letter[syllable]`
  - `variants[entry]`
  - `initial_options[entry][i]`
  - `bigrams[entry]`
  - `syllable_starts[entry]`
- 音节替换代价用 `cache[q.."\0"..r]` 缓存；查询级缓存可在每次按键开始时清空，避免跨查询污染。

### 9.3 字符串操作

- `string.sub(s, i, j)`、`string.byte(s, i)`、`string.char(...)`。
- 关键词子序列用 `string.find(text, ch, pos, true)`（`plain=true`，避免模式匹配）。
- 不要用 Lua 模式匹配做拼音规范化；用显式 `string.sub` 判断 `zh/ch/sh` 前缀和 `ng` 结尾。
- `fuzzy_core` 对整串替换时，`string.gsub` 可用，但建议手写循环，避免每次分配。

### 9.4 OSA 与 DP

- OSA 只需保留前两行（`prev2`, `prev`, `cur`），空间 `O(n)`。
- 音节 DP 需要 `(n+1)*(m+1)`；`n,m ≤ 24`，可直接分配二维表，或复用预分配的扁平数组。
- 换位代价矩阵 `swap[j][i]` 先算好，再进 DP，避免在状态循环里重复遍历读音。
- 所有代价用 number；Lua 5.4 默认 double，足够。

### 9.5 排序与候选输出

- `table.sort` 的比较器必须实现完整并列规则：
  `score desc, channel_rank asc, length asc, weight desc, idx asc`。
- 只取前 `N` 时可用部分选择（插入排序维护 N 个），避免全排序；1212 条全排序也很快。
- librime translator 中：

```lua
function translator.translator(input, seg, env)
  local q, boundaries = normalize(input)
  ...
  for _, item in ipairs(top_n) do
    local cand = Candidate("ff7", seg.start, seg._end, item.text, item.comment)
    cand.quality = item.score
    yield(cand)
  end
end
```

- `item.text` 必须来自原始 `dict.txt`，不能重新拼接或改写标点。
- `comment` 可显示主拼音或命中通道，便于调试；正式版可关闭以减少视觉噪音。
- `quality` 用融合分数，librime 会按 quality 再排序；如果希望完全由 Lua 控制顺序，可把 quality 设为递减的极小值或统一值，并在 `yield` 顺序中体现。

### 9.6 性能注意事项

- 不要在每个按键重新读取/解析 1212 条数据。
- 不要为每个候选创建大量临时表；尽量复用。
- 先用 `input` 的长度和首字母做粗筛：
  - 输入很长且不含元音时，优先走声母通道；
  - 输入是完整音节序列时，优先走精确/前缀通道。
- 如果逐键延迟超标，可先只算 `exact`、`prefix`、`initial_*`，再在空闲时补算 `syllable`/`keyword`。

---

## 10. 失败案例与风险

### 10.1 `kcc` 的歧义

`kcc` 的 top1 是“狂野驰骋”（`kuangyechicheng`，声母 `k y c ch` 模糊后 `k y c c`），目标长句只排第 3。原因：

- `kcc` 只有 3 个字母，短词“狂野驰骋”的声母子序列更紧凑；
- 长句的 `phrase_cov` 低，`compact` 也不如 4 字母的 `lkcc`。

这不是算法错误，而是输入本身歧义。文档和测试以 `lkcc` 作为关键词示例；`kcc` 只要求进入 top5（见 `test_cases.json` 的 `keyword_kcc_in_top5`）。

### 10.2 `shenluoshen` 的“多一个音节”

输入 `shenluoshen` 时 top1 是“神罗兵”，原词“神罗”排第 2：

- “神罗兵”是 3 音节，查询也是 3 音节，音节 DP 的替换代价只涉及最后一个音节；
- “神罗”是 2 音节，需要额外插入一个音节，归一化后略低。

这符合“输入多了一个音节时，长度相同的词条更可信”的直觉；原词仍在 top3。若希望原词优先，可提高 `prefix` 权重或对“输入以词条全拼为前缀”的情况加一个 `prefix_bonus`；当前设计选择不额外加，以避免长词条前缀过度占优。

### 10.3 `shanshou` 的异读 + 长词条前缀

“单手是枪的男人”的“单”可读 `shan`，但 `shanshou` 只覆盖 7 字长句的前 2 个音节；短词“蛇鸡兽”（`shejishou`）在编辑距离/音节对齐上更接近。结果 `shanshou` 的 top1 是“蛇鸡兽”，`单手是枪的男人` 不在 top10。

这是“部分输入 + 低频异读 + 长词条”的三重劣势：

- 覆盖率 `2/7` 很低；
- `shan` 是第 3 读音，权重 0.70；
- 短词的音节对齐分数更高。

如果实际用户经常用异读前缀打长句，可以提高 `prefix` 通道权重或给“首音节为异读且后续匹配”的情况加通道；当前默认优先保证短词/精确匹配的稳定性。

### 10.4 噪声或饱和

多个通道同时命中时，融合分数会接近 1，导致高分区区分度下降。例如：

- `神罗` 精确 = 1.0；
- `神罗兵` 前缀 0.762 + bigram 0.75 + keyword 0.679 + syllable 0.667 → 0.9941。

排序仍正确（精确 1.0 在前），但分数差距只有 0.006。若 UI 需要展示分数，建议做单调压缩或只显示通道标签。

### 10.5 多音字过度生成

`区` 的异读 `ou`、`单` 的 `chan/shan`、`解` 的 `xie` 等会扩大召回，也可能带来误命中。当前用读音权重（0.82/0.76/…）和 `reading_penalty` 抑制；如果实际误命中过多，可以：

- 只保留常用异读（人工白名单）；
- 降低 `alt_reading_weight`；
- 对第 3 个及以后异读设更低权重或禁用。

### 10.6 误读表是人工的

`蒂→ti`、`诺→ruo` 是人工加入的；`岑→qin` 目前词典中没有“岑”，所以不影响结果。误读表无法覆盖所有“有边读边”的情况，需要后续根据用户反馈扩充。建议：

- 按词条维护 `allowed_misreadings`；
- 误读权重固定在 0.4–0.6；
- 误读匹配只在没有规范读音精确匹配时作为补充证据。

### 10.7 切分歧义 `xian`

`xian` 同时保留 `xian` 和 `xi'an`。如果词典同时有“先”和“西安”，两者都会得到候选；当前词典没有“西安”，所以不构成实际问题。Lua 侧应保留同样的多切分，不要只取最长匹配。

### 10.8 性能风险

Python 原型约 0.4–0.5 秒/查询；Lua 侧如果逐键执行全部通道，可能超过 100ms。必须：

- 预加载数据；
- 缓存音节代价；
- 限制切分数；
- 对明显不匹配的词条跳过音节 DP（`|n-m|>4`）；
- 在 `lua-probe` 中实测并做粗筛。

### 10.9 无调与同音词

无调全拼无法区分声调，同音词完全依赖词条长度、读音权重和通道证据。当前词典只有 1212 条，冲突有限；若扩充词典，需要引入词频/上下文模型，否则同音短词会互相竞争。

---

## 11. 验收对照

| 验收项 | 结果 |
|---|---|
| `lkcc` top1 长句 | 通过（0.8708，第二名 0.5699） |
| `lienuo` / `leino` / `leiknuo` top1 雷诺 | 通过（0.9862 / 0.9924 / 0.9874） |
| 模糊音 zh/z、ch/c、sh/s、ng/n | 通过（`zongli` / `congfengzhihua` / `senluo` / `shengluo` / `cen`） |
| 精确全拼短词/长句/标点/间隔号 | 通过 |
| 多音字 9 类 | 通过（重、长、行、乐、曾、区、解、单、仇） |
| 误读 蒂→ti、诺→ruo | 通过 |
| 无匹配仍返回 N 个 | 通过（5 个乱码用例 + 9 个候选用例） |
| 测试集可复现 | `python prototype.py --eval test_cases.json`，55/55 |

详细数字、消融和敏感性见 `RESULTS.md`。
