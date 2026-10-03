# Paths do Windows no Herdr

Abre no app padrão do Windows (via `explorer.exe`; pastas no Explorer) paths mostrados nos panes do Herdr:

- **Clique** em link `file://` (hyperlink OSC 8 ou URI em texto puro). O Herdr só entrega URLs ao plugin; path Windows ou relativo em texto puro não vira link.
- **Seleção** → botão direito → **Abrir no Windows**. Aceita path Windows (`C:\...`, `\\wsl.localhost\...`), Linux absoluto, `~/...` ou relativo ao cwd do pane; remove molduras equilibradas de crases, aspas e parênteses, preservando pontuação e espaços do nome. O nome literal existente tem precedência. Path Linux inexistente não abre (ver log).

Caso do Codex: ele reescreve links `file://` como `texto (path/relativo)`, então o clique não funciona; selecionar o path relativo resolve.

`AGENTS.md` manda os agentes mostrarem o path Windows (`wslpath -w`) em crases e o URI `file://` em linha própria.

Herdr 0.9.0 ou superior, WSL, Python 3. Sem dependências externas.

```bash
herdr plugin link /home/drelu/Projects/agent-scripts/herdr-windows-paths
herdr plugin log list   # conferir execuções
herdr plugin unlink andre.windows-paths
```
