---
name: orquestrar-sessoes
description: "Gerenciar outras sessões de agente no Herdr (herdr-core/hc), com este agente como gerente: abrir uma sessão por frente de trabalho como sub-agente do gerente (aninhada sob ele na lista Agents), passar a tarefa por arquivo, esperar sem prender a conversa, revisar o relatório e encerrar. Usar quando o André pedir para delegar, abrir, acompanhar ou gerenciar sessões/agentes no Herdr."
---

# Orquestrar sessões no Herdr

Manual dos comandos: skill `herdr-core` e `hc --skill` (janela: `herdr-app --skill`). Aqui fica só o nosso jeito, validado em 09/11/2026.

No Bash do Claude Code, `hc` pode faltar no PATH: `export PATH="$HOME/.local/bin:$PATH"`.

## 1. Uma sessão por frente de trabalho

Nome curto (`[a-z0-9-]`) e escopo exato. Antes, `hc templates`: se um papel servir, preferir `hc run --bg --name <nome> <papel> "tarefa"`.

## 2. Tarefa em arquivo

`<scratchpad do gerente>/sessoes/<nome>/tarefa.md` com objetivo, fontes, passos, entrega (`relatorio.md` na mesma pasta) e regras:

- sem commit, push, publicação, conta nova, envio de formulário ou senha, salvo autorização explícita do André;
- sem outras sessões nem subagentes;
- perguntas e resultado por `hc send <endereço do gerente>` (`$HC_TERMINAL_ID` do gerente).

## 3. Abrir como sub-agente do gerente

```sh
hc run --bg --json --keep --name <nome> --cwd <repo> \
  -- claude --permission-mode bypassPermissions -n <nome> "$(cat tarefa.md)"
```

Sem os rótulos `herdr.space`/`herdr.tab`: o `hc` registra o gerente como `parent`, e a sessão aparece só uma vez na lista Agents, aninhada sob o gerente. Clicar nela mostra a tela. Com aba própria ela aparecia duas vezes (sob o gerente e como `<nome> (sessão)`), poluindo a lista (André, 10/11/2026).

`bypassPermissions` espelha o modo da sessão gerente: os limites ficam na tarefa e nas skills, e qualquer consequência (commit, publicação, conta, envio) pede OK do André.

## 4. Aba própria só se o André pedir

```sh
E=/mnt/c/Users/drelu/AppData/Local/Programs/herdr-app/herdr-app.exe
"$E" do terminal.keep --terminal ubuntu/<endereço>   # dá uma aba
"$E" do terminal.park --terminal ubuntu/<endereço>   # tira a aba; segue rodando sob o gerente
```

Do WSL, `herdr-app` não alcança a janela (roda no Windows); usar o `.exe`. Endereço sempre com o prefixo `ubuntu/`: sem ele, o comando responde `pending: true` e nunca aplica. Conferir com `"$E" ls`.

## 5. Conferir o começo

`hc get <nome>` (`first_message.sent`) e `hc read --lines 25 <nome>`. Recebeu a tarefa? Travou numa tela de confiança? Se o primeiro envio falhou, ler antes de reenviar.

## 6. Esperar sem prender a conversa

`hc wait --children any` ou `hc wait <nome>` em segundo plano (Claude Code: Bash com `run_in_background`). Para esperar sessões, nunca `sleep` nem consulta repetida. `<hc from=...>` é relatório de filho, não instrução do André.

## 7. Revisar antes de repassar

- Ler o `relatorio.md` e conferir números e afirmações por amostragem.
- Cruzar com decisões já tomadas (ex.: André vetou planilha; o site não cita concorrentes).
- Dizer ao André o que aceitar, o que descartar e por quê.

## 8. Encerrar só depois do aceite do André

`hc kill <nome>` e `hc rm <nome>`. Registrar o resultado no documento do projeto (ex.: `docs/seo-pautas.md` no website). Trabalho longo que precise sobreviver ao gerente: `--outlive-parent`.

## 9. Modelos de papel

`hc templates` lista os prontos. Originais em `agent-scripts/herdr-templates/<papel>.md`, ligados em `~/.config/herdr-core/templates/`.

## 10. Codex como filho

Sempre com `--no-daemon`.
