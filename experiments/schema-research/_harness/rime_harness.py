#!/usr/bin/env python3
"""Minimal librime harness for testing a Rime schema in an isolated user dir.

Uses the real rime.dll shipped with Weasel 0.17.4 (librime 1.13.1) via its
C API. It never touches %APPDATA%\\Rime or the install directory's data.

Usage:
  python rime_harness.py deploy --user-dir DIR [--shared-dir DIR]
  python rime_harness.py type --user-dir DIR --schema ID --keys lkcc [--keys ...]
"""
import argparse
import ctypes
import os
import sys
from ctypes import POINTER, Structure, c_char_p, c_int, c_uint64, c_void_p

RIME_DLL = r"C:\Program Files\Rime\weasel-0.17.4\rime.dll"
SHARED_DEFAULT = r"C:\Program Files\Rime\weasel-0.17.4\data"


class RimeTraits(Structure):
    _fields_ = [
        ("data_size", c_int),
        ("shared_data_dir", c_char_p),
        ("user_data_dir", c_char_p),
        ("distribution_name", c_char_p),
        ("distribution_code_name", c_char_p),
        ("distribution_version", c_char_p),
        ("app_name", c_char_p),
        ("modules", POINTER(c_char_p)),
        ("min_log_level", c_int),
        ("log_dir", c_char_p),
        ("prebuilt_data_dir", c_char_p),
        ("staging_dir", c_char_p),
    ]


class RimeComposition(Structure):
    _fields_ = [
        ("length", c_int),
        ("cursor_pos", c_int),
        ("sel_start", c_int),
        ("sel_end", c_int),
        ("preedit", c_char_p),
    ]


class RimeCandidate(Structure):
    _fields_ = [
        ("text", c_char_p),
        ("comment", c_char_p),
        ("reserved", c_void_p),
    ]


class RimeMenu(Structure):
    _fields_ = [
        ("page_size", c_int),
        ("page_no", c_int),
        ("is_last_page", c_int),
        ("highlighted_candidate_index", c_int),
        ("num_candidates", c_int),
        ("candidates", POINTER(RimeCandidate)),
        ("select_keys", c_char_p),
    ]


class RimeContext(Structure):
    _fields_ = [
        ("data_size", c_int),
        ("composition", RimeComposition),
        ("menu", RimeMenu),
        ("commit_text_preview", c_char_p),
        ("select_labels", POINTER(c_char_p)),
    ]


class RimeCommit(Structure):
    _fields_ = [
        ("data_size", c_int),
        ("text", c_char_p),
    ]


def _init_struct(struct):
    struct.data_size = ctypes.sizeof(struct) - ctypes.sizeof(c_int)
    return struct


def load_lib():
    os.add_dll_directory(os.path.dirname(RIME_DLL))
    lib = ctypes.CDLL(RIME_DLL)

    lib.RimeSetup.argtypes = [POINTER(RimeTraits)]
    lib.RimeSetup.restype = None
    lib.RimeInitialize.argtypes = [POINTER(RimeTraits)]
    lib.RimeInitialize.restype = c_int
    lib.RimeFinalize.argtypes = []
    lib.RimeFinalize.restype = None
    lib.RimeStartMaintenance.argtypes = [c_int]
    lib.RimeStartMaintenance.restype = c_int
    lib.RimeJoinMaintenanceThread.argtypes = []
    lib.RimeJoinMaintenanceThread.restype = None
    lib.RimeCreateSession.argtypes = []
    lib.RimeCreateSession.restype = c_uint64
    lib.RimeDestroySession.argtypes = [c_uint64]
    lib.RimeDestroySession.restype = c_int
    lib.RimeCleanupAllSessions.argtypes = []
    lib.RimeCleanupAllSessions.restype = None
    lib.RimeSelectSchema.argtypes = [c_uint64, c_char_p]
    lib.RimeSelectSchema.restype = c_int
    lib.RimeSimulateKeySequence.argtypes = [c_uint64, c_char_p]
    lib.RimeSimulateKeySequence.restype = c_int
    lib.RimeGetContext.argtypes = [c_uint64, POINTER(RimeContext)]
    lib.RimeGetContext.restype = c_int
    lib.RimeFreeContext.argtypes = [POINTER(RimeContext)]
    lib.RimeFreeContext.restype = None
    lib.RimeGetCommit.argtypes = [c_uint64, POINTER(RimeCommit)]
    lib.RimeGetCommit.restype = c_int
    lib.RimeFreeCommit.argtypes = [POINTER(RimeCommit)]
    lib.RimeFreeCommit.restype = None
    lib.RimeGetOption.argtypes = [c_uint64, c_char_p]
    lib.RimeGetOption.restype = c_int
    lib.RimeSetOption.argtypes = [c_uint64, c_char_p, c_int]
    lib.RimeSetOption.restype = None
    return lib


def make_traits(user_dir, shared_dir, log_dir):
    traits = RimeTraits()
    traits.shared_data_dir = os.fsencode(shared_dir)
    traits.user_data_dir = os.fsencode(user_dir)
    traits.distribution_name = "小狼毫".encode("utf-8")
    traits.distribution_code_name = b"Weasel"
    traits.distribution_version = b"0.17.4"
    traits.app_name = b"rime.harness"
    traits.min_log_level = 0
    traits.log_dir = os.fsencode(log_dir)
    traits.prebuilt_data_dir = os.fsencode(shared_dir)
    return _init_struct(traits)


def setup(user_dir, shared_dir, log_dir):
    lib = load_lib()
    traits = make_traits(user_dir, shared_dir, log_dir)
    lib.RimeSetup(ctypes.byref(traits))
    if not lib.RimeInitialize(ctypes.byref(traits)):
        raise SystemExit("RimeInitialize failed")
    return lib, traits


def deploy(user_dir, shared_dir, log_dir):
    lib, traits = setup(user_dir, shared_dir, log_dir)
    started = lib.RimeStartMaintenance(1)
    print(f"RimeStartMaintenance(full_check=1) -> {started}")
    if started:
        lib.RimeJoinMaintenanceThread()
    # After maintenance, re-initialize is not needed for this process; sessions
    # created below see the freshly built workspace.
    lib.RimeFinalize()
    print("deploy finished")


def dump_context(lib, session, label=""):
    ctx = _init_struct(RimeContext())
    if not lib.RimeGetContext(session, ctypes.byref(ctx)):
        print(f"{label} GetContext failed")
        return None
    preedit = ctx.composition.preedit.decode("utf-8", "replace") if ctx.composition.preedit else ""
    print(f"{label} preedit={preedit!r} len={ctx.composition.length} "
          f"menu_candidates={ctx.menu.num_candidates} page_size={ctx.menu.page_size}")
    out = []
    for i in range(ctx.menu.num_candidates):
        cand = ctx.menu.candidates[i]
        text = cand.text.decode("utf-8", "replace") if cand.text else ""
        comment = cand.comment.decode("utf-8", "replace") if cand.comment else ""
        out.append((text, comment))
        print(f"  [{i}] {text!r}  comment={comment!r}")
    lib.RimeFreeContext(ctypes.byref(ctx))
    return {"preedit": preedit, "candidates": out}


def run_typing(user_dir, shared_dir, log_dir, schema_id, key_sequences, options=None,
               get_options=None):
    lib, traits = setup(user_dir, shared_dir, log_dir)
    started = lib.RimeStartMaintenance(0)
    if started:
        lib.RimeJoinMaintenanceThread()

    session = lib.RimeCreateSession()
    if not session:
        raise SystemExit("RimeCreateSession failed")
    ok = lib.RimeSelectSchema(session, schema_id.encode())
    print(f"RimeSelectSchema({schema_id}) -> {ok}")
    if not ok:
        lib.RimeDestroySession(session)
        lib.RimeFinalize()
        raise SystemExit("schema selection failed")

    for name in (get_options or []):
        print(f"option[{name}] = {lib.RimeGetOption(session, name.encode())}")

    for name, value in (options or {}).items():
        lib.RimeSetOption(session, name.encode(), 1 if value else 0)
        print(f"option {name} = {lib.RimeGetOption(session, name.encode())}")

    results = []
    for keys in key_sequences:
        ok = lib.RimeSimulateKeySequence(session, keys.encode())
        print(f"\n== RimeSimulateKeySequence({keys!r}) -> {ok}")
        results.append((keys, dump_context(lib, session, label=f"after {keys!r}")))
        commit = _init_struct(RimeCommit())
        if lib.RimeGetCommit(session, ctypes.byref(commit)):
            text = commit.text.decode("utf-8", "replace") if commit.text else ""
            print(f"  COMMIT: {text!r}")
            lib.RimeFreeCommit(ctypes.byref(commit))

    lib.RimeDestroySession(session)
    lib.RimeCleanupAllSessions()
    lib.RimeFinalize()
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", default=RIME_DLL)
    parser.add_argument("--shared-dir", default=SHARED_DEFAULT)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_deploy = sub.add_parser("deploy")
    p_deploy.add_argument("--user-dir", required=True)
    p_deploy.add_argument("--log-dir", default=None)

    p_type = sub.add_parser("type")
    p_type.add_argument("--user-dir", required=True)
    p_type.add_argument("--log-dir", default=None)
    p_type.add_argument("--schema", required=True)
    p_type.add_argument("--keys", action="append", default=[])
    p_type.add_argument("--option", action="append", default=[],
                        help="name=0|1")
    p_type.add_argument("--get-option", action="append", default=[],
                        help="print the value of this schema option")

    args = parser.parse_args()
    log_dir = args.log_dir or os.path.join(args.user_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    if args.cmd == "deploy":
        deploy(args.user_dir, args.shared_dir, log_dir)
    elif args.cmd == "type":
        options = {}
        for item in args.option:
            name, _, value = item.partition("=")
            options[name] = value.strip() not in ("0", "false", "False", "")
        run_typing(args.user_dir, args.shared_dir, log_dir, args.schema, args.keys, options,
                   get_options=args.get_option)
    return 0


if __name__ == "__main__":
    sys.exit(main())
