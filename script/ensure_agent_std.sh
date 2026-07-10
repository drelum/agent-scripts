#!/usr/bin/env bash
set -euo pipefail

# Sincroniza o AGENTS.md deste repo com o arquivo usado pelo Codex (`~/.codex/AGENTS.md`).
# Uso:
#   bash script/ensure_agent_std.sh
#
# Extra:
# - Varre projetos em ~/Projects (exceto ~/Projects/oss) e garante que cada
#   AGENTS.md e CLAUDE.md tenham no topo uma linha `READ: ~/.codex/AGENTS.md`.
#   Regra:
#   - Se essa linha não existir em nenhum lugar do arquivo, prefixa no topo.
#   - Se existir em algum lugar (inclusive duplicada), remove todas as ocorrencias
#     e escreve uma única vez no topo.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="${repo_root}/AGENTS.md"
dst="${HOME}/.codex/AGENTS.md"
claude_dir="${HOME}/.claude"

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

src_real="$(realpath "$src")"
dst_real="$(realpath "$dst")"
claude_links_created=0
claude_links_unchanged=0
claude_links_preserved=0

ensure_claude_link() {
  local destination="$1"
  local current

  if [[ -L "$destination" ]]; then
    current="$(realpath -m "$destination")"
    if [[ "$current" == "$src_real" ]]; then
      claude_links_unchanged=$((claude_links_unchanged + 1))
    elif [[ "$current" == "$dst_real" ]]; then
      ln -sfnT "$src_real" "$destination"
      claude_links_created=$((claude_links_created + 1))
    else
      echo "Aviso: symlink estrangeiro preservado: $destination -> $(readlink "$destination")" >&2
      claude_links_preserved=$((claude_links_preserved + 1))
    fi
  elif [[ -e "$destination" ]]; then
    echo "Aviso: arquivo global do Claude preservado: $destination" >&2
    claude_links_preserved=$((claude_links_preserved + 1))
  else
    ln -s "$src_real" "$destination"
    claude_links_created=$((claude_links_created + 1))
  fi
}

mkdir -p "$claude_dir"
ensure_claude_link "$claude_dir/CLAUDE.md"
ensure_claude_link "$claude_dir/AGENTS.md"
echo "OK: diretivas globais do Claude: criadas/atualizadas: $claude_links_created; inalteradas: $claude_links_unchanged; preservadas: $claude_links_preserved"

# ------------------------------
# Normaliza AGENTS.md e CLAUDE.md por projeto
# ------------------------------

projects_root="${HOME}/Projects"
oss_root="${projects_root}/oss"
read_line='READ: ~/.codex/AGENTS.md'

if [[ ! -d "$projects_root" ]]; then
  echo "Aviso: $projects_root não existe; pulei normalização de projetos." >&2
  exit 0
fi

updated=0
checked=0
skipped=0
created=0
renamed=0

normalize_read_line() {
  local f="$1"

  if [[ -L "$f" ]]; then
    echo "Aviso: symlink de diretiva preservado: $f -> $(readlink "$f")" >&2
    skipped=$((skipped + 1))
    return
  fi

  if [[ ! -w "$f" ]]; then
    echo "Aviso: sem permissão de escrita: $f" >&2
    skipped=$((skipped + 1))
    return
  fi

  # Remove todas as ocorrencias da linha READ e escreve uma única no topo.
  # Obs: comparação ignora CR final para tolerar arquivos com CRLF.
  local tmp
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
    return
  fi

  cat "$tmp" >"$f"
  rm -f "$tmp"
  updated=$((updated + 1))
}

for dir in "$projects_root"/*; do
  [[ -d "$dir" ]] || continue
  [[ "$dir" == "$oss_root" ]] && continue

  # Padrao: AGENTS.md (case-sensitive). Aceita agents.md por compat.
  # Se só existir agents.md, renomeia para AGENTS.md.
  # Se não existir nenhum dos dois, cria AGENTS.md.
  f=""
  if [[ -f "$dir/AGENTS.md" || -L "$dir/AGENTS.md" ]]; then
    f="$dir/AGENTS.md"
  elif [[ -f "$dir/agents.md" || -L "$dir/agents.md" ]]; then
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
    f_real="$(realpath -m "$f")"
  fi
  if [[ "$f_real" != "$src_real" ]]; then
    checked=$((checked + 1))
    normalize_read_line "$f"
  fi

  claude_file="$dir/CLAUDE.md"
  if [[ ! -f "$claude_file" && ! -L "$claude_file" ]]; then
    if [[ ! -w "$dir" ]]; then
      echo "Aviso: sem permissão para criar: $claude_file" >&2
      skipped=$((skipped + 1))
      continue
    fi
    printf '%s\n' "$read_line" >"$claude_file"
    created=$((created + 1))
  fi
  checked=$((checked + 1))
  normalize_read_line "$claude_file"
done

echo "OK: arquivos checados: $checked; criados: $created; renomeados: $renamed; atualizados: $updated; pulados: $skipped"
