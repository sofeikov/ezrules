#!/usr/bin/env bash
set -euo pipefail

base_ref="${1:?base ref is required}"
head_ref="${2:?head ref is required}"

git -c core.quotePath=false diff \
  --merge-base \
  --name-only \
  --diff-filter=ACMRD \
  "$base_ref" \
  "$head_ref"
