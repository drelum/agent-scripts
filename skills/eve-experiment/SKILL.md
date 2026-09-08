---
name: eve-experiment
description: Planejar e executar ciclos medidos de melhoria de agentes EVE, do baseline à decisão sobre uma hipótese, reutilizando gates, deployments e evidências. Usar para otimizar prompts, tools, instruções, modelos ou trajetórias com baterias locais ou em Production; usar eve-isolated-evals sozinho quando o pedido for apenas isolamento mecânico de uma bateria já definida.
---

# Eve Experiment

Coordene o experimento; delegue o isolamento da execução à skill `eve-isolated-evals` e aos comandos
canônicos do projeto. Não recrie runners já existentes no repositório, no Eve ou em `~/Projects/eve-kit`.

## Contrato do experimento

Antes de alterar o agente, fixe no thread ou no artefato canônico do projeto:

- objetivo e hipótese testável;
- baseline e métrica primária;
- dataset/casos, ambiente, modelo, concorrência e deployment;
- quais arquivos podem mudar e se a execução pode persistir ou publicar dados.

Descubra valores já disponíveis; não faça perguntas redundantes. Antes da primeira execução, informe em
texto curto: `fase`, `local|Production`, `deployment`, `modelo`, `concorrência` e `persistência`.

## Ciclo

1. Reuse resultados, artefatos e deployments compatíveis já existentes.
2. Trabalhe uma hipótese por vez. Faça a menor alteração capaz de testá-la.
3. Durante a iteração, rode somente testes e checks focados no comportamento alterado.
4. Trate `commit + diff local + configuração relevante + dataset` como o estado da execução. Registre o
   estado junto do resultado.
5. Rode no máximo um gate completo para o mesmo estado. Se ele já passou, reutilize o resultado.
6. Faça build/deploy somente quando o estado relevante mudou. Falha de infraestrutura externa não invalida
   gate ou build aprovado e não justifica novo deploy do mesmo artefato.
7. Para local limpo, use `eve-eval-isolated`. Para Production, use `eve-eval-remote-production`, identidade
   efêmera e deployment fixado conforme `eve-isolated-evals`.
8. Compare contra o baseline; classifique a hipótese como confirmada, rejeitada ou inconclusiva antes de
   iniciar outra alteração.

Se o usuário autorizou uma sequência de hipóteses, continue enquanto houver ganho mensurável e o escopo
permanecer estável. Sem essa autorização, encerre após um ciclo medido e proponha a próxima hipótese.

## Diagnóstico e progresso

- Para investigar uma execução, leia [Traces completos de runs](references/run-traces.md): CLI como
  índice, stream durável como evidência; nunca confunda sessão aberta com conversão incompleta.
- Classifique falhas em `código`, `contrato do agente`, `modelo`, `dados` ou `infraestrutura`.
- Em falha externa, preserve deployment, artefatos e estado; faça primeiro o menor teste discriminante.
- Não troque modelo, credencial, storage ou integração para contornar um erro sem demonstrar a camada causal.
- Durante operações longas, reporte a fase e o fato novo ao menos a cada 60 segundos; não despeje logs crus.
- Não peça autorização entre etapas somente leitura. Respeite os gates globais imediatamente antes de
  commit, push, deploy ou outra mutação externa.

## Encerramento

Retorne Markdown conciso com: hipótese, baseline, estado executado, resultado, métricas, evidências,
classificação da falha quando houver, decisão e próxima hipótese. Diferencie sucesso operacional da bateria
do diagnóstico sobre a efetividade da mudança.
