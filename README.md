# 魔光键影 · ff7-ime

> 面向 **小狼毫 Weasel 0.17.4（Windows x64）** 的《最终幻想7》专属拼音输入方案。
> 输入中国大陆普通话无调全拼，只输出 `data/dict.txt` 中的 **1212 条**词条，并支持模糊音、多音字与允许误读、声母/关键词缩写、漏错与换位容错；任何输入都会给出候选。

![方案](https://img.shields.io/badge/Rime-Weasel%200.17.4-blue) ![Lua](https://img.shields.io/badge/Lua-5.4.7-green) ![词条](https://img.shields.io/badge/词条-1212-orange) ![许可](https://img.shields.io/badge/许可-MIT-green)

---

## 特性

| 能力 | 说明 | 示例 |
|---|---|---|
| 固定词库 | 只输出 `data/dict.txt` 的 1212 条，不造句、不联想词库外内容 | `shenluo` → 神罗 |
| 精确全拼 | 无调全拼，`ü` 可写 `v` 或 `u` | `leinuo` → 雷诺 |
| 模糊音 | 默认开启 `zh/ch/sh → z/c/s`、`ng → n`；`n/l`、`r/l`、`f/h`、`en/eng`、`in/ing` 等可配置 | `senluo` → 神罗 |
| 多音字/误读 | 按词条内上下文匹配多音字，并允许“有边读边”等误读；规范读音优先 | `chongli` → 重力；`qinmu` → 梣木 |
| 全声母 | 输入每个音节的声母 | `wmhlkcdccnm` → 我们会立刻彻底铲除你们！ |
| 关键词缩写 | 声母的稀疏子序列，长句可缩写 | `lkcc` → 我们会立刻彻底铲除你们！ |
| 中段关键词 | 匹配词条中段的音节前缀，可跳过前导音节 | `meishao` → 有时是出手相助的美少女忍者！ |
| 内嵌预编辑 | 输入框内显示预测的音节分隔符，不影响上屏文本 | `diou` → `di'ou`；`nd` → `n'd` |
| 部分输入 | 全拼前缀或不完整音节 | `shenl` → 神罗 |
| 漏/多/错/换位 | 漏字母、多字母、相邻换位、音节换位 | `lienuo` / `leino` / `leiknuo` / `nuolei` → 雷诺 |
| 候选稳定 | 每次按键都给出 N 个候选；乱码、单字母、空输入也不空输出 | `zzzzzz` → 9 个候选 |
| 可配置 | 候选数、分页、注释、模糊开关、容错上限等均在 YAML 中 | `ff7-ime/top_n: 12` |

本方案禁用了 Shift 中英切换：按 Shift 不会进入英文模式，Shift 会透传给游戏，不会吞掉冲刺/奔跑键。需要输入英文时切换到 `luna_pinyin_simp`。

---

## 安装

本项目是标准的 **Rime 包（Plum recipe）**，通过小狼毫自带的
**方案选单设定 → 获取更多输入方案** 安装，不需要额外安装脚本。

前置条件：

- 小狼毫 Weasel 0.17.4 x64；
- Git for Windows（含 Git Bash）。官方安装器检测到 Git Bash 才会走 Plum；
  否则只会复制根目录 YAML，不会复制 `lua/`。

安装步骤：

1. 右键小狼毫托盘图标 → **方案选单设定**；
2. 点击左下角 **获取更多输入方案…**；
3. 在控制台提示后输入安装标识：

   ```
   Tanimodori/ff7-ime
   ```

4. 看到 `Installing recipe: Tanimodori/ff7-ime` 和 4 个 `Installing:` 文件后关闭控制台；
5. 在自动刷新的方案列表里勾选 **魔光键影**，点击 **中**；
6. 若未立即生效，右键托盘 → **重新部署**，或重启 WeaselServer。

通过 Plum 安装时，安装器只复制 4 个运行时文件，不改写 `default.custom.yaml`，也不会
覆盖用户自己的 `ff7-ime.custom.yaml`。完整说明、更新、卸载与故障排查见
[docs/INSTALL.md](docs/INSTALL.md)。

> 不要用 Weasel 的本地 ZIP 路径安装：该路径会复制仓库根目录的 `*.yaml`，
> 可能把示例 `ff7-ime.custom.yaml` 一并写入用户目录并覆盖已有配置，而且不会
> 复制 `lua/`。

---

## 使用

| 模式 | 输入 | 结果 |
|---|---|---|
| 全拼 | `shenluo` | 神罗 |
| 模糊 | `senluo` | 神罗 |
| 多音/异读 | `chongli` | 重力 |
| 误读 | `qinmu` | 梣木 |
| 全声母 | `wmhlkcdccnm` | 我们会立刻彻底铲除你们！ |
| 关键词 | `lkcc` | 我们会立刻彻底铲除你们！ |
| 中段关键词 | `meishao` | 有时是出手相助的美少女忍者！ |
| 前缀 | `shenl` | 神罗 |
| 漏字母 | `leino` | 雷诺 |
| 相邻换位 | `lienuo` | 雷诺 |
| 多字母 | `leiknuo` | 雷诺 |
| 音节换位 | `nuolei` | 雷诺 |
| 含标点词条 | `renshengjiushizhandou` | 人生就是战斗！ |

候选窗口默认显示 9 个；注释显示命中通道与主拼音，例如 `全拼 · shen luo`、
`关键词 · wo men hui ...`、`容错 · lei nuo`。空格、回车或小键盘回车提交高亮候选。

更完整的输入规则与示例见 [docs/USAGE.md](docs/USAGE.md)。

---

## 配置

把需要的配置写入 `%APPDATA%\Rime\ff7-ime.custom.yaml`，修改后重新部署：

```yaml
patch:
  ff7-ime/top_n: 12              # 候选数量 N
  menu/page_size: 12             # 每页候选数
  ff7-ime/show_comment: true     # 是否显示注释
  ff7-ime/fuzzy/n_l: true        # 开启 n/l 模糊
  ff7-ime/fuzzy/ng_n: false      # 关闭 ng/n 模糊
  ff7-ime/typo/max_edit: 1       # 容错编辑距离上限
  ff7-ime/preedit/enabled: true  # 预编辑音节分隔
```

方案本身已经包含全部默认值，不创建 custom 文件也能正常工作。完整配置项与
F4 开关说明见 [docs/USAGE.md](docs/USAGE.md)。

---

## 项目结构

```
data/dict.txt                 原始词表（UTF-16 LE BOM，1212 条）
ff7-ime.schema.yaml           Rime 方案（Plum 安装）
ff7-ime.custom.yaml           用户配置示例（Plum 不安装；不要用 ZIP 路径安装）
lua/
  ff7-ime.lua                 Rime translator 适配层
  ff7-ime_matcher.lua         纯 Lua 匹配与排序引擎
  ff7-ime_data.lua            构建生成的词条数据
recipe.yaml                   Plum 安装清单（只装 schema + lua）
docs/                         安装、使用、维护文档
tools/                        数据构建、包校验、测试脚本
  pinyin-data/                注音 TSV、读音覆盖表与提取脚本
tests/                        Lua 核心用例与全量评估
LICENSE                       MIT
```

---

## 兼容性

| 项目 | 版本 |
|---|---|
| 前端 | 小狼毫 Weasel 0.17.4 x64 |
| librime | 1.13.1 |
| Lua | 5.4.7（内嵌于 `rime.dll`） |
| 系统 | Windows 10 19045 x64；理论兼容 Windows 11 |
| 安装依赖 | Git for Windows（含 Git Bash） |
| 运行时依赖 | 无外部服务或运行时 |

其他 Rime 前端（macOS/Linux）未做验证；需要确认其 `lua_translator` 与中文路径支持。

---

## 已知限制

1. **关键词存在天然歧义**：极稀疏的声母子序列（如 `mlh`）或多个词条共享的中段音节串
   （如“是我的”“护身符”）可能同时匹配多个词条。方案保证返回 N 个候选，但不保证
   top1 总是您想要的那条。
2. **只输出固定词库**：词库外输入只按字面相似度回退，不会造句或输出其他内容；
   回退候选只保证字母相关，不保证语义相关。
3. **安装源是整仓 Plum 包**：安装时会浅克隆整个仓库，仓库必须公开，目标机器需要
   Git for Windows（Git Bash）。Weasel 0.17.4 的本地 ZIP 安装路径不复制 `lua/`，
   不能作为完整安装方式。
4. **安装器不改方案列表**：是否启用“魔光键影”由官方“方案选单设定”的勾选决定；
   不建议用第三方脚本直接改写 `default.custom.yaml`，以免与 `luna_pinyin_simp`
   等方案冲突。
5. **读音为人工整理**：以 pypinyin、luna_pinyin 与人工覆盖表为准。如发现译名读音
   争议，可修改 `tools/pinyin-data/override.yaml` 后重新构建。
6. **性能取决于输入类型**：精确/前缀输入很快；长模糊与容错输入会执行更完整的
   对齐计算，可能稍慢。可通过 `ff7-ime/dp_max_candidates`、
   `ff7-ime/fallback/max_candidates` 等配置调整。

---

## 文档

- [docs/INSTALL.md](docs/INSTALL.md) — 安装、更新、卸载、共存与排错
- [docs/USAGE.md](docs/USAGE.md) — 输入模式、候选、配置项与 F4 开关
- [docs/MAINTENANCE.md](docs/MAINTENANCE.md) — 更新词库、修正读音、测试与发布
- [LICENSE](LICENSE) — MIT

---

## 版本与许可

- 方案版本：**1.0.0**
- 词库：`data/dict.txt`，1212 条（UTF-16 LE BOM）
- 许可：代码采用 [MIT](LICENSE)；词表数据由用户提供，再分发前请确认数据权利。

数据来源：用户提供的 `data/dict.txt`；拼音参考 pypinyin、luna_pinyin、
terra_pinyin 与人工覆盖表。
