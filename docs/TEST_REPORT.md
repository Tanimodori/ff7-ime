# 测试报告

> 测试对象：魔光键影 1.0.0
> 环境：Windows 10 19045 x64；小狼毫 Weasel 0.17.4；librime 1.13.1；内嵌 Lua 5.4.7；Python 3.14.7；Node 24.21；wasmoon Lua 5.4。
> 说明：按用户要求，本轮**跳过独立子代理验收步骤**；以下为实现者自动化测试与真机 GUI 实测记录。

---

## 1. 数据验收

| 指标 | 结果 |
|---|---:|
| `data/dict.txt` 有效词条 | 1212 |
| `data/phrases.json` / `ff7-ime_data.lua` 词条 | 1212 |
| 重复词条 | 0 |
| 汉字总出现 | 5560 |
| 唯一汉字 | 1326 |
| 语料内多音字（实际出现多读） | 28 |
| pypinyin 多音字 | 576 |
| 人工覆盖字 / 实际改动词条 | 23 / 48 |
| 整词人工确认 | 62 |
| luna 未解决读音冲突 | 0（1 处已知漏收：缪 miù，已人工覆盖） |
| 生僻字缺失 | 0 |
| 标点种类 / 出现次数 | 6 / 127 |

关键读音抽查（均已确认）：

```
曾 zeng          长杖/长靴/长矛/月长石 chang
重拾 chong       之都 du          我得/得活着 dei
不得了 liao      弹跳 tan         劲歌 jing
华勒斯/盖恩斯伯勒 le              巴拔维拉缪 miu
吉尔伽美什 jia/shi                琪里耶 ye
蒂法 di          克劳德 ke/lao/de  爱丽丝 ai/li/si
萨菲罗斯 sa/fei/luo/si            扎克斯 zha
雷诺 lei/nuo     路德 lu/de        五台 wu/tai
宝条 bao/tiao    陆行鸟 lu/xing/niao
都市 du          航空 hang         血祭 xue/ji
梣木 cen（允许 qin/chen 误读）     骰子 tou（允许 shai）
第陆区 liu       刽子手 gui/zi/shou
```

最终数据规模：

```
phrases=1212
alt-slots=586
full-variants=1973
init-variants=1543
ff7-ime_data.lua = 416 KB
data/phrases.json = 646 KB
```

---

## 2. 核心需求用例

`tests/lua/run_cases.js`（wasmoon，最终数据）：

| 输入 | 期望 top1 | 实际 |
|---|---|---|
| `shenluo` | 神罗 | ✅ |
| `senluo` | 神罗 | ✅ |
| `diou` | 迪欧 | ✅ |
| `leinuo` | 雷诺 | ✅ |
| `lienuo` | 雷诺 | ✅ |
| `leino` | 雷诺 | ✅ |
| `leiknuo` | 雷诺 | ✅ |
| `nuolei` | 雷诺 | ✅ |
| `lkcc` | 我们会立刻彻底铲除你们！ | ✅ |
| `wmhlkcdccnm` | 我们会立刻彻底铲除你们！ | ✅ |
| `shenl` | 神罗 | ✅ |
| `zhongli` | 重力 | ✅ |
| `chongli` | 重力 | ✅ |
| `zeng` | 曾 | ✅ |
| `ceng` | 曾 | ✅ |
| `renshengjiushizhandou` | 人生就是战斗！ | ✅ |
| `difa` | 蒂法 | ✅ |
| `kelaode` | 克劳德 | ✅ |
| `safeiluosi` | 萨菲罗斯 | ✅ |
| `meishao` | 有时是出手相助的美少女忍者！ | ✅ |
| `meishaonv` | 有时是出手相助的美少女忍者！ | ✅ |
| `meishaonvrenzhe` | 有时是出手相助的美少女忍者！ | ✅ |
| `chushou` | 有时是出手相助的美少女忍者！ | ✅ |
| `shouxiang` | 有时是出手相助的美少女忍者！（top3） | ✅ |
| `zhiwen` | 少女之吻（top3） | ✅ |
| `aan` | 阿尼安·库尼昂（top5） | ✅ |
| `keye` | 凯泽尔科亚特尔（top5） | ✅ |
| `zzzzzz` | 非空 9 候选，且无 DP | ✅ |
| 空输入 | 非空 9 候选 | ✅ |
| `a` | 非空 9 候选 | ✅ |
| `fagnge` | 芳格（DP 通道） | ✅ |
| `fangge` | 芳格 | ✅ |
| `asdfghjkl` | 非空 9 候选，且无 DP | ✅ |
| `qwxz` | 非空 9 候选，且无 DP | ✅ |
| `mina` | 蜜娜 | ✅ |
| `mian` | 双面相 | ✅ |

结果：**40/40 通过**。新增用例同时锁定：
- DP 置信度门槛（`asdfghjkl`/`qwxz`/`zzzzzz` 不得出现 `dp` 候选）；
- fallback 不再按静态顺序补位；
- `fagnge` 这类相邻字母换位仍由 DP 命中；
- `mina`/`mian` 是合法输入，不能被“减少音节数”的 swap 规则改写。

同一批用例中的预编辑断言（节选）：

| 输入 | 期望 preedit | 实际 |
|---|---|---|
| `diou` | `di'ou` | ✅ |
| `shenluo` | `shen'luo` | ✅ |
| `senluo` | `sen'luo` | ✅ |
| `meishao` | `mei'shao` | ✅ |
| `shenl`（未打完） | `shen'l` | ✅ |
| `aan` | `a'an` | ✅ |
| `lkcc`（首字母） | `lkcc` | ✅ |

---

## 3. 全量自动评估

`tools/gen_eval_cases.py` + `tests/lua/bulk_eval.js`（wasmoon，`dp_max_candidates=56`）：

| 类别 | 用例 | 通过标准 | 通过 | top1 率 | 平均耗时 |
|---|---:|---|---:|---:|---:|
| exact | 1212 | top1 | **1212/1212（100%）** | 100% | 1.5 ms |
| fuzzy | 878 | top1 | **878/878（100%）** | 100% | 34.9 ms |
| initial | 1212 | top1 或 top3 | **1212/1212（100%）** | 98.3% | 5.3 ms |
| typo | 600 | top3 | **600/600（100%）** | 99.7% | 53.5 ms |
| keyword | 238 | top5 | **233/238（97.9%）** | 76.1% | 5.9 ms |
| mid_keyword | 300 | top5 | **300/300（100%）** | 91.0% | 26.5 ms |
| fallback | 7 | 返回 N | **7/7（100%）** | — | 4.0 ms |

### 3.1 keyword 的 5 个失败

均为极稀疏声母子序列的天然歧义，例如：

```
mlh   → 墨绿海马（短/紧凑） vs 莫古力召唤术（长/稀疏）
lds   → 神罗大厦 vs 里维·杜耶斯提
slsh  → 神罗手镯 vs 赛特拉护身符
dzhsh → 盗贼护手 vs 道路之星手镯
mgj   → 猫咪攻击 vs 迷你古兰迦兰
```

需求示例 `lkcc`、`wmhlkcdccnm`、`jdzhyo`、`adbym`、`asbnl` 均为 top1。该限制已写入 README/USAGE。

### 3.2 mid_keyword 的 300 例

覆盖长句中段**唯一出现**的 2–3 音节串，例如 `meishao`、`chushou`、
`shouxiang`。生成器排除了另一词条的全拼前缀、精确全拼和跨词条共享
的音节串，避免把天然歧义算成失败。结果：**300/300 进 top5，top1 91.0%**。

### 3.3 initial 的 top1 非 100%

20 组声母完全相同的词条（如 `ml` = 玛琳/玛蕾，`fl` = 菲拉/芙兰，`qd` = 强盗/祈祷）无法仅靠声母区分；方案把它们都放进 top3，通过标准为 top1 或 top3，全部通过。

### 3.4 fallback 与 DP 置信度

改造前 `fill_static` 按 `static_top` 的固定顺序取前 N 个，`fallback_score`
只在这个任意池内排序；例如 `zzzzzz` 会返回“曾/乔/神罗/…”这类与输入
无关的静态前排。改造后：

| 输入 | 旧行为 | 新行为 |
|---|---|---|
| `zzzzzz` | 曾/乔/神罗/…（静态） | 刺针蜘蛛 等共享 `z` 的候选（fallback/neighbor） |
| `qwxz` | 乔/曾/杰西/…（静态） | 青蛙戒指 等（fallback/neighbor） |
| `asdfghjkl` | 魔法使徒 等 9 个 DP raw≈0.55 | 格拉斯兰 等回退候选；无 DP 候选 |
| `fangge` | 芳格 + 曾/蜜娜/玛琳/… | 芳格 + 防御长靴/反击射击/… |

DP 置信度门槛设为 `dp_min_raw=0.65`：全量评估中成功用例的 DP top1
raw 最低为 0.94（核心用例 `fagnge` 为 0.875），而长垃圾串的 DP raw 约
0.55，因此该门槛不会伤害现有召回，只丢弃低置信度的“硬凑”结果。

回退延迟通过“有强命中只做 16 个小池、无强命中才做 96 个”控制：
全量 wasmoon 评估中 exact 从 1.09→1.5 ms、fuzzy 36.7→34.9 ms、
keyword 5.3→5.9 ms，其余类别基本持平或略降。

---

## 4. 真实 Rime 集成

用 `experiments/rime-harness/rime_harness.py` 在临时 user dir 与真实 user dir 查询：

| 输入 | 真实 user dir top1 | 注释 |
|---|---|---|
| `shenluo` | 神罗 | 全拼 · shen luo |
| `senluo` | 神罗 | 模糊 · shen luo |
| `leinuo` | 雷诺 | 全拼 · lei nuo |
| `lienuo` | 雷诺 | 容错 · lei nuo |
| `leino` | 雷诺 | 容错 · lei nuo |
| `leiknuo` | 雷诺 | 容错 · lei nuo |
| `lkcc` | 我们会立刻彻底铲除你们！ | 关键词 · wo men hui li ke che di… |
| `wmhlkcdccnm` | 我们会立刻彻底铲除你们！ | 声母 · wo men hui li ke che di… |
| `zanguokuaigon` | 掌掴快攻 | 容错 · zhang guo kuai gong |
| `senguilon` | 圣柜龙 | 容错 · sheng gui long |
| `shuanganozhe` | 双脑者 | 容错 · shuang nao zhe |
| `meishao` | 有时是出手相助的美少女忍者！ | 关键词 · you shi shi chu shou xiang… |
| `meishaonv` | 有时是出手相助的美少女忍者！ | 关键词 · you shi shi chu shou xiang… |
| `chushou` | 有时是出手相助的美少女忍者！ | 关键词 · you shi shi chu shou xiang… |
| `shouxiang` | 有时是出手相助的美少女忍者！ | 关键词 · you shi shi chu shou xiang… |
| `fangge` | 芳格 | 全拼 · fang ge；后续为回退候选 |
| `fagnge` | 芳格 | 容错 · fang ge（preedit `fagnge`） |
| `zzzzzz` | 刺针蜘蛛 | 回退 · ci zhen zhi zhu |
| `qwxz` | 青蛙戒指 | 回退 · qing wa jie zhi |
| `asdfghjkl` | 格拉斯兰 | 回退 · ge la si lan；无容错候选 |
| `mina` | 蜜娜 | 全拼 · mi na（preedit `mi'na`） |
| `mian` | 双面相 | 关键词 · shuang mian xiang |

候选顺序、注释、Top-N（9）均正确。`fagnge`、`fangge`、`zzzzzz`、`qwxz`、
`asdfghjkl`、`meishao` 的 preedit 分别为 `fagnge`、`fang'ge`、`zzzzzz`、
`qwxz`、`asdfghjkl`、`mei'shao`；`asdfghjkl`/`qwxz`/`zzzzzz` 的候选注释中
不再出现“容错”，说明 DP 置信度门槛生效。

### 4.1 提交与键绑定回归（真实 librime）

| 操作 | 提交 | 结果 |
|---|---|---|
| `fagnge` + 选择候选 0 | 芳格 | ✅ |
| `fagnge{Return}` | 芳格 | ✅ |
| `fagnge{KP_Enter}` | 芳格 | ✅ |
| `meishao{Return}` | 有时是出手相助的美少女忍者！ | ✅ |

---

## 5. GUI 实测

环境：Windows 10 记事本；小狼毫设为默认输入法；逐键输入。

| 输入 | 提交/显示 | 结果 |
|---|---|---|
| `lkcc` | 我们会立刻彻底铲除你们！ | ✅ |
| `lienuo` | 雷诺 | ✅ |
| `senluo` | 神罗 | ✅ |
| `zanguokuaigon` | 掌掴快攻 | ✅ |
| `renshengjiushizhandou` | 人生就是战斗！ | ✅（标点保留） |
| `diou` | 输入框内显示 `di'ou`；回车提交 迪欧 | ✅ |
| `meishao` | 输入框内显示 `mei'shao`；回车提交 有时是出手相助的美少女忍者！ | ✅ |
| `shenluo` | 小键盘回车提交 神罗 | ✅ |

> 内嵌预编辑通过全屏截图确认（`di'ou`/`mei'shao` 直接显示在记事本文本区，候选窗口同时出现）；提交文本通过记事本文本框 Accessibility `value` 确认。`style/inline_preedit: true` 由 schema 提供，Weasel 从 schema 读取，未修改 `weasel.custom.yaml`。测试后已关闭测试窗口并把系统默认输入法恢复为微软拼音。
>
> 本轮 fallback/DP 置信度改动不影响输入框绘制；新增行为用真实 librime 键序列验证（见 §4.1），未重复 GUI 截图。

---

## 6. 配置与开关实测

| 配置 | 输入 | 结果 |
|---|---|---|
| `ff7-ime/top_n: 12` + `menu/page_size: 12` | `shenluo` | 12 个候选 ✅ |
| `ff7-ime/show_comment: false` | `shenluo` | 注释为空 ✅ |
| `ff7-ime/typo/enabled: false` | `lienuo` | 不再命中雷诺（回退 神罗）✅ |
| `ff7-ime/initial/enabled: false` | `lkcc` | 不再命中长句（回退 曾）✅ |
| `ff7-ime/fuzzy/ng_n: false` + `typo: false` | `senguilon` | 不再命中圣柜龙（回退 神罗）✅ |
| `use_switches: true` + `ff7-ime_fuzzy_ng_n=false` + `ff7-ime_typo=false` | `senguilon` | 神秘龙（回退）✅ |
| 同上，开关打开 | `senguilon` | 圣柜龙 ✅ |
| `ff7-ime/preedit/enabled: false` | `diou` | preedit=`diou` ✅ |
| `ff7-ime/preedit/separator: " "` | `diou` | preedit=`di ou` ✅ |

说明：`typo.enabled=false` 为严格模式，只允许精确/模糊整音节；`senguilon` 仍可命中圣柜龙，因为 `ng→n` 属模糊而非 typo。

---

## 7. 共存与部署

- 真实 user dir：
  - `default.custom.yaml` 的 `schema_list` 同时含 `luna_pinyin_simp`、`ff7-ime`；
  - `build/default.yaml` 同时含两者；
  - `build/ff7-ime.schema.yaml` 存在；
  - `luna_pinyin_simp` 输入 `nihao` → 你好（前 5 候选：你好/妳好/逆号/拟好/你）。
- 官方安装器：
  - `recipe.yaml` 只安装 `ff7-ime.schema.yaml` 与 `lua/ff7-ime*.lua` 共 4 个文件；
  - 安装器不改写 `default.custom.yaml`，方案启用由“方案选单设定”的勾选完成；
  - 用 `rime_harness.py` 直接查真实 user dir 时必须加 `--no-write-custom`；否则 harness 默认会把 `default.custom.yaml` 重写成只含当前 schema。
- 包校验与 Plum 安装：
  - `python tools/check_package.py` 通过，安装清单恰好 4 个运行时文件；
  - 发布前用本地克隆模拟 Plum 安装，用户目录只出现 schema + 3 个 Lua，没有 custom、`data/dict.txt`、tests；
  - 发布后用官方 `rime-install.bat` 从 `https://github.com/Tanimodori/ff7-ime.git` 克隆：
    输出 `Downloading package` → `Installing recipe: Tanimodori/ff7-ime`，安装 1 个包；
  - **缺失文件重装实测**：删除用户目录中的 4 个运行时文件后重跑官方 `rime-install.bat`，
    输出 4 个 `Installing:`，文件全部恢复；安装文件 SHA-256 与公开仓库 clone 一致
    （本地工作树的 LF 与安装文件的 CRLF 仅为行尾差异，去掉 `\r` 后逐字节相同）；
  - 安装器执行前后 `default.custom.yaml` 的 SHA-256 一致，确认安装器未改写方案列表；
  - Plum 缓存 origin 为 `https://github.com/Tanimodori/ff7-ime.git`，更新后停在 `b3effcf`。
- 本机旧安装迁移：
  - 旧 `moguang_jianying.schema.yaml`、旧 custom、旧 `lua/mgjy*.lua` 和旧 build 产物已备份后删除；
  - `default.custom.yaml` 现在为 `luna_pinyin_simp` + `ff7-ime`；
  - 新 schema 由 Plum 安装，`build/ff7-ime.schema.yaml` 存在；
  - 真实 librime 查询：`shenluo`→神罗、`senluo`→神罗、`fagnge`→芳格、
    `meishao`→长句、`lkcc`→长句、`asdfghjkl`→格拉斯兰、`nuolei`→雷诺；
    `diou` 预编辑为 `di'ou`；
  - `luna_pinyin_simp` 输入 `nihao` 仍得到“你好”。

---

## 8. 原生逐键性能

测量：真实 `rime.dll`、真实 Lua 5.4、单会话逐键 `RimeProcessKey`；`dp_max_candidates=56`。

| 输入 | 总耗时 | 单键最大 | 单键平均 |
|---|---:|---:|---:|
| `shenluo`（精确） | 40.7 ms | 10.6 ms | 5.8 ms |
| `lkcc`（关键词） | 16.9 ms | 5.6 ms | 4.2 ms |
| `wmhlkcdccnm`（全声母） | 69.5 ms | 8.1 ms | 6.3 ms |
| `lienuo`（换位） | 60.2 ms | 19.2 ms | 10.0 ms |
| `leiknuo`（多字） | 68.0 ms | 20.7 ms | 9.7 ms |
| `dhenluo`（首字母错） | 82.5 ms | 27.1 ms | 11.8 ms |
| `senguilon`（ng 模糊） | 124.3 ms | 35.7 ms | 13.8 ms |
| `zanguokuaigon`（长模糊） | 294.7 ms | 64.9 ms | 22.7 ms |
| `shuanganozhe`（音节内换位） | 244.2 ms | 45.3 ms | 20.3 ms |
| `meishao`（中段关键词，7 键） | 61.4 ms | 23.3 ms | 8.8 ms |
| `shouxiang`（中段关键词，9 键） | 141.2 ms | 40.7 ms | 15.7 ms |
| `renshengjiushizhandou`（20 键精确） | 86.9 ms | 11.8 ms | 4.1 ms |
| `fagnge`（换位/模糊） | 38.8 ms | 13.8 ms | 6.5 ms |
| `zzzzzz`（回退） | 31.7 ms | 8.2 ms | 5.3 ms |
| `asdfghjkl`（回退） | 69.8 ms | 11.2 ms | 7.8 ms |

结论：精确/前缀输入流畅（约 5–6 ms/键）；长模糊/容错输入最坏约
65 ms/键，中段关键词约 9–16 ms/键，仍在目标（单键 <50–100 ms）内。
回退改动没有改变 DP 短名单大小；如仍卡顿，可调 `dp_max_candidates`
或 `fallback/max_candidates`。

---

## 9. 已知限制

1. keyword 极稀疏子序列存在天然歧义（5/238 未进 top5）；`lkcc` 等需求示例稳定。
2. 中段共享音节串（如“是我的”“护身符”）存在天然歧义；`mid_keyword` 评测只使用唯一出现的 2–3 音节串。
3. 只输出 1212 条，词库外输入仅做 n-gram + Damerau/Dice-LCS 回退；回退候选只保证表面字母相关，不保证语义相关。
4. 安装源是整仓 Plum 包：用户浅克隆整个仓库（约 7 MB，含 tests/experiments/docs），需要公开仓库 + Git Bash；Weasel 0.17.4 的本地 ZIP 路径不复制 `lua/`。
5. 安装器不改 `default.custom.yaml`；启用方案靠官方“方案选单设定”的勾选，避免与 luna 等方案冲突。
6. 数据读音为工程化整理，争议读音需改 `override.yaml` 后重建。
7. 20 组声母完全相同的词条，top1 无法仅靠声母唯一确定；Top-3 内均包含。

---

## 10. 复现命令

```bash
cd "D:/Tanimodori/Projects/@FF14/ff7-ime"

# 数据与核心
python tools/build_from_pinyin_data.py
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/run_cases.js tests/lua/core_cases.json lua/ff7-ime_data.lua

# 全量评估
python tools/gen_eval_cases.py
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" node tests/lua/bulk_eval.js

# 包校验
python tools/check_package.py

# 真实 Rime
cd experiments/rime-harness
python rime_harness.py \
  --shared "C:\Program Files\Rime\weasel-0.17.4\data" \
  --user "%TEMP%\ff7-ime-test" \
  --schema ff7-ime --input lkcc --deploy always --json
```
