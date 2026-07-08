#!/bin/bash
set -euo pipefail

uv run pytest -q tests/test_cli_smoke.py "$@"
