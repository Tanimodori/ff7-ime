# 使用说明

---

## 1. 基本输入

- 方案切换：**F4** 或 **Ctrl+`**，选择 **魔光键影**。
- 输入法：中国大陆普通话**无调全拼**；不需要输入声调。
- 候选：默认每页 9 个，数字键 1–9 选择；空格/回车/小键盘回车提交高亮候选；`-`/`=` 或 `,`/`.` 翻页（取决于 `key_binder`）。
- 预编辑：输入框内实时显示预测音节分隔符（`diou` → `di'ou`，`shenl` → `shen'l`）；只影响显示，不影响上屏文本。
- 中英切换：本方案禁用 Shift 中英切换（`Shift_L`/`Shift_R` 均为 `noop`），按 Shift 不会进入英文模式，Shift 会透传给游戏；需要英文时切换到 `luna_pinyin_simp`。
- 只输出 `data/dict.txt` 的 1212 条词条；不会出现词库外候选、造句、用户新词。
- 所有候选项右侧有注释：`通道 · 主拼音`，例如：
  - `全拼 · shen luo`
  - `模糊 · shen luo`
  - `前缀 · shen luo bing`
  - `容错 · lei nuo`
  - `关键词 · wo men hui li ke che di…`
  - `声母 · wo men hui ...`
  - 命中非主读音时显示 `全拼·异读 · zhong li`。

---

## 2. 输入模式与示例

### 2.1 精确全拼

| 输入 | 候选 |
|---|---|
| `shenluo` | 神罗 |
| `leinuo` | 雷诺 |
| `difa` | 蒂法 |
| `kelaode` | 克劳德 |
| `safeiluosi` | 萨菲罗斯 |
| `renshengjiushizhandou` | 人生就是战斗！ |
| `difaluokehate` | 蒂法·洛克哈特（间隔号自动保留） |

### 2.2 模糊音

默认开启：

- `zh/ch/sh → z/c/s`
- `ng → n`
- `v/u` 互通（ü 的两种输入）

| 输入 | 候选 | 说明 |
|---|---|---|
| `senluo` | 神罗 | sh→s |
| `zanguokuaigon` | 掌掴快攻 | zh→z、ng→n |
| `senguilon` | 圣柜龙 | ng→n |
| `sangulon` | 上古龙 | sh→s、ng→n |

可选（默认关闭）：`n/l`、`r/l`、`f/h`、`en/eng`、`in/ing`、`an/ang`、`uan/uang`。

### 2.3 多音字与允许误读

- 多音字按词条内上下文读音匹配：
  - `zhongli` / `chongli` → 重力（重 zhòng / chóng）
  - `changzhang` / `zhangzhang` → 长杖（长 cháng / zhǎng）
  - `hangkong` → 野马航空（行 háng）
  - `deihuozhe...` → 得活着才能是塔克斯（得 děi）
- 允许误读（权重低于规范读音）：
  - `qinmu` / `cenmu` → 梣木
  - `ceng` / `zeng` → 曾
  - `xueji` / `xieji` → 血祭
  - `touzi` / `shaizi` → 骰子
  - `luode` / `leide` → 路德（德 dé；dei 为低权重误读）

### 2.4 全声母

输入每个音节的声母，`zh/ch/sh` 可写全或只写首字母：

| 输入 | 候选 |
|---|---|
| `wmhlkcdccnm` | 我们会立刻彻底铲除你们！ |
| `sl` | 神罗 |
| `chm` | 沉默（而非催眠，因为原始声母串精确） |
| `hshkyq` | 回声扩音器（而非黄色扩音器） |

### 2.5 关键词子序列

声母的稀疏子序列，适合长句缩写：

| 输入 | 候选 |
|---|---|
| `lkcc` | 我们会立刻彻底铲除你们！ |
| `jdzhyo` | 就是大家最喜欢的尤菲哦！ |
| `adbym` | 肮脏的鼠辈，欢迎你们！ |

> 极稀疏缩写可能存在天然歧义（例如 `mlh` 同时像“墨绿海马”和“莫古力召唤术”）；方案保证 Top-N，但不保证 top1 一定是您心中那一条。

### 2.6 中段关键词（音节前缀子序列）

输入可以匹配词条**中段**的连续音节，用每个音节的前缀拼出来，不需要从词条开头输入：

| 输入 | 候选 |
|---|---|
| `meishao` | 有时是出手相助的美少女忍者！ |
| `meishaonv` | 有时是出手相助的美少女忍者！ |
| `shouxiang` | 有时是出手相助的美少女忍者！ |
| `chushou` | 有时是出手相助的美少女忍者！ |

规则：

- 输入块必须是某个音节读音的前缀，例如 `mei` + `shao`；
- 允许跳过中间音节，所以关键词可以出现在词条中段；
- 不做编辑距离；错字仍走“容错”通道；
- 如果输入同时是另一个词条的全拼前缀，前缀候选仍然优先。例如 `zhiwen` 会先给 `直纹叶翼蜥`，`少女之吻` 排在其后；
- 可用 `ff7-ime/keyword/syllable_subsequence: false` 关闭，只保留声母子序列。

### 2.7 部分输入

| 输入 | 候选 |
|---|---|
| `shen` | 神罗 / 神罗兵 / 神罗大厦 … |
| `shenl` | 神罗（短词优先） |
| `shenluo` | 神罗（精确） |

### 2.8 漏输 / 多输 / 错输 / 换位

| 输入 | 候选 | 错误类型 |
|---|---|---|
| `leino` | 雷诺 | 漏 u |
| `leiknuo` | 雷诺 | 多 k |
| `lienuo` | 雷诺 | 相邻字母换位 |
| `nuolei` | 雷诺 | 相邻音节换位 |
| `dhenluo` | 神罗 | 首字母错 |
| `shuanganozhe` | 双脑者 | 音节内换位 |

### 2.9 含标点词条

词条中的 `！，·……？、` 会原样输出，用户不需要输入标点：

| 输入 | 候选 |
|---|---|
| `renshengjiushizhandou` | 人生就是战斗！ |
| `zouleixinderen` | 走了，新来的！ |
| `hexihexi` | 呵嘻，呵嘻！ |
| `shuangrenshizhinazhongshuangrenma` | 双人……是指那种双人吗？ |
| `difaluokehate` | 蒂法·洛克哈特 |

---

## 3. 候选与 Top-N

- 每次按键都会重新计算并给出 **N 个候选**（默认 9）。
- N 可在 `ff7-ime/top_n` 修改；`menu/page_size` 建议与 N 相同（或更小，用翻页）。
- 即使输入乱码、单字母或空串，也不会空输出：
  - 乱码/无匹配：按共享 bigram/trigram 召回，再用 Damerau + Dice-LCS 排序；
  - 已有强命中时只补 16 个小池候选；无强命中时补 96 个；
  - 空输入：按词条权重/长度/词典序取前 N。
- 精确全拼永远 top1；同分时按通道优先级、短词、词条权重、词典序排序。

---

## 4. 配置

编辑 `%APPDATA%\Rime\ff7-ime.custom.yaml`，修改后重新部署。默认配置见 `ff7-ime.custom.yaml`。

### 4.1 候选与注释

```yaml
patch:
  ff7-ime/top_n: 9
  menu/page_size: 9
  ff7-ime/show_comment: true
  ff7-ime/show_score: false      # 调试时打开，注释显示分数
```

### 4.2 模糊音开关

| 配置 | 默认 | 说明 |
|---|---|---|
| `ff7-ime/fuzzy/zh_z` | true | zh→z |
| `ff7-ime/fuzzy/ch_c` | true | ch→c |
| `ff7-ime/fuzzy/sh_s` | true | sh→s |
| `ff7-ime/fuzzy/ng_n` | true | ng→n |
| `ff7-ime/fuzzy/n_l` | false | n→l（音节首） |
| `ff7-ime/fuzzy/r_l` | false | r→l |
| `ff7-ime/fuzzy/f_h` | false | f→h |
| `ff7-ime/fuzzy/en_eng` | false | eng→en |
| `ff7-ime/fuzzy/in_ing` | false | ing→in |
| `ff7-ime/fuzzy/an_ang` | false | ang→an |
| `ff7-ime/fuzzy/uan_uang` | false | uang→uan |
| `ff7-ime/fuzzy/v_u` | true | v/u 互通 |

示例：

```yaml
patch:
  ff7-ime/fuzzy/n_l: true
  ff7-ime/fuzzy/ng_n: false
```

### 4.3 容错

```yaml
patch:
  ff7-ime/typo/enabled: true
  ff7-ime/typo/max_edit: 2        # 0–4
  ff7-ime/typo/transposition: true
  ff7-ime/typo/syllable_swap: true
```

- `typo/enabled: false` 进入**严格模式**：只允许精确/模糊整音节，不允许漏/多/前缀/编辑距离/换位。
  - `lienuo` 不再匹配雷诺；
  - `senguilon` 仍可匹配圣柜龙（纯 ng→n 模糊）。

### 4.4 声母/关键词

```yaml
patch:
  ff7-ime/initial/enabled: true
  ff7-ime/keyword/gap_penalty: 0.02
  ff7-ime/keyword/syllable_subsequence: true
```

- `initial/enabled: false`：`lkcc`、`wmhlkcdccnm` 等不再命中，只保留全拼/前缀/模糊/容错；
- `keyword/syllable_subsequence: false`：关闭 `meishao` 这类中段音节前缀关键词，只保留声母子序列。

### 4.5 性能

```yaml
patch:
  ff7-ime/dp_max_candidates: 56   # 8–500；越小越快，越大召回越稳
  # 回退与置信度
  ff7-ime/fallback/use_lcs: true
  ff7-ime/fallback/dp_min_raw: 0.65
  ff7-ime/fallback/strong_raw: 0.70
  ff7-ime/fallback/fast_max_candidates: 16
  ff7-ime/fallback/max_candidates: 96
```

- 精确/前缀输入不跑 DP，通常 5–10 ms/键；
- 长模糊/容错输入最坏约 65 ms/键；
- 卡顿时优先降到 40/32，或关闭 `n_l`、`r_l`、`f_h`；
- `fallback/dp_min_raw` 控制 DP 最低置信度，低于它的近似对齐会被丢弃；
- `fallback/strong_raw` 以上视为强命中，只用 `fast_max_candidates` 个小池补位；
- `fallback/max_candidates` 是无强命中时的回退池上限。

### 4.6 通道权重（高级）

```yaml
patch:
  ff7-ime/weights/exact: 1.0
  ff7-ime/weights/fuzzy: 0.97
  ff7-ime/weights/fuzzy_prefix: 0.95
  ff7-ime/weights/prefix: 0.96
  ff7-ime/weights/swap: 0.93
  ff7-ime/weights/dp: 0.94
  ff7-ime/weights/initial_exact: 0.96
  ff7-ime/weights/initial: 0.86
  ff7-ime/weights/keyword: 0.80
  ff7-ime/weights/fallback: 0.55
```

- `exact` 是唯一可到 1.0 的通道；
- 调高 `keyword` 会让声母关键词和中段音节前缀关键词都更激进；调低 `dp` 会减少容错候选。
- 一般不建议修改，除非有明确偏好。

### 4.7 F4 开关 vs 配置文件

- 默认 `ff7-ime/use_switches: false`：**以 `*.custom.yaml` 的 `ff7-ime/fuzzy/*` 等配置为准**；
- 改为 `true`：F4 菜单中的 `ff7-ime_fuzzy_*`、`ff7-ime_initial`、`ff7-ime_typo` 开关优先，custom 中对应配置被忽略；
- 如果既想用 F4，又想保留配置默认值，可把 `use_switches: true` 并在 schema 的 switches `reset` 中设置默认。

> **不要**在 `*.custom.yaml` 中按名字 patch switches（如 `switches/@fuzzy_zh_z/reset`），Rime 会把它解析成数字索引 0，改错 `ascii_mode`。要 patch 请用数字索引 `switches/@<数字>/reset`。

### 4.8 预编辑显示

schema 内已设置 `style/inline_preedit: true`，Weasel 会把预编辑串直接画在输入框里（不需要改 `weasel.custom.yaml`）；同时会预测音节边界：

| 输入 | 预编辑 |
|---|---|
| `diou` | `di'ou` |
| `shenluo` | `shen'luo` |
| `meishao` | `mei'shao` |
| `shenl`（未打完） | `shen'l` |
| `nd`（声母缩写） | `n'd` |
| `lkcc`（声母缩写） | `l'k'c'c` |

配置：

```yaml
patch:
  ff7-ime/preedit/enabled: true      # false: 不预测分隔符，仍显示原始输入
  ff7-ime/preedit/separator: "'"     # 改成 " " 即显示为 di ou
  style/inline_preedit: true      # false: 回到候选窗口内显示预编辑
```

分词只影响显示，上屏文本仍是词条原文。

---

## 5. 候选选择与提交

- 数字键 1–9 选择当前页候选；
- 空格、回车、小键盘回车提交高亮候选；
- `-`/`=` 或 `,`/`.` 翻页（取决于 `key_binder` 预设）；
- 提交文本就是词条原文（含标点）；不会追加拼音或注释；
- 预编辑显示预测音节（`diou` → `di'ou`），仅用于提示，不进入上屏文本；
- 本方案没有用户词频/自造词；同一输入每次候选顺序稳定。

---

## 6. 常见问题

### 6.1 为什么 `zzzzzz` 也有候选？

需求要求“永远给出 N 个”，因此无匹配时按共享 bigram/trigram 召回，再用
Damerau + Dice-LCS 排序；只有回退池为空才用静态优先序兜底。它们不代表
真实匹配，只是保证不空输出。`zzzzzz` 现在会优先给出含 `z` 的词条，而不是
固定的静态前 9 条。

### 6.2 为什么 `lkcc` 有时不是第一？

- 若词库中存在另一个词的原始声母正好是 `lkcc`，它会以 `initial_exact`（0.96）排在关键词（0.80/0.90）之前；
- 若输入被判定为非缩写模式（例如含较多元音），关键词权重会降低；
- 可调高 `ff7-ime/weights/keyword` 或检查 `ff7-ime/initial/enabled`。

### 6.3 为什么某些生僻字读法不对？

数据由 pypinyin + luna_pinyin + 人工覆盖生成。若某译名/生僻字读音有争议：

1. 编辑 `experiments/pinyin-data/override.yaml` 的 `confirmed_phrases` / `char_rules` / `char_defaults` / `misread_candidates`；
2. 重新生成 `phrases.tsv`（或直接改 `data/phrases.json`）；
3. 运行 `python tools/build_from_pinyin_data.py`；
4. 复制 `lua/ff7-ime_data.lua` 到 `%APPDATA%\Rime\lua\` 并重新部署。

### 6.4 如何只输出某个词条？

本方案只输出 `data/dict.txt` 的 1212 条，不能临时添加词库外内容。要增删词条，修改 `data/dict.txt` 后重新构建（见 `docs/BUILD.md`）。

### 6.5 如何关闭某类容错？

- 关闭全部容错：`ff7-ime/typo/enabled: false`；
- 只关闭音节换位：`ff7-ime/typo/syllable_swap: false`；
- 只关闭声母/关键词：`ff7-ime/initial/enabled: false`；
- 只关闭某模糊音：`ff7-ime/fuzzy/<name>: false`。

---

## 7. 输入法状态

- 方案不修改系统输入法默认值；安装包只把方案加入 `schema_list`。
- 切换回 `luna_pinyin_simp`：F4 / Ctrl+`。
- 若系统默认输入法被临时改为小狼毫，可在 Windows 设置 → 时间和语言 → 语言 → 中文 → 选项 → 键盘 中调整，或 `Win+Space` 切换。
