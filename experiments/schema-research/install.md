# 魔光键影 安装与部署指南（Windows / 小狼毫 Weasel）

适用：小狼毫 Weasel 0.17.4（librime 1.13.1），Windows x64。
目标：只新增 `moguang_jianying` 方案，不覆盖、不破坏现有 `luna_pinyin_simp`。

> 说明：本指南中的部署命令依据 Weasel 0.17.4 源码与真实日志整理；研究阶段未对真实
> `%APPDATA%\Rime` 执行部署（避免影响现有输入法）。临时 user dir 的等价部署已验证，
> 见 `REPORT.md`。

---

## 0. 前置检查

1. 确认安装目录：

   ```bat
   dir "C:\Program Files\Rime\weasel-0.17.4\WeaselDeployer.exe"
   dir "C:\Program Files\Rime\weasel-0.17.4\data\default.yaml"
   ```

2. 确认用户目录（默认 `%APPDATA%\Rime`；如果改过 `RimeUserDir`，以注册表为准）：

   ```bat
   reg query "HKCU\SOFTWARE\Rime\Weasel" /v RimeUserDir
   ```

   没有该值时使用 `%APPDATA%\Rime`。

3. 确认现有方案列表：

   ```bat
   type "%APPDATA%\Rime\default.custom.yaml"
   ```

   典型内容：

   ```yaml
   patch:
     schema_list:
       - {schema: luna_pinyin_simp}
   ```

4. 关闭正在进行的输入（按 Esc 清空 composition）。

---

## 1. 备份（强烈建议）

### 1.1 最小备份

```bat
set BACKUP=%USERPROFILE%\Rime-backup-moguang
mkdir "%BACKUP%"
copy "%APPDATA%\Rime\default.custom.yaml" "%BACKUP%\default.custom.yaml"
copy "%APPDATA%\Rime\user.yaml" "%BACKUP%\user.yaml" 2>nul
xcopy "%APPDATA%\Rime\luna_pinyin.userdb" "%BACKUP%\luna_pinyin.userdb\" /E /I /H /Y 2>nul
```

### 1.2 完整备份

```bat
robocopy "%APPDATA%\Rime" "%USERPROFILE%\Rime-backup-full" /E /COPY:DAT /R:1 /W:1
```

Python 安装脚本也会把它修改/覆盖/删除的每个文件复制到：

```
%APPDATA%\Rime\_backup\moguang_<YYYYmmdd-HHMMSS>\
```

---

## 2. 复制方案文件

### 2.1 手动复制

在 `experiments/schema-research/` 下执行：

```bat
set RIME_USER=%APPDATA%\Rime

copy moguang_jianying.schema.yaml "%RIME_USER%\moguang_jianying.schema.yaml"
copy moguang_jianying.custom.yaml "%RIME_USER%\moguang_jianying.custom.yaml"
copy moguang_jianying_data.sample.tsv "%RIME_USER%\moguang_jianying_data.tsv"
mkdir "%RIME_USER%\lua" 2>nul
copy lua\moguang_jianying.lua "%RIME_USER%\lua\moguang_jianying.lua"
```

最终结构：

```
%APPDATA%\Rime\
├─ moguang_jianying.schema.yaml
├─ moguang_jianying.custom.yaml
├─ moguang_jianying_data.tsv
└─ lua\
   └─ moguang_jianying.lua
```

### 2.2 使用安装脚本（推荐）

需要 Python 3.8+ 和 PyYAML：

```bat
python -c "import yaml" 2>nul || python -m pip install pyyaml
python install_moguang.py --user-dir "%APPDATA%\Rime"
```

脚本行为：

- 复制 schema / custom / lua / data；
- `moguang_jianying.custom.yaml` 默认只写了一个与 schema 相同的 `menu/page_size: 5`（等于不改变默认值）；需要改开关/候选数时再取消其中注释；
- 如果目标 custom 或 data 已存在，**不覆盖**（保留用户配置/用户数据）；
- 如果 `default.custom.yaml` 已有 `patch/schema_list`，追加 `{schema: moguang_jianying}`；
- 如果没有，写入 `patch/schema_list/+`，保留 `default.yaml` 的完整方案列表；
- 幂等：重复运行不会重复追加；
- 所有修改前备份。

先看将做什么（不写任何文件）：

```bat
python install_moguang.py --user-dir "%APPDATA%\Rime" --dry-run
```

---

## 3. 修改 default.custom.yaml

### 3.1 已有 `patch/schema_list`（最常见）

原文件：

```yaml
patch:
  schema_list:
    - {schema: luna_pinyin_simp}
```

改成：

```yaml
patch:
  schema_list:
    - {schema: luna_pinyin_simp}
    - {schema: moguang_jianying}
```

保留 `customization:` 段和其余 patch 项，不要删除。

### 3.2 没有自定义过 schema_list

用 `/+` 追加，避免覆盖 `default.yaml` 里的默认方案：

```yaml
patch:
  schema_list/+:
    - {schema: moguang_jianying}
```

### 3.3 注意

- 必须放在 `patch:` 下；顶层 `schema_list:` 不会被 Rime 当成 patch。
- YAML 缩进用空格，不要 Tab。
- 不要写 `schema_list/@moguang_jianying` 之类的命名索引；列表索引只支持数字/`next`/`last` 等。
- 修改后必须重新部署。

---

## 4. 部署

### 4.1 cmd / 批处理

```bat
start /wait "" "C:\Program Files\Rime\weasel-0.17.4\WeaselDeployer.exe" /deploy
echo exit=%ERRORLEVEL%
```

必须用 `start /wait`：`WeaselDeployer.exe` 是 GUI 子系统，直接运行不会等待。

### 4.2 PowerShell

```powershell
$p = Start-Process -Wait -PassThru `
  -FilePath "C:\Program Files\Rime\weasel-0.17.4\WeaselDeployer.exe" `
  -ArgumentList "/deploy"
$p.ExitCode
```

### 4.3 退出码说明

- `0`：没有并发 deployer、初始化成功；
- `1`：已有一个 `WeaselDeployer` 在运行（互斥量冲突）；
- **0 不代表构建一定成功**：源码中 `rime->deploy()` 的返回值被忽略。必须继续做第 5 步验证。

### 4.4 如果 WeaselServer 没运行

部署本身仍可执行；但输入法不会自动重载。启动服务：

```bat
start "" "C:\Program Files\Rime\weasel-0.17.4\WeaselServer.exe"
```

需要停止时：

```bat
"C:\Program Files\Rime\weasel-0.17.4\WeaselServer.exe" /q
```

---

## 5. 验证部署成功

### 5.1 构建产物

```bat
if exist "%APPDATA%\Rime\build\moguang_jianying.schema.yaml" (
  echo BUILD_OK
) else (
  echo BUILD_MISSING
)
findstr /C:"schema_id: moguang_jianying" "%APPDATA%\Rime\build\moguang_jianying.schema.yaml"
```

### 5.2 方案列表

```bat
findstr /C:"moguang_jianying" "%APPDATA%\Rime\build\default.yaml"
```

应能看到：

```
  - schema: moguang_jianying
```

### 5.3 日志

日志在 `%TEMP%\rime.weasel`：

```powershell
Get-ChildItem "$env:TEMP\rime.weasel\*.log" |
  Sort-Object LastWriteTime |
  Select-Object -Last 3
```

查找关键行：

```powershell
Select-String -Path "$env:TEMP\rime.weasel\*.log" `
  -Pattern "updating schemas|schema: moguang_jianying|lua|ERROR" |
  Select-Object -Last 30
```

成功时通常能看到：

```
deployment_tasks.cc:163] updating workspace.
deployment_tasks.cc:186] updating schemas.
deployment_tasks.cc:195] schema: moguang_jianying
config_data.cc:92] saving config file '...\build\moguang_jianying.schema.yaml'
```

失败时优先看 `Error parsing YAML`、`nonexistent config file`、`autoload error`、`module ... not found`。

### 5.4 实际输入

1. 在任意文本框按 `Ctrl+\`` 或 `F4`；
2. 选择“魔光键影”；
3. 输入 `lkcc`；
4. 应出现候选“测试候选（lkcc 分段验证用）”（使用样例数据时）。

如果候选窗显示 `lkcc` 被空格拆开（如 `l k c c`），说明 segment 被拆，回到 `REPORT.md` §3 检查 `speller`/`recognizer`。

### 5.5 确认 luna_pinyin_simp 未受影响

切换到 `朙月拼音·简化字`，输入 `nihao`，应仍出现“你好”等候选。两者互不干扰。

---

## 6. 切换与默认方案

- `Ctrl+\`` 或 `F4`：方案选单；
- 本方案 `key_binder` 还绑定了 `Ctrl+Shift+1`：切换到下一个方案；
- 想默认进入本方案：把 `{schema: moguang_jianying}` 放在 `schema_list` 第一位；
- Rime 会在 `user.yaml` 记录 `previously_selected_schema`，已有用户可能仍沿用上次方案。

---

## 7. 常见问题速查

| 现象 | 优先检查 |
|---|---|
| 方案选单没有“魔光键影” | `build/default.yaml` 的 `schema_list`；YAML 是否解析失败；是否重新部署 |
| 有 preedit 但无候选 | `lua/` 路径、`lua_translator@*...` 星号、日志 `autoload error`、数据文件路径 |
| `lkcc` 被拆段 | `speller/finals`、`speller/algebra`、`delimiter`、`recognizer/patterns` |
| 改了配置没变化 | 同一秒 mtime、`start /wait`、是否有另一个 deployer、根 `__patch` |
| 候选重复/合并异常 | `engine/filters` 是否挂了 `uniquifier` |
| 开关改错项 | 是否用了 `switches/@名字/reset`；必须用数字索引 |
| 部署退出码 0 但没生效 | 查 `build/` 和日志；退出码不代表构建成功 |

---

## 8. 升级方案

1. 备份 `default.custom.yaml` 和 `moguang_jianying.custom.yaml`（脚本会自动备份被覆盖文件）；
2. 用新版本覆盖 `moguang_jianying.schema.yaml` 和 `lua/moguang_jianying.lua`；
3. 如果数据格式变化，替换 `moguang_jianying_data.tsv`（脚本默认不覆盖已有 data，需要手动替换）；
4. 修改文件后等待 1-2 秒，再部署；
5. 验证 `build/moguang_jianying.schema.yaml` 的 `__build_info/timestamps` 已更新。

注意：`switches` 的顺序是 patch 索引的一部分。升级时如果调整了开关顺序，用户 custom 里的 `switches/@N/reset` 会指向别的开关；应保持顺序稳定，或在升级说明中给出迁移表。

---

## 9. 安全安装检查清单

- [ ] 已备份 `default.custom.yaml`、`user.yaml`、`luna_pinyin.userdb`
- [ ] 只新增 `moguang_jianying.*`、`lua/moguang_jianying.lua`、数据文件
- [ ] `default.custom.yaml` 只追加 schema，不删除 luna_pinyin_simp
- [ ] 没有修改 `installation.yaml`
- [ ] 没有写入 `C:\Program Files\Rime\weasel-0.17.4`
- [ ] 部署后 luna_pinyin_simp 和 moguang_jianying 都能输入
- [ ] 记录了回滚方法（见 `uninstall.md`）
