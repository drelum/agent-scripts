#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -gt 0 ]]; then
  echo "Uso: ./script/sync-agent-environment.sh" >&2
  exit 1
fi

echo "[1/2] Publicando skills para Codex e Claude..."
"${script_dir}/sync-codex-skills.sh"

echo
echo "[2/2] Propagando diretivas globais e ponteiros dos projetos..."
"${script_dir}/ensure_agent_std.sh"

echo
echo "Ambiente de agentes sincronizado com sucesso."
