from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


DEFAULT_CODEX_MODEL = "gpt-5.6-sol"
DEFAULT_CODEX_REASONING_EFFORT = "high"
DEFAULT_HEARTBEAT_SECONDS = 30
TERMINATION_GRACE_SECONDS = 5


class EngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerRun:
    report: str
    session_id: str
    duration_seconds: float


def codex_command(
    repository: Path,
    output_file: Path,
    model: str | None,
    *,
    fast: bool = False,
    resume: str | None = None,
) -> list[str]:
    shared = ["--disable", "multi_agent"]
    if not resume or model:
        shared.extend(
            [
                "--model",
                model or DEFAULT_CODEX_MODEL,
                "--config",
                f'model_reasoning_effort="{DEFAULT_CODEX_REASONING_EFFORT}"',
            ]
        )
    if fast:
        shared.extend(["--enable", "fast_mode", "--config", 'service_tier="fast"'])
    execution = [
        "--dangerously-bypass-approvals-and-sandbox",
        "--output-last-message",
        str(output_file),
        "--json",
    ]
    if resume:
        return ["codex", "exec", "resume", *shared, *execution, resume, "-"]
    return ["codex", "exec", *shared, *execution, "--cd", str(repository), "-"]


def run_codex(
    repository: Path,
    prompt: str,
    run_dir: Path,
    model: str | None,
    *,
    fast: bool = False,
    resume: str | None = None,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    progress: Callable[[str], None] | None = None,
    interrupted: Callable[[], bool] | None = None,
) -> WorkerRun:
    if interrupted and interrupted():
        raise KeyboardInterrupt
    output_file = run_dir / "worker-report.md"
    command = codex_command(
        repository,
        output_file,
        model,
        fast=fast,
        resume=resume,
    )
    events_path = run_dir / "worker-events.jsonl"
    stderr_path = run_dir / "worker-stderr.log"
    started = time.monotonic()
    _notify(progress, started, "Codex worker started; runtime deadline disabled")
    event_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
    writer_errors: list[str] = []
    session_id = resume
    step_ids: dict[str, int] = {}

    with (
        events_path.open("w", encoding="utf-8", buffering=1) as events_file,
        stderr_path.open("w", encoding="utf-8", buffering=1) as stderr_file,
    ):
        try:
            process = subprocess.Popen(
                command,
                cwd=repository,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except OSError as error:
            raise EngineError(f"cannot launch Codex worker: {error}") from error

        process_group = process.pid
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
        next_heartbeat = started + heartbeat_seconds
        last_activity = started
        try:
            while open_streams or process.poll() is None:
                if interrupted and interrupted():
                    _notify(progress, started, "interruption requested; terminating worker")
                    _terminate_process_group(process, process_group)
                    raise KeyboardInterrupt
                now = time.monotonic()
                wait_for = min(0.25, max(0.01, next_heartbeat - now))
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
                        parsed_session = _session_from_event(line)
                        if parsed_session:
                            session_id = parsed_session
                            (run_dir / "session-id.txt").write_text(
                                parsed_session + "\n", encoding="utf-8"
                            )
                        message = _event_message(line, step_ids)
                        if message:
                            _notify(progress, started, message)
                    else:
                        stderr_file.write(line)
                        last_activity = time.monotonic()

                now = time.monotonic()
                if now >= next_heartbeat and process.poll() is None:
                    idle_seconds = max(0, int(now - last_activity))
                    _notify(
                        progress,
                        started,
                        f"heartbeat; worker active; last event {idle_seconds}s ago; timeout disabled",
                    )
                    while next_heartbeat <= now:
                        next_heartbeat += heartbeat_seconds
        except (KeyboardInterrupt, SystemExit):
            _terminate_process_group(process, process_group)
            raise

        returncode = process.wait()
        for reader in readers:
            reader.join(timeout=1)
        writer.join(timeout=1)
        process.stdout.close()
        process.stderr.close()
        if not process.stdin.closed:
            process.stdin.close()

    duration = round(time.monotonic() - started, 3)
    if returncode != 0:
        raise EngineError(
            f"Codex worker failed with exit code {returncode}; inspect {stderr_path} and {events_path}"
        )
    if writer_errors:
        raise EngineError(f"cannot send work order to Codex worker: {writer_errors[0]}")
    if not output_file.is_file():
        raise EngineError("Codex worker did not write its Markdown report")
    report = output_file.read_text(encoding="utf-8").strip()
    if not report:
        raise EngineError("Codex worker returned an empty Markdown report")
    if not session_id:
        raise EngineError("Codex worker did not expose a resumable session id")
    return WorkerRun(report=report, session_id=session_id, duration_seconds=duration)


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


def _session_from_event(line: str) -> str | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if event.get("type") != "thread.started":
        return None
    value = event.get("thread_id")
    return value if isinstance(value, str) and value else None


def _event_message(line: str, step_ids: dict[str, int]) -> str | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    event_type = event.get("type")
    if event_type == "thread.started":
        return "Codex worker connected"
    if event_type == "turn.started":
        return "implementation started"
    item = event.get("item")
    if not isinstance(item, dict):
        if event_type == "turn.completed":
            return "implementation reasoning completed"
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


def _terminate_process_group(process: subprocess.Popen[str], process_group: int) -> None:
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


def _notify(
    progress: Callable[[str], None] | None,
    started: float,
    message: str,
) -> None:
    if progress:
        progress(f"[{_elapsed_label(time.monotonic() - started)}] {message}")


def _elapsed_label(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, remaining = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remaining:02d}"
    return f"{minutes:02d}:{remaining:02d}"
