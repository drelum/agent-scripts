---
read_when: Analisar gravações rrweb já baixadas, preparar evidências de jornada e capturar trechos locais.
---

# Análise local de gravações

Para investigar um erro com horário conhecido, usar `replay-lab.md`: o laboratório tem relógio relativo ao erro. Os auxiliares abaixo usam tempo relativo à janela escolhida, outro relógio. Para obter a gravação a partir do PostHog, começar por `replay-download.md`. Os auxiliares desta etapa não usam dependências Python externas, credenciais ou chamadas à aplicação/PostHog. `frame` recebe a pasta gerada pelo downloader, com `reproducao.html`. `analyze` recebe uma amostra enriquecida com `index.json`, `analytics-events.json` e `<session-id>/events.json` (objeto janela → lista rrweb); o downloader sozinho não cria o índice/analytics dessa amostra. A saída é evidência, não classificação automática de intenção ou emoção.

Resolver `<skill>` pela pasta do `SKILL.md`, inclusive em outro clone/máquina.

```bash
python3 <skill>/scripts/replay_evidence.py analyze \
  /caminho/amostra --output /caminho/amostra/analise-nova

python3 <skill>/scripts/replay_evidence.py frame \
  /caminho/amostra/session-id --at 1057 --browser-session replay-investigacao \
  --window-id '<window-id-do-manifesto>' --output /caminho/amostra/frame-1057.png

agent-browser --session replay-investigacao close
```

`analyze`: processa todas as janelas; liga cliques a controles do DOM após snapshots/mutações; registra mudanças de visibilidade e contagens de inputs sem seus valores; lista repetições rápidas sem chamá-las de rage clicks; mantém analytics separado e marca eventos fora dos limites visuais. `location_snapshot` é uma localização capturada, não necessariamente uma navegação naquele instante. Não confundir `input_updates` com teclas humanas.

`frame`: usa o `reproducao.html` já existente e a CLI global `agent-browser`. Viewport antes de montar o player; reproduz dois segundos antes do ponto solicitado e pausa. Emite PNG e JSON de conferência, com tempo real, diálogos na área visível, botão de finalizar e mensagem de bloqueio. Selecionar `--window-id` pelo manifesto; sem essa opção usa a primeira janela. Tempo de `--at` relativo à janela selecionada, não ao início global da sessão. Interseção/opacidade não excluem oclusão; conferir a imagem. Não altera o DOM gravado nem executa scripts da aplicação.

Arquivos novos 0600; diretório novo 0700; não sobrescreve destinos. Não exporta payloads, URLs cruas, valores de inputs ou propriedades completas. Redação de rótulos é uma proteção adicional, não substitui sanitizar a entrada.

## Protocolo de interpretação

1. Conferir cobertura, janela, versão da aplicação e identidade. Listas limitadas/paginadas não são o universo; perfil atual não prova vínculo histórico.
2. Distinguir evidências de **objetivo** (importar lista, contexto de compra, comparação), **etapa** (consulta, seleção, carrinho), **impedimento** (mensagem/botão desabilitado/erro) e **resultado** (sucesso + pedido identificado).
3. Identificar checkpoints pelas ações semânticas. Rever antes/depois do bloqueio; DOM bruto não prova que algo estava na tela.
4. Usar relógio relativo de cada fonte. Não ajustar todos os eventos por um offset único sem validar pares de referência.
5. Escrever fato, hipótese, confiança e evidência faltante. Sem clique não comprova leitura; ausência de sucesso não comprova desistência; duração não é tempo de esforço; ausência de erro não comprova experiência boa.
6. Propor solução ligada ao bloqueio demonstrado e um critério verificável de melhoria. Mudança no produto exige tarefa própria.

## Eventos úteis verificados em 07/10/2026

- Objetivo/entrada: `purchase_context_resolved`, `quote_bulk_searched`, `quote_products_searched`, `quote_search_succeeded`, `offer_clicked`, `store_context_changed`.
- Exploração/decisão: `assortment_filter_applied`, `assortment_sorted`, `assortment_molecule_view_opened`, `purchase_suggestion_explanation_opened`, `quote_item_selected`.
- Compra: `cart_item_added`, `cart_checkout_started`, `cart_checkout_succeeded`, `cart_checkout_failed`, `cart_item_add_failed`.
- Bloqueio/recuperação: `cart_minimum_helper_opened` (`level`, `gap_amount`), `cart_minimum_helper_minimum_reached` (`level`, `items_added`), `cart_review_exited` (`open_duration_s`, `has_blocking_errors`, totais), `cart_condition_removed`, `cart_cleared`.
- Sinais complementares: `$pageview`, `$dead_click`, `$exception`. `$rageclick` não observado nos trinta dias da descoberta.

A taxonomia cobre versões diferentes. A sessão 9 usou `app_version=1307c42` e não registrou `minimum_reached`, `review_exited` ou `quote_search_succeeded` na janela consultada. Não presumir que o caminho estava instrumentado. `cart_checkout_started` pode representar abertura/revisão do carrinho, não clique em Finalizar. `offer_quote_sent` não é pedido enviado.

Para a próxima consulta: descobrir esquema novamente por `posthog-cli api`; selecionar propriedades necessárias. **Nunca selecionar `properties` inteiro**, pois há `token` nas super-propriedades. Limites de datas com timezone explícito; apresentar São Paulo.

## Verificação

```bash
python3 -m unittest discover -s <skill>/scripts -p 'replay_*test.py' -v
```

Piloto da amostra de dez sessões: 8,176 segundos para preparar as evidências locais, excluindo download, frames e interpretação. Captura de frame da sessão 9 conferida com o carrinho e Finalizar desabilitado. Esses tempos são medições de um piloto, não SLA.
