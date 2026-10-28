#!/usr/bin/env python3
"""Safely add/remove the 魔光键影 schema in a Weasel user directory.

Never writes to %APPDATA%\\Rime unless you pass that directory explicitly.
Every modified/removed file is backed up first.

Examples:
  python install_ff7_ime.py --user-dir "C:/Users/me/AppData/Roaming/Rime"
  python install_ff7_ime.py --user-dir ... --dry-run
  python install_ff7_ime.py --user-dir ... --uninstall
"""
import argparse
import datetime as _dt
import os
import shutil
import sys

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML：python -m pip install pyyaml")

SCHEMA_ID = "ff7-ime"
HERE = os.path.dirname(os.path.abspath(__file__))
FILES = [
    ("ff7-ime.schema.yaml", "ff7-ime.schema.yaml"),
    ("ff7-ime.custom.yaml", "ff7-ime.custom.yaml"),
    (os.path.join("lua", "ff7-ime.lua"), os.path.join("lua", "ff7-ime.lua")),
    ("ff7-ime_data.sample.tsv", "ff7-ime_data.tsv"),
]

# 用户可能已经改过这两类文件，安装/升级时不覆盖。
KEEP_IF_EXISTS = {
    "ff7-ime.custom.yaml",
    "ff7-ime_data.tsv",
}


def backup_path(user_dir, name):
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    root = os.path.join(user_dir, "_backup", f"moguang_{stamp}")
    return root, os.path.join(root, name.replace("/", "_").replace("\\", "_"))


def backup_file(user_dir, rel):
    src = os.path.join(user_dir, rel)
    if not os.path.exists(src):
        return None
    root, dst = backup_path(user_dir, rel)
    os.makedirs(root, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def load_default_custom(user_dir):
    path = os.path.join(user_dir, "default.custom.yaml")
    if not os.path.exists(path):
        return path, {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"{path} is not a YAML map; refusing to edit")
    return path, data


def schema_entries(data):
    patch = data.get("patch")
    if patch is None:
        patch = {}
        data["patch"] = patch
    if not isinstance(patch, dict):
        raise SystemExit("patch: is not a YAML map; refusing to edit")
    # 两种合法写法：
    #   patch/schema_list:   完整列表（用户已自定义过，直接追加）
    #   patch/schema_list/+: 追加到 default.yaml 的列表（用户没自定义过时最安全）
    if isinstance(patch.get("schema_list"), list):
        return patch["schema_list"], "schema_list"
    if isinstance(patch.get("schema_list/+"), list):
        return patch["schema_list/+"], "schema_list/+"
    return None, None


def ensure_schema_entry(data):
    """Return (entries, key, changed)."""
    entries, key = schema_entries(data)
    if entries is not None:
        if has_schema(entries):
            return entries, key, False
        entries.append({"schema": SCHEMA_ID})
        return entries, key, True
    # 没有自定义过 schema_list：用 /+ 追加，保留 default.yaml 里的全部方案
    patch = data["patch"]
    patch["schema_list/+"] = [{"schema": SCHEMA_ID}]
    return patch["schema_list/+"], "schema_list/+", True


def has_schema(entries):
    for item in entries:
        if isinstance(item, dict) and item.get("schema") == SCHEMA_ID:
            return True
        if item == SCHEMA_ID:
            return True
    return False


def write_yaml(path, data, dry_run):
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                          default_flow_style=False)
    if dry_run:
        print(f"[dry-run] would write {path}:\n{text}")
        return
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def install(user_dir, dry_run):
    os.makedirs(user_dir, exist_ok=True)

    for src_rel, dst_rel in FILES:
        src = os.path.join(HERE, src_rel)
        dst = os.path.join(user_dir, dst_rel)
        if not os.path.exists(src):
            print(f"[skip] source missing: {src}")
            continue
        if os.path.exists(dst) and dst_rel in KEEP_IF_EXISTS:
            print(f"[keep] {dst} exists (not overwritten)")
            continue
        os.makedirs(os.path.dirname(dst) or user_dir, exist_ok=True)
        if os.path.exists(dst):
            if dry_run:
                print(f"[dry-run] would back up {dst}")
            else:
                bak = backup_file(user_dir, dst_rel)
                print(f"[backup] {dst} -> {bak}")
        if dry_run:
            print(f"[dry-run] would copy {src} -> {dst}")
        else:
            shutil.copy2(src, dst)
            print(f"[copy] {src} -> {dst}")

    path, data = load_default_custom(user_dir)
    entries, key, changed = ensure_schema_entry(data)
    if not changed:
        print(f"[ok] {SCHEMA_ID} already in {path} ({key})")
        return 0
    bak = None
    if not dry_run:
        bak = backup_file(user_dir, "default.custom.yaml")
        if bak:
            print(f"[backup] default.custom.yaml -> {bak}")
    write_yaml(path, data, dry_run)
    print(f"[patch] appended {SCHEMA_ID} via {key} in {path}")
    return 0


def uninstall(user_dir, dry_run, purge):
    path, data = load_default_custom(user_dir)
    changed = False
    patch = data.get("patch") if isinstance(data, dict) else None
    if isinstance(patch, dict):
        for key in ("schema_list", "schema_list/+"):
            entries = patch.get(key)
            if not isinstance(entries, list):
                continue
            kept = [e for e in entries
                    if not ((isinstance(e, dict) and e.get("schema") == SCHEMA_ID)
                            or e == SCHEMA_ID)]
            if len(kept) != len(entries):
                if kept:
                    patch[key] = kept
                else:
                    del patch[key]
                changed = True
    if changed:
        if dry_run:
            print(f"[dry-run] would back up default.custom.yaml")
        else:
            bak = backup_file(user_dir, "default.custom.yaml")
            if bak:
                print(f"[backup] default.custom.yaml -> {bak}")
        write_yaml(path, data, dry_run)
        print(f"[patch] removed {SCHEMA_ID} from {path}")
    else:
        print(f"[ok] {SCHEMA_ID} not present in {path}")

    remove = ["ff7-ime.schema.yaml", "ff7-ime.custom.yaml"]
    if purge:
        remove += [os.path.join("lua", "ff7-ime.lua"),
                   "ff7-ime_data.tsv"]
    # 部署生成的 build/<schema_id>.schema.yaml 不会因为从 schema_list 移除而
    # 自动删除；不删的话 RimeSelectSchema 仍能选中旧方案，回滚不彻底。
    build_dir = os.path.join(user_dir, "build")
    if os.path.isdir(build_dir):
        for name in os.listdir(build_dir):
            if name.startswith(SCHEMA_ID + "."):
                remove.append(os.path.join("build", name))
    for rel in remove:
        src = os.path.join(user_dir, rel)
        if not os.path.exists(src):
            continue
        if dry_run:
            print(f"[dry-run] would remove {src}")
        else:
            bak = backup_file(user_dir, rel)
            os.remove(src)
            print(f"[remove] {src} (backup {bak})")
    print("[note] 运行 WeaselDeployer.exe /deploy 让 schema_list 变更生效；"
          "本脚本已删除 build/ 下该方案的编译产物")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--purge", action="store_true",
                    help="with --uninstall, also remove lua/data files")
    args = ap.parse_args()
    user_dir = os.path.abspath(args.user_dir)
    if args.uninstall:
        return uninstall(user_dir, args.dry_run, args.purge)
    return install(user_dir, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
