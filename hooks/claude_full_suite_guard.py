#!/usr/bin/env python3
"""Hook PreToolUse (Bash) do Claude Code: barra a suíte de testes inteira durante a iteração.

Em projetos com suíte grande, `vitest`/`pnpm test` sem seleção rodam centenas de arquivos
(~4 min no aura-ui). Na iteração, o agente deve rodar só o que foi afetado; a suíte cheia roda
uma vez, no estado final, antes do commit/push — e então leva o prefixo `FULL_SUITE=1`.

Liberado: `FULL_SUITE=1`, `--changed`, `vitest related`, caminhos de teste, `--help`.
Projetos pequenos (< MIN_TEST_FILES) e falhas de leitura passam (fail-open).
Saída 2 bloqueia e devolve a explicação ao agente pelo stderr.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

MIN_TEST_FILES = 150
TEST_FILE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")
SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
REDIRECT = re.compile(r"^(\d*|&)(>>?|<)")
REDIRECT_ALONE = re.compile(r"^(\d*|&)(>>?|<)$")
# Opções do Vitest que consomem o próximo token como valor (forma `--opt valor`).
VALUE_OPTIONS = {
    "--project", "--maxWorkers", "--minWorkers", "--pool", "--environment", "--reporter",
    "--outputFile", "--config", "-c", "--root", "-r", "--dir", "--shard", "--testNamePattern",
    "-t", "--vmMemoryLimit", "--exclude", "--mode", "--testTimeout", "--hookTimeout",
    "--sequence.seed", "--retry", "--bail", "--tags", "--inspect", "--inspect-brk",
}
RUNNER_TOKENS = {"exec", "npx", "bunx", "dlx", "x", "pnpx", "--bun"}
SELECTING_SUBCOMMANDS ={"related", "list", "bench", "init"}
PASSIVE_SUBCOMMANDS = {"run", "watch", "dev"}

BLOCK_MESSAGE = """Suíte de testes inteira bloqueada ({count} arquivos de teste em {project}).
Na iteração, rode só o que a mudança afeta:
  - testes tocados: vitest run <arquivos-ou-pastas-de-teste>
  - consumidores de um fonte: vitest related --run <arquivos-fonte>
  - mudanças não commitadas: vitest run --changed (ou o script do projeto, ex.: pnpm test:changed)
A suíte cheia roda UMA vez, no estado final, antes do commit/push. Se é esse o momento, repita o
comando com o prefixo FULL_SUITE=1 (ex.: FULL_SUITE=1 pnpm test ...)."""


def tokenize(segment: str) -> list[str]:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        tokens = segment.split()
    # Remove redirecionamentos (`2>&1`, `> log`, `&>log`), que não selecionam arquivos.
    out: list[str] = []
    skip = False
    for t in tokens:
        if skip:
            skip = False
            continue
        if REDIRECT.match(t):
            skip = REDIRECT_ALONE.match(t) is not None
            continue
        out.append(t)
    return out


def strip_prefix(tokens: list[str]) -> list[str]:
    i = 0
    while i < len(tokens) and (ENV_ASSIGN.match(tokens[i]) or tokens[i] in {"time", "env", "command", "exec"}):
        i += 1
    return tokens[i:]


def has_selection(args: list[str]) -> bool:
    """True quando os argumentos restringem os arquivos executados."""
    if not args:
        return False
    if any(a in {"--help", "-h", "--version", "-v"} or a == "--changed" or a.startswith("--changed=") for a in args):
        return True
    rest = list(args)
    if rest and not rest[0].startswith("-"):
        if rest[0] in SELECTING_SUBCOMMANDS:
            return True
        if rest[0] in PASSIVE_SUBCOMMANDS:
            rest = rest[1:]
    skip = False
    for a in rest:
        if skip:
            skip = False
            continue
        if a == "--":
            continue
        if a.startswith("-"):
            if "=" not in a and a in VALUE_OPTIONS:
                skip = True
            continue
        return True  # posicional = filtro de arquivo
    return False


def vitest_args(tokens: list[str]) -> list[str] | None:
    """Argumentos repassados ao Vitest, ou None se o segmento não roda a suíte."""
    tokens = strip_prefix(tokens)
    if not tokens:
        return None
    head = os.path.basename(tokens[0])
    for i, t in enumerate(tokens):
        if os.path.basename(t) not in {"vitest", "vitest.mjs"}:
            continue
        # Só em posição de comando: `vitest`, `pnpm exec vitest`, `npx vitest`, `node .../vitest.mjs`.
        if i == 0 or tokens[i - 1] in RUNNER_TOKENS or head in {"node", "bun"}:
            return tokens[i + 1:]
    if head == "vp" and len(tokens) > 1 and tokens[1] == "test":
        return tokens[2:]
    if head in {"pnpm", "npm", "yarn", "bun"}:
        rest = tokens[1:]
        # pula opções do gerenciador (`-C dir`, `--dir dir`, `--filter x`) e `run`
        j = 0
        while j < len(rest):
            if rest[j] in {"-C", "--dir", "--filter", "-F", "--prefix"}:
                j += 2
            elif rest[j].startswith("-") or rest[j] == "run":
                j += 1
            else:
                break
        if j < len(rest) and rest[j] == "test":
            return rest[j + 1:]
    return None


def manager_dir(tokens: list[str]) -> str | None:
    tokens = strip_prefix(tokens)
    for i, t in enumerate(tokens[:-1]):
        if t in {"-C", "--dir", "--prefix"}:
            return tokens[i + 1]
    return None


def resolve(base: str, target: str) -> str:
    return os.path.normpath(os.path.join(base, os.path.expanduser(target)))


def count_test_files(project: str) -> int | None:
    try:
        out = subprocess.run(
            ["git", "-C", project, "ls-files", "--", "."],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return sum(1 for line in out.splitlines() if TEST_FILE.search(line) and "node_modules/" not in line)


def find_broad_run(command: str, cwd: str) -> str | None:
    """Diretório do projeto de uma execução ampla, ou None se nada precisa ser barrado."""
    if re.search(r"(^|\s)FULL_SUITE=1(\s|$)", command):
        return None
    current = cwd
    for segment in SEGMENT_SPLIT.split(command):
        tokens = tokenize(segment.strip())
        if not tokens:
            continue
        if tokens[0] == "cd" and len(tokens) > 1:
            current = resolve(current, tokens[1])
            continue
        args = vitest_args(tokens)
        if args is None or has_selection(args):
            continue
        project = manager_dir(tokens)
        return resolve(current, project) if project else current
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    cwd = payload.get("cwd") or os.getcwd()
    project = find_broad_run(command, cwd)
    if project is None:
        return 0
    count = count_test_files(project)
    if count is None or count < MIN_TEST_FILES:
        return 0
    print(BLOCK_MESSAGE.format(count=count, project=project), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
