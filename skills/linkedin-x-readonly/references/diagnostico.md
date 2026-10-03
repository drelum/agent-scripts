---
read_when: "Quando identidade ou leitura falhar, ou houver dúvida sobre perfil e sessão."
---

# Diagnóstico delimitado

```bash
command -v opencli
opencli --version
opencli profile list
opencli doctor
```

`doctor` não comprova login nos sites. Na versão 1.8.8, já retornou zero com `[FAIL]` e a seleção por `--profile` não resolveu sozinho a ambiguidade de diagnóstico. Conferir texto e perfil padrão, sem trocar padrão automaticamente. Leituras mantêm `--profile social`.

- **AUTH_REQUIRED / logged_in=false:** parar consultas do site; André completa autenticação no Chrome correto.
- **Navigation rejected:** uma repetição da leitura pode testar transitoriedade. Se persistir, uma tentativa com `--site-session persistent` é uma opção oficial de diagnóstico; no laboratório ajudou `whoami` uma vez, sem comprovar solução geral. Se falhar de novo, parar e registrar comando/erro exato, sem payload privado.
- **EMPTY_RESULT:** não confundir com inexistência do conteúdo.
- **COMMAND_EXEC / extração:** relatar operação e erro; não corrigir adaptador ou mudar mecanismo silenciosamente.

Conferir `siteSession` na ajuda: adaptadores podem declarar sessão persistente como padrão, embora o executor geral use sessão efêmera quando não há configuração específica. Sessão persistente mantém a aba de automação e a reutiliza no perfil/site; `--keep-tab false` não desfaz isso na implementação examinada. Executar sequencialmente e preservar abas humanas. `tab list` do navegador não enumera todos os Chromes.

Não habilitar trace por padrão, publicar issues/logs, instalar atualização, extrair cookies, executar scripts de browser ou criar fallback. Traces podem conter dados privados. Um diagnóstico que precise dessas medidas é trabalho separado.

Relatos upstream semelhantes: [#2487](https://github.com/jackwener/OpenCLI/issues/2487) e [#2533](https://github.com/jackwener/OpenCLI/issues/2533). A semelhança não identifica a causa local.
