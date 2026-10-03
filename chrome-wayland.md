# Chrome Linux com Wayland

O launcher `bin/google-chrome-wayland` inicia o Chrome com
`--ozone-platform=wayland` e preserva os argumentos recebidos.

Instalação local: `~/.local/bin/google-chrome` e
`~/.local/bin/google-chrome-stable` apontam para esse launcher.
O atalho `~/.local/share/applications/google-chrome.desktop` aponta para
`chrome-wayland.desktop`, uma cópia do atalho oficial com Wayland nas três
ações: abrir, nova janela e janela anônima.

Após configurar, fechar todas as janelas do Chrome Linux e abrir novamente.
Conferir `--ozone-platform=wayland` na linha de comando em `chrome://version`.
Uma chamada direta a `/usr/bin/google-chrome-stable` ignora o launcher local.
