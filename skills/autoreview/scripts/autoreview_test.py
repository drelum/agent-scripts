from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from autoreview_lib.bundle import BundleError, build_bundle
from autoreview_lib.engines import (
    EngineError,
    claude_command,
    codex_command,
    reviewer_env,
    run_engine,
)
from autoreview_lib.report import REPORT_SCHEMA, ReportError, extract_report, render_markdown


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

    def test_unborn_repository_reviews_staged_and_untracked_files(self) -> None:
        unborn = self.repo / "unborn"
        unborn.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=unborn, check=True)
        (unborn / "staged.txt").write_text("staged\n", encoding="utf-8")
        subprocess.run(["git", "add", "staged.txt"], cwd=unborn, check=True)
        (unborn / "staged.txt").write_text("final staged content\n", encoding="utf-8")
        (unborn / "untracked.txt").write_text("untracked\n", encoding="utf-8")

        bundle = build_bundle(unborn, "local", None, "HEAD", 100_000)

        self.assertEqual(bundle.label, "initial working tree (no HEAD)")
        self.assertIn("initial file: staged.txt", bundle.content)
        self.assertIn("final staged content", bundle.content)
        self.assertIn("initial file: untracked.txt", bundle.content)

    def test_auto_mode_selects_initial_worktree_without_head(self) -> None:
        unborn = self.repo / "unborn-auto"
        unborn.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=unborn, check=True)
        (unborn / "app.txt").write_text("initial app\n", encoding="utf-8")

        bundle = build_bundle(unborn, "auto", None, "HEAD", 100_000)

        self.assertEqual(bundle.label, "initial working tree (no HEAD)")
        self.assertIn("initial file: app.txt", bundle.content)

    def test_cli_dry_run_accepts_repository_without_head(self) -> None:
        unborn = self.repo / "unborn-cli"
        unborn.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=unborn, check=True)
        (unborn / "app.txt").write_text("initial app\n", encoding="utf-8")
        script = Path(__file__).with_name("autoreview")

        result = subprocess.run(
            [str(script), "--repo", str(unborn), "--mode", "auto", "--dry-run"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Alvo: initial working tree (no HEAD)", result.stdout)

    def test_unborn_repository_still_screens_sensitive_paths(self) -> None:
        unborn = self.repo / "unborn-sensitive"
        unborn.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=unborn, check=True)
        (unborn / ".git-credentials").write_text("fixture\n", encoding="utf-8")

        with self.assertRaisesRegex(BundleError, "sensitive path in initial working tree"):
            build_bundle(unborn, "local", None, "HEAD", 100_000)

    def test_untracked_environment_file_is_not_path_blocked(self) -> None:
        (self.repo / ".env").write_text("TOKEN=placeholder\n", encoding="utf-8")
        bundle = build_bundle(self.repo, "local", None, "HEAD", 100_000)
        self.assertIn("untracked file: .env", bundle.content)

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

    def test_tracked_environment_file_is_not_path_blocked(self) -> None:
        tracked = self.repo / ".env"
        tracked.write_text("TOKEN=placeholder\n", encoding="utf-8")
        self.git("add", ".env")
        self.git("commit", "-qm", "add fixture")
        tracked.write_text("TOKEN=changed\n", encoding="utf-8")
        bundle = build_bundle(self.repo, "local", None, "HEAD", 100_000)
        self.assertIn("+TOKEN=changed", bundle.content)

    def test_unquoted_secret_like_value_fails_closed(self) -> None:
        secret_like = "abcdefghijklmnopqrstuvwxyz" + "123456"
        (self.repo / "app.txt").write_text(
            f"api_key={secret_like}\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(BundleError, "secret-like content"):
            build_bundle(self.repo, "local", None, "HEAD", 100_000)

    def test_generic_token_and_bearer_values_fail_closed(self) -> None:
        generic = "abcdefghijklmnopqrstuvwxyz" + "123456"
        bearer = "header.payload." + "abcdefghijklmnopqrstuvwxyz123456"
        (self.repo / "app.txt").write_text(
            f'token="{generic}"\nAuthorization: Bearer {bearer}\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(BundleError, "secret-like content"):
            build_bundle(self.repo, "local", None, "HEAD", 100_000)

    def test_password_values_are_not_screened(self) -> None:
        (self.repo / "app.txt").write_text(
            "\n".join([
                "const password = smartpedPasswordFromDetail(detail);",
                "const fallbackPassword = process.env.SMARTPED_PASSWORD;",
                'const testPassword = "abcdefghijklmnopqrstuvwxyz123456";',
            ]),
            encoding="utf-8",
        )
        bundle = build_bundle(self.repo, "local", None, "HEAD", 100_000)
        self.assertIn("smartpedPasswordFromDetail", bundle.content)
        self.assertIn("SMARTPED_PASSWORD", bundle.content)
        self.assertIn("abcdefghijklmnopqrstuvwxyz123456", bundle.content)

    def test_merge_commit_requires_an_explicit_comparison(self) -> None:
        self.git("checkout", "-qb", "feature")
        (self.repo / "feature.txt").write_text("feature\n", encoding="utf-8")
        self.git("add", "feature.txt")
        self.git("commit", "-qm", "feature")
        self.git("checkout", "-q", "-")
        (self.repo / "main.txt").write_text("main\n", encoding="utf-8")
        self.git("add", "main.txt")
        self.git("commit", "-qm", "main")
        self.git("merge", "--no-ff", "feature", "-qm", "merge")
        with self.assertRaisesRegex(BundleError, "merge commits require"):
            build_bundle(self.repo, "commit", None, "HEAD", 100_000)

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
    def test_rejects_non_finite_runtime_intervals(self) -> None:
        script = Path(__file__).with_name("autoreview")
        for option, value in (("--timeout-seconds", "nan"), ("--heartbeat-seconds", "inf")):
            with self.subTest(option=option, value=value):
                result = subprocess.run(
                    [str(script), option, value, "--dry-run"],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("finite number greater than zero", result.stderr)

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
        self.assertIn("--json", command)
        self.assertNotIn('".env*"="deny"', command)
        self.assertNotIn('"**/.env*"="deny"', command)

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

    def test_codex_fast_is_explicit_and_keeps_sol_high(self) -> None:
        standard = codex_command(Path("/repo"), Path("schema.json"), Path("result.json"), None)
        fast = codex_command(
            Path("/repo"), Path("schema.json"), Path("result.json"), None, fast=True
        )
        self.assertNotIn("fast_mode", standard)
        self.assertNotIn('service_tier="fast"', standard)
        self.assertEqual(fast[fast.index("--model") + 1], "gpt-5.6-sol")
        self.assertIn('model_reasoning_effort="high"', fast)
        self.assertIn("--enable", fast)
        self.assertEqual(fast[fast.index("--enable") + 1], "fast_mode")
        self.assertIn('service_tier="fast"', fast)

    def test_fast_is_rejected_for_claude(self) -> None:
        script = Path(__file__).with_name("autoreview")
        result = subprocess.run(
            [str(script), "--engine", "claude", "--fast", "--dry-run"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--fast is valid only with --engine codex", result.stderr)

    def test_claude_command_uses_safe_mode_and_read_only_tools(self) -> None:
        command = claude_command(None)
        self.assertIn("--safe-mode", command)
        self.assertIn("--strict-mcp-config", command)
        self.assertNotIn("--allowedTools", command)
        self.assertIn(
            "Bash,Edit,Write,NotebookEdit,Read,Grep,Glob,WebFetch,WebSearch,mcp__*",
            command,
        )
        self.assertEqual(command[command.index("--output-format") + 1], "stream-json")
        self.assertIn("--verbose", command)

    def test_incremental_logs_and_filtered_progress(self) -> None:
        report = {
            "findings": [],
            "overall_correctness": "patch is correct",
            "summary": "No findings.",
        }
        with tempfile.TemporaryDirectory(prefix="autoreview-engine-") as temp:
            root = Path(temp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_codex = fake_bin / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys, time\n"
                "args = sys.argv[1:]\n"
                "out = pathlib.Path(args[args.index('--output-last-message') + 1])\n"
                "print(json.dumps({'type':'thread.started'}), flush=True)\n"
                "print(json.dumps({'type':'item.started','item':{'type':'command_execution','command':'RAW_PRIVATE_COMMAND'}}), flush=True)\n"
                "time.sleep(0.4)\n"
                f"out.write_text({json.dumps(json.dumps(report))}, encoding='utf-8')\n"
                "print(json.dumps({'type':'turn.completed'}), flush=True)\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            progress: list[str] = []
            outcome: list[object] = []

            def invoke() -> None:
                try:
                    outcome.append(run_engine(
                        "codex", root, "review", None,
                        timeout_seconds=5,
                        heartbeat_seconds=0.1,
                        stream_engine_output=True,
                        output_root=root / "runs",
                        progress=progress.append,
                    ))
                except Exception as error:  # pragma: no cover - assertion reports it
                    outcome.append(error)

            with patch.dict(os.environ, {"PATH": f"{fake_bin}:{os.environ['PATH']}"}):
                thread = threading.Thread(target=invoke)
                thread.start()
                deadline = time.monotonic() + 2
                events_log: Path | None = None
                while time.monotonic() < deadline:
                    run_messages = [item for item in progress if item.startswith("run directory: ")]
                    if run_messages:
                        events_log = Path(run_messages[0].removeprefix("run directory: ")) / "reviewer-events.jsonl"
                        if events_log.exists() and "thread.started" in events_log.read_text(encoding="utf-8"):
                            break
                    time.sleep(0.02)
                self.assertIsNotNone(events_log)
                self.assertTrue(thread.is_alive(), "event log should be written before review completion")
                thread.join(timeout=3)

            self.assertFalse(thread.is_alive())
            self.assertEqual(len(outcome), 1)
            self.assertNotIsInstance(outcome[0], Exception)
            run = outcome[0]
            self.assertEqual(run.result, json.dumps(report))  # type: ignore[union-attr]
            self.assertTrue(any(item.startswith("heartbeat:") for item in progress))
            self.assertTrue(any(item.startswith("follow events: tail -n 200 -f ") for item in progress))
            self.assertTrue(any(item.startswith("follow stderr: tail -n 200 -f ") for item in progress))
            self.assertIn("read-only review step started", progress)
            self.assertNotIn("RAW_PRIVATE_COMMAND", "\n".join(progress))
            self.assertIn("RAW_PRIVATE_COMMAND", run.events_log.read_text(encoding="utf-8"))  # type: ignore[union-attr]

    def test_internal_timeout_preserves_partial_logs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autoreview-timeout-") as temp:
            root = Path(temp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_codex = fake_bin / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env python3\n"
                "import json, signal, time\n"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                "print(json.dumps({'type':'thread.started'}), flush=True)\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            progress: list[str] = []
            started = time.monotonic()
            with patch.dict(os.environ, {"PATH": f"{fake_bin}:{os.environ['PATH']}"}), patch(
                "autoreview_lib.engines.PROCESS_TERMINATION_GRACE_SECONDS", 0.05
            ):
                with self.assertRaisesRegex(EngineError, "internal timeout reached"):
                    run_engine(
                        "codex", root, "review", None,
                        timeout_seconds=0.2,
                        heartbeat_seconds=0.05,
                        output_root=root / "runs",
                        progress=progress.append,
                    )
            self.assertLess(time.monotonic() - started, 2)
            run_dir = Path(next(
                item.removeprefix("run directory: ")
                for item in progress if item.startswith("run directory: ")
            ))
            self.assertIn("thread.started", (run_dir / "reviewer-events.jsonl").read_text(encoding="utf-8"))
            self.assertTrue(any(item.startswith("heartbeat:") for item in progress))

    def test_internal_timeout_reaps_a_terminated_parent_without_waiting_full_grace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autoreview-timeout-reap-") as temp:
            root = Path(temp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_codex = fake_bin / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env python3\n"
                "import time\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            started = time.monotonic()
            with patch.dict(os.environ, {"PATH": f"{fake_bin}:{os.environ['PATH']}"}):
                with self.assertRaisesRegex(EngineError, "internal timeout reached"):
                    run_engine(
                        "codex", root, "review", None,
                        timeout_seconds=0.1,
                        heartbeat_seconds=0.05,
                        output_root=root / "runs",
                    )
            self.assertLess(time.monotonic() - started, 1)

    def test_rejects_symlinked_or_shared_output_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autoreview-output-root-") as temp:
            root = Path(temp)
            private = root / "private"
            private.mkdir(mode=0o700)
            linked = root / "linked"
            linked.symlink_to(private, target_is_directory=True)
            with self.assertRaisesRegex(EngineError, "not a real directory"):
                run_engine("codex", root, "review", None, output_root=linked)

            shared = root / "shared"
            shared.mkdir(mode=0o755)
            with self.assertRaisesRegex(EngineError, "must not be accessible"):
                run_engine("codex", root, "review", None, output_root=shared)

    def test_engine_failure_does_not_echo_raw_stderr(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autoreview-engine-failure-") as temp:
            root = Path(temp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_codex = fake_bin / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "print('RAW_PRIVATE_STDERR', file=sys.stderr, flush=True)\n"
                "raise SystemExit(7)\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            progress: list[str] = []
            with patch.dict(os.environ, {"PATH": f"{fake_bin}:{os.environ['PATH']}"}):
                with self.assertRaises(EngineError) as raised:
                    run_engine(
                        "codex", root, "review", None,
                        output_root=root / "runs",
                        progress=progress.append,
                    )
            message = str(raised.exception)
            self.assertNotIn("RAW_PRIVATE_STDERR", message)
            run_dir = Path(next(
                item.removeprefix("run directory: ")
                for item in progress if item.startswith("run directory: ")
            ))
            self.assertIn("RAW_PRIVATE_STDERR", (run_dir / "reviewer-stderr.log").read_text(encoding="utf-8"))

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

    def test_renders_human_markdown_after_structured_validation(self) -> None:
        report = {
            "findings": [
                {
                    "title": "Broken normal flow",
                    "severity": "P1",
                    "body": "The changed branch skips persistence.",
                    "file": "src/save.ts",
                    "line": 42,
                }
            ],
            "overall_correctness": "patch is incorrect",
            "summary": "One actionable finding.",
        }
        markdown = render_markdown(
            report,
            engine="codex",
            target="local changes",
            duration_seconds=1.25,
            report_file="/tmp/autoreview/report.md",
        )
        self.assertTrue(markdown.startswith("Status: FINDINGS\n"))
        self.assertIn("# Execução", markdown)
        self.assertIn("## P1 — Broken normal flow", markdown)
        self.assertIn("`src/save.ts`", markdown)
        self.assertNotIn('{"findings"', markdown)

    def test_cli_returns_success_for_clean_and_findings_reports(self) -> None:
        cases = [
            (
                "CLEAN",
                {
                    "findings": [],
                    "overall_correctness": "patch is correct",
                    "summary": "No actionable findings.",
                },
            ),
            (
                "FINDINGS",
                {
                    "findings": [
                        {
                            "title": "Broken normal flow",
                            "severity": "P1",
                            "body": "The changed branch skips persistence.",
                            "file": "src/save.ts",
                            "line": 42,
                        }
                    ],
                    "overall_correctness": "patch is incorrect",
                    "summary": "One actionable finding.",
                },
            ),
        ]
        for expected_status, report in cases:
            with self.subTest(status=expected_status):
                with tempfile.TemporaryDirectory(prefix="autoreview-cli-") as temp:
                    root = Path(temp)
                    repo = root / "repo"
                    repo.mkdir()
                    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
                    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
                    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
                    (repo / "app.txt").write_text("before\n", encoding="utf-8")
                    subprocess.run(["git", "add", "app.txt"], cwd=repo, check=True)
                    subprocess.run(["git", "commit", "-qm", "initial"], cwd=repo, check=True)
                    (repo / "app.txt").write_text("after\n", encoding="utf-8")

                    fake_bin = root / "bin"
                    fake_bin.mkdir()
                    fake_codex = fake_bin / "codex"
                    fake_codex.write_text(
                        "#!/usr/bin/env python3\n"
                        "import json, pathlib, sys\n"
                        "args = sys.argv[1:]\n"
                        "sys.stdin.read()\n"
                        "out = pathlib.Path(args[args.index('--output-last-message') + 1])\n"
                        f"out.write_text({json.dumps(json.dumps(report))}, encoding='utf-8')\n",
                        encoding="utf-8",
                    )
                    fake_codex.chmod(0o755)
                    env = os.environ.copy()
                    env["PATH"] = f"{fake_bin}:{env['PATH']}"
                    result = subprocess.run(
                        [
                            str(Path(__file__).with_name("autoreview")),
                            "--repo",
                            str(repo),
                            "--mode",
                            "local",
                            "--output-root",
                            str(root / "runs"),
                        ],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(result.stdout.startswith(f"Status: {expected_status}\n"))
                    self.assertIn("# Achados", result.stdout)
                    report_line = next(
                        line for line in result.stdout.splitlines() if line.startswith("- Relatório: ")
                    )
                    report_file = Path(report_line.removeprefix("- Relatório: ").strip("`"))
                    self.assertEqual(report_file.read_text(encoding="utf-8"), result.stdout)


if __name__ == "__main__":
    unittest.main()
