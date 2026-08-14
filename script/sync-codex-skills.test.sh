#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

source_dir="$tmp/source"
codex_target="$tmp/codex"
claude_target="$tmp/claude"
mkdir -p "$source_dir/demo" "$source_dir/collision" "$source_dir/disabled" "$codex_target/collision" "$tmp/foreign"
printf '%s\n' '---' 'name: demo' 'description: "Demo skill."' '---' '# Demo' >"$source_dir/demo/SKILL.md"
printf '%s\n' '---' 'name: collision' 'description: "Collision skill."' '---' '# Collision' >"$source_dir/collision/SKILL.md"
printf '%s\n' '---' 'name: disabled' 'description: "Disabled skill."' '---' '# Disabled' >"$source_dir/disabled/SKILL.md"
touch "$source_dir/disabled/.disabled"

mkdir -p "$codex_target" "$claude_target"
ln -s "$tmp/foreign" "$claude_target/foreign"
ln -s "$source_dir/stale" "$codex_target/stale"
ln -s "$source_dir/disabled" "$codex_target/disabled"
ln -s "$source_dir/disabled" "$claude_target/disabled"

"$repo_root/script/sync-codex-skills.sh" \
  --source "$source_dir" \
  --codex-target "$codex_target" \
  --claude-target "$claude_target"

[[ -L "$codex_target/demo" ]]
[[ -L "$claude_target/demo" ]]
[[ -L "$claude_target/collision" ]]
[[ "$(realpath "$codex_target/demo")" == "$source_dir/demo" ]]
[[ "$(realpath "$claude_target/demo")" == "$source_dir/demo" ]]
[[ -d "$codex_target/collision" ]]
[[ "$(readlink "$claude_target/foreign")" == "$tmp/foreign" ]]
[[ ! -e "$codex_target/stale" && ! -L "$codex_target/stale" ]]
[[ ! -e "$codex_target/disabled" && ! -L "$codex_target/disabled" ]]
[[ ! -e "$claude_target/disabled" && ! -L "$claude_target/disabled" ]]

second="$($repo_root/script/sync-codex-skills.sh \
  --source "$source_dir" \
  --codex-target "$codex_target" \
  --claude-target "$claude_target")"
[[ "$second" == *"Links criados/atualizados: 0; inalterados: 3"* ]]

dry_codex="$tmp/dry-codex"
dry_claude="$tmp/dry-claude"
"$repo_root/script/sync-codex-skills.sh" \
  --source "$source_dir" \
  --codex-target "$dry_codex" \
  --claude-target "$dry_claude" \
  --dry-run >/dev/null
[[ ! -e "$dry_codex" && ! -e "$dry_claude" ]]

legacy_home="$tmp/legacy-home"
legacy_target="$tmp/legacy-codex"
HOME="$legacy_home" "$repo_root/script/sync-codex-skills.sh" \
  --source "$source_dir" \
  --target "$legacy_target" >/dev/null
[[ -L "$legacy_target/demo" ]]
[[ ! -e "$legacy_home/.claude/skills" ]]

legacy_copy="$tmp/legacy-copy"
mkdir -p "$legacy_copy/demo"
cp -R "$source_dir/demo/." "$legacy_copy/demo/"
printf '%s\n' '# Stale legacy copy' >>"$legacy_copy/demo/SKILL.md"
"$repo_root/script/sync-codex-skills.sh" \
  --source "$source_dir" \
  --codex-target "$legacy_copy" \
  --claude-target "$tmp/legacy-copy-claude" \
  --replace-existing >/dev/null
[[ -L "$legacy_copy/demo" ]]
[[ "$(realpath "$legacy_copy/demo")" == "$source_dir/demo" ]]

if "$repo_root/script/sync-codex-skills.sh" \
  --source "$source_dir" \
  --codex-target "$source_dir" \
  --claude-target "$tmp/overlap-claude" \
  --replace-existing >/dev/null 2>&1; then
  echo "sync-codex-skills: destino sobreposto deveria falhar" >&2
  exit 1
fi
[[ -f "$source_dir/demo/SKILL.md" ]]

echo "sync-codex-skills: testes aprovados"
