# 构建说明

> 本文说明如何从 `data/dict.txt` 重新生成拼音数据、Lua 数据、Plum 安装包，以及如何运行测试。
> 运行时不需要 Python/Node；它们只用于构建与测试。

---

## 1. 环境

| 工具 | 版本（本机实测） | 用途 |
|---|---|---|
| Python | 3.14.7 x64 | 注音、数据构建、评估用例、打包 |
| pypinyin | 0.55.0 | 主注音源 |
| PyYAML | 6.0.3 | 读取 `override.yaml` |
| Node.js | 24.21.0 | 运行 wasmoon Lua 5.4 沙箱测试 |
| wasmoon | `npm install wasmoon` | 纯 Lua 引擎测试 |
| Weasel | 0.17.4 x64 | 真实 Rime 集成测试 |
| librime | 1.13.1（内嵌） | `rime.dll` |
| Lua | 5.4.7（内嵌） | 运行时 |

安装 Python 依赖：

```bash
python -m pip install pypinyin pyyaml
```

安装 Lua 沙箱依赖：

```bash
cd tools/lua-sandbox
npm install wasmoon
```

---

## 2. 从零重建

### 2.1 确认词表

`data/dict.txt` 必须是：

- UTF-16 LE + BOM（当前文件就是）；
- 每行一个词条；
- 可含中文标点（`！，·……？、`）；
- 无重复（当前 1212 条唯一）。

检查：

```bash
python - <<'PY'
raw = open('data/dict.txt','rb').read().decode('utf-16')
lines = [l.strip('\ufeff\r\n\t ') for l in raw.splitlines() if l.strip('\ufeff\r\n\t ')]
print(len(lines), len(set(lines)))
PY
```

期望：`1212 1212`。

### 2.2 生成注音 TSV

```bash
python experiments/pinyin-data/extract.py
```

- 读取 `data/dict.txt`、`override.yaml`；
- 使用 pypinyin + luna_pinyin + terra_pinyin 交叉校验；
- 输出 `experiments/pinyin-data/phrases.tsv`、`chars.tsv`。

校验：

```bash
python experiments/pinyin-data/extract.py --check
```

期望：覆盖 1212/1212，无缺失/冲突。

> 若修改了 `override.yaml`（读音/误读），先重跑本步，再跑 2.3。

### 2.3 生成最终 Lua 数据

```bash
python tools/build_from_pinyin_data.py
```

输入：

- `experiments/pinyin-data/phrases.tsv`
- `experiments/pinyin-data/override.yaml`

输出：

- `lua/ff7-ime_data.lua`
- `data/phrases.json`

规则：

- 主读音来自 TSV；
- 备选读音 = 语料内上下文读音（0.97）+ `misread_candidates`（0.90）+ 少量补充；
- 每条最多 8 个全拼变体，组合权重为乘积；
- 声母变体、相邻换位一并生成。

期望输出示例：

```
phrases=1212 alt-slots=586 full-variants=1973 init-variants=1543
wrote lua/ff7-ime_data.lua
```

### 2.4 运行核心与全量测试

```bash
# 核心用例
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/run_cases.js tests/lua/core_cases.json lua/ff7-ime_data.lua

# 生成全量评估用例
python tools/gen_eval_cases.py

# 全量评估（wasmoon）
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/bulk_eval.js
```

期望：

- 核心 40/40（含 `meishao` 中段关键词、`di'ou` 预编辑分词、`fagnge` 换位/模糊对齐、fallback 与 DP 置信度回归）；
- exact 1212/1212；
- fuzzy 878/878；
- initial 1212/1212（top1 或 top3）；
- typo 600/600（top3）；
- keyword 233/238 top5（极稀疏声母子序列的天然歧义）；
- mid_keyword 300/300 top5（长句中段唯一音节串）；
- fallback 7/7（n-gram + Damerau/Dice-LCS 回退）。

### 2.5 真实 Rime 集成测试

用临时 user dir，不碰真实配置：

```bash
cd experiments/rime-harness
python rime_harness.py \
  --shared "C:\Program Files\Rime\weasel-0.17.4\data" \
  --user "%TEMP%\ff7-ime-build-test" \
  --schema ff7-ime \
  --input lkcc --deploy always --json
```

首次运行会自动部署（约 3–5 秒）。期望候选第一项为“我们会立刻彻底铲除你们！”。

预编辑与提交绑定：

```bash
# preedit 应为 di'ou；meishao 应为 mei'shao
python rime_harness.py ... --input diou --json
python rime_harness.py ... --input meishao --json

# 回车 / 小键盘回车都应提交高亮候选
python rime_harness.py ... --sequence "meishao{Return}" --json
python rime_harness.py ... --sequence "meishao{KP_Enter}" --json
```

也可以逐个测试：

```bash
for q in shenluo senluo leinuo lienuo leino leiknuo nuolei zanguokuaigon; do
  python rime_harness.py ... --input "$q" --json
done
```

### 2.6 校验 Plum 包布局

仓库本身就是 Plum 包：根 `recipe.yaml` 只安装 schema + 3 个 Lua 文件。

```bash
python tools/check_package.py
```

期望：

```
recipe: ff7-ime 1.0.0
installed files (4):
  ff7-ime.schema.yaml
  lua/ff7-ime.lua
  lua/ff7-ime_data.lua
  lua/ff7-ime_matcher.lua
package layout OK
```

脚本会检查：

- `recipe.yaml` 的安装清单恰好是 4 个运行时文件；
- recipe 版本与 schema 版本一致；
- `schema_id: ff7-ime`、`author: Tanimodori`、`description: 魔光键影专属拼音输入方案`；
- `engine.translators` 含 `lua_translator@*ff7-ime`；
- 不安装 `*.custom.yaml`、`data/dict.txt`、测试或文档；
- 安装路径没有绝对路径或 `..`。

### 2.7 本地 Plum 安装验证

仓库尚未公开时，可以用本地克隆模拟 GitHub 的 Plum 安装：

1. 先把当前改动提交；
2. 把仓库克隆到 Plum 缓存目录：

   ```bash
   mkdir -p "$APPDATA/plum/package/Tanimodori"
   git clone --depth 1 <本仓库路径> "$APPDATA/plum/package/Tanimodori/ff7-ime"
   ```

3. 运行官方 `rime-install.bat`，输入 `Tanimodori/ff7-ime`；
4. 确认输出包含 `Installing recipe:` 和 4 个 `Installing:` 文件；
5. 检查用户目录只有 `ff7-ime.schema.yaml` 与 `lua/ff7-ime*.lua`，
   没有 custom、`data/dict.txt`、tests。

用临时 user dir 做真实 librime 验证（不碰真实配置）：

```bash
python experiments/rime-harness/rime_harness.py \
  --user "$TEMP/ff7-ime-plum-test" \
  --schema ff7-ime --input shenluo --deploy always --json
```

真实用户目录的安装、旧 `moguang_jianying` 迁移见 [INSTALL.md](INSTALL.md)。

---

## 3. 一键重建脚本（示例）

```bash
set -e
cd "D:/Tanimodori/Projects/@FF14/ff7-ime"

python experiments/pinyin-data/extract.py
python experiments/pinyin-data/extract.py --check
python tools/build_from_pinyin_data.py

NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/run_cases.js tests/lua/core_cases.json lua/ff7-ime_data.lua

python tools/gen_eval_cases.py
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" node tests/lua/bulk_eval.js

python tools/check_package.py
```

---

## 4. 版本升级

修改以下位置：

1. `ff7-ime.schema.yaml` 的 `schema/version`；
2. `recipe.yaml` 的 `recipe/version`（必须与 schema 一致）；
3. `README.md` 的版本段；
4. 如数据有变，重跑 2.2–2.6。

---

## 5. 构建期常见问题

| 问题 | 处理 |
|---|---|
| `ModuleNotFoundError: pypinyin` | `python -m pip install pypinyin` |
| `ModuleNotFoundError: yaml` | `python -m pip install pyyaml` |
| wasmoon 报 `cannot open ...` | 测试脚本用 `fs.readFileSync` + `doString`，不依赖虚拟文件系统；确认 `NODE_PATH` 指向 `tools/lua-sandbox/node_modules` |
| `extract.py --check` 报读音冲突 | 检查 `override.yaml` 的 `char_rules`/`confirmed_phrases`，修正后重跑 |
| 数据条数不是 1212 | 检查 `data/dict.txt` 编码/空行/重复；不要用 Excel 另存导致编码变化 |
| Lua 数据过大 | 默认最多 8 个 full 变体；可降低 `--cap`，但会减少多音组合覆盖 |
| `check_package.py` 报版本不一致 | 同步 `ff7-ime.schema.yaml` 的 `schema/version` 与 `recipe.yaml` 的 `recipe/version` |
| 包安装后 `build` 无产物 | 确认 `rime.dll` 架构为 x64、`shared_data_dir` 有 `default.yaml`；用 harness 的 `--deploy always` 查看部署错误 |
| 中文路径失败 | 用纯 ASCII 临时路径测试定位；确认 Python/Node 以 UTF-8 读取路径 |

---

## 6. 不修改的目录

- `experiments/` 下的探针/研究产物可保留，不参与运行时；
- `tools/lua-sandbox/node_modules` 仅为测试依赖，不进入 Plum 安装包；
- `recipe.yaml` 是安装清单，改动后必须跑 `tools/check_package.py`。
