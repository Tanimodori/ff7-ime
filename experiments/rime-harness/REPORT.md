# REPORT — librime 1.13.1 C API 测试夹具（rime-harness）

日期：2026-10-28
目标：不依赖真实用户配置，用 `rime.dll` 的 C API 驱动 Rime，读取组合/候选/提交，
为“魔光键影”提供可批量调用的验收工具。

**结论：已跑通。** `luna_pinyin_simp` 输入 `nihao` 得到候选
`你好 / 妳好 / 逆号 / 拟好 / 你`，选 0 提交 `你好`；`test_luna.py` 44 项检查全通过。
自定义 schema + 自定义 dict 放在临时 user 目录、共享目录用安装 data 的流程也已验证。

---

## 1. 环境事实

| 项目 | 值 |
|---|---|
| OS | Windows 10.0.19045 x64 |
| Rime 前端 | Weasel 0.17.4 x64，`C:\Program Files\Rime\weasel-0.17.4` |
| DLL | `rime.dll` 3,524,096 字节，PE32+ (0x8664)，7 个节 |
| librime | 1.13.1（DLL 内含字符串 `1.13.1`） |
| Python | 3.14.7 (MSC v.1944 64 bit)，`C:\Python314\python.exe` |
| 共享数据 | `...\data`（无 `build/`，必须自行部署） |

### 1.1 导出表分析（关键）

`rime.dll` 共 723 个导出名，其中 83 个 `Rime*`。**不是** `rime_api.h` 里的全部
函数都能直接 `GetProcAddress`：

- 有：`RimeSetup`、`RimeInitialize`、`RimeFinalize`、`RimeStartMaintenance`、
  `RimeJoinMaintenanceThread`、`RimeIsMaintenancing`、`RimeCreateSession`、
  `RimeDestroySession`、`RimeProcessKey`、`RimeSimulateKeySequence`、
  `RimeGetContext`、`RimeFreeContext`、`RimeGetCommit`、`RimeFreeCommit`、
  `RimeGetStatus`、`RimeFreeStatus`、`RimeSetOption`、`RimeGetOption`、
  `RimeSelectCandidate`、`RimeSelectCandidateOnCurrentPage`、
  `RimeGetSchemaList`、`RimeFreeSchemaList`、`RimeGetSharedDataDir` 等。
- **没有** `RimeGetVersion`（`src/rime_api.cc` 里它没有 `RIME_API` 修饰，C++ 链接，
  未导出）。
- **没有** `RimeJoinMaintenance`；正确名字是 **`RimeJoinMaintenanceThread`**
  （`void(void)`）。
- **没有** `RimeGetInput`；原始输入用 `RimeGetContext` 的 `composition.preedit`
  （或 `RimeGetProperty`，未用）。
- 该构建导出的是**传统（legacy）C API**，即 `rime_api_stdbool.h` 未启用：
  `Bool` = `int`（4 字节）。没有 `_stdbool` 后缀的符号。
- 另有 C++ 修饰名导出 `?RimeGetKeycodeByName@@YAHPEBD@Z` /
  `?RimeGetModifierByName@@YAHPEBD@Z`，夹具优先用它们解析 `{Key_Name}`，
  保证与 librime 自身 `KeyEvent::Parse` 行为一致。
- DLL 内含 `lua_translator` / `lua_filter` / `lua_processor` / `lua_segmentor`
  字符串及 `lua_gears.cc`、`luaL_*` 符号 → 该 Weasel 构建静态链接了 librime-lua
  （本夹具未专项验证 Lua 方案）。

---

## 2. 结构体布局（Windows x64）

来源：librime 1.13.1 `src/rime_api.h`，用 `ctypes.Structure` 复刻，启动时断言
`sizeof`。**`Bool` 是 `int`**，结构体按 8 字节对齐。

```python
class RimeTraits(Structure):          # sizeof = 96, data_size = 92
    data_size            int           # offset 0
    shared_data_dir      char*         # 8
    user_data_dir        char*         # 16
    distribution_name    char*         # 24
    distribution_code_name char*       # 32
    distribution_version char*         # 40
    app_name             char*         # 48
    modules              char**        # 56
    min_log_level        int           # 64（+4 padding）
    log_dir              char*         # 72
    prebuilt_data_dir    char*         # 80
    staging_dir          char*         # 88

class RimeComposition(Structure):     # sizeof = 24
    length, cursor_pos, sel_start, sel_end: int   # 0,4,8,12
    preedit: char*                                 # 16

class RimeCandidate(Structure):       # sizeof = 24
    text: char*        # 0
    comment: char*     # 8
    reserved: void*    # 16

class RimeMenu(Structure):            # sizeof = 40
    page_size: int                    # 0
    page_no: int                      # 4
    is_last_page: int (Bool)          # 8
    highlighted_candidate_index: int  # 12
    num_candidates: int               # 16
    candidates: RimeCandidate*        # 24
    select_keys: char*                # 32

class RimeContext(Structure):         # sizeof = 88, data_size = 84
    data_size: int                    # 0
    composition: RimeComposition      # 8
    menu: RimeMenu                    # 32
    commit_text_preview: char*        # 72
    select_labels: char**             # 80

class RimeStatus(Structure):          # sizeof = 56, data_size = 52
    data_size: int                    # 0
    schema_id: char*                  # 8
    schema_name: char*                # 16
    is_disabled: int                  # 24
    is_composing: int                 # 28
    is_ascii_mode: int                # 32
    is_full_shape: int                # 36
    is_simplified: int                # 40
    is_traditional: int               # 44
    is_ascii_punct: int               # 48（+4 padding）

class RimeCommit(Structure):          # sizeof = 16, data_size = 12
    data_size: int                    # 0
    text: char*                       # 8
```

`RimeSchemaList`: `size_t size; RimeSchemaListItem* list;`，
item = `{char* schema_id; char* name; void* reserved;}`。

### 2.1 `data_size` 语义（最容易踩的坑）

`RIME_STRUCT_INIT(Type, var)` 把 `data_size` 设为 `sizeof(Type) - sizeof(data_size)`，
即上表第二列（96→92、88→84、56→52、16→12），**不是** `sizeof(Type)`。

librime 侧的行为：

```c
if (!context || context->data_size <= 0) return False;
RIME_STRUCT_CLEAR(*context);   // memset(&ctx + 4, 0, data_size)
...
if (RIME_STRUCT_HAS_MEMBER(*context, context->commit_text_preview)) { ... }
```

`RIME_STRUCT_HAS_MEMBER` 用 `data_size` 判断“调用方是否提供了该尾字段”。若把
`data_size` 设小，1.13 新增的 `commit_text_preview` / `select_labels` 不会被填充，
`FreeContext` 也不会释放它们。夹具统一调用 `_new_struct()` 设为 `sizeof-4`。

---

## 3. 调用顺序

```
LoadLibrary(rime.dll)
  RimeSetup(&traits)              # 必须：应用 log_dir/min_log_level（SetupDeployer）
  RimeInitialize(&traits)         # LoadModules + StartService
  [首次/变更时]
  RimeStartMaintenance(True)      # 异步启动维护线程
  RimeJoinMaintenanceThread()     # 等待部署完成
  RimeCreateSession() -> sid
  RimeSelectSchema(sid, "luna_pinyin_simp")
  RimeSetOption(sid, "zh_simp", 1)          # 可选
  for key in keys:
      RimeProcessKey(sid, keycode, mask)    # keycode = ASCII / X11 keysym
      RimeGetContext(sid, &ctx) ... RimeFreeContext(&ctx)   # 每步读取
  RimeSelectCandidateOnCurrentPage(sid, 0)  # 可选（页内下标）
  RimeGetCommit(sid, &commit) ... RimeFreeCommit(&commit)
  RimeGetStatus(sid, &status) ... RimeFreeStatus(&status)
  RimeDestroySession(sid)
  RimeFinalize()
```

注意事项：

- `RimeInitialize` 只调用 `SetupDeployer + LoadModules + StartService`，**不调用
  `SetupLogging`**。不先 `RimeSetup` 的话 `log_dir/min_log_level` 不生效，glog
  会把 INFO 写到 stderr，且出现
  `WARNING: Logging before InitGoogleLogging()`。加上 `RimeSetup` 后 stdout/stderr
  干净（实测 stderr 0 字节）。
- `RimeStartMaintenance` 返回 `True` 只代表任务已启动；必须
  `RimeJoinMaintenanceThread`。部署结果通过通知回调
  `(type="deploy", value="start"/"success"/"failure")` 获得，夹具会收集并校验。
- `RimeFinalize` 内部也会 join 维护线程；夹具先 join 再 finalize，避免重复等待。
- `RimeProcessKey` 的 keycode 是 **X11 keysym**：小写字母/数字/ASCII 标点就是
  ASCII 码；`space=0x20`、`Return=0xff0d`、`BackSpace=0xff08`、
  `Page_Down=0xff56`、`Left/Right/Up/Down=0xff51..0xff54`。修饰键 mask：
  `Shift=1, Lock=2, Control=4, Alt=8, Mod2=16, Mod3=32, Mod4=64, Mod5=128,
  Super=1<<26, Hyper=1<<27, Meta=1<<28`。**不是** Windows VK 码。
- `RimeSimulateKeySequence(sid, "nihao{space}")` 可作为逐键 `ProcessKey` 的替代，
  它使用 librime 自己的解析器（支持 `{Control+a}`）。

---

## 4. 部署机制

- 共享目录无 `build/`，所以第一次必须部署。
- `RimeStartMaintenance(True)` 依次跑 `installation_update`、`workspace_update`、
  `user_dict_upgrade`、`cleanup_trash`：
  - 读共享 `default.yaml` + 用户 `default.custom.yaml`，生成 `<user>/build/default.yaml`；
  - 对 `schema_list` 中每个 schema 部署（含 `dependencies:`，例如
    `luna_pinyin_simp` 会带上 `stroke` 做反查）；
  - 词典编译产物写 `<user>/build/`（`luna_pinyin.table.bin` 约 13 MB、
    `luna_pinyin_simp.prism.bin`、`stroke.*`）。
- **schema/dict 可以只放在 user 目录**：部署解析器同时搜索 user_data_dir 与
  shared_data_dir。实测在临时 user 目录放 `ff7-ime_test2.schema.yaml` +
  `ff7-ime_test2.dict.yaml`，共享目录用安装 data，输入：
  - `nihao` → `你好`（来自自定义 dict）
  - `moguangjianying` → `魔光键影`
  这是给“魔光键影”做回归测试的推荐姿势：**项目文件进临时 user 目录，系统目录零改动**。
- 部署只写 `--user`/`--staging`；`--shared` 可以只读（Program Files 下没问题）。
- 缓存：`<user>/.rime_harness_state.json` 记录 schema、目录、YAML 源文件
  `size+mtime` 签名。`--deploy auto` 命中则跳过；`always` 强制；`never` 不部署。
- 实测：首次 `luna_pinyin_simp` 部署 3.3–4.0 s；无变化强制全量 ~0.3 s；
  已部署时整次 CLI 进程 0.3–0.5 s。

---

## 5. 内存管理

librime 在 C API 里分配字符串/数组，必须由对应 `Free` 释放：

| 读取 | 释放 |
|---|---|
| `RimeGetContext`（preedit、candidates[i].text/comment、candidates 数组、select_keys、commit_text_preview、select_labels） | `RimeFreeContext`（一次释放全部） |
| `RimeGetCommit` | `RimeFreeCommit` |
| `RimeGetStatus` | `RimeFreeStatus` |
| `RimeGetSchemaList` | `RimeFreeSchemaList` |

夹具每次 `context()`/`status()`/`commit_text()` 都在 `try/finally` 里配对释放，
`ctypes` 只读不 free。`RimeGetCommit` 读取时会 `ResetCommitText()`，**只能读一次**。

---

## 6. 踩过的坑

1. **`RimeGetVersion`/`RimeJoinMaintenance` 不存在**：按导出表找实际名字
   （`RimeJoinMaintenanceThread`），不要照抄 `rime_api.h` 的函数名。
2. **`Bool` 宽度**：该 DLL 是 legacy API，`Bool=int`。若误用 `c_bool`（1 字节），
   `RimeMenu` 后续字段全部错位，候选数量会变成天文数字或崩溃。
3. **`data_size` 必须 = `sizeof-4`**：否则 `RimeGetContext` 直接返回 False
   （`data_size<=0`）或丢尾字段。
4. **不调用 `RimeSetup`**：日志配置不生效，stderr 被 INFO 淹没；加上后干净。
5. **部署是异步的**：只调 `RimeStartMaintenance` 不 join，紧接着
   `CreateSession` 会读到半成品 `build/`（schema 未就绪）。
6. **部署签名把状态文件自己算进去**：第一版把 `.rime_harness_state.json`
   纳入签名，导致每次 `auto` 都判定“变化”→ 永远重新部署。必须排除
   `installation.yaml`、`user.yaml`、`*.userdb/`、`logs/`、状态文件本身。
7. **`ascii_mode` 不产生 commit**：`RimeProcessKey` 返回 False（透传给宿主），
   `consumed=0`、`commit=null`。验证开关请看 `status.is_ascii_mode`/`options`。
8. **候选索引语义**：`RimeSelectCandidate` 是候选总表下标；
   `RimeSelectCandidateOnCurrentPage` 才是当前页下标。JSON 里的
   `candidates[].index` 是页内下标，所以 `--select` 用后者。
9. **`RimeGetCommit` 是破坏性读取**：中间步骤反复读会把提交文本读没。
10. **翻页要按键**：`{Page_Down}`（0xff56）或 `-`/`=`，没有独立的 C API。
11. **非 ASCII 路径**：实测中文 user 目录可用（`%TEMP%\魔光键影`），
    路径按 UTF-8 传入（ctypes `c_char_p`）。
12. **`--schema` 会覆盖 `default.custom.yaml`**：夹具为每个 user 目录只保留一个
    schema 以缩短部署；需要自行管理时用 `--no-write-custom`。
13. **schema 依赖会被一起构建**：`luna_pinyin_simp` 依赖 `stroke`，`data/build`
    不存在时首次部署约 3.5 s 是正常的；直接部署安装 data 默认的 8 个方案会慢得多
    （夹具默认把 schema_list 收窄到一个）。

---

## 7. 验证结果

### 7.1 任务给定命令（首次，空 user 目录）

```bat
python rime_harness.py --shared "C:\Program Files\Rime\weasel-0.17.4\data" ^
  --user "%TEMP%\ff7-ime-test" --schema luna_pinyin_simp --input nihao --json
```

输出（截取）：

```json
{"ok":true,"input":"nihao","schema":"luna_pinyin_simp",
 "preedit":"ni hao",
 "candidates":[{"index":0,"text":"你好","comment":""},
               {"index":1,"text":"妳好","comment":""},
               {"index":2,"text":"逆号","comment":""},
               {"index":3,"text":"拟好","comment":""},
               {"index":4,"text":"你","comment":""}],
 "commit":null, ...}
```

`meta.deployed=true`、`meta.deploy_seconds≈3.5`、`deploy_events` 含
`start`/`success`、`status.is_composing=true`、`page_size=5`。

加 `--select 0` 后 `commit="你好"`；完整对象见 `sample_output.json`。

### 7.2 `test_luna.py`（44 项）

```
[PASS] first run: 你好 in candidates
[PASS] first run: commit after selecting 0
[PASS] repeat run: deploy skipped
[PASS] repeat run: stable candidate order
[PASS] zh_simp=0: commit 漢字
[PASS] zh_simp=1: commit 汉字
[PASS] paging: page number
[PASS] paging: selecting page-relative 0 commits that candidate
[PASS] ascii_mode: status flag
[PASS] select-absolute 0: commit matches candidate 0
[PASS] bad schema: exit code
[PASS] real Rime user dir untouched
...
44 checks, 0 failed, 5.4s
```

覆盖：首次部署、二次复用跳过部署、候选顺序稳定性、`zh_simp` 开关（简/繁）、
翻页、页内选择、`--select-absolute`、`ascii_mode`、`--list-schemas`、
错误 schema、`--deploy never` 空目录报错、真实用户目录未被修改。
完整日志见 `sample_test_luna.log`。

### 7.3 其它实测

| 场景 | 结果 |
|---|---|
| 换 schema `luna_pinyin`（同一 user 目录） | 自动重新部署，候选 `你好/妳好/逆號/擬好/你` |
| 自定义 schema（user 目录）+ stock shared | 部署成功，`schema=ff7-ime_test` |
| 自定义 schema + 自定义 dict（user 目录） | `nihao→你好`、`moguangjianying→魔光键影` |
| 非 ASCII 临时目录 `%TEMP%\魔光键影` | 正常工作 |
| 真实 `%APPDATA%\Rime`（WeaselServer 运行中） | 测试前后快照一致 |
| `--fresh-user` / 默认 user 目录 | 正常 |
| 错误路径（候选越界、未知键名、非法 option、非 ASCII 输入） | 退出码 1 + `{"ok":false,"error":...}` |

---

## 8. 给“魔光键影”的回归测试方案

1. **把共享目录固定为安装 data**（或项目 `dist\` 若它是完整 data 目录，含
   `default.yaml`、`pinyin.yaml`、`opencc/` 等）。
2. **每个用例一个临时 user 目录**（或一套只读用例复用一个已部署目录）：
   - 项目 `*.schema.yaml` / `*.dict.yaml` / Lua 文件放进去；
   - 夹具自动写 `default.custom.yaml`，`--schema` 指定方案，首次自动部署。
3. **用例形式**：`rime_harness.py ... --input "<键序列>" --select N --json`，
   断言：
   - `candidates[*].text/comment`（顺序、注释、提示码）；
   - `preedit` / `commit_text_preview`；
   - `commit`（选候选后）；
   - `status` / `options`（开关、简繁、全半角、标点）；
   - `page`（翻页行为）；
   - `meta.deployed`（批量时断言 false 以确认复用缓存）。
4. **性能**：预热一次后每条用例 0.3~0.5 s；几十条用例可接受。更大量可用
   `rime_harness.RimeHarness` 在一个进程里开多个 session。
5. **排除用户词典干扰**：不同用例用不同 user 目录，或每轮清空
   `<user>/*.userdb/`；选择候选会写入用户词典并影响下次排序（已验证：
   选过 `妳` 后 `ni` 的首选可能变化）。
6. **变更后重部署**：编辑了 schema/dict 后 `--deploy always`，或依赖默认 `auto`
   的 mtime 签名（注意 `touch` 也会触发）。
7. **CI 形态**：`python test_luna.py` 退出码即结果；JSON 输出可直接入库为 fixture。

---

## 9. 复现步骤（从零）

```bat
:: 1) 快速验证
python experiments\rime-harness\rime_harness.py ^
  --shared "C:\Program Files\Rime\weasel-0.17.4\data" ^
  --user "%TEMP%\ff7-ime-test" --schema luna_pinyin_simp ^
  --input nihao --json

:: 2) 验收测试
python experiments\rime-harness\test_luna.py

:: 3) 自定义方案（把 yaml 放进临时用户目录）
set U=%TEMP%\ff7-ime-project
mkdir "%U%"
copy /y dist\*.schema.yaml "%U%\"
copy /y dist\*.dict.yaml   "%U%\"
python experiments\rime-harness\rime_harness.py ^
  --shared "C:\Program Files\Rime\weasel-0.17.4\data" ^
  --user "%U%" --schema ff7-ime --input nihao --json
```

无需管理员权限，无需安装/重启 Weasel，不修改 `%APPDATA%\Rime`。
