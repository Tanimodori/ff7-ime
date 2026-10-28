# librime-lua 运行时能力探针报告

项目：魔光键影 / ff7-ime  
探针目录：`D:\Tanimodori\Projects\@FF14\ff7-ime\experiments\lua-probe`  
日期：2026-10-28

---

## 0. 结论摘要

**核心目标已真实跑通**：在完全隔离的临时用户目录中部署最小 schema，用 Python ctypes 直接调用
`C:\Program Files\Rime\weasel-0.17.4\rime.dll`（文件版本 **1.13.1**，内嵌 **Lua 5.4.7**），观察到：

| 输入 | Lua translator 调用 | 候选（RimeContext） | 提交 |
|---|---|---|---|
| `lkcc`（非法拼音） | 是，`input="lkcc"`, `[0,4)` | `力克兮兮` / `custom: illegal pinyin lkcc` | 选中后提交 `力克兮兮` |
| `nihao` | 是，`input="nihao"`, `[0,5)` | `你好` / `custom: nihao` | `RimeSelectCandidateOnCurrentPage(0)` → 提交 `你好` |
| `lkcc`（全局注册写法） | 是 | `GLOBAL:lkcc` | 提交 `GLOBAL:lkcc` |

关键结论一句话：**`lua_translator@*模块名` + `require` 是最稳的注册方式；`translator` 的入口字段叫
`func`（不是 `translate`），收到的是“当前 segment 的原始子串”；`Candidate` 的第一个参数是 `type`，
不是文本。** 这两点如果按常见示例写错，会出现“有调用但候选文本/类型错位”的问题。

可用性速查：

| 能力 | 结论 |
|---|---|
| `user_data_dir/lua/*.lua` + `require` | **可用** |
| 共享目录 `data/lua/*.lua` + `require` | **可用**（已用共享目录副本实测） |
| `rime.lua` 自动执行 | **可用**（用户目录优先） |
| `lua_translator@*mod` / `lua_translator@global` | **均可用** |
| `env.engine.schema.config:get_int/get_string/get_bool/get_list/get_map` | **可用**，缺失路径返回 `nil` |
| `env.engine.context:get_option("switch")` | **可用**，能实时反映 switches |
| `log.info/warning/error` | **可用**；落到 glog 文件 |
| `print` | 能输出到宿主 stdout，但 **Weasel 服务里不可依赖** |
| `io.open` / `os.*` / `debug` / `require` | **可用**（完整 `luaL_openlibs`） |
| `seg.start` / `seg._start` / `seg._end` | **可用**，0-based 字节偏移 |
| `seg:get_text()` | **不存在**（`nil`） |
| `seg:active_text(input)` | **有绑定但不可用**（translator 里 segment 是 const，报参数类型错误） |
| `seg.length` | 有字段，但 fallback segment 上可能不等于 `_end-start`，**别信** |
| 任意数量候选 / yield | **可用且惰性**；菜单按 `menu/page_size` 分页 |
| `Candidate` 的 `type` 可写 | **可用**；`gen_type` **不存在** |
| 多 translator + `uniquifier` | **可用**；先注册的 translator 候选在前，重复 text 合并 |

---

## 1. 环境与验证方法

### 1.1 目标二进制

```
C:\Program Files\Rime\weasel-0.17.4\rime.dll
FileVersionRaw : 1.13.1.0
```

内嵌 Lua 版本字符串：

```
$LuaVersion: Lua 5.4.7  Copyright (C) 1994-2024 Lua.org, PUC-Rio $
```

静态字符串中确认存在：

```
plugins/lua/src/{modules.cc,lua_gears.cc,types.cc,types_ext.cc,opencc.cc,...}
registering components from module 'lua'.
lua_translator / lua_filter / lua_segmentor / lua_processor
rime.lua error:
rime.lua info: rime.lua should be either in the rime user data directory or in the rime shared data directory
%s%slua%s?.lua;%s%slua%s?%sinit.lua;%s%slua%s?.lua;%s%slua%s?%sinit.lua;
```

`D:\a\librime\librime\plugins\lua\src\...` 的编译路径说明这是 GitHub Actions 构建的 librime 1.13.1，
Lua 插件源码来自上游 `hchunhui/librime-lua`（本目录 `refs/` 保存了 master 快照，用于对照 API）。

### 1.2 不碰真实用户目录

所有实验都在：

```
%TEMP%\mgjy-lua-probe\user
%TEMP%\mgjy-lua-probe\logs
%TEMP%\mgjy-lua-probe-shared\...
```

真实 `C:\Users\Tanimodori\AppData\Roaming\Rime` 与安装目录均只读，未修改。

### 1.3 动态验证

`harness.py` 用 `ctypes` 调用 1.13.1 的 C API：

- `RimeSetup` → `RimeInitialize` → `RimeStartMaintenance(True)` → `RimeJoinMaintenanceThread`
- `RimeCreateSession` / `RimeSelectSchema`
- `RimeProcessKey`（真实按键）与 `RimeSetInput`（构造边界串）
- `RimeGetContext` / `RimeFreeContext` 读取菜单、候选、comment
- `RimeGetCommit` / `RimeFreeCommit`
- `RimeGetOption` / `RimeSetOption`
- `RimeFinalize`

复现：

```bash
cd D:\Tanimodori\Projects\@FF14\ff7-ime\experiments\lua-probe
python harness.py
python shared_test.py
```

完整控制台记录：`logs/console.txt`；Lua 探针日志：`logs/lua_probe_log.txt`；
共享目录测试：`logs/shared_test_console.txt`、`logs/shared_probe_log.txt`。

### 1.4 部署结果

`default.custom.yaml` 只放三个探针 schema，部署日志：

```
finished updating schemas: 3 success, 0 failure.
3 tasks ran: 3 success, 0 failure.
```

**踩过的坑**：Rime 只认文件名 `<schema_id>.schema.yaml`。第一次把交付文件命名为
`minimal.schema.yaml` 直接拷进用户目录，部署报：

```
deployment_tasks.cc:208] missing input schema: mgjy_probe
deployment_tasks.cc:243] finished updating schemas: 0 success, 2 failure.
```

`harness.py` 现在会把它复制成 `mgjy_probe.schema.yaml` 再部署。交付文件仍叫
`minimal.schema.yaml`，两者内容相同。

---

## 2. 逐条回答

### Q1. Lua 模块如何加载？rime.lua、require、共享目录

#### 搜索路径（运行时实测）

`mgjy_probe.lua` 在 `init` 里打印 `package.path`：

```
[mgjy_probe] package.path=
C:\Users\TANIMO~1\AppData\Local\Temp\mgjy-lua-probe\user\lua\?.lua;
C:\Users\TANIMO~1\AppData\Local\Temp\mgjy-lua-probe\user\lua\?\init.lua;
C:\Program Files\Rime\weasel-0.17.4\data\lua\?.lua;
C:\Program Files\Rime\weasel-0.17.4\data\lua\?\init.lua;
C:\Python314\lua\?.lua; ...;.\?.lua;.\?\init.lua
```

即 librime-lua 在默认 `package.path` **前面**追加了四项：

```
<user_data_dir>/lua/?.lua
<user_data_dir>/lua/?/init.lua
<shared_data_dir>/lua/?.lua
<shared_data_dir>/lua/?/init.lua
```

本 harness 是 Python 进程，所以后面还能看到 `C:\Python314\...` 等宿主路径；在 Weasel 里
这一段会换成 Weasel 自己的默认路径，不影响前面的四项。

上游 `refs/modules.cc` 的 `lua_init()` 与此一致，格式串就是 DLL 里的
`%s%slua%s?.lua;%s%slua%s?%sinit.lua;...`。

#### rime.lua 自动执行

`lua_init()` 在追加路径后：

1. 若 `<user_data_dir>/rime.lua` 存在，`luaL_dofile` 执行它；
2. 否则若 `<shared_data_dir>/rime.lua` 存在，执行共享目录版本；
3. 都不存在则打一条 INFO。

实测日志：

```
[mgjy_probe] rime.lua loaded from user data dir
```

说明 `rime.lua` **确实自动执行**，且用户目录优先。共享目录的 `rime.lua` 兜底是源码明确行为，
未单独构造共享 `rime.lua` 测试（共享目录模块加载已单独验证，见下）。

#### require 用户目录

`lua/mgjy_probe_data.lua` 返回一个表：

```lua
return { magic = "MGJY-DATA-OK", values = { "alpha", "beta", "gamma" } }
```

实测：

```
require("mgjy_probe_data") => ok | table magic=MGJY-DATA-OK values=3
package.searchpath("mgjy_probe_data") => ...\user\lua\mgjy_probe_data.lua
```

#### require 共享目录（实测，非推测）

`shared_test.py` 把安装目录的 `data` 完整复制到临时 `shared/`，在
`shared/lua/mgjy_shared_data.lua` 放：

```lua
return { magic = "MGJY-SHARED-OK" }
```

用户目录的 translator 只 `require("mgjy_shared_data")`，用户目录没有这个文件。结果：

```
[mgjy_shared_probe] require mgjy_shared_data ok=true magic=MGJY-SHARED-OK
context: [00] text='MGJY-SHARED-OK:lkcc' comment='loaded from shared_data_dir/lua'
PASS: shared_data_dir/lua is searched by require
```

**结论：共享目录 `data/lua/` 确实参与搜索，且用户目录优先。**

#### 两种模块写法

| schema 写法 | 行为 |
|---|---|
| `- lua_translator@*mgjy_probe` | `require("mgjy_probe")`，模块返回 table（含 `init`/`func`/`fini`）或 function |
| `- lua_translator@mgjy_global` | 不 require，直接取 `rime.lua` 里的全局变量 `mgjy_global` |

实测两种都成功。注意 `env.name_space` 在带 `*` 时是 **`*mgjy_probe`**（包含星号），
全局写法是 `mgjy_global`：

```
[mgjy_probe] env.name_space=*mgjy_probe
[mgjy_global] init name_space=mgjy_global
```

---

### Q2. lua_translator 注册方式与最小 schema

#### 确切写法

```yaml
engine:
  translators:
    - lua_translator@*mgjy_probe
    - lua_translator@*mgjy_probe_b
```

`@` 后是 name_space/模块名；`*` 表示 require。注册名
`lua_translator`/`lua_filter`/`lua_segmentor`/`lua_processor` 由 DLL 的 lua 模块注册，
静态字符串与 `modules.cc` 均已确认。

`LuaComponent::Create` 会用 name_space 重新构造 Ticket：

```cpp
Ticket t(a.engine, a.name_space, a.name_space);
```

所以 `lua_translator@*mgjy_probe` 最终查找的模块名是 `*mgjy_probe`，`raw_init` 看到首字符
`*` 就 `require("mgjy_probe")`；不带 `*` 则 `lua_getglobal("mgjy_global")`。

#### Lua 模块最小形态

```lua
local M = {}

function M.init(env)
  -- 组件创建时调用一次；env.engine / env.name_space 可用
end

function M.func(input, seg, env)
  yield(Candidate("mgjy_probe", seg.start, seg._end, "文本", "注释"))
end

return M
```

- 入口字段是 **`func`**，不是 `translate`；写成 `translate` 会报
  `func type error expect function`。
- `init` 可选，创建时调用；`fini` 可选，销毁时调用。
- `tags_match` 仅 filter 使用。
- 模块可以返回 function 而不是 table，但那样没有 `init`/`fini`。

#### 最小可用 schema

见 `minimal.schema.yaml`。精简后关键部分：

```yaml
schema:
  schema_id: mgjy_probe
  name: "MGJY Lua Probe"
  version: "0.1.0"

switches:
  - name: mgjy_probe_enabled
    reset: 1

menu:
  page_size: 5

speller:
  alphabet: "zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA0123456789"
  initials: "zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA0123456789"
  delimiter: " '"
  use_space: true

engine:
  processors:
    - ascii_composer
    - speller
    - selector
    - navigator
    - express_editor
  segmentors:
    - abc_segmentor
    - fallback_segmentor
  translators:
    - lua_translator@*mgjy_probe
  filters:
    - lua_filter@*mgjy_probe_filter
    - uniquifier
```

不需要任何词典/`translator` 配置，部署即可 3/3 成功。只有一个 translator 时也能工作；
`mgjy_probe_b` 是为了验证多 translator 顺序与 uniquifier 才加的。

---

### Q3. translator 函数契约：input、seg、yield

#### 入口签名

```lua
function M.func(input, seg, env)
```

- `input`：**当前 segment 的原始子串**，不是整条 composition，也不是按音节切好的拼音。
- `seg`：`Segment` userdata（translator 里是 const）。
- `env`：表，含 `engine`、`name_space`。

`ConcreteEngine::TranslateSegments` 的实现是：

```cpp
string input = segments->input().substr(segment.start, len);
auto translation = entry.component->Query(input, segment);
```

#### input 实测

单 segment：

```
input="lkcc" #bytes=4 seg.start=0 seg._start=0 seg._end=4 seg.length=4
input="nihao" #bytes=5 ... seg._end=5
```

多 segment（`RimeSetInput("ni,hao")`）会分别调用：

```
input="ni"  start=0 end=2   ctx.input="ni,hao"
input=","   start=2 end=3   ctx.input="ni,hao"
input="hao" start=3 end=6   ctx.input="ni,hao"
```

所以：`input` 是**按 segment 切开的子串**；拼音音节不是 Rime 在这里切分的单位，segment 才是。
每个 segment 的 translator 之间互不知道对方。

#### seg 字段/方法

| 写法 | 结果 |
|---|---|
| `seg.start` | 可用，0-based 字节偏移 |
| `seg._start` | 可用，同 `start` |
| `seg._end` | 可用，0-based 右开区间 |
| `seg.length` | 字段存在，但 fallback segment 上可能不等于 `_end-start` |
| `seg.status` / `seg.tags` / `seg.selected_index` | 可用 |
| `seg.end` | 不存在（`end` 是 Lua 关键字，绑定只提供 `_end`） |
| `seg:get_text()` | **不存在**，`type(seg.get_text) == "nil"` |
| `seg:active_text(input)` | **有绑定但调用失败** |

实测错误：

```
seg:active_text(input) => ERROR | bad argument #2 to '?' (struct LuaType<struct rime::Segment & __ptr64> expected)
type(seg.get_text)=nil
seg:get_text() => ERROR | attempt to call a nil value (method 'get_text')
```

原因：translator 收到的是 `const Segment&`，而 `active_text` 的 C++ 签名要非 const
`Segment&`；这个绑定在 translator 上下文里不可用。**替代写法**：

```lua
local text = input:sub(seg.start + 1, seg._end)
```

实测增量输入依次得到 `"l"`、`"lk"`、`"lkc"`、`"lkcc"`，正确。

**`seg.length` 的坑**：对 `RimeSetInput("!!")` 的 fallback segment，日志是：

```
input="!!" #bytes=2 seg.start=0 seg._start=0 seg._end=2 seg.length=1
```

`length=1` 但区间是 `[0,2)`。所以位置一律用 `_end - start`，不要用 `seg.length`。

#### yield 的 Candidate 字段顺序（重要）

这个版本的构造函数是：

```cpp
an<T> make(const string type, size_t start, size_t end,
           const string text, const string comment)
```

即：

```lua
yield(Candidate(
  "mgjy_probe",      -- 1 type（候选类型字符串）
  seg.start,         -- 2 start（0-based）
  seg._end,          -- 3 end（0-based，右开）
  "力克兮兮",         -- 4 text（真正上屏的文本）
  "custom: ..."      -- 5 comment（候选注释）
))
```

实测：

```
Candidate(type,start,end,text,comment):
  type=mgjy_probe start=0 _end=1 text="TEXT-l" comment="COMMENT-l" dyn=Simple
```

如果按“文本放第一位”的直觉写：

```lua
Candidate("TEXT-"..input, seg.start, seg._end, "mgjy_probe", "COMMENT")
```

会得到：

```
type=TEXT-l text="mgjy_probe" comment="COMMENT-l"
```

即文本和类型互换。**任务描述里的示例顺序需要纠正。**

#### yield 数量、截断、分页

- `LuaTranslation` 是惰性的：每次 `Next()` resume 协程取一个 Candidate，没有固定上限。
- `Menu` 只按当前页 `menu/page_size` 取候选（`Menu::CreatePage` → `Prepare`）。
- 实测 translator A yield 8 个、B yield 2 个（1 个重复），uniquifier 后 9 个唯一候选；
  `page_size: 5` 时第 0 页 5 个、第 1 页 4 个，`is_last_page=true`。
- 再按 Page_Down 不会产生第 2 页（已经最后一页），`page_no` 保持 1。
- 所以“Rime 是否截断”答案是：**translator 层不截断；UI/API 按页取，翻页可取到全部**。
  不要一次 yield 几万条，因为虽然惰性，但排序/去重/翻页会逐步消费。

#### 提交验证

用 `RimeSelectCandidateOnCurrentPage(0)` 选中第一个候选后：

```
[select] RimeSelectCandidateOnCurrentPage(0) -> True
[commit] '你好'
```

`lkcc` 场景同样实测选中首候选后提交：

```
[select] RimeSelectCandidateOnCurrentPage(0) -> True
[commit] '力克兮兮'
```

全局注册场景提交 `GLOBAL:lkcc`。三个场景的提交都来自 Lua yield 的候选文本，不是原始输入。

> 注意：`Return` 在 `express_editor` 下提交的是**原始输入** `'lkcc'`，不是当前候选。
> 要验证候选文本，必须用选词 API/数字键/空格选词。

---

### Q4. 配置读取、开关读取、日志

#### Config API（全部运行时验证）

`schema = env.engine.schema`, `cfg = schema.config`：

```lua
cfg:get_int("menu/page_size")        --> 5          (Lua number)
cfg:get_int("/menu/page_size")       --> 5          (前导 / 也接受)
cfg:get_string("schema/name")        --> "MGJY Lua Probe"
cfg:get_bool("mgjy_probe/flag")      --> true       (Lua boolean)
cfg:get_int("mgjy_probe/number")     --> 7
cfg:get_string("mgjy_probe/name")    --> "探针配置"
cfg:get_int("no/such/int")           --> nil
cfg:get_string("no/such/string")     --> nil
cfg:get_bool("no/such/bool")         --> nil
cfg:get_list("mgjy_probe/list")      --> ConfigList userdata
cfg:get_map("mgjy_probe")            --> ConfigMap userdata
```

列表（0-based）：

```
list.size=2
list[0] type=kScalar value="alpha"
list[1] type=kScalar value="beta"
```

Map：

```
map.size=4 map.type=kMap keys=flag,list,name,number
map:get_value("number"):get_int() = 7
```

缺失路径**没有默认值参数**，统一返回 `nil`。需要默认值时自己写
`local page = cfg:get_int("menu/page_size") or 5`。

`get_double`、`get_item`、`get_value`、`set_*`、`get_list_size` 也在绑定里（静态确认），
本报告未逐一运行。

#### 开关读取

schema：

```yaml
switches:
  - name: mgjy_probe_enabled
    reset: 1
  - name: mgjy_probe_extra
    reset: 0
```

Lua：

```lua
local on = env.engine.context:get_option("mgjy_probe_enabled")
```

实测：

```
option mgjy_probe_enabled=true mgjy_probe_extra=false
```

用 C API / 其他组件改开关后，下一次翻译立刻反映：

```
RimeSetOption(mgjy_probe_extra, True)
option mgjy_probe_enabled=true mgjy_probe_extra=true
```

并且候选列表中出现：

```
[01] text='EXTRA-ON:lkcc' comment='switch mgjy_probe_extra is ON'
```

关掉后该候选消失。**这正是正式方案用 `*.custom.yaml` 开关控制模糊规则所需的机制**：

- 在 schema 的 `switches` 里声明开关（带 `reset` 默认值）；
- 在 `*.custom.yaml` 里 patch `switches` 或直接 `RimeSetOption`；
- Lua 里用 `ctx:get_option("名字")` 读，开关变化后无需重建引擎。

`env.engine.context:set_option(name, bool)` 也存在（源码确认），可在 Lua 里改开关；
另有 `option_update_notifier` 可用于监听开关变化（源码确认，本次未运行）。

#### 日志

`log.info` / `log.warning` / `log.error` 是 lua 模块注入的全局表，映射到 glog。
实测日志文件（设置 `RimeTraits.log_dir` 并调用 `RimeSetup` 后）：

```
%TEMP%\mgjy-lua-probe\logs\rime.mgjyprobe.<host>.<user>.log.INFO.<timestamp>.<pid>.log
```

Weasel 自己的 glog 目录实测是 `%TEMP%\rime.weasel\`，文件形如：

```
rime.weasel.DESKTOP-0P43DKN.Tanimodori.log.INFO.20261028-195100.2276.log
```

因此 `log.info("[mgjy] ...")` 在 Weasel 里会落到 `%TEMP%\rime.weasel\rime.weasel.*.log`。

**坑 1**：`log` 在 `rime.lua` 执行时已经可用（`types_init` 先于加载 `rime.lua`），可以在
`rime.lua` 里直接写。

**坑 2**：如果宿主只调用 `RimeInitialize` 而不先 `RimeSetup`，`log_dir` 不生效，glog 会写
stderr（本 harness 第一次就是这样）。Weasel 自己会正确 setup；自建 harness 要注意。

**坑 3**：`print` 写宿主进程 stdout。harness 里能看到：

```
[mgjy_probe] print() from Lua: hello
```

但 Weasel 是后台服务，没有控制台，**正式代码不要用 `print`，统一用 `log.*`**。

---

### Q5. 沙箱能力：io / os / require / 外部数据

librime-lua 的 `Lua::Lua()` 走 `luaL_newstate()` + `luaL_openlibs()`，没有额外沙箱限制。
运行时实测：

```
type(io), type(os), type(debug), type(require) => table,table,table,function
io.open(user_data_dir/probe_data.txt) => ok | MGJY-IO-OK	读到了外部 TSV 文件
os.getenv(TEMP) => C:\Users\TANIMO~1\AppData\Local\Temp
os.date() => 2026-10-28 20:40:26
```

结论：

- `io.open` 可用，能读外部 TSV/JSON 原始文本；
- `os.*`（含 `os.getenv`、`os.date`、`os.time`）可用；
- `debug` 也可用；
- `require` 会搜索 `lua/?.lua` 和 `lua/?/init.lua`，用户目录优先、共享目录兜底；
- `package.cpath` 里还有 `.\?.dll` 等，理论上能 `require` C 模块，但**正式方案不要依赖**，
  分发和 ABI 都不可控。

**没有内置 JSON 解析器**。可选方案：

1. **构建期嵌入 Lua 表（推荐）**：本项目 `lua/mgjy_probe_data.lua` 就是示例，
   `require("mgjy_probe_data")` 直接得到 table；
2. 构建期把 JSON/TSV 转成 Lua 源码（生成 `return { ... }`），随 `lua/` 一起分发；
3. 运行时 `io.open` 读文件再手写解析/带纯 Lua JSON 库——可行，但路径、权限、编码、
   Weasel 服务工作目录都增加不确定性，**不建议作为正式方案的主路径**。

如果一定要外部文件，建议在 `init(env)` 里只读一次并缓存，不要每次按键都读盘。

---

### Q6. 多 translator / filter 共存：顺序、去重、uniquifier、comment

#### 顺序

schema 顺序：

```yaml
translators:
  - lua_translator@*mgjy_probe     # A
  - lua_translator@*mgjy_probe_b   # B
filters:
  - lua_filter@*mgjy_probe_filter
  - uniquifier
```

A 每次 yield 8 个候选，B yield 2 个。实测 `lkcc`：

```
[00] 力克兮兮        (A, type=mgjy_probe)
[01] lkcc#01         (A)
...
[07] lkcc#07         (A)
[08] B:lkcc          (B, type=mgjy_probe_b)
```

即 A 的 8 个全部排在 B 之前。原因在 `MergedTranslation` / `Candidate::compare`：

1. `start` 小者优先；
2. `end` 大者优先；
3. `quality` 大者优先；
4. 全相等时，先注册的 translation 保持 elected（稳定顺序）。

`type` **不参与**比较。要让 B 的候选插到 A 前面，应该设更高的 `quality`，而不是改 `type`。

#### uniquifier

B 的第 1 个候选与 A 的首候选 text 相同（`力克兮兮`），B 的 comment 是
`B duplicate comment`。透传 Lua filter 在 uniquifier **之前**运行，因此它看到 10 个：

```
[mgjy_filter] cand#1  text="力克兮兮" comment="custom: illegal pinyin lkcc"
...
[mgjy_filter] cand#9  text="力克兮兮" comment="B duplicate comment"
[mgjy_filter] cand#10 text="B:lkcc"   comment="B distinct comment"
[mgjy_filter] passed 10 candidates
```

最终菜单只有 9 个唯一候选，`力克兮兮` 只出现一次，comment 保留**第一个**的
`custom: illegal pinyin lkcc`；B 的 comment 被丢弃（原始候选仍保留在 UniquifiedCandidate 中，
Lua 可用 `cand:get_genuines()` 取到，源码确认）。

#### filter 顺序

filter 按 schema 列表顺序链式应用。Lua filter 的签名是：

```lua
function M.func(translation, env, candidates)
  for cand in translation:iter() do
    yield(cand)   -- 透传；也可改 comment/插新候选
  end
end
```

`lua_filter@*name` 与 translator 的 `*` 规则相同。`tags_match` 可选，用来按 segment tag
决定是否应用（源码确认）。

#### comment 显示

`Candidate.comment` 直接进入 `RimeCandidate.comment`，`RimeGetContext` 可读：

```
[00] text='力克兮兮' comment='custom: illegal pinyin lkcc'
```

Weasel UI 是否显示、显示在候选右侧还是下方由皮肤/主题决定；数据层始终可用。
`preedit` 字段也可写，但常规候选不需要。

---

### Q7. 边界：大写、数字、空格、分隔符、标点、alphabet

#### 实测矩阵（主 schema，alphabet 含大小写字母+数字，delimiter 含空格和 `'`）

| 输入方式 | 输入 | Lua 收到的 input | 结果 |
|---|---|---|---|
| 真实按键 | `lkcc` | `"lkcc"` `[0,4)` | 候选 `力克兮兮` |
| 真实按键 | `nihao` | `"nihao"` `[0,5)` | 候选 `你好` |
| `RimeSetInput` | `niHao123` | `"niHao123"` `[0,8)` | 候选 `探针:niHao123` |
| `RimeSetInput` | `ni hao` | `"ni hao"` `[0,6)` | 空格保留在 segment 内 |
| `RimeSetInput` | `ni'hao` | `"ni'hao"` `[0,6)` | 分隔符保留在 segment 内 |
| `RimeSetInput` | `ni,hao` | `"ni"`、`","`、`"hao"` 三次调用 | 逗号成为独立 segment |
| `RimeSetInput` | `NIHAO` | `"NIHAO"` `[0,5)` | 大写通过 |
| `RimeSetInput` | `!!` | `"!!"` `[0,2)` | 标点通过（fallback segment） |
| `RimeSetInput` | `a-b` | `"a"`、`"-"`、`"b"` 三次调用 | 连字符独立 segment |

多 segment 时 `ctx.input` 仍是完整串（如 `ni,hao`），但每次 translator 只拿到当前 segment。
前面 segment 的候选会被“预确认”进 preedit，所以 preedit 可能显示
`探针:ni探针:,hao` 这种拼接结果——这是 Rime 的 composition 行为，不是 translator 被调用了多次同一段。

#### alphabet 的作用（strict 对照 schema）

`strict.schema.yaml` 只允许小写字母、无 fallback_segmentor：

| 按键 | `RimeProcessKey` 返回 | composition |
|---|---|---|
| `a` `b` | True / True | `ab`，translator 被调用 |
| keycode `A` `B`（0x41/0x42） | False / False | 空，translator 不调用 |
| Shift+a / Shift+b（keycode 0x61/0x62 + mask 1） | True / True | `ab`（keycode 层仍是小写） |
| `1` `2` `3` | False / False | 空，translator 不调用 |

结论：

- `speller/alphabet` 是**第一道门**：键码必须在 alphabet 或 delimiter 里，否则 `speller` 返回
  `kNoop`，输入根本不进 composition，translator 自然不会调用。
- `speller/initials` / `speller/finals` 影响“是否期待下一个字母是声母”；若 alphabet 收了
  大写/数字但 initials 没收，可能在第二个字符就 break。正式方案若要把大写/数字纳入，
  **initials 也要同步包含**（本项目主 schema 就是这么做的）。
- `speller/delimiter` 里的字符可以进入 composition；空格还需要
  `speller/use_space: true`，否则空格被 `speller` 放行给 selector/editor。
- `abc_segmentor` 用同一份 alphabet/delimiter 切段；不在其中的字符会停止当前 abc segment。
  若加了 `fallback_segmentor`，剩余字符（标点、不在 alphabet 的字母等）会被单独切成
  fallback segment，translator 仍会被调用（`!!`、`,`、`-` 的实测就是如此）。
- 如果不加 `fallback_segmentor`（且没有其他 segmentor 接管），这些字符不会形成 segment，
  translator 不会调用。
- 真实键盘输入标点时，通常先被 `punctuator` 处理器消费并直接上屏，根本不会进入
  composition；`RimeSetInput` 是绕过处理器直接构造 composition，所以能看到标点 segment。
  正式方案不要指望 translator 处理常规标点，除非显式配置 punctuation/segmentor。

#### 大写/Shift 的 harness 注意点

`RimeProcessKey(session, ord('a'), 1)` 在 keycode 层仍得到小写 `a`，不是 `A`。
要模拟真正的大写键，应发 keycode `ord('A')`（0x41）或在 keyevent 层构造 shift 后的 keysym。
Weasel 从 Windows 键盘消息映射 keysym 时具体走哪条路径，需要在真机上再确认一次。

---

### Q8. `type` / `gen_type` 能否设置，是否影响排序/过滤

#### 能设置什么

`Candidate` 的可写属性（源码 + 实测）：

```
type, start, _start, _end, quality, text, comment, preedit
```

实测：

```lua
local c = Candidate("mgjy_probe", seg.start, seg._end, "TEXT", "COMMENT")
c.type = "mgjy_probe_typed"
c.quality = 0.0
```

日志：

```
after write: type=mgjy_probe_typed quality=0.0; gen_type field type=nil
```

- `type` 可通过构造函数第 1 参或 `c.type = ...` 设置；
- `quality` 可写，且**会影响跨 translator 的排序**（`Candidate::compare` 第 3 关键字）；
- `text` / `comment` / `preedit` 对 SimpleCandidate 可写；
- `c:get_dynamic_type()` 返回 C++ 实际类型：`Simple` / `Shadow` / `Uniquified` / `Phrase` / `Sentence`。

#### `gen_type`

**不存在**。运行时 `type(c.gen_type) == "nil"`；在 `rime.dll` 的全部字符串里也搜不到
`gen_type`/`get_gen_type`。1.13.1 的 `Candidate` 只有 `type()`，没有 `gen_type`。

如果正式方案需要区分“生成来源”，只能：

- 用 `type` 字符串自己编码（如 `mgjy_fuzzy`、`mgjy_phrase`）；
- 或用 `get_dynamic_type()` 区分 Simple/Phrase/Uniquified；
- 或把来源写进 comment/自定义 userdata（不推荐）。

#### 是否影响排序/过滤

- **不影响菜单排序**：`Candidate::compare` 只看 `start`、`end`、`quality`，不看 `type`。
- **不影响 uniquifier**：`UniquifiedTranslation::find_text_match` 只比较 `text`。
- **可能影响其他组件**：
  - `speller` 的 `auto_select` 判断 `is_table_entry(cand)`，条件是
    `type == "table" || type == "user_table"`；Lua 的 type 不要随便写成这两个值，
    否则可能被当作词典候选自动上屏；
  - 词典/用户词典学习、`table_translator` 等会看 type；
  - 某些 filter（如按 type 过滤的第三方 filter）可能看 type。

结论：`type` 是**元数据**，可用于正式方案内部标记，但不要指望它改变候选顺序；排序请用
`quality` 或 yield 顺序/translator 顺序。

---

## 3. 可用 / 不可用 / 有坑 清单

### 可用（可依赖）

- `lua_translator@*module` + `require`（用户/共享目录）
- `lua_translator@global`（`rime.lua` 全局变量）
- `rime.lua` 自动加载
- `func(input, seg, env)` + `yield(Candidate(...))`
- `Candidate(type, start, end, text, comment)`
- `seg.start` / `seg._start` / `seg._end`
- `input:sub(seg.start+1, seg._end)`
- `env.engine.schema.config:get_int/get_string/get_bool/get_list/get_map`
- `env.engine.context:get_option`
- `log.info/warning/error`
- `io.open` / `os.*` / `require`
- `lua_filter@*module` 透传/改 comment/插候选
- `uniquifier` 去重
- 任意数量惰性 yield + `menu/page_size` 分页
- `quality` 控制跨 translator 排序

### 不可用（不要依赖）

- `seg:get_text()` —— 不存在
- `seg:active_text(input)` —— 绑定存在但在 translator 的 const Segment 上调用失败
- `gen_type` / `get_gen_type` —— 不存在
- `print` 作为正式日志 —— Weasel 服务无控制台
- `RimeJoinMaintenance` —— DLL 没有这个导出；实际是 `RimeJoinMaintenanceThread`
- `RimeGetVersion` —— 没有该 C 导出；Lua 里用 `rime_api.get_rime_version()`，或读文件版本
- 共享 `data/lua/` 的 C 模块（`.dll`）—— 理论可行但不建议

### 有坑（必须处理）

1. **Candidate 参数顺序**：第一参是 `type`，不是 text。写错会“类型=文本、文本=类型”。
2. **schema 文件名**：必须是 `<schema_id>.schema.yaml`，否则部署 `missing input schema`。
3. **`seg.length` 不可靠**：fallback segment 上可能不等于 `_end-start`，统一用 `_end-start`。
4. **`env.name_space` 带 `*`**：`lua_translator@*mgjy_probe` 的 name_space 是
   `*mgjy_probe`；日志/条件判断时注意。
5. **`Return` 提交原始输入**：`express_editor` 下 Return 不等同于选词；验证候选要用
   `RimeSelectCandidateOnCurrentPage` / 数字键 / 空格。
6. **空格进入 composition 需要 `speller/use_space: true`**，且空格要放进 delimiter。
7. **大写/数字要同时加入 `alphabet` 和 `initials`**，否则可能第二个字符就 break。
8. **标点通常到不了 translator**：`punctuator` 会先消费；`RimeSetInput` 才能构造标点 segment。
9. **`log_dir` 需要 `RimeSetup`**：只调 `RimeInitialize` 时 glog 写 stderr。
10. **正式方案别每次按键读配置/读文件**：在 `init` 缓存；开关用 `get_option` 轻量读取。

---

## 4. 对正式实现的建议

### 4.1 可以直接依赖的 API

- 注册：`engine/translators: - lua_translator@*mgjy_xxx`
- 入口：模块返回 table，提供 `init(env)` 和 `func(input, seg, env)`
- 候选：`yield(Candidate(type, seg.start, seg._end, text, comment))`
- 配置：`env.engine.schema.config:get_int/get_string/get_bool/get_list/get_map`
- 开关：`env.engine.context:get_option("mgjy_xxx_enabled")`
- 日志：`log.info/warning/error`
- 子串：`input:sub(seg.start+1, seg._end)`

### 4.2 必须回退/封装的 API

- `seg:active_text` / `seg:get_text` → 封装成 `local function seg_text(input, seg)`
- `seg.length` → 封装成 `seg._end - seg.start`
- `gen_type` → 用 `type` 字符串约定，或 `get_dynamic_type()`
- `print` → 禁用，统一 `log.*`
- 外部 JSON/TSV → 构建期生成 Lua 表；运行时读取只作为可选路径

### 4.3 推荐的 Lua 文件组织

```
rime.lua                     # 极简：全局 log、共享 helper；不要塞大逻辑
lua/
  mgjy_fuzzy.lua             # 主 translator（require）
  mgjy_fuzzy_data.lua        # 构建期生成的数据表（规则/词表）
  mgjy_fuzzy_filter.lua      # 可选 filter（改 comment / 插候选）
  mgjy_common.lua            # 共享工具（require）
```

- 一个 translator 一个模块，`return M`；
- `init(env)` 里读取 schema 配置、构建规则索引、缓存开关初始值；
- `func` 里只做轻量查询 + yield；
- 模块之间用 `require("mgjy_common")`，不要依赖全局变量（除 `lua_translator@global` 的兼容写法）；
- 数据在构建期嵌入 Lua 表，避免运行时 IO；
- 需要热更新开关时，`func` 里读 `ctx:get_option`（很轻），或用 `option_update_notifier` 监听。

### 4.4 对“模糊规则开关”的具体建议

- 在 schema 里声明：

  ```yaml
  switches:
    - name: mgjy_fuzzy_enabled
      reset: 1
    - name: mgjy_fuzzy_loose
      reset: 0
  ```

- 在 `*.custom.yaml` 里 patch 默认值，或运行时 `RimeSetOption`；
- Lua 里：

  ```lua
  local fuzzy_on = env.engine.context:get_option("mgjy_fuzzy_enabled")
  local loose = env.engine.context:get_option("mgjy_fuzzy_loose")
  ```

- 规则表本身放 schema 配置（`get_list`/`get_map`）或构建期数据表；开关只控制“是否应用”，
  不要把规则硬编码进 if。

### 4.5 性能

- `yield` 是惰性的，但候选排序/去重会消费；单次翻译 yield 数量建议控制在几十条以内；
- 大词表/规则表在 `init` 建索引，不要在 `func` 里线性扫描全表；
- 不要每次按键 `io.open`；
- `menu/page_size` 别设太大（5~9 常见）。

---

## 5. 交付物

| 文件 | 说明 |
|---|---|
| `REPORT.md` | 本报告 |
| `minimal.schema.yaml` | 最小可运行 schema（schema_id `mgjy_probe`，部署时需改名） |
| `strict.schema.yaml` | 对照 schema（仅小写 alphabet，无 fallback） |
| `global.schema.yaml` | 对照 schema（`lua_translator@mgjy_global`，不带 `*`） |
| `rime.lua` | 自动加载 + 全局 translator 示例 |
| `lua/mgjy_probe.lua` | 主探针 translator（日志/配置/开关/候选） |
| `lua/mgjy_probe_b.lua` | 第二 translator（顺序/重复候选） |
| `lua/mgjy_probe_filter.lua` | 透传 Lua filter（观察 filter 与 uniquifier 顺序） |
| `lua/mgjy_probe_data.lua` | 构建期数据嵌入示例 |
| `harness.py` | ctypes 部署 + 按键 + 读候选 + 收集日志 |
| `shared_test.py` | 共享目录 `data/lua` 的 require 验证 |
| `logs/console.txt` | 主 harness 完整控制台记录 |
| `logs/lua_probe_log.txt` | Lua 探针日志摘录（1200+ 行） |
| `logs/rime_log.txt` | 合并后的 glog 全文 |
| `logs/result.json` | 结构化结果（每个场景的 preedit/menu/candidates） |
| `logs/shared_test_console.txt` | 共享目录测试输出 |
| `logs/shared_probe_log.txt` | 共享目录测试 Lua 日志 |
| `logs/deploy_pitfall.txt` | `missing input schema` 踩坑记录 |
| `refs/` | 上游源码快照（modules.cc / lua_gears.cc / types.cc / rime_api.h 等） |

### 关键证据位置

在 `logs/console.txt` / `logs/lua_probe_log.txt` 中搜索以下锚点：

- `CONTEXT lkcc after typing`、`CONTEXT lkcc before selecting first candidate`
- `CONTEXT nihao (page 0)`、`[commit] '你好'`
- `scenario: lua_translator@mgjy_global`
- `scenario: strict alphabet`
- `RimeSetInput('niHao123')` 及其后的边界输入段落
- `[mgjy_filter] passed 10 candidates`
- `get_int(menu/page_size)`、`get_map(mgjy_probe)`、`missing get_int`
- `logs/shared_test_console.txt` 中的 `MGJY-SHARED-OK:lkcc` 与 `PASS`

---

## 6. 一句话总结

**这套 weasel 0.17.4 / librime 1.13.1 的 librime-lua 足以支撑正式方案**：用
`lua_translator@*模块` + `require` 注册，`func(input, seg, env)` 里 `yield` 任意数量
`Candidate(type, start, _end, text, comment)`，用 `env.engine.schema.config` 读规则、用
`ctx:get_option` 读 `*.custom.yaml` 开关、用 `log.info` 记录；只要避开
`seg:get_text`/`seg:active_text`/`seg.length`/`gen_type` 这几个不存在的或不可靠的 API，
并在构建期把数据嵌成 Lua 表，就能稳定实现“任意字母串都有候选”的魔光键影 translator。
