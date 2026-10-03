---
name: visual-inspection
description: "Run browser QA in a separate full-access Codex worker pinned to gpt-6-luna with medium reasoning and Fast enabled by default, using agent-browser in an isolated session and returning a text report for caller assessment. Use for visual inspection, responsive checks, browser acceptance testing, screenshots, UI regressions, or any request that should keep browser work outside the main agent while sharing complete task context and repository access."
---

# Visual Inspection

Delegate visual and browser QA to one separate Codex worker. Give it the repository and a complete task handoff from the main agent. Use `agent-browser`; never Playwright, Puppeteer, or a built-in browser tool.

## Workflow

Resolve `<skill-dir>` as the directory containing this `SKILL.md`.

1. Finish implementation, tests, builds, and Auto Review first. Do not overlap an inspection with those jobs. Up to three inspections may run concurrently (the runner's ceiling per output root); do not change output roots to evade it.
2. Start the application separately. Immediately before invoking the worker, use permitted non-browser diagnostics to confirm that the target route, compiled assets, and required dependencies are ready and not returning 5xx. An HTML 200 alone does not prove readiness. For authenticated flows, verify the exact bootstrap mechanism and include its usage instructions in the handoff. Do not spend a worker on a runtime still starting, restarting, or hot-reloading; browser QA itself remains in the separate worker.
3. Build a complete handoff: current request, relevant decisions, implementation summary, exact runtime route and known entity, flows, viewports, acceptance criteria, known uncertainties, and required evidence. Before delegating a data-dependent criterion, confirm its required scenario through permitted diagnostics or an existing canonical fixture: role, destination store, entity and state, including counts or matching records across stores when relevant. State known missing prerequisites before spending a run; do not ask the worker to hunt for them or create business data.

For an authenticated target, the caller may supply a short-lived token through a protected channel, such as an inherited environment variable, together with app-specific instructions for consuming it. Put the channel name and usage instructions in the handoff, never the token value; do not echo, persist, or expose the token in reports or artifacts.

4. Invoke the runner:

```bash
<skill-dir>/scripts/visual-inspection --repo <repository> --url <ready-url> < /tmp/visual-inspection-context.txt
```

Fast is enabled by default, independently of the calling client's tier or config. No flag is required; `--fast` remains accepted for compatibility.

Use a safe file-editing mechanism for the temporary handoff. Do not interpolate user text into shell quoting.
The total timeout is at most 7 minutes. Use `--timeout-seconds <seconds>` only to lower it; do not wrap the runner in an external timeout.
Invoke the runner once. Keep stdout and stderr attached; the runner already persists protected logs. If the client yields a process or session handle, resume or poll that same handle until completion—never relaunch the command to check progress. Exit code zero means the runner completed. The output is a text response for the calling agent to assess, not a fully validated schema or automatic approval; evaluate the declared status together with criteria, limitations, validation notices and evidence.

Keep the run concise:

- Give an exact route and known entity when a criterion depends on data.
- Default to viewport `1366x768`; use another viewport only when the request explicitly names it. Record the actual viewport in preflight evidence.
- Exercise only the requested flows, with one attempt and one reasonable retry. If data or access is still unavailable, report `BLOCKED`; do not hunt across contexts, and allow at most one focused repository lookup.
- Use compact incremental snapshots, expand scope for static/deep content, and finish each criterion before the next. The runner passes a monotonic finalization deadline in `VISUAL_INSPECTION_FINALIZE_AT`; its embedded protocol tells the worker to check the clock before browser work, after each browser command, and before retries or new criteria. At 90% of the runtime budget, stop exploration, restore reversible changes, close the session, and finish the report; mark unproven criteria BLOCKED. Preserve FAIL when a defect was already demonstrated.
- The clock check is cooperative. The runner's progress notice is for the caller, not an injected worker message. The hard timeout remains unchanged and still returns BLOCKED if the worker fails to conclude.
- Append each post-command budget check to that browser command's shell invocation. Avoid a separate tool roundtrip solely for the clock after every action; keep the initial check and checks before retries or new criteria when needed.

5. Follow progress and 30-second heartbeats on stderr. The runner announces the evidence directory and an exact `tail` command at startup; `worker-events.jsonl` is written incrementally. Final stdout is a Markdown report, also saved as `report.md`. At the end of every completed run on WSL, the runner opens that evidence directory in Windows Explorer so the user can review its thumbnails immediately. This is best-effort and never changes the inspection status; set `VISUAL_INSPECTION_AUTO_OPEN=0` only for headless automation.
6. Read the text report and any validation notices. Minor layout/heading differences do not discard the response: evaluate the original worker text when the recommended structure is incomplete. A blocked preflight means the requested flow was not exercised. Treat a worker `PASS` as provisional: open every cited screenshot with the main agent's image-viewing tool and confirm the claimed content and viewport. If image viewing is unavailable, do not accept a visual pass. The runner checks references/status consistency, not image content or business correctness.
7. Report failures and blocked criteria. Fixes remain a separate main-agent action. Before another run, state what changed: repaired behavior/runtime, available entity, corrected fixture/bootstrap, or a narrower handoff that addresses the previous blocker. Never rerun solely hoping for a different result. When the scope cannot fit the budget, inspect smaller explicit units sequentially and retain the list of uncovered criteria; do not increase the timeout.

## Worker Contract

- Model: `gpt-6-luna`; reasoning effort: `medium`. Fixed by the runner. Fast is enabled by default through `fast_mode` and `service_tier="fast"`. If the provider rejects the configured model or tier, report the blocker; never substitute another model silently.
- One ephemeral Codex process, one unique `agent-browser` session, one evidence directory per run.
- Codex runs inside the supplied repository with approvals and sandbox disabled. It inherits the caller environment and may inspect the complete repository, Git history, configuration, tests, logs, and documentation.
- Complete relevant task context comes from the main agent through stdin. The runner cannot export hidden reasoning or the raw conversation automatically; synthesize a faithful handoff.
- Browser interaction uses only `agent-browser`. Do not substitute Playwright, Puppeteer, browser MCPs, or built-in browsing.
- Preflight is generic: confirm that the target opens and the application is usable. Authenticate only when the requested flow requires it. Domain-specific setup belongs in the flow and acceptance criteria.
- A `PASS` may include only `LOW` findings; `MEDIUM`, `HIGH`, or `BLOCKING` findings require `FAIL`.
- Use the concise `agent-browser` protocol embedded by the runner. Observe fresh snapshots/deltas after DOM-changing actions; surviving refs can persist, while replaced elements and navigation invalidate them.
- Do not mask failed required actions. Retry once from a fresh snapshot, then report the affected criterion as `blocked` or `fail`.
- The worker is an inspector, not an implementer. It may read and run diagnostics, but must not edit repository files, install dependencies, commit, push, or change external state beyond reversible interactions required by the handoff.
- Store screenshots and browser artifacts in the returned evidence directory. Finalize any native recording before closing the session, including early finalization.
- The runner streams safe step progress and heartbeats to stderr while preserving stdout for the final Markdown report. Raw Codex events and stderr are persisted incrementally in the evidence directory.
- The runner owns its timeout and process lifecycle. On timeout, it terminates the worker process group, closes the isolated browser session, preserves partial artifacts, and returns `blocked`.
- The runner allows three concurrent inspections per output root (`MAX_CONCURRENT_INSPECTIONS`). A fourth invocation in that root returns `BLOCKED` without starting another Codex or browser worker; follow an active run instead of retrying. This is not a global lock across different output roots.
- Evidence roots must be directories owned by the current user under `/tmp`; `/tmp` itself and symlinked roots are rejected. Existing owned roots are restricted to mode `0700`. Lock files reject symlinks and hardlinks before any permission or content change.
- A formatting issue preserves the worker text with review notices. Missing/invalid evidence or contradictory conclusions are still explicit; PASS is not retained automatically in those cases. Operational failures/timeouts produce BLOCKED with preserved artifacts and partial records when available. Partial work never proves a complete pass.
- On WSL, use viewport screenshots; never use `agent-browser screenshot --full`, which can produce black captures. Scroll and capture multiple viewports for full-page coverage.
- The main agent independently inspects the pixels of every cited screenshot. A worker statement or successful screenshot command alone is not visual proof.
- No technical sandbox or post-run worktree fingerprint is applied.
- No silent fallback to the main agent. If Codex or `agent-browser` is unavailable, return the blocker.

## Evidência temporal

Ler [references/media.md](references/media.md) ao escolher entre screenshots, snapshots e vídeo. Vídeo nativo é obrigatório quando o critério depende de sequência ou quando pedido: capturar antes do gesto, finalizar com `record stop`, verificar duração/decodificação e citar intervalos. O principal inspeciona os quadros e evidências temporais; folha de contato isolada não prova transição rápida. Captura parcial não vira PASS.

Usar `snapshot --delta` no acompanhamento e `--delta --full` para renovar a base. Usar `screenshot --if-changed` somente em observações intermediárias; screenshots finais são explícitos. Evidência técnica não recebe cartões ou máscaras editoriais que alterem o objeto avaliado.

## Handoff Shape

```text
Current user request:
<what the user asked and what must be proven>

Relevant conversation context:
- <decisions, constraints, corrections, and non-goals>

Implementation and repository context:
- <what changed, relevant areas, current state, and known risks>

Runtime target:
- Repository: <path>
- URL: <ready URL>

Verified prerequisites (when criteria depend on data or authentication):
- <bootstrap instructions without secrets, required role, destination store, entity and state>
- <evidence that the required scenario exists; known missing prerequisites>

Flows:
- <navigation or interaction to exercise>

Viewports:
- <desktop/mobile dimensions or named device>

Acceptance criteria:
- <observable result>

Evidence:
- <screenshots, console errors, accessibility snapshot, or other proof>

Known uncertainties:
- <anything the worker should verify rather than assume>
```

The goal, flows, and observable acceptance criteria are required; include verified prerequisites for data-dependent or authenticated criteria. Add the other sections only when they materially help; the runner already supplies repository, URL, model, viewport policy, isolation, and evidence rules.

## Report Shape

```markdown
Status: PASS|FAIL|BLOCKED

# Resumo

# Preflight
Status: PASS|BLOCKED

# Critérios
## <criterion> — PASS|FAIL|BLOCKED

# Achados
## LOW|MEDIUM|HIGH|BLOCKING — <title>

# Limitações

# Evidências
- /absolute/path/to/artifact.png
```

This shape is recommended, not a rigid response schema. The worker writes Markdown directly; the runner tolerates ordinary Markdown evidence links/captions and preserves free text with notices when structural parsing fails. The calling agent must assess the response and actual evidence. Status/reference checks do not prove visual or business acceptance; no JSON response is required.

## Conferência e registro durante a execução

Após cada critério, o worker envia por stdin um registro Markdown curto (critério, status declarado, observação e evidências) para:

```bash
<skill-dir>/scripts/visual-inspection-report checkpoint --evidence-dir <diretório-da-execução>
```

O helper acrescenta o registro em `progress.md`, com horário de São Paulo. O runner inclui esses registros na resposta mesmo após interrupção; são evidências parciais para avaliação, sem aprovação automática. Nunca incluir segredos.

Antes de concluir, salvar o texto proposto como `draft-report.md` no diretório da execução e conferir:

```bash
<skill-dir>/scripts/visual-inspection-report check <diretório-da-execução>/draft-report.md --evidence-dir <diretório-da-execução>
```

Código 1 indica avisos a revisar. Corrigir o texto uma vez, se houver tempo, usando artefatos existentes. Não repetir navegação nem descartar o laudo por erro de formato; devolver o melhor texto disponível com limitações. O comando não executa browser e não aprova a inspeção.
