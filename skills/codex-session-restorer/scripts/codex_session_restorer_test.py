from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from codex_session_restorer import main


CURRENT_ID = "019f4cd8-680b-7ca0-851f-31f92ef44236"
RECENT_ID = "019fc944-d057-7403-b344-38fb8dc0a8a3"
OLD_ID = "019faf63-12f7-7910-abc0-ccb94c82035a"
SUBAGENT_ID = "019fc94d-0b58-7402-8299-1cc844479d75"
LEGACY_ID = "019fc911-d3e1-7c93-aa2c-deb1c7ba8ebc"


class CodexSessionRestorerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.codex_home = self.root / ".codex"
        self.codex_home.mkdir()
        self.project = self.root / "Projects" / "aura"
        self.project.mkdir(parents=True)
        self.rollout = self.codex_home / "recent.jsonl"
        self.rollout.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "Implemente AITRUS-432"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "Ajuste a interface"},
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )
        self._create_database()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _create_database(self) -> None:
        connection = sqlite3.connect(self.codex_home / "state_5.sqlite")
        connection.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                cwd TEXT NOT NULL,
                title TEXT NOT NULL,
                first_user_message TEXT NOT NULL,
                preview TEXT NOT NULL,
                rollout_path TEXT NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                archived INTEGER NOT NULL,
                source TEXT NOT NULL,
                thread_source TEXT,
                agent_role TEXT
            )
            """
        )
        now_ms = 1_785_796_800_000
        rows = [
            (
                CURRENT_ID,
                str(self.project),
                "Sessão atual",
                "Atual",
                "Atual",
                str(self.rollout),
                now_ms,
                0,
                "cli",
                "user",
                None,
            ),
            (
                RECENT_ID,
                str(self.project),
                "Título original",
                "Implemente AITRUS-432",
                "Interface de preferências",
                str(self.rollout),
                now_ms - 3_600_000,
                0,
                "cli",
                "user",
                None,
            ),
            (
                LEGACY_ID,
                str(self.project),
                "Sessão legada",
                "Sessão com origem migrada",
                "Sessão legada",
                str(self.rollout),
                now_ms - 2 * 3_600_000,
                0,
                "cli",
                "",
                None,
            ),
            (
                OLD_ID,
                str(self.project),
                "Sessão antiga",
                "Antiga",
                "Antiga",
                str(self.rollout),
                now_ms - 13 * 3_600_000,
                0,
                "cli",
                "user",
                None,
            ),
            (
                SUBAGENT_ID,
                str(self.project),
                "Worker",
                "Worker",
                "Worker",
                str(self.rollout),
                now_ms - 1_800_000,
                0,
                "cli",
                "user",
                "worker",
            ),
        ]
        connection.executemany("INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        connection.commit()
        connection.close()

    def run_main(self, arguments: list[str]) -> tuple[int, str]:
        output = StringIO()
        with redirect_stdout(output):
            result = main(arguments)
        return result, output.getvalue()

    def test_list_filters_window_current_session_and_subagents(self) -> None:
        with patch.dict(os.environ, {"CODEX_THREAD_ID": CURRENT_ID}):
            result, output = self.run_main(
                [
                    "list",
                    "--hours",
                    "12",
                    "--codex-home",
                    str(self.codex_home),
                    "--now",
                    "2026-08-03T22:00:00Z",
                ]
            )

        self.assertEqual(result, 0)
        payload = json.loads(output)
        self.assertTrue(payload["current_session_excluded"])
        self.assertEqual(
            [session["session_id"] for session in payload["sessions"]],
            [RECENT_ID, LEGACY_ID],
        )
        self.assertEqual(
            payload["sessions"][0]["recent_user_messages"],
            ["Implemente AITRUS-432", "Ajuste a interface"],
        )

    def test_open_dry_run_builds_windows_terminal_command(self) -> None:
        result, output = self.run_main(
            [
                "open",
                "--session-id",
                RECENT_ID,
                "--project-dir",
                str(self.project),
                "--title",
                "AITRUS-432 — Interface de preferências",
                "--profile",
                "{profile-id}",
                "--distro",
                "Ubuntu",
                "--wt-binary",
                "wt.exe",
                "--dry-run",
            ]
        )

        self.assertEqual(result, 0)
        command = json.loads(output)["command"]
        self.assertEqual(command[:4], ["wt.exe", "-w", "0", "new-tab"])
        self.assertIn("--suppressApplicationTitle", command)
        self.assertEqual(command[-3:-1], ["bash", "-lic"])
        self.assertIn(f"codex resume -C {self.project}", command[-1])
        self.assertTrue(command[-1].endswith(RECENT_ID))

    def test_open_preserves_symlinked_project_directory(self) -> None:
        project_link = self.root / "Projects" / "aura-link"
        project_link.symlink_to(self.project, target_is_directory=True)

        result, output = self.run_main(
            [
                "open",
                "--session-id",
                RECENT_ID,
                "--project-dir",
                str(project_link),
                "--title",
                "AITRUS-432 — Interface de preferências",
                "--wt-binary",
                "wt.exe",
                "--dry-run",
            ]
        )

        self.assertEqual(result, 0)
        payload = json.loads(output)
        self.assertEqual(payload["project_dir"], str(project_link))
        self.assertIn(f"codex resume -C {project_link}", payload["command"][-1])

    def test_open_rejects_long_title(self) -> None:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(
                    [
                        "open",
                        "--session-id",
                        RECENT_ID,
                        "--project-dir",
                        str(self.project),
                        "--title",
                        "x" * 81,
                        "--wt-binary",
                        "wt.exe",
                        "--dry-run",
                    ]
                )
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
