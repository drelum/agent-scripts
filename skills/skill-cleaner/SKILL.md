---
name: skill-cleaner
description: "Audit Codex skill inventory, prompt budget, recent usage, duplicates, disabled copies, and compact descriptions. Use when reviewing installed skills, investigating routing pressure, finding stale or duplicate skills, or deciding what to keep, remove, or consolidate."
---

# Skill Cleaner

Audit skills and suggest changes. Never remove or edit a skill without explicit user authorization.

## Workflow

Resolve `<skill-dir>` as the directory containing this `SKILL.md`, regardless of the current repository.

1. Run the analyzer:

```bash
node --experimental-strip-types <skill-dir>/scripts/skill-cleaner.ts
```

Useful variants:

```bash
node --experimental-strip-types <skill-dir>/scripts/skill-cleaner.ts --no-logs
node --experimental-strip-types <skill-dir>/scripts/skill-cleaner.ts --no-live --no-logs
node --experimental-strip-types <skill-dir>/scripts/skill-cleaner.ts --months 6 --max-log-mb 800
node --experimental-strip-types <skill-dir>/scripts/skill-cleaner.ts --months 6 --max-log-mb 800 --deep-logs
node --experimental-strip-types <skill-dir>/scripts/skill-cleaner.ts --context-tokens 272000 --budget-percent 2 --no-logs
node --experimental-strip-types <skill-dir>/scripts/skill-cleaner.ts --root ~/.agents/skills --root-only --no-logs
```

2. Read the report in this order:
- `Skill Budget`: live Codex inventory, 2% budget, budgeted usage, and full-description pressure.
- `Description candidates`: long descriptions where relaxed grammar saves prompt budget.
- `Duplicates`: same skill name or near-identical description/body across Codex, plugin cache, repo siblings, and personal skill roots.
- `Unused candidates`: no recent user mention or actual `SKILL.md` read in the analyzed history window.
- `Root summary`: where skills came from and whether config marks them disabled.

3. Before deleting or editing:
- Verify the kept copy exists and is loaded.
- Prefer deleting repo-local or `agent-scripts` duplicates when Codex built-ins cover them.
- Preserve trigger nouns in descriptions: product, tool, action, object.

## Analyzer Notes

- By default, `codex debug prompt-input` supplies the exact model-visible skill list, order, names, and aliased paths. `--no-live` forces the broader filesystem fallback.
- The broad filesystem scan remains for duplicate, disabled, and archived-cache diagnostics; it is not treated as the loaded inventory.
- The script mirrors Codex's model-visible line shape: `- name: description (file: path)`.
- It applies Codex-like frontmatter rules: YAML frontmatter only, default name from parent dir, single-line sanitized `name` and `description`.
- It follows Codex `core-skills/src/render.rs`: 2% of raw `context_window`, token cost `ceil(utf8_bytes / 4)`, then full descriptions -> equal description truncation -> omitted minimum lines. Alias-table line cost is included.
- It reads `~/.codex/models_cache.json` for the selected model's `context_window`; fallback is 272,000 tokens and 2%.
- It scans normal Codex, plugin, `~/.agents/skills`, and `agent-scripts` roots by default. Extra folders are included only with `--root <path>`.
- `--root-only` requires at least one `--root <path>`, skips the live Codex inventory, and scans only those supplied roots.
- It realpath-dedupes roots, so symlinked skill roots do not create false duplicates.
- For duplicate names, it reports description/body similarity and suggests deletion candidates only when bodies are near copies. Keep priority defaults to direct Codex system skills, then direct Codex skills, then plugin skills, then personal/repo copies.
- It scans recent `~/.codex/history.jsonl` and session logs by default. Use `--no-logs` to disable history reads; use `--deep-logs` to include archived Codex sessions.
- Usage evidence is heuristic: user `$skill`/`use skill` mentions and paths observed in standard or custom tool-call inputs.

## Output Policy

- Suggest first; edit only when the user asks.
- If asked to apply cleanup, make small grouped edits: descriptions, deletes, config disables. Commit only after explicit approval.
- Do not delete ignored/untracked skill dirs without naming the destination or confirming they are disposable.
