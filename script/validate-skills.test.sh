#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT

mkdir -p "$temp/repo/script" "$temp/repo/skills/valid" "$temp/outside"
cp "$repo_root/script/validate-skills" "$temp/repo/script/validate-skills"
cat > "$temp/repo/skills/valid/SKILL.md" <<'EOF'
---
name: fixture
description: Skill de teste.
---
EOF

output="$(cd "$temp/outside" && "$temp/repo/script/validate-skills")"
[[ "$output" == 'Skills validadas: 1.' ]]

mkdir -p "$temp/repo/skills/invalid"
expect_failure() {
  if output="$(cd "$temp/outside" && "$temp/repo/script/validate-skills" 2>&1)"; then
    echo "Validação deveria rejeitar: $1" >&2
    exit 1
  fi
  [[ "$output" == *"$1"* ]]
}

cat > "$temp/repo/skills/invalid/SKILL.md" <<'EOF'
---
name: invalid
description: [
---
EOF
expect_failure 'YAML inválido'

cat > "$temp/repo/skills/invalid/SKILL.md" <<'EOF'
---
name: invalid
---
EOF
expect_failure 'campo obrigatório ausente ou vazio: description'

cat > "$temp/repo/skills/invalid/SKILL.md" <<'EOF'
---
name: fixture
description: Nome repetido.
---
EOF
expect_failure 'nome duplicado'

"$repo_root/script/validate-skills"

echo "validate-skills: testes aprovados"
