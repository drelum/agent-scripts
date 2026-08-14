#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Publica custom agents canônicos do Codex como cópias gerenciadas.

Uso:
  ./script/sync-codex-agents.sh [opções]

Opções:
  --source <dir>       Fonte canônica (padrão: ./agents/codex)
  --target <dir>       Destino Codex (padrão: ~/.codex/agents)
  --dry-run            Mostra ações sem alterar arquivos
  --no-clean           Não remove cópias gerenciadas que ficaram obsoletas
  --replace-existing   Substitui arquivos ou links estrangeiros com nomes canônicos
  -h, --help           Mostra esta ajuda
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
source_dir="${repo_root}/agents/codex"
target_dir="${HOME}/.codex/agents"
state_name=".agent-scripts-managed"
dry_run=0
clean=1
replace_existing=0

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
target_real="$(realpath -m "$target_dir")"
if [[ "$target_real" == "$source_real" || "$target_real" == "$source_real"/* ]]; then
  echo "Destino não pode ser igual ou interno à fonte canônica: $target_dir" >&2
  exit 1
fi

declare -A desired_hash=()
while IFS= read -r -d '' agent_file; do
  agent_name="$(basename "$agent_file")"
  if [[ ! "$agent_name" =~ ^[a-zA-Z0-9_-]+\.toml$ ]]; then
    echo "Nome inválido de custom agent: $agent_name" >&2
    exit 1
  fi
  desired_hash["$agent_name"]="$(sha256sum "$agent_file" | cut -d ' ' -f 1)"
done < <(find "$source_real" -mindepth 1 -maxdepth 1 -type f -name '*.toml' -print0 | sort -z)

if [[ "${#desired_hash[@]}" -eq 0 ]]; then
  echo "Nenhum custom agent encontrado em: $source_real" >&2
  exit 1
fi

declare -A previous_hash=()
state_file="$target_dir/$state_name"
if [[ -f "$state_file" ]]; then
  while read -r hash agent_name; do
    [[ "$hash" =~ ^[0-9a-f]{64}$ ]] || continue
    [[ "$agent_name" =~ ^[a-zA-Z0-9_-]+\.toml$ ]] || continue
    previous_hash["$agent_name"]="$hash"
  done <"$state_file"
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

source_symlink() {
  local link="$1"
  local resolved
  resolved="$(realpath -m "$link")"
  [[ "$resolved" == "$source_real"/* ]]
}

copied=0
updated=0
unchanged=0
pruned=0
preserved=0
declare -A managed_hash=()

run_cmd mkdir -p "$target_dir"

while IFS= read -r agent_name; do
  [[ -n "$agent_name" ]] || continue
  source_agent="$source_real/$agent_name"
  destination="$target_dir/$agent_name"
  expected_hash="${desired_hash[$agent_name]}"
  publish=0

  if [[ -L "$destination" ]]; then
    if source_symlink "$destination" || [[ "$replace_existing" -eq 1 ]]; then
      run_cmd rm -f "$destination"
      publish=1
    else
      echo "Aviso: symlink estrangeiro preservado: $destination -> $(readlink "$destination")" >&2
      preserved=$((preserved + 1))
    fi
  elif [[ -f "$destination" ]]; then
    current_hash="$(sha256sum "$destination" | cut -d ' ' -f 1)"
    if [[ -n "${previous_hash[$agent_name]+x}" && "$current_hash" == "${previous_hash[$agent_name]}" ]]; then
      if [[ "$current_hash" == "$expected_hash" ]]; then
        unchanged=$((unchanged + 1))
        managed_hash["$agent_name"]="$expected_hash"
      else
        publish=1
      fi
    elif [[ "$replace_existing" -eq 1 ]]; then
      publish=1
    else
      echo "Aviso: arquivo estrangeiro ou alterado preservado: $destination" >&2
      preserved=$((preserved + 1))
    fi
  elif [[ -e "$destination" ]]; then
    echo "Aviso: caminho não regular preservado: $destination" >&2
    preserved=$((preserved + 1))
  else
    publish=1
  fi

  if [[ "$publish" -eq 1 ]]; then
    existed=0
    [[ -e "$destination" ]] && existed=1
    run_cmd cp "$source_agent" "$destination"
    if [[ "$existed" -eq 1 ]]; then
      updated=$((updated + 1))
    else
      copied=$((copied + 1))
    fi
    managed_hash["$agent_name"]="$expected_hash"
  fi
done < <(printf '%s\n' "${!desired_hash[@]}" | sort)

while IFS= read -r agent_name; do
  [[ -n "$agent_name" ]] || continue
  [[ -n "${desired_hash[$agent_name]+x}" ]] && continue
  destination="$target_dir/$agent_name"
  if [[ "$clean" -eq 0 ]]; then
    managed_hash["$agent_name"]="${previous_hash[$agent_name]}"
    continue
  fi
  if [[ -f "$destination" && ! -L "$destination" ]]; then
    current_hash="$(sha256sum "$destination" | cut -d ' ' -f 1)"
    if [[ "$current_hash" == "${previous_hash[$agent_name]}" ]]; then
      run_cmd rm -f "$destination"
      pruned=$((pruned + 1))
    else
      echo "Aviso: cópia gerenciada alterada foi preservada: $destination" >&2
      preserved=$((preserved + 1))
    fi
  fi
done < <(printf '%s\n' "${!previous_hash[@]}" | sort)

if [[ "$dry_run" -eq 0 ]]; then
  temp_state="$(mktemp "$target_dir/${state_name}.XXXXXX")"
  while IFS= read -r agent_name; do
    [[ -n "$agent_name" ]] || continue
    printf '%s %s\n' "${managed_hash[$agent_name]}" "$agent_name"
  done < <(printf '%s\n' "${!managed_hash[@]}" | sort) >"$temp_state"
  mv "$temp_state" "$state_file"
fi

echo "Publicação de custom agents concluída."
echo "Fonte: $source_real"
echo "Codex: $target_dir"
echo "Copiados: $copied; atualizados: $updated; inalterados: $unchanged; removidos: $pruned; preservados: $preserved"
