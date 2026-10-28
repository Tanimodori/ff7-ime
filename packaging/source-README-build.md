# 在 portable 分发包内重建 Lua 数据

包内 `source/` 已包含：

- `dict.txt`：原始词表
- `phrases.tsv`：已注音的 1212 条（可直接用于重建）
- `override.yaml`：人工读音/误读覆盖
- `build_from_pinyin_data.py`：生成 `mgjy_data.lua`

## 只重建 Lua 数据（推荐）

在包根目录执行：

```bash
python source/build_from_pinyin_data.py \
  --input source/phrases.tsv \
  --override source/override.yaml \
  --lua rime/lua/mgjy_data.lua \
  --json data/phrases.json
```

然后把 `rime/lua/mgjy_data.lua` 复制到 `%APPDATA%\Rime\lua\`，并运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy-rime.ps1
```

## 修改读音

编辑 `source/override.yaml` 后，重新执行上面的构建命令。

## 修改词条

1. 编辑 `source/dict.txt`（UTF-16 LE BOM，每行一条）；
2. 需要重新注音时，在完整源码仓库中使用
   `experiments/pinyin-data/extract.py` 重新生成 `phrases.tsv`（需要 pypinyin + PyYAML）；
3. 再执行上面的 Lua 数据构建命令。

> 包内不包含 pypinyin 注音脚本的完整运行环境；如果只是增删已有注音词条，可直接编辑
> `phrases.tsv`（保持列格式）后重建。
