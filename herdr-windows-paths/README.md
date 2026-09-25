# Paths do Windows no Herdr

Abre no app padrão do Windows (via `explorer.exe`; pastas no Explorer) os hyperlinks `file://` clicados nos panes do Herdr.

O Herdr só entrega ao plugin URLs: hyperlink OSC 8 ou `file://...` em texto puro. Path Windows em texto puro (`C:\...`, `\\wsl.localhost\...`) não é detectado. Por isso `AGENTS.md` manda os agentes mostrarem paths como link markdown — texto = path Windows (`wslpath -w`), destino = `file://` —; funciona tanto renderizado como OSC 8 quanto com o URI visível.

URIs aceitos: `file://wsl.localhost/Ubuntu/...`, `file:///C:/...`, `file:///home/...` (convertido com `wslpath -w`).

Herdr 0.9.0 ou superior, WSL, Python 3. Sem dependências externas.

```bash
herdr plugin link /home/drelu/Projects/agent-scripts/herdr-windows-paths
herdr plugin log list   # conferir execuções do clique
herdr plugin unlink andre.windows-paths
```
