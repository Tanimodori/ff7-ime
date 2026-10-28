# 魔光键影 卸载与回滚指南

目标：完整移除 `moguang_jianying`，恢复 `default.custom.yaml`，不影响
`luna_pinyin_simp` 及其用户词库。

---

## 1. 使用卸载脚本（推荐）

```bat
python install_moguang.py --user-dir "%APPDATA%\Rime" --uninstall
```

脚本会：

1. 从 `default.custom.yaml` 的 `patch/schema_list` 或 `patch/schema_list/+`
   中移除 `{schema: moguang_jianying}`；
2. 把 `default.custom.yaml` 备份到 `_backup\moguang_<时间戳>\`；
3. 把 `moguang_jianying.schema.yaml`、`moguang_jianying.custom.yaml` 移到备份目录；
4. 删除 `build\moguang_jianying.*`（编译产物），因为从 `schema_list` 移除不会
   自动删除它们；不删的话 `RimeSelectSchema("moguang_jianying")` 仍可能选中旧方案。

默认**保留**：

- `lua\moguang_jianying.lua`
- `moguang_jianying_data.tsv`

如果确定不再需要，加 `--purge`：

```bat
python install_moguang.py --user-dir "%APPDATA%\Rime" --uninstall --purge
```

先预览（不写任何文件）：

```bat
python install_moguang.py --user-dir "%APPDATA%\Rime" --uninstall --dry-run
```

---

## 2. 手动卸载

### 2.1 修改 default.custom.yaml

如果原来是：

```yaml
patch:
  schema_list:
    - {schema: luna_pinyin_simp}
    - {schema: moguang_jianying}
```

改回：

```yaml
patch:
  schema_list:
    - {schema: luna_pinyin_simp}
```

如果是 `schema_list/+` 形式：

```yaml
patch:
  schema_list/+:
    - {schema: moguang_jianying}
```

删除整个 `schema_list/+` 项，或只删掉 moguang 那一行。

### 2.2 删除/移走文件

```bat
set RIME_USER=%APPDATA%\Rime
set BACKUP=%USERPROFILE%\Rime-uninstall-moguang
mkdir "%BACKUP%"

move "%RIME_USER%\moguang_jianying.schema.yaml" "%BACKUP%\" 2>nul
move "%RIME_USER%\moguang_jianying.custom.yaml" "%BACKUP%\" 2>nul
move "%RIME_USER%\moguang_jianying_data.tsv" "%BACKUP%\" 2>nul
move "%RIME_USER%\lua\moguang_jianying.lua" "%BACKUP%\" 2>nul
```

### 2.3 删除构建产物（关键）

```bat
del "%APPDATA%\Rime\build\moguang_jianying.schema.yaml" 2>nul
del "%APPDATA%\Rime\build\moguang_jianying.prism.bin" 2>nul
```

如果以后重新安装，部署会重新生成。

### 2.4 重新部署

```bat
start /wait "" "C:\Program Files\Rime\weasel-0.17.4\WeaselDeployer.exe" /deploy
```

### 2.5 验证

```bat
findstr /C:"moguang_jianying" "%APPDATA%\Rime\build\default.yaml"
```

应无输出。

```bat
if exist "%APPDATA%\Rime\build\moguang_jianying.schema.yaml" echo STILL_EXISTS
```

应无输出。

切换到 `朙月拼音·简化字`，输入 `nihao`，确认仍正常。

---

## 3. 完整回滚（恢复安装前状态）

如果安装时做了完整备份：

```bat
set BACKUP=%USERPROFILE%\Rime-backup-full

rem 先停止 WeaselServer
"C:\Program Files\Rime\weasel-0.17.4\WeaselServer.exe" /q

rem 恢复用户目录（会覆盖同名文件；确认备份内容后再执行）
robocopy "%BACKUP%" "%APPDATA%\Rime" /E /COPY:DAT /R:1 /W:1

rem 重新启动并部署
start "" "C:\Program Files\Rime\weasel-0.17.4\WeaselServer.exe"
start /wait "" "C:\Program Files\Rime\weasel-0.17.4\WeaselDeployer.exe" /deploy
```

注意：

- `robocopy /E` 不会删除目标中多出来的文件；本方案的文件仍需按 §2.2 删除。
- 不要把整个 `build/` 从旧备份恢复后就不再部署；部署会按当前配置重建。
- `luna_pinyin.userdb` 是用户词库，恢复前确认备份时间，避免丢失新学词。

---

## 4. 使用脚本备份恢复

脚本备份目录示例：

```
%APPDATA%\Rime\_backup\moguang_20261028-204717\
├─ default.custom.yaml
├─ moguang_jianying.schema.yaml
├─ moguang_jianying.custom.yaml
├─ build_moguang_jianying.schema.yaml
└─ ...
```

恢复单个文件：

```bat
copy "%APPDATA%\Rime\_backup\moguang_20261028-204717\default.custom.yaml" "%APPDATA%\Rime\default.custom.yaml"
```

然后部署。

---

## 5. 卸载后的检查清单

- [ ] `default.custom.yaml` 不再包含 `moguang_jianying`
- [ ] `%APPDATA%\Rime` 下没有 `moguang_jianying.*`
- [ ] `%APPDATA%\Rime\lua\moguang_jianying.lua` 已移走（如选择 purge）
- [ ] `%APPDATA%\Rime\build` 下没有 `moguang_jianying.*`
- [ ] 部署成功，日志无 YAML/ERROR
- [ ] `luna_pinyin_simp` 输入正常
- [ ] 方案选单不再显示“魔光键影”

---

## 6. 只禁用、不卸载

如果只是想暂时停用：

1. 从 `default.custom.yaml` 的 `schema_list` 中移除 `{schema: moguang_jianying}`；
2. 重新部署；
3. 保留文件，随时可以再加回列表。

这样不会删除用户数据，也不影响 luna_pinyin_simp。
