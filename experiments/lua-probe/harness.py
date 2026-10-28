#!/usr/bin/env python3
"""
魔光键影 / librime-lua 探针 harness。

用 Python ctypes 直接调用 weasel 0.17.4 自带的 rime.dll (1.13.1)：
  1. 在一个完全隔离的临时用户目录里部署最小 schema（不碰 %APPDATA%\\Rime）
  2. 创建 session，真实发送按键 / RimeSetInput
  3. 读取 RimeContext 菜单，打印候选与 comment
  4. 从 Glog 日志中提取 Lua 探针输出

运行：
    python harness.py
输出：
    控制台完整记录 + 本目录 logs/harness_console.txt + logs/rime_*.log
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
PROJECT = Path(__file__).resolve().parent
RIME_ROOT = Path(r"C:\Program Files\Rime\weasel-0.17.4")
RIME_DLL = RIME_ROOT / "rime.dll"
SHARED_DATA = RIME_ROOT / "data"

TEMP_ROOT = Path(tempfile.gettempdir()) / "mgjy-lua-probe"
USER_DATA = TEMP_ROOT / "user"
LOG_DIR = TEMP_ROOT / "logs"
PROJECT_LOGS = PROJECT / "logs"

# --------------------------------------------------------------------------
# ctypes 结构体（严格对应 librime 1.13.1 src/rime_api.h）
# --------------------------------------------------------------------------
c_int = ctypes.c_int
c_char_p = ctypes.c_char_p
c_size_t = ctypes.c_size_t
c_void_p = ctypes.c_void_p


class RimeTraits(ctypes.Structure):
    _fields_ = [
        ("data_size", c_int),
        ("shared_data_dir", c_char_p),
        ("user_data_dir", c_char_p),
        ("distribution_name", c_char_p),
        ("distribution_code_name", c_char_p),
        ("distribution_version", c_char_p),
        ("app_name", c_char_p),
        ("modules", ctypes.POINTER(c_char_p)),
        ("min_log_level", c_int),
        ("log_dir", c_char_p),
        ("prebuilt_data_dir", c_char_p),
        ("staging_dir", c_char_p),
    ]


class RimeComposition(ctypes.Structure):
    _fields_ = [
        ("length", c_int),
        ("cursor_pos", c_int),
        ("sel_start", c_int),
        ("sel_end", c_int),
        ("preedit", c_char_p),
    ]


class RimeCandidate(ctypes.Structure):
    _fields_ = [
        ("text", c_char_p),
        ("comment", c_char_p),
        ("reserved", c_void_p),
    ]


class RimeMenu(ctypes.Structure):
    _fields_ = [
        ("page_size", c_int),
        ("page_no", c_int),
        ("is_last_page", c_int),
        ("highlighted_candidate_index", c_int),
        ("num_candidates", c_int),
        ("candidates", ctypes.POINTER(RimeCandidate)),
        ("select_keys", c_char_p),
    ]


class RimeContext(ctypes.Structure):
    _fields_ = [
        ("data_size", c_int),
        ("composition", RimeComposition),
        ("menu", RimeMenu),
        ("commit_text_preview", c_char_p),
        ("select_labels", ctypes.POINTER(c_char_p)),
    ]


class RimeCommit(ctypes.Structure):
    _fields_ = [
        ("data_size", c_int),
        ("text", c_char_p),
    ]


class RimeStatus(ctypes.Structure):
    _fields_ = [
        ("data_size", c_int),
        ("schema_id", c_char_p),
        ("schema_name", c_char_p),
        ("is_disabled", c_int),
        ("is_composing", c_int),
        ("is_ascii_mode", c_int),
        ("is_full_shape", c_int),
        ("is_simplified", c_int),
        ("is_traditional", c_int),
        ("is_ascii_punct", c_int),
    ]


def struct_init(obj):
    """RIME_STRUCT_INIT: data_size = sizeof(Type) - sizeof(data_size)"""
    obj.data_size = ctypes.sizeof(obj) - ctypes.sizeof(c_int)
    return obj


def _s(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


# --------------------------------------------------------------------------
# 加载 DLL 并声明 API
# --------------------------------------------------------------------------
def load_rime():
    if not RIME_DLL.exists():
        raise SystemExit(f"rime.dll not found: {RIME_DLL}")

    lib = ctypes.CDLL(str(RIME_DLL))

    signatures = {
        "RimeInitialize": (None, [ctypes.POINTER(RimeTraits)]),
        "RimeSetup": (None, [ctypes.POINTER(RimeTraits)]),
        "RimeFinalize": (None, []),
        "RimeStartMaintenance": (c_int, [c_int]),
        "RimeJoinMaintenanceThread": (None, []),
        "RimeIsMaintenancing": (c_int, []),
        "RimeCreateSession": (c_size_t, []),
        "RimeDestroySession": (c_int, [c_size_t]),
        "RimeSelectSchema": (c_int, [c_size_t, c_char_p]),
        "RimeSelectCandidateOnCurrentPage": (c_int, [c_size_t, c_size_t]),
        "RimeCommitComposition": (c_int, [c_size_t]),
        "RimeGetCurrentSchema": (c_int, [c_size_t, c_char_p, c_size_t]),
        "RimeProcessKey": (c_int, [c_size_t, c_int, c_int]),
        "RimeSetInput": (c_int, [c_size_t, c_char_p]),
        "RimeClearComposition": (None, [c_size_t]),
        "RimeGetContext": (c_int, [c_size_t, ctypes.POINTER(RimeContext)]),
        "RimeFreeContext": (c_int, [ctypes.POINTER(RimeContext)]),
        "RimeGetCommit": (c_int, [c_size_t, ctypes.POINTER(RimeCommit)]),
        "RimeFreeCommit": (c_int, [ctypes.POINTER(RimeCommit)]),
        "RimeGetStatus": (c_int, [c_size_t, ctypes.POINTER(RimeStatus)]),
        "RimeFreeStatus": (c_int, [ctypes.POINTER(RimeStatus)]),
        "RimeGetOption": (c_int, [c_size_t, c_char_p]),
        "RimeSetOption": (None, [c_size_t, c_char_p, c_int]),
        "RimeGetSharedDataDir": (c_char_p, []),
        "RimeGetUserDataDir": (c_char_p, []),
        "RimeGetVersion": (c_char_p, []),
    }
    for name, (restype, argtypes) in signatures.items():
        fn = getattr(lib, name, None)
        if fn is None:
            if name == "RimeGetVersion":
                continue
            raise SystemExit(f"missing export: {name}")
        fn.restype = restype
        fn.argtypes = argtypes
    return lib


# --------------------------------------------------------------------------
# 部署
# --------------------------------------------------------------------------
DEFAULT_CUSTOM = """\
patch:
  schema_list:
    - schema: mgjy_probe
    - schema: mgjy_probe_strict
    - schema: mgjy_probe_global
"""


def deploy_assets():
    if TEMP_ROOT.exists():
        shutil.rmtree(TEMP_ROOT)
    USER_DATA.mkdir(parents=True)
    LOG_DIR.mkdir(parents=True)

    # 部署时文件名必须是 <schema_id>.schema.yaml
    shutil.copy2(PROJECT / "minimal.schema.yaml", USER_DATA / "mgjy_probe.schema.yaml")
    shutil.copy2(PROJECT / "strict.schema.yaml", USER_DATA / "mgjy_probe_strict.schema.yaml")
    shutil.copy2(PROJECT / "global.schema.yaml", USER_DATA / "mgjy_probe_global.schema.yaml")
    shutil.copy2(PROJECT / "rime.lua", USER_DATA / "rime.lua")
    shutil.copytree(PROJECT / "lua", USER_DATA / "lua")
    (USER_DATA / "default.custom.yaml").write_text(DEFAULT_CUSTOM, encoding="utf-8")
    (USER_DATA / "probe_data.txt").write_text(
        "MGJY-IO-OK\t读到了外部 TSV 文件\n", encoding="utf-8"
    )
    # 给 deployer 一个稳定的 installation id
    (USER_DATA / "installation.yaml").write_text(
        "distribution_code_name: mgjy-lua-probe\n"
        "distribution_name: MGJY Lua Probe\n"
        "distribution_version: '0.1.0'\n"
        "install_time: '2026-10-28T00:00:00+08:00'\n"
        "installation_id: mgjy-lua-probe\n"
        "rime_version: 1.13.1\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# 会话封装
# --------------------------------------------------------------------------
class Rime:
    def __init__(self, lib):
        self.lib = lib
        self.session = None
        self._keep = []

    # -- lifecycle ------------------------------------------------------
    def initialize(self):
        traits = RimeTraits()
        struct_init(traits)

        def keep(s):
            b = str(s).encode("utf-8")
            self._keep.append(b)
            return b

        traits.shared_data_dir = keep(SHARED_DATA)
        traits.user_data_dir = keep(USER_DATA)
        traits.distribution_name = keep("MGJY Lua Probe")
        traits.distribution_code_name = keep("mgjy-lua-probe")
        traits.distribution_version = keep("0.1.0")
        traits.app_name = keep("rime.mgjyprobe")
        traits.modules = None
        traits.min_log_level = 0
        traits.log_dir = keep(LOG_DIR)
        traits.prebuilt_data_dir = None
        traits.staging_dir = keep(USER_DATA / "build")

        self.lib.RimeSetup(ctypes.byref(traits))
        print("[api] RimeSetup done (loads logging config incl. log_dir)")
        self.lib.RimeInitialize(ctypes.byref(traits))
        print(f"[api] RimeInitialize done; dll={RIME_DLL}")
        print(f"[api] shared_data_dir={_s(self.lib.RimeGetSharedDataDir())}")
        print(f"[api] user_data_dir={_s(self.lib.RimeGetUserDataDir())}")

        started = bool(self.lib.RimeStartMaintenance(1))
        print(f"[api] RimeStartMaintenance(full_check=1) -> {started}")
        self.lib.RimeJoinMaintenanceThread()
        print(f"[api] RimeJoinMaintenanceThread done; is_maintenancing="
              f"{bool(self.lib.RimeIsMaintenancing())}")

    def create_session(self):
        sid = self.lib.RimeCreateSession()
        if not sid:
            raise SystemExit("RimeCreateSession failed")
        self.session = sid
        print(f"[api] session=0x{sid:x}")
        return sid

    def select_schema(self, schema_id: str) -> bool:
        ok = bool(self.lib.RimeSelectSchema(self.session, schema_id.encode()))
        buf = ctypes.create_string_buffer(256)
        self.lib.RimeGetCurrentSchema(self.session, buf, len(buf))
        print(f"[api] RimeSelectSchema({schema_id}) -> {ok}; current={buf.value.decode('utf-8', 'replace')}")
        return ok

    def destroy(self):
        if self.session:
            self.lib.RimeDestroySession(self.session)
            self.session = None
        self.lib.RimeFinalize()
        print("[api] RimeFinalize done")

    # -- input ----------------------------------------------------------
    def key(self, code: int, mask: int = 0, label: str | None = None) -> bool:
        ok = bool(self.lib.RimeProcessKey(self.session, code, mask))
        print(f"[key] keycode=0x{code:04x} mask={mask} -> {ok}"
              + (f"  ({label})" if label else ""))
        return ok

    def keys(self, text: str, mask: int = 0):
        for ch in text:
            self.key(ord(ch), mask, repr(ch))

    def set_input(self, text: str) -> bool:
        self.lib.RimeClearComposition(self.session)
        ok = bool(self.lib.RimeSetInput(self.session, text.encode("utf-8")))
        print(f"[input] RimeSetInput({text!r}) -> {ok}")
        return ok

    def clear(self):
        self.lib.RimeClearComposition(self.session)
        print("[input] RimeClearComposition")

    def option(self, name: str) -> bool:
        return bool(self.lib.RimeGetOption(self.session, name.encode()))

    def set_option(self, name: str, value: bool):
        self.lib.RimeSetOption(self.session, name.encode(), int(value))
        print(f"[option] RimeSetOption({name}={value}); now={self.option(name)}")

    def select_candidate_on_page(self, index: int):
        ok = bool(self.lib.RimeSelectCandidateOnCurrentPage(self.session, index))
        print(f"[select] RimeSelectCandidateOnCurrentPage({index}) -> {ok}")
        return ok

    # -- output ---------------------------------------------------------
    def context(self, label: str = "") -> dict:
        ctx = struct_init(RimeContext())
        if not self.lib.RimeGetContext(self.session, ctypes.byref(ctx)):
            print(f"[ctx] {label}: RimeGetContext FAILED")
            return {}
        try:
            comp = ctx.composition
            menu = ctx.menu
            data = {
                "preedit": _s(comp.preedit),
                "cursor_pos": comp.cursor_pos,
                "sel_start": comp.sel_start,
                "sel_end": comp.sel_end,
                "page_size": menu.page_size,
                "page_no": menu.page_no,
                "is_last_page": bool(menu.is_last_page),
                "highlighted": menu.highlighted_candidate_index,
                "num_candidates": menu.num_candidates,
                "commit_preview": _s(ctx.commit_text_preview),
                "candidates": [],
            }
            for i in range(menu.num_candidates):
                c = menu.candidates[i]
                data["candidates"].append(
                    {
                        "index": menu.page_no * menu.page_size + i,
                        "text": _s(c.text),
                        "comment": _s(c.comment),
                    }
                )
            print(f"===== CONTEXT {label} =====")
            print(f"  preedit={data['preedit']!r} cursor={data['cursor_pos']} "
                  f"sel=[{data['sel_start']},{data['sel_end']})")
            print(f"  page={data['page_no']} page_size={data['page_size']} "
                  f"last={data['is_last_page']} num={data['num_candidates']} "
                  f"highlighted={data['highlighted']}")
            print(f"  commit_preview={data['commit_preview']!r}")
            for c in data["candidates"]:
                print(f"    [{c['index']:02d}] text={c['text']!r} comment={c['comment']!r}")
            return data
        finally:
            self.lib.RimeFreeContext(ctypes.byref(ctx))

    def status(self) -> dict:
        st = struct_init(RimeStatus())
        if not self.lib.RimeGetStatus(self.session, ctypes.byref(st)):
            return {}
        try:
            data = {
                "schema_id": _s(st.schema_id),
                "schema_name": _s(st.schema_name),
                "is_composing": bool(st.is_composing),
                "is_ascii_mode": bool(st.is_ascii_mode),
                "is_ascii_punct": bool(st.is_ascii_punct),
            }
            print(f"[status] {data}")
            return data
        finally:
            self.lib.RimeFreeStatus(ctypes.byref(st))

    def commit(self) -> str | None:
        cm = struct_init(RimeCommit())
        if not self.lib.RimeGetCommit(self.session, ctypes.byref(cm)):
            print("[commit] no commit text")
            return None
        try:
            text = _s(cm.text)
            print(f"[commit] {text!r}")
            return text
        finally:
            self.lib.RimeFreeCommit(ctypes.byref(cm))


# --------------------------------------------------------------------------
# 场景
# --------------------------------------------------------------------------
def scenario_main(r: Rime, result: dict):
    print("\n########## scenario: mgjy_probe / lkcc key typing ##########")
    r.status()
    r.keys("lkcc")
    result["lkcc_page0"] = r.context("lkcc after typing (page 0)")

    print("\n----- page down -----")
    r.key(0xFF56, 0, "Page_Down")
    result["lkcc_page1"] = r.context("lkcc page 1")
    r.key(0xFF56, 0, "Page_Down")
    result["lkcc_page2"] = r.context("lkcc page 2")

    print("\n----- commit selected candidate (Return) -----")
    r.key(0xFF0D, 0, "Return")
    result["lkcc_return_commit"] = r.commit()

    print("\n----- select first lkcc candidate -----")
    r.clear()
    r.keys("lkcc")
    r.context("lkcc before selecting first candidate")
    r.select_candidate_on_page(0)
    result["lkcc_select_commit"] = r.commit()

    print("\n########## scenario: nihao ##########")
    r.clear()
    r.keys("nihao")
    result["nihao_page0"] = r.context("nihao (page 0)")
    r.select_candidate_on_page(0)
    result["nihao_commit"] = r.commit()

    print("\n########## scenario: switch mgjy_probe_extra ##########")
    r.clear()
    print(f"[option] mgjy_probe_extra before = {r.option('mgjy_probe_extra')}")
    r.set_option("mgjy_probe_extra", True)
    r.keys("lkcc")
    result["extra_on"] = r.context("lkcc with mgjy_probe_extra=ON (page 0)")
    r.set_option("mgjy_probe_extra", False)
    r.clear()
    r.keys("lkcc")
    result["extra_off"] = r.context("lkcc with mgjy_probe_extra=OFF (page 0)")

    print("\n########## scenario: boundary strings via RimeSetInput ##########")
    for s in ["niHao123", "ni hao", "ni'hao", "ni,hao", "NIHAO", "!!", "a-b"]:
        r.set_input(s)
        result[f"setinput:{s}"] = r.context(f"RimeSetInput({s!r})")
        # 清掉这个 composition，避免下一个 SetInput 叠加
        r.clear()


def scenario_strict(r: Rime, result: dict):
    print("\n########## scenario: strict alphabet ##########")
    r.select_schema("mgjy_probe_strict")
    r.status()
    r.clear()
    print("-- lowercase ab --")
    r.keys("ab")
    result["strict_ab"] = r.context("strict: ab")

    r.clear()
    print("-- uppercase AB (alphabet has no uppercase) --")
    for ch in "AB":
        r.key(ord(ch), 0, repr(ch))
    result["strict_AB_keycode"] = r.context("strict: A B as keycodes")

    r.clear()
    print("-- uppercase AB via Shift mask --")
    for ch in "ab":
        r.key(ord(ch), 1, "Shift+" + ch)
    result["strict_AB_shift"] = r.context("strict: Shift+a Shift+b")

    r.clear()
    print("-- digits 123 (alphabet has no digits) --")
    r.keys("123")
    result["strict_123"] = r.context("strict: 1 2 3")

    r.select_schema("mgjy_probe")


def scenario_global(r: Rime, result: dict):
    print("\n########## scenario: lua_translator@mgjy_global (no star) ##########")
    r.select_schema("mgjy_probe_global")
    r.status()
    r.clear()
    r.keys("lkcc")
    result["global_lkcc"] = r.context("global schema lkcc")
    r.select_candidate_on_page(0)
    result["global_commit"] = r.commit()
    r.select_schema("mgjy_probe")


# --------------------------------------------------------------------------
# 日志收集
# --------------------------------------------------------------------------
def collect_logs():
    PROJECT_LOGS.mkdir(exist_ok=True)
    found = sorted(LOG_DIR.glob("*")) if LOG_DIR.exists() else []
    print(f"\n[logs] temp log dir: {LOG_DIR}")
    for p in found:
        print(f"[logs]   {p.name} ({p.stat().st_size} bytes)")
    # 合并所有 rime/glog 日志到项目目录
    combined = []
    for p in found:
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        combined.append(f"===== {p.name} =====\n{text}\n")
    if combined:
        (PROJECT_LOGS / "rime_log.txt").write_text("\n".join(combined), encoding="utf-8")
    # 只摘出 Lua 探针行
    lua_lines = []
    for block in combined:
        for line in block.splitlines():
            if "[mgjy_" in line:
                lua_lines.append(line)
    (PROJECT_LOGS / "lua_probe_log.txt").write_text("\n".join(lua_lines), encoding="utf-8")
    print(f"[logs] lua probe lines: {len(lua_lines)}")
    return lua_lines


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> int:
    print("=" * 78)
    print("MGJY librime-lua probe harness")
    print(f"python={sys.version}")
    print(f"project={PROJECT}")
    print(f"rime_dll={RIME_DLL}")
    print(f"temp_user={USER_DATA}")
    print("=" * 78)

    deploy_assets()
    lib = load_rime()
    r = Rime(lib)

    result = {}
    try:
        r.initialize()
        r.create_session()
        if not r.select_schema("mgjy_probe"):
            raise SystemExit("RimeSelectSchema(mgjy_probe) failed")
        scenario_main(r, result)
        scenario_strict(r, result)
        scenario_global(r, result)
    finally:
        try:
            r.destroy()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] finalize error: {exc}")

    lua_lines = collect_logs()
    result["lua_log_lines"] = lua_lines
    (PROJECT_LOGS / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[done] wrote {PROJECT_LOGS / 'result.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
