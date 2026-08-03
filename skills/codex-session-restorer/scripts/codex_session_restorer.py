from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SESSION_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
MAX_TITLE_LENGTH = 80
MAX_CONTEXT_LENGTH = 700


class RestorerError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_from_epoch_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def compact_text(value: str, limit: int = MAX_CONTEXT_LENGTH) -> str:
    compacted = " ".join(value.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 1].rstrip() + "…"


def extract_recent_user_messages(rollout_path: Path, limit: int) -> list[str]:
    if limit == 0 or not rollout_path.is_file():
        return []

    event_messages: list[str] = []
    response_messages: list[str] = []
    try:
        with rollout_path.open(encoding="utf-8") as rollout:
            for line in rollout:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = item.get("payload") or {}
                if item.get("type") == "event_msg" and payload.get("type") == "user_message":
                    message = payload.get("message")
                    if isinstance(message, str) and message.strip():
                        event_messages.append(compact_text(message))
                    continue
                if (
                    item.get("type") == "response_item"
                    and payload.get("type") == "message"
                    and payload.get("role") == "user"
                ):
                    texts = [
                        content.get("text", "")
                        for content in payload.get("content", [])
                        if content.get("type") == "input_text" and isinstance(content.get("text"), str)
                    ]
                    message = "\n".join(texts).strip()
                    if message:
                        response_messages.append(compact_text(message))
    except OSError:
        return []

    messages = event_messages or response_messages
    return messages[-limit:]


def list_sessions(args: argparse.Namespace) -> int:
    if args.hours <= 0:
        raise RestorerError("--hours deve ser maior que zero")
    if args.max_user_messages < 0:
        raise RestorerError("--max-user-messages não pode ser negativo")

    codex_home = Path(args.codex_home).expanduser().resolve()
    database = codex_home / "state_5.sqlite"
    if not database.is_file():
        raise RestorerError(f"Base de sessões do Codex não encontrada: {database}")

    now = parse_utc(args.now) if args.now else utc_now()
    cutoff_ms = int((now - timedelta(hours=args.hours)).timestamp() * 1000)
    current_session_id = os.environ.get("CODEX_THREAD_ID")

    uri = f"file:{database}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                id,
                cwd,
                title,
                first_user_message,
                preview,
                rollout_path,
                updated_at_ms
            FROM threads
            WHERE archived = 0
              AND source = 'cli'
              AND COALESCE(NULLIF(thread_source, ''), 'user') = 'user'
              AND agent_role IS NULL
              AND updated_at_ms >= ?
            ORDER BY updated_at_ms DESC
            """,
            (cutoff_ms,),
        ).fetchall()
    except sqlite3.Error as error:
        raise RestorerError(f"Falha ao consultar sessões do Codex: {error}") from error
    finally:
        if "connection" in locals():
            connection.close()

    sessions: list[dict[str, Any]] = []
    excluded_current = False
    for row in rows:
        if not args.include_current and current_session_id and row["id"] == current_session_id:
            excluded_current = True
            continue
        rollout_path = Path(row["rollout_path"])
        sessions.append(
            {
                "session_id": row["id"],
                "cwd": row["cwd"],
                "cwd_exists": Path(row["cwd"]).is_dir(),
                "updated_at": iso_from_epoch_ms(row["updated_at_ms"]),
                "existing_title": compact_text(row["title"] or ""),
                "first_user_message": compact_text(row["first_user_message"] or ""),
                "preview": compact_text(row["preview"] or ""),
                "recent_user_messages": extract_recent_user_messages(
                    rollout_path, args.max_user_messages
                ),
                "rollout_path": str(rollout_path),
            }
        )

    result = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "window_hours": args.hours,
        "order": "most_recent_first",
        "current_session_excluded": excluded_current,
        "sessions": sessions,
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def normalized_title(value: str) -> str:
    title = " ".join(value.split())
    if not title:
        raise RestorerError("--title não pode ser vazio")
    if len(title) > MAX_TITLE_LENGTH:
        raise RestorerError(f"--title deve ter no máximo {MAX_TITLE_LENGTH} caracteres")
    return title


def open_session(args: argparse.Namespace) -> int:
    if not SESSION_ID_PATTERN.fullmatch(args.session_id):
        raise RestorerError("--session-id deve ser um UUID válido")

    project_dir = Path(os.path.abspath(os.path.expanduser(args.project_dir)))
    if not project_dir.is_dir():
        raise RestorerError(f"Diretório da sessão não existe: {project_dir}")

    title = normalized_title(args.title)
    distro = args.distro or os.environ.get("CODEX_SESSION_RESTORER_DISTRO") or os.environ.get(
        "WSL_DISTRO_NAME", "Ubuntu"
    )
    profile = (
        args.profile
        or os.environ.get("CODEX_SESSION_RESTORER_PROFILE")
        or os.environ.get("WT_PROFILE_ID")
        or distro
    )
    window = args.window or os.environ.get("CODEX_SESSION_RESTORER_WINDOW", "0")
    wt_binary = args.wt_binary or shutil.which("wt.exe")
    if not wt_binary:
        raise RestorerError("wt.exe não encontrado; execute dentro do WSL com Windows Terminal instalado")

    resume_command = "exec codex resume -C {} {}".format(
        shlex.quote(str(project_dir)), shlex.quote(args.session_id)
    )
    command = [
        wt_binary,
        "-w",
        window,
        "new-tab",
        "--profile",
        profile,
        "--title",
        title,
        "--suppressApplicationTitle",
        "wsl.exe",
        "-d",
        distro,
        "--",
        "bash",
        "-lic",
        resume_command,
    ]

    if args.dry_run:
        json.dump(
            {
                "title": title,
                "session_id": args.session_id,
                "project_dir": str(project_dir),
                "command": command,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    try:
        completed = subprocess.run(command, check=False)
    except OSError as error:
        raise RestorerError(f"Falha ao iniciar Windows Terminal: {error}") from error
    if completed.returncode != 0:
        raise RestorerError(f"wt.exe encerrou com código {completed.returncode}")

    print(f"Aba aberta: {title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="restore-codex-sessions",
        description="Lista sessões recentes do Codex e abre cada sessão em uma aba nomeada.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="Lista sessões recentes em JSON")
    list_parser.add_argument("--hours", type=float, default=12)
    list_parser.add_argument("--max-user-messages", type=int, default=6)
    list_parser.add_argument("--include-current", action="store_true")
    list_parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", "~/.codex"))
    list_parser.add_argument("--now", help=argparse.SUPPRESS)
    list_parser.set_defaults(handler=list_sessions)

    open_parser = subparsers.add_parser("open", help="Abre uma sessão em nova aba")
    open_parser.add_argument("--session-id", required=True)
    open_parser.add_argument("--project-dir", required=True)
    open_parser.add_argument("--title", required=True)
    open_parser.add_argument("--profile")
    open_parser.add_argument("--distro")
    open_parser.add_argument("--window")
    open_parser.add_argument("--wt-binary")
    open_parser.add_argument("--dry-run", action="store_true")
    open_parser.set_defaults(handler=open_session)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except RestorerError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
