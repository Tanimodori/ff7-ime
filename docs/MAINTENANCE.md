# 维护与构建

> 本页面向需要修改词库、读音或配置的维护者。只使用方案的用户不必阅读。

---

## 1. 文件职责

| 文件 | 作用 |
|---|---|
| `data/dict.txt` | 词条唯一来源；UTF-16 LE BOM，每行一条 |
| `tools/pinyin-data/override.yaml` | 人工读音/误读覆盖；优先级最高 |
| `tools/pinyin-data/extract.py` | 从词表生成 `phrases.tsv` / `chars.tsv` |
| `tools/pinyin-data/phrases.tsv` | 逐字注音结果，可人工审阅 |
| `tools/build_from_pinyin_data.py` | 生成最终 `lua/ff7-ime_data.lua` 与 `data/phrases.json` |
| `lua/ff7-ime_matcher.lua` | 匹配与排序算法 |
| `lua/ff7-ime.lua` | Rime 适配、配置读取与候选输出 |
| `lua/ff7-ime_filter.lua` | 按键过滤：只放行字母与分隔符，吞掉数字/标点/符号 |
| `ff7-ime.schema.yaml` | 方案接线与默认配置 |
| `ff7-ime.custom.yaml` | 用户配置示例 |
| `install.cmd` / `uninstall.cmd` / `verify.cmd` | 安装器入口（纯 ASCII，只负责定位 PowerShell 并转发参数） |
| `packaging/ff7-ime.ps1` | 安装器核心：路径探测、复制/备份、部署、卸载、只读校验（PowerShell 5.1） |
| `packaging/manifest.txt` | 运行时文件清单；必须与 `recipe.yaml` 的 `install_files` 完全一致 |
| `recipe.yaml` | 可选的 Plum 安装清单；只安装 schema + 4 个 Lua 文件 |
| `tools/check_package.py` | 校验 recipe、manifest、安装器脚本、版本、schema 元信息与安装清单 |
| `tools/build_release_zip.py` | 生成 `dist/ff7-ime-<版本>.zip` 发行包并自校验 |
| `.gitattributes` | 行尾策略：`.cmd` 固定 CRLF（cmd.exe 对 LF-only 的多行块会解析错），运行时 `*.lua` / `*.schema.yaml` 固定 LF（安装器按 SHA-256 逐字节比对） |
| `tests/` | Lua 核心用例与全量评估 |

---

## 2. 环境

| 工具 | 用途 |
|---|---|
| Python 3.9+ | 注音、数据构建、评估用例、包校验 |
| pypinyin | 主注音源 |
| PyYAML | 读取 `override.yaml` 与 `recipe.yaml` |
| Node.js | 运行 wasmoon Lua 5.4 沙箱测试 |
| wasmoon | 纯 Lua 引擎测试 |

安装 Python 依赖：

```bash
python -m pip install pypinyin pyyaml
```

安装 Lua 沙箱依赖：

```bash
cd tools/lua-sandbox
npm install wasmoon
```

运行时不需要 Python/Node；它们只用于构建与测试。

---

## 3. 更新词库

### 3.1 增删词条

1. 编辑 `data/dict.txt`（保持 UTF-16 LE BOM，每行一条，不要留空行）；
2. 重新生成注音：

   ```bash
   python tools/pinyin-data/extract.py
   python tools/pinyin-data/extract.py --check
   ```

3. 重新生成 Lua 数据：

   ```bash
   python tools/build_from_pinyin_data.py
   ```

4. 运行测试：

   ```bash
   NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
     node tests/lua/run_cases.js tests/lua/core_cases.json lua/ff7-ime_data.lua
   python tools/gen_eval_cases.py
   NODE_PATH="$PWD/tools/lua-sandbox/node_modules" node tests/lua/bulk_eval.js
   ```

5. 更新本机安装（二选一）：
   - **正式发布**：提交并推送后，在“获取更多输入方案”中重新输入
     `Tanimodori/ff7-ime`，Plum 会更新清单中的运行时文件（未变化的文件会跳过）；
   - **本地验证**：只复制变化的数据文件，然后在 Weasel 托盘选择“重新部署”：

     ```powershell
     Copy-Item lua\ff7-ime_data.lua "$env:APPDATA\Rime\lua\ff7-ime_data.lua" -Force
     ```

6. 切换方案并输入新词条全拼验证。

### 3.2 词条格式注意事项

- 只允许一行一条；标点可以保留；
- 不要用 Excel 另存，容易改变编码/BOM；
- 若出现重复词条，会占用匹配与排序名额，建议先去重；
- 词条中的标点不参与拼音；`extract.py` 只对汉字注音；
- 间隔号 `·` 原样输出，不注音。

---

## 4. 修正读音

### 4.1 优先级

```
confirmed_phrases（整词）
  > char_rules（上下文规则）
  > char_defaults（单字默认）
  > pypinyin 词组
  > pypinyin 单字
```

### 4.2 常见修改

**整词读音**：

```yaml
confirmed_phrases:
  - phrase: "曾"
    readings: ["zeng1"]
    reason: "Tseng；姓氏读 zēng"
```

**上下文规则**（某字在包含某子串时改读）：

```yaml
char_rules:
  - char: "长"
    when_contains: "长杖"
    reading: "chang2"
    reason: "长杖 = cháng zhàng"
```

**单字默认**：

```yaml
char_defaults:
  - char: "勒"
    reading: "le4"
    reason: "译名勒读 lè"
```

**允许误读**（低权重，不替代规范读音）：

```yaml
misread_candidates:
  "梣": ["qin2", "chen2"]
  "曾": ["ceng2"]
  "骰": ["shai3"]
```

修改后重新生成：

```bash
python tools/pinyin-data/extract.py
python tools/pinyin-data/extract.py --check
python tools/build_from_pinyin_data.py
```

### 4.3 确认某字最终读音

```bash
python - <<'PY'
import json
rows = json.load(open('data/phrases.json', encoding='utf-8'))
for r in rows:
    if r['text'] in ('曾', '防御长杖', '梣木', '骰子'):
        print(r['text'], r['syls'], r['alts'])
PY
```

- `syls` 是主读音；
- `alts` 是备选（多音/误读），带权重。

---

## 5. 调参

常用配置项与默认值见 [USAGE.md](USAGE.md)。维护时重点注意：

- `ff7-ime/top_n` 与 `menu/page_size` 保持一致；
- 开启更多模糊音会提高召回，但也可能增加歧义；
- `ff7-ime/typo/enabled: false` 是严格模式；
- `ff7-ime/dp_max_candidates`、`ff7-ime/fallback/*` 用于平衡召回与响应速度；
- 修改权重前先确认目标输入场景，避免破坏精确全拼的 top1。

---

## 6. 测试与包校验

### 6.1 核心用例

```bash
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/run_cases.js tests/lua/core_cases.json lua/ff7-ime_data.lua
```

覆盖精确全拼、模糊、声母、关键词、中段关键词、混合缩写、前缀、漏错换位、
预编辑、fallback 与空输入等核心行为。

### 6.2 全量评估

```bash
python tools/gen_eval_cases.py
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" node tests/lua/bulk_eval.js
```

输出按类别统计的通过率与失败样例。极稀疏关键词的少量歧义属于已知限制。

### 6.3 包布局与安装器

```bash
python tools/check_package.py
python tools/build_release_zip.py
python tools/check_package.py --zip dist/ff7-ime-1.0.0.zip
```

`check_package.py` 校验内容：

- `recipe.yaml` 的安装清单恰好是 5 个运行时文件；
- `packaging/manifest.txt` 与 `recipe.yaml` 的 `install_files` **完全一致**
  （两条安装路线不会各自漂移）；
- recipe 版本与 schema 版本一致；
- `schema_id: ff7-ime`、`author: Tanimodori`、`description: 魔光键影专属拼音输入方案`；
- `engine.translators` 含 `lua_translator@*ff7-ime`；
- `engine.processors` 含 `lua_processor@*ff7-ime_filter` 且在 `speller` 之前；
- 不安装 `*.custom.yaml`、`data/`、测试或文档；
- 安装路径没有绝对路径或 `..`；
- `install.cmd` / `uninstall.cmd` / `verify.cmd` 存在、是纯 ASCII、CRLF、
  用 `-File -ExecutionPolicy Bypass` 调用脚本，且**不引用 bash 或 pwsh**；
- `packaging/ff7-ime.ps1` 是 **UTF-8 with BOM**（PowerShell 5.1 缺 BOM 会按 ANSI
  读，中文提示会全部乱码）。

`build_release_zip.py` 生成 `dist/ff7-ime-<版本>/` 与 `.zip`、`.zip.sha256`，
并在打包后自校验：单个顶层目录、成员名安全、5 个运行时文件都在且非空、
包内 `.ps1` 仍带 BOM。`check_package.py --zip` 可再独立复核一次。

### 6.4 按键过滤

```bash
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/run_filter_cases.js
```

覆盖空闲状态下数字、标点、符号、空格与分隔符被吞掉，组合中分隔符/空格放行，
候选展开时数字 1–9 选词，以及控制键、导航键和小键盘回车透传。

---

## 7. 发布与回滚

### 7.1 版本升级

修改以下位置：

1. `ff7-ime.schema.yaml` 的 `schema/version`；
2. `recipe.yaml` 的 `recipe/version`（必须与 schema 一致）；
3. `README.md` 的版本段与安装说明里出现的 zip 文件名。

`packaging/manifest.txt` 只在运行时文件增删时才改；改完必须与 `recipe.yaml` 的
`install_files` 保持完全一致，`check_package.py` 会拦住不一致。
发行包名 `dist/ff7-ime-<版本>.zip` 由脚本按 schema 版本自动生成，不必手改。

数据有变化时，重新执行第 3 节的生成与测试步骤。

### 7.2 发版流程

1. 跑完第 6 节的测试与包校验；
2. 生成发行包并复核：

   ```bash
   python tools/build_release_zip.py
   python tools/check_package.py --zip dist/ff7-ime-1.0.0.zip
   ```

3. 提交并推送仓库；
4. 打 tag、建 Release，把 `dist/ff7-ime-1.0.0.zip` 和 `dist/ff7-ime-1.0.0.zip.sha256`
   作为附件上传。

> 打 tag、建 Release、上传附件都属于对外发布动作，必须先得到明确同意再执行。

### 7.3 本机更新

推送到 GitHub 后，本机更新有两条路：

- **自带安装器（推荐）**：重新下载 / 解压新版本，双击 `install.cmd`。
  只覆盖清单里的 5 个文件，内容没变的会跳过；
- **只更新数据做本地验证**：复制变化的文件后重新部署：

  ```powershell
  Copy-Item lua\ff7-ime_data.lua "$env:APPDATA\Rime\lua\ff7-ime_data.lua" -Force
  ```

### 7.4 回滚

先用 git 回到上一版提交，再重新安装或复制运行时文件。升级前建议备份整个
Rime 用户目录：

```powershell
Copy-Item "$env:APPDATA\Rime" "$env:APPDATA\Rime.backup-$(Get-Date -Format yyyyMMdd-HHmmss)" -Recurse
```

需要恢复时，把备份目录中的文件复制回 `%APPDATA%\Rime`，然后重启 WeaselServer
或重新部署。

---

## 8. 日志与调试

| 内容 | 路径 |
|---|---|
| Rime/Weasel 日志 | `%TEMP%\rime.weasel\rime.weasel.*.log` |
| 构建产物 | `%APPDATA%\Rime\build\` |
| 用户配置（可选） | `%APPDATA%\Rime\ff7-ime.custom.yaml` |

调试候选分数：

```yaml
patch:
  ff7-ime/show_score: true
```

注释会变成 `通道 · 拼音 · 0.xx`。

查看最近的 Lua 错误：

```powershell
Get-ChildItem "$env:TEMP\rime.weasel\*.log" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1 |
  Select-String -Pattern "lua|ERROR|ff7-ime" -Context 2,2
```

---

## 9. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| 安装器报「找不到小狼毫安装目录」（退出码 3） | 注册表、运行中的进程、卸载项、常见位置都没找到含 `WeaselDeployer.exe` 的目录 | 用 `-WeaselDir` 指定，或 `-NoDeploy` 只复制文件（见 INSTALL.md 7.1） |
| 安装器报「包不完整」（退出码 2） | 压缩包没解压全，或缺 `packaging\` | 重新完整解压；不要只把 `install.cmd` 单独复制出来运行（见 INSTALL.md 7.2） |
| 安装器报「目录不可写」（退出码 5） | 用户目录权限、或安全软件拦截 | 检查权限，或用 `-RimeUserDir` 指定可写目录（见 INSTALL.md 7.3） |
| 安装器报退出码 4 | 部署失败，或部署后应有产物消失 | 看 `%TEMP%\rime.weasel` 日志，手动重新部署（见 INSTALL.md 7.4） |
| 安装器报「指定的 -WeaselDir 无效」 | `-WeaselDir` 指错目录 | 指向含 `WeaselDeployer.exe` 的目录 |
| `packaging\ff7-ime.ps1` 的中文提示全是乱码 | 文件丢了 UTF-8 BOM（PowerShell 5.1 会按 ANSI 读） | 重新解压；`python tools/check_package.py` 会检查这一点 |
| 方案不显示 | `build/default.yaml` 没有条目 | 在「方案选单设定」中勾选「魔光键影」，重新部署 |
| 安装后完全无法打字/无候选 | 还没在方案选单里勾选，`build/ff7-ime.schema.yaml` 未生成 | 勾选「魔光键影」并保存，然后重新部署；必要时重启 WeaselServer |
| 有方案无候选 | Lua 模块未加载/文件名错 | 先跑 `verify.cmd`，再检查 `lua_translator@*ff7-ime` 与日志 |
| 输入被拆段 | `speller/algebra`/`finals`/`delimiter` 配置 | 保持 `alphabet` 全字母、`finals` 空、`delimiter` 为 `'`、无 algebra |
| 数字/标点/空格无输出 | `lua_processor@*ff7-ime_filter` 正在过滤 | 正常行为；候选展开时 1–9 可选词，切换其他方案可输入符号 |
| `lkcc` 被当 ASCII | `ascii_mode` 被外部打开 | 本方案已禁用 Shift 切换；切换到其他方案再切回，或重新部署 |
| 改了配置不生效 | 秒级 mtime/未重建 | 等 2 秒后重新部署；重启 WeaselServer |
| luna 丢失 | 其他工具改写了 `default.custom.yaml` | 在方案选单中同时勾选 luna 与「魔光键影」，重新部署 |
| 输入卡顿 | 长模糊/容错计算 | 降 `dp_max_candidates`、`max_edit`，关闭可选模糊 |
| 生僻字读音错 | 读音覆盖缺失 | 修改 `tools/pinyin-data/override.yaml` 后重新生成 |
| 词条重复 | `data/dict.txt` 重复 | 去重后重建；完全相同的文本会被 `uniquifier` 隐藏，但重复条目仍影响匹配与排序 |

---

## 10. 安全与隐私

- 方案自身不联网、不写日志、不上传输入；Rime/Weasel 的日志位置见第 8 节；
- 只读取 `%APPDATA%\Rime` 与安装目录的 Rime 数据；
- 所有候选来自本地 `ff7-ime_data.lua`；
- 自带安装器只写 `packaging/manifest.txt` 列出的 5 个运行时文件，以及
  需要时才创建的 `_backup\ff7-ime-*` 备份目录；不改写 `default.custom.yaml`；
- 安装器不依赖 bash / Git，只调用系统自带的 PowerShell 5.1，且不访问网络；
- 卸载默认只删除本方案自己的文件；`-PruneSchemaList` 必须显式指定才会修改
  `default.custom.yaml`，并且改前先备份；
- 卸载不会删除 `luna_pinyin_simp` 等既有方案。
