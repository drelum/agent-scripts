from __future__ import annotations

import fcntl
import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from .contract import VisualInspectionError


OPERATIONAL_FILES = {
    "report.md",
    "worker-report.md",
    "worker-events.jsonl",
    "worker-stderr.log",
    "progress.md",
    "draft-report.md",
}
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
AUTO_OPEN_DISABLED_VALUES = {"0", "false", "no", "off"}
MAX_CONCURRENT_INSPECTIONS = 3
LOCK_SCAN_ATTEMPTS = 2


class ActiveVisualInspection(VisualInspectionError):
    pass


@dataclass
class RunLock:
    handle: TextIO

    def close(self) -> None:
        if self.handle.closed:
            return
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.flush()
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()

    def __enter__(self) -> RunLock:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


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
    root = (output_root or Path("/tmp/visual-inspection")).expanduser().absolute()
    resolved_root = root.resolve()
    temporary_root = Path("/tmp").resolve()
    if temporary_root not in resolved_root.parents:
        raise VisualInspectionError("evidence output must be under /tmp")
    timestamp = datetime.now(SAO_PAULO).strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:8]
    run_id = f"visual-{timestamp}-{suffix}"
    evidence_dir = root / run_id
    root_fd = _open_private_root(root)
    try:
        os.mkdir(run_id, mode=0o700, dir_fd=root_fd)
    finally:
        os.close(root_fd)
    return run_id, evidence_dir


def _open_private_root(root: Path) -> int:
    if root.resolve() == Path("/tmp").resolve():
        raise VisualInspectionError("evidence root must be a private directory under /tmp")
    descriptor = None
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if os.fstat(descriptor).st_uid != os.getuid():
            raise VisualInspectionError("evidence root must belong to the current user")
        os.fchmod(descriptor, 0o700)
        return descriptor
    except (OSError, VisualInspectionError) as error:
        if descriptor is not None:
            os.close(descriptor)
        raise VisualInspectionError(f"unsafe evidence root {root}: {error}") from error


def _open_lock(root: Path, name: str) -> TextIO:
    root_fd = _open_private_root(root)
    descriptor = None
    try:
        descriptor = os.open(
            name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=root_fd
        )
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid() or metadata.st_nlink != 1):
            raise VisualInspectionError("lock must be a private regular file without links")
        os.fchmod(descriptor, 0o600)
        return os.fdopen(descriptor, "r+", encoding="utf-8")
    except (OSError, VisualInspectionError) as error:
        if descriptor is not None:
            os.close(descriptor)
        raise VisualInspectionError(f"unsafe inspection lock {root / name}: {error}") from error
    finally:
        os.close(root_fd)


def open_evidence_directory(evidence_dir: Path) -> bool:
    if (
        os.environ.get("VISUAL_INSPECTION_AUTO_OPEN", "1").strip().lower()
        in AUTO_OPEN_DISABLED_VALUES
    ):
        return False
    if not (os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP")):
        return False

    resolved = evidence_dir.resolve()
    if not resolved.is_dir():
        return False
    wslpath = shutil.which("wslpath")
    cmd = shutil.which("cmd.exe")
    windows_cwd = Path("/mnt/c")
    if not wslpath or not cmd or not windows_cwd.is_dir():
        return False

    try:
        converted = subprocess.run(
            [wslpath, "-w", str(resolved)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        windows_path = converted.stdout.strip()
        if converted.returncode != 0 or not windows_path:
            return False
        opened = subprocess.run(
            [cmd, "/d", "/c", "start", "", windows_path],
            cwd=windows_cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return opened.returncode == 0


def acquire_run_lock(root: Path, session: str, repository: Path) -> RunLock:
    lock_paths = [root / ".runner.lock"] + [
        root / f".runner.{slot}.lock"
        for slot in range(2, MAX_CONCURRENT_INSPECTIONS + 1)
    ]

    for _ in range(LOCK_SCAN_ATTEMPTS):
        active_runs: list[dict[str, object]] = []
        for lock_path in lock_paths:
            handle = _open_lock(root, lock_path.name)
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.seek(0)
                active_runs.append(_lock_metadata(handle.read()))
                handle.close()
                continue

            handle.seek(0)
            handle.truncate()
            json.dump(
                {
                    "pid": os.getpid(),
                    "session": session,
                    "repository": str(repository),
                    "started_at": datetime.now(SAO_PAULO).isoformat(
                        timespec="seconds"
                    ),
                },
                handle,
            )
            handle.write("\n")
            handle.flush()
            return RunLock(handle)

    active_summary = "; ".join(
        "session={session}; repository={repository}".format(
            session=run.get("session", "unknown"),
            repository=run.get("repository", "unknown"),
        )
        for run in active_runs
    )
    raise ActiveVisualInspection(
        f"visual inspection capacity reached ({MAX_CONCURRENT_INSPECTIONS}/"
        f"{MAX_CONCURRENT_INSPECTIONS} active); {active_summary}; "
        "follow an existing process instead of launching another"
    )


def _lock_metadata(raw: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def discover_preserved_artifacts(evidence_dir: Path) -> list[str]:
    artifacts: list[str] = []
    for path in sorted(evidence_dir.rglob("*")):
        if path.name in OPERATIONAL_FILES or path.is_symlink() or not path.is_file():
            continue
        artifacts.append(str(path.resolve()))
    return artifacts
