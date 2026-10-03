---
read_when: "Ao consultar publicações, perfis ou buscas no X."
---

# X / Twitter

Prefixo de todos os exemplos: `opencli --profile social`.

```bash
twitter whoami -f json
twitter search "CONSULTA" --product live --limit 3 -f json
twitter timeline --limit 5 -f json
twitter timeline --type following --limit 5 -f json
twitter thread "https://x.com/USUARIO/status/ID" --limit 3 -f json
```

Confirmar flags na ajuda instalada; `--product live` foi usado na busca validada. A thread aceita a URL exata obtida na busca. Feed algorítmico, following e busca são recortes diferentes, não uma exportação completa.

Em 03/10/2026, São Paulo, OpenCLI 1.8.8: identidade, feed, busca e leitura de um post via thread funcionaram. Carregamento de todas as respostas não foi comprovado. `profile`, `tweets`, `followers`, `following`, `notifications` e `trending` são classificados como leitura no catálogo, mas não foram validados nesta exploração.

Não há mecanismo validado para leitura de DMs individuais do X. `reply-dm` realiza envios em lote e está proibido nesta skill, inclusive para tentar descobrir conversas. Se o pedido depender de DMs, explicar a limitação.
