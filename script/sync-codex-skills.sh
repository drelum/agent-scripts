#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Publica skills canônicas para Codex e Claude por links simbólicos individuais.

Uso:
  ./script/sync-codex-skills.sh [opções]

Opções:
  --source <dir>          Fonte canônica (padrão: ./skills)
  --codex-target <dir>    Destino Codex (padrão: ~/.agents/skills)
  --claude-target <dir>   Destino Claude (padrão: ~/.claude/skills)
  --target <dir>          Modo legado: publica somente no destino Codex informado
  --dry-run               Mostra ações sem alterar arquivos
  --no-clean              Não remove links gerenciados que ficaram obsoletos
  --replace-existing      Remove diretórios reais com nomes canônicos e cria links
  -h, --help              Mostra esta ajuda
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
source_dir="${repo_root}/skills"
codex_target="${HOME}/.agents/skills"
claude_target="${HOME}/.claude/skills"
dry_run=0
clean=1
replace_existing=0
legacy_target=0
explicit_claude_target=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      source_dir="$2"
      shift 2
      ;;
    --codex-target)
      codex_target="$2"
      shift 2
      ;;
    --target)
      codex_target="$2"
      legacy_target=1
      shift 2
      ;;
    --claude-target)
      claude_target="$2"
      explicit_claude_target=1
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --no-clean)
      clean=0
      shift
      ;;
    --replace-existing)
      replace_existing=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Opção inválida: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$source_dir" ]]; then
  echo "Diretório fonte não existe: $source_dir" >&2
  exit 1
fi

source_real="$(realpath "$source_dir")"
declare -A desired=()
while IFS= read -r -d '' skill_file; do
  skill_name="$(basename "$(dirname "$skill_file")")"
  desired["$skill_name"]=1
done < <(find "$source_real" -mindepth 2 -maxdepth 2 -name SKILL.md -print0 | sort -z)

if [[ "${#desired[@]}" -eq 0 ]]; then
  echo "Nenhuma skill encontrada em: $source_real" >&2
  exit 1
fi

if [[ "$source_real" == "$(realpath "${repo_root}/skills")" ]]; then
  "${repo_root}/script/validate-skills"
fi

run_cmd() {
  if [[ "$dry_run" -eq 1 ]]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

managed_target() {
  local link="$1"
  local raw resolved
  raw="$(readlink "$link")"
  if [[ "$raw" = /* ]]; then
    resolved="$(realpath -m "$raw")"
  else
    resolved="$(realpath -m "$(dirname "$link")/$raw")"
  fi
  [[ "$resolved" == "$source_real"/* ]]
}

linked=0
unchanged=0
pruned=0
skipped=0

publish_root() {
  local target_root="$1"
  local skill_name source_skill destination current target_real
  target_real="$(realpath -m "$target_root")"
  if [[ "$target_real" == "$source_real" || "$target_real" == "$source_real"/* ]]; then
    echo "Destino não pode ser igual ou interno à fonte canônica: $target_root" >&2
    return 1
  fi
  run_cmd mkdir -p "$target_root"

  while IFS= read -r skill_name; do
    source_skill="$source_real/$skill_name"
    destination="$target_root/$skill_name"

    if [[ -L "$destination" ]]; then
      current="$(realpath -m "$destination")"
      if [[ "$current" == "$source_skill" ]]; then
        unchanged=$((unchanged + 1))
      elif managed_target "$destination"; then
        run_cmd ln -sfnT "$source_skill" "$destination"
        linked=$((linked + 1))
      else
        echo "Aviso: symlink estrangeiro preservado: $destination -> $(readlink "$destination")" >&2
        skipped=$((skipped + 1))
      fi
    elif [[ -d "$destination" && "$replace_existing" -eq 1 ]]; then
      run_cmd rm -rf "$destination"
      run_cmd ln -s "$source_skill" "$destination"
      linked=$((linked + 1))
    elif [[ -e "$destination" ]]; then
      echo "Aviso: caminho real preservado; não substituído: $destination" >&2
      skipped=$((skipped + 1))
    else
      run_cmd ln -s "$source_skill" "$destination"
      linked=$((linked + 1))
    fi
  done < <(printf '%s\n' "${!desired[@]}" | sort)

  [[ "$clean" -eq 1 ]] || return 0
  [[ -d "$target_root" ]] || return 0
  while IFS= read -r -d '' destination; do
    managed_target "$destination" || continue
    skill_name="$(basename "$destination")"
    [[ -n "${desired[$skill_name]+x}" ]] && continue
    run_cmd rm -f "$destination"
    pruned=$((pruned + 1))
  done < <(find "$target_root" -mindepth 1 -maxdepth 1 -type l -print0)
}

publish_root "$codex_target"
if [[ "$legacy_target" -eq 0 || "$explicit_claude_target" -eq 1 ]]; then
  publish_root "$claude_target"
fi

echo "Publicação concluída."
echo "Fonte: $source_real"
echo "Codex: $codex_target"
if [[ "$legacy_target" -eq 1 && "$explicit_claude_target" -eq 0 ]]; then
  echo "Claude: não publicado (modo legado --target)"
else
  echo "Claude: $claude_target"
fi
echo "Links criados/atualizados: $linked; inalterados: $unchanged; removidos: $pruned; preservados: $skipped"
