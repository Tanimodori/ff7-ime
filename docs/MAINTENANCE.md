# 维护说明

---

## 1. 文件职责

| 文件 | 维护方式 |
|---|---|
| `dict.txt` | 词条唯一来源；UTF-16 LE BOM，每行一条 |
| `experiments/pinyin-data/override.yaml` | 人工读音/误读覆盖；优先级最高 |
| `experiments/pinyin-data/extract.py` | 生成 `phrases.tsv`/`chars.tsv` |
| `experiments/pinyin-data/phrases.tsv` | 注音中间产物；可人工审阅 |
| `tools/build_from_pinyin_data.py` | 生成最终 `src/lua/mgjy_data.lua` |
| `src/lua/mgjy_matcher.lua` | 匹配算法；改动需跑全量测试 |
| `src/lua/mgjy.lua` | Rime 适配/配置读取；改动需跑 Rime 集成 |
| `src/moguang_jianying.schema.yaml` | 方案接线/默认配置 |
| `src/moguang_jianying.custom.yaml` | 用户配置示例 |
| `packaging/*.ps1` | 安装/卸载/无头部署 |
| `tools/build_package.py` | 生成 portable 分发包（含 MANIFEST/SHA256SUMS） |
| `tests/*` | 回归测试 |

---

## 2. 更新词库

### 2.1 增删词条

1. 编辑 `dict.txt`（保持 UTF-16 LE BOM，每行一条；不要留空行）；
2. 重新生成注音：

```bash
python experiments/pinyin-data/extract.py
python experiments/pinyin-data/extract.py --check
```

3. 重新生成 Lua 数据：

```bash
python tools/build_from_pinyin_data.py
```

4. 跑核心/全量测试：

```bash
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/run_cases.js tests/lua/core_cases.json src/lua/mgjy_data.lua
python tools/gen_eval_cases.py
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" node tests/lua/bulk_eval.js
```

5. 部署到本机：

```bash
python tools/build_package.py
# 方式 A：包安装脚本
powershell -NoProfile -ExecutionPolicy Bypass -File dist\moguang_jianying-portable\install.ps1
# 方式 B：只复制数据并重建
copy src\lua\mgjy_data.lua "%APPDATA%\Rime\lua\mgjy_data.lua"
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\deploy-rime.ps1
```

6. 按 F4/Ctrl+` 切换方案，输入新词条全拼验证。

### 2.2 词条格式注意事项

- 只允许一行一条；标点可以保留；
- 不要使用 Excel 另存，容易改变编码/BOM；
- 若出现重复词条，候选会重复，建议先去重；
- 词条中的标点不参与拼音；`extract.py` 只对汉字注音；
- 间隔号 `·` 原样输出，不注音。

---

## 3. 修正读音

### 3.1 优先级

```
confirmed_phrases（整词）
  > char_rules（上下文规则）
  > char_defaults（单字默认）
  > pypinyin 词组
  > pypinyin 单字
```

### 3.2 常见修改

**整词读音**：

```yaml
confirmed_phrases:
  - phrase: "曾"
    readings: ["zeng1"]
    reason: "Tseng；姓氏读 zēng"
```

**上下文规则**（某字在包含某子串时改读）：

```yaml
char_rules:
  - char: "长"
    when_contains: "长杖"
    reading: "chang2"
    reason: "长杖 = cháng zhàng"
```

**单字默认**：

```yaml
char_defaults:
  - char: "勒"
    reading: "le4"
    reason: "译名勒读 lè"
```

**允许误读**（低权重，不替代规范读音）：

```yaml
misread_candidates:
  "梣": ["qin2", "chen2"]
  "曾": ["ceng2"]
  "骰": ["shai3"]
```

修改后必须：

```bash
python experiments/pinyin-data/extract.py
python experiments/pinyin-data/extract.py --check
python tools/build_from_pinyin_data.py
```

然后重跑核心测试并部署。

### 3.3 如何确认某字最终读音

```bash
python - <<'PY'
import json
rows=json.load(open('data/phrases.json',encoding='utf-8'))
for r in rows:
    if r['text'] in ('曾','防御长杖','梣木','骰子'):
        print(r['text'], r['syls'], r['alts'])
PY
```

- `syls` 是主读音；
- `alts` 是备选（多音/误读），带权重。

---

## 4. 调参

### 4.1 候选数 N

`mgjy/top_n`（1–64）；建议 `menu/page_size` 等于 N。修改后重新部署。

### 4.2 模糊音

`mgjy/fuzzy/*`：

- 开启更多模糊（`n_l`、`r_l`、`f_h`、`en_eng`、`in_ing`）会提高召回，但可能增加歧义；
- 关闭 `ng_n` 会让 `senguilon` 之类失效；
- `v_u` 建议保持开启。

### 4.3 容错

- `mgjy/typo/max_edit`：0–4，默认 2；
- `mgjy/typo/transposition`：相邻字母换位；
- `mgjy/typo/syllable_swap`：相邻音节换位；
- `mgjy/typo/enabled: false`：严格模式（只精确/模糊整音节）。

### 4.4 关键词/声母

- `mgjy/initial/enabled`：总开关；
- `mgjy/keyword/gap_penalty`：跳跃惩罚，越大越偏好紧凑匹配；
- `mgjy/weights/keyword` / `initial_exact` / `initial`：通道权重。

### 4.5 性能与回退

- `mgjy/dp_max_candidates`：默认 56；卡顿降到 40/32；召回不足升到 64/80；
- `mgjy/fallback/dp_min_raw`：默认 0.65；调高会丢弃更多低置信 DP，调低会保留更多“硬凑”候选；
- `mgjy/fallback/strong_raw`：默认 0.70；有强命中时只用小池补位；
- `mgjy/fallback/fast_max_candidates`：默认 16；`max_candidates`：默认 96；
- 长模糊输入最坏约 65 ms/键；精确/前缀 5–10 ms/键。

### 4.6 调参后的验证

```bash
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" \
  node tests/lua/run_cases.js tests/lua/core_cases.json src/lua/mgjy_data.lua
NODE_PATH="$PWD/tools/lua-sandbox/node_modules" node tests/lua/bulk_eval.js
```

至少保证：

- `lkcc`、`wmhlkcdccnm`、`shenl`、`lienuo`、`leino`、`leiknuo`、`nuolei` top1；
- 精确全拼 1212/1212；
- 乱码仍返回 N。

---

## 5. 日志与调试

| 内容 | 路径 |
|---|---|
| Rime/Weasel 日志 | `%TEMP%\rime.weasel\rime.weasel.*.log` |
| 构建产物 | `%APPDATA%\Rime\build\` |
| 安装备份 | `%APPDATA%\Rime\default.custom.yaml.mgjy-backup-*` |
| 临时测试 user dir | `%TEMP%\mgjy-*` |

调试候选分数：

```yaml
patch:
  mgjy/show_score: true
```

注释会变成 `通道 · 拼音 · 0.xx`。

调试 Lua 错误：

```powershell
Get-ChildItem "$env:TEMP\rime.weasel\*.log" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1 |
  Select-String -Pattern "lua|ERROR|mgjy" -Context 2,2
```

---

## 6. 备份与回滚

### 6.1 安装前备份

`install.ps1` 自动备份 `default.custom.yaml`。建议同时手动备份整个 `%APPDATA%\Rime`：

```powershell
Copy-Item "$env:APPDATA\Rime" "$env:APPDATA\Rime.backup-$(Get-Date -Format yyyyMMdd-HHmmss)" -Recurse
```

### 6.2 回滚方案文件

```powershell
# 删除本方案文件
Remove-Item "$env:APPDATA\Rime\moguang_jianying.*" -Force
Remove-Item "$env:APPDATA\Rime\lua\mgjy*.lua" -Force
# 恢复 default.custom.yaml 备份（或手动删掉本方案条目）
Copy-Item "$env:APPDATA\Rime\default.custom.yaml.mgjy-backup-<timestamp>" `
          "$env:APPDATA\Rime\default.custom.yaml" -Force
# 无头重建
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\deploy-rime.ps1
```

或直接运行 `uninstall.ps1 -RestoreBackup`。

### 6.3 版本回滚

保留上一版 `dist/moguang_jianying-portable.zip`、对应的 `.zip.sha256` 与 `src/` 快照；回滚时用旧包重装即可。

---

## 7. 版本管理

- `src/moguang_jianying.schema.yaml` 的 `schema/version`
- `tools/build_package.py` 的 `VERSION`
- `README.md` 的版本段
- 建议 git tag：`v1.0.0`、`v1.0.1` …

数据变更与算法变更分开提交，便于定位回归。

---

## 8. 常见故障速查

| 症状 | 原因 | 处理 |
|---|---|---|
| 方案不显示 | `build/default.yaml` 没有条目 | 检查 `default.custom.yaml`，跑 `deploy-rime.ps1` |
| 有方案无候选 | Lua 模块未加载/文件名错 | 检查 `lua/mgjy*.lua`、`lua_translator@*mgjy`、日志 |
| 输入被拆段 | `speller/algebra`/`finals`/`delimiter` 配置 | 保持 `alphabet` 全字母、`finals` 空、无 algebra |
| `lkcc` 被当 ASCII | `ascii_mode` 打开 | F4 关闭“西文”或 `Shift` 切回 |
| 改了配置不生效 | 秒级 mtime/未重建 | 等 2 秒再 `deploy-rime.ps1`；重启 WeaselServer |
| luna 丢失 | WeaselDeployer GUI 改写 | 恢复备份，确认两方案，跑 `deploy-rime.ps1` |
| 输入卡顿 | 长模糊/容错 DP | 降 `dp_max_candidates`、`max_edit`，关可选模糊 |
| 生僻字读音错 | 数据覆盖缺失 | 改 `override.yaml`，重跑 2.2/2.3 |
| 候选重复 | `dict.txt` 重复 | 去重后重建 |

---

## 9. 安全与隐私

- 方案不联网、不写外部日志、不上传输入；
- 只读取 `%APPDATA%\Rime` 与安装目录的 Rime 数据；
- 所有候选来自本地 `mgjy_data.lua`；
- 安装脚本只修改 `%APPDATA%\Rime` 下本方案相关文件和 `default.custom.yaml` 的 `schema_list` 条目；
- 卸载脚本不删除 `luna_pinyin_simp` 等既有方案。
