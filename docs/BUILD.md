# 构建说明

> 本文说明如何从 `dict.txt` 重新生成拼音数据、Lua 数据、portable 分发包，以及如何运行测试。
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

`dict.txt` 必须是：

- UTF-16 LE + BOM（当前文件就是）；
- 每行一个词条；
- 可含中文标点（`！，·……？、`）；
- 无重复（当前 1212 条唯一）。

检查：

```bash
python - <<'PY'
raw = open('dict.txt','rb').read().decode('utf-16')
lines = [l.strip('\ufeff\r\n\t ') for l in raw.splitlines() if l.strip('\ufeff\r\n\t ')]
print(len(lines), len(set(lines)))
PY
```

期望：`1212 1212`。

### 2.2 生成注音 TSV

```bash
python experiments/pinyin-data/extract.py
```

- 读取 `dict.txt`、`override.yaml`；
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

- `src/lua/mgjy_data.lua`
- `data/phrases.json`

规则：

- 主读音来自 TSV；
- 备选读音 = 语料内上下文读音（0.97）+ `misread_candidates`（0.90）+ 少量补充；
- 每条最多 8 个全拼变体，组合权重为乘积；
- 声母变体、相邻换位一并生成。

期望输出示例：

```
phrases=1212 alt-slots=586 full-variants=1973 init-variants=1543
wrote src/lua/mgjy_data.lua
```

### 2.4 运行核心与全量测试

```bash
# 核心用例
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/run_cases.js tests/lua/core_cases.json src/lua/mgjy_data.lua

# 生成全量评估用例
python tools/gen_eval_cases.py

# 全量评估（wasmoon）
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/bulk_eval.js
```

期望：

- 核心 34/34（含 `meishao` 中段关键词与 `di'ou` 预编辑分词回归）；
- exact 1212/1212；
- fuzzy 878/878；
- initial 1212/1212（top1 或 top3）；
- typo 600/600（top3）；
- keyword 233/238 top5（极稀疏声母子序列的天然歧义）；
- mid_keyword 300/300 top5（长句中段唯一音节串）；
- fallback 7/7。

### 2.5 真实 Rime 集成测试

用临时 user dir，不碰真实配置：

```bash
cd experiments/rime-harness
python rime_harness.py \
  --shared "C:\Program Files\Rime\weasel-0.17.4\data" \
  --user "%TEMP%\mgjy-build-test" \
  --schema moguang_jianying \
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

### 2.6 构建分发包（portable）

```bash
python tools/build_package.py
```

这里的 **portable 指可分发档案**：一个自包含的 Rime 方案 zip，`rime/` 目录即 Rime 用户目录覆盖层，可直接复制安装，也可用包内脚本安装。

输出：

- `dist/moguang_jianying-portable/`
- `dist/moguang_jianying-portable.zip`
- `dist/moguang_jianying-portable.zip.sha256`

> `dist/` 是构建产物，已在 `.gitignore` 中忽略，不进入版本库；需要分发时再构建。
> 包内 `docs/` 不包含 `install-real*.log` 等开发机日志。

包内容：

```
README.md, VERSION, MANIFEST.txt, SHA256SUMS
install.ps1/.cmd, uninstall.ps1/.cmd, verify.ps1/.cmd
deploy-rime.ps1
rime/moguang_jianying.schema.yaml
rime/moguang_jianying.custom.yaml
rime/lua/mgjy.lua, mgjy_matcher.lua, mgjy_data.lua
docs/...
source/README-build.md
source/dict.txt, phrases.tsv, override.yaml, extract.py, 构建脚本
tools/rime_harness.py
```

构建脚本会校验 zip：无绝对路径/`..`/反斜杠成员名，且只有一个顶层目录。`MANIFEST.txt` 记录 schema、版本、目标平台与安装入口；`SHA256SUMS` 覆盖包内每个文件；`.zip.sha256` 覆盖压缩包本身。

### 2.7 分发包冒烟测试

先核对压缩包哈希：

```bash
(cd dist && sha256sum -c moguang_jianying-portable.zip.sha256)
```

再在临时 user dir 重放安装：

```powershell
$Test = "$env:TEMP\mgjy-pkg-test"
Remove-Item -Recurse -Force $Test -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Test | Out-Null

.\dist\moguang_jianying-portable\install.ps1 -RimeUserDir $Test -NoDeploy
.\dist\moguang_jianying-portable\deploy-rime.ps1 -UserDataDir $Test
```

检查：

```powershell
Get-Content "$Test\default.custom.yaml"
Get-Content "$Test\build\default.yaml" | Select-String schema_list -Context 0,3
Test-Path "$Test\build\moguang_jianying.schema.yaml"
```

期望：两个方案都在列表、构建产物存在。

---

## 3. 一键重建脚本（示例）

```bash
set -e
cd "D:/Tanimodori/Projects/@FF14/ff7-ime"

python experiments/pinyin-data/extract.py
python experiments/pinyin-data/extract.py --check
python tools/build_from_pinyin_data.py

NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/run_cases.js tests/lua/core_cases.json src/lua/mgjy_data.lua

python tools/gen_eval_cases.py
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" node tests/lua/bulk_eval.js

python tools/build_package.py
```

---

## 4. 版本升级

修改以下位置：

1. `src/moguang_jianying.schema.yaml` 的 `schema/version`；
2. `tools/build_package.py` 写入的 `VERSION`；
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
| 数据条数不是 1212 | 检查 `dict.txt` 编码/空行/重复；不要用 Excel 另存导致编码变化 |
| Lua 数据过大 | 默认最多 8 个 full 变体；可降低 `--cap`，但会减少多音组合覆盖 |
| 包安装后 `build` 无产物 | 运行 `deploy-rime.ps1` 查看错误；确认 `rime.dll` 架构为 x64、`shared_data_dir` 有 `default.yaml` |
| 中文路径失败 | PowerShell 脚本用 UTF-8 无 BOM 写配置；`deploy-rime.ps1` 用 UTF-8 传路径；如仍失败，改用纯 ASCII 临时路径测试定位 |

---

## 6. 不修改的目录

- `experiments/` 下的探针/研究产物可保留，不参与运行时；
- `tools/lua-sandbox/node_modules` 仅为测试依赖，不进入 portable 分发包；
- `dist/` 由 `build_package.py` 重新生成，不要手改。
