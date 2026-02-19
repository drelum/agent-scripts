#!/usr/bin/env bash
set -euo pipefail

# Sincroniza o AGENTS.md deste repo com o arquivo usado pelo Codex (`~/.codex/AGENTS.md`).
# Uso:
#   bash script/ensure_agent_std.sh
#
# Extra:
# - Varre projetos em ~/Projects (exceto ~/Projects/oss) e garante que cada
#   AGENTS.md tenha no topo uma linha `READ: ~/.codex/AGENTS.md`.
#   Regra:
#   - Se essa linha não existir em nenhum lugar do arquivo, prefixa no topo.
#   - Se existir em algum lugar (inclusive duplicada), remove todas as ocorrencias
#     e escreve uma única vez no topo.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="${repo_root}/AGENTS.md"
dst="${HOME}/.codex/AGENTS.md"

if [[ ! -f "$src" ]]; then
  echo "Erro: não achei $src" >&2
  exit 1
fi

mkdir -p "$(dirname "$dst")"
install -m 644 "$src" "$dst"

if cmp -s "$src" "$dst"; then
  echo "OK: $dst atualizado (idêntico ao repo)."
else
  echo "Erro: $dst não ficou idêntico ao repo." >&2
  exit 2
fi

# ------------------------------
# Normaliza AGENTS.md por projeto
# ------------------------------

projects_root="${HOME}/Projects"
oss_root="${projects_root}/oss"
read_line='READ: ~/.codex/AGENTS.md'

if [[ ! -d "$projects_root" ]]; then
  echo "Aviso: $projects_root não existe; pulei normalização de projetos." >&2
  exit 0
fi

src_real="$src"
if command -v realpath >/dev/null 2>&1; then
  src_real="$(realpath "$src")"
fi

updated=0
checked=0
skipped=0
created=0
renamed=0
claude_created=0
claude_linked=0
claude_backed_up=0
claude_skipped=0

ensure_claude_link() {
  local dir="$1"
  local agents_path="$dir/AGENTS.md"
  local claude_path="$dir/CLAUDE.md"
  local existed=0

  [[ -e "$agents_path" ]] || return 0

  if [[ ! -w "$dir" ]]; then
    echo "Aviso: sem permissão de escrita no diretório (CLAUDE.md): $dir" >&2
    claude_skipped=$((claude_skipped + 1))
    return 0
  fi

  # Já está apontando para o AGENTS.md do próprio projeto? Então OK.
  if [[ -L "$claude_path" ]]; then
    if command -v realpath >/dev/null 2>&1; then
      local claude_real agents_real
      claude_real="$(realpath "$claude_path" 2>/dev/null || true)"
      agents_real="$(realpath "$agents_path" 2>/dev/null || true)"
      if [[ -n "$claude_real" && -n "$agents_real" && "$claude_real" == "$agents_real" ]]; then
        return 0
      fi
    elif command -v readlink >/dev/null 2>&1; then
      local link_target
      link_target="$(readlink "$claude_path" 2>/dev/null || true)"
      if [[ "$link_target" == "AGENTS.md" || "$link_target" == "./AGENTS.md" ]]; then
        return 0
      fi
    fi
  fi

  # Existe, mas não é o link desejado: preservar como backup e criar o symlink.
  if [[ -e "$claude_path" || -L "$claude_path" ]]; then
    existed=1
    local ts backup
    ts="$(date +%Y%m%d%H%M%S)"
    backup="$dir/CLAUDE.md.bak.$ts"
    if ! mv "$claude_path" "$backup"; then
      echo "Aviso: falha ao mover para backup (CLAUDE.md): $claude_path" >&2
      claude_skipped=$((claude_skipped + 1))
      return 0
    fi
    claude_backed_up=$((claude_backed_up + 1))
  fi

  if ln -s "AGENTS.md" "$claude_path"; then
    claude_linked=$((claude_linked + 1))
    if [[ "$existed" -eq 0 ]]; then
      claude_created=$((claude_created + 1))
    fi
  else
    echo "Aviso: falha ao criar symlink (CLAUDE.md): $claude_path" >&2
    claude_skipped=$((claude_skipped + 1))
  fi
}

for dir in "$projects_root"/*; do
  [[ -d "$dir" ]] || continue
  [[ "$dir" == "$oss_root" ]] && continue

  # Padrao: AGENTS.md (case-sensitive). Aceita agents.md por compat.
  # Se só existir agents.md, renomeia para AGENTS.md.
  # Se não existir nenhum dos dois, cria AGENTS.md.
  f=""
  if [[ -f "$dir/AGENTS.md" ]]; then
    f="$dir/AGENTS.md"
  elif [[ -f "$dir/agents.md" ]]; then
    if [[ -f "$dir/AGENTS.md" ]]; then
      # Caso raro: ambos existem. Preferir AGENTS.md; não apaga o outro.
      echo "Aviso: ambos existem; usando AGENTS.md: $dir" >&2
      f="$dir/AGENTS.md"
    else
      if [[ ! -w "$dir/agents.md" || ! -w "$dir" ]]; then
        echo "Aviso: sem permissão para renomear: $dir/agents.md" >&2
        skipped=$((skipped + 1))
        continue
      fi
      mv "$dir/agents.md" "$dir/AGENTS.md"
      renamed=$((renamed + 1))
      f="$dir/AGENTS.md"
    fi
  else
    if [[ ! -w "$dir" ]]; then
      echo "Aviso: sem permissão de escrita no diretório: $dir" >&2
      skipped=$((skipped + 1))
      continue
    fi
    f="$dir/AGENTS.md"
    printf '%s\n' "$read_line" >"$f"
    created=$((created + 1))
  fi

  # Não toque no AGENTS.md deste repo; ele é a fonte do global.
  f_real="$f"
  if command -v realpath >/dev/null 2>&1; then
    f_real="$(realpath "$f")"
  fi
  [[ "$f_real" == "$src_real" ]] && continue

  checked=$((checked + 1))

  # CLAUDE.md: sempre tentar padronizar, mesmo quando AGENTS.md não é gravável.
  ensure_claude_link "$dir"

  if [[ ! -w "$f" ]]; then
    echo "Aviso: sem permissão de escrita (AGENTS.md): $f" >&2
    skipped=$((skipped + 1))
    continue
  fi

  # Remove todas as ocorrencias da linha READ e escreve uma única no topo.
  # Obs: comparação ignora CR final para tolerar arquivos com CRLF.
  tmp="$(mktemp)"
  awk -v read_line="$read_line" '
    BEGIN { print read_line }
    {
      line = $0
      sub(/\r$/, "", line)
      if (line == read_line) next
      print $0
    }
  ' "$f" >"$tmp"

  # Se nada mudou, não reescreve.
  if cmp -s "$f" "$tmp"; then
    rm -f "$tmp"
    continue
  fi

  cat "$tmp" >"$f"
  rm -f "$tmp"
  updated=$((updated + 1))
done

echo "OK: projetos checados: $checked; criados: $created; renomeados: $renamed; atualizados: $updated; pulados: $skipped; CLAUDE.md links: $claude_linked; CLAUDE.md backups: $claude_backed_up; CLAUDE.md novos: $claude_created; CLAUDE.md pulados: $claude_skipped"
