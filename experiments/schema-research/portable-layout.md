# 魔光键影 portable 包目录结构建议

结论先说：**小狼毫 Weasel 没有官方 portable（便携）模式**。0.17.4 的 GitHub
release 只有 `weasel-0.17.4.0-installer.exe`；Weasel 源码中也没有 portable
分支。用户目录由注册表 `HKCU\Software\Rime\Weasel\RimeUserDir` 决定，缺省为
`%APPDATA%\Rime`。

因此这里给出两种“便携”：

- **A. 便携方案包**（推荐）：Weasel 正常安装，zip 只带方案文件与安装脚本；
- **B. 便携数据目录**：把 Rime 用户目录整体搬到 U 盘/绿色目录，通过
  `WeaselSetup.exe /userdir:<dir>` 切换。它仍然是“全局用户目录”，会影响现有
  `luna_pinyin_simp`，必须迁移/备份。

---

## 1. 证据

### 1.1 官方 release 没有 portable 资产

GitHub API `releases/latest`（0.17.4）资产：

```
debug_symbols.7z
weasel-0.17.4.0-installer.exe
```

### 1.2 用户目录来源

`RimeWithWeasel/WeaselUtility.cpp`：

```cpp
fs::path WeaselUserDataPath() {
  RegQueryValueEx(HKEY_CURRENT_USER, L"Software\\Rime\\Weasel",
                  L"RimeUserDir", ...);
  // 没有值时：
  ExpandEnvironmentStringsW(L"%AppData%\\Rime", ...);
}
```

共享数据目录是 **exe 所在目录 + `data`**：

```cpp
fs::path WeaselSharedDataPath() {
  GetModuleFileNameW(NULL, _path, ...);
  return fs::path(_path).remove_filename().append("data");
}
```

所以把安装目录整个复制到 U 盘，`shared_data_dir` 可以工作；但 `user_data_dir`
仍然读注册表/AppData，且 IME 需要注册 TSF/COM，不能真正“双击即用”。

### 1.3 切换用户目录的官方参数

`WeaselSetup/WeaselSetup.cpp`：

```
/userdir:<dir> - Set user directory
```

实现是直接写：

```
HKCU\Software\Rime\Weasel\RimeUserDir = <dir>
```

不需要管理员权限（HKCU）。

安装目录可从注册表读取：

```
HKLM\SOFTWARE\WOW6432Node\Rime\Weasel\WeaselRoot
# 本机值：C:\Program Files\Rime\weasel-0.17.4
```

---

## 2. 方案 A：便携方案包（推荐）

### 2.1 zip 目录结构

```
moguang-jianying-0.1.0/
├─ README.txt
├─ install.bat
├─ uninstall.bat
├─ payload/
│  ├─ moguang_jianying.schema.yaml
│  ├─ moguang_jianying.custom.yaml
│  ├─ moguang_jianying_data.tsv
│  └─ lua/
│     └─ moguang_jianying.lua
├─ tools/
│  ├─ install_moguang.py
│  └─ rime_harness.py          （可选，开发/验证用）
└─ backup/                     （安装时创建）
```

目标安装位置：

```
%APPDATA%\Rime\
├─ moguang_jianying.schema.yaml
├─ moguang_jianying.custom.yaml
├─ moguang_jianying_data.tsv
├─ lua\moguang_jianying.lua
└─ default.custom.yaml         （只追加 schema）
```

### 2.2 install.bat 参考

```bat
@echo off
setlocal
set HERE=%~dp0
set RIME_USER=%APPDATA%\Rime

echo [1/3] 复制方案文件...
python "%HERE%tools\install_moguang.py" --user-dir "%RIME_USER%"
if errorlevel 1 (
  echo 安装脚本失败：请确认已安装 Python 3.8+ 与 PyYAML
  pause
  exit /b 1
)

echo [2/3] 部署...
start /wait "" "C:\Program Files\Rime\weasel-0.17.4\WeaselDeployer.exe" /deploy

echo [3/3] 检查...
if exist "%RIME_USER%\build\moguang_jianying.schema.yaml" (
  echo 部署成功：build\moguang_jianying.schema.yaml
) else (
  echo 部署可能失败，请查看 %TEMP%\rime.weasel 日志
)

pause
```

说明：

- `python` 不在 PATH 时，可改为随包附带的 Python embeddable 包，或在 README
  中给出手动复制步骤。
- 安装目录不是默认路径时，从注册表读取 `WeaselRoot` 后替换 deployer 路径。
- 运行前建议先备份 `default.custom.yaml`；脚本自身也会备份。

### 2.3 uninstall.bat 参考

```bat
@echo off
setlocal
set HERE=%~dp0
set RIME_USER=%APPDATA%\Rime

python "%HERE%tools\install_moguang.py" --user-dir "%RIME_USER%" --uninstall
start /wait "" "C:\Program Files\Rime\weasel-0.17.4\WeaselDeployer.exe" /deploy
pause
```

加 `--purge` 可同时删除 `lua\moguang_jianying.lua` 与数据文件。

### 2.4 优点与限制

优点：

- 不改变 Weasel 安装，不影响其他输入法；
- 只新增文件，`default.custom.yaml` 只追加一行；
- 卸载可逆，脚本自动备份；
- 用户现有 `luna_pinyin_simp` 完全不动。

限制：

- 依赖已安装的 Weasel；
- Python 不是 Windows 自带；若要“双击即用”，需要把 YAML 合并逻辑改写成
  PowerShell（见 §4）或附带 Python 运行时。

---

## 3. 方案 B：便携数据目录

### 3.1 目录结构

```
D:\MoguangRime\                 （U 盘或绿色目录）
├─ rime-data/                   ← 作为 RimeUserDir
│  ├─ default.custom.yaml
│  ├─ user.yaml
│  ├─ installation.yaml         （从旧目录复制，保留 installation_id）
│  ├─ luna_pinyin.userdb/       （如果要保留现有用户词库）
│  ├─ moguang_jianying.schema.yaml
│  ├─ moguang_jianying.custom.yaml
│  ├─ moguang_jianying_data.tsv
│  ├─ lua/moguang_jianying.lua
│  └─ build/                    （可留空，部署生成）
├─ install-portable.ps1
├─ uninstall-portable.ps1
├─ backup/
│  └─ old_userdir.txt
└─ README.txt
```

### 3.2 install-portable.ps1（参考）

```powershell
$ErrorActionPreference = "Stop"
$HERE   = Split-Path -Parent $MyInvocation.MyCommand.Path
$TARGET = Join-Path $HERE "rime-data"
$WEASEL = (Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel").WeaselRoot
$KEY    = "HKCU:\Software\Rime\Weasel"

New-Item -ItemType Directory -Force (Join-Path $HERE "backup") | Out-Null

# 1. 停止服务
& "$WEASEL\WeaselServer.exe" /q
Start-Sleep -Seconds 2

# 2. 保存旧 RimeUserDir（没有则写空文件）
$old = (Get-ItemProperty -Path $KEY -Name RimeUserDir -ErrorAction SilentlyContinue).RimeUserDir
if ($null -eq $old) { $old = "" }
Set-Content -Path (Join-Path $HERE "backup\old_userdir.txt") -Value $old -Encoding UTF8

# 3. 迁移现有用户数据（目标为空时）
if (-not (Test-Path $TARGET)) {
    New-Item -ItemType Directory -Force $TARGET | Out-Null
    robocopy "$env:APPDATA\Rime" $TARGET /E /COPY:DAT /R:1 /W:1 | Out-Null
}

# 4. 切换并部署
& "$WEASEL\WeaselSetup.exe" "/userdir:$TARGET"
Start-Process "$WEASEL\WeaselServer.exe"
Start-Process -Wait -FilePath "$WEASEL\WeaselDeployer.exe" -ArgumentList "/deploy"
```

### 3.3 uninstall-portable.ps1（参考）

```powershell
$ErrorActionPreference = "Stop"
$HERE   = Split-Path -Parent $MyInvocation.MyCommand.Path
$WEASEL = (Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel").WeaselRoot
$KEY    = "HKCU:\Software\Rime\Weasel"

& "$WEASEL\WeaselServer.exe" /q
Start-Sleep -Seconds 2

$oldFile = Join-Path $HERE "backup\old_userdir.txt"
$old = if (Test-Path $oldFile) { (Get-Content $oldFile -Raw).Trim() } else { "" }

if ($old) {
    & "$WEASEL\WeaselSetup.exe" "/userdir:$old"
} else {
    Remove-ItemProperty -Path $KEY -Name RimeUserDir -ErrorAction SilentlyContinue
}

Start-Process "$WEASEL\WeaselServer.exe"
Start-Process -Wait -FilePath "$WEASEL\WeaselDeployer.exe" -ArgumentList "/deploy"
```

注意：

- `WeaselSetup.exe /userdir:` 只写注册表，不复制数据；第 3 步的 robocopy 是必须的。
- 如果目标目录已经有旧数据，脚本不会覆盖；请自行决定是否先清空。
- `HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel` 的 `WeaselRoot` 在 64 位系统上通常
  存在；如果读不到，回退到 `C:\Program Files\Rime\weasel-0.17.4`。

### 3.4 优点与限制

优点：

- 用户配置真正落在 U 盘/绿色目录，换机器可带走；
- 通过官方 `/userdir` 参数切换，不改 Weasel 二进制。

限制与风险：

- **全局生效**：`RimeUserDir` 是当前 Windows 用户的全局设置，所有方案
  （luna_pinyin_simp 等）都会跟着搬走；
- 目标目录必须提前迁移 `%APPDATA%\Rime` 的内容，否则现有方案/词库“消失”；
- `installation.yaml` 的 `installation_id` 会跟随目录；如果多台机器共用同一
  目录，同步/用户词典可能冲突；
- WeaselServer 是后台服务，切换目录后必须停止/重启；
- 仍然不是真正的 portable IME：Weasel 仍需安装、注册 TSF/COM；换一台没有
  安装 Weasel 的机器不能直接用；
- 卸载时如果旧 `RimeUserDir` 是 `%APPDATA%\Rime`，恢复即可；如果旧值不存在，
  删除该值。

---

## 4. 无 Python 的 YAML 合并方案（PowerShell 思路）

如果不想依赖 Python，可用 PowerShell 5.1 做最小合并：

1. 读取 `default.custom.yaml` 文本；
2. 如果已包含 `moguang_jianying`，跳过；
3. 如果文件为空或不存在，写入：

   ```yaml
   patch:
     schema_list/+:
       - {schema: moguang_jianying}
   ```

4. 如果存在 `patch:` 和 `schema_list:`，在 `schema_list:` 下插入一行
   `    - {schema: moguang_jianying}`；
5. 否则写入 `patch: { schema_list/+: [...] }` 或提示用户手动编辑。

PowerShell 没有内置 YAML 解析器，文本插入对缩进/注释敏感。建议：

- 简单场景：只处理“空文件”和“已有 `schema_list:`”两种；
- 复杂场景：仍然用 Python/PyYAML，或让用户手动合并。

研究阶段使用的是 Python 脚本（已实测），PowerShell 版本未在干净机器实测。

---

## 5. 备份与恢复

### 5.1 安装前

```bat
robocopy "%APPDATA%\Rime" "%USERPROFILE%\Rime-backup-full" /E /COPY:DAT /R:1 /W:1
```

### 5.2 方案包自带备份

`install_moguang.py` 会把被修改/覆盖/删除的文件复制到：

```
%APPDATA%\Rime\_backup\moguang_<YYYYmmdd-HHMMSS>\
```

### 5.3 恢复

1. 停止 WeaselServer：`WeaselServer.exe /q`
2. 恢复文件（`robocopy` 或手工 copy）
3. 启动 WeaselServer
4. `WeaselDeployer.exe /deploy`
5. 验证 luna_pinyin_simp 与 moguang_jianying

### 5.4 便携数据目录的备份

直接复制整个 `rime-data/` 即可；其中 `build/` 可以不复制（部署会重建），
`luna_pinyin.userdb/` 是用户词库，按需保留。

---

## 6. 推荐结论

- 面向最终用户：**方案 A（便携方案包）**。Weasel 正常安装，zip 只带方案文件，
  安装脚本只追加 schema，风险最低。
- 面向“想把配置放 U 盘/绿色目录”的高级用户：**方案 B（便携数据目录）**，但要在
  README 中明确“会全局切换 RimeUserDir，现有方案会一起搬走”。
- 不要宣称“免安装 portable 小狼毫”：官方没有该能力，IME 注册无法绕过。
