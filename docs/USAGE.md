# 使用说明

---

## 1. 基本输入

- 方案切换：**F4** 或 **Ctrl+`**，选择 **魔光键影**。
- 输入法：中国大陆普通话**无调全拼**，不需要输入声调。
- 候选：默认每页 9 个；候选菜单展开时数字键 1–9 选择；空格、回车或小键盘回车
  提交高亮候选；`-`/`=` 或 `,`/`.` 翻页（只翻页，不会输入符号）。
- 按键过滤：本方案只接受拼音字母和音节分隔符 `'`。数字、标点、符号以及没有候选
  时的空格会被吞掉，不会透传给游戏；需要输入这些字符时切换到 `luna_pinyin_simp`。
- 预编辑：输入框内显示预测的音节分隔符（`diou` → `di'ou`，`shenl` → `shen'l`，
  `nd` → `n'd`）；只影响显示，不影响上屏文本。
- 中英切换：本方案禁用 Shift 中英切换（`Shift_L`/`Shift_R` 均为 `noop`）。
  按 Shift 不会进入英文模式，Shift 会透传给游戏；需要英文时切换到
  `luna_pinyin_simp`。
- 只输出 `data/dict.txt` 的 1212 条词条；不会出现词库外候选、造句或用户新词。
- 候选右侧显示注释：`通道 · 主拼音`，例如：
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
  - `zhongli` / `chongli` → 重力
  - `changzhang` / `zhangzhang` → 魔法长杖（长杖系词条）
  - `hangkong` → 野马航空
  - `deihuozhe...` → 得活着才能是塔克斯
- 允许误读（权重低于规范读音）：
  - `qinmu` / `cenmu` → 梣木
  - `ceng` / `zeng` → 曾
  - `xueji` / `xieji` → 血祭
  - `touzi` / `shaizi` → 骰子
  - `ludei` → 路德（“德”的允许误读）

### 2.4 全声母

输入每个音节的声母，`zh/ch/sh` 可写全或只写首字母：

| 输入 | 候选 |
|---|---|
| `wmhlkcdccnm` | 我们会立刻彻底铲除你们！ |
| `sl` | 神罗 |
| `chm` | 沉默（原始声母串精确） |
| `hshkyq` | 回声扩音器（原始声母串精确） |

### 2.5 关键词缩写

声母的稀疏子序列，适合长句缩写：

| 输入 | 候选 |
|---|---|
| `lkcc` | 我们会立刻彻底铲除你们！ |
| `jdzhyo` | 就是大家最喜欢的尤菲哦！ |
| `adbym` | 肮脏的鼠辈，欢迎你们！ |

> 极稀疏缩写可能存在歧义（例如 `mlh` 同时像“墨绿海马”和“莫古力召唤术”）；
> 方案保证返回 N 个候选，但不保证 top1 一定是您心中那一条。

混合缩写：前段写若干声母，末尾写完整音节，中间可以跳过音节：

| 输入 | 候选 |
|---|---|
| `shbi` | 金属护臂、水手护臂、司令护臂 … |

`shbi` 可拆成 `s`(hou) + `h`(u) + `bi`，因此能命中“水手护臂”；
同样的缩写也会命中所有结构相同的词条，所以“金属护臂”等可能排在前面。

### 2.6 中段关键词

输入可以匹配词条**中段**的连续音节前缀，不需要从词条开头输入：

| 输入 | 候选 |
|---|---|
| `meishao` | 有时是出手相助的美少女忍者！ |
| `meishaonv` | 有时是出手相助的美少女忍者！ |
| `shouxiang` | 有时是出手相助的美少女忍者！ |
| `chushou` | 有时是出手相助的美少女忍者！ |

规则：

- 输入块必须是某个音节读音的前缀，例如 `mei` + `shao`；
- 允许跳过中间音节，因此关键词可以出现在词条中段；
- 如果输入同时是另一个词条的全拼前缀，前缀候选仍然优先。例如 `zhiwen`
  会先给 `直纹叶翼蜥`，`少女之吻` 排在其后；
- 可用 `ff7-ime/keyword/syllable_subsequence: false` 关闭，只保留声母子序列。

### 2.7 部分输入

| 输入 | 候选 |
|---|---|
| `shen` | 神罗等以 `shen` 开头的候选 |
| `shenl` | 神罗 / 神罗兵 / 神罗大厦 … |
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
| `zouleixinlaide` | 走了，新来的！ |
| `hexihexi` | 呵嘻，呵嘻！ |
| `shuangrenshizhinazhongshuangrenma` | 双人……是指那种双人吗？ |
| `difaluokehate` | 蒂法·洛克哈特 |

---

## 3. 候选与 Top-N

- 每次按键都会重新计算并给出 **N 个候选**（默认 9）。
- N 可在 `ff7-ime/top_n` 修改；`menu/page_size` 建议与 N 相同（或更小，用翻页）。
- 即使输入乱码、单字母或空串，也不会空输出：
  - 无匹配时按字面相似度召回候选；
  - 空输入按词条权重、长度和词典序取前 N。
- 精确全拼永远 top1；同分时按通道优先级、短词、词条权重、词典序排序。
- 本方案没有用户词频或自造词，同一输入每次候选顺序稳定。

---

## 4. 配置

编辑 `%APPDATA%\Rime\ff7-ime.custom.yaml`，修改后重新部署。默认配置见
仓库根目录的 `ff7-ime.custom.yaml`。

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

- `typo/enabled: false` 进入**严格模式**：只允许精确/模糊整音节，不允许漏、多、
  前缀、编辑距离或换位。
  - `lienuo` 不再匹配雷诺；
  - `senguilon` 仍可匹配圣柜龙（纯 ng→n 模糊）。

### 4.4 声母/关键词

```yaml
patch:
  ff7-ime/initial/enabled: true
  ff7-ime/keyword/gap_penalty: 0.02
  ff7-ime/keyword/syllable_subsequence: true
```

- `initial/enabled: false`：`lkcc`、`wmhlkcdccnm` 等不再命中，只保留
  全拼、前缀、模糊和容错；
- `keyword/syllable_subsequence: false`：关闭 `meishao` 这类中段音节前缀关键词
  和 `shbi` 这类混合缩写，只保留声母子序列。

### 4.5 性能

```yaml
patch:
  ff7-ime/dp_max_candidates: 56   # 8–500；越小越快，越大召回越稳
  ff7-ime/fallback/use_lcs: true
  ff7-ime/fallback/dp_min_raw: 0.65
  ff7-ime/fallback/strong_raw: 0.70
  ff7-ime/fallback/fast_max_candidates: 16
  ff7-ime/fallback/max_candidates: 96
```

- 精确/前缀输入不进行完整对齐，通常响应很快；
- 长模糊/容错输入计算量较大，若感觉卡顿，优先把 `dp_max_candidates`
  降到 40 或 32，或关闭 `n_l`、`r_l`、`f_h`；
- `fallback/dp_min_raw` 控制近似对齐的最低置信度；
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
- 调高 `keyword` 会让关键词匹配更激进；调低 `dp` 会减少容错候选；
- 一般不建议修改，除非有明确偏好。

### 4.7 F4 开关与配置文件

- 默认 `ff7-ime/use_switches: false`：以 `*.custom.yaml` 的 `ff7-ime/fuzzy/*`
  等配置为准；
- 改为 `true`：F4 菜单中的 `ff7-ime_fuzzy_*`、`ff7-ime_initial`、`ff7-ime_typo`
  开关优先，custom 中对应配置被忽略；
- 如果既想用 F4，又想保留配置默认值，可把 `use_switches: true` 并在 schema
  的 switches `reset` 中设置默认。

> **不要**在 `*.custom.yaml` 中按名字 patch switches（如
> `switches/@fuzzy_zh_z/reset`），Rime 会把它解析成数字索引 0，改错
> `ascii_mode`。要 patch 请用数字索引 `switches/@<数字>/reset`。

### 4.8 预编辑显示

schema 内已设置 `style/inline_preedit: true`，Weasel 会把预编辑串直接画进
输入框（不需要改 `weasel.custom.yaml`）；同时会预测音节边界：

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
  style/inline_preedit: true         # false: 回到候选窗口内显示预编辑
```

分词只影响显示，上屏文本仍是词条原文。

---

## 5. 候选选择与提交

- 候选菜单展开时，数字键 1–9 选择当前页候选；
- 空格、回车、小键盘回车提交高亮候选；
- `-`/`=` 或 `,`/`.` 翻页（取决于 `key_binder` 预设），不会输入符号；
- 没有展开候选时，数字、标点、符号和空格都会被吞掉；
- 提交文本就是词条原文（含标点），不会追加拼音或注释；
- 预编辑仅用于提示，不进入上屏文本；
- 本方案没有用户词频或自造词，同一输入每次候选顺序稳定。

---

## 6. 常见问题

### 6.1 为什么 `zzzzzz` 也有候选？

本方案对任何输入都返回 N 个候选。无匹配时按字面相似度召回，只有回退池为空
才用静态优先序兜底；这些候选不代表真实匹配，只是保证不空输出。

### 6.2 为什么 `lkcc` 有时不是第一？

- 若词库中存在另一个词的原始声母正好是 `lkcc`，它会以精确声母排在关键词之前；
- 若输入含较多元音，关键词权重会降低；
- 可调高 `ff7-ime/weights/keyword` 或检查 `ff7-ime/initial/enabled`。

### 6.3 为什么某些生僻字读法不对？

数据由 pypinyin、luna_pinyin 与人工覆盖表整理。若某译名/生僻字读音有争议：

1. 编辑 `tools/pinyin-data/override.yaml` 的 `confirmed_phrases`、`char_rules`、
   `char_defaults` 或 `misread_candidates`；
2. 运行：

   ```bash
   python tools/pinyin-data/extract.py
   python tools/pinyin-data/extract.py --check
   python tools/build_from_pinyin_data.py
   ```

3. 复制 `lua/ff7-ime_data.lua` 到 `%APPDATA%\Rime\lua\` 并重新部署；
   或者直接双击安装包里的 `install.cmd`，它会把 5 个运行时文件对齐到发行版，
   只覆盖内容有变化的文件（旧文件会先备份）。

更完整的维护流程见 [MAINTENANCE.md](MAINTENANCE.md)。

### 6.4 如何增删词条？

本方案只输出 `data/dict.txt` 的 1212 条。修改 `data/dict.txt` 后按
[MAINTENANCE.md](MAINTENANCE.md) 重新生成注音与 Lua 数据，再部署。

### 6.5 为什么数字、标点或空格没有反应？

这是本方案的预期行为：`lua/ff7-ime_filter.lua` 只放行拼音字母和音节分隔符 `'`，
其余可打印字符会被吞掉，避免在游戏中误触菜单或输入符号。候选菜单展开时，
主键盘 1–9 仍然可以选词；需要输入数字、标点或空格时，切换到
`luna_pinyin_simp` 等其他方案。

### 6.6 如何关闭某类容错？

- 关闭全部容错：`ff7-ime/typo/enabled: false`；
- 只关闭音节换位：`ff7-ime/typo/syllable_swap: false`；
- 只关闭声母/关键词：`ff7-ime/initial/enabled: false`；
- 只关闭某模糊音：`ff7-ime/fuzzy/<name>: false`。

---

## 7. 输入法状态

- 方案不修改系统输入法默认值；是否加入 `schema_list` 由“方案选单设定”中的勾选决定，
  安装包本身不改写 `default.custom.yaml`。
- 切换回 `luna_pinyin_simp`：F4 / Ctrl+`。
- 若系统默认输入法被临时改为小狼毫，可在 Windows 设置 → 时间和语言 → 语言 →
  中文 → 选项 → 键盘 中调整，或 `Win+Space` 切换。
