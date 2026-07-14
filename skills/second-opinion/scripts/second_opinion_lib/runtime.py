from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from .consultation import ConsultationError


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def create_run(output_root: Path | None) -> tuple[str, Path]:
    root = (output_root or Path("/tmp/second-opinion")).expanduser().resolve()
    temporary_root = Path("/tmp").resolve()
    if root != temporary_root and temporary_root not in root.parents:
        raise ConsultationError("advisor output must be under /tmp")
    timestamp = datetime.now(SAO_PAULO).strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:8]
    run_id = f"opinion-{timestamp}-{suffix}"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    return run_id, run_dir
