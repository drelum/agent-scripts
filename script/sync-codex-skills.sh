#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Sincroniza skills canônicas para o ambiente global do Codex.

Uso:
  ./script/sync-codex-skills.sh [opções]

Opções:
  --source <dir>   Diretório fonte com skills (padrão: ./skills)
  --target <dir>   Diretório destino de skills do Codex (padrão: ~/.agents/skills)
  --dry-run        Mostra ações sem alterar arquivos
  --no-clean       Não remove skills antigas no destino com os mesmos nomes canônicos
  -h, --help       Mostra esta ajuda
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
source_dir="${repo_root}/skills"
target_dir="${HOME}/.agents/skills"
dry_run=0
clean=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      source_dir="$2"
      shift 2
      ;;
    --target)
      target_dir="$2"
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

if [[ ! -d "${source_dir}" ]]; then
  echo "Diretório fonte não existe: ${source_dir}" >&2
  exit 1
fi

run_cmd() {
  if [[ "${dry_run}" -eq 1 ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

declare -A desired=()
while IFS= read -r -d '' skill_file; do
  skill_dir="$(dirname "${skill_file}")"
  skill_name="$(basename "${skill_dir}")"
  desired["${skill_name}"]=1
done < <(find "${source_dir}" -mindepth 2 -maxdepth 2 -name 'SKILL.md' -print0 | sort -z)

if [[ "${#desired[@]}" -eq 0 ]]; then
  echo "Nenhuma skill encontrada em: ${source_dir}" >&2
  exit 1
fi

run_cmd mkdir -p "${target_dir}"

removed=0
if [[ "${clean}" -eq 1 ]]; then
  for skill_name in "${!desired[@]}"; do
    if [[ -e "${target_dir}/${skill_name}" || -L "${target_dir}/${skill_name}" ]]; then
      run_cmd rm -rf "${target_dir:?}/${skill_name}"
      removed=$((removed + 1))
    fi
  done
fi

copied=0
for skill_name in "${!desired[@]}"; do
  run_cmd mkdir -p "${target_dir}/${skill_name}"
  run_cmd cp -R "${source_dir}/${skill_name}/." "${target_dir}/${skill_name}/"
  copied=$((copied + 1))
done

echo "Sincronização concluída."
echo "Fonte: ${source_dir}"
echo "Destino: ${target_dir}"
echo "Skills copiadas/atualizadas: ${copied}"
echo "Skills removidas antes da cópia: ${removed}"
