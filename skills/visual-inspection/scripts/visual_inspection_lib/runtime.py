from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from .contract import VisualInspectionError


OPERATIONAL_FILES = {"report.json", "worker-events.jsonl", "worker-stderr.log"}
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def resolve_repository(requested: Path) -> Path:
    candidate = requested.expanduser().resolve()
    if not candidate.is_dir():
        raise VisualInspectionError(f"repository directory does not exist: {candidate}")
    result = subprocess.run(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "not a Git repository"
        raise VisualInspectionError(f"invalid repository {candidate}: {detail}")
    return Path(result.stdout.strip()).resolve()


def validate_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise VisualInspectionError("URL must be an absolute http:// or https:// address")
    if parsed.username or parsed.password:
        raise VisualInspectionError("URL must not contain embedded credentials")
    return value


def create_run(output_root: Path | None) -> tuple[str, Path]:
    root = (output_root or Path("/tmp/visual-inspection")).expanduser().resolve()
    temporary_root = Path("/tmp").resolve()
    if root != temporary_root and temporary_root not in root.parents:
        raise VisualInspectionError("evidence output must be under /tmp")
    timestamp = datetime.now(SAO_PAULO).strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:8]
    run_id = f"visual-{timestamp}-{suffix}"
    evidence_dir = root / run_id
    evidence_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    return run_id, evidence_dir


def discover_preserved_artifacts(evidence_dir: Path) -> list[str]:
    artifacts: list[str] = []
    for path in sorted(evidence_dir.rglob("*")):
        if path.name in OPERATIONAL_FILES or path.is_symlink() or not path.is_file():
            continue
        artifacts.append(str(path.resolve()))
    return artifacts
