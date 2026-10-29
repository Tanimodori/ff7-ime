# 安装、更新与卸载

> 适用：小狼毫 Weasel 0.17.4（Windows x64，librime 1.13.1）。
> 本方案自带 Windows 安装器，**不依赖 Plum、不依赖 Git、不依赖 bash**。

---

## 1. 安装

### 1.1 前置条件

| 项目 | 要求 |
|---|---|
| 小狼毫 | Weasel 0.17.4 x64 |
| 系统 | Windows 10 / 11 x64 |
| PowerShell | 5.1（Windows 自带；**不需要** PowerShell 7） |
| 网络 | 不需要，解压即可离线安装 |
| Git / Git Bash | 不需要 |

安装器会在动手之前把所有相关路径探测出来并打印，所以小狼毫装在非默认目录、
用户目录被改到别处也都能正常工作（见 1.7）。

### 1.2 获取安装包

两种方式，内容完全相同：

1. 打开仓库页面 → **Code → Download ZIP**，解压到任意可写目录；
2. 在 Release 页下载 `ff7-ime-1.0.0.zip` 并解压（可用旁边的
   `ff7-ime-1.0.0.zip.sha256` 校验完整性）。

解压后目录根部应能看到：

```
install.cmd
uninstall.cmd
verify.cmd
packaging\ff7-ime.ps1
packaging\manifest.txt
ff7-ime.schema.yaml
lua\ff7-ime*.lua
```

### 1.3 运行安装器

双击 **`install.cmd`**。安装器先探测、后动手，输出形如：

```
魔光键影 · ff7-ime 安装器 1.0.0
动作：install    模式：正式执行
PowerShell：5.1.19041.6456    管理员：否（不需要）

== 探测结果
  包目录               C:\Users\<你>\Downloads\ff7-ime-1.0.0（脚本所在位置）
  运行时清单             packaging\manifest.txt（5 项）
  Rime 用户目录         C:\Users\<你>\AppData\Roaming\Rime（注册表 HKCU\SOFTWARE\Rime\Weasel\RimeUserDir）
  小狼毫目录             C:\Program Files\Rime\weasel-0.17.4（注册表 HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel\WeaselRoot）
  小狼毫版本             0.17.4.0（卸载项 DisplayVersion）；rime.dll：无版本信息
  日志目录              C:\Users\<你>\AppData\Local\Temp\rime.weasel
  已安装状态             0 / 5 个运行时文件存在

== 复制运行时文件
  [OK]   新增 ff7-ime.schema.yaml
  [OK]   新增 lua\ff7-ime.lua
  ...
  结果                新增 5 个，更新 0 个，已是最新 0 个

== 重新部署
  暂停服务              WeaselServer（部署期间需要停一下，结束后自动拉起）
  部署方式              rime.dll 无头部署
  恢复服务              WeaselServer 已重新启动

== 检查部署产物
  [注意] build\ff7-ime.schema.yaml 还没有生成：首次安装时这是正常的，
         librime 只编译已勾选的方案。
```

每一行探测结果都注明**来源**（参数 / 注册表 / 默认 / 扫描），
所以路径不对时能立刻看出是哪一步猜错了，而不是让安装悄悄写到别的地方。

> 首次安装时部署这一步可能要几十秒：librime 会检查并重建所有已启用方案的缓存。
> 期间 WeaselServer 会被短暂停止再自动拉起，输入法图标会闪一下，属正常现象。

### 1.4 激活方案

1. 右键小狼毫托盘图标 → **方案选单设定**（或运行 `WeaselDeployer.exe`）；
2. 在列表里勾选 **魔光键影**，点击 **中** 保存；
3. 若候选没有立即生效：右键托盘 → **重新部署**，或重启 WeaselServer。

> **为什么勾选之后才出现 `build\ff7-ime.schema.yaml`？**
> librime 只编译 `schema_list` 里已启用的方案。安装器触发的那次部署是为「更新」
> 重建缓存；首次安装时方案还没被勾选，所以 build 产物要等勾选后才会生成。
> 这不是安装失败。

### 1.5 安装器做什么 / 不做什么

| 会做 | 不会做 |
|---|---|
| 把清单里的 5 个运行时文件写进 Rime 用户目录 | 不改写 `default.custom.yaml` |
| 内容不同时先备份到 `_backup\ff7-ime-<时间戳>\` 再覆盖 | 不覆盖用户自己的 `ff7-ime.custom.yaml` |
| 安装后触发一次重新部署 | 不安装 `data/`、`tools/`、`tests/`、`docs/` |
| 卸载时只删除自己写的文件与 `build\ff7-ime*` | 不碰 `luna_pinyin_simp` 等其他方案 |
| 只读校验（`verify.cmd`） | 不联网、不上传任何数据 |

安装的 5 个运行时文件：

```
ff7-ime.schema.yaml
lua/ff7-ime.lua
lua/ff7-ime_matcher.lua
lua/ff7-ime_data.lua
lua/ff7-ime_filter.lua
```

安装目标是 Rime 用户目录（默认 `%APPDATA%\Rime`），并保留 `lua/` 子目录。
这些文件就足够运行：词库数据在 `lua/ff7-ime_data.lua`，`data/dict.txt` 只是重建数据的源文件。

> **不需要 opencc/**：本方案没有启用 `simplifier`，输出文本本身就是简体。

### 1.6 命令行选项

`install.cmd` / `uninstall.cmd` / `verify.cmd` 后面的参数会原样传给
`packaging\ff7-ime.ps1`：

| 选项 | 作用 |
|---|---|
| `-RimeUserDir <目录>` | 指定 Rime 用户目录，跳过注册表探测 |
| `-WeaselDir <目录>` | 指定小狼毫安装目录（含 `WeaselDeployer.exe`） |
| `-DryRun` | 只探测并打印将要执行的动作，**不写任何文件、不部署** |
| `-NoDeploy` | 只复制 / 删除文件，不触发重新部署 |
| `-PruneSchemaList` | 仅卸载：从 `default.custom.yaml` 移除 `ff7-ime` 条目（先备份） |
| `-PurgeBackups` | 仅卸载：删除 `_backup\ff7-ime-*` 备份目录 |
| `-Json` | 机器可读模式，见 1.9 |
| `--no-pause` | 结束后不等待按键（自动化用；也可设环境变量 `FF7_IME_NO_PAUSE=1`） |

示例：

```bat
rem 先看看会做什么
install.cmd -DryRun

rem 装到非默认的用户目录，且不自动部署
install.cmd -RimeUserDir D:\rime-user -NoDeploy

rem 卸载并顺手清理方案列表里的残留勾选
uninstall.cmd -PruneSchemaList

rem 只读检查装好了没有
verify.cmd
```

也可以直接调用脚本本体（例如 PowerShell 被策略限制、或你想在已有 PowerShell
会话里跑）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\ff7-ime.ps1 -Action install -DryRun
```

### 1.7 非默认路径

安装器按下面的顺序找路径，并在输出里打印命中来源：

**Rime 用户目录**

1. `-RimeUserDir` 参数（无条件优先）；
2. 注册表 `HKCU\SOFTWARE\Rime\Weasel` 的 `RimeUserDir`；
3. 默认 `%APPDATA%\Rime`。

没有显式指定时，会优先取「已经存在」的候选，避免注册表里的旧路径把安装引到空目录。

**小狼毫安装目录**（需要其中的 `WeaselDeployer.exe`）

1. `-WeaselDir` 参数（无条件优先，且必须是有效目录，否则直接报错）；
2. 注册表 `HKCU` / `HKLM`（含 `WOW6432Node`）的
   `SOFTWARE\Rime\Weasel\WeaselRoot` / `InstallDir`；
3. 自启动项 `…\CurrentVersion\Run` 里的 `WeaselServer.exe` 路径
   （覆盖「装在非常规目录、注册表没有 WeaselRoot、且当前没在运行」的情况，
   例如便携式安装到 `C:\小狼毫\weasel-0.17.4`）；
4. 正在运行的 `WeaselServer` / `WeaselDeployer` 进程路径；
5. 卸载项（`DisplayName` 含 Weasel / 小狼毫）的 `InstallLocation` / `DisplayIcon`；
6. 常见位置扫描：`%ProgramFiles%\Rime\weasel-*`、`%ProgramFiles(x86)%\...`、
   `%LOCALAPPDATA%\Programs\Rime\weasel-*`、`%SystemDrive%\Rime\weasel-*`，多版本取最高。

以上都找不到时会直接失败（退出码 3）并提示用 `-WeaselDir` 指定——不会静默猜一个目录。

> **部署是怎么做的**：安装器**不使用** `WeaselDeployer.exe`。它的 `/deploy` 虽然被
> 自己的 `/?` 列为「Update workspace」，但在 0.17.4 上实测会打开「方案选单设定」
> 窗口而不是静默部署，会让安装卡住；而且它只认注册表里的用户目录。
> 安装器改为调用内嵌 `rime.dll` 的无头部署，显式传入 `shared_data_dir` /
> `user_data_dir`，所以 `-RimeUserDir` 指向别处时也不会误部署到真实用户目录。
>
> 当目标目录正是 WeaselServer 正在使用的用户目录时，安装器会先停掉 WeaselServer、
> 部署完再自动拉起（它 mmap 了 `build\` 里的产物，同时写会冲突）。这就是输出里出现
> 「暂停服务 / 恢复服务」的原因。目标目录是别的目录时不会动 WeaselServer。

### 1.8 幂等与备份

- 重复运行 `install.cmd` 是安全的：内容相同的文件报「已是最新」并跳过；
- 内容不同（例如你手动改过、或上一版是通过 Plum 装的）会先把旧文件备份到
  `%APPDATA%\Rime\_backup\ff7-ime-<yyyyMMdd-HHmmss>\<相对路径>`，再覆盖；
- 卸载时同样会先备份「与发行版不一致」的文件，再删除；
- 备份目录不会被 Rime 扫描（不在 `lua\` 和根目录的 schema 通配范围内），可以放心留着；
- `uninstall.cmd -PurgeBackups` 可一次性删除所有 `_backup\ff7-ime-*`。

### 1.9 机器可读模式（`-Json`）

`-Json` 抑制人类可读输出，最后在 stdout 输出**一行**：

```
FF7IME-JSON {"ok":true,"action":"install",...}
```

前缀是必须的：librime 会把自己的诊断（glog 的 ERROR 级消息）直接写到 stderr，
调用方一旦 `2>&1` 合并，JSON 就会被污染。解析时取以 `FF7IME-JSON ` 开头的那一行、
去掉前缀即可。退出码仍然表示结果。

### 1.10 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 一般失败 / 校验未通过 |
| 2 | 包不完整（缺少清单里的文件） |
| 3 | 找不到小狼毫安装目录（且未给 `-NoDeploy`） |
| 4 | 部署失败，或部署后应有的产物消失 |
| 5 | 路径不可创建 / 不可写 |

---

## 2. 验证安装

### 2.1 运行只读校验

双击 **`verify.cmd`**（不改动任何文件）。它会逐个比对 5 个运行时文件是否与发行版
一致，并报告 build 产物与备份情况：

```
== 运行时文件
  [OK]   ff7-ime.schema.yaml
  [OK]   lua\ff7-ime.lua
  ...
== 构建产物
  [注意] build\ff7-ime.schema.yaml 不存在（尚未在方案选单中勾选，或还没重新部署）
```

### 2.2 检查文件

在 PowerShell 中：

```powershell
$rime = Join-Path $env:APPDATA 'Rime'
Get-ChildItem "$rime\ff7-ime.schema.yaml",
              "$rime\lua\ff7-ime.lua",
              "$rime\lua\ff7-ime_matcher.lua",
              "$rime\lua\ff7-ime_data.lua",
              "$rime\lua\ff7-ime_filter.lua"
```

五个文件都应存在。

### 2.3 检查方案列表

```powershell
Select-String -Path "$env:APPDATA\Rime\build\default.yaml" -Pattern 'ff7-ime'
```

在方案选单里勾选过「魔光键影」后，这里才会有条目。若没有，回到 1.4 节。

### 2.4 检查输入

在记事本中测试：

| 输入 | 期望 top1 |
|---|---|
| `shenluo` | 神罗 |
| `senluo` | 神罗（模糊音） |
| `nuolei` | 雷诺（音节换位） |
| `lkcc` | 我们会立刻彻底铲除你们！ |
| `meishao` | 有时是出手相助的美少女忍者！ |

再验证按键过滤：单独按 `1`、`0`、`,`、`!`、空格或小键盘数字，不应输入任何字符；
输入 `shenluo` 后按 `1`，应上屏「神罗」。回到 `luna_pinyin_simp` 后这些键恢复正常。

---

## 3. 用户配置

`ff7-ime.custom.yaml` 是**示例**，安装器不会安装它。需要改配置时：

1. 在安装包 / 仓库中打开 `ff7-ime.custom.yaml`，按需修改；
2. 复制到 `%APPDATA%\Rime\ff7-ime.custom.yaml`（如果已存在，先备份/合并）；
3. 重新部署。

方案本身已经包含全部默认值（schema 的 `ff7-ime:` 块与 `lua/ff7-ime.lua` 的内置默认），
不创建 custom 文件也能正常工作。

常用配置见 [USAGE.md](USAGE.md)。

---

## 4. 更新

1. 下载新版本（Download ZIP 或 Release 包）并解压；
2. 双击 **`install.cmd`**；
3. 按提示在方案选单里确认勾选，必要时重新部署。

安装器只会覆盖清单里的 5 个运行时文件；内容没变的会跳过，所以你通常只会看到
1–2 个「更新」。用户自己的 `ff7-ime.custom.yaml` 不会被改动。

> 从旧版本升级到自带安装器时，如果之前是用 Plum 装的，5 个文件的行尾可能不同，
> 第一次运行会全部报「更新（旧文件已备份）」并写进 `_backup\`。这是预期行为。

---

## 5. 卸载

双击 **`uninstall.cmd`**。它会：

1. 删除清单里的 5 个运行时文件（与发行版不一致的先备份再删）；
2. 删除 `%APPDATA%\Rime\build\ff7-ime*` 构建产物；
3. 重新部署，让 build 缓存里不再有本方案。

**默认不改 `default.custom.yaml`**。如果你之前在方案选单里勾选过，请在那里取消勾选
并保存；或者：

```bat
uninstall.cmd -PruneSchemaList
```

`-PruneSchemaList` 会只移除 `default.custom.yaml` 中 `ff7-ime` 的 `schema_list` 条目
（先备份原文件），不动其他方案。

想连备份一起清掉：`uninstall.cmd -PurgeBackups`。

`luna_pinyin_simp` 及其他方案的设置不受影响。若只想暂时停用，在方案选单里取消勾选
即可，不必删文件。

---

## 6. 与 `luna_pinyin_simp` 共存

- 安装器只新增 5 个文件，不改动其他方案；
- 方案是否启用由「方案选单设定」里的勾选决定，勾选后 Weasel 自己写入
  `default.custom.yaml` 的 `schema_list`；
- 同一用户目录中 `luna_pinyin_simp` 与本方案可以同时启用，互不覆盖；
- 切换方案：F4 / Ctrl+`。

---

## 7. 故障排查

### 7.1 安装器报「找不到小狼毫安装目录」（退出码 3）

说明注册表、运行中的进程、卸载项、常见位置都没找到含 `WeaselDeployer.exe` 的目录。

- 确认小狼毫确实装了（托盘有图标）；
- 用 `-WeaselDir` 明确指定：

  ```bat
  install.cmd -WeaselDir "D:\Rime\weasel-0.17.4"
  ```

- 或者只复制文件、自己手动重新部署：

  ```bat
  install.cmd -NoDeploy
  ```

### 7.2 安装器报「包不完整」（退出码 2）

`packaging\manifest.txt` 里列的文件没找齐。通常是从压缩包里只解压了一部分。

- 重新完整解压；
- 确认 `packaging\ff7-ime.ps1`、`packaging\manifest.txt`、`ff7-ime.schema.yaml`、
  `lua\` 都在；
- 注意不要只把 `install.cmd` 单独复制出来运行——它依赖同目录的 `packaging\`。

### 7.3 安装器报「目录不可写」（退出码 5）

- 检查 `%APPDATA%\Rime` 的权限；
- 写用户目录**不需要**管理员权限；如果被安全软件拦截，请放行；
- 用 `-RimeUserDir` 指定一个确定可写的目录，然后自行在方案选单里配置。

### 7.4 部署失败 / 部署后产物消失（退出码 4）

- 看日志：`%TEMP%\rime.weasel\rime.weasel.*.log`；
- 手动重新部署：右键小狼毫托盘图标 → **重新部署**；或重新运行一次 `install.cmd`
  （它会自己走无头部署）；
- 若 schema 的 YAML 被手工改坏了，用 `verify.cmd` 比对、重新运行 `install.cmd` 覆盖。

### 7.5 方案列表里没有「魔光键影」

1. 确认 `%APPDATA%\Rime\ff7-ime.schema.yaml` 存在；
2. 关闭并重新打开「方案选单设定」，让它重新扫描；
3. 查看日志中的 YAML 解析错误；
4. 如果文件存在但你之前手动改过 `default.custom.yaml`，检查其中是否有重复的
   `schema_list` 或 `schema_list/+` 键（YAML 后出现的键会覆盖前面的）。

### 7.6 输入只有字母、完全没有候选框（最常见：`lua/` 没被装进去）

症状：方案在列表里、能勾选、能切过去，但打字只出字母或者什么都不出，候选框根本不出现。
日志 `%TEMP%\rime.weasel\rime.weasel.*.log` 里会有：

```
Lua Compoment of autoload error: module 'ff7-ime' not found:
  no file '<用户目录>\lua\ff7-ime.lua'
Lua Compoment of autoload error: module 'ff7-ime_filter' not found: ...
LuaProcessor::ProcessKeyEvent of *ff7-ime_filter error: attempt to call a string value
```

原因几乎总是：**这个方案是用小狼毫内置的「获取更多输入方案」装的，而那条路径不复制
`lua/`**（详见附录 A.2）。本方案的全部匹配逻辑都在 Lua 里，缺了 `lua/` 就只剩一个空壳
schema——按键被处理了，翻译器却产不出任何候选。

处理：

1. 双击 `verify.cmd`，它会直接指出 `lua\` 下缺了哪几个文件；
2. 下载本发行包，双击 `install.cmd` 重装一遍（补齐 5 个运行时文件并自动重新部署）；
3. 右键小狼毫托盘图标 → **重新部署**；
4. 再打 `shenluo`，应出现「神罗」。

补齐之后如果还不通，再按顺序查：

- schema 中是否为 `lua_translator@*ff7-ime`（`*` 不能少）；
- `speller/alphabet` 包含全部小写字母，`delimiter` 为 `'`，无 `algebra`；
- 重新部署并重启 WeaselServer。

### 7.7 `luna_pinyin_simp` 从方案列表消失

通常是 `default.custom.yaml` 被其他工具改写。把它改为同时包含两个方案：

```yaml
patch:
  schema_list:
    - {schema: luna_pinyin_simp}
    - {schema: ff7-ime}
```

然后重新部署。

### 7.8 修改配置后不生效

- Rime 部署签名是**秒级 mtime**；改完等 1–2 秒再部署；
- Lua 模块只在 engine 初始化时加载；部署后建议重启 WeaselServer；
- 检查 `ff7-ime/use_switches`：
  - `false`（默认）：`ff7-ime/fuzzy/*` 等配置生效；
  - `true`：F4 的 `ff7-ime_fuzzy_*` 开关优先。

### 7.9 输入卡顿

- 调小 `ff7-ime/dp_max_candidates`（默认 56，可试 32/40）；
- 调小 `ff7-ime/fallback/max_candidates`（默认 96）或 `fast_max_candidates`（默认 16）；
- 调小 `ff7-ime/typo/max_edit`（默认 2，可试 1）；
- 关闭不需要的模糊音（尤其 `n_l`、`r_l`、`f_h`）。

### 7.10 标点、数字与空格

- 词条中的 `！，·……` 是候选文本的一部分，由 Lua 原样输出；
- 用户不需要输入标点；输入拼音即可；
- 本方案移除了 `punctuator`，标点、数字、符号和空闲时的空格由
  `lua/ff7-ime_filter.lua` 吞掉，不会进入候选或透传给游戏；
- 候选菜单展开时，主键盘数字 1–9 仍由 `selector` 用于选词；
- 需要输入数字、标点或空格时，切换到 `luna_pinyin_simp` 等其他方案。

### 7.11 日志与缓存位置

| 内容 | 路径 |
|---|---|
| Rime/Weasel 日志 | `%TEMP%\rime.weasel\rime.weasel.*.log` |
| 构建产物 | `%APPDATA%\Rime\build\` |
| 安装器备份 | `%APPDATA%\Rime\_backup\ff7-ime-*` |
| Plum 包缓存（仅用 Plum 时） | `%APPDATA%\plum\package\Tanimodori\ff7-ime` |

---

## 8. 兼容性

| 项目 | 值 |
|---|---|
| 前端 | 小狼毫 Weasel 0.17.4 x64 |
| librime | 1.13.1 |
| Lua | 5.4.7（内嵌） |
| 系统 | Windows 10 19045 x64（理论 Windows 11 亦可） |
| 安装依赖 | Windows 自带的 PowerShell 5.1 |
| 运行时依赖 | 无外部运行时 |

---

## 附录 A：用 Plum 安装（可选）

仓库根目录的 `recipe.yaml` 仍然保留，所以也可以用官方包管理器安装。

> **注意：这条路只在装了 Git for Windows（含 Git Bash）时才成立。**
> 没有 Git 时它不会报错，而是**静默降级**成小狼毫内置的 ZIP 路径，而那条路径
> **装不出本方案**（见 A.2）；装了 WSL 的机器上还可能直接失败（见 A.1）。
> 所以除非你确认目标机器有 Git Bash，否则请用第 1 节的 `install.cmd`。

1. 右键小狼毫托盘图标 → 方案选单设定；
2. 点击左下角 **获取更多输入方案…**；
3. 输入：

   ```
   Tanimodori/ff7-ime
   ```

4. 看到 `Installing recipe:` 和 5 个 `Installing:` 即成功；
5. 回到方案选单勾选「魔光键影」，重新部署。

### A.1 控制台报 `/bin/bash: ...\plum/rime-install: No such file or directory`

这不是包或网络问题，而是 Windows 解析 `bash` 的顺序导致的：

- 「获取更多输入方案」以 `C:\Windows\System32` 为工作目录启动 `rime-install.bat`；
- 该目录里正好有 WSL 的 `bash.exe`（`C:\Windows\System32\bash.exe`）。Windows
  解析命令时先查当前目录、再查 PATH，所以它抢在了 Git Bash 前面；
- 安装器把 `/usr/bin/env bash` 脚本交给 WSL 的 bash 后，WSL 不认识 `C:\...` 路径，
  于是报 “No such file or directory”。

上游 rime/plum 至今未修（issue #84）。规避方法：先进入一个普通目录再手动运行安装器。

```bat
cd /d %APPDATA%\Rime
"C:\Program Files\Rime\weasel-0.17.4\rime-install.bat" Tanimodori/ff7-ime
```

或者干脆用本包自带的 `install.cmd`（见第 1 节），完全不碰 bash。

### A.2 输入只有字母、没有候选框：内置 ZIP 路径不复制 `lua/`

**没装 Git for Windows 时，`Tanimodori/ff7-ime` 会静默降级到内置 ZIP 路径**，这是这条路
最需要警惕的地方。`rime-install.bat` 的判断是：

```bat
if not defined use_plum if "%has_git_bash%" == "1" set use_plum=1
```

找不到 Git Bash 时 `use_plum` 保持关闭，它于是不再调用 Plum，而是把仓库 ZIP 下载到
`%TEMP%`、解压，然后按一份**白名单**复制到用户目录：

```
*.yaml
*.txt
opencc\*.json
opencc\*.ocd
opencc\*.txt
```

`lua\` 不在白名单里。后果是：

- 用户目录里出现 `ff7-ime.schema.yaml`、`ff7-ime.custom.yaml`、`recipe.yaml`
  （都是根目录 `*.yaml`），**唯独没有 `lua\`**；
- 打字只出字母、完全没有候选框，日志里是 `module 'ff7-ime' not found`；
- 根目录那份示例 `ff7-ime.custom.yaml` 被一并写进用户目录，可能覆盖你自己的配置。

怎么判断自己走的是哪条路：

| 线索 | Plum 路径 | 内置 ZIP 路径（坏） |
|---|---|---|
| 控制台输出 | `Installing recipe:` + 5 个 `Installing:` | `Unpacking ...` |
| `%APPDATA%\plum` | 存在（有克隆下来的包） | 不存在 |
| 用户目录 | 只有 5 个运行时文件 | 多出 `recipe.yaml`、`ff7-ime.custom.yaml`，缺 `lua\` |

处理：改用本包自带的 `install.cmd`（见第 1 节）。它不依赖 Git、不需要联网，
而且会把这 5 个文件补齐并重新部署。修好之后症状和排查见 7.6。

---

## 附录 B：完全手动安装

不想运行任何脚本时，把下面 5 个文件复制到 Rime 用户目录（默认
`%APPDATA%\Rime`），保持 `lua\` 子目录结构，然后重新部署：

```
ff7-ime.schema.yaml            → %APPDATA%\Rime\ff7-ime.schema.yaml
lua/ff7-ime.lua                → %APPDATA%\Rime\lua\ff7-ime.lua
lua/ff7-ime_matcher.lua        → %APPDATA%\Rime\lua\ff7-ime_matcher.lua
lua/ff7-ime_data.lua           → %APPDATA%\Rime\lua\ff7-ime_data.lua
lua/ff7-ime_filter.lua         → %APPDATA%\Rime\lua\ff7-ime_filter.lua
```

用户目录不在默认位置时，先确认它在哪里：注册表
`HKCU\SOFTWARE\Rime\Weasel` 的 `RimeUserDir`（没有该值就是 `%APPDATA%\Rime`）。

最后在方案选单设定里勾选「魔光键影」并重新部署。
