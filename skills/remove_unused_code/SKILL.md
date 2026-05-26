# Remove Unused Code

Use when the user asks to detect unused code, unused exports, orphan files, dead config, or candidates for safe removal.

Analise o escopo indicado pelo usuário, ou o repo inteiro se nenhum escopo for informado, para encontrar código potencialmente não utilizado.
Considere primeiro trechos/arquivos modificados recentemente, mas compare com a estrutura existente e arquivos relacionados para confirmar se algo está realmente sem uso, duplicado ou apenas deslocado.

Objetivo:
- Identificar código morto/não referenciado.
- Priorizar remoções por impacto e risco.
- Propor plano incremental seguro.

Cheque obrigatoriamente:
- Imports não usados.
- Funções/classes/exportações sem referência.
- Arquivos órfãos.
- Feature flags legadas.
- Código comentado temporário antigo.
- Testes obsoletos por funcionalidade removida.
- Config/env vars sem uso.
- Rotas/endpoints não alcançáveis.

Formato de saída:

## Resumo

## Candidatos à remoção
Para cada item:
- Item
- Evidência: arquivo/símbolo
- Confiança: Alta | Média | Baixa
- Impacto: Alto | Médio | Baixo
- Risco: Alto | Médio | Baixo
- Validação antes de remover
- Ação sugerida

## Plano de remoção segura
- Fase 1: baixo risco
- Fase 2: médio risco
- Fase 3: alto impacto

## Testes de regressão recomendados
