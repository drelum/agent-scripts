---
read_when: Investigar um erro com sessão e horário conhecidos; reconstruir a gravação em volta do erro e examiná-la com agent-browser.
---

# Laboratório de um erro

Pré-requisito: login do `posthog-cli` com acesso ao projeto, conforme `replay-download.md` (seção Primeiro acesso).
Resolver `<skill>` pela pasta do `SKILL.md`.

Caminho padrão quando se sabe a sessão e o horário do erro (evento PostHog). Uma chamada deixa a gravação
reconstruída para o agente investigar com `agent-browser`:

```bash
python3 <skill>/scripts/replay_lab.py <session-id> --at 2026-10-08T14:43:47.879Z \
  --output /caminho/privado/fora-do-git
```

- `--at`: ISO 8601 (sem fuso = São Paulo) ou epoch em ms. `--window-id`: `$window_id` do evento; sem ele, a
  janela com evento gravado mais próximo do erro (critério registrado no manifesto).
- Download: lista os blocos e busca **lotes de 21** (máximo por requisição com personal key; a cota conta
  requisições, não bytes), com 5 s entre requisições. Sessão de 206 blocos = 11 requisições. Tudo fica em
  `.lotes/` (0600); repetir a chamada ou pedir outro intervalo não faz requisição nova. 429 encerra com o
  `Retry-After` na mensagem; rodar de novo depois retoma do cache.
- `--modo banda`: só os lotes necessários. O primeiro termina no último bloco que começa até o fim do intervalo;
  recua um lote por vez até a janela do erro ter snapshot completo (tipo 2) e Meta (tipo 4) antes do erro.
  Normalmente 2 requisições; outras janelas podem faltar.
- Laboratório: `lab_T<de>_T<ate>.html` + manifesto `.json`, intervalo padrão `--de -300 --ate 120`. A sessão
  inteira no player chegou a 526 MB; o intervalo fica em 5–30 MB. Cada janela começa no Meta anterior ao último
  snapshot completo até `de`: começar num evento incremental deixa a tela vazia.
- `LEIA-ME.md` traz os comandos. API na página: `lab.info()` (erro, janelas no laboratório e na sessão, lacunas,
  cobertura), `lab.ir(s)`, `lab.tocar(de, ate)`, `lab.linha(de, ate)` (cliques com rótulo, rotas, visibilidade),
  `lab.janela(id)`, `lab.estado()`. `agent-browser snapshot` lê o DOM gravado dentro do player.
- `lab.ir` reproduz 2 s reais antes do alvo: com salto direto, animações CSS (gavetas, modais) ficam congeladas na
  posição inicial e o screenshot não corresponde ao DOM. A faixa no topo mostra `T±s` e fica vermelha quando a
  tela não é do instante pedido (fim da gravação, lacuna, pedido fora do trecho).
- `cobertura_erro.sem_gravacao_no_erro`: nenhum evento da janela até 30 s antes e depois do erro. Visto em
  08/10/2026: a janela parou de gravar 136 s antes do erro, com analytics ativo até depois dele; a sessão
  seguiu em outra janela. Baixar mais não resolve; declarar e cruzar com os eventos.

## Verificação

```bash
python3 -m unittest discover -s <skill>/scripts -p 'replay_*test.py' -v
```

Validado em 09/10/2026 com três sessões reais (12, 142 e 206 blocos): 2, 8 e 11 requisições na primeira montagem
e 0 nas seguintes; instante do erro conferido por screenshot. Para amostras de jornada sem erro de referência,
usar `replay_download.py` e `replay-analysis.md`.
