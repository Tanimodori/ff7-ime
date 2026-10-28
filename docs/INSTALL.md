# 安装、更新与卸载

> 适用：小狼毫 Weasel 0.17.4（Windows x64，librime 1.13.1）。
> 本方案通过 **Rime 官方包管理器（Plum）** 安装，不需要额外的安装脚本。

---

## 1. 安装

### 1.1 前置条件

| 项目 | 要求 |
|---|---|
| 小狼毫 | 0.17.4 x64（自带 `rime-install.bat`） |
| Git for Windows | 需要其中的 `git` 与 `bash`；Plum 依赖它们 |
| 网络 | 首次安装需要访问 GitHub |

> 小狼毫的“获取更多输入方案”按钮实际运行安装目录下的 `rime-install.bat`。
> 检测到 Git Bash 时它会把安装交给 Plum；没有 Git Bash 时只会解压 zip 并复制
> 根目录的 `*.yaml`/`*.txt`，**不会复制 `lua/`**，方案会缺少翻译器。
> 该 ZIP 路径还会复制根目录的示例 `ff7-ime.custom.yaml`，可能覆盖用户已有配置；
> 因此不要用它安装本方案。
> 如果目标机器没有 Git，可先在同一个控制台输入 `git` 让官方安装器自动安装，
> 关闭控制台后重新打开，再安装本方案。

### 1.2 通过“获取更多输入方案”安装

1. 确认仓库公开；安装标识为 **`Tanimodori/ff7-ime`**。如果你 fork 或改名，
   换成自己的 `用户名/仓库名`。
2. 右键小狼毫托盘图标 → **方案选单设定**（或运行 `WeaselDeployer.exe`）。
3. 点击左下角 **获取更多输入方案…**，会打开标题为 **Rime package installer** 的控制台。
4. 在 `Enter package name, URL, user/repo or downloaded ZIP to install:` 后输入：

   ```
   Tanimodori/ff7-ime
   ```

   按回车。
5. 看到类似输出即表示安装成功：

   ```
   Installing recipe: Tanimodori/ff7-ime
   Installing: lua/ff7-ime.lua
   Installing: lua/ff7-ime_data.lua
   Installing: lua/ff7-ime_matcher.lua
   Installing: ff7-ime.schema.yaml
   Updated ~ 4 files from 1 packages in 'C:\Users\<你>\AppData\Roaming\Rime'
   ```

6. 关闭控制台。方案选单设定窗口会自动刷新；在列表中找到 **魔光键影** 并勾选，
   然后点击 **中** 保存。
7. 如果候选没有立即生效，右键托盘 → **重新部署**，或重启 WeaselServer。
8. 在任意输入框输入 `shenluo`，应出现“神罗”；输入 `lkcc`，应出现
   “我们会立刻彻底铲除你们！”。

> 如果安装器输出 4 个 `Installing:` 但完全无法打字，先检查
> `%APPDATA%\Rime\build\ff7-ime.schema.yaml` 是否存在。缺失说明只复制了文件、
> 还没有完成部署；执行第 7 步并在必要时重启 WeaselServer 即可恢复。

### 1.3 安装器做了什么

仓库根目录的 `recipe.yaml` 告诉 Plum 只安装 4 个运行时文件：

```
ff7-ime.schema.yaml
lua/ff7-ime.lua
lua/ff7-ime_matcher.lua
lua/ff7-ime_data.lua
```

安装目标是 Rime 用户目录（默认 `%APPDATA%\Rime`），并保留 `lua/` 子目录。
安装器**不会**：

- 改写 `default.custom.yaml`（方案是否启用由第 6 步的勾选决定）；
- 覆盖 `ff7-ime.custom.yaml`（通过 Plum 安装时；用户配置示例见第 3 节）；
- 安装 `data/`、`tools/`、`tests/` 或 `docs/`（它们只用于构建与维护）。

这些文件也足以运行：词库数据在 `lua/ff7-ime_data.lua`，`data/dict.txt` 只是重建数据的源文件。

> **不需要 opencc/**：本方案没有启用 `simplifier`，输出文本已经是简体；安装器里
> `opencc/*` 的复制规则与本包无关。

---

## 2. 验证安装

### 2.1 检查文件

在 PowerShell 中：

```powershell
$rime = Join-Path $env:APPDATA 'Rime'
Get-ChildItem "$rime\ff7-ime.schema.yaml",
              "$rime\lua\ff7-ime.lua",
              "$rime\lua\ff7-ime_matcher.lua",
              "$rime\lua\ff7-ime_data.lua"
```

四个文件都应存在。

### 2.2 检查方案列表

```powershell
Select-String -Path "$env:APPDATA\Rime\build\default.yaml" -Pattern 'ff7-ime'
```

在方案选单里勾选过“魔光键影”后，这里才会有条目。若没有，回到第 1.2 节第 6 步。

### 2.3 检查输入

在记事本中测试：

| 输入 | 期望 top1 |
|---|---|
| `shenluo` | 神罗 |
| `senluo` | 神罗（模糊音） |
| `nuolei` | 雷诺（音节换位） |
| `lkcc` | 我们会立刻彻底铲除你们！ |
| `meishao` | 有时是出手相助的美少女忍者！ |

---

## 3. 用户配置

`ff7-ime.custom.yaml` 是**示例**，通过 Plum 安装时不会安装它。如果使用 ZIP 路径，
根目录的示例文件也会被复制，请先备份已有的用户配置。需要改配置时：

1. 在仓库中打开 `ff7-ime.custom.yaml`，按需修改；
2. 复制到 `%APPDATA%\Rime\ff7-ime.custom.yaml`（如果已存在，先备份/合并）；
3. 重新部署。

方案本身已经包含全部默认值（schema 的 `ff7-ime:` 块与 `lua/ff7-ime.lua` 的内置默认），
不创建 custom 文件也能正常工作。

常用配置见 [USAGE.md](USAGE.md)。

---

## 4. 更新

再次打开 **获取更多输入方案**，输入同一个标识：

```
Tanimodori/ff7-ime
```

Plum 会更新 `%APPDATA%\plum\package\Tanimodori\ff7-ime` 并只覆盖清单中的 4 个文件。
随后在方案选单设定中确认勾选并重新部署。用户自己的 `ff7-ime.custom.yaml`
不会被改动。

---

## 5. 卸载

官方安装器没有卸载命令，按 Rime 的标准方式处理：

1. 打开 **方案选单设定**，取消勾选 **魔光键影**，点击 **中**；
2. 删除以下文件（存在才删）：

   ```
   %APPDATA%\Rime\ff7-ime.schema.yaml
   %APPDATA%\Rime\lua\ff7-ime.lua
   %APPDATA%\Rime\lua\ff7-ime_matcher.lua
   %APPDATA%\Rime\lua\ff7-ime_data.lua
   %APPDATA%\Rime\ff7-ime.custom.yaml   # 如果创建过
   ```

3. 重新部署。

`luna_pinyin_simp` 及其他方案的设置不受影响。若只想暂时停用，取消勾选即可，不必删文件。

---

## 6. 与 `luna_pinyin_simp` 共存

- 安装器只新增 4 个文件，不改动其他方案；
- 方案是否启用由“方案选单设定”里的勾选决定，勾选后 Weasel 自己写入
  `default.custom.yaml` 的 `schema_list`；
- 同一用户目录中 `luna_pinyin_simp` 与本方案可以同时启用，互不覆盖；
- 切换方案：F4 / Ctrl+`。

---

## 7. 故障排查

### 7.1 控制台提示找不到包

- 确认标识拼写为 `Tanimodori/ff7-ime`（或你的实际 `用户名/仓库名`）；
- 确认仓库是**公开**的；Plum 通过 `https://github.com/<user>/<repo>.git` 克隆；
- 私有仓库需要目标机器已配置 GitHub 凭据，官方安装器不会提示登录。

### 7.2 控制台输出 `Unpacking ...` 而不是 `Installing recipe ...`

说明没有使用 Plum，而是走了内置 ZIP 安装路径。该路径只复制根目录
`*.yaml`/`*.txt` 和 `opencc/`，**不会复制 `lua/`**，因此输入不会有候选；
它还会复制根目录的示例 `ff7-ime.custom.yaml`，可能覆盖已有用户配置。

处理：

1. 安装 Git for Windows（含 Git Bash）；
2. 关闭并重新打开控制台；
3. 重新输入 `Tanimodori/ff7-ime`，确认输出为 `Installing recipe:`。

### 7.3 方案列表里有“魔光键影”，但输入没有候选

1. 检查 `%APPDATA%\Rime\lua\ff7-ime.lua`、`ff7-ime_matcher.lua`、`ff7-ime_data.lua` 是否存在；
2. 检查 schema 中是否为 `lua_translator@*ff7-ime`（`*` 不能少）；
3. 查看日志 `%TEMP%\rime.weasel\rime.weasel.*.log` 中的
   `lua_translator` / `lua error` / `module not found`；
4. 确认 `speller/alphabet` 包含全部小写字母，`delimiter` 为 `'`，无 `algebra`；
5. 重新部署并重启 WeaselServer。

### 7.4 方案列表里没有“魔光键影”

1. 确认 `%APPDATA%\Rime\ff7-ime.schema.yaml` 存在；
2. 关闭并重新打开“方案选单设定”，让它重新扫描；
3. 查看日志中的 YAML 解析错误；
4. 如果文件存在但你之前手动改过 `default.custom.yaml`，检查其中是否有重复的
   `schema_list` 或 `schema_list/+` 键（YAML 后出现的键会覆盖前面的）。

### 7.5 `luna_pinyin_simp` 从方案列表消失

通常是 `default.custom.yaml` 被其他工具改写。把它改为同时包含两个方案：

```yaml
patch:
  schema_list:
    - {schema: luna_pinyin_simp}
    - {schema: ff7-ime}
```

然后重新部署。

### 7.6 修改配置后不生效

- Rime 部署签名是**秒级 mtime**；改完等 1–2 秒再部署；
- Lua 模块只在 engine 初始化时加载；部署后建议重启 WeaselServer；
- 检查 `ff7-ime/use_switches`：
  - `false`（默认）：`ff7-ime/fuzzy/*` 等配置生效；
  - `true`：F4 的 `ff7-ime_fuzzy_*` 开关优先。

### 7.7 输入卡顿

- 调小 `ff7-ime/dp_max_candidates`（默认 56，可试 32/40）；
- 调小 `ff7-ime/fallback/max_candidates`（默认 96）或 `fast_max_candidates`（默认 16）；
- 调小 `ff7-ime/typo/max_edit`（默认 2，可试 1）；
- 关闭不需要的模糊音（尤其 `n_l`、`r_l`、`f_h`）。

### 7.8 标点/间隔号

- 词条中的 `！，·……` 是候选文本的一部分，由 Lua 原样输出；
- 用户不需要输入标点；输入拼音即可；
- 标点键由 Rime 的 `punctuator` 处理，不会影响候选文本。

### 7.9 日志与缓存位置

| 内容 | 路径 |
|---|---|
| Rime/Weasel 日志 | `%TEMP%\rime.weasel\rime.weasel.*.log` |
| 构建产物 | `%APPDATA%\Rime\build\` |
| Plum 包缓存 | `%APPDATA%\plum\package\Tanimodori\ff7-ime` |

---

## 8. 兼容性

| 项目 | 值 |
|---|---|
| 前端 | 小狼毫 Weasel 0.17.4 x64 |
| librime | 1.13.1 |
| Lua | 5.4.7（内嵌） |
| 系统 | Windows 10 19045 x64（理论 Windows 11 亦可） |
| 安装依赖 | Git for Windows（含 Git Bash） |
| 运行时依赖 | 无外部运行时 |
