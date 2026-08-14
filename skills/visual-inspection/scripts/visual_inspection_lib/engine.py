from __future__ import annotations

import json
import math
import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO
from zoneinfo import ZoneInfo

from .contract import VisualInspectionError


CODEX_MODEL = "gpt-5.6-sol"
CODEX_REASONING_EFFORT = "medium"
MAX_TIMEOUT_SECONDS = 5 * 60
DEFAULT_TIMEOUT_SECONDS = MAX_TIMEOUT_SECONDS
DEFAULT_HEARTBEAT_SECONDS = 30
DEFAULT_CLEANUP_TIMEOUT_SECONDS = 10
TERMINATION_GRACE_SECONDS = 5
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class WorkerRun:
    raw_report: str | None
    timed_out: bool
    started_at: str
    finished_at: str
    duration_seconds: float


def worker_env(
    session: str,
    evidence_dir: Path,
    source: dict[str, str] | None = None,
) -> dict[str, str]:
    inherited = dict(source if source is not None else os.environ)
    inherited.update(
        {
            "AGENT_BROWSER_SESSION": session,
            "AGENT_BROWSER_SCREENSHOT_DIR": str(evidence_dir),
            "AGENT_BROWSER_SOCKET_DIR": f"/tmp/ab-{session.rsplit('-', 1)[-1]}",
        }
    )
    return inherited


def codex_command(
    repository: Path,
    output_file: Path,
    fast: bool = False,
) -> list[str]:
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--strict-config",
        "--disable",
        "multi_agent",
        "--cd",
        str(repository),
        "--dangerously-bypass-approvals-and-sandbox",
        "--config",
        "project_doc_max_bytes=0",
        "--config",
        'shell_environment_policy.inherit="all"',
        "--config",
        f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"',
        "--model",
        CODEX_MODEL,
        "--output-last-message",
        str(output_file),
        "--json",
    ]
    if fast:
        command.extend(["--enable", "fast_mode", "--config", 'service_tier="fast"'])
    command.append("-")
    return command


def run_worker(
    repository: Path,
    evidence_dir: Path,
    prompt: str,
    session: str,
    fast: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    progress: Callable[[str], None] | None = None,
) -> WorkerRun:
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise VisualInspectionError("worker timeout must be greater than zero")
    if timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise VisualInspectionError(
            f"worker timeout must be at most {MAX_TIMEOUT_SECONDS:g} seconds"
        )
    if not math.isfinite(heartbeat_seconds) or heartbeat_seconds <= 0:
        raise VisualInspectionError("heartbeat interval must be greater than zero")
    output_file = evidence_dir / "worker-report.md"
    started_at = datetime.now(SAO_PAULO)
    started_monotonic = time.monotonic()
    _notify(progress, started_monotonic, "worker started")
    event_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
    writer_errors: list[str] = []
    events_path = evidence_dir / "worker-events.jsonl"
    stderr_path = evidence_dir / "worker-stderr.log"
    with (
        events_path.open("w", encoding="utf-8", buffering=1) as events_file,
        stderr_path.open("w", encoding="utf-8", buffering=1) as stderr_file,
    ):
        try:
            process = subprocess.Popen(
                    codex_command(repository, output_file, fast),
                    cwd=repository,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=worker_env(session, evidence_dir),
                    start_new_session=True,
                )
        except OSError as error:
            raise VisualInspectionError(f"cannot launch Codex worker: {error}") from error

        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        readers = [
                threading.Thread(
                    target=_read_stream,
                    args=("stdout", process.stdout, event_queue),
                    daemon=True,
                ),
                threading.Thread(
                    target=_read_stream,
                    args=("stderr", process.stderr, event_queue),
                    daemon=True,
                ),
        ]
        for reader in readers:
            reader.start()
        writer = threading.Thread(
                target=_write_prompt,
                args=(process.stdin, prompt, writer_errors),
                daemon=True,
        )
        writer.start()

        open_streams = {"stdout", "stderr"}
        deadline = started_monotonic + timeout_seconds
        next_heartbeat = started_monotonic + heartbeat_seconds
        last_activity = started_monotonic
        step_ids: dict[str, int] = {}
        timed_out = False
        while open_streams or process.poll() is None:
            now = time.monotonic()
            if not timed_out and now >= deadline and process.poll() is None:
                timed_out = True
                _notify(
                        progress,
                        started_monotonic,
                        f"timeout reached after {_seconds_label(timeout_seconds)}; terminating worker",
                )
                _terminate_process(process)
            wait_for = min(
                    0.25,
                    max(0.01, next_heartbeat - now),
                    max(0.01, deadline - now) if not timed_out else 0.25,
            )
            try:
                stream_name, line = event_queue.get(timeout=wait_for)
            except queue.Empty:
                stream_name = ""
                line = None
            if stream_name:
                if line is None:
                    open_streams.discard(stream_name)
                elif stream_name == "stdout":
                    events_file.write(line)
                    last_activity = time.monotonic()
                    message = _event_message(line, step_ids)
                    if message:
                        _notify(progress, started_monotonic, message)
                else:
                    stderr_file.write(line)
                    last_activity = time.monotonic()

            now = time.monotonic()
            if now >= next_heartbeat and process.poll() is None:
                idle_seconds = max(0, int(now - last_activity))
                _notify(
                        progress,
                        started_monotonic,
                        f"heartbeat; worker active; last event {idle_seconds}s ago",
                )
                while next_heartbeat <= now:
                    next_heartbeat += heartbeat_seconds

        returncode = process.wait()
        for reader in readers:
            reader.join(timeout=1)
        writer.join(timeout=1)
        process.stdout.close()
        process.stderr.close()
        if not process.stdin.closed:
            process.stdin.close()

    finished_at = datetime.now(SAO_PAULO)
    duration_seconds = round(time.monotonic() - started_monotonic, 3)
    if timed_out:
        return WorkerRun(
                raw_report=None,
                timed_out=True,
                started_at=started_at.isoformat(timespec="seconds"),
                finished_at=finished_at.isoformat(timespec="seconds"),
                duration_seconds=duration_seconds,
        )
    if returncode != 0:
        raise VisualInspectionError(
                f"Codex worker failed with exit code {returncode}; "
                f"inspect {stderr_path} and {events_path}"
        )
    if writer_errors:
        raise VisualInspectionError(f"cannot send context to Codex worker: {writer_errors[0]}")
    if not output_file.is_file():
        raise VisualInspectionError("Codex worker did not write the Markdown report")
    return WorkerRun(
            raw_report=output_file.read_text(encoding="utf-8").strip(),
            timed_out=False,
            started_at=started_at.isoformat(timespec="seconds"),
            finished_at=finished_at.isoformat(timespec="seconds"),
            duration_seconds=duration_seconds,
    )


def _read_stream(
    name: str,
    stream: TextIO,
    event_queue: queue.Queue[tuple[str, str | None]],
) -> None:
    try:
        for line in stream:
            event_queue.put((name, line))
    finally:
        event_queue.put((name, None))


def _write_prompt(stream: TextIO, prompt: str, errors: list[str]) -> None:
    try:
        stream.write(prompt)
        stream.close()
    except OSError as error:
        errors.append(str(error))


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process_group = process.pid
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        process.terminate()
    deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
    while time.monotonic() < deadline:
        process.poll()
        if not _process_group_exists(process_group):
            break
        time.sleep(0.05)
    if _process_group_exists(process_group):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            process.kill()
    process.wait()


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _event_message(line: str, step_ids: dict[str, int]) -> str | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    event_type = event.get("type")
    if event_type == "thread.started":
        return "worker connected"
    if event_type == "turn.started":
        return "inspection started"
    item = event.get("item")
    if not isinstance(item, dict):
        if event_type == "turn.completed":
            return "inspection reasoning completed"
        return None
    item_type = item.get("type")
    item_id = item.get("id")
    if event_type == "item.started" and item_type == "command_execution":
        step = len(step_ids) + 1
        if isinstance(item_id, str):
            step_ids[item_id] = step
        return f"worker step {step} started"
    if event_type == "item.completed" and item_type == "command_execution":
        step = step_ids.get(item_id, len(step_ids))
        return f"worker step {step} completed; exit={item.get('exit_code')}"
    if event_type == "item.completed" and item_type == "agent_message":
        return "worker prepared Markdown report"
    return None


def _notify(
    progress: Callable[[str], None] | None,
    started_monotonic: float,
    message: str,
) -> None:
    if progress:
        progress(f"[{_elapsed_label(time.monotonic() - started_monotonic)}] {message}")


def _elapsed_label(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, remaining = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remaining:02d}"
    return f"{minutes:02d}:{remaining:02d}"


def _seconds_label(seconds: float) -> str:
    return f"{seconds:g}s"


def command_preview(repository: Path, fast: bool = False) -> list[str]:
    return codex_command(repository, Path("<report.md>"), fast)


def close_browser_session(
    session: str,
    evidence_dir: Path,
    timeout_seconds: float = DEFAULT_CLEANUP_TIMEOUT_SECONDS,
) -> str | None:
    try:
        result = subprocess.run(
            ["agent-browser", "close"],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=worker_env(session, evidence_dir),
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return f"agent-browser cleanup timed out after {timeout_seconds:g}s"
    except OSError as error:
        return f"cannot launch agent-browser cleanup: {error}"
    if result.returncode != 0:
        return f"agent-browser cleanup failed with exit code {result.returncode}"
    return None
