#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rime_harness.py -- drive the librime C API from Python on Windows x64.

This is a *test fixture* for Rime schemas: it initializes librime with an
isolated user data directory, optionally deploys schemas, feeds keystrokes to
a session and reports the composition (preedit), the current candidate page,
options/status and the committed text as JSON.

Tested against Weasel 0.17.4 x64 / librime 1.13.1
(C:\\Program Files\\Rime\\weasel-0.17.4\\rime.dll).

Typical use:

    python rime_harness.py \
        --shared "C:\\Program Files\\Rime\\weasel-0.17.4\\data" \
        --user "%TEMP%\\mgjy-test" \
        --schema luna_pinyin_simp \
        --input nihao --select 0 --json

Only the current page of candidates is reported (that is all the C API
exposes through RimeGetContext).  Use --select N to pick from that page,
"{Page_Down}" / "{Page_Up}" in --input to turn pages.

Requirements: Windows x64, Python 3.8+, the Rime DLL.  No third-party
packages.  One RimeHarness per process (librime keeps global state).
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sys
import tempfile
import time

from ctypes import POINTER, byref, c_char_p, c_int, c_size_t, c_void_p

IS_WINDOWS = os.name == "nt"

DEFAULT_DLL = r"C:\Program Files\Rime\weasel-0.17.4\rime.dll"
DEFAULT_SHARED = r"C:\Program Files\Rime\weasel-0.17.4\data"


# ---------------------------------------------------------------------------
# ctypes mirrors of librime 1.13.1 src/rime_api.h
#
# Layout notes (Windows x64, MSVC):
#   Bool is `int` (4 bytes) -- the *non*-stdbool C API exported by rime.dll.
#   All following sizes are asserted at RimeApi construction time.
# ---------------------------------------------------------------------------


class RimeTraits(ctypes.Structure):
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
        ("candidates", POINTER(RimeCandidate)),
        ("select_keys", c_char_p),
    ]


class RimeContext(ctypes.Structure):
    _fields_ = [
        ("data_size", c_int),
        ("composition", RimeComposition),
        ("menu", RimeMenu),
        ("commit_text_preview", c_char_p),
        ("select_labels", POINTER(c_char_p)),
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


class RimeCommit(ctypes.Structure):
    _fields_ = [
        ("data_size", c_int),
        ("text", c_char_p),
    ]


class RimeSchemaListItem(ctypes.Structure):
    _fields_ = [
        ("schema_id", c_char_p),
        ("name", c_char_p),
        ("reserved", c_void_p),
    ]


class RimeSchemaList(ctypes.Structure):
    _fields_ = [
        ("size", c_size_t),
        ("list", POINTER(RimeSchemaListItem)),
    ]


# sizeof() on Windows x64, verified against the DLL.
EXPECTED_SIZES = {
    RimeTraits: 96,
    RimeComposition: 24,
    RimeCandidate: 24,
    RimeMenu: 40,
    RimeContext: 88,
    RimeStatus: 56,
    RimeCommit: 16,
}

# Standard switches worth reporting on every run.
STD_OPTIONS = [
    "ascii_mode",
    "full_shape",
    "ascii_punct",
    "simplification",
    "zh_simp",
    "traditional",
    "extended_charset",
    "emoji",
]

# X11 modifier masks as used by librime's KeyEvent (see key_table.cc).
MODIFIERS = {
    "Shift": 1 << 0,
    "Lock": 1 << 1,
    "Control": 1 << 2,
    "Alt": 1 << 3,
    "Mod2": 1 << 4,
    "Mod3": 1 << 5,
    "Mod4": 1 << 6,
    "Mod5": 1 << 7,
    "Button1": 1 << 8,
    "Button2": 1 << 9,
    "Button3": 1 << 10,
    "Button4": 1 << 11,
    "Button5": 1 << 12,
    "Super": 1 << 26,
    "Hyper": 1 << 27,
    "Meta": 1 << 28,
    "Release": 1 << 30,
}

# Fallback key-name table, used only if the DLL's own C++ helper
# RimeGetKeycodeByName() cannot be resolved through its mangled export name.
# Values are X11 keysyms, exactly what librime expects.
FALLBACK_KEYCODES = {
    "space": 0x0020,
    "exclam": 0x0021,
    "quotedbl": 0x0022,
    "numbersign": 0x0023,
    "dollar": 0x0024,
    "percent": 0x0025,
    "ampersand": 0x0026,
    "apostrophe": 0x0027,
    "parenleft": 0x0028,
    "parenright": 0x0029,
    "asterisk": 0x002A,
    "plus": 0x002B,
    "comma": 0x002C,
    "minus": 0x002D,
    "period": 0x002E,
    "slash": 0x002F,
    "colon": 0x003A,
    "semicolon": 0x003B,
    "less": 0x003C,
    "equal": 0x003D,
    "greater": 0x003E,
    "question": 0x003F,
    "at": 0x0040,
    "bracketleft": 0x005B,
    "backslash": 0x005C,
    "bracketright": 0x005D,
    "asciicircum": 0x005E,
    "underscore": 0x005F,
    "grave": 0x0060,
    "braceleft": 0x007B,
    "bar": 0x007C,
    "braceright": 0x007D,
    "asciitilde": 0x007E,
    "BackSpace": 0xFF08,
    "Tab": 0xFF09,
    "Return": 0xFF0D,
    "Escape": 0xFF1B,
    "Insert": 0xFF63,
    "Delete": 0xFF9F,
    "Home": 0xFF50,
    "Left": 0xFF51,
    "Up": 0xFF52,
    "Right": 0xFF53,
    "Down": 0xFF54,
    "Page_Up": 0xFF55,
    "Page_Down": 0xFF56,
    "End": 0xFF57,
}

XK_VOID_SYMBOL = 0xFFFFFF

NOTIFICATION_CB = ctypes.CFUNCTYPE(
    None, c_void_p, c_size_t, c_char_p, c_char_p
)


class HarnessError(RuntimeError):
    pass


def _data_size(cls):
    """Value RIME_STRUCT_INIT() would assign: sizeof - sizeof(data_size)."""
    return ctypes.sizeof(cls) - ctypes.sizeof(c_int)


def _new_struct(cls):
    obj = cls()
    ctypes.memset(byref(obj), 0, ctypes.sizeof(obj))
    obj.data_size = _data_size(cls)
    return obj


def _s(value):
    """Decode a C string (bytes) as UTF-8, mapping NULL to ''."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class RimeApi:
    """Thin, version-checked binding of the exported legacy C API."""

    def __init__(self, dll_path=DEFAULT_DLL):
        if not IS_WINDOWS:
            raise HarnessError("rime_harness only supports Windows (ctypes.WinDLL)")
        if not os.path.isfile(dll_path):
            raise HarnessError("rime.dll not found: %s" % dll_path)
        self.dll_path = os.path.abspath(dll_path)
        self.dll = ctypes.WinDLL(self.dll_path)
        self._check_struct_sizes()
        self._bind_exports()
        self.notifications = []
        self._notif_cb = NOTIFICATION_CB(self._on_notification)
        self.dll.RimeSetNotificationHandler(self._notif_cb, None)
        self._resolve_key_helpers()

    # -- setup ------------------------------------------------------------

    def _check_struct_sizes(self):
        wrong = []
        for cls, expected in EXPECTED_SIZES.items():
            actual = ctypes.sizeof(cls)
            if actual != expected:
                wrong.append("%s: %d (expected %d)" % (cls.__name__, actual, expected))
        if wrong:
            raise HarnessError(
                "ctypes struct layout mismatch (is Python 64-bit?): " + "; ".join(wrong)
            )

    def _bind_exports(self):
        d = self.dll

        def sig(name, argtypes, restype):
            try:
                fn = getattr(d, name)
            except AttributeError:
                raise HarnessError("rime.dll does not export %s" % name)
            fn.argtypes = argtypes
            fn.restype = restype

        P = POINTER
        sig("RimeSetup", [P(RimeTraits)], None)
        sig("RimeInitialize", [P(RimeTraits)], None)
        sig("RimeFinalize", [], None)
        sig("RimeStartMaintenance", [c_int], c_int)
        sig("RimeJoinMaintenanceThread", [], None)
        sig("RimeIsMaintenancing", [], c_int)
        sig("RimeCreateSession", [], c_size_t)
        sig("RimeDestroySession", [c_size_t], c_int)
        sig("RimeFindSession", [c_size_t], c_int)
        sig("RimeSelectSchema", [c_size_t, c_char_p], c_int)
        sig("RimeGetCurrentSchema", [c_size_t, c_char_p, c_size_t], c_int)
        sig("RimeProcessKey", [c_size_t, c_int, c_int], c_int)
        sig("RimeSimulateKeySequence", [c_size_t, c_char_p], c_int)
        sig("RimeCommitComposition", [c_size_t], c_int)
        sig("RimeClearComposition", [c_size_t], None)
        sig("RimeGetContext", [c_size_t, P(RimeContext)], c_int)
        sig("RimeFreeContext", [P(RimeContext)], c_int)
        sig("RimeGetCommit", [c_size_t, P(RimeCommit)], c_int)
        sig("RimeFreeCommit", [P(RimeCommit)], c_int)
        sig("RimeGetStatus", [c_size_t, P(RimeStatus)], c_int)
        sig("RimeFreeStatus", [P(RimeStatus)], c_int)
        sig("RimeSetOption", [c_size_t, c_char_p, c_int], None)
        sig("RimeGetOption", [c_size_t, c_char_p], c_int)
        sig("RimeSelectCandidate", [c_size_t, c_size_t], c_int)
        sig("RimeSelectCandidateOnCurrentPage", [c_size_t, c_size_t], c_int)
        sig("RimeGetSchemaList", [P(RimeSchemaList)], c_int)
        sig("RimeFreeSchemaList", [P(RimeSchemaList)], None)
        sig("RimeGetSharedDataDir", [], c_char_p)
        sig("RimeGetUserDataDir", [], c_char_p)
        sig("RimeGetPrebuiltDataDir", [], c_char_p)
        sig("RimeGetStagingDir", [], c_char_p)
        sig("RimeSetNotificationHandler", [NOTIFICATION_CB, c_void_p], None)

    def _resolve_key_helpers(self):
        """Optionally bind the C++ helpers used by librime's key parser.

        They are exported with MSVC-mangled names; using them makes
        "{Control+Shift+4}" style specs behave exactly like librime itself.
        """
        self._get_keycode_by_name = None
        self._get_modifier_by_name = None
        for attr, mangled, restype in (
            ("_get_keycode_by_name", "?RimeGetKeycodeByName@@YAHPEBD@Z", c_int),
            ("_get_modifier_by_name", "?RimeGetModifierByName@@YAHPEBD@Z", c_int),
        ):
            try:
                fn = getattr(self.dll, mangled)
            except AttributeError:
                continue
            fn.argtypes = [c_char_p]
            fn.restype = restype
            setattr(self, attr, fn)

    # -- notifications -----------------------------------------------------

    def _on_notification(self, _ctx, session_id, message_type, message_value):
        self.notifications.append(
            {
                "session_id": int(session_id),
                "type": _s(message_type),
                "value": _s(message_value),
            }
        )

    def clear_notifications(self):
        del self.notifications[:]

    def drain_deploy_events(self):
        return [n for n in self.notifications if n["type"] == "deploy"]

    # -- key names ---------------------------------------------------------

    def keycode_by_name(self, name):
        if self._get_keycode_by_name is not None:
            code = self._get_keycode_by_name(name.encode("ascii", "strict"))
            if code != XK_VOID_SYMBOL and code != 0:
                return code
            raise HarnessError("unknown key name %r" % name)
        if name in FALLBACK_KEYCODES:
            return FALLBACK_KEYCODES[name]
        raise HarnessError(
            "unknown key name %r (DLL key helper unavailable, using fallback table)"
            % name
        )

    def modifier_by_name(self, name):
        if self._get_modifier_by_name is not None:
            return int(self._get_modifier_by_name(name.encode("ascii", "strict")))
        return MODIFIERS.get(name, 0)


class RimeHarness:
    """One librime instance with isolated shared/user data directories.

    Usage:
        with RimeHarness(shared, user, schema="luna_pinyin_simp") as h:
            with h.session() as session:
                session.type("nihao")
                print(session.context(), session.commit())
    """

    def __init__(
        self,
        shared_data_dir=DEFAULT_SHARED,
        user_data_dir=None,
        schema=None,
        dll_path=DEFAULT_DLL,
        prebuilt_data_dir=None,
        staging_dir=None,
        log_dir=None,
        min_log_level=2,
        deploy="auto",
        write_custom_config=True,
    ):
        self.shared = os.path.abspath(shared_data_dir)
        if user_data_dir is None:
            user_data_dir = os.path.join(
                tempfile.gettempdir(), "mgjy-rime-harness", "default"
            )
        self.user = os.path.abspath(user_data_dir)
        self.schema = schema
        self.deploy_mode = deploy
        self.min_log_level = int(min_log_level)
        self.prebuilt = os.path.abspath(prebuilt_data_dir) if prebuilt_data_dir else None
        self.staging = os.path.abspath(staging_dir) if staging_dir else None
        self.log_dir = os.path.abspath(log_dir) if log_dir else os.path.join(
            self.user, "logs"
        )
        self.write_custom_config = write_custom_config

        self._validate_paths()
        os.makedirs(self.user, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        self.deployed_this_run = False
        self.deploy_seconds = 0.0
        self.deploy_events = []
        self._sessions = []
        self._closed = False
        self._api = RimeApi(dll_path)
        self._traits = self._build_traits()
        # RimeSetup() applies paths + logging config (RimeInitialize() alone
        # does not call SetupLogging, so without this glog writes to stderr).
        self._api.dll.RimeSetup(byref(self._traits))
        self._api.dll.RimeInitialize(byref(self._traits))
        self._initialized = True

        try:
            if self.write_custom_config and self.schema:
                self._write_default_custom()
            if self.deploy_mode == "always":
                self.deploy()
            elif self.deploy_mode == "auto":
                if self._needs_deploy():
                    self.deploy()
            elif self.deploy_mode != "never":
                raise HarnessError("invalid deploy mode %r" % self.deploy_mode)
            self._verify_build()
        except Exception:
            self.close()
            raise

    # -- paths and traits --------------------------------------------------

    def _validate_paths(self):
        if not os.path.isdir(self.shared):
            raise HarnessError("shared_data_dir not found: %s" % self.shared)
        if not os.path.isfile(os.path.join(self.shared, "default.yaml")):
            raise HarnessError(
                "shared_data_dir does not look like Rime data (missing default.yaml): %s"
                % self.shared
            )

    def _build_traits(self):
        traits = _new_struct(RimeTraits)
        traits.shared_data_dir = self.shared.encode("utf-8")
        traits.user_data_dir = self.user.encode("utf-8")
        traits.distribution_name = b"Rime"
        traits.distribution_code_name = b"weasel"
        traits.distribution_version = b"0.17.4"
        traits.app_name = b"rime.mgjy_harness"
        traits.min_log_level = self.min_log_level
        traits.log_dir = self.log_dir.encode("utf-8")
        if self.prebuilt:
            traits.prebuilt_data_dir = self.prebuilt.encode("utf-8")
        if self.staging:
            traits.staging_dir = self.staging.encode("utf-8")
        return traits

    @property
    def build_dir(self):
        return self.staging or os.path.join(self.user, "build")

    @property
    def state_file(self):
        return os.path.join(self.user, ".rime_harness_state.json")

    def _write_default_custom(self):
        path = os.path.join(self.user, "default.custom.yaml")
        content = (
            "# generated by experiments/rime-harness/rime_harness.py\n"
            "patch:\n"
            "  schema_list:\n"
            "    - schema: %s\n" % self.schema
        )
        try:
            with open(path, "r", encoding="utf-8") as f:
                if f.read() == content:
                    return
        except OSError:
            pass
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    # -- deployment --------------------------------------------------------

    def _path_signature(self):
        """Cheap fingerprint of the YAML sources that affect deployment."""
        h = hashlib.sha256()
        for label, base in (("shared", self.shared), ("user", self.user)):
            for dirpath, dirnames, filenames in os.walk(base):
                rel = os.path.relpath(dirpath, base)
                if label == "user":
                    dirnames[:] = [
                        d
                        for d in dirnames
                        if d not in ("build", "logs") and not d.endswith(".userdb")
                    ]
                dirnames.sort()
                for name in sorted(filenames):
                    if label == "user" and (
                        name in (
                            "installation.yaml",
                            "user.yaml",
                            "userdb.txt",
                            ".rime_harness_state.json",
                        )
                        or name.endswith(".log")
                    ):
                        continue
                    path = os.path.join(dirpath, name)
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    h.update(
                        ("%s/%s/%s\0%d\0%d\n"
                         % (label, rel.replace("\\", "/"), name, st.st_size, st.st_mtime_ns)
                        ).encode("utf-8", "replace")
                    )
        return h.hexdigest()

    def _read_state(self):
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _write_state(self, signature):
        state = {
            "schema": self.schema,
            "shared_data_dir": self.shared,
            "prebuilt_data_dir": self.prebuilt,
            "staging_dir": self.staging,
            "signature": signature,
            "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def _needs_deploy(self):
        if not os.path.isdir(self.build_dir):
            return True
        if not os.path.isfile(os.path.join(self.build_dir, "default.yaml")):
            return True
        state = self._read_state()
        if state.get("schema") != self.schema:
            return True
        if state.get("shared_data_dir") != self.shared:
            return True
        if state.get("prebuilt_data_dir") != self.prebuilt:
            return True
        if state.get("staging_dir") != self.staging:
            return True
        return state.get("signature") != self._path_signature()

    def deploy(self):
        """Run a full maintenance pass and join the maintenance thread."""
        signature_before = self._path_signature()
        self._api.clear_notifications()
        started = time.time()
        ok = self._api.dll.RimeStartMaintenance(1)
        self._api.dll.RimeJoinMaintenanceThread()
        self.deploy_seconds = time.time() - started
        self.deploy_events = self._api.drain_deploy_events()
        self.deployed_this_run = True
        if not ok:
            raise HarnessError(
                "RimeStartMaintenance() failed; see logs in %s" % self.log_dir
            )
        failures = [e for e in self.deploy_events if e["value"] == "failure"]
        if failures:
            detail = ""
            if self.schema:
                expected = os.path.join(
                    self.build_dir, self.schema + ".schema.yaml"
                )
                if not os.path.isfile(expected):
                    detail = "; schema %r was not deployed" % self.schema
            raise HarnessError(
                "deployment reported failure%s; see logs in %s"
                % (detail, self.log_dir)
            )
        self._write_state(signature_before)

    def _verify_build(self):
        if not os.path.isdir(self.build_dir):
            raise HarnessError(
                "deployment artifacts missing (%s). Run with --deploy always, or "
                "omit --deploy never." % self.build_dir
            )
        if self.schema:
            expected = os.path.join(self.build_dir, self.schema + ".schema.yaml")
            if not os.path.isfile(expected):
                available = self.list_schemas()
                raise HarnessError(
                    "schema %r was not deployed (missing %s). Available: %s"
                    % (
                        self.schema,
                        expected,
                        ", ".join(s["schema_id"] for s in available) or "(none)",
                    )
                )

    # -- misc API ----------------------------------------------------------

    def list_schemas(self):
        lst = RimeSchemaList()
        ctypes.memset(byref(lst), 0, ctypes.sizeof(lst))
        if not self._api.dll.RimeGetSchemaList(byref(lst)):
            return []
        out = []
        try:
            for i in range(lst.size):
                item = lst.list[i]
                out.append(
                    {"schema_id": _s(item.schema_id), "name": _s(item.name)}
                )
        finally:
            self._api.dll.RimeFreeSchemaList(byref(lst))
        return out

    # -- sessions ----------------------------------------------------------

    def session(self, schema=None, options=None):
        return RimeSession(self, schema=schema, options=options)

    def _register_session(self, session):
        self._sessions.append(session)

    def _unregister_session(self, session):
        if session in self._sessions:
            self._sessions.remove(session)

    def close(self):
        if self._closed:
            return
        for session in list(self._sessions):
            session.close()
        if getattr(self, "_initialized", False):
            try:
                self._api.dll.RimeFinalize()
            except Exception:
                pass
            self._initialized = False
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class RimeSession:
    """A librime session: schema selection, typing, reading state."""

    def __init__(self, harness, schema=None, options=None):
        self.h = harness
        self.api = harness._api
        self.schema = schema or harness.schema
        self.id = self.api.dll.RimeCreateSession()
        if not self.id:
            raise HarnessError("RimeCreateSession() failed")
        harness._register_session(self)
        self._closed = False
        self._options = {}
        try:
            if self.schema:
                if not self.api.dll.RimeSelectSchema(
                    self.id, self.schema.encode("utf-8")
                ):
                    available = harness.list_schemas()
                    raise HarnessError(
                        "RimeSelectSchema(%r) failed. Deployed schemas: %s"
                        % (
                            self.schema,
                            ", ".join(s["schema_id"] for s in available) or "(none)",
                        )
                    )
            for name, value in (options or {}).items():
                self.set_option(name, value)
        except Exception:
            self.close()
            raise

    # -- options -----------------------------------------------------------

    def set_option(self, name, value):
        self.api.dll.RimeSetOption(self.id, name.encode("utf-8"), 1 if value else 0)
        self._options[name] = bool(value)

    def get_option(self, name):
        return bool(self.api.dll.RimeGetOption(self.id, name.encode("utf-8")))

    def options(self, names=None):
        names = list(names or [])
        for name in STD_OPTIONS + list(self._options):
            if name not in names:
                names.append(name)
        return {name: self.get_option(name) for name in names}

    # -- typing ------------------------------------------------------------

    def process(self, keycode, mask=0):
        return bool(self.api.dll.RimeProcessKey(self.id, int(keycode), int(mask)))

    def type(self, spec, collect_steps=False):
        """Type a key spec: plain ASCII chars plus {Name} tokens.

        Returns (consumed_count, steps).  Each step captures the state *after*
        that key so callers can assert intermediate behaviour.
        """
        keys = parse_key_sequence(spec, self.api)
        steps = []
        consumed = 0
        for label, keycode, mask in keys:
            ok = self.process(keycode, mask)
            if ok:
                consumed += 1
            if collect_steps:
                ctx = self.context()
                steps.append(
                    {
                        "key": label,
                        "keycode": keycode,
                        "mask": mask,
                        "consumed": ok,
                        "preedit": ctx["preedit"],
                        "page": ctx["page"],
                        "candidates": ctx["candidates"],
                    }
                )
        return consumed, steps

    def simulate(self, sequence):
        """Use librime's own key-sequence parser (supports Control+a etc.)."""
        return bool(
            self.api.dll.RimeSimulateKeySequence(
                self.id, sequence.encode("utf-8")
            )
        )

    def commit_composition(self):
        return bool(self.api.dll.RimeCommitComposition(self.id))

    def clear_composition(self):
        self.api.dll.RimeClearComposition(self.id)

    # -- reading -----------------------------------------------------------

    def context(self):
        ctx = _new_struct(RimeContext)
        if not self.api.dll.RimeGetContext(self.id, byref(ctx)):
            return {
                "preedit": "",
                "composition": {
                    "length": 0,
                    "cursor_pos": 0,
                    "sel_start": 0,
                    "sel_end": 0,
                },
                "commit_text_preview": "",
                "commit_text_preview_present": False,
                "page": 0,
                "page_size": 0,
                "page_no": 0,
                "is_last_page": False,
                "highlighted_candidate_index": 0,
                "candidates": [],
                "select_keys": "",
                "select_labels": [],
            }
        try:
            candidates = []
            for i in range(ctx.menu.num_candidates):
                cand = ctx.menu.candidates[i]
                candidates.append(
                    {
                        "index": i,
                        "text": _s(cand.text),
                        "comment": _s(cand.comment),
                    }
                )
            labels = []
            if ctx.select_labels and ctx.menu.page_size:
                for i in range(ctx.menu.page_size):
                    labels.append(_s(ctx.select_labels[i]))
            return {
                "preedit": _s(ctx.composition.preedit),
                "composition": {
                    "length": int(ctx.composition.length),
                    "cursor_pos": int(ctx.composition.cursor_pos),
                    "sel_start": int(ctx.composition.sel_start),
                    "sel_end": int(ctx.composition.sel_end),
                },
                "commit_text_preview": _s(ctx.commit_text_preview),
                "commit_text_preview_present": bool(ctx.commit_text_preview),
                "page": int(ctx.menu.page_no),
                "page_size": int(ctx.menu.page_size),
                "page_no": int(ctx.menu.page_no),
                "is_last_page": bool(ctx.menu.is_last_page),
                "highlighted_candidate_index": int(
                    ctx.menu.highlighted_candidate_index
                ),
                "candidates": candidates,
                "select_keys": _s(ctx.menu.select_keys),
                "select_labels": labels,
            }
        finally:
            self.api.dll.RimeFreeContext(byref(ctx))

    def status(self):
        st = _new_struct(RimeStatus)
        if not self.api.dll.RimeGetStatus(self.id, byref(st)):
            return {}
        try:
            return {
                "schema_id": _s(st.schema_id),
                "schema_name": _s(st.schema_name),
                "is_disabled": bool(st.is_disabled),
                "is_composing": bool(st.is_composing),
                "is_ascii_mode": bool(st.is_ascii_mode),
                "is_full_shape": bool(st.is_full_shape),
                "is_simplified": bool(st.is_simplified),
                "is_traditional": bool(st.is_traditional),
                "is_ascii_punct": bool(st.is_ascii_punct),
            }
        finally:
            self.api.dll.RimeFreeStatus(byref(st))

    def commit_text(self):
        commit = _new_struct(RimeCommit)
        if not self.api.dll.RimeGetCommit(self.id, byref(commit)):
            return None
        try:
            return _s(commit.text)
        finally:
            self.api.dll.RimeFreeCommit(byref(commit))

    def select(self, index, on_current_page=True):
        """Select candidate by index; returns True on success.

        on_current_page=True matches the indices of the `candidates` array
        reported in the JSON output; False uses librime's absolute index
        (RimeSelectCandidate).
        """
        fn = (
            self.api.dll.RimeSelectCandidateOnCurrentPage
            if on_current_page
            else self.api.dll.RimeSelectCandidate
        )
        return bool(fn(self.id, int(index)))

    def current_schema(self):
        buf = ctypes.create_string_buffer(256)
        if self.api.dll.RimeGetCurrentSchema(self.id, buf, 256):
            return buf.value.decode("utf-8", "replace")
        return None

    # -- lifecycle ---------------------------------------------------------

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.api.dll.RimeDestroySession(self.id)
        finally:
            self.h._unregister_session(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


# ---------------------------------------------------------------------------
# Key sequence parsing (mirrors librime's KeySequence::Parse / KeyEvent::Parse)
# ---------------------------------------------------------------------------


def parse_key_sequence(spec, api=None):
    """Parse 'nihao' or 'ni{Page_Down}{Control+a}'.

    Returns a list of (label, keycode, modifier_mask).
    """
    from_api = api
    keys = []
    i = 0
    n = len(spec)
    while i < n:
        ch = spec[i]
        if ch == "{" and i + 1 < n:
            end = spec.find("}", i + 1)
            if end < 0:
                raise HarnessError("unbalanced '{' in key sequence: %r" % spec)
            token = spec[i + 1 : end]
            label = "{" + token + "}"
            keycode, mask = parse_key_token(token, from_api)
            keys.append((label, keycode, mask))
            i = end + 1
        else:
            code = ord(ch)
            if code > 0x7E or code < 0x20:
                raise HarnessError(
                    "non-ASCII/control character %r is not supported in --input; "
                    "use a {Key_Name} token instead" % ch
                )
            keys.append((ch, code, 0))
            i += 1
    return keys


def parse_key_token(token, api=None):
    if not token:
        raise HarnessError("empty {} key token")
    if len(token) == 1:
        return ord(token), 0
    parts = token.split("+")
    mask = 0
    for part in parts[:-1]:
        mod = api.modifier_by_name(part) if api else MODIFIERS.get(part, 0)
        if not mod:
            raise HarnessError("unknown modifier %r in {%s}" % (part, token))
        mask |= mod
    name = parts[-1]
    keycode = api.keycode_by_name(name) if api else FALLBACK_KEYCODES.get(name)
    if not keycode:
        raise HarnessError("unknown key name %r in {%s}" % (name, token))
    return keycode, mask


# ---------------------------------------------------------------------------
# High-level run + CLI
# ---------------------------------------------------------------------------


def run_single(
    harness,
    input_spec="",
    sequence=None,
    schema=None,
    options=None,
    select=None,
    select_absolute=None,
    include_steps=False,
    extra_options=(),
):
    started = time.time()
    with harness.session(schema=schema, options=options) as session:
        if sequence is not None:
            simulate_ok = session.simulate(sequence)
            consumed, steps = (None, [])
        else:
            simulate_ok = None
            consumed, steps = session.type(input_spec, collect_steps=include_steps)

        ctx = session.context()
        status = session.status()

        select_ok = None
        selected_index = None
        commit = None
        post_ctx = None
        if select is not None:
            select_ok = session.select(select, on_current_page=True)
            selected_index = select
            if not select_ok:
                raise HarnessError(
                    "candidate %d not selectable on current page (page %d has %d candidates)"
                    % (select, ctx["page"], len(ctx["candidates"]))
                )
        elif select_absolute is not None:
            select_ok = session.select(select_absolute, on_current_page=False)
            selected_index = select_absolute
            if not select_ok:
                raise HarnessError(
                    "absolute candidate index %d not selectable" % select_absolute
                )
        commit = session.commit_text()
        if select_ok:
            post_ctx = session.context()
        options_snapshot = session.options(list(extra_options))
        elapsed = time.time() - started

    result = {
        "ok": True,
        "input": sequence if sequence is not None else input_spec,
        "schema": status.get("schema_id") or (schema or harness.schema),
        "schema_name": status.get("schema_name", ""),
        "preedit": ctx["preedit"],
        "composition": ctx["composition"],
        "commit_text_preview": ctx["commit_text_preview"],
        "page": ctx["page"],
        "page_size": ctx["page_size"],
        "is_last_page": ctx["is_last_page"],
        "highlighted_candidate_index": ctx["highlighted_candidate_index"],
        "candidates": ctx["candidates"],
        "select_keys": ctx["select_keys"],
        "select_labels": ctx["select_labels"],
        "commit": commit,
        "status": status,
        "options": options_snapshot,
        "keys": {
            "consumed": consumed,
            "simulate_ok": simulate_ok,
        },
        "select": {"requested": selected_index, "ok": select_ok},
        "meta": {
            "dll": harness._api.dll_path,
            "shared_data_dir": harness.shared,
            "user_data_dir": harness.user,
            "build_dir": harness.build_dir,
            "deployed": harness.deployed_this_run,
            "deploy_seconds": round(harness.deploy_seconds, 2),
            "deploy_events": harness.deploy_events,
            "elapsed_ms": int(elapsed * 1000),
            "librime_struct_sizes": {
                cls.__name__: ctypes.sizeof(cls) for cls in EXPECTED_SIZES
            },
        },
    }
    if include_steps:
        result["steps"] = steps
    if post_ctx is not None:
        result["post_select"] = {
            "preedit": post_ctx["preedit"],
            "is_composing": bool(post_ctx["preedit"]),
        }
    return result


def _parse_option(spec):
    if "=" not in spec:
        raise argparse.ArgumentTypeError(
            "--option expects NAME=VALUE, got %r" % spec
        )
    name, value = spec.split("=", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("empty option name in %r" % spec)
    v = value.strip().lower()
    if v in ("1", "true", "yes", "on"):
        return name, True
    if v in ("0", "false", "no", "off"):
        return name, False
    raise argparse.ArgumentTypeError(
        "option value must be 0/1/true/false, got %r" % value
    )


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Drive librime (Rime) from the command line and print JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--dll", default=DEFAULT_DLL, help="path to rime.dll")
    p.add_argument(
        "--shared",
        default=DEFAULT_SHARED,
        help="shared_data_dir (default: Weasel 0.17.4 data dir)",
    )
    p.add_argument(
        "--user",
        default=None,
        help="user_data_dir; created if missing (default: %%TEMP%%\\mgjy-rime-harness\\default)",
    )
    p.add_argument("--schema", default=None, help="schema id, e.g. luna_pinyin_simp")
    p.add_argument(
        "--input",
        default="",
        help='keys to type; plain ASCII plus {Name} tokens, e.g. "nihao" or "ni{Page_Down}"',
    )
    p.add_argument(
        "--sequence",
        default=None,
        help='librime key sequence via RimeSimulateKeySequence, e.g. "nihao{space}"',
    )
    p.add_argument(
        "--option",
        action="append",
        default=[],
        type=_parse_option,
        metavar="NAME=VALUE",
        help="set a session option before typing (repeatable)",
    )
    p.add_argument(
        "--get-option",
        action="append",
        default=[],
        metavar="NAME",
        help="additional option to report (repeatable)",
    )
    p.add_argument(
        "--select",
        type=int,
        default=None,
        metavar="N",
        help="select candidate N from the current page (indices as in candidates[])",
    )
    p.add_argument(
        "--select-absolute",
        type=int,
        default=None,
        metavar="N",
        help="select candidate N using librime's absolute index",
    )
    p.add_argument(
        "--deploy",
        choices=["auto", "always", "never"],
        default="auto",
        help="deploy before running: auto=only when sources/build changed (default)",
    )
    p.add_argument("--prebuilt", default=None, help="prebuilt_data_dir override")
    p.add_argument("--staging", default=None, help="staging_dir override")
    p.add_argument("--log-dir", default=None, help="directory for librime logs")
    p.add_argument(
        "--log-level",
        type=int,
        default=2,
        choices=[0, 1, 2, 3],
        help="min log level: 0=INFO 1=WARNING 2=ERROR 3=FATAL (default: 2)",
    )
    p.add_argument(
        "--no-write-custom",
        action="store_true",
        help="do not write default.custom.yaml (use the dir's existing config)",
    )
    p.add_argument(
        "--fresh-user",
        action="store_true",
        help="create a new unique temp user dir instead of reusing --user",
    )
    p.add_argument("--steps", action="store_true", help="include per-key snapshots")
    p.add_argument("--json", action="store_true", help="print one JSON object")
    p.add_argument("--pretty", action="store_true", help="indent JSON output")
    p.add_argument(
        "--list-schemas", action="store_true", help="list deployed schemas and exit"
    )
    return p


def _print_human(result):
    print("input      : %s" % result["input"])
    print(
        "schema     : %s (%s)"
        % (result.get("schema") or "?", result.get("schema_name") or "?")
    )
    print(
        "preedit    : %r  cursor=%d  len=%d"
        % (
            result["preedit"],
            result["composition"]["cursor_pos"],
            result["composition"]["length"],
        )
    )
    print(
        "page       : %d  size=%d  last=%s  highlighted=%d"
        % (
            result["page"],
            result["page_size"],
            result["is_last_page"],
            result["highlighted_candidate_index"],
        )
    )
    print("candidates :")
    if not result["candidates"]:
        print("  (none)")
    for cand in result["candidates"]:
        comment = ("  # " + cand["comment"]) if cand["comment"] else ""
        print("  %2d. %s%s" % (cand["index"], cand["text"], comment))
    print("commit     : %r" % (result["commit"],))
    print("options    : %s" % json.dumps(result["options"], ensure_ascii=False))
    meta = result["meta"]
    print(
        "deploy     : %s (%.2fs)  user=%s"
        % (meta["deployed"], meta["deploy_seconds"], meta["user_data_dir"])
    )


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.select is not None and args.select_absolute is not None:
        parser.error("--select and --select-absolute are mutually exclusive")
    if args.sequence is not None and args.input:
        parser.error("--input and --sequence are mutually exclusive")

    user_dir = args.user
    if args.fresh_user:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        user_dir = os.path.join(
            tempfile.gettempdir(),
            "mgjy-rime-harness",
            "run-%s-%d" % (stamp, os.getpid()),
        )

    options = dict(args.option)

    try:
        harness = RimeHarness(
            shared_data_dir=args.shared,
            user_data_dir=user_dir,
            schema=args.schema,
            dll_path=args.dll,
            prebuilt_data_dir=args.prebuilt,
            staging_dir=args.staging,
            log_dir=args.log_dir,
            min_log_level=args.log_level,
            deploy=args.deploy,
            write_custom_config=not args.no_write_custom,
        )
    except HarnessError as exc:
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
        print("error: %s" % exc, file=sys.stderr)
        return 1

    try:
        if args.list_schemas:
            schemas = harness.list_schemas()
            if args.json:
                print(
                    json.dumps(
                        {"ok": True, "schemas": schemas},
                        ensure_ascii=False,
                        indent=2 if args.pretty else None,
                    )
                )
            else:
                for item in schemas:
                    print("%s\t%s" % (item["schema_id"], item["name"]))
            return 0

        result = run_single(
            harness,
            input_spec=args.input,
            sequence=args.sequence,
            schema=args.schema,
            options=options,
            select=args.select,
            select_absolute=args.select_absolute,
            include_steps=args.steps,
            extra_options=args.get_option,
        )
    except (HarnessError, ValueError) as exc:
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
        print("error: %s" % exc, file=sys.stderr)
        return 1
    finally:
        harness.close()

    if args.json:
        print(
            json.dumps(
                result, ensure_ascii=False, indent=2 if args.pretty else None
            )
        )
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
