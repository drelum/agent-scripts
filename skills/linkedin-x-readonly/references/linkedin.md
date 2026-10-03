---
read_when: "Ao consultar mensagens, pessoas ou publicações no LinkedIn."
---

# LinkedIn

Prefixo de todos os exemplos: `opencli --profile social`.

```bash
linkedin whoami -f json
linkedin inbox --limit 5 -f json
linkedin thread-snapshot --thread-url "URL_EXATA_DA_THREAD" --max-scrolls 1 -f json
linkedin people-search "CONSULTA" --limit 5 -f json
linkedin profile-read --profile-url "https://www.linkedin.com/in/PERFIL/" -f json
linkedin connections --limit 3 -f json
linkedin timeline --limit 5 -f json
```

Inbox traz prévias e URLs. Para histórico, usar a URL retornada, sem inventar IDs. `snapshot_json` contém as mensagens; extrair apenas o necessário ao pedido. `max-scrolls=1` limita a exploração inicial, sem prometer histórico integral; ampliar se o pedido exigir mensagens antigas, com limite definido.

Em 03/10/2026, São Paulo, OpenCLI 1.8.8: identidade, inbox, uma conversa já lida com oito mensagens, busca de pessoas, perfil público, conexões e feed funcionaram. Cargo encontrado em busca não comprova tese ou intenção de investimento: conferir perfil e fontes institucionais para pesquisas de contatos.

`posts` retornou `EMPTY_RESULT` em dois perfis e `company` falhou na extração de nome em duas empresas. Não afirmar ausência de publicações/empresa; relatar falha do adaptador. Consultar ajuda antes de tentar esses comandos. `search` consta como leitura no catálogo, mas não foi validado nesta exploração.

Sales Navigator não integra esta skill: assinatura e adaptadores ainda não validados. Não recorrer a envio ou convite para descobrir dados.
