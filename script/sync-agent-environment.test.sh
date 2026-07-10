#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT

export HOME="$temp/home"
project="$HOME/Projects/demo"
linked_project="$HOME/Projects/linked"
broken_project="$HOME/Projects/broken"
mkdir -p "$project"
mkdir -p "$linked_project"
mkdir -p "$broken_project"
printf '%s\n' '# Demo' >"$project/AGENTS.md"
printf '%s\n' '# Claude demo' >"$project/CLAUDE.md"
printf '%s\n' '# Shared agents' >"$temp/shared-agents.md"
printf '%s\n' '# Shared claude' >"$temp/shared-claude.md"
ln -s "$temp/shared-agents.md" "$linked_project/AGENTS.md"
ln -s "$temp/shared-claude.md" "$linked_project/CLAUDE.md"
ln -s "$temp/missing/nested/agents.md" "$broken_project/AGENTS.md"
ln -s "$temp/missing/nested/claude.md" "$broken_project/CLAUDE.md"

output="$("$repo_root/script/sync-agent-environment.sh")"

cmp -s "$repo_root/AGENTS.md" "$HOME/.codex/AGENTS.md"
[[ "$(realpath "$HOME/.claude/CLAUDE.md")" == "$(realpath "$repo_root/AGENTS.md")" ]]
[[ "$(realpath "$HOME/.claude/AGENTS.md")" == "$(realpath "$repo_root/AGENTS.md")" ]]
for skill in autoreview behavior-validator skill-cleaner; do
  [[ "$(realpath "$HOME/.agents/skills/$skill")" == "$(realpath "$repo_root/skills/$skill")" ]]
  [[ "$(realpath "$HOME/.claude/skills/$skill")" == "$(realpath "$repo_root/skills/$skill")" ]]
done

[[ "$(head -n 1 "$project/AGENTS.md")" == 'READ: ~/.codex/AGENTS.md' ]]
[[ "$(head -n 1 "$project/CLAUDE.md")" == 'READ: ~/.codex/AGENTS.md' ]]
[[ -L "$linked_project/AGENTS.md" ]]
[[ -L "$linked_project/CLAUDE.md" ]]
[[ "$(cat "$temp/shared-agents.md")" == '# Shared agents' ]]
[[ "$(cat "$temp/shared-claude.md")" == '# Shared claude' ]]
[[ -L "$broken_project/AGENTS.md" ]]
[[ -L "$broken_project/CLAUDE.md" ]]
[[ ! -e "$temp/missing/nested/agents.md" ]]
[[ ! -e "$temp/missing/nested/claude.md" ]]
grep -q 'Ambiente de agentes sincronizado com sucesso.' <<<"$output"

echo "sync-agent-environment: testes aprovados"
