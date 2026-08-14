from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from second_opinion_lib.consultation import (
    ConsultationError,
    consultation_prompt,
    extract_claude_report,
    validate_brief,
    validate_report,
)
from second_opinion_lib.repository import resolve_repository
from second_opinion_lib.structured_engines import (
    claude_command,
    codex_command,
    reviewer_env,
    run_structured_engine,
)


REPORT = "# Avaliação arquitetural\n\nA fronteira atual é adequada para este contexto."


class ConsultationCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="second-opinion-repo-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "architecture.txt").write_text("modular monolith\n", encoding="utf-8")
        self.runner = Path(__file__).with_name("second-opinion")

    def test_prompt_requests_topic_shaped_markdown_without_implementation(self) -> None:
        prompt = consultation_prompt("Questão: qual estratégia de migração devemos usar?")
        self.assertIn("Do not implement", prompt)
        self.assertIn("independently inspect the repository", prompt.lower())
        self.assertIn("complete Markdown report", prompt)
        self.assertIn("no fixed sections", prompt)
        self.assertNotIn("JSON object", prompt)

    def test_brief_validation(self) -> None:
        with self.assertRaisesRegex(ConsultationError, "empty"):
            validate_brief("  ", 1000)
        with self.assertRaisesRegex(ConsultationError, "exceeds limit"):
            validate_brief("x" * 101, 100)
        with self.assertRaisesRegex(ConsultationError, "secret-like"):
            validate_brief("api_key=" + "a" * 32, 1000)

    def test_extracts_claude_markdown_report(self) -> None:
        raw = json.dumps({"type": "result", "result": REPORT})
        self.assertEqual(extract_claude_report(raw), REPORT)
        with self.assertRaisesRegex(ConsultationError, "empty Markdown"):
            extract_claude_report(json.dumps({"type": "result", "result": "  "}))
        with self.assertRaisesRegex(ConsultationError, "empty Markdown"):
            validate_report(None)

    def test_resolves_repository_from_nested_directory(self) -> None:
        nested = self.repo / "src" / "module"
        nested.mkdir(parents=True)
        self.assertEqual(resolve_repository(nested), self.repo.resolve())

    def test_rejects_non_repository_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="second-opinion-non-repo-") as temp:
            with self.assertRaisesRegex(ConsultationError, "invalid repository"):
                resolve_repository(Path(temp))

    def test_commands_do_not_request_structured_output(self) -> None:
        codex = codex_command(self.repo, Path("report.md"), None)
        self.assertIn("--output-last-message", codex)
        self.assertIn("--json", codex)
        self.assertNotIn("--output-schema", codex)
        claude = claude_command(None)
        self.assertEqual(claude[claude.index("--output-format") + 1], "stream-json")
        self.assertNotIn("--json-schema", claude)
        self.assertIn("--dangerously-skip-permissions", claude)
        self.assertEqual(claude[claude.index("--tools") + 1], "default")

    def test_codex_fast_is_explicit_and_keeps_sol_high(self) -> None:
        standard = codex_command(self.repo, Path("report.md"), None)
        fast = codex_command(self.repo, Path("report.md"), None, fast=True)
        self.assertNotIn("fast_mode", standard)
        self.assertNotIn('service_tier="fast"', standard)
        self.assertEqual(fast[fast.index("--model") + 1], "gpt-5.6-sol")
        self.assertIn('model_reasoning_effort="high"', fast)
        self.assertEqual(fast[fast.index("--enable") + 1], "fast_mode")
        self.assertIn('service_tier="fast"', fast)

    def test_fast_is_rejected_for_claude(self) -> None:
        result = subprocess.run(
            [
                str(self.runner),
                "--dry-run",
                "--engine",
                "claude",
                "--fast",
                "--repo",
                str(self.repo),
            ],
            input="Question: Should we split this module?",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--fast is valid only with --engine codex", result.stderr)

    def test_filtered_environment_excludes_credentials(self) -> None:
        source = {
            "HOME": "/home/reviewer",
            "PATH": "/usr/bin",
            "LANG": "C.UTF-8",
            "OPENAI_API_KEY": "secret",
            "ANTHROPIC_API_KEY": "secret",
        }
        self.assertEqual(
            reviewer_env(source),
            {"HOME": "/home/reviewer", "PATH": "/usr/bin", "LANG": "C.UTF-8"},
        )

    def test_dry_run_is_markdown_and_has_no_schema_flags(self) -> None:
        result = subprocess.run(
            [str(self.runner), "--dry-run", "--engine", "codex", "--repo", str(self.repo)],
            input="Question: Should we split this module?",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("# Second Opinion — dry run"))
        self.assertIn(f"Repository: `{self.repo.resolve()}`", result.stdout)
        self.assertIn("Repository access: full", result.stdout)
        self.assertIn("Fast: false", result.stdout)
        self.assertNotIn("--output-schema", result.stdout)
        self.assertNotIn("--json-schema", result.stdout)

    def test_dry_run_exposes_fast_without_changing_model_or_reasoning(self) -> None:
        result = subprocess.run(
            [
                str(self.runner),
                "--dry-run",
                "--fast",
                "--engine",
                "codex",
                "--repo",
                str(self.repo),
            ],
            input="Question: Should we split this module?",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fast: true", result.stdout)
        self.assertIn("gpt-5.6-sol", result.stdout)
        self.assertIn('model_reasoning_effort="high"', result.stdout)
        self.assertIn("fast_mode", result.stdout)
        self.assertIn('service_tier="fast"', result.stdout)

    def test_runs_from_a_standalone_skill_copy(self) -> None:
        copied = self.repo / "second-opinion"
        shutil.copytree(Path(__file__).resolve().parents[1], copied)
        result = subprocess.run(
            [str(copied / "scripts" / "second-opinion"), "--dry-run", "--repo", str(self.repo)],
            input="Question: Is this standalone copy functional?",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("# Second Opinion"))

    def test_codex_returns_markdown_and_saves_report(self) -> None:
        fake_bin = self.repo / "fake-codex-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            f"""#!/usr/bin/env python3
import json, pathlib, sys, time
args = sys.argv[1:]
sys.stdin.read()
print(json.dumps({{'type': 'thread.started', 'thread_id': 'test'}}), flush=True)
time.sleep(0.25)
pathlib.Path(args[args.index('--output-last-message') + 1]).write_text({REPORT!r})
print(json.dumps({{'type': 'turn.completed'}}), flush=True)
""",
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        output_root = self.repo / "codex-runs"
        result = self._run_with_fake(fake_bin, output_root, "codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), REPORT)
        report_file = next(output_root.glob("*/report.md"))
        self.assertEqual(report_file.read_text(encoding="utf-8").strip(), REPORT)
        self.assertIn("heartbeat", result.stderr)
        self.assertIn("codex advisor connected", result.stderr)
        self.assertIn("tail -n 200 -f ", result.stderr)

    def test_claude_returns_markdown_and_saves_report(self) -> None:
        fake_bin = self.repo / "fake-claude-bin"
        fake_bin.mkdir()
        fake_claude = fake_bin / "claude"
        fake_claude.write_text(
            f"""#!/usr/bin/env python3
import json, sys, time
sys.stdin.read()
print(json.dumps({{'type': 'system', 'subtype': 'init'}}), flush=True)
time.sleep(0.25)
print(json.dumps({{'type': 'result', 'result': {REPORT!r}}}), flush=True)
""",
            encoding="utf-8",
        )
        fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IXUSR)
        output_root = self.repo / "claude-runs"
        result = self._run_with_fake(fake_bin, output_root, "claude")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), REPORT)
        self.assertEqual(next(output_root.glob("*/report.md")).read_text().strip(), REPORT)
        self.assertIn("claude advisor connected", result.stderr)

    def test_engine_failure_returns_markdown_and_exit_two(self) -> None:
        fake_bin = self.repo / "failure-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            """#!/usr/bin/env python3
import json, sys
sys.stdin.read()
print(json.dumps({'type': 'item.started', 'item': {'id': 'x', 'type': 'command_execution', 'command': 'RAW_SECRET_COMMAND'}}), flush=True)
raise SystemExit(7)
""",
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        output_root = self.repo / "failure-runs"
        result = self._run_with_fake(fake_bin, output_root, "codex")
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stdout.startswith("# Segunda opinião indisponível"))
        self.assertIn("failed with exit code 7", result.stdout)
        self.assertNotIn("RAW_SECRET_COMMAND", result.stdout + result.stderr)
        events = next(output_root.glob("*/advisor-events.jsonl"))
        self.assertIn("RAW_SECRET_COMMAND", events.read_text(encoding="utf-8"))

    def test_timeout_kills_advisor_descendants(self) -> None:
        fake_bin = self.repo / "timeout-bin"
        fake_bin.mkdir()
        child_pid_file = fake_bin / "child.pid"
        child_program = (
            "import os, pathlib, signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"pathlib.Path({str(child_pid_file)!r}).write_text(str(os.getpid())); "
            "time.sleep(10)"
        )
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            f"""#!/usr/bin/env python3
import json, subprocess, sys
sys.stdin.read()
subprocess.Popen([sys.executable, '-c', {json.dumps(child_program)}], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(json.dumps({{'type': 'thread.started', 'thread_id': 'timeout'}}), flush=True)
""",
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        run_dir = self.repo / "timeout-run"
        run_dir.mkdir()
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        with patch.dict(os.environ, env, clear=True), patch(
            "second_opinion_lib.structured_engines.TERMINATION_GRACE_SECONDS", 0.2
        ):
            run = run_structured_engine(
                "codex",
                self.repo,
                "Question: Synthetic timeout?",
                None,
                run_dir,
                timeout_seconds=0.3,
                heartbeat_seconds=0.1,
            )
        self.assertTrue(run.timed_out)
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)

    def _run_with_fake(self, fake_bin: Path, output_root: Path, engine: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        return subprocess.run(
            [
                str(self.runner),
                "--engine",
                engine,
                "--repo",
                str(self.repo),
                "--output-root",
                str(output_root),
                "--timeout-seconds",
                "2",
                "--heartbeat-seconds",
                "0.1",
            ],
            input="Question: Is this architecture appropriate?",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
            timeout=5,
        )


if __name__ == "__main__":
    unittest.main()
