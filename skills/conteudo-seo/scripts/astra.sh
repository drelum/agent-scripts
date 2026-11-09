#!/usr/bin/env bash
# Chama o Astra (Codex gpt-6-astra) para pesquisa, texto ou revisão de uma página do site.
#
# Uso:
#   astra.sh [-C <repo>] <pedido.md> <saida.md> [esforço]
#
#   -C <repo>   raiz que o Astra lê; padrão: $ASTRA_REPO ou /home/drelu/Projects/website
#   pedido.md   pedido completo (modelos em ../references/modelos-de-pedido.md)
#   saida.md    resposta final do Astra; o log completo vai para <saida sem .md>.log
#   esforço     model_reasoning_effort: high (padrão), medium, low…
#
# Modo fixo: só leitura (-s read-only), sem aprovação, busca na web ao vivo, sessão efêmera.
# O sandbox só leitura bloqueia rede no shell (curl falha com DNS): links e páginas publicadas
# ficam para Claude conferir; o Astra usa a busca na web própria.
#
# Ex.: astra.sh pbm-1a-pesquisa.md pbm-1a-pesquisa.saida.md
#      astra.sh -C ~/Projects/context pedido.md saida.md medium   (ou ASTRA_REPO=~/Projects/context)
#
# Rodar em segundo plano (Bash com run_in_background): leva de 2 a 15 minutos.
# Acompanhar: tail -n 50 -f <saida sem .md>.log
set -euo pipefail

repo="${ASTRA_REPO:-/home/drelu/Projects/website}"
if [[ "${1:-}" == "-C" ]]; then
  repo="${2:?-C pede o caminho do repositório}"
  shift 2
fi
if [[ $# -lt 2 ]]; then
  sed -n '4,10p' "$0" >&2
  exit 2
fi

pedido="$1"; saida="$2"; esforco="${3:-high}"
log="${saida%.md}.log"
[[ -f "$pedido" ]] || { echo "pedido não encontrado: $pedido" >&2; exit 2; }
[[ -d "$repo" ]] || { echo "repositório não encontrado: $repo" >&2; exit 2; }

if ! codex exec --ephemeral --skip-git-repo-check \
  -C "$repo" \
  -m gpt-6-astra \
  -s read-only \
  -c approval_policy='"never"' \
  -c model_reasoning_effort="\"$esforco\"" \
  -c web_search='"live"' \
  -o "$saida" - < "$pedido" > "$log" 2>&1; then
  echo "falhou: veja tail -n 80 $log" >&2
  exit 1
fi

# Contexto cheio: a compactação falha e a resposta final vira uma saudação genérica.
falhas=$(grep -c "The backend request failed" "$log" || true)
if [[ "$falhas" -gt 0 ]]; then
  echo "aviso: $falhas× \"The backend request failed\" no log; confira se $saida é a entrega (senão, divida o pedido)" >&2
fi
echo "ok: $saida ($(wc -l < "$saida") linhas) · log: $log"
