from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from implementation_delegator_lib.contract import (
    DelegationError,
    correction_prompt,
    implementation_prompt,
    validate_work_order,
)
from implementation_delegator_lib.engine import codex_command
from implementation_delegator_lib.repository import resolve_repository


REPORT = "# Implementation report\n\nStatus: COMPLETE\n\nTests passed."


class ImplementationDelegatorCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="implementation-delegator-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.runner = Path(__file__).with_name("delegate-implementation")

    def test_contract_preserves_scope_and_allows_truthful_stop(self) -> None:
        prompt = implementation_prompt("Goal: fix the parser")
        self.assertIn("Execute exactly the bounded work order", prompt)
        self.assertIn("STOP and report the exact blocker", prompt)
        self.assertIn("Do not commit, push", prompt)
        self.assertIn("at most three test workers", prompt)
        correction = correction_prompt("Fix the failing parser test")
        self.assertIn("same delegated implementation session", correction)
        self.assertIn("Address only", correction)

    def test_work_order_validation(self) -> None:
        with self.assertRaisesRegex(DelegationError, "empty"):
            validate_work_order("  ", 100)
        with self.assertRaisesRegex(DelegationError, "exceeds limit"):
            validate_work_order("x" * 101, 100)

    def test_resolves_repository_from_nested_directory(self) -> None:
        nested = self.repo / "src" / "module"
        nested.mkdir(parents=True)
        self.assertEqual(resolve_repository(nested), self.repo.resolve())

    def test_fresh_command_is_full_access_resumable_sol_high(self) -> None:
        command = codex_command(self.repo, Path("report.md"), None)
        self.assertEqual(command[:2], ["codex", "exec"])
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-sol")
        self.assertIn('model_reasoning_effort="high"', command)
        self.assertIn("--cd", command)
        self.assertNotIn("--ephemeral", command)
        self.assertNotIn("timeout", " ".join(command))

    def test_fast_changes_only_service_tier(self) -> None:
        standard = codex_command(self.repo, Path("report.md"), None)
        fast = codex_command(self.repo, Path("report.md"), None, fast=True)
        self.assertNotIn("fast_mode", standard)
        self.assertIn("fast_mode", fast)
        self.assertIn('service_tier="fast"', fast)
        self.assertEqual(fast[fast.index("--model") + 1], "gpt-5.6-sol")
        self.assertIn('model_reasoning_effort="high"', fast)

    def test_resume_preserves_session_model_without_cd(self) -> None:
        command = codex_command(
            self.repo,
            Path("report.md"),
            None,
            resume="019f-session",
        )
        self.assertEqual(command[:3], ["codex", "exec", "resume"])
        self.assertIn("019f-session", command)
        self.assertNotIn("--cd", command)
        self.assertNotIn("--model", command)
        self.assertNotIn('model_reasoning_effort="high"', command)

    def test_resume_model_override_is_explicit(self) -> None:
        command = codex_command(
            self.repo,
            Path("report.md"),
            "gpt-5.6-terra",
            resume="019f-session",
        )
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-terra")
        self.assertIn('model_reasoning_effort="high"', command)

    def test_help_has_no_timeout_option(self) -> None:
        result = subprocess.run(
            [str(self.runner), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--timeout", result.stdout)
        self.assertIn("--heartbeat-seconds", result.stdout)

    def test_dry_run_declares_unbounded_runtime(self) -> None:
        result = subprocess.run(
            [str(self.runner), "--dry-run", "--repo", str(self.repo)],
            input="Goal: implement a parser fix",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Runtime timeout: none", result.stdout)
        self.assertIn("Claude Code -> Codex", result.stdout)
        self.assertIn("gpt-5.6-sol", result.stdout)

    def test_fake_codex_streams_heartbeat_and_saves_session(self) -> None:
        fake_bin = self.repo / "fake-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            f"""#!/usr/bin/env python3
import json, pathlib, sys, time
args = sys.argv[1:]
sys.stdin.read()
print(json.dumps({{'type': 'thread.started', 'thread_id': 'test-session'}}), flush=True)
print(json.dumps({{'type': 'turn.started'}}), flush=True)
time.sleep(0.15)
pathlib.Path(args[args.index('--output-last-message') + 1]).write_text({REPORT!r})
print(json.dumps({{'type': 'turn.completed'}}), flush=True)
""",
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        output_root = self.repo / "runs"
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        result = subprocess.run(
            [
                str(self.runner),
                "--repo",
                str(self.repo),
                "--output-root",
                str(output_root),
                "--heartbeat-seconds",
                "0.05",
            ],
            input="Goal: implement a parser fix",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), REPORT)
        run_dir = next(output_root.glob("*/"))
        self.assertEqual((run_dir / "session-id.txt").read_text().strip(), "test-session")
        self.assertEqual((run_dir / "report.md").read_text().strip(), REPORT)
        self.assertIn("heartbeat", result.stderr)
        self.assertIn("timeout disabled", result.stderr)
        self.assertIn("tail -n 200 -f ", result.stderr)
        self.assertTrue((run_dir / "state-before.txt").is_file())
        self.assertTrue((run_dir / "state-after.txt").is_file())

    def test_termination_stops_active_worker_group(self) -> None:
        fake_bin = self.repo / "slow-fake-bin"
        fake_bin.mkdir()
        pid_file = self.repo / "worker.pid"
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            """#!/usr/bin/env python3
import json, os, pathlib, sys, time
pathlib.Path(os.environ['FAKE_WORKER_PID']).write_text(str(os.getpid()))
sys.stdin.read()
print(json.dumps({'type': 'thread.started', 'thread_id': 'slow-session'}), flush=True)
time.sleep(60)
""",
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        env["FAKE_WORKER_PID"] = str(pid_file)
        runner = subprocess.Popen(
            [str(self.runner), "--repo", str(self.repo), "--heartbeat-seconds", "0.05"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        assert runner.stdin is not None
        runner.stdin.write("Goal: exercise interruption")
        runner.stdin.close()
        deadline = time.monotonic() + 3
        while not pid_file.is_file() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(pid_file.is_file(), "fake worker did not start")
        worker_pid = int(pid_file.read_text())
        runner.terminate()
        returncode = runner.wait(timeout=10)
        assert runner.stdout is not None
        assert runner.stderr is not None
        runner.stdout.close()
        runner.stderr.close()
        self.assertEqual(returncode, 130)
        with self.assertRaises(ProcessLookupError):
            os.kill(worker_pid, 0)

    def test_runs_from_standalone_skill_copy(self) -> None:
        copied = self.repo / "implementation-delegator"
        shutil.copytree(Path(__file__).resolve().parents[1], copied)
        result = subprocess.run(
            [
                str(copied / "scripts" / "delegate-implementation"),
                "--dry-run",
                "--repo",
                str(self.repo),
            ],
            input="Goal: validate the standalone copy",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Runtime timeout: none", result.stdout)


if __name__ == "__main__":
    unittest.main()
