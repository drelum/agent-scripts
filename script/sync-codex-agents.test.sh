#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

python3 - "$repo_root/agents/codex/visual-inspector.toml" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as file:
    agent = tomllib.load(file)

assert agent["model"] == "gpt-5.6-sol"
assert agent["model_reasoning_effort"] == "medium"
assert agent["name"] == "visual_inspector"
assert agent["description"]
assert agent["developer_instructions"]
PY

source_dir="$tmp/source"
target_dir="$tmp/target"
mkdir -p "$source_dir" "$target_dir" "$tmp/foreign"
printf '%s\n' 'name = "demo"' 'description = "Demo"' 'developer_instructions = "Demo"' >"$source_dir/demo.toml"
printf '%s\n' 'name = "collision"' 'description = "Collision"' 'developer_instructions = "Collision"' >"$source_dir/collision.toml"
printf '%s\n' 'name = "linked"' 'description = "Linked"' 'developer_instructions = "Linked"' >"$source_dir/linked.toml"
printf '%s\n' 'preserve' >"$target_dir/collision.toml"
ln -s "$tmp/foreign/agent.toml" "$target_dir/foreign.toml"
ln -s "$source_dir/linked.toml" "$target_dir/linked.toml"

"$repo_root/script/sync-codex-agents.sh" --source "$source_dir" --target "$target_dir"

[[ -f "$target_dir/demo.toml" && ! -L "$target_dir/demo.toml" ]]
[[ -f "$target_dir/linked.toml" && ! -L "$target_dir/linked.toml" ]]
cmp -s "$source_dir/demo.toml" "$target_dir/demo.toml"
cmp -s "$source_dir/linked.toml" "$target_dir/linked.toml"
[[ -f "$target_dir/collision.toml" && ! -L "$target_dir/collision.toml" ]]
[[ "$(readlink "$target_dir/foreign.toml")" == "$tmp/foreign/agent.toml" ]]

printf '%s\n' 'developer_instructions = "Atualizado"' >>"$source_dir/demo.toml"
second="$("$repo_root/script/sync-codex-agents.sh" --source "$source_dir" --target "$target_dir")"
[[ "$second" == *"atualizados: 1; inalterados: 1"* ]]
cmp -s "$source_dir/demo.toml" "$target_dir/demo.toml"

printf '%s\n' '# alteração local' >>"$target_dir/demo.toml"
printf '%s\n' '# nova fonte' >>"$source_dir/demo.toml"
"$repo_root/script/sync-codex-agents.sh" --source "$source_dir" --target "$target_dir" >/dev/null
grep -q '# alteração local' "$target_dir/demo.toml"

"$repo_root/script/sync-codex-agents.sh" \
  --source "$source_dir" \
  --target "$target_dir" \
  --replace-existing >/dev/null
cmp -s "$source_dir/demo.toml" "$target_dir/demo.toml"
cmp -s "$source_dir/collision.toml" "$target_dir/collision.toml"

dry_target="$tmp/dry-target"
"$repo_root/script/sync-codex-agents.sh" \
  --source "$source_dir" \
  --target "$dry_target" \
  --dry-run >/dev/null
[[ ! -e "$dry_target" ]]

if "$repo_root/script/sync-codex-agents.sh" \
  --source "$source_dir" \
  --target "$source_dir" >/dev/null 2>&1; then
  echo "sync-codex-agents: destino sobreposto deveria falhar" >&2
  exit 1
fi
[[ -f "$source_dir/demo.toml" ]]

echo "sync-codex-agents: testes aprovados"
