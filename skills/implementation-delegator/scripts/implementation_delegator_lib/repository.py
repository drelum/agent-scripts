from __future__ import annotations

import subprocess
from pathlib import Path

from .contract import DelegationError


def resolve_repository(requested: Path) -> Path:
    candidate = requested.expanduser().resolve()
    if not candidate.is_dir():
        raise DelegationError(f"repository directory does not exist: {candidate}")
    result = subprocess.run(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "not a Git repository"
        raise DelegationError(f"invalid repository {candidate}: {detail}")
    return Path(result.stdout.strip()).resolve()


def capture_state(repository: Path, output: Path) -> None:
    commands = (
        ("HEAD", ["git", "rev-parse", "HEAD"]),
        ("BRANCH", ["git", "branch", "--show-current"]),
        ("STATUS", ["git", "status", "--short"]),
    )
    sections: list[str] = []
    for label, command in commands:
        result = subprocess.run(
            command,
            cwd=repository,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        value = result.stdout.rstrip() if result.returncode == 0 else "<unavailable>"
        sections.append(f"[{label}]\n{value}\n")
    output.write_text("\n".join(sections), encoding="utf-8")
