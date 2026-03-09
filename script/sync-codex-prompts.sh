#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Sincroniza comandos slash canônicos para o ambiente global do Codex.

Uso:
  ./script/sync-codex-prompts.sh [opções]

Opções:
  --source <dir>   Diretório fonte com arquivos .md (padrão: ./commands)
  --target <dir>   Diretório destino de prompts do Codex (padrão: $CODEX_HOME/prompts ou ~/.codex/prompts)
  --dry-run        Mostra ações sem alterar arquivos
  --no-clean       Não remove arquivos antigos no destino
  -h, --help       Mostra esta ajuda
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
source_dir="${repo_root}/commands"
codex_home="${CODEX_HOME:-${HOME}/.codex}"
target_dir="${codex_home}/prompts"
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

normalize_name() {
  local input="$1"
  local name
  name="$(printf '%s' "${input}" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's#/#-#g; s/[[:space:]]+/-/g; s/[^a-z0-9._-]+/-/g; s/-+/-/g; s/^-+//; s/-+$//')"
  printf '%s' "${name}"
}

duplicate_canonical_name() {
  local file_name="$1"
  local candidate=""

  if [[ "${file_name}" =~ ^(.+)[[:space:]_-][0-9]+\.md$ ]]; then
    candidate="${BASH_REMATCH[1]}.md"
  elif [[ "${file_name}" =~ ^(.+)[[:space:]]\([0-9]+\)\.md$ ]]; then
    candidate="${BASH_REMATCH[1]}.md"
  elif [[ "${file_name}" =~ ^(.+)[[:space:]]copy([[:space:]][0-9]+)?\.md$ ]]; then
    candidate="${BASH_REMATCH[1]}.md"
  elif [[ "${file_name}" =~ ^(.+)\.md\.[0-9]+$ ]]; then
    candidate="${BASH_REMATCH[1]}.md"
  fi

  printf '%s' "${candidate}"
}

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

declare -A desired=()
while IFS= read -r -d '' file; do
  rel_path="${file#${source_dir}/}"
  rel_no_ext="${rel_path%.md}"
  normalized="$(normalize_name "${rel_no_ext}")"
  if [[ -z "${normalized}" ]]; then
    echo "Falha ao normalizar nome: ${rel_path}" >&2
    exit 1
  fi
  if [[ -n "${desired[${normalized}]+x}" ]]; then
    echo "Colisão de nomes após normalização: ${rel_path} => ${normalized}.md" >&2
    exit 1
  fi
  desired["${normalized}"]=1
  cp "${file}" "${tmp_dir}/${normalized}.md"
done < <(find "${source_dir}" -type f -name '*.md' -print0 | sort -z)

if [[ "${#desired[@]}" -eq 0 ]]; then
  echo "Nenhum comando encontrado em: ${source_dir}" >&2
  exit 1
fi

run_cmd mkdir -p "${target_dir}"

removed_duplicates=0
while IFS= read -r -d '' file; do
  base_name="$(basename "${file}")"
  canonical="$(duplicate_canonical_name "${base_name}")"
  if [[ -z "${canonical}" ]]; then
    continue
  fi
  canonical_key="${canonical%.md}"
  if [[ -n "${desired[${canonical_key}]+x}" || -f "${target_dir}/${canonical}" ]]; then
    run_cmd rm -f "${file}"
    removed_duplicates=$((removed_duplicates + 1))
  fi
done < <(find "${target_dir}" -maxdepth 1 -type f \( -name '*.md' -o -name '*.md.*' \) -print0)

removed_stale=0
if [[ "${clean}" -eq 1 ]]; then
  while IFS= read -r -d '' file; do
    base_name="$(basename "${file}")"
    key="${base_name%.md}"
    if [[ -z "${desired[${key}]+x}" ]]; then
      run_cmd rm -f "${file}"
      removed_stale=$((removed_stale + 1))
    fi
  done < <(find "${target_dir}" -maxdepth 1 -type f -name '*.md' -print0)
fi

copied=0
while IFS= read -r -d '' file; do
  run_cmd cp "${file}" "${target_dir}/$(basename "${file}")"
  copied=$((copied + 1))
done < <(find "${tmp_dir}" -maxdepth 1 -type f -name '*.md' -print0 | sort -z)

echo "Sincronização concluída."
echo "Fonte: ${source_dir}"
echo "Destino: ${target_dir}"
echo "Copiados/atualizados: ${copied}"
echo "Removidos por duplicação: ${removed_duplicates}"
echo "Removidos por limpeza: ${removed_stale}"
