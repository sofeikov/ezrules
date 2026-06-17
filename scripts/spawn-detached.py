#!/usr/bin/env python3
"""Spawn a command in a new session so it survives the parent shell exit."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: spawn-detached.py LOG_FILE command [args...]")

    log_path = sys.argv[1]
    command = sys.argv[2:]
    working_directory = os.environ.get("AGENT_STACK_CWD")

    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
            cwd=working_directory,
            env=os.environ.copy(),
        )

    print(process.pid)


if __name__ == "__main__":
    main()
