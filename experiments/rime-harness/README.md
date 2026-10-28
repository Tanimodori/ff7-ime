# rime-harness —  librime C API 自动化测试夹具

用 Python `ctypes` 直接调用 `rime.dll` 导出的 librime 1.13.1 C API，在**完全隔离的临时
用户目录**里部署 schema、逐键输入、读取候选/组合/提交文本，并输出稳定的 JSON。

已验证环境：

| 项目 | 值 |
|---|---|
| Rime 前端 | 小狼毫 Weasel 0.17.4 x64 |
| `rime.dll` | `C:\Program Files\Rime\weasel-0.17.4\rime.dll`（librime 1.13.1） |
| 共享数据 | `C:\Program Files\Rime\weasel-0.17.4\data` |
| Python | 3.14.7 x64（3.8+ 应均可，必须 64 位） |

当前状态：**跑通**。`nihao` → 候选 `你好/妳好/逆号/拟好/你`，选 0 提交 `你好`；
`test_luna.py` 44 项检查全部通过（约 5 秒）。详见 [REPORT.md](REPORT.md)。

---

## 文件

| 文件 | 说明 |
|---|---|
| `rime_harness.py` | 夹具本体 + CLI；也可作为模块 import |
| `test_luna.py` | `luna_pinyin_simp` 端到端验收测试 |
| `sample_output.json` | 一次真实运行的完整 JSON（`--input nihao --select 0`） |
| `sample_test_luna.log` | `test_luna.py` 的一次完整输出 |
| `REPORT.md` | 结构体布局、调用顺序、坑、验证结果、回归测试方案 |

---

## 快速开始

```bat
cd /d "D:\Tanimodori\Projects\@FF14\ff7-ime\experiments\rime-harness"

python rime_harness.py ^
  --shared "C:\Program Files\Rime\weasel-0.17.4\data" ^
  --user "%TEMP%\mgjy-test" ^
  --schema luna_pinyin_simp ^
  --input nihao --json
```

首次运行会自动部署（约 3~4 秒），之后同一 `--user` 会跳过部署（约 0.4 秒）。

选第一个候选并拿到提交文本：

```bat
python rime_harness.py --shared "C:\Program Files\Rime\weasel-0.17.4\data" ^
  --user "%TEMP%\mgjy-test" --schema luna_pinyin_simp ^
  --input nihao --select 0 --json --pretty
```

人类可读模式（去掉 `--json`）：

```
input      : nihao
schema     : luna_pinyin_simp (朙月拼音·简化字)
preedit    : 'ni hao'  cursor=6  len=6
page       : 0  size=5  last=False  highlighted=0
candidates :
   0. 你好
   1. 妳好
   2. 逆号
   3. 拟好
   4. 你
commit     : '你好'
```

跑验收测试：

```bat
python test_luna.py
```

---

## 输出 JSON 契约

成功时 stdout **只有一个 JSON 对象**（`--pretty` 时为多行）。关键字段：

```jsonc
{
  "ok": true,
  "input": "nihao",                  // 传入的键序列
  "schema": "luna_pinyin_simp",      // 实际生效的 schema_id
  "schema_name": "朙月拼音·简化字",
  "preedit": "ni hao",               // 当前组合串（librime 格式化后的 preedit）
  "composition": {"length": 6, "cursor_pos": 6, "sel_start": 0, "sel_end": 6},
  "commit_text_preview": "你好",      // librime 1.13 的提交预览
  "page": 0,                        // 当前候选页（0 起）
  "page_size": 5,
  "is_last_page": false,
  "highlighted_candidate_index": 0,
  "candidates": [                   // 仅当前页；index 为页内下标
    {"index": 0, "text": "你好", "comment": ""}
  ],
  "select_keys": "",                // menu/select_keys，未配置为空
  "select_labels": [],              // menu/alternative_select_labels
  "commit": "你好",                  // 无提交时为 null
  "status": {
    "schema_id": "luna_pinyin_simp", "schema_name": "朙月拼音·简化字",
    "is_disabled": false, "is_composing": true,   // 选择候选之前的状态
    "is_ascii_mode": false, "is_full_shape": false,
    "is_simplified": false, "is_traditional": false, "is_ascii_punct": false
  },
  "options": {"ascii_mode": false, "zh_simp": true, "...": false},
  "keys": {"consumed": 5, "simulate_ok": null},
  "select": {"requested": 0, "ok": true},
  "steps": [ ... ],                 // 仅 --steps
  "post_select": {"preedit": "", "is_composing": false},
  "meta": {
    "dll": "...\\rime.dll",
    "shared_data_dir": "...", "user_data_dir": "...", "build_dir": "...",
    "deployed": true, "deploy_seconds": 3.6,
    "deploy_events": [{"type": "deploy", "value": "start"}, {"type": "deploy", "value": "success"}],
    "elapsed_ms": 37,
    "librime_struct_sizes": {"RimeTraits": 96, "...": 0}
  }
}
```

稳定性约定：

- 成功时 `ok/input/schema/preedit/candidates/commit/status/options/meta` 一定存在；
- `candidates[*]` 一定含 `index/text/comment`；
- 后续只增字段，不改已有字段语义；
- 失败时 `{"ok": false, "error": "..."}`，退出码 1；参数错误退出码 2（stderr 用法信息）。
- 输出为 UTF-8。批量调用请按 UTF-8 解码 stdout（Windows 下建议设 `PYTHONUTF8=1`）。

---

## 命令行参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--dll PATH` | `C:\Program Files\Rime\weasel-0.17.4\rime.dll` | rime.dll |
| `--shared DIR` | `C:\Program Files\Rime\weasel-0.17.4\data` | 共享数据目录（必须含 `default.yaml`） |
| `--user DIR` | `%TEMP%\mgjy-rime-harness\default` | 用户数据目录，自动创建；部署产物只写这里 |
| `--fresh-user` | 关 | 每次新建唯一临时用户目录（并行/干净测试） |
| `--schema ID` | 无 | schema_id；会写 `<user>/default.custom.yaml` 并只部署该方案 |
| `--input SPEC` | `""` | 键序列，见下节 |
| `--sequence SPEC` | 无 | 改用 `RimeSimulateKeySequence`（支持 `{Control+a}`），与 `--input` 二选一 |
| `--option NAME=0/1` | 无 | 输入前设置选项，可重复 |
| `--get-option NAME` | 无 | 额外读取并输出某选项，可重复 |
| `--select N` | 无 | 选择**当前页**第 N 个候选（与 `candidates[].index` 对齐） |
| `--select-absolute N` | 无 | 选择候选总表第 N 个（`RimeSelectCandidate`） |
| `--deploy auto\|always\|never` | `auto` | 见“部署与缓存” |
| `--prebuilt DIR` / `--staging DIR` | librime 默认 | 覆盖 prebuilt/staging 目录 |
| `--log-dir DIR` | `<user>\logs` | librime 日志目录 |
| `--log-level 0..3` | `2` | 0=INFO 1=WARNING 2=ERROR 3=FATAL |
| `--no-write-custom` | 关 | 不覆盖 `default.custom.yaml` |
| `--steps` | 关 | JSON 增加每个按键后的状态快照 |
| `--list-schemas` | 关 | 初始化（含部署）后列出已部署 schema |
| `--json` / `--pretty` | 关 | 输出 JSON / 缩进美化 |

---

## 键序列语法（`--input`）

与 librime `KeySequence::Parse` 一致：

- 普通字符 = 单键，取 ASCII 码：`nihao`、`ni'hao`、`a1`；
- `{名字}` = 命名键，名字是 **X11 keysym 名**（不是 Windows 虚拟键码）：
  `{space}` `{Return}` `{BackSpace}` `{Escape}` `{Tab}` `{Page_Down}` `{Page_Up}`
  `{Left}` `{Right}` `{Up}` `{Down}` `{comma}` `{period}` `{apostrophe}` …
- 组合键：`{Control+a}`、`{Shift+4}`、`{Control+Shift+4}`（修饰键名：
  `Shift Lock Control Alt Mod2..Mod5 Super Hyper Meta`）。
- 翻页：默认配置支持 `{Page_Down}`/`{Page_Up}`、`-`/`=`、`,`/`.`。

示例：

```bat
:: 输入 ni 后翻一页，选当前页第 0 个候选
python rime_harness.py ... --input "ni{Page_Down}" --select 0 --json

:: 输入 nihao 后按空格提交首选
python rime_harness.py ... --input "nihao{space}" --json

:: 用 librime 自带序列解析器（等价能力）
python rime_harness.py ... --sequence "nihao{space}" --json
```

> `--input` 不支持直接输入非 ASCII 字符（librime 按键事件本身就是 ASCII/X11
> keysym）。中文标点请用 `{comma}` 等键，或改 `--sequence`。

---

## 选项/开关测试

```bat
:: zh_simp：0=繁体 1=简体（luna_pinyin_simp 的开关）
python rime_harness.py ... --input hanzi --option zh_simp=0 --select 0 --json   :: 漢字
python rime_harness.py ... --input hanzi --option zh_simp=1 --select 0 --json   :: 汉字

:: ascii_mode：西文模式（注意：字母不会被消费，也不会产生 commit）
python rime_harness.py ... --input nihao --option ascii_mode=1 --json
:: -> status.is_ascii_mode=true, keys.consumed=0, commit=null

:: 全角/半角、英文标点
python rime_harness.py ... --input "ni{comma}" --option full_shape=1 --json
python rime_harness.py ... --input "ni{comma}" --option ascii_punct=1 --json
```

输出里的 `options` 默认包含：`ascii_mode full_shape ascii_punct simplification
zh_simp traditional extended_charset emoji`，加上 `--option`/`--get-option` 指定的项。
**开关状态以 `status`/`options` 为准**；`ascii_mode` 下按键直接透传给宿主程序，
本夹具（无宿主）看到的是 `consumed=0` 且无 commit，这是 librime 的正常行为。

---

## 部署与缓存

librime 的部署是“读共享/用户目录的 YAML → 在 `staging_dir`（默认
`<user>/build`）生成 `*.prism.bin/*.table.bin/*.reverse.bin`”：

1. `RimeSetup(traits)` → `RimeInitialize(traits)`；
2. `RimeStartMaintenance(True)` 触发**异步**维护线程；
3. `RimeJoinMaintenanceThread()` 等待完成；
4. 生成 `default.yaml`、`<schema>.schema.yaml`、词典二进制等。

`--deploy auto`（默认）会比较 `.rime_harness_state.json` 里记录的签名：
共享/用户目录下所有 YAML（含自定义 schema、dict、`*.custom.yaml`）的
`大小+mtime`、schema id、prebuilt/staging 路径。任何一项变化都会重新部署；
否则跳过。`--deploy always` 强制全量部署，`--deploy never` 完全跳过
（空目录会直接报错）。

实测耗时（本机）：

| 场景 | 耗时 |
|---|---|
| 首次部署 `luna_pinyin_simp` + 依赖 `stroke` | 3.3–4.0 s |
| 已部署、无变化（`auto` 跳过） | 0.3–0.5 s（整次进程） |
| 强制 `always` 且无变化 | ~0.3 s |
| 同一 user 目录切换 schema | 重新部署（~3 s） |

测试建议：一个 schema 一个 `--user` 目录；或先用 `--deploy always` 预热一次，
之后批量调用都走 `auto`。

---

## 用“魔光键影”自己的 schema/dict 测试（不装进系统）

librime 部署时会同时搜索 **user_data_dir** 和 shared_data_dir，因此把项目的
`schema.yaml` / `dict.yaml` 直接放进临时 user 目录即可，共享目录继续用安装自带的
`data`：

```bat
set U=%TEMP%\mgjy-project
:: 1) 先把 mgjy.schema.yaml / mgjy.dict.yaml 放进 %U%（任意方式复制）
:: 2) 直接跑；夹具会自动写 default.custom.yaml 并部署
python rime_harness.py --shared "C:\Program Files\Rime\weasel-0.17.4\data" ^
  --user "%U%" --schema mgjy --input "nihao" --select 0 --json
```

已实测通过：在 user 目录放自定义 `mgjy_test2.schema.yaml` + `mgjy_test2.dict.yaml`
（含 `ni hao → 你好`、`mo guang jian ying → 魔光键影`），共享目录保持安装目录，
输入 `nihao` 得到 `你好`，输入 `moguangjianying` 得到 `魔光键影`。
注意：`--schema` 会覆盖 `<user>\default.custom.yaml`；若要自己管理，用
`--no-write-custom`。项目其它 `*.custom.yaml` 补丁会被保留并参与部署。

---

## 隔离与安全

- 只写 `--user` 指定的目录（以及其下 `build/`、`logs/`）；不读写
  `%APPDATA%\Rime`。`test_luna.py` 会在测试前后对比真实用户目录；若
  `WeaselServer.exe` 正在运行则只告警（它可能后台写日志/用户词典）。
- `--shared` 可以指向 `Program Files` 下只读数据：部署只读共享目录。
- 并发注意：**不要**让两个进程同时使用同一个 `--user`（librime/LevelDB 会锁）。
  并行测试请用 `--fresh-user` 或各自独立的 `--user`。

---

## Python 内嵌调用（批量测试更快）

一个进程只允许一个 `RimeHarness`（librime 全局状态），但可以有多个 session：

```python
import rime_harness

h = rime_harness.RimeHarness(
    shared_data_dir=r"C:\Program Files\Rime\weasel-0.17.4\data",
    user_data_dir=r"C:\Users\me\AppData\Local\Temp\mgjy-batch",
    schema="luna_pinyin_simp",
)
try:
    with h.session(options={"zh_simp": False}) as s:
        consumed, steps = s.type("nihao", collect_steps=True)
        print(s.context()["candidates"])
        s.select(0)                 # 当前页第 0 个
        print(s.commit_text())      # 你好
finally:
    h.close()
```

同一进程复用 `RimeHarness` 做几十条用例可省去每次 0.3~0.5 秒的初始化；
CLI 仍是验收/回归的主入口。

---

## 已知限制

1. **Windows x64 only**；Python 必须 64 位（结构体大小在启动时断言）。
2. 一个进程一个 `RimeHarness` 实例（librime 单例）；session 可多个。
3. 传统 `RimeGetContext` 只给**当前页**候选；总候选表需翻页或用
   `candidate_list_*`（本夹具未封装）。
4. `--select` 默认按**页内下标**；总表下标用 `--select-absolute`。
5. `RimeGetCommit` 读取即清空；每次提交只能读一次（夹具在结束前统一读）。
6. `ascii_mode` 等透传键不会产生 commit、`consumed=0`，请查 `status`。
7. 不能直接键入非 ASCII 字符；只支持 ASCII/X11 keysym 键名。
8. 维护线程没有超时保护；部署卡死时进程会一直等（可用外部 timeout 包裹）。
9. 签名只看 `size+mtime`，`touch` 一下也会触发重新部署。
10. `RimeGetVersion` 在该 DLL 中**没有导出**，夹具不报告 librime 版本号。
11. 该 `rime.dll` 静态包含 librime-lua 组件（`lua_translator/lua_filter/...`），
    但本夹具尚未针对 Lua 方案做专项测试。

---

## 排错

| 现象 | 处理 |
|---|---|
| `deployment artifacts missing` | 用 `--deploy auto/always`，或先跑一次部署 |
| `schema 'x' was not deployed` | 检查 schema_id 拼写；把 `x.schema.yaml` 放 user 或 shared 目录；看 `<user>\logs` |
| `unknown key name` | 用 X11 键名（`space`/`Return`/`Page_Down`…），普通字符直接写 |
| `RimeGetContext` 一直空 | schema 没选中/没部署；看 `--list-schemas` 和 `status.schema_id` |
| JSON 解析失败 | 检查 stderr；确认用的是 `--json` 且 stdout 未被其它输出污染 |
| 中文乱码 | 以 UTF-8 解码输出；或 `set PYTHONUTF8=1` |
| 部署很慢 | 首次构建词典正常；`--schema` 只部署一个方案；复用 user 目录 |
| 想看 librime 日志 | `--log-level 0`，日志在 `<user>\logs` |
