from __future__ import annotations

import subprocess
from pathlib import Path

from .consultation import ConsultationError


def resolve_repository(requested: Path) -> Path:
    candidate = requested.expanduser().resolve()
    if not candidate.is_dir():
        raise ConsultationError(f"repository directory does not exist: {candidate}")
    result = subprocess.run(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "not a Git repository"
        raise ConsultationError(f"invalid repository {candidate}: {detail}")
    return Path(result.stdout.strip()).resolve()
