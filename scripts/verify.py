"""Run the source verification gates without treating skipped tests as success."""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def diff_base() -> str:
    candidates = [os.environ.get("VERIFY_BASE_SHA"), "main", "origin/main", "HEAD^"]
    for candidate in candidates:
        if not candidate or set(candidate) == {"0"}:
            continue
        result = subprocess.run(
            ["git", "rev-parse", "--verify", candidate],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return candidate
    raise RuntimeError("Could not find a base revision for committed diff checks.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-only", action="store_true", help="Explicitly omit desktop tests")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 14):
        print("Verification needs the project's Python 3.14 interpreter.", file=sys.stderr)
        return 1
    if not args.backend_only and importlib.util.find_spec("PySide6") is None:
        print(
            "Full verification needs requirements-desktop.txt. --web-only omits desktop explicitly.",
            file=sys.stderr,
        )
        return 1
    with tempfile.TemporaryDirectory(prefix="flexweek-verify-") as directory:
        report = Path(directory) / "pytest.xml"
        try:
            base = diff_base()
        except RuntimeError as error:
            print(f"FAILED: {error}", file=sys.stderr)
            return 1
        steps = [
            ("Python lint", [sys.executable, "-m", "ruff", "check", "."]),
            ("Backend types", [sys.executable, "-m", "mypy", "backend"]),
            (
                "Python behavior",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    # One worker a core: the suite took 461 s on one and about a minute on eight.
                    "-n",
                    "auto",
                    f"--junitxml={report}",
                    *(["backend/tests"] if args.backend_only else []),
                ],
            ),
            ("Working diff whitespace", ["git", "diff", "--check"]),
            ("Staged diff whitespace", ["git", "diff", "--cached", "--check"]),
            ("Committed range whitespace", ["git", "diff", "--check", f"{base}...HEAD"]),
        ]
        for name, command in steps:
            print(f"\n{name}", flush=True)
            try:
                capture = False
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    check=False,
                    timeout=480,
                    capture_output=capture,
                    text=capture,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                print(f"FAILED: {name}: {error}", file=sys.stderr)
                return 1
            if result.returncode:
                if capture:
                    print(result.stdout, end="")
                    print(result.stderr, end="", file=sys.stderr)
                print(f"FAILED: {name} (exit {result.returncode})", file=sys.stderr)
                return 1
            if capture:
                print(result.stdout, end="")
                print(result.stderr, end="", file=sys.stderr)
                tests_match = re.search(r"^# tests (\d+)$", result.stdout, re.MULTILINE)
                skipped_match = re.search(r"^# skipped (\d+)$", result.stdout, re.MULTILINE)
                if (
                    not tests_match
                    or not skipped_match
                    or int(tests_match.group(1)) == 0
                    or int(skipped_match.group(1)) != 0
                ):
                    print(
                        "FAILED: Frontend suite ran no tests, skipped tests, or emitted unknown TAP.",
                        file=sys.stderr,
                    )
                    return 1
        suites = list(ET.parse(report).getroot().iter("testsuite"))
        count = sum(int(suite.get("tests", "0")) for suite in suites)
        skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
        if count == 0 or skipped:
            print(f"FAILED: Python suite ran {count} tests with {skipped} skipped.", file=sys.stderr)
            return 1
    scope = "Backend only; desktop NOT VERIFIED" if args.backend_only else "Backend and desktop"
    print(f"\nVERIFIED: {scope}. Packaged binaries and other platforms need separate checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
