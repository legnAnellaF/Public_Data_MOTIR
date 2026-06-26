#!/usr/bin/env python3
"""Run the offline/fixture resource-first backend flow checks."""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", "tests/test_offline_resource_flow.py"]
    print("Running offline resource flow checks:", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
