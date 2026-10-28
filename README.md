# 魔光键影 · ff7-ime

> 面向 **小狼毫 Weasel 0.17.4（Windows x64，librime 1.13.1）** 的《最终幻想7》专属拼音输入方案。
> 输入中国大陆普通话无调全拼，**只输出 `data/dict.txt` 中的 1212 条词条**，并支持模糊音、多音字/允许误读、声母/关键词、漏错/换位容错，任何输入都给出 N 个候选。

![方案](https://img.shields.io/badge/Rime-Weasel%200.17.4-blue) ![Lua](https://img.shields.io/badge/Lua-5.4.7-green) ![词条](https://img.shields.io/badge/词条-1212-orange) ![许可](https://img.shields.io/badge/许可-MIT-green)

---

## 1. 特性

| 能力 | 说明 | 示例 |
|---|---|---|
| 固定词库 | 只输出 `data/dict.txt` 的 1212 条，不造句、不联想词库外内容 | `shenluo` → 神罗 |
| 精确全拼 | 无调全拼，`ü` 可写 `v` 或 `u` | `leinuo` → 雷诺 |
| 模糊音 | `zh/ch/sh→z/c/s`、`ng→n` 默认开启；`n/l`、`r/l`、`f/h`、`en/eng`、`in/ing` 等可配置 | `senluo` → 神罗 |
| 多音字/误读 | 语料内上下文多音 + 允许“有边读边”等误读，规范读音优先 | `chongli` → 重力；`qinmu` → 梣木 |
| 全声母 | 每个音节首字母 | `wmhlkcdccnm` → 我们会立刻彻底铲除你们！ |
| 关键词子序列 | 声母的稀疏子序列，长句可缩写 | `lkcc` → 我们会立刻彻底铲除你们！ |
| 中段关键词 | 词条中段的音节前缀子序列，可跳过前导音节 | `meishao` → 有时是出手相助的美少女忍者！ |
| 内嵌预编辑 | 输入框内实时显示预测音节分隔符，不影响上屏文本 | `diou` → `di'ou`；`meishao` → `mei'shao` |
| 部分输入 | 全拼前缀/不完整音节 | `shenl` → 神罗 |
| 漏/多/错/换位 | 漏字母、多字母、相邻换位、音节换位 | `lienuo` / `leino` / `leiknuo` / `nuolei` → 雷诺 |
| 永远 N 个 | 乱码、单字母、空输入也不空输出 | `zzzzzz` → 9 个候选 |
| 可配置 | 候选数、分页、注释、模糊开关、权重、DP 上限均在 YAML | `ff7-ime/top_n: 12` |

---

## 2. 快速安装

本项目是标准的 **Rime 包（Plum recipe）**，通过小狼毫自带的
**方案选单设定 → 获取更多输入方案** 安装，不使用自带安装脚本。

### 2.1 前置条件

- 小狼毫 Weasel 0.17.4 x64；
- Git for Windows（含 Git Bash）。官方安装器检测到 Git Bash 才会走 Plum；
  否则只会复制 YAML，不会复制 `lua/`。

### 2.2 安装步骤

1. 右键托盘图标 → **方案选单设定**；
2. 点击左下角 **获取更多输入方案…**；
3. 在控制台提示后输入安装标识：

   ```
   Tanimodori/ff7-ime
   ```

4. 看到 `Installing recipe: Tanimodori/ff7-ime` 与 4 个 `Installing:` 文件后关闭控制台；
5. 在自动刷新的方案列表里勾选 **魔光键影**，点击 **中**；
6. 若未立即生效，右键托盘 → **重新部署**。

安装器只复制 4 个运行时文件，不改写 `default.custom.yaml`，也不会覆盖用户自己的
`ff7-ime.custom.yaml`。详见 [docs/INSTALL.md](docs/INSTALL.md)。

> 安装标识就是 GitHub 仓库名。仓库必须公开；如果你 fork/改名，把
> `Tanimodori/ff7-ime` 换成你的 `用户名/仓库名`。

### 2.3 卸载

在方案选单设定中取消勾选“魔光键影”，然后删除用户目录中的
`ff7-ime.schema.yaml` 与 `lua/ff7-ime*.lua`，重新部署即可。

---

## 3. 使用

### 3.1 输入模式

| 模式 | 输入 | 结果 |
|---|---|---|
| 全拼 | `shenluo` | 神罗 |
| 模糊 | `senluo` | 神罗 |
| 多音/异读 | `chongli` | 重力（“重”的 chóng 读音） |
| 误读 | `qinmu` | 梣木（“梣”被读半边 qín） |
| 全声母 | `wmhlkcdccnm` | 我们会立刻彻底铲除你们！ |
| 关键词 | `lkcc` | 我们会立刻彻底铲除你们！ |
| 中段关键词 | `meishao` | 有时是出手相助的美少女忍者！ |
| 前缀 | `shenl` | 神罗 |
| 漏字母 | `leino` | 雷诺 |
| 相邻换位 | `lienuo` | 雷诺 |
| 多字母 | `leiknuo` | 雷诺 |
| 音节换位 | `nuolei` | 雷诺 |
| 含标点词条 | `renshengjiushizhandou` | 人生就是战斗！ |

候选窗口默认显示 9 个；注释显示命中通道与主拼音，例如 `全拼 · shen luo`、`关键词 · wo men hui ...`、`容错 · lei nuo`。若命中非主读音，会标注 `异读`。

### 3.2 常用配置

编辑 `%APPDATA%\Rime\ff7-ime.custom.yaml`，修改后重新部署（Weasel 托盘 → 重新部署，或在方案选单中确认）。

```yaml
patch:
  ff7-ime/top_n: 12              # 候选数量 N
  menu/page_size: 12          # 每页候选数
  ff7-ime/show_comment: true     # 是否显示注释
  ff7-ime/fuzzy/n_l: true        # 开启 n/l 模糊
  ff7-ime/fuzzy/ng_n: false      # 关闭 ng/n 模糊
  ff7-ime/typo/max_edit: 1       # 容错编辑距离上限
  ff7-ime/dp_max_candidates: 56  # 需要 DP 时的候选上限（性能/召回权衡）
  ff7-ime/fallback/dp_min_raw: 0.65  # DP 最低置信度；低于它不再作为强候选
```

完整配置项与 F4 开关说明见 [docs/USAGE.md](docs/USAGE.md)。

---

## 4. 项目结构

```
data/dict.txt                         原始词表（UTF-16 LE BOM，1212 条）
ff7-ime.schema.yaml                   Rime schema（根目录，Plum 安装）
ff7-ime.custom.yaml                   用户配置示例（根目录，不随包安装）
lua/
  ff7-ime.lua                         Rime translator 适配层（读配置/开关/yield）
  ff7-ime_matcher.lua                 纯 Lua 匹配/排序引擎
  ff7-ime_data.lua                    构建期生成的数据表（1212 条）
recipe.yaml                           Plum 安装清单（只装 schema + lua）
LICENSE                               MIT
tools/                                数据构建、包校验、测试脚本
tests/                                核心用例、全量评估、Lua 沙箱测试
experiments/                          研究/探针/中间产物（不参与运行时）
docs/                                 算法、架构、安装、使用、构建、维护、测试报告
PLAN.md                               总体方案与验收门
```

---

## 5. 测试结果（本机实测）

| 类别 | 用例数 | 通过标准 | 结果 |
|---|---:|---|---|
| 精确全拼 | 1212 | top1 | **1212/1212（100%）** |
| 模糊音 | 878 | top1 | **878/878（100%）** |
| 全声母/前缀 | 1212 | top1 或 top3 | **1212/1212（100%；top1 98.3%）** |
| 漏/多/换位 | 600 | top3 | **600/600（100%；top1 99.7%）** |
| 关键词稀疏子序列 | 238 | top5 | **233/238（97.9%；top1 76.1%）** |
| 中段关键词 | 300 | top5 | **300/300（100%；top1 91.0%）** |
| 乱码/单字母/空 | 7 | 返回 N | **7/7（100%）** |

核心需求用例：

```
shenluo             → 神罗（全拼）
senluo              → 神罗（模糊）
diou                → 迪欧（预编辑 di'ou）
leinuo / lienuo / leino / leiknuo / nuolei → 雷诺（全拼/漏/换位/多字/音节换位）
lkcc                → 我们会立刻彻底铲除你们！（关键词）
meishao             → 有时是出手相助的美少女忍者！（中段关键词，预编辑 mei'shao）
wmhlkcdccnm         → 我们会立刻彻底铲除你们！（全声母）
zanguokuaigon       → 掌掴快攻（跨音节 ng→n 模糊）
fagnge              → 芳格（音节内换位/模糊对齐）
renshengjiushizhandou → 人生就是战斗！（含标点）
zzzzzz              → 9 个共享 z 的回退候选（不再是固定静态前 9）
asdfghjkl           → 9 个回退候选，低分 DP 噪声被置信度门槛丢弃
```

核心 Lua 回归 40/40 通过，其中 19 条同时断言预编辑分词（`di'ou`、`shen'luo`、`mei'shao`、`shen'l`、`a'an` 等），并新增了 `fagnge`、fallback 候选池和 DP 置信度门槛的回归。

真实 Rime 逐键性能（K=56，测量于本机 `rime.dll`）：精确/前缀约 5–10 ms/键，长模糊/容错最坏约 65 ms/键，中段关键词约 9–16 ms/键（`meishao` 7 键总耗时 61 ms，`shouxiang` 9 键 141 ms）；20 键长句 `renshengjiushizhandou` 总耗时约 87 ms。GUI 已在记事本中实测 `lkcc`、`lienuo`、`senluo`、`zanguokuaigon`、`renshengjiushizhandou` 均正确提交；内嵌预编辑 `di'ou`/`mei'shao`、回车/小键盘回车提交也已实测通过。

详见 [docs/TEST_REPORT.md](docs/TEST_REPORT.md) 与 [docs/acceptance/](docs/acceptance/)。

---

## 6. 文档

- [PLAN.md](PLAN.md) — 总体方案、执行步骤、验收门
- [docs/ALGORITHM.md](docs/ALGORITHM.md) — 算法设计：多通道、音节 DP、关键词、评分、复杂度
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 架构与数据流、Rime/Lua 集成、配置与开关
- [docs/INSTALL.md](docs/INSTALL.md) — 安装、部署、卸载、共存与排错
- [docs/USAGE.md](docs/USAGE.md) — 输入模式、示例、配置项
- [docs/BUILD.md](docs/BUILD.md) — 从 data/dict.txt 重新构建数据/Lua/包与跑测试
- [docs/MAINTENANCE.md](docs/MAINTENANCE.md) — 更新词库、调权重、看日志、版本维护
- [docs/TEST_REPORT.md](docs/TEST_REPORT.md) — 测试矩阵、结果、性能、GUI 记录
- [docs/acceptance/](docs/acceptance/) — 独立子代理验收报告
- [LICENSE](LICENSE) — MIT

---

## 7. 已知限制

1. **关键词模式存在天然歧义**：极稀疏声母子序列（如 `mlh`）和多个词条共享的中段音节串（如“是我的”“护身符”）可能同时匹配多个词条；方案保证返回 Top-N，但 top1 不保证是用户心中那一条。需求示例 `lkcc`、`meishao` 已稳定 top1。
2. **中段关键词低于全拼前缀**：`zhiwen` 会先给前缀词 `直纹叶翼蜥`，包含 `zhi wen` 的 `少女之吻` 排在其后；这是有意保留“前缀优先”。
3. **只输出 1212 条**：词库外输入只做 bigram/trigram 召回 + Damerau/Dice-LCS 回退，不会造句或输出其他内容；回退候选只保证表面字母相关，不保证语义相关。
4. **安装源是整仓 Plum 包**：用户会浅克隆整个仓库（约 6 MB，含 tests/experiments/docs），仓库必须公开，并且目标机器要有 Git for Windows（Git Bash）。Weasel 0.17.4 的本地 ZIP 安装路径不复制 `lua/`，不能作为完整安装方式。
5. **安装器不改 `default.custom.yaml`**：是否启用“魔光键影”由官方“方案选单设定”的勾选决定；不要用第三方脚本直接改写方案列表，以免与 luna 等方案冲突。
6. **数据读音为工程化整理**：以 pypinyin + luna_pinyin + 人工覆盖为准；若发现译名读音争议，改 `experiments/pinyin-data/override.yaml` 后重新构建。
7. **性能取决于词条长度与输入类型**：纯精确/前缀很快；长模糊/容错输入会跑音节 DP，最坏约 65 ms/键；中段关键词约 9–16 ms/键。可通过 `ff7-ime/dp_max_candidates`、`ff7-ime/fallback/max_candidates` 调整。

---

## 8. 版本与许可

- 方案版本：**1.0.0**
- 目标：Weasel 0.17.4 / librime 1.13.1 / Windows 10 19045 x64
- 数据：`data/dict.txt` 1212 条（UTF-16 LE BOM）
- 运行时：Lua 5.4.7（内嵌于 `rime.dll`）
- 许可：代码采用 [MIT](LICENSE)；词表数据由用户提供，再分发前请确认数据权利。

数据来源：用户提供的 `data/dict.txt`；拼音参考 pypinyin、luna_pinyin、terra_pinyin 与人工覆盖表。方案代码可供用户自行修改与再分发。
