#!/usr/bin/env python3
"""Launch the supported Unicorn C API -> LSL streamer."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent / "unicorn_capi_stream.py"

COMMON_LIBLSL_PATHS = [
    "/usr/local/lib/liblsl.so",
    "/usr/lib/liblsl.so",
    "/usr/lib/aarch64-linux-gnu/liblsl.so",
    "/usr/lib/arm-linux-gnueabihf/liblsl.so",
]

COMMON_LIBLSL_DIRS = [
    "/usr/local/lib",
    "/usr/lib",
    "/usr/lib/aarch64-linux-gnu",
    "/usr/lib/arm-linux-gnueabihf",
]


def main() -> int:
    forwarded = list(sys.argv[1:])
    cmd = [sys.executable, str(SCRIPT_PATH), *forwarded]
    print("[launcher] Running Unicorn C API streamer")
    print("[launcher] Command:", " ".join(cmd))
    env = os.environ.copy()
    if "PYLSL_LIB" not in env:
        for candidate in COMMON_LIBLSL_PATHS:
            if Path(candidate).exists():
                env["PYLSL_LIB"] = candidate
                print(f"[launcher] Using PYLSL_LIB={candidate}")
                break
        else:
            for directory in COMMON_LIBLSL_DIRS:
                path = Path(directory)
                if not path.exists():
                    continue
                matches = sorted(path.glob("liblsl.so*"))
                if matches:
                    env["PYLSL_LIB"] = str(matches[0])
                    print(f"[launcher] Using PYLSL_LIB={matches[0]}")
                    break

    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())

