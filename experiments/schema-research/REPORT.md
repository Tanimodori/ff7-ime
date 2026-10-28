# 魔光键影 Rime 方案结构与 Windows 部署研究报告

日期：2026-10-28
目标环境：小狼毫 Weasel 0.17.4（librime 1.13.1，Windows x64）
研究范围：schema 结构、纯字母输入分段、Lua translator 接入、开关/配置、Weasel 部署与便携化

---

## 0. 结论摘要

1. **本机 rime.dll 确实带 librime-lua**。`rime.dll` 内含 Lua 5.4.7，并注册 `lua_translator`、`lua_filter`、`lua_segmentor`、`lua_processor` 四个组件。实测 `lua_translator@*ff7-ime` 能自动 `require` 用户目录 `lua/ff7-ime.lua`，不需要修改 `rime.lua`。
2. **`lkcc` 可以作为单个 segment 进入 Lua**。条件是：
   - `speller/alphabet` 覆盖全部字母；
   - `speller/initials` 与 alphabet 相同，`speller/finals` 为空（或不写）；
   - 不引入 `speller/algebra`（拼音音节切分）；
   - `delimiter` 为空；
   - 不配置会匹配子区间的 `recognizer/patterns`。
   实测 preedit 为 `lkcc`（无空格），Lua 收到的 `input` 长度为 4，直接产出候选。
3. **只要不挂 `script_translator` / `table_translator`，就没有造句**；不配置 `user_dict` 就没有用户词频/用户词库；不挂 `simplifier` 就没有简繁转换；不挂 `uniquifier` 就不会合并同文候选。本方案只保留一个 Lua translator。
4. **标点策略选择“明确禁用 punctuator”**：不加载 `punctuator` processor、`punct_translator`、`punct_segmentor`。词条文本中的 `！，·……` 由 Lua 原样作为候选文本输出；键盘上的标点不参与组词。有候选时按标点键先提交当前选中候选，无候选时提交原始输入，然后把 ASCII 标点交给应用（实测 `lkcc,` 提交“测试候选…”后清空 composition）。
5. **最危险的不是 schema 语法，而是三件事**：
   - `switches/@fuzzy_zh_z/reset` 这类“按名字 patch”会被 Rime 解析成 `@0`，静默改到 `ascii_mode` 上；
   - 同一秒内修改 schema/custom 后部署，可能因为 mtime 秒级精度而被判定“未变化”，不重建；
   - `WeaselDeployer.exe /deploy` 的退出码 0 不代表部署成功（源码里 `rime->deploy()` 的返回值被忽略），必须查 `build/` 与日志。
6. **Weasel 没有官方 portable 模式**。0.17.4 的 release 只有 installer；源码中用户目录来自注册表 `HKCU\Software\Rime\Weasel\RimeUserDir`，缺省 `%APPDATA%\Rime`。可行的“便携数据目录”方案是 `WeaselSetup.exe /userdir:<dir>`（或直接写 `RimeUserDir`），但它是**全局用户目录**，会影响现有 luna_pinyin_simp，必须迁移/备份。

---

## 1. 环境与证据来源

### 1.1 安装与用户目录

| 项 | 值 |
|---|---|
| Weasel 安装目录 | `C:\Program Files\Rime\weasel-0.17.4` |
| 共享数据目录 | `C:\Program Files\Rime\weasel-0.17.4\data` |
| 真实用户目录 | `C:\Users\Tanimodori\AppData\Roaming\Rime` |
| 构建输出 | `%APPDATA%\Rime\build` |
| 日志目录 | `%TEMP%\rime.weasel` |
| Deployer | `WeaselDeployer.exe` |
| Setup | `WeaselSetup.exe` |
| Server | `WeaselServer.exe`（`/q` 退出） |

真实用户目录当前内容：

- `default.custom.yaml`：`patch/schema_list` 只有 `luna_pinyin_simp`
- `installation.yaml`：distribution 信息、installation_id
- `user.yaml`：`last_build_time`、`previously_selected_schema`
- `luna_pinyin.userdb/`
- `build/`：luna_pinyin_simp、stroke 等构建产物
- `weasel.custom.yaml`：0 字节

项目词表 `dict.txt` 是 **UTF-16LE + BOM + CRLF**，解码后 1212 行、无空行；
最长词条 15 个字符，106 条含 `！，。·……` 等标点。Lua 运行时数据文件使用
UTF-8 TSV（样例 `ff7-ime_data.sample.tsv`），两者编码不同，数据构建
脚本需要显式转换。

**本研究的部署实验全部在 `experiments/schema-research/_testuser*` 等临时 user dir 中完成，没有修改真实用户目录或安装目录。**

### 1.2 Lua 支持证据

命令：

```bash
grep -a -o -E "lua_translator|lua_filter|lua_processor|lua_segmentor|Lua" \
  "C:/Program Files/Rime/weasel-0.17.4/rime.dll" | sort | uniq -c
```

输出（节选）：

```
    548 Lua
      1 lua_filter
      1 lua_processor
      1 lua_segmentor
      1 lua_translator
```

进一步：

```bash
grep -a -o -E "Lua [0-9]\.[0-9](\.[0-9])?" rime.dll | sort -u
# Lua 5.4
# Lua 5.4.7
```

实测日志（临时 user dir 的 `logs/`）：

```
I... modules.cc:96] registering components from module 'lua'.
I... modules.cc:87] rime.lua info: rime.lua should be either in the rime user data directory or in the rime shared data directory
I... registry.cc:14] registering component: lua_translator
...
I... types.cc:1558] ff7-ime: loaded 6 entries from .../ff7-ime_data.tsv
```

说明：

- 不需要 `lua/rime.lua`；`lua_translator@*ff7-ime` 的 `*` 前缀会走 `require`（librime-lua `raw_init` 的 autoload 分支）。
- 如果把 `lua/ff7-ime.lua` 删掉，日志会明确报：
  ```
  E... lua_gears.cc:83] Lua Compoment of autoload error: ... module 'ff7-ime' not found:
  E... lua_gears.cc:131] ... func type error expect function
  E... lua_gears.cc:17] LuaTranslation::Next error(2): ...
  ```
  候选数为 0。排查时直接 grep `autoload error` / `module .* not found`。

### 1.3 参考文件

- `C:\Program Files\Rime\weasel-0.17.4\data\default.yaml`
- `C:\Program Files\Rime\weasel-0.17.4\data\luna_pinyin.schema.yaml`
- `C:\Program Files\Rime\weasel-0.17.4\data\luna_pinyin_simp.schema.yaml`
- `C:\Program Files\Rime\weasel-0.17.4\data\weasel.yaml`
- `C:\Program Files\Rime\weasel-0.17.4\data\key_bindings.yaml`
- `C:\Program Files\Rime\weasel-0.17.4\data\punctuation.yaml`
- librime 1.13.1 源码：<https://github.com/rime/librime/tree/1.13.1>
- librime-lua 源码：<https://github.com/hchunhui/librime-lua>
- Weasel 源码：<https://github.com/rime/weasel>

关键源码位置：

- `src/rime/gear/abc_segmentor.cc`：使用 `speller/alphabet`、`speller/delimiter`、`speller/initials`、`speller/finals` 决定 abc segment 边界。
- `src/rime/engine.cc` 的 `TranslateSegments`：对每个 segment 调用**所有** translator，`input` 是 segment 的子串；tag 过滤必须由 translator 自己做。
- `src/rime/gear/speller.cc`：只接受 `0x20 <= ch < 0x7f` 且属于 alphabet/delimiter 的键；`max_code_length` 默认 0。
- `src/rime/config/config_data.cc` 的 `ResolveListIndex`：`@` 后不是 `next/before/after/last` 时走 `strtoul`，非数字得到 0。
- `src/rime/config/auto_patch_config_plugin.cc`：根节点有显式 `__patch` 时跳过自动 `<schema>.custom.yaml`。
- `src/rime/lever/deployment_tasks.cc`：`source file changed` 用 `(int)to_time_t(last_write_time)`，秒级。
- `src/rime/gear/uniquifier.cc`：按候选文本合并为 `UniquifiedCandidate`。
- `src/rime/gear/punctuator.cc`：`PunctSegmentor` 依赖 punctuator 映射。
- Weasel `WeaselDeployer/WeaselDeployer.cpp`、`Configurator.cpp`、`WeaselSetup/WeaselSetup.cpp`、`RimeWithWeasel/WeaselUtility.cpp`。

---

## 2. Schema 结构设计

骨架文件：`experiments/schema-research/ff7-ime.schema.yaml`

### 2.1 组件取舍

| 区块 | 配置 | 理由 |
|---|---|---|
| `schema` | `schema_id: ff7-ime`、`name: 魔光键影` | schema_id 必须与文件名一致 |
| `switches` | `ascii_mode` + 11 个自定义开关 | 见 §4 |
| `engine/processors` | `ascii_composer`, `recognizer`, `key_binder`, `speller`, `selector`, `navigator`, `express_editor` | 不加载 `punctuator` |
| `engine/segmentors` | `ascii_segmentor`, `matcher`, `abc_segmentor`, `fallback_segmentor` | `abc_segmentor` 是纯字母整段的关键；不加载 `punct_segmentor` |
| `engine/translators` | 仅 `lua_translator@*ff7-ime` | 没有 script/table translator，因此没有造句 |
| `engine/filters` | `[]` | 不挂 `simplifier`、`uniquifier`、`charset_filter` |
| `speller` | alphabet 大小写、delimiter 空、initials=alphabet、max_code_length 0 | 见 §3 |
| `punctuator` | 空 map，且不加载组件 | 明确禁用 |
| `recognizer` | `patterns: {}` | 不引入 default 的 email/url/uppercase；避免 recognizer 在 speller 之前接受字母表外字符 |
| `key_binder` | 自写 bindings，不 import default | 避免 comma/period 翻页占用标点键 |
| `menu` | `page_size: 5` | 可按用户 patch |
| `ff7-ime` | `top_n`、`show_comment`、`data_file`、长度限制、matcher | Lua 读取的配置命名空间 |
| `translator` | 仅说明性 `tag: abc` | 不参与引擎；tag 过滤在 Lua 内 |

各组件在本方案中的作用：

- `speller`：决定哪些按键能进入 composition。`alphabet` 是允许的字母集合，
  `delimiter` 是编码内允许的分隔符，`initials`/`finals` 供 `abc_segmentor`
  判断音节边界。本方案 alphabet 含大小写、delimiter 空、initials=alphabet、
  finals 空。
- `abc_segmentor`：把一段连续字母标成 tag `abc`；它读取的正是
  `speller/alphabet`、`speller/delimiter`、`speller/initials`、`speller/finals`。
  它是 `lkcc` 不被拆段的关键。
- `matcher`：读取 `recognizer/patterns`，在 `abc_segmentor` 之前按正则添加
  带自定义 tag 的 segment（如 `uppercase`、`url`、`email`）。本方案 patterns
  为空，因此 matcher 不产生任何 segment；保留它是为了以后需要 `reverse_lookup`
  等扩展时有固定位置。
- `fallback_segmentor`：把没有被其他 segmentor 认领的字符逐个标成 tag `raw`。
  字母都被 `abc_segmentor` 认领，所以纯字母输入不会走到它；它只处理字母表外
  的残留字符（如果有）。
- `ascii_segmentor`：只在 `ascii_mode` 打开时把整串标成 `raw`，让 Lua 跳过。
- `express_editor`：处理空格/回车/退格/Esc；空格有候选时选当前候选，无候选时
  提交原始输入。

### 2.2 为什么没有内置 translator

Rime 的 `script_translator` / `table_translator` 会：

- 用 `translator/dictionary` 建词库；
- 可能 `enable_sentence: true` 造句；
- 用 `user_dict` 学习；
- 受 `translator/enable_completion`、`initial_quality` 等影响。

本方案只需要“固定词表 + 自定义匹配”，所以 translator 只留 Lua。`express_editor` 不会造句；没有 `Memory` 就不会创建 `.userdb`。实测临时 user dir 中只有 `build/`、`user.yaml`、`installation.yaml`，没有 `ff7-ime.userdb`。

### 2.3 Lua translator 的调用约定

- `lua_translator@*ff7-ime` 的组件别名是 `*ff7-ime`，`env.name_space` 也带 `*`。因此 Lua 里不要用 `env.name_space` 拼配置路径，直接写 `ff7-ime/...`。
- `Query(input, segment)` 中 `input` 是**当前 segment 的子串**，不是整串输入；前缀输入时每敲一个字母都会调用一次。
- translator 必须自己判断 tag：
  ```lua
  if not seg:has_tag("abc") then return end
  ```
  实测 `LKCC` 的 segment 同时带 `abc` 和 `uppercase`（default recognizer 导入时），`has_tag("abc")` 仍为 true；但为了可预测性，本方案不放任何 recognizer pattern。
- 返回 table `{ init = init, func = translate }`；`func` 用 `yield(Candidate(...))` 产出候选。librime-lua 同时支持直接返回 function。

---

## 3. 核心问题：如何保证 `lkcc` 不被拆成多个 segment

### 3.1 机制

`abc_segmentor.cc`（librime 1.13.1）逻辑：

```cpp
config->GetString("speller/alphabet", &alphabet_);
config->GetString("speller/delimiter", &delimiter_);
config->GetString("speller/initials", &initials_);
config->GetString("speller/finals", &finals_);
if (initials_.empty()) initials_ = alphabet_;

for (; k < input.length(); ++k) {
  bool is_letter = alphabet_.find(input[k]) != string::npos;
  bool is_delimiter = (k != j) && (delimiter_.find(input[k]) != string::npos);
  if (!is_letter && !is_delimiter) break;
  bool is_initial = initials_.find(input[k]) != string::npos;
  bool is_final = finals_.find(input[k]) != string::npos;
  if (expecting_an_initial && !is_initial && !is_delimiter) break;
  expecting_an_initial = is_final || is_delimiter;
}
if (j < k) {
  Segment segment(j, k);
  segment.tags.insert("abc");
  ...
}
```

本方案：

- `alphabet` 包含 26 个小写 + 26 个大写；
- `initials` 与 `alphabet` 相同；
- `finals` 不写（空）；
- `delimiter` 为空；
- 没有 `speller/algebra`。

因此对 `lkcc`：

- 每个字符都是 letter、都是 initial；
- `expecting_an_initial` 永远为 true；
- `is_final` 永远 false，不会进入“等韵母”状态；
- 循环一直到输入末尾，生成一个 `[0,4)` 的 abc segment。

### 3.2 实测

临时 user dir `_testuser`，`RimeSimulateKeySequence("lkcc")`：

```
after 'lkcc' preedit='lkcc' len=4 menu_candidates=1 page_size=5
  [0] '测试候选（lkcc 分段验证用）'  comment='测试用'
```

对比 luna_pinyin_simp 的 `nihao`：

```
after 'nihao' preedit='ni hao' len=6 menu_candidates=5 page_size=5
```

`ni hao` 中的空格是 Rime 显示多 segment 的方式；`lkcc` 没有空格，说明是一个 segment。

进一步用调试 Lua 打印每次 translator 调用：

```
DBG input=L len=1 abc=true upper=true raw=false punct=false
DBG input=LK len=2 abc=true upper=true raw=false punct=false
DBG input=LKC len=3 abc=true upper=true raw=false punct=false
DBG input=LKCC len=4 abc=true upper=true raw=false punct=false
```

（该调试版本额外导入了 default 的 `uppercase` pattern，segment 同时带 `uppercase` 和 `abc`；本方案 `recognizer/patterns` 为空，不会出现 `upper`。）

### 3.3 会导致拆段的配置（务必避免）

- `speller/finals` 写了拼音韵母表，而 `initials` 只写声母：某些字母组合会在“等韵母”状态被切断。
- `speller/algebra` 引入 `pinyin:/abbreviation` 等规则：`derive/^([jqxy])u$/$1v/` 之类会改写输入；虽然未必拆段，但会改变 Lua 收到的字符串。
- `delimiter: " '"`：单引号会被当作分隔符；用户输入中的 `'` 会进入 input。
- `recognizer/patterns` 匹配子区间：`matcher` 在 `abc_segmentor` 之前添加 segment；如果 pattern 只覆盖一部分，`abc_segmentor` 会从 pattern 的 end 继续，产生多个 segment。default 的 `uppercase` 因为覆盖整串，会和同长度 abc segment 合并 tag（`Segmentation::AddSegment` rule three），不一定坏事；但 `url`/`email` 里的 `.`/`@` 不在 alphabet，recognizer 又会在 speller 之前接受它们，属于不可控输入。
- `speller/max_code_length` 非 0 + `auto_select: true`：长码会被自动上屏/截断。

---

## 4. 标点处理

### 4.1 方案选择：禁用 punctuator

本方案不加载：

- `punctuator` processor
- `punct_translator`
- `punct_segmentor`

`punctuator: {}` 只是显式声明“没有标点映射”。

效果（实测 `lkcc,`）：

```
after 'lkcc,' preedit='' len=0 menu_candidates=0 page_size=0
  COMMIT: '测试候选（lkcc 分段验证用）'
```

即：逗号键先触发 `express_editor` 的 `DirectCommit`，提交当前选中候选，然后把逗号作为普通字符交给应用（ASCII 逗号）。没有中文标点转换，也没有和词条内标点冲突。

### 4.2 词条内标点

1212 条词条中有 106 条包含 `！，·……` 等标点（例如“人生就是战斗！”、“走了，新来的！”）。这些标点是 **candidate text 的一部分**，由 Lua 的 `Candidate(...)` 原样输出，与输入法标点键无关。

- 不需要在 `speller/alphabet` 里加标点；
- 不需要在 `punctuator` 里映射这些标点；
- 用户输入始终是纯字母。

### 4.3 如果以后要恢复中文标点

需要同时：

1. `engine/processors` 加回 `punctuator`；
2. `engine/translators` 加回 `punct_translator`；
3. `engine/segmentors` 加回 `punct_segmentor`；
4. 配置 `punctuator/half_shape`（或 `import_preset: punctuation`）。

但要注意 `punct_segmentor` 会在字母 segment 之间插入 `punct` segment；Lua 只处理 `abc`，不会误匹配。风险主要是 `punctuator` 的 `use_space`、数字分隔符等行为。

---

## 5. 开关、配置与候选数

### 5.1 switches 列表与索引

| 索引 | 名称 | 默认 reset | 语义 |
|---|---|---|---|
| @0 | `ascii_mode` | 0 | 中文/西文 |
| @1 | `fuzzy_zh_z` | 1 | zh ↔ z |
| @2 | `fuzzy_ch_c` | 1 | ch ↔ c |
| @3 | `fuzzy_sh_s` | 1 | sh ↔ s |
| @4 | `fuzzy_ng_n` | 1 | ng ↔ n（韵尾） |
| @5 | `fuzzy_n_l` | 0 | n ↔ l |
| @6 | `fuzzy_r_l` | 0 | r ↔ l |
| @7 | `fuzzy_f_h` | 0 | f ↔ h |
| @8 | `fuzzy_en_eng` | 1 | en ↔ eng |
| @9 | `fuzzy_in_ing` | 1 | in ↔ ing |
| @10 | `keyword_mode` | 1 | 关键词/别名匹配 |
| @11 | `initial_mode` | 1 | 简拼匹配 |
| @12 | `typo_mode` | 0 | 一次编辑距离容错 |

`reset` 必须显式写 0/1。日志里 `reset: -1` 表示“不重置”，会沿用会话里的旧值。

### 5.2 用户 patch 开关默认值

正确写法（按索引；下面这些行在交付的 `ff7-ime.custom.yaml` 里默认是注释，取消注释即可）：

```yaml
patch:
  switches/@1/reset: 0   # fuzzy_zh_z 关闭
  switches/@5/reset: 1   # fuzzy_n_l 打开
```

**错误写法**：

```yaml
patch:
  switches/@fuzzy_zh_z/reset: 1
```

Rime 的 `ResolveListIndex` 对 `@` 后内容做 `strtoul`；`fuzzy_zh_z` 解析为 0，于是实际改的是 `switches/@0`，也就是 `ascii_mode`。实测结果：

```
option[ascii_mode] = 1
option[fuzzy_zh_z] = 1
after 'lkcc' preedit='' len=0 menu_candidates=0
```

`ascii_mode` 被打开后，输入直接走 ASCII，Lua 不再产出候选。这个坑非常隐蔽，因为 YAML 合法、部署成功、没有报错。

### 5.3 Lua 读取开关和配置

```lua
local ctx = env.engine.context
local enabled = ctx:get_option("fuzzy_zh_z")   -- boolean

local config = env.engine.schema.config
local top_n = config:get_int("ff7-ime/top_n")
local show_comment = config:get_bool("ff7-ime/show_comment")
local data_file = config:get_string("ff7-ime/data_file")
```

- `context:get_option(name)` 返回 boolean；开关由 `switches` 的 reset 初始化。
- `schema.config` 读取的是**编译后的 schema 配置**，用户 custom patch 已经合并进来。
- `ctx:set_option(name, bool)` 可在 Lua 里临时改选项，但本方案不需要。
- 注意：`switches` 的 `save_options` 在 `default.yaml` 里只列了 `full_shape`、`ascii_punct`、`simplification` 等标准项，自定义开关不会跨会话保存；每次会话按 `reset` 重置。这是预期行为。

### 5.4 候选数量、分页、注释

| 配置 | 位置 | 默认 | 说明 |
|---|---|---|---|
| 候选总数 | `ff7-ime/top_n` | 10 | Lua 内 `math.min(n, 100)` |
| 每页数量 | `menu/page_size` | 5 | 必须写在 **schema** 或其 custom patch；写在 `default.custom.yaml` 不会覆盖 schema 的 `menu/page_size`（实测 schema 值优先） |
| 是否显示注释 | `ff7-ime/show_comment` | true | false 时传空字符串 |

`menu/page_size` 建议 ≤ 10，否则数字选词键只有 `1-9,0`，第 11 个以后只能鼠标点选或翻页。

实测：

- 默认 `top_n=10`、`page_size=20`：`menu_candidates=10`（第一页受 top_n 限制）
- custom `top_n=20`、`page_size=20`：`menu_candidates=20`

---

## 6. 部署与打包

### 6.1 用户目录结构

```
%APPDATA%\Rime\
├─ default.custom.yaml           # 只改 schema_list，保留 customization
├─ user.yaml                     # Rime 自动维护
├─ installation.yaml             # Rime 自动维护；不需要改
├─ weasel.custom.yaml            # Weasel 自动创建；可选
├─ ff7-ime.schema.yaml  # 方案
├─ ff7-ime.custom.yaml  # 可选用户 patch
├─ ff7-ime_data.tsv     # Lua 运行时读取的数据
├─ lua\
│  └─ ff7-ime.lua       # Lua translator
├─ build\                        # 部署生成，不要手改
│  ├─ default.yaml
│  └─ ff7-ime.schema.yaml
├─ luna_pinyin.userdb\           # 现有方案的用户词库，不要动
└─ sync\                         # 如同步
```

- schema、custom、data、`lua/` 都放**用户目录**，不要写 `C:\Program Files`。
- `lua/` 搜索顺序：`<user_data_dir>/lua/?.lua` 优先，然后 `<shared_data_dir>/lua/?.lua`。
- 数据文件不需要编译；但 Lua 只在 engine 初始化时读取，修改 data/lua 后要重新部署或重启 WeaselServer 才生效。
- `installation.yaml` 不需要改；它只记录 distribution、installation_id、sync 信息。

### 6.2 default.custom.yaml 合并策略

现状（真实用户）：

```yaml
patch:
  schema_list:
    - {schema: luna_pinyin_simp}
```

**策略 A：已有 `patch/schema_list`**，直接追加，保留原有顺序：

```yaml
patch:
  schema_list:
    - {schema: luna_pinyin_simp}
    - {schema: ff7-ime}
```

**策略 B：没有自定义过 schema_list**，用 `/+` 追加到 `default.yaml` 的完整列表，避免把默认 8 个方案全部替换掉：

```yaml
patch:
  schema_list/+:
    - {schema: ff7-ime}
```

实测策略 B 的构建结果：

```
schema_list:
  - schema: luna_pinyin
  - schema: luna_pinyin_simp
  - schema: luna_pinyin_fluency
  - schema: bopomofo
  - schema: bopomofo_tw
  - schema: cangjie5
  - schema: stroke
  - schema: terra_pinyin
  - schema: ff7-ime
```

**幂等性**：安装脚本 `install_ff7_ime.py` 会先检查 `schema_list` 或 `schema_list/+` 中是否已有 `{schema: ff7-ime}`，有就跳过；重复运行不会产生重复项。

**备份**：脚本在修改 `default.custom.yaml`、覆盖 schema/lua、删除文件前，会把原文件复制到：

```
%APPDATA%\Rime\_backup\moguang_<YYYYmmdd-HHMMSS>\
```

**注意**：脚本用 PyYAML 读写，会丢失 `default.custom.yaml` 里的注释和原有缩进风格；文件内容语义不变，但格式会重排。若用户在 `default.custom.yaml` 里有大量注释，建议先手工备份或改用“只追加一行”的方式。

### 6.3 部署命令

```bat
start /wait "" "C:\Program Files\Rime\weasel-0.17.4\WeaselDeployer.exe" /deploy
echo exit=%ERRORLEVEL%
```

- `WeaselDeployer.exe` 是 **GUI 子系统**（PE `Subsystem: IMAGE_SUBSYSTEM_WINDOWS_GUI`）。在 cmd/批处理里直接运行不会等待，必须 `start /wait`；PowerShell 用 `Start-Process -Wait`。
- `/deploy` 对应源码 `Configurator::UpdateWorkspace()`：先尝试连接 WeaselServer 进入 maintenance，然后 `rime->deploy()`，再 `deploy_config_file("weasel.yaml")`，最后恢复服务。
- **退出码**：
  - `0`：没有并发 deployer、初始化成功；
  - `1`：`WeaselDeployerExclusiveMutex` 或 `WeaselDeployerMutex` 已存在（另一个部署进程）；
  - 源码中 `rime->deploy()` 的 bool 返回值被忽略，所以 **0 不代表 schema 一定构建成功**。
- 日志：`%TEMP%\rime.weasel\rime.weasel.<host>.<user>.log.INFO.<date>.<pid>.log`。成功部署会出现：
  ```
  deployment_tasks.cc:163] updating workspace.
  deployment_tasks.cc:186] updating schemas.
  deployment_tasks.cc:195] schema: ff7-ime
  config_data.cc:92] saving config file '...\build\ff7-ime.schema.yaml'
  ```
- 若 WeaselServer 没运行，deploy 仍会执行（`client.Connect()` 失败不阻断），但 IME 不会自动重载；需要 `start "" WeaselServer.exe` 或重新登录。

### 6.4 部署成功确认

1. 文件：
   ```bat
   if exist "%APPDATA%\Rime\build\ff7-ime.schema.yaml" echo BUILD_OK
   findstr /C:"schema_id: ff7-ime" "%APPDATA%\Rime\build\ff7-ime.schema.yaml"
   ```
2. 日志：
   ```powershell
   Select-String -Path "$env:TEMP\rime.weasel\*.log" -Pattern "ff7-ime|ERROR" | Select-Object -Last 20
   ```
3. 方案选单：`Ctrl+\`` 或 `F4`（`default.yaml` 的 `switcher/hotkeys`），应出现“魔光键影”。
4. 输入 `lkcc`，应出现候选。

### 6.5 切换方案

- `F4` 或 `Ctrl+\`` 打开方案选单；`Ctrl+Shift+1`（本方案 key_binder）切到下一个方案。
- `user.yaml` 会记录 `previously_selected_schema`，下次启动沿用。
- 若想让新用户默认进入本方案，把 `{schema: ff7-ime}` 放在 `schema_list` 第一位；已有用户的 `user.yaml` 仍可能记住上次方案。

### 6.6 Weasel portable 结论

- 0.17.4 官方 release 资产只有 `weasel-0.17.4.0-installer.exe`，没有 portable zip。
- Weasel 源码中没有 `portable` 逻辑；用户目录固定由 `WeaselUserDataPath()` 决定：
  ```cpp
  // RimeWithWeasel/WeaselUtility.cpp
  RegQueryValueEx(HKEY_CURRENT_USER, L"Software\\Rime\\Weasel", L"RimeUserDir", ...);
  // 缺省 %AppData%\Rime
  ```
- 因此**没有真正的 portable Weasel**。可行的替代：
  1. **便携数据目录**：`WeaselSetup.exe /userdir:<dir>`（源码 `WeaselSetup.cpp` 直接写 `RimeUserDir`），或 `reg add HKCU\Software\Rime\Weasel /v RimeUserDir /t REG_SZ /d <dir>`；然后重启 WeaselServer、部署。
  2. **便携方案包**（推荐）：Weasel 正常安装，zip 内只带 schema/lua/data/安装脚本，安装到 `%APPDATA%\Rime`。

详见 `portable-layout.md`。

### 6.7 不破坏现有 luna_pinyin_simp 的安装流程

1. 备份 `%APPDATA%\Rime`（至少 `default.custom.yaml`、`user.yaml`、`luna_pinyin.userdb`）。
2. 只新增 `ff7-ime.*`、`lua/ff7-ime.lua`、数据文件。
3. 只修改 `default.custom.yaml` 的 `patch/schema_list`（追加），不动 `customization`、`user.yaml`、`installation.yaml`。
4. 不删除、不覆盖 `luna_pinyin.*`、`build/luna_pinyin*`。
5. 部署后同时测试 luna_pinyin_simp 和 ff7-ime。实测两者共存：

```
luna_pinyin_simp + nihao -> 你好 / 妳好 / 逆号 ...
ff7-ime + lkcc -> 测试候选（lkcc 分段验证用）
build/default.yaml schema_list -> luna_pinyin_simp, ff7-ime
```

6. 回滚：`install_ff7_ime.py --uninstall`，恢复 `default.custom.yaml` 备份，部署。

---

## 7. 实测记录（临时 user dir）

测试工具：`_harness/rime_harness.py`，用 Python ctypes 直接加载安装目录的 `rime.dll`，调用 `RimeSetup` / `RimeInitialize` / `RimeStartMaintenance` / `RimeCreateSession` / `RimeSelectSchema` / `RimeSimulateKeySequence` / `RimeGetContext`。`shared_data_dir` 指向安装目录的 `data`（只读），`user_data_dir` 指向 `_testuser*`，日志写 `_testuser*/logs`。

### 7.1 基本输入

| 输入 | preedit | 候选 |
|---|---|---|
| `lkcc` | `lkcc` | 测试候选（lkcc 分段验证用） |
| `LKCC` | `LKCC` | 同上（Lua lower 后匹配） |
| `kld` | `kld` | 克劳德（简拼 initial_mode） |
| `kelaode` | `kelaode` | 克劳德（全拼） |
| `cloud` | `cloud` | 克劳德（keyword_mode） |
| `zzzz` | `zzzz` | 0 个 |
| `lkcc,` | 空 | 提交“测试候选…”后逗号交给应用 |

### 7.2 开关实测

`_testuser` 加 custom：

```yaml
patch:
  menu/page_size: 7
  switches/@1/reset: 0   # fuzzy_zh_z off
  switches/@5/reset: 1   # fuzzy_n_l on
```

结果：

```
option[fuzzy_zh_z] = 0
option[fuzzy_n_l] = 1
zang -> 0 candidates      (zh/z 模糊关闭)
lina -> 妮娜              (n/l 模糊打开)
page_size=7
```

`typo_mode` 运行时打开：

```
kelaod (typo off) -> 0
kelaod --option typo_mode=1 -> 克劳德
```

### 7.3 错误 patch 实测

```yaml
patch:
  switches/@fuzzy_zh_z/reset: 1
```

结果：

```
option[ascii_mode] = 1
option[fuzzy_zh_z] = 1
lkcc -> preedit='' candidates=0
```

### 7.4 共存安装实测

用真实 `default.custom.yaml`（只有 luna_pinyin_simp）复制到 `_testuser_coexist`，运行 `install_ff7_ime.py`：

- 第一次：追加 `{schema: ff7-ime}`；备份原文件到 `_backup/moguang_...`
- 第二次：识别已存在，不重复追加
- 部署后 `build/default.yaml` 同时有 luna_pinyin_simp 与 ff7-ime
- `nihao` 在 luna 下正常，`lkcc` 在 moguang 下正常

无 existing custom 的目录测试 `schema_list/+`：部署后 `build/default.yaml` 保留 default 的 8 个方案并追加 ff7-ime。

### 7.5 Lua 缺失实测

删除 `lua/ff7-ime.lua` 后部署：

```
E... lua_gears.cc:83] Lua Compoment of autoload error:( module: *ff7-ime ... ): module 'ff7-ime' not found:
E... lua_gears.cc:131] ... func type error expect function
lkcc -> 0 candidates
```

### 7.6 部署时间戳实测

同一秒内把 custom `top_n` 从 10 改成 20 后立即部署，构建文件仍是 10；等待 2 秒再部署才变成 20。原因：`__build_info/timestamps` 与 `last_write_time` 都是秒级整数。

### 7.7 卸载/回滚实测

- `install_ff7_ime.py --uninstall` 从 `schema_list`/`schema_list/+` 移除条目，并删除 `build/ff7-ime.*`；
- 部署后 `build/default.yaml` 恢复为默认 8 个方案，`build/` 无 moguang 产物；
- 如果不删除 `build/ff7-ime.schema.yaml`，即使从 schema_list 移除，`RimeSelectSchema("ff7-ime")` 仍可能返回成功（旧编译产物还在），所以卸载脚本必须删除 build 产物。

---

## 8. 常见坑与排查

### 坑 1：lua_translator 不加载，输入没有任何候选

症状：

- 输入 `lkcc`，preedit 有 `lkcc`，候选 0；
- 日志有 `autoload error` / `module '...' not found` / `func type error`。

原因：

1. `lua_translator@ff7-ime` 没有 `*`，而 `rime.lua` 里又没有 `ff7-ime = require("ff7-ime")`；
2. `lua/` 目录位置不对（应在 user dir 或 shared data dir 下）；
3. 文件名与组件别名不一致；
4. `return` 的不是 function/table；
5. 部署的 rime.dll 不带 Lua（本机带，但其他发行版可能不带）。

排查：

```powershell
Select-String -Path "$env:TEMP\rime.weasel\*.log" -Pattern "lua|autoload|not found|func type" |
  Select-Object -Last 30
```

修复：使用 `lua_translator@*ff7-ime`；确认 `%APPDATA%\Rime\lua\ff7-ime.lua`；重新部署。

### 坑 2：`lkcc` 被拆成多个 segment / 候选只匹配前缀

症状：

- preedit 显示 `l k c c` 或 `lk cc`；
- Lua 收到的 `input` 只有 `l` 或 `lk`；
- 只有部分输入能匹配。

原因：

- `speller/finals` 非空、`initials` 不是全 alphabet；
- `speller/algebra` 引入了拼音简写/纠错规则；
- `delimiter` 包含 `'` 或空格；
- `recognizer/patterns` 匹配了子区间。

排查：构建后的 `build/ff7-ime.schema.yaml` 里看 `speller` 和 `recognizer`；在 Lua 里临时打印 `input` 和 `seg.length`。

修复：按 §3 配置；不要在 speller 里 import `pinyin:/...`。

### 坑 3：候选被 uniquifier 去重/合并

症状：

- 数据里两条不同注释/不同来源的同名词条只剩一条；
- 或者候选文本相同但注释丢失。

原因：`engine/filters` 里挂了 `uniquifier`。源码 `uniquifier.cc` 会把文本相同的候选合并成 `UniquifiedCandidate`，只保留一行，注释取第一个。

排查：看 `build/ff7-ime.schema.yaml` 的 `engine/filters`。

修复：本方案不挂 `uniquifier`；Lua 自己按文本去重并保留第一条注释。若确实需要全局去重，再自行添加并接受合并行为。

### 坑 4：部署“没反应”，改了配置不生效

症状：

- 修改 schema/custom 后部署，候选/开关不变；
- `build/ff7-ime.schema.yaml` 的 `__build_info/timestamps` 没变。

原因：

1. 同一秒内修改并部署，秒级 mtime 比较认为“未变化”（实测）；
2. schema 根节点有显式 `__patch`，导致 `<schema>.custom.yaml` 自动 patch 被跳过；
3. `WeaselDeployer.exe /deploy` 是 GUI 子系统，批处理没等待就继续；
4. 另一个 deployer 占用 mutex，退出码 1；
5. 修改的是 `default.custom.yaml` 里的 `menu/page_size`，但 schema 自己也有 `menu/page_size`，schema 优先。

排查：

```powershell
Get-Item "$env:APPDATA\Rime\ff7-ime.schema.yaml" |
  Select-Object LastWriteTime
Get-Item "$env:APPDATA\Rime\build\ff7-ime.schema.yaml" |
  Select-Object LastWriteTime
Select-String -Path "$env:TEMP\rime.weasel\*.log" -Pattern "source file changed|updating schemas|ERROR"
```

修复：改完等 1-2 秒再部署；不要写根 `__patch`；用 `start /wait`；确保只有一个 deployer。

### 坑 5：F4/方案选单里看不到“魔光键影”

症状：部署成功，但方案选单没有。

原因：

1. `schema_id` 与文件名不一致；
2. `default.custom.yaml` 的 `patch/schema_list` 没包含；
3. YAML 解析失败（缩进、Tab、中文冒号）；
4. schema 文件放错目录（应在 user dir，文件名 `ff7-ime.schema.yaml`）；
5. 没有重新部署；
6. `default.custom.yaml` 被写成了顶层 `schema_list` 而不是 `patch/schema_list`。

排查：看 `build/default.yaml` 的 `schema_list`；看日志 `Error parsing YAML` / `nonexistent config file`。

修复：按 §6.2 写 patch；部署；检查 build。

### 坑 6：按名字 patch 开关，静默改错项

见 §5.2。`switches/@fuzzy_zh_z/reset` 会被当作 `@0`；必须用数字索引。

### 坑 7：`/deploy` 退出码 0 但实际失败

源码 `Configurator::UpdateWorkspace()`：

```cpp
rime->deploy();  // 返回值未使用
...
return 0;
```

退出码 0 只代表没有并发 deployer。必须检查 `build/` 产物和日志中的 `ERROR`。

### 坑 8：卸载后旧方案仍能被选中

原因：`build/ff7-ime.schema.yaml` 不会因为从 `schema_list` 移除而自动删除。`RimeSelectSchema` 仍可能成功。卸载脚本必须删除 `build/ff7-ime.*`，并重新部署。

---

## 9. 未实测与限制

- **未在真实 Weasel IME 进程中测试**：没有运行 `WeaselDeployer.exe /deploy` 对真实 `%APPDATA%\Rime` 部署，也没有在游戏/记事本里通过 TSF 实际按键。所有实测均通过 `rime.dll` C API + 临时 user dir 完成，schema 编译、Lua 加载、候选生成、开关行为都是真实 librime 行为；WeaselDeployer 的 CLI/退出码/日志依据源码和现有日志推断。
- **未测试 F4/方案选单的 UI**：`schema_list` 构建结果已验证；F4 弹出行为依赖 Weasel UI。
- **未测试 portable 包在干净机器上的安装**：`WeaselSetup /userdir` 只依据源码确认写注册表，没有实际改本机注册表。
- **未测试 1212 条正式数据的匹配性能**：骨架数据只有 6-8 条；正式算法应由 `algorithm-design` / `pinyin-data` 任务替换 `match_entries()`。
- **Lua 骨架的模糊匹配是字符串级近似**：`zh→z`、`ng→n` 等 gsub 不理解音节边界，只用于验证开关通路；正式实现应按声母/韵母展开，避免跨音节误匹配。

---

## 10. 交付文件

| 文件 | 用途 |
|---|---|
| `REPORT.md` | 本报告 |
| `ff7-ime.schema.yaml` | 可直接作为起点的 schema 骨架（含注释） |
| `ff7-ime.custom.yaml` | 开关/候选数/注释配置示例 |
| `lua/ff7-ime.lua` | Lua translator 参考实现（骨架级匹配） |
| `ff7-ime_data.sample.tsv` | 数据格式样例 |
| `install.md` | 安装、部署、验证、切换方案 |
| `uninstall.md` | 卸载与回滚 |
| `portable-layout.md` | portable 包目录结构与替代方案 |
| `install_ff7_ime.py` | 幂等安装/卸载脚本（备份 + schema_list 合并） |
| `_harness/rime_harness.py` | 临时 user dir 的 librime 测试工具（可选） |
