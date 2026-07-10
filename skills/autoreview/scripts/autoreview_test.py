from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoreview_lib.bundle import BundleError, build_bundle
from autoreview_lib.engines import claude_command, codex_command, reviewer_env
from autoreview_lib.report import REPORT_SCHEMA, ReportError, extract_report


class RepositoryCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="autoreview-test-")
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        (self.repo / "app.txt").write_text("before\n", encoding="utf-8")
        self.git("add", "app.txt")
        self.git("commit", "-qm", "initial")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, check=True)

    def test_local_bundle_includes_tracked_and_untracked_changes(self) -> None:
        (self.repo / "app.txt").write_text("after\n", encoding="utf-8")
        (self.repo / "new.txt").write_text("new\n", encoding="utf-8")
        bundle = build_bundle(self.repo, "local", None, "HEAD", 100_000)
        self.assertIn("+after", bundle.content)
        self.assertIn("untracked file: new.txt", bundle.content)

    def test_sensitive_untracked_path_fails_closed(self) -> None:
        (self.repo / ".env").write_text("TOKEN=placeholder\n", encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "sensitive untracked path"):
            build_bundle(self.repo, "local", None, "HEAD", 100_000)

    def test_aws_credentials_fail_closed(self) -> None:
        credentials = self.repo / ".aws" / "credentials"
        credentials.parent.mkdir()
        access_key = "ABCDEFGHIJKLMNOP" + "QRST"
        secret_key = "abcdefghijklmnopqrstuvwxyz" + "1234567890ABCD"
        credentials.write_text(
            f"[default]\naws_access_key_id={access_key}\n"
            f"aws_secret_access_key={secret_key}\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(BundleError, "sensitive untracked path"):
            build_bundle(self.repo, "local", None, "HEAD", 100_000)

    def test_git_credentials_fail_closed(self) -> None:
        (self.repo / ".git-credentials").write_text("credential fixture\n", encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "sensitive untracked path"):
            build_bundle(self.repo, "local", None, "HEAD", 100_000)

    def test_untracked_symlink_fails_closed(self) -> None:
        outside = self.repo.parent / "outside-review.txt"
        outside.write_text("private external content\n", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        (self.repo / "notes.txt").symlink_to(outside)
        with self.assertRaisesRegex(BundleError, "untracked symlink"):
            build_bundle(self.repo, "local", None, "HEAD", 100_000)

    def test_sensitive_tracked_path_fails_closed(self) -> None:
        tracked = self.repo / ".env"
        tracked.write_text("TOKEN=placeholder\n", encoding="utf-8")
        self.git("add", ".env")
        self.git("commit", "-qm", "add fixture")
        tracked.write_text("TOKEN=changed\n", encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "sensitive tracked path"):
            build_bundle(self.repo, "local", None, "HEAD", 100_000)

    def test_unquoted_secret_like_value_fails_closed(self) -> None:
        secret_like = "abcdefghijklmnopqrstuvwxyz" + "123456"
        (self.repo / "app.txt").write_text(
            f"api_key={secret_like}\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(BundleError, "secret-like content"):
            build_bundle(self.repo, "local", None, "HEAD", 100_000)

    def test_oversized_bundle_fails_closed(self) -> None:
        (self.repo / "app.txt").write_text("x" * 10_000, encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "exceeds limit"):
            build_bundle(self.repo, "local", None, "HEAD", 100)

    def test_oversized_untracked_file_is_rejected_before_open(self) -> None:
        (self.repo / "large.txt").write_text("x" * 1_000, encoding="utf-8")
        with patch.object(Path, "open", side_effect=AssertionError("file should not be opened")):
            with self.assertRaisesRegex(BundleError, "untracked file exceeds limit"):
                build_bundle(self.repo, "local", None, "HEAD", 100_000, max_file_bytes=100)


class EngineAndReportCase(unittest.TestCase):
    def test_schema_avoids_unsupported_draft_marker(self) -> None:
        self.assertNotIn("$schema", REPORT_SCHEMA)

    def test_codex_command_is_ephemeral_and_read_only(self) -> None:
        command = codex_command(Path("/repo"), Path("schema.json"), Path("result.json"), None)
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn('default_permissions="autoreview"', command)
        self.assertIn('shell_environment_policy.inherit="none"', command)
        self.assertNotIn("--sandbox", command)
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-sol")
        self.assertIn('model_reasoning_effort="high"', command)

    def test_reviewer_environment_excludes_credentials(self) -> None:
        source = {
            "HOME": "/home/reviewer",
            "PATH": "/usr/bin",
            "LANG": "C.UTF-8",
            "OPENAI_API_KEY": "secret",
            "ANTHROPIC_API_KEY": "secret",
            "GH_TOKEN": "secret",
        }
        self.assertEqual(
            reviewer_env(source),
            {"HOME": "/home/reviewer", "PATH": "/usr/bin", "LANG": "C.UTF-8"},
        )

    def test_codex_command_accepts_an_explicit_model_override(self) -> None:
        command = codex_command(
            Path("/repo"), Path("schema.json"), Path("result.json"), "gpt-5.5"
        )
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.5")
        self.assertIn('model_reasoning_effort="high"', command)

    def test_claude_command_uses_safe_mode_and_read_only_tools(self) -> None:
        command = claude_command(None)
        self.assertIn("--safe-mode", command)
        self.assertIn("--strict-mcp-config", command)
        self.assertNotIn("--allowedTools", command)
        self.assertIn(
            "Bash,Edit,Write,NotebookEdit,Read,Grep,Glob,WebFetch,WebSearch,mcp__*",
            command,
        )

    def test_extracts_claude_structured_output(self) -> None:
        expected = {
            "findings": [],
            "overall_correctness": "patch is correct",
            "summary": "No findings.",
        }
        raw = json.dumps({"structured_output": expected})
        self.assertEqual(extract_report(raw), expected)

    def test_rejects_contradictory_clean_report(self) -> None:
        raw = json.dumps({
            "findings": [],
            "overall_correctness": "patch is incorrect",
            "summary": "Contradictory result.",
        })
        with self.assertRaisesRegex(ReportError, "contradictory"):
            extract_report(raw)


if __name__ == "__main__":
    unittest.main()
