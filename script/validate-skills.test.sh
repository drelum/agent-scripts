#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT

output="$(cd "$temp" && "$repo_root/script/validate-skills")"
[[ "$output" == 'Skills validadas: 3.' ]]

echo "validate-skills: testes aprovados"
