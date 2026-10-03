from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from .contract import DelegationError


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def create_run(output_root: Path | None) -> tuple[str, Path]:
    root = (output_root or Path("/tmp/implementation-delegator")).expanduser().resolve()
    temporary_root = Path("/tmp").resolve()
    if root != temporary_root and temporary_root not in root.parents:
        raise DelegationError("worker output must be under /tmp")
    timestamp = datetime.now(SAO_PAULO).strftime("%Y%m%d-%H%M%S")
    run_id = f"delegation-{timestamp}-{uuid4().hex[:8]}"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    return run_id, run_dir
