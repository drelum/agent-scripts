# Correlação e ticket

Read when: investigar incidente completo, priorizar backlog ou redigir ticket.

1. Registre início/fim em São Paulo e equivalente UTC, projetos/serviços/revisões e hosts. Backend, frontend, enriquecimento/cotação e Sync são fontes separadas. Revalide a janela ao responder situação atual.
2. No Cloud Logging, filtre serviço, endpoint, status e período. Busque erro de aplicação e request correspondente; preserve trace/request ID. Conte tentativas deduplicadas, não linhas. Registre limite/paginação. Não baixar payload completo por padrão.
3. No PostHog, confirme schema de eventos e propriedades. Consulte `$exception` e eventos de falha de negócio realmente existentes. Projete UUID do evento, horário, erro, `$session_id`, identidade necessária, rota, release/chunk e IDs de domínio. Evite `properties` inteiro: URLs podem conter JWT. Confira resolução de stack por frame/release; upload novo não resolve bundle antigo automaticamente.
4. Una `$session_id` a metadados de gravação. Não inferir identidade pela sessão: conferir person/distinct ID e cadastro. Verificar loja/CNPJ selecionado no momento, inclusive troca de loja durante sessão. Número de pedido vem da entidade persistida, não de ID de carrinho. Falha anterior ao commit pode não ter criado pedido.
5. Descubra schemas MySQL/ClickHouse antes de consultar. Ligue IDs de carrinho, cotação, item, pedido, tarefa e loja no grão correto. Cheque persistência, rollback, envio e confirmação; HTTP 200, fila publicada ou tarefa SUCCEEDED não provam completude. Para Sync, medir última informação persistida e cobertura por domínio/loja. Não usar o warehouse como prova de causa sem chave/semântica de junção verificada.
6. Revise gravações disponíveis com [replay.md](replay.md). Separe rede do browser, console, exceção do SDK e log do servidor. Proximidade de tempo/revisão é correlação, não causalidade; sem trace/ID compartilhado, atribuir confiança e dizer o que falta.
7. Priorize bloqueio de checkout, pedidos com persistência/envio incorretos e dados de estoque/vendas/cotações ausentes ou defasados. Depois, alcance de lojas/pessoas e persistência/recência. Distinguir falha funcional, erro recuperado após retry e ruído. Atribuir P0/P1/P2 conforme política atual do time, sem prioridade deduzida apenas do volume.

## Registro por incidente

| Campo | Conteúdo |
|---|---|
| Janela/ambiente | Corte, timezone, host, serviço/revisão |
| Sintoma e impacto | Ação da loja, resultado observado, persistência confirmada |
| Ocorrências | Eventos únicos, tentativas, usuários, lojas e pedidos em colunas distintas |
| Associações | Identificador necessário + fonte + confiança + chave de junção |
| Evidências | Erro/stack sanitizado, request/trace, consulta, replay com instante |
| Cobertura | Limites, truncamento, fonte inacessível, replay ausente/incompleto |
| Diagnóstico | Fatos, hipótese, evidência faltante; não misturar |

## Ticket conciso

Título: `<fluxo>: <falha observável> impede <resultado de negócio>`.

```markdown
Ao [ação], [resultado observado]. Impacto: [confirmado, janela e alcance]; [lacuna].

Evidências:
- [horário São Paulo, erro e request/trace; link da fonte]
- [usuário/loja/pedido necessário, fonte e confiança]
- [gravação no instante relevante; trecho antes/depois e resultado observado]

Diagnóstico: [causa sustentada ou hipótese claramente nomeada].

Aceite: [fluxo conclui corretamente e persistência/confirmacão conferidas no caso afetado].
```

Usar AITRUS-450 como referência de contexto e links, não como regra geral de causa ou responsável. Buscar duplicatas antes de publicar. Quando publicação estiver autorizada, confirmar time, prioridade, responsável e conteúdo exatos; reler ticket publicado e atribuição. Não publicar dados pessoais desnecessários nem artefatos brutos de replay.
