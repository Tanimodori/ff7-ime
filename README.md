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
| 混合缩写 | 声母序列 + 末尾完整音节，可跳过中间音节 | `shbi` → 金属护臂 / 水手护臂 |
| 中段关键词 | 匹配词条中段的音节前缀，可跳过前导音节 | `meishao` → 有时是出手相助的美少女忍者！ |
| 内嵌预编辑 | 输入框内显示预测的音节分隔符，不影响上屏文本 | `diou` → `di'ou`；`nd` → `n'd` |
| 部分输入 | 全拼前缀或不完整音节 | `shenl` → 神罗 |
| 漏/多/错/换位 | 漏字母、多字母、相邻换位、音节换位 | `lienuo` / `leino` / `leiknuo` / `nuolei` → 雷诺 |
| 候选稳定 | 每次按键都给出 N 个候选；乱码、单字母、空输入也不空输出 | `zzzzzz` → 9 个候选 |
| 按键过滤 | 只接受拼音字母与分隔符 `'`；数字、标点、符号和空闲时的空格不会透传给游戏 | `1` / `,` / `!` → 无输出；`shenluo1` → 神罗 |
| 可配置 | 候选数、分页、注释、模糊开关、容错上限等均在 YAML 中 | `ff7-ime/top_n: 12` |

本方案禁用了 Shift 中英切换：按 Shift 不会进入英文模式，Shift 会透传给游戏，不会吞掉冲刺/奔跑键。需要输入英文时切换到 `luna_pinyin_simp`。

同时，本方案只接受拼音字母和音节分隔符 `'`。数字、标点、符号以及没有候选时的空格会被吞掉，不会落到游戏里；候选菜单展开时，数字 1–9 仍然用于选词。

---

## 安装

本方案自带 Windows 安装器：**不依赖 Plum、不依赖 Git、不依赖 bash**，
唯一要求是 Windows 10/11 系统自带的 PowerShell 5.1（不需要 PowerShell 7）。

### 用自带安装器安装（推荐）

1. 下载发行包：
   - 在 GitHub 上点 **Code → Download ZIP**，或
   - 从 Release 下载 `ff7-ime-1.0.0.zip`；
2. 解压到任意可写目录（路径含中文、空格都可以）；
3. 双击解压出来的 **`install.cmd`**；
4. 安装器先打印它探测到的路径，然后把 5 个运行时文件复制到 Rime 用户目录，
   并触发一次重新部署；
5. 右键小狼毫托盘图标 → **方案选单设定**，勾选 **魔光键影**，点击 **中**；
6. 若候选没有立即生效，右键托盘 → **重新部署**，或重启 WeaselServer。

安装器不会改写 `default.custom.yaml`，也不会覆盖你自己的 `ff7-ime.custom.yaml`。
重复运行是安全的：内容相同的文件会跳过，内容不同的文件会先备份到
`%APPDATA%\Rime\_backup\ff7-ime-<时间戳>\` 再覆盖。

卸载运行 **`uninstall.cmd`**，只读校验运行 **`verify.cmd`**。
非默认路径、无网络安装、命令行选项（`-RimeUserDir` / `-WeaselDir` / `-DryRun` /
`-NoDeploy`）与完整排错见 [docs/INSTALL.md](docs/INSTALL.md)。

> 如果你更习惯官方包管理器，`recipe.yaml` 仍然保留，可以用小狼毫的
> **获取更多输入方案** 输入 `Tanimodori/ff7-ime` 安装（需要 Git for Windows）。
> 该路径在装了 WSL 的机器上可能因 `bash` 冲突失败，见
> [docs/INSTALL.md](docs/INSTALL.md) 附录 A。

> 不要用 Weasel 内置的 **获取更多输入方案** 直接喂本仓库的 ZIP：那条路径只复制
> 根目录的 `*.yaml`，会漏掉 `lua/`，还会把示例 `ff7-ime.custom.yaml` 覆盖进用户目录。
> 请用本包自带的 `install.cmd`。

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
`关键词 · wo men hui ...`、`容错 · lei nuo`。候选菜单展开时可用数字 1–9 选词；
空格、回车或小键盘回车提交高亮候选。没有展开候选时，数字、标点、符号和空格
不会输入到游戏中。

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
install.cmd                   安装器入口（双击即用）
uninstall.cmd                 卸载器入口
verify.cmd                    只读校验入口
packaging/
  ff7-ime.ps1                 安装器核心（PowerShell 5.1）
  manifest.txt                运行时文件清单
data/dict.txt                 原始词表（UTF-16 LE BOM，1212 条）
ff7-ime.schema.yaml           Rime 方案
ff7-ime.custom.yaml           用户配置示例（安装器不会安装它）
lua/
  ff7-ime.lua                 Rime translator 适配层
  ff7-ime_matcher.lua         纯 Lua 匹配与排序引擎
  ff7-ime_data.lua            构建生成的词条数据
  ff7-ime_filter.lua          按键过滤（只放行字母与分隔符）
recipe.yaml                   可选的 Plum 安装清单（只装 schema + lua）
docs/                         安装、使用、维护文档
tools/                        数据构建、包校验、发行包打包脚本
  build_release_zip.py        生成 dist/ff7-ime-<版本>.zip
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
| 安装依赖 | Windows 自带的 PowerShell 5.1；不需要 Git、Git Bash 或 PowerShell 7 |
| 运行时依赖 | 无外部服务或运行时 |

其他 Rime 前端（macOS/Linux）未做验证；需要确认其 `lua_translator`、`lua_processor`
与中文路径支持。

---

## 已知限制

1. **关键词存在天然歧义**：极稀疏的声母子序列（如 `mlh`）或多个词条共享的中段音节串
   （如“是我的”“护身符”）可能同时匹配多个词条。方案保证返回 N 个候选，但不保证
   top1 总是您想要的那条。
2. **只输出固定词库**：词库外输入只按字面相似度回退，不会造句或输出其他内容；
   回退候选只保证字母相关，不保证语义相关。
3. **安装不依赖官方包管理器**：自带 `install.cmd` 直接写 Rime 用户目录，
   不需要网络、Git 或 Git Bash。`recipe.yaml` 仍保留，供习惯 Plum 的用户使用。
4. **安装器不改方案列表**：是否启用「魔光键影」由官方「方案选单设定」的勾选决定；
   安装器不会自动改写 `default.custom.yaml`，以免与 `luna_pinyin_simp` 等方案冲突。
   卸载时可用 `uninstall.cmd -PruneSchemaList` 清理残留勾选。
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
