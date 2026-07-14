#!/usr/bin/env bash
set -euo pipefail

base_version="${1:-}"
current_version="${2:-}"

if [[ -z "$base_version" || -z "$current_version" ]]; then
  echo "Could not parse the project version from the base or current pyproject.toml." >&2
  exit 2
fi

if [[ "$base_version" != "$current_version" ]]; then
  echo "changed=true"
  exit 0
fi

release_relevant_files=()
while IFS= read -r path || [[ -n "$path" ]]; do
  [[ -z "$path" ]] && continue
  case "$path" in
    tests/* | docs/* | .github/* | .vscode/* | .codex/* | .omx/*)
      ;;
    AGENTS.md | DOCUMENTATION_MAP.md | README.md | mkdocs.yml)
      ;;
    *)
      release_relevant_files+=("$path")
      ;;
  esac
done

if (( ${#release_relevant_files[@]} > 0 )); then
  echo "Project version remains $current_version, but release-relevant files changed:" >&2
  printf '  - %s\n' "${release_relevant_files[@]}" >&2
  echo "Bump the version in pyproject.toml for shipped code, API, runtime, or product changes." >&2
  exit 1
fi

echo "changed=false"
