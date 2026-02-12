#!/usr/bin/env bash
set -euo pipefail

# Script: setup-codex-wsl-title.sh
# Uso:
#   bash script/setup-codex-wsl-title.sh
#   source ~/.bashrc
#
# Objetivo:
# - No WSL, ao rodar "codex", mudar o título da aba para o nome da pasta atual.
#
# O que este script altera:
# 1) ~/.bashrc
#    - Remove alias antigo do codex (se existir).
#    - Escreve bloco gerenciado com função "codex":
#      - envia OSC 2 + OSC 0 para atualizar título da aba;
#      - chama o binário real do codex com
#        --dangerously-bypass-approvals-and-sandbox;
#      - cria alias opcional "codecs".
# 2) Windows Terminal settings.json
#    - Garante "profiles.defaults.suppressApplicationTitle": false
#      para permitir que o terminal aceite título vindo da aplicação.
#
# Segurança:
# - Cria backups com timestamp antes de alterar ~/.bashrc e settings.json.
# - Idempotente para o bloco gerenciado no ~/.bashrc.

BASHRC="${HOME}/.bashrc"
WT_CFG="/mnt/c/Users/${USER}/AppData/Local/Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json"
START_MARK="# >>> codex-title-wrapper >>>"
END_MARK="# <<< codex-title-wrapper <<<"

if [[ ! -f "${BASHRC}" ]]; then
  echo "Erro: ~/.bashrc não encontrado em ${BASHRC}" >&2
  exit 1
fi

cp "${BASHRC}" "${BASHRC}.bak_codex_title_$(date +%Y%m%d_%H%M%S)"

# Remove alias antigo comum, se existir.
sed -i '/^alias codex="codex --dangerously-bypass-approvals-and-sandbox"$/d' "${BASHRC}"

# Remove bloco gerenciado anterior, se existir.
awk -v s="${START_MARK}" -v e="${END_MARK}" '
  $0==s {skip=1; next}
  $0==e {skip=0; next}
  skip!=1 {print}
' "${BASHRC}" > "${BASHRC}.tmp"
mv "${BASHRC}.tmp" "${BASHRC}"

cat >> "${BASHRC}" <<'BASH_EOF'

# >>> codex-title-wrapper >>>
# Wrapper do Codex para WSL/Windows Terminal.
# Define título da guia com o nome da pasta atual antes de iniciar o Codex.
codex() {
  local pasta codex_bin
  pasta="${PWD##*/}"

  # OSC 2 + OSC 0 para maior compatibilidade de terminal.
  printf '\033]2;%s\007\033]0;%s\007' "$pasta" "$pasta"

  codex_bin="$(type -P codex)"
  if [[ -z "${codex_bin}" ]]; then
    echo "codex não encontrado no PATH" >&2
    return 127
  fi

  "${codex_bin}" --dangerously-bypass-approvals-and-sandbox "$@"
}

# Atalho opcional para erro de digitação comum.
alias codecs='codex'
# <<< codex-title-wrapper <<<
BASH_EOF

if [[ -f "${WT_CFG}" ]]; then
  cp "${WT_CFG}" "${WT_CFG}.bak_codex_title_$(date +%Y%m%d_%H%M%S)"

  if ! rg -q '"suppressApplicationTitle"\s*:\s*false' "${WT_CFG}"; then
    perl -0pi -e 's/"profiles"\s*:\s*\{\s*"defaults"\s*:\s*\{\s*\},/"profiles": {\n        "defaults": {\n            "suppressApplicationTitle": false\n        },/s' "${WT_CFG}"
  fi

  echo "Windows Terminal: suppressApplicationTitle=false (ok)"
else
  echo "Aviso: settings.json do Windows Terminal não encontrado em ${WT_CFG}."
  echo "Se estiver em outro usuário Windows, ajuste o caminho no script."
fi

echo "Concluído."
echo "Próximos passos:"
echo "1) Fechar e reabrir o Windows Terminal"
echo "2) Rodar: source ~/.bashrc"
echo "3) Entrar em uma pasta e executar: codex"
