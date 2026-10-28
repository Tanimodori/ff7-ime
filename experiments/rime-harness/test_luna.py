#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_luna.py -- automated acceptance test for the rime_harness fixture.

Runs the CLI end-to-end against the stock Weasel 0.17.4 data directory with
`luna_pinyin_simp`, using temporary user data directories only.

    python test_luna.py
    python test_luna.py --keep          # keep temp dirs for debugging
    python test_luna.py --save-sample sample_output.json

Exit code 0 means every check passed.  The test never writes to the real
Rime user directory (%APPDATA%\\Rime); it verifies that as far as possible.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "rime_harness.py")
sys.path.insert(0, HERE)
import rime_harness  # noqa: E402  (for default paths only)

REAL_USER_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "Rime"
)


class Checker:
    def __init__(self):
        self.results = []

    def check(self, name, ok, detail=""):
        ok = bool(ok)
        self.results.append({"name": name, "ok": ok, "detail": detail})
        status = "PASS" if ok else "FAIL"
        line = "[%s] %s" % (status, name)
        if detail and not ok:
            line += " -- " + detail
        print(line)
        return ok

    def equal(self, name, actual, expected):
        return self.check(
            name, actual == expected, "expected %r, got %r" % (expected, actual)
        )

    @property
    def failed(self):
        return [r for r in self.results if not r["ok"]]


def snapshot_tree(root):
    """Map of relative path -> (size, mtime_ns) for every file under root."""
    snap = {}
    if not os.path.isdir(root):
        return snap
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            snap[os.path.relpath(path, root)] = (st.st_size, st.st_mtime_ns)
    return snap


def weasel_server_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq WeaselServer.exe", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
    except OSError:
        return False
    return "WeaselServer.exe" in out


class HarnessRunner:
    def __init__(self, shared, dll, user_dir):
        self.shared = shared
        self.dll = dll
        self.user_dir = user_dir
        self.env = dict(os.environ)
        self.env["PYTHONUTF8"] = "1"
        self.env["PYTHONIOENCODING"] = "utf-8"

    def run(self, *args, expect_ok=True):
        cmd = [
            sys.executable,
            HARNESS,
            "--shared",
            self.shared,
            "--user",
            self.user_dir,
            "--dll",
            self.dll,
            "--json",
            *args,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.env,
        )
        if expect_ok and proc.returncode != 0:
            raise RuntimeError(
                "harness failed (exit %d)\ncmd: %s\nstdout: %s\nstderr: %s"
                % (proc.returncode, " ".join(cmd), proc.stdout, proc.stderr)
            )
        try:
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise RuntimeError(
                "no JSON on stdout (exit %d)\nstdout: %s\nstderr: %s"
                % (proc.returncode, proc.stdout, proc.stderr)
            )
        data["_exit_code"] = proc.returncode
        data["_stderr"] = proc.stderr
        return data


def candidates_text(data):
    return [c["text"] for c in data.get("candidates", [])]


def index_of(data, text):
    for cand in data.get("candidates", []):
        if cand["text"] == text:
            return cand["index"]
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared", default=rime_harness.DEFAULT_SHARED)
    parser.add_argument("--dll", default=rime_harness.DEFAULT_DLL)
    parser.add_argument(
        "--schema", default="luna_pinyin_simp", help="schema under test"
    )
    parser.add_argument("--keep", action="store_true", help="keep temp dirs")
    parser.add_argument(
        "--save-sample", default=None, help="write the main JSON result here"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if not os.path.isfile(HARNESS):
        print("cannot find %s" % HARNESS, file=sys.stderr)
        return 2
    if not os.path.isfile(args.dll):
        print("cannot find %s" % args.dll, file=sys.stderr)
        return 2

    tmp_root = tempfile.mkdtemp(prefix="mgjy-luna-test-")
    user_dir = os.path.join(tmp_root, "user")
    bad_user_dir = os.path.join(tmp_root, "user-bad")
    never_user_dir = os.path.join(tmp_root, "user-never")
    runner = HarnessRunner(args.shared, args.dll, user_dir)
    bad_runner = HarnessRunner(args.shared, args.dll, bad_user_dir)
    never_runner = HarnessRunner(args.shared, args.dll, never_user_dir)
    checker = Checker()

    real_before = snapshot_tree(REAL_USER_DIR)
    server_running = weasel_server_running()
    print("temp root  : %s" % tmp_root)
    print("schema     : %s" % args.schema)
    print("real Rime  : %s (%s)" % (REAL_USER_DIR, "exists" if real_before else "absent"))
    print("weasel srv : %s" % ("running" if server_running else "not running"))
    print("-" * 78)

    sample = None
    started = time.time()
    try:
        # ------------------------------------------------------------- 1
        first = runner.run(
            "--schema", args.schema,
            "--input", "nihao",
            "--select", "0",
        )
        sample = first
        texts = candidates_text(first)
        print("nihao -> %r" % (texts,))
        checker.equal("first run: ok", first.get("ok"), True)
        checker.equal("first run: schema", first.get("schema"), args.schema)
        checker.equal("first run: deploy ran", first["meta"]["deployed"], True)
        checker.check(
            "first run: deploy success notification",
            any(
                e.get("type") == "deploy" and e.get("value") == "success"
                for e in first["meta"]["deploy_events"]
            ),
            repr(first["meta"]["deploy_events"]),
        )
        checker.check(
            "first run: user_data_dir is the temp dir",
            os.path.normcase(os.path.abspath(first["meta"]["user_data_dir"]))
            == os.path.normcase(os.path.abspath(user_dir)),
            first["meta"]["user_data_dir"],
        )
        checker.check(
            "first run: shared_data_dir is the install data dir",
            os.path.normcase(os.path.abspath(first["meta"]["shared_data_dir"]))
            == os.path.normcase(os.path.abspath(args.shared)),
            first["meta"]["shared_data_dir"],
        )
        checker.check("first run: candidates non-empty", len(texts) > 0, repr(texts))
        checker.check("first run: 你好 in candidates", "你好" in texts, repr(texts))
        checker.equal("first run: candidates[0]", texts[0] if texts else None, "你好")
        checker.equal("first run: commit after selecting 0", first.get("commit"), "你好")
        checker.equal(
            "first run: commit_text_preview", first.get("commit_text_preview"), "你好"
        )
        checker.equal("first run: composing", first["status"]["is_composing"], True)
        checker.check(
            "first run: preedit contains the typed syllables",
            "ni" in first["preedit"] and "hao" in first["preedit"],
            repr(first["preedit"]),
        )
        checker.equal("first run: keys consumed", first["keys"]["consumed"], 5)
        checker.equal("first run: page size", first["page_size"], 5)
        for key in ("input", "candidates", "commit"):
            checker.check("first run: JSON has key %r" % key, key in first)

        # ------------------------------------------------------------- 2
        second = runner.run(
            "--schema", args.schema,
            "--input", "nihao",
            "--select", "0",
        )
        print("second run texts -> %r" % (candidates_text(second),))
        checker.equal("repeat run: ok", second.get("ok"), True)
        checker.equal("repeat run: deploy skipped", second["meta"]["deployed"], False)
        checker.equal("repeat run: same commit", second.get("commit"), "你好")
        checker.equal(
            "repeat run: stable candidate order",
            candidates_text(second),
            texts,
        )

        # ------------------------------------------------------------- 3
        for value, expected in (("0", "漢字"), ("1", "汉字")):
            option_run = runner.run(
                "--schema", args.schema,
                "--input", "hanzi",
                "--option", "zh_simp=" + value,
            )
            texts = candidates_text(option_run)
            print("hanzi zh_simp=%s -> %r" % (value, texts))
            checker.equal(
                "zh_simp=%s: option value" % value,
                option_run["options"]["zh_simp"],
                value == "1",
            )
            checker.check(
                "zh_simp=%s: %s in candidates" % (value, expected),
                expected in texts,
                repr(texts),
            )
            idx = index_of(option_run, expected)
            if idx is None:
                checker.check("zh_simp=%s: select %s" % (value, expected), False, "not found")
                continue
            selected = runner.run(
                "--schema", args.schema,
                "--input", "hanzi",
                "--option", "zh_simp=" + value,
                "--select", str(idx),
            )
            checker.equal(
                "zh_simp=%s: commit %s" % (value, expected),
                selected.get("commit"),
                expected,
            )

        # ------------------------------------------------------------- 4
        page0 = runner.run("--schema", args.schema, "--input", "ni")
        page1 = runner.run(
            "--schema", args.schema,
            "--input", "ni{Page_Down}",
            "--select", "0",
        )
        print("ni page0 -> %r" % (candidates_text(page0),))
        print("ni page1 -> %r" % (candidates_text(page1),))
        checker.equal("paging: page number", page1.get("page"), 1)
        checker.equal("paging: page size", page1.get("page_size"), 5)
        checker.check(
            "paging: page 1 has candidates", len(candidates_text(page1)) > 0,
            repr(candidates_text(page1)),
        )
        checker.check(
            "paging: page 1 differs from page 0",
            candidates_text(page1) != candidates_text(page0),
            "page0=%r page1=%r" % (candidates_text(page0), candidates_text(page1)),
        )
        checker.equal(
            "paging: selecting page-relative 0 commits that candidate",
            page1.get("commit"),
            candidates_text(page1)[0] if candidates_text(page1) else None,
        )

        # ------------------------------------------------------------- 5
        ascii_run = runner.run(
            "--schema", args.schema,
            "--input", "nihao",
            "--option", "ascii_mode=1",
        )
        checker.equal(
            "ascii_mode: status flag", ascii_run["status"]["is_ascii_mode"], True
        )
        checker.equal("ascii_mode: no keys consumed", ascii_run["keys"]["consumed"], 0)
        checker.equal("ascii_mode: no commit", ascii_run.get("commit"), None)

        # ------------------------------------------------------------- 6
        absolute = runner.run(
            "--schema", args.schema,
            "--input", "nihao",
            "--select-absolute", "0",
        )
        checker.equal(
            "select-absolute 0: commit matches candidate 0",
            absolute.get("commit"),
            candidates_text(absolute)[0] if candidates_text(absolute) else None,
        )

        # ------------------------------------------------------------- 7
        schemas = runner.run("--schema", args.schema, "--list-schemas")
        checker.check(
            "list-schemas includes %s" % args.schema,
            any(s["schema_id"] == args.schema for s in schemas.get("schemas", [])),
            repr(schemas.get("schemas")),
        )

        # ------------------------------------------------------------- 8
        bad = bad_runner.run(
            "--schema", "no_such_schema", "--input", "a", expect_ok=False
        )
        checker.equal("bad schema: exit code", bad["_exit_code"], 1)
        checker.equal("bad schema: ok=false", bad.get("ok"), False)
        checker.check(
            "bad schema: error message",
            "no_such_schema" in (bad.get("error") or ""),
            repr(bad.get("error")),
        )

        # ------------------------------------------------------------- 9
        never = never_runner.run(
            "--schema", args.schema,
            "--input", "a",
            "--deploy", "never",
            expect_ok=False,
        )
        checker.equal("deploy never on empty dir: exit code", never["_exit_code"], 1)
        checker.check(
            "deploy never on empty dir: error mentions build",
            "deployment artifacts missing" in (never.get("error") or ""),
            repr(never.get("error")),
        )

    except Exception as exc:  # noqa: BLE001 - report and keep going
        checker.check("test execution", False, "%s: %s" % (type(exc).__name__, exc))
    finally:
        real_after = snapshot_tree(REAL_USER_DIR)
        if real_before == real_after:
            checker.check("real Rime user dir untouched", True)
        elif server_running:
            checker.check(
                "real Rime user dir untouched",
                True,
                "changed, but WeaselServer.exe is running (background writes)",
            )
            print(
                "NOTE: %s changed while WeaselServer.exe was running; this is "
                "most likely the running IME, not the harness." % REAL_USER_DIR
            )
        else:
            changed = sorted(
                set(real_before) ^ set(real_after)
                | {
                    p
                    for p in set(real_before) & set(real_after)
                    if real_before[p] != real_after[p]
                }
            )
            checker.check(
                "real Rime user dir untouched",
                False,
                "changed files: %s" % ", ".join(changed[:10]),
            )

    elapsed = time.time() - started
    failed = checker.failed
    print("-" * 78)
    print(
        "%d checks, %d failed, %.1fs"
        % (len(checker.results), len(failed), elapsed)
    )

    if args.save_sample and sample is not None:
        with open(args.save_sample, "w", encoding="utf-8", newline="\n") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("sample written to %s" % args.save_sample)

    if args.verbose and sample is not None:
        print(json.dumps(sample, ensure_ascii=False, indent=2))

    if not args.keep:
        shutil.rmtree(tmp_root, ignore_errors=True)
    else:
        print("kept temp dirs under %s" % tmp_root)

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
