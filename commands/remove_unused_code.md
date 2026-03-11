---
description: Detecta código não utilizado e sugere remoção com prioridade por impacto/risco
argument-hint: "[opcional: arquivo/pasta/diff; vazio = repo inteiro]"
---

Analise `$ARGUMENTS` (ou o repo inteiro, se vazio) para encontrar código potencialmente não utilizado.
Considere primeiro os trechos/arquivos modificados recentemente, mas sempre compare com a estrutura existente e com arquivos pré-existentes relacionados do projeto para confirmar se algo está realmente sem uso, duplicado ou apenas deslocado.

Objetivo:
- Identificar código morto/não referenciado.
- Priorizar remoções por impacto e risco.
- Propor plano incremental seguro.

Cheque obrigatoriamente:
- Imports não usados
- Funções/classes/exportações sem referência
- Arquivos órfãos
- Feature flags legadas
- Código comentado “temporário” antigo
- Testes obsoletos por funcionalidade removida
- Config/env vars sem uso
- Rotas/endpoints não alcançáveis

Formato de saída:
## Resumo
## Candidatos à remoção (priorizados)
- Item
- Evidência (arquivo/símbolo)
- Confiança (Alta/Média/Baixa)
- Impacto (Alto/Médio/Baixo)
- Risco (Alto/Médio/Baixo)
- Validação antes de remover
- Ação sugerida

## Plano de remoção segura
- Fase 1: baixo risco
- Fase 2: médio risco
- Fase 3: alto impacto

## Testes de regressão recomendados
