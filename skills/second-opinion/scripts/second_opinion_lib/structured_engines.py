from __future__ import annotations

import json
import math
import os
import queue
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO
from zoneinfo import ZoneInfo


DEFAULT_CODEX_MODEL = "gpt-5.6-sol"
DEFAULT_CODEX_REASONING_EFFORT = "high"
DEFAULT_TIMEOUT_SECONDS = 15 * 60
DEFAULT_HEARTBEAT_SECONDS = 30
TERMINATION_GRACE_SECONDS = 5
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
SAFE_ENV_KEYS = (
    "HOME",
    "PATH",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "NODE_EXTRA_CA_CERTS",
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "XDG_CONFIG_HOME",
)


class StructuredEngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineRun:
    raw_result: str | None
    timed_out: bool
    started_at: str
    finished_at: str
    duration_seconds: float


def reviewer_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    current = source if source is not None else os.environ
    return {key: current[key] for key in SAFE_ENV_KEYS if current.get(key)}


def codex_command(
    workspace: Path,
    output_file: Path,
    model: str | None,
) -> list[str]:
    return [
        "codex",
        "exec",
        "--ephemeral",
        "--disable",
        "multi_agent",
        "--disable",
        "apps",
        "--disable",
        "hooks",
        "--disable",
        "memories",
        "--ignore-user-config",
        "--ignore-rules",
        "--cd",
        str(workspace),
        "--config",
        "project_doc_max_bytes=0",
        "--config",
        'default_permissions=":danger-full-access"',
        "--config",
        'approval_policy="never"',
        "--config",
        'shell_environment_policy.inherit="all"',
        "--config",
        'web_search="live"',
        "--config",
        f'model_reasoning_effort="{DEFAULT_CODEX_REASONING_EFFORT}"',
        "--model",
        model or DEFAULT_CODEX_MODEL,
        "--output-last-message",
        str(output_file),
        "--json",
        "-",
    ]


def claude_command(model: str | None) -> list[str]:
    command = [
        "claude",
        "--print",
        "--safe-mode",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--dangerously-skip-permissions",
        "--tools",
        "default",
        "--disallowedTools",
        "Agent,Task,mcp__*",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if model:
        command.extend(["--model", model])
    return command


def run_structured_engine(
    engine: str,
    workspace: Path,
    prompt: str,
    model: str | None,
    run_dir: Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    progress: Callable[[str], None] | None = None,
) -> EngineRun:
    if engine not in {"codex", "claude"}:
        raise StructuredEngineError(f"unsupported engine: {engine}")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise StructuredEngineError("advisor timeout must be greater than zero")
    if not math.isfinite(heartbeat_seconds) or heartbeat_seconds <= 0:
        raise StructuredEngineError("heartbeat interval must be greater than zero")

    with tempfile.TemporaryDirectory(prefix="second-opinion-engine-") as temp:
        output_file = Path(temp) / "report.md"
        command = (
            codex_command(workspace, output_file, model)
            if engine == "codex"
            else claude_command(model)
        )
        started_at = datetime.now(SAO_PAULO)
        started_monotonic = time.monotonic()
        _notify(progress, started_monotonic, f"{engine} advisor started")
        event_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        writer_errors: list[str] = []
        events_path = run_dir / "advisor-events.jsonl"
        stderr_path = run_dir / "advisor-stderr.log"
        final_stream_event: str | None = None
        with (
            events_path.open("w", encoding="utf-8", buffering=1) as events_file,
            stderr_path.open("w", encoding="utf-8", buffering=1) as stderr_file,
        ):
            try:
                process = subprocess.Popen(
                    command,
                    cwd=workspace,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=reviewer_env(),
                    start_new_session=True,
                )
            except OSError as error:
                raise StructuredEngineError(f"cannot launch {engine} advisor: {error}") from error

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
            deadline = started_monotonic + timeout_seconds
            next_heartbeat = started_monotonic + heartbeat_seconds
            last_activity = started_monotonic
            step_ids: dict[str, int] = {}
            timed_out = False
            while (
                open_streams
                or process.poll() is None
                or (not timed_out and _process_group_exists(process_group))
            ):
                now = time.monotonic()
                process.poll()
                if not timed_out and now >= deadline:
                    timed_out = True
                    _notify(
                        progress,
                        started_monotonic,
                        f"timeout reached after {timeout_seconds:g}s; terminating advisor",
                    )
                    if _process_group_exists(process_group):
                        _terminate_process_group(process, process_group)

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
                        if engine == "claude" and _is_claude_result(line):
                            final_stream_event = line.strip()
                        message = _event_message(engine, line, step_ids)
                        if message:
                            _notify(progress, started_monotonic, message)
                    else:
                        stderr_file.write(line)
                        last_activity = time.monotonic()

                now = time.monotonic()
                if (
                    now >= next_heartbeat
                    and not timed_out
                    and (
                        process.poll() is None
                        or _process_group_exists(process_group)
                    )
                ):
                    idle_seconds = max(0, int(now - last_activity))
                    _notify(
                        progress,
                        started_monotonic,
                        f"heartbeat; advisor active; last event {idle_seconds}s ago",
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
            return EngineRun(
                raw_result=None,
                timed_out=True,
                started_at=started_at.isoformat(timespec="seconds"),
                finished_at=finished_at.isoformat(timespec="seconds"),
                duration_seconds=duration_seconds,
            )
        if returncode != 0:
            raise StructuredEngineError(
                f"{engine} advisor failed with exit code {returncode}; "
                f"inspect {stderr_path} and {events_path}"
            )
        if writer_errors:
            raise StructuredEngineError(
                f"cannot send brief to {engine} advisor: {writer_errors[0]}"
            )
        if engine == "codex":
            if not output_file.is_file():
                raise StructuredEngineError("Codex did not write the Markdown report file")
            raw_result = output_file.read_text(encoding="utf-8").strip()
        else:
            if not final_stream_event:
                raise StructuredEngineError("Claude did not emit a final result event")
            raw_result = final_stream_event
        return EngineRun(
            raw_result=raw_result,
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


def _terminate_process_group(
    process: subprocess.Popen[str],
    process_group: int,
) -> None:
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


def _event_message(engine: str, line: str, step_ids: dict[str, int]) -> str | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    event_type = event.get("type")
    if engine == "claude":
        if event_type == "system" and event.get("subtype") == "init":
            return "claude advisor connected"
        if event_type == "assistant":
            return "claude advisor produced response activity"
        if event_type == "user":
            return "claude advisor received tool results"
        if event_type == "result":
            return "claude advisor prepared Markdown report"
        return None
    if event_type == "thread.started":
        return "codex advisor connected"
    if event_type == "turn.started":
        return "codex consultation started"
    item = event.get("item")
    if not isinstance(item, dict):
        if event_type == "turn.completed":
            return "codex consultation reasoning completed"
        return None
    item_type = item.get("type")
    item_id = item.get("id")
    if event_type == "item.started" and item_type == "command_execution":
        step = len(step_ids) + 1
        if isinstance(item_id, str):
            step_ids[item_id] = step
        return f"codex advisor step {step} started"
    if event_type == "item.completed" and item_type == "command_execution":
        step = step_ids.get(item_id, len(step_ids))
        return f"codex advisor step {step} completed; exit={item.get('exit_code')}"
    if event_type == "item.completed" and item_type == "agent_message":
        return "codex advisor prepared Markdown report"
    return None


def _is_claude_result(line: str) -> bool:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return False
    return isinstance(event, dict) and event.get("type") == "result"


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


def command_preview(
    engine: str,
    workspace: Path,
    model: str | None,
) -> dict[str, Any]:
    if engine == "claude":
        return {"engine": engine, "command": claude_command(model)}
    return {
        "engine": engine,
        "command": codex_command(workspace, Path("<report.md>"), model),
    }
