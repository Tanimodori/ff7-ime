# 安装与部署

> 目标：小狼毫 Weasel 0.17.4（Windows x64，librime 1.13.1）。
> 本方案只新增文件，不覆盖 `luna_pinyin_simp`；安装脚本会备份 `default.custom.yaml`。

---

## 1. 交付物

| 路径 | 说明 |
|---|---|
| `dist/moguang_jianying-portable.zip` | portable 分发包（可分发档案，推荐分发） |
| `dist/moguang_jianying-portable.zip.sha256` | 压缩包本身的 SHA-256 |
| `dist/moguang_jianying-portable/` | 解压后的目录 |
| `dist/moguang_jianying-portable/rime/` | Rime 用户目录覆盖层：schema/custom/lua/data |
| `dist/moguang_jianying-portable/MANIFEST.txt` | 包元数据：版本、目标、安装入口 |
| `dist/moguang_jianying-portable/SHA256SUMS` | 包内每个文件的 SHA-256 |
| `dist/moguang_jianying-portable/install.ps1` / `.cmd` | 安装 |
| `dist/moguang_jianying-portable/uninstall.ps1` / `.cmd` | 卸载 |
| `dist/moguang_jianying-portable/verify.ps1` / `.cmd` | 只读校验 |
| `dist/moguang_jianying-portable/deploy-rime.ps1` | 无头部署（直接调 rime.dll） |
| `dist/moguang_jianying-portable/source/` | `dict.txt`、拼音 TSV、override、构建脚本 |
| `dist/moguang_jianying-portable/docs/` | 完整文档 |

### 1.1 “portable”的定义

本项目中的 **portable 指“可以分发的档案”**，即一个自包含的 Rime 方案 zip：

- 包含完整方案源文件（`*.schema.yaml`、`*.custom.yaml`、`lua/`），`rime/` 目录就是 Rime 用户目录覆盖层；
- 包含安装/卸载/校验脚本、文档、重建数据与测试 harness，不依赖 Python/Node/网络；
- 解压后既可以运行 `install.ps1` 自动安装，也可以按 Rime 的常规做法把 `rime/` 下的文件复制到用户目录再部署；
- 用 `MANIFEST.txt` + `SHA256SUMS` 标识版本与完整性，适合作为发布附件或离线拷贝。

它**不是**“小狼毫便携运行时”：Weasel 的用户目录由前端/注册表决定，见第 8 节。

---

## 2. 快速安装

1. 解压到一个**可写**目录（不要放在 `Program Files`）。
2. 双击 `install.cmd`；或在 PowerShell 中：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

3. 等待脚本输出：

```
[MGJY] Deploying via rime.dll (headless) ...
[MGJY] rime maintenance started=1
[MGJY] Installed. Press F4 or Ctrl+` and select 魔光键影.
```

4. 按 **F4** 或 **Ctrl+`** 打开方案选单，选择 **魔光键影**。
5. 在记事本输入 `shenluo`，候选应出现“神罗”；输入 `lkcc`，候选应出现“我们会立刻彻底铲除你们！”。

### 手工安装（不运行脚本）

解压后把 `rime/` 下的全部文件复制到 Rime 用户目录，将 `moguang_jianying` 加入 `default.custom.yaml` 的 `patch/schema_list`，然后重新部署。完整步骤见第 4 节。

### 校验分发包

```powershell
# 压缩包本身（在 dist/ 或下载目录执行）
$expected = (Get-Content .\moguang_jianying-portable.zip.sha256).Split()[0]
$actual = (Get-FileHash .\moguang_jianying-portable.zip -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $expected) { Write-Error "zip hash mismatch" }

# 解压后逐文件核对（在包根目录执行）
Get-Content .\SHA256SUMS | ForEach-Object {
    $hash, $file = $_ -split '  ', 2
    $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $hash) { Write-Error "mismatch: $file" }
}
```

标准 `sha256sum` 环境（Git Bash/WSL）也可以直接 `sha256sum -c SHA256SUMS`。

### 参数

```powershell
# 非默认安装目录
.\install.ps1 -WeaselDir "D:\Apps\Rime\weasel-0.17.4"

# 非默认用户目录（仅本方案复制/部署到这个目录，不修改注册表）
.\install.ps1 -RimeUserDir "D:\RimeUser"

# 只复制和 patch，不部署
.\install.ps1 -NoDeploy
```

> `-RimeUserDir` 只影响本脚本操作的目标目录；小狼毫真正的用户目录由注册表
> `HKCU\Software\Rime\Weasel\RimeUserDir` 决定。若要让小狼毫使用其他目录，需要：
>
> ```powershell
> & "C:\Program Files\Rime\weasel-0.17.4\WeaselSetup.exe" /userdir:"D:\RimeUser"
> ```
>
> 然后重启 WeaselServer。该操作是全局的，会影响现有方案，务必先备份。

---

## 3. 安装脚本做了什么

`install.ps1`：

1. 校验 `rime/lua/mgjy_data.lua` 等文件存在；
2. 创建 `%APPDATA%\Rime\lua`；
3. 备份 `default.custom.yaml` → `default.custom.yaml.mgjy-backup-<timestamp>`；
4. 复制：
   - `moguang_jianying.schema.yaml`
   - `moguang_jianying.custom.yaml`
   - `lua/mgjy.lua`、`mgjy_matcher.lua`、`mgjy_data.lua`
5. 幂等 patch `default.custom.yaml` 的 `schema_list`：
   - 已有 `schema_list:` 块 → 在最后一个列表项后追加本方案；
   - 没有 → 在 `patch:` 下加 `schema_list/+:`；
   - 已包含本方案 → 跳过；
6. 停止 WeaselServer（如果正在运行）；
7. 调用 `deploy-rime.ps1`：通过 C# P/Invoke 调 `rime.dll` 的维护接口，无 GUI 完成重建；
8. 重启 WeaselServer；
9. 检查 `build/moguang_jianying.schema.yaml` 与 `build/default.yaml`。

> **不要用 `WeaselDeployer.exe /deploy` 代替第 7 步**：本机实测它会打开“方案选单设定”GUI，
> 并可能把 `default.custom.yaml` 改写成只剩当前方案，导致 `luna_pinyin_simp` 丢失。
> 如已发生，按第 7 节恢复。

---

## 4. 手动安装（不使用脚本）

1. 解压分发包，把 `rime/` 下的文件复制到 `%APPDATA%\Rime`（保持 `lua/` 子目录）：

```
moguang_jianying.schema.yaml
moguang_jianying.custom.yaml
lua\mgjy.lua
lua\mgjy_matcher.lua
lua\mgjy_data.lua
```

2. 编辑 `%APPDATA%\Rime\default.custom.yaml`，确认 `patch/schema_list` 同时含：

```yaml
patch:
  schema_list:
    - {schema: luna_pinyin_simp}
    - {schema: moguang_jianying}
```

若原本没有 `schema_list`，可写：

```yaml
patch:
  schema_list/+:
    - {schema: moguang_jianying}
```

3. 部署（任选其一）：
   - 包内无头部署：
     ```powershell
     powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy-rime.ps1
     ```
   - 小狼毫托盘菜单 → “重新部署”；
   - `WeaselDeployer.exe` → 在“方案选单设定”窗口中勾选/确认后点击部署。

4. 检查：

```
%APPDATA%\Rime\build\moguang_jianying.schema.yaml
%APPDATA%\Rime\build\default.yaml   # schema_list 应含两个方案
```

---

## 5. 卸载

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
```

- 删除本方案的 schema/custom/lua 文件；
- 从 `default.custom.yaml` 删除含 `moguang_jianying` 的行；
- 清理空的 `schema_list/+` 块；
- 无头重建，`luna_pinyin_simp` 保持可用。

恢复安装前的方案列表：

```powershell
.\uninstall.ps1 -RestoreBackup
```

> 备份文件：`default.custom.yaml.mgjy-backup-<timestamp>`。
> 恢复会覆盖安装后对 `default.custom.yaml` 的其他修改；如安装后又改过配置，请手动合并。

仅检查不修改：

```powershell
.\verify.ps1
```

---

## 6. 与 luna_pinyin_simp 共存

- 安装脚本只追加 `schema_list` 条目，不删除/覆盖 luna 文件；
- 无头部署保留 `build/default.yaml` 的完整 `schema_list`；
- 已实测：同一 user dir 中 `luna_pinyin_simp` 输入 `nihao` 仍得到“你好”，本方案输入 `shenluo` 得到“神罗”；
- 切换方案：F4 / Ctrl+`，或 `Ctrl+Shift+1`（若 key_binder 生效）。

---

## 7. 故障排查

### 7.1 方案选单里没有“魔光键影”

1. 检查 `%APPDATA%\Rime\build\default.yaml` 的 `schema_list` 是否含 `moguang_jianying`；
2. 检查 `%APPDATA%\Rime\default.custom.yaml` 是否有该条目；
3. 重新运行 `deploy-rime.ps1`；
4. 若仍无，检查文件名必须是 `moguang_jianying.schema.yaml`（Rime 只认 `<schema_id>.schema.yaml`）；
5. 查看日志：`%TEMP%\rime.weasel\rime.weasel.*.log`。

### 7.2 有方案但输入无候选

1. 检查 `%APPDATA%\Rime\lua\mgjy.lua`、`mgjy_matcher.lua`、`mgjy_data.lua` 是否存在；
2. 检查 schema 中是否为 `lua_translator@*mgjy`（`*` 不能少）；
3. 查看日志中的 Lua 错误（`lua_translator` / `lua error` / `module not found`）；
4. 确认 `speller/alphabet` 包含全部小写字母，`delimiter` 为 `'`，无 `algebra`；
5. 重新部署并重启 WeaselServer。

### 7.3 `luna_pinyin_simp` 从方案列表消失

通常是不当使用 `WeaselDeployer` 导致 `default.custom.yaml` 被改写。恢复：

```powershell
# 找到最新备份
Get-ChildItem "$env:APPDATA\Rime\default.custom.yaml.mgjy-backup-*" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1

# 恢复后手动确认同时含两个方案，再无头部署
Copy-Item <备份文件> "$env:APPDATA\Rime\default.custom.yaml" -Force
.\deploy-rime.ps1
```

或直接编辑 `default.custom.yaml` 为：

```yaml
patch:
  schema_list:
    - {schema: luna_pinyin_simp}
    - {schema: moguang_jianying}
```

然后跑 `deploy-rime.ps1`。

### 7.4 修改配置后不生效

- Rime 部署签名是**秒级 mtime**；改完等 1–2 秒再部署；
- Lua 模块只在 engine 初始化时加载；部署后建议重启 WeaselServer；
- 检查 `mgjy/use_switches`：
  - `false`（默认）：`mgjy/fuzzy/*` 等配置生效；
  - `true`：F4 的 `mgjy_fuzzy_*` 开关优先，custom 中的 fuzzy 配置会被忽略。

### 7.5 输入卡顿

- 调小 `mgjy/dp_max_candidates`（默认 56，可试 32/40）；
- 调小 `mgjy/typo/max_edit`（默认 2，可试 1）；
- 关闭不需要的模糊音（尤其 `n_l`、`r_l`、`f_h`）；
- 精确/前缀输入本身不跑 DP，通常 1–15 ms/键；长模糊/容错输入最坏约 50 ms/键。

### 7.6 标点/间隔号

- 词条中的 `！，·……` 是候选文本的一部分，由 Lua 原样输出；
- 用户不需要输入标点；输入拼音即可；
- 标点键由 Rime 的 `punctuator` 处理，不会影响候选文本。

### 7.7 日志位置

| 内容 | 路径 |
|---|---|
| Rime/Weasel 日志 | `%TEMP%\rime.weasel\rime.weasel.*.log` |
| 构建产物 | `%APPDATA%\Rime\build\` |
| 本方案备份 | `%APPDATA%\Rime\default.custom.yaml.mgjy-backup-*` |

---

## 8. 分发包（portable）的定义与边界

本项目把 **portable 定义为“可以分发的档案”**，而不是“整个小狼毫随 U 盘走”的便携运行时。具体含义：

- 单个 zip 自带 schema、custom、`lua/`、安装/卸载/校验脚本、文档、源数据与测试 harness；
- `rime/` 是 Rime 用户目录覆盖层，可按 Rime 的通用安装方式直接复制到用户目录；
- 不依赖 Python/Node/网络；安装脚本可指定 `-RimeUserDir` 与 `-WeaselDir`；
- 卸载可回滚，包内 `MANIFEST.txt`/`SHA256SUMS` 用于版本识别与完整性校验。

边界：Weasel 的用户目录由前端/注册表决定（默认 `%APPDATA%\Rime`），分发包不会改变这一点。若确实需要“整个小狼毫随 U 盘走”，需要：

1. 在目标机器安装 Weasel；
2. `WeaselSetup.exe /userdir:<U盘目录>` 切换全局用户目录；
3. 重启 WeaselServer；
4. 注意这会改变该机器上所有 Rime 方案的用户目录，需迁移/备份。

---

## 9. 兼容性

| 项目 | 值 |
|---|---|
| 前端 | 小狼毫 Weasel 0.17.4 x64 |
| librime | 1.13.1 |
| Lua | 5.4.7（内嵌） |
| 系统 | Windows 10 19045 x64（理论 Windows 11 亦可） |
| 依赖 | 无外部运行时；安装脚本需 PowerShell 5.1+ |
