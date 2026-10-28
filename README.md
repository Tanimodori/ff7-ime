# 魔光键影 · Moguang Jianying

> 面向 **小狼毫 Weasel 0.17.4（Windows x64，librime 1.13.1）** 的《最终幻想7》专属拼音输入方案。
> 输入中国大陆普通话无调全拼，**只输出 `dict.txt` 中的 1212 条词条**，并支持模糊音、多音字/允许误读、声母/关键词、漏错/换位容错，任何输入都给出 N 个候选。

![方案](https://img.shields.io/badge/Rime-Weasel%200.17.4-blue) ![Lua](https://img.shields.io/badge/Lua-5.4.7-green) ![词条](https://img.shields.io/badge/词条-1212-orange) ![许可](https://img.shields.io/badge/许可-用户自有数据-lightgrey)

---

## 1. 特性

| 能力 | 说明 | 示例 |
|---|---|---|
| 固定词库 | 只输出 `dict.txt` 的 1212 条，不造句、不联想词库外内容 | `shenluo` → 神罗 |
| 精确全拼 | 无调全拼，`ü` 可写 `v` 或 `u` | `leinuo` → 雷诺 |
| 模糊音 | `zh/ch/sh→z/c/s`、`ng→n` 默认开启；`n/l`、`r/l`、`f/h`、`en/eng`、`in/ing` 等可配置 | `senluo` → 神罗 |
| 多音字/误读 | 语料内上下文多音 + 允许“有边读边”等误读，规范读音优先 | `chongli` → 重力；`qinmu` → 梣木 |
| 全声母 | 每个音节首字母 | `wmhlkcdccnm` → 我们会立刻彻底铲除你们！ |
| 关键词子序列 | 声母的稀疏子序列，长句可缩写 | `lkcc` → 我们会立刻彻底铲除你们！ |
| 中段关键词 | 词条中段的音节前缀子序列，可跳过前导音节 | `meishao` → 有时是出手相助的美少女忍者！ |
| 部分输入 | 全拼前缀/不完整音节 | `shenl` → 神罗 |
| 漏/多/错/换位 | 漏字母、多字母、相邻换位、音节换位 | `lienuo` / `leino` / `leiknuo` / `nuolei` → 雷诺 |
| 永远 N 个 | 乱码、单字母、空输入也不空输出 | `zzzzzz` → 9 个候选 |
| 可配置 | 候选数、分页、注释、模糊开关、权重、DP 上限均在 YAML | `mgjy/top_n: 12` |

---

## 2. 快速安装

### 2.1 本机（已部署）

本机已安装到：

```
C:\Users\Tanimodori\AppData\Roaming\Rime\
```

并已确认与 `luna_pinyin_simp` 共存。按 **F4** 或 **Ctrl+`** 打开方案选单，选择 **魔光键影**。

### 2.2 从分发包（portable）安装

本项目的 **portable 指“可分发档案”**：一个自包含的 Rime 方案 zip，不是小狼毫便携运行时。包内 `rime/` 就是 Rime 用户目录覆盖层（schema、custom、`lua/`），因此它既能用脚本安装，也能按 Rime 的常规做法手动复制。

**方式 A：安装脚本**

1. 解压 `dist/moguang_jianying-portable.zip`。
2. 双击 `install.cmd`（或运行 `install.ps1`）。
3. 脚本会：备份 `default.custom.yaml` → 复制方案/Lua/数据 → 加入 `schema_list` → 用 `rime.dll` 无头部署 → 校验 `build/moguang_jianying.schema.yaml`。
4. 按 **F4** / **Ctrl+`** 选择 **魔光键影**。

**方式 B：手动复制（Rime 标准做法）**

1. 解压后把 `rime/` 下的全部文件复制到 Rime 用户目录（小狼毫默认 `%APPDATA%\Rime`）。
2. 在 `default.custom.yaml` 的 `patch/schema_list` 中加入 `moguang_jianying`。
3. 重新部署（托盘菜单 → “重新部署”，或包内 `deploy-rime.ps1`）。

卸载：双击 `uninstall.cmd`；如需恢复安装前的方案列表，运行 `uninstall.ps1 -RestoreBackup`。

分发包完整性：包内 `SHA256SUMS` 列出每个文件的 SHA-256；`dist/moguang_jianying-portable.zip.sha256` 给出压缩包本身的哈希。详见 [docs/INSTALL.md](docs/INSTALL.md)。

> 若你使用非默认的小狼毫安装目录，给 `install.ps1` 加 `-WeaselDir "D:\...\weasel-0.17.4"`。
> 若想把用户数据放到其他目录，加 `-RimeUserDir "D:\RimeUser"`；但小狼毫本身仍通过注册表 `RimeUserDir` 决定用户目录，详见 [docs/INSTALL.md](docs/INSTALL.md)。

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

编辑 `%APPDATA%\Rime\moguang_jianying.custom.yaml`，修改后重新部署（安装脚本的无头部署或 Weasel 托盘“重新部署”）。

```yaml
patch:
  mgjy/top_n: 12              # 候选数量 N
  menu/page_size: 12          # 每页候选数
  mgjy/show_comment: true     # 是否显示注释
  mgjy/fuzzy/n_l: true        # 开启 n/l 模糊
  mgjy/fuzzy/ng_n: false      # 关闭 ng/n 模糊
  mgjy/typo/max_edit: 1       # 容错编辑距离上限
  mgjy/dp_max_candidates: 56  # 需要 DP 时的候选上限（性能/召回权衡）
```

完整配置项与 F4 开关说明见 [docs/USAGE.md](docs/USAGE.md)。

---

## 4. 项目结构

```
dict.txt                         原始词表（UTF-16 LE BOM，1212 条）
src/
  moguang_jianying.schema.yaml   Rime schema
  moguang_jianying.custom.yaml   用户配置示例
  lua/
    mgjy.lua                     Rime translator 适配层（读配置/开关/yield）
    mgjy_matcher.lua             纯 Lua 匹配/排序引擎
    mgjy_data.lua                构建期生成的数据表（1212 条）
packaging/                       安装/卸载/校验/无头部署脚本
dist/                            portable 分发包（构建产物，不入库）
tools/                           数据构建、测试、打包脚本
tests/                           核心用例、全量评估、Lua 沙箱测试
experiments/                     研究/探针/中间产物（不参与运行时）
docs/                            算法、架构、安装、使用、构建、维护、测试报告
PLAN.md                          总体方案与验收门
```

---

## 5. 测试结果（本机实测）

| 类别 | 用例数 | 通过标准 | 结果 |
|---|---:|---|---|
| 精确全拼 | 1212 | top1 | **1212/1212（100%）** |
| 模糊音 | 878 | top1 | **878/878（100%）** |
| 全声母/前缀 | 1212 | top1 或 top3 | **1212/1212（100%；top1 98.3%）** |
| 漏/多/换位 | 600 | top3 | **600/600（100%；top1 99.7%）** |
| 关键词稀疏子序列 | 238 | top5 | **233/238（97.9%；top1 75.6%）** |
| 中段关键词 | 300 | top5 | **300/300（100%；top1 91.0%）** |
| 乱码/单字母/空 | 7 | 返回 N | **7/7（100%）** |

核心需求用例：

```
shenluo             → 神罗（全拼）
senluo              → 神罗（模糊）
leinuo / lienuo / leino / leiknuo / nuolei → 雷诺（全拼/漏/换位/多字/音节换位）
lkcc                → 我们会立刻彻底铲除你们！（关键词）
meishao             → 有时是出手相助的美少女忍者！（中段关键词）
wmhlkcdccnm         → 我们会立刻彻底铲除你们！（全声母）
zanguokuaigon       → 掌掴快攻（跨音节 ng→n 模糊）
renshengjiushizhandou → 人生就是战斗！（含标点）
zzzzzz              → 仍有 9 个候选
```

真实 Rime 逐键性能（K=56，测量于本机 `rime.dll`）：精确/前缀输入通常 1–15 ms/键，长模糊/容错输入最坏约 50 ms/键，中段关键词约 17–23 ms/键（`meishao` 7 键总耗时 123 ms）；20 键长句 `renshengjiushizhandou` 总耗时约 57 ms。GUI 已在记事本中实测 `lkcc`、`lienuo`、`senluo`、`zanguokuaigon`、`renshengjiushizhandou` 均正确提交。

详见 [docs/TEST_REPORT.md](docs/TEST_REPORT.md) 与 [docs/acceptance/](docs/acceptance/)。

---

## 6. 文档

- [PLAN.md](PLAN.md) — 总体方案、执行步骤、验收门
- [docs/ALGORITHM.md](docs/ALGORITHM.md) — 算法设计：多通道、音节 DP、关键词、评分、复杂度
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 架构与数据流、Rime/Lua 集成、配置与开关
- [docs/INSTALL.md](docs/INSTALL.md) — 安装、部署、卸载、共存与排错
- [docs/USAGE.md](docs/USAGE.md) — 输入模式、示例、配置项
- [docs/BUILD.md](docs/BUILD.md) — 从 dict.txt 重新构建数据/Lua/包与跑测试
- [docs/MAINTENANCE.md](docs/MAINTENANCE.md) — 更新词库、调权重、看日志、版本维护
- [docs/TEST_REPORT.md](docs/TEST_REPORT.md) — 测试矩阵、结果、性能、GUI 记录
- [docs/acceptance/](docs/acceptance/) — 独立子代理验收报告

---

## 7. 已知限制

1. **关键词模式存在天然歧义**：极稀疏声母子序列（如 `mlh`）和多个词条共享的中段音节串（如“是我的”“护身符”）可能同时匹配多个词条；方案保证返回 Top-N，但 top1 不保证是用户心中那一条。需求示例 `lkcc`、`meishao` 已稳定 top1。
2. **中段关键词低于全拼前缀**：`zhiwen` 会先给前缀词 `直纹叶翼蜥`，包含 `zhi wen` 的 `少女之吻` 排在其后；这是有意保留“前缀优先”。
3. **只输出 1212 条**：词库外输入只做最近邻回退，不会造句或输出其他内容。
4. **portable 是分发包，不是便携运行时**：本项目的 portable 定义为可分发档案，安装目标是 Rime 用户目录（小狼毫默认 `%APPDATA%\Rime`）。若要让小狼毫整体随 U 盘走，需要 `WeaselSetup.exe /userdir:<dir>` 并重启服务，这会改变该机器所有方案的用户目录。
5. **WeaselDeployer 的 `/deploy` 在部分环境会打开“方案选单设定”GUI 并改写 `default.custom.yaml`**。本包改用 `deploy-rime.ps1`（直接调用 `rime.dll` 的维护接口）无头部署，避免该问题。
6. **数据读音为工程化整理**：以 pypinyin + luna_pinyin + 人工覆盖为准；若发现译名读音争议，改 `experiments/pinyin-data/override.yaml` 后重新构建。
7. **性能取决于词条长度与输入类型**：纯精确/前缀很快；长模糊/容错输入会跑音节 DP，最坏约 50 ms/键；中段关键词约 17–23 ms/键。可通过 `mgjy/dp_max_candidates` 调整。

---

## 8. 版本

- 方案版本：**1.0.0**
- 目标：Weasel 0.17.4 / librime 1.13.1 / Windows 10 19045 x64
- 数据：`dict.txt` 1212 条（UTF-16 LE BOM）
- 运行时：Lua 5.4.7（内嵌于 `rime.dll`）

数据来源：用户提供的 `dict.txt`；拼音参考 pypinyin、luna_pinyin、terra_pinyin 与人工覆盖表。方案代码可供用户自行修改与再分发。
