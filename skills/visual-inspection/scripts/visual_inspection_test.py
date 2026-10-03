from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from visual_inspection_lib.contract import (
    BUDGET_CHECK_COMMAND,
    VisualInspectionError,
    extract_report,
    inspection_prompt,
    render_report,
    validate_context,
    validate_evidence,
)
from visual_inspection_lib.engine import (
    close_browser_session,
    codex_command,
    run_worker,
    worker_env,
)
from visual_inspection_lib.runtime import (
    MAX_CONCURRENT_INSPECTIONS,
    ActiveVisualInspection,
    acquire_run_lock,
    create_run,
    open_evidence_directory,
    resolve_repository,
    validate_url,
)


def sample_report() -> dict[str, object]:
    return {
        "status": "pass",
        "summary": "The page rendered correctly.",
        "preflight": {
            "status": "pass",
            "evidence": "Target URL and ready state confirmed.",
        },
        "criteria": [
            {
                "criterion": "Page is visible",
                "status": "pass",
                "evidence": "Screenshot captured.",
            }
        ],
        "findings": [],
        "evidence_paths": ["/tmp/evidence.png"],
        "limitations": [],
    }


def execution_value(markdown: str, label: str) -> str:
    prefix = f"- {label}: "
    line = next(line for line in markdown.splitlines() if line.startswith(prefix))
    return line.removeprefix(prefix).strip().strip("`")


class VisualInspectionCase(unittest.TestCase):
    def setUp(self) -> None:
        self.auto_open = patch.dict(
            os.environ,
            {"VISUAL_INSPECTION_AUTO_OPEN": "0"},
        )
        self.auto_open.start()
        self.addCleanup(self.auto_open.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="visual-inspection-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def test_prompt_passes_full_context_and_repository(self) -> None:
        prompt = inspection_prompt(
            "Current user request: inspect the updated settings flow",
            self.repo,
            "https://example.com",
            "visual-test",
            Path("/tmp/visual-test"),
        )
        self.assertIn("complete task handoff", prompt)
        self.assertIn(str(self.repo), prompt)
        self.assertIn("Inspect repository context only when it helps", prompt)
        self.assertIn("load only `agent-browser skills get core` once", prompt)
        self.assertIn("do not load `core --full` or `dogfood`", prompt)
        self.assertIn("Never use Playwright", prompt)
        self.assertIn("Do not edit", prompt)
        self.assertIn("never pass `--full`", prompt)
        self.assertIn("set -euo pipefail", prompt)
        self.assertIn("Use 1366x768 when the handoff does not explicitly request", prompt)
        self.assertIn("State the actual viewport in the preflight evidence", prompt)
        self.assertIn("agent-browser set viewport 1366 768", prompt)
        self.assertNotIn("agent-browser set viewport 1440 900", prompt)
        self.assertIn("agent-browser snapshot -i -c -d 3", prompt)
        self.assertIn('find role button click --name "Submit"', prompt)
        self.assertIn("retry once", prompt)
        self.assertIn("try one visible candidate", prompt)
        self.assertIn("report the criterion as BLOCKED", prompt)
        self.assertIn("do not revisit completed criteria", prompt)
        self.assertIn("total runtime budget is 420s", prompt)
        self.assertIn("reserve the final 42s", prompt)
        self.assertIn("Confirm only that the target opens", prompt)
        self.assertIn("Keep domain-specific readiness", prompt)
        self.assertNotIn("90-second", prompt)
        self.assertNotIn("preflight.json", prompt)

    def test_prompt_shell_quotes_url_with_query_control_characters(self) -> None:
        prompt = inspection_prompt(
            "Current user request: inspect filtered orders",
            self.repo,
            "https://example.com/orders?filter=active&tab=open",
            "visual-test",
            Path("/tmp/visual-test"),
            timeout_seconds=420,
        )
        self.assertIn(
            "agent-browser open 'https://example.com/orders?filter=active&tab=open'",
            prompt,
        )
        self.assertIn("total runtime budget is 420s", prompt)
        self.assertIn("reserve the final 42s", prompt)

    def test_budget_check_uses_supplied_monotonic_deadline(self) -> None:
        for remaining, expected in [(60, "CONTINUE"), (-60, "FINALIZE")]:
            with self.subTest(expected=expected):
                result = subprocess.run(
                    ["bash", "-c", BUDGET_CHECK_COMMAND],
                    env={**os.environ, "VISUAL_INSPECTION_FINALIZE_AT":
                         str(time.monotonic() + remaining)},
                    text=True, capture_output=True, check=True,
                )
                self.assertEqual(result.stdout.strip(), expected)
        prompt = inspection_prompt(
            "Inspect settings", self.repo, "https://example.com",
            "visual-budget", self.root, timeout_seconds=240,
        )
        self.assertIn(BUDGET_CHECK_COMMAND, prompt)
        self.assertIn("after each browser command", prompt)
        self.assertIn("same shell invocation as each browser command", prompt)
        self.assertIn("reserve the final 24s", prompt)
        self.assertIn("keep overall FAIL", prompt)
        self.assertIn("unexercised or unproven criterion as BLOCKED", prompt)

    def test_worker_receives_deadline_and_can_finalize_before_hard_timeout(self) -> None:
        fake_bin = self.root / "budget-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            """#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time
args = sys.argv[1:]
command = sys.stdin.read()
deadline = float(os.environ['VISUAL_INSPECTION_FINALIZE_AT'])
before = subprocess.check_output(['bash', '-c', command], text=True).strip()
time.sleep(max(0, deadline - time.monotonic()) + 0.03)
after = subprocess.check_output(['bash', '-c', command], text=True).strip()
output = pathlib.Path(args[args.index('--output-last-message') + 1])
output.write_text(json.dumps({'before': before, 'after': after, 'deadline': deadline}))
""",
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        evidence = self.root / "budget-evidence"
        evidence.mkdir()
        progress: list[str] = []
        started = time.monotonic()
        with patch.dict(os.environ, {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "VISUAL_INSPECTION_FINALIZE_AT": "0",
        }):
            run = run_worker(
                self.repo, evidence, BUDGET_CHECK_COMMAND, "visual-budget",
                timeout_seconds=3, heartbeat_seconds=0.1, progress=progress.append,
            )
        result = json.loads(run.raw_report)
        self.assertFalse(run.timed_out)
        self.assertEqual(result["before"], "CONTINUE")
        self.assertEqual(result["after"], "FINALIZE")
        self.assertGreaterEqual(result["deadline"], started + 2.7)
        self.assertLess(run.duration_seconds, 3)
        self.assertEqual(sum("janela de fechamento" in x for x in progress), 1)

    def test_invalid_context_is_rejected(self) -> None:
        with self.assertRaisesRegex(VisualInspectionError, "empty"):
            validate_context("  ", 100)
        with self.assertRaisesRegex(VisualInspectionError, "exceeds limit"):
            validate_context("x" * 101, 100)

    def test_url_validation(self) -> None:
        self.assertEqual(validate_url("https://demo.localhost"), "https://demo.localhost")
        with self.assertRaisesRegex(VisualInspectionError, "absolute"):
            validate_url("file:///tmp/demo.html")
        with self.assertRaisesRegex(VisualInspectionError, "credentials"):
            validate_url("https://user:secret@example.com")

    def test_repository_resolution(self) -> None:
        nested = self.repo / "src"
        nested.mkdir()
        self.assertEqual(resolve_repository(nested), self.repo.resolve())

    def test_evidence_must_exist_inside_run_directory(self) -> None:
        evidence_dir = self.root / "evidence"
        evidence_dir.mkdir()
        screenshot = evidence_dir / "home.png"
        screenshot.write_bytes(b"png")
        report = sample_report()
        report["evidence_paths"] = [str(screenshot)]
        validate_evidence(report, evidence_dir)
        outside = self.root / "outside.png"
        outside.write_bytes(b"png")
        report["evidence_paths"] = [str(outside)]
        with self.assertRaisesRegex(VisualInspectionError, "outside"):
            validate_evidence(report, evidence_dir)

    def test_output_directory_is_private_and_under_tmp(self) -> None:
        with self.assertRaisesRegex(VisualInspectionError, "under /tmp"):
            create_run(Path("/var/tmp/visual-inspection"))
        _, evidence_dir = create_run(self.root / "private-evidence")
        self.assertEqual(stat.S_IMODE(evidence_dir.stat().st_mode), 0o700)

    def test_run_identifier_uses_sao_paulo_time(self) -> None:
        with patch("visual_inspection_lib.runtime.datetime") as clock:
            clock.now.return_value = datetime(2026, 7, 13, 23, 59, 58)
            session, _ = create_run(self.root / "local-time")
        self.assertTrue(session.startswith("visual-20260713-235958-"))

    def test_evidence_directory_opens_in_windows_explorer_on_wsl(self) -> None:
        evidence_dir = self.root / "evidence with spaces"
        evidence_dir.mkdir()
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        converted = subprocess.CompletedProcess(
            [],
            0,
            stdout=r"\\wsl.localhost\Ubuntu\tmp\evidence with spaces" + "\n",
            stderr="",
        )

        with (
            patch.dict(
                os.environ,
                {
                    "VISUAL_INSPECTION_AUTO_OPEN": "1",
                    "WSL_DISTRO_NAME": "Ubuntu",
                },
            ),
            patch(
                "visual_inspection_lib.runtime.shutil.which",
                side_effect=lambda command: {
                    "wslpath": "/usr/bin/wslpath",
                    "cmd.exe": "/mnt/c/Windows/System32/cmd.exe",
                }.get(command),
            ),
            patch(
                "visual_inspection_lib.runtime.subprocess.run",
                side_effect=[converted, completed],
            ) as run,
        ):
            self.assertTrue(open_evidence_directory(evidence_dir))

        self.assertEqual(
            run.call_args_list[1].args[0],
            [
                "/mnt/c/Windows/System32/cmd.exe",
                "/d",
                "/c",
                "start",
                "",
                r"\\wsl.localhost\Ubuntu\tmp\evidence with spaces",
            ],
        )

    def test_evidence_directory_auto_open_can_be_disabled(self) -> None:
        evidence_dir = self.root / "evidence"
        evidence_dir.mkdir()
        with (
            patch.dict(os.environ, {"VISUAL_INSPECTION_AUTO_OPEN": "0"}),
            patch("visual_inspection_lib.runtime.subprocess.run") as run,
        ):
            self.assertFalse(open_evidence_directory(evidence_dir))
        run.assert_not_called()

    def hold_all_run_slots(self, root: Path) -> list:
        locks = []
        for slot in range(1, MAX_CONCURRENT_INSPECTIONS + 1):
            lock = acquire_run_lock(root, f"visual-{slot}", self.repo)
            self.addCleanup(lock.close)
            locks.append(lock)
        return locks

    def test_run_lock_allows_three_active_inspections(self) -> None:
        self.assertEqual(MAX_CONCURRENT_INSPECTIONS, 3)
        root = self.root / "exclusive-runs"
        root.mkdir()
        locks = self.hold_all_run_slots(root)

        with self.assertRaisesRegex(
            ActiveVisualInspection,
            r"3/3 active.*session=visual-1.*session=visual-2.*session=visual-3",
        ):
            acquire_run_lock(root, "visual-extra", self.repo)

        locks[0].close()
        extra = acquire_run_lock(root, "visual-extra", self.repo)
        extra.close()

    def test_lock_links_cannot_modify_an_existing_file(self) -> None:
        for link_kind in ("symlink", "hardlink"):
            with self.subTest(link_kind=link_kind):
                root = self.root / link_kind
                root.mkdir(mode=0o700)
                victim = self.root / f"victim-{link_kind}"
                victim.write_text("conteúdo preservado", encoding="utf-8")
                victim.chmod(0o640)
                if link_kind == "symlink":
                    (root / ".runner.lock").symlink_to(victim)
                else:
                    os.link(victim, root / ".runner.lock")
                with self.assertRaisesRegex(VisualInspectionError, "unsafe inspection lock"):
                    acquire_run_lock(root, "visual-rejected", self.repo)
                self.assertEqual(victim.read_text(encoding="utf-8"), "conteúdo preservado")
                self.assertEqual(stat.S_IMODE(victim.stat().st_mode), 0o640)

    def test_run_rejects_symlinked_and_foreign_roots(self) -> None:
        root = self.root / "root-target"
        root.mkdir(mode=0o755)
        linked = self.root / "root-link"
        linked.symlink_to(root, target_is_directory=True)
        with self.assertRaisesRegex(VisualInspectionError, "unsafe evidence root"):
            create_run(linked)
        self.assertEqual(list(root.iterdir()), [])
        with patch("visual_inspection_lib.runtime.os.getuid", return_value=os.getuid() + 1):
            with self.assertRaisesRegex(VisualInspectionError, "must belong to the current user"):
                create_run(root)
        self.assertEqual(list(root.iterdir()), [])
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o755)

    def test_existing_owned_root_becomes_private_before_run(self) -> None:
        root = self.root / "previous-version-root"
        root.mkdir(mode=0o755)
        _, evidence = create_run(root)
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(evidence.stat().st_mode), 0o700)

    def test_shared_tmp_cannot_be_used_as_the_root(self) -> None:
        previous = Path("/tmp").stat().st_mode
        with self.assertRaisesRegex(VisualInspectionError, "under /tmp"):
            create_run(Path("/tmp"))
        with self.assertRaisesRegex(VisualInspectionError, "private directory"):
            acquire_run_lock(Path("/tmp"), "visual-rejected", self.repo)
        self.assertEqual(Path("/tmp").stat().st_mode, previous)

    def test_run_lock_rescans_when_a_slot_is_released_during_scan(self) -> None:
        root = self.root / "racing-runs"
        root.mkdir()
        locks = self.hold_all_run_slots(root)
        real_flock = fcntl.flock
        nonblocking_attempts = 0

        def release_first_during_scan(file_descriptor: int, operation: int) -> None:
            nonlocal nonblocking_attempts
            if operation & fcntl.LOCK_NB:
                nonblocking_attempts += 1
                if nonblocking_attempts == 2:
                    locks[0].close()
            real_flock(file_descriptor, operation)

        with patch(
            "visual_inspection_lib.runtime.fcntl.flock",
            side_effect=release_first_during_scan,
        ):
            extra = acquire_run_lock(root, "visual-extra", self.repo)

        extra.close()
        self.assertEqual(nonblocking_attempts, MAX_CONCURRENT_INSPECTIONS + 1)

    def test_concurrent_cli_run_returns_blocked_report_without_worker(self) -> None:
        root = self.root / "busy-runs"
        root.mkdir()
        self.hold_all_run_slots(root)

        result = subprocess.run(
            [
                str(Path(__file__).with_name("visual-inspection")),
                "--repo",
                str(self.repo),
                "--url",
                "https://example.com",
                "--output-root",
                str(root),
            ],
            input="Current user request: inspect the page",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = extract_report(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("all 3 execution slots are active", report["summary"])
        for slot in range(1, MAX_CONCURRENT_INSPECTIONS + 1):
            self.assertIn(f"visual-{slot}", report["limitations"][0])
        self.assertIn("blocked by inspection capacity", result.stderr)
        report_file = Path(execution_value(result.stdout, "Relatório"))
        self.assertTrue(report_file.is_file())

    def test_codex_invocation_defaults_to_luna_medium_fast_with_full_access(self) -> None:
        command = codex_command(self.repo, Path("report.md"))
        self.assertEqual(command[command.index("--model") + 1], "gpt-6-luna")
        self.assertIn('model_reasoning_effort="medium"', command)
        self.assertIn("--ephemeral", command)
        self.assertEqual(command[command.index("--cd") + 1], str(self.repo))
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertNotIn("--skip-git-repo-check", command)
        self.assertNotIn("--ignore-user-config", command)
        self.assertIn("--json", command)
        self.assertEqual(command[command.index("--enable") + 1], "fast_mode")
        self.assertIn('service_tier="fast"', command)

    def test_explicit_fast_keeps_luna_medium(self) -> None:
        command = codex_command(
            self.repo,
            Path("report.md"),
            fast=True,
        )
        self.assertEqual(command[command.index("--model") + 1], "gpt-6-luna")
        self.assertIn('model_reasoning_effort="medium"', command)
        self.assertEqual(command[command.index("--enable") + 1], "fast_mode")
        self.assertIn('service_tier="fast"', command)

    def test_worker_environment_is_inherited(self) -> None:
        inherited = worker_env(
            "visual-test",
            Path("/tmp/visual-test"),
            {
                "HOME": "/home/test",
                "PATH": "/usr/bin",
                "CUSTOM_CONTEXT": "available",
            },
        )
        self.assertEqual(inherited["HOME"], "/home/test")
        self.assertEqual(inherited["CUSTOM_CONTEXT"], "available")
        self.assertEqual(inherited["AGENT_BROWSER_SESSION"], "visual-test")
        self.assertEqual(
            inherited["AGENT_BROWSER_SCREENSHOT_DIR"],
            "/tmp/visual-test",
        )

    def test_missing_executables_return_clear_errors(self) -> None:
        evidence_dir = self.root / "missing-tools"
        evidence_dir.mkdir()
        with patch(
            "visual_inspection_lib.engine.subprocess.Popen",
            side_effect=FileNotFoundError("codex"),
        ):
            with self.assertRaisesRegex(VisualInspectionError, "cannot launch Codex"):
                run_worker(self.repo, evidence_dir, "prompt", "visual-test")
            cleanup = close_browser_session("visual-test", evidence_dir)
        self.assertIn("cannot launch agent-browser cleanup", cleanup or "")

    def test_worker_rejects_timeout_above_seven_minutes(self) -> None:
        evidence_dir = self.root / "timeout-ceiling"
        evidence_dir.mkdir()
        with self.assertRaisesRegex(
            VisualInspectionError, "must be at most 420 seconds"
        ):
            run_worker(
                self.repo,
                evidence_dir,
                "prompt",
                "visual-test",
                timeout_seconds=421,
            )

    def test_browser_cleanup_has_a_bounded_timeout(self) -> None:
        evidence_dir = self.root / "cleanup-timeout"
        evidence_dir.mkdir()
        with patch(
            "visual_inspection_lib.engine.subprocess.run",
            side_effect=subprocess.TimeoutExpired("agent-browser", 0.1),
        ):
            cleanup = close_browser_session(
                "visual-test",
                evidence_dir,
                timeout_seconds=0.1,
            )
        self.assertEqual(cleanup, "agent-browser cleanup timed out after 0.1s")

    def test_extracts_and_checks_markdown_report(self) -> None:
        expected = sample_report()
        self.assertEqual(extract_report(render_report(expected)), expected)
        expected["evidence_paths"] = []
        with self.assertRaisesRegex(VisualInspectionError, "must cite evidence"):
            extract_report(render_report(expected))

    def test_pass_accepts_only_low_findings(self) -> None:
        report = sample_report()
        report["findings"] = [
            {
                "severity": "low",
                "title": "Local environment noise",
                "details": "Open the page. Vite HMR websocket warning without product impact.",
            }
        ]
        self.assertEqual(extract_report(render_report(report)), report)

        for severity in ("medium", "high", "blocking"):
            with self.subTest(severity=severity):
                report["findings"][0]["severity"] = severity
                with self.assertRaisesRegex(VisualInspectionError, "non-LOW finding"):
                    extract_report(render_report(report))

    def test_rejects_unstructured_finding_text_instead_of_losing_it(self) -> None:
        markdown = render_report(sample_report()).replace(
            "# Achados\n\nNenhum.",
            "# Achados\n\n- HIGH: checkout is visibly broken",
        )
        with self.assertRaisesRegex(VisualInspectionError, "unexpected content"):
            extract_report(markdown)

    def test_report_requires_preflight(self) -> None:
        markdown = render_report(sample_report()).replace("# Preflight", "# Preparação")
        with self.assertRaisesRegex(VisualInspectionError, "missing sections: preflight"):
            extract_report(markdown)

    def test_blocked_preflight_requires_blocked_report(self) -> None:
        report = sample_report()
        report["preflight"] = {
            "status": "blocked",
            "evidence": "Required authentication did not complete.",
        }
        with self.assertRaisesRegex(
            VisualInspectionError, "blocked preflight requires Status: BLOCKED"
        ):
            extract_report(render_report(report))

    def test_preflight_requires_evidence(self) -> None:
        report = sample_report()
        report["preflight"]["evidence"] = ""
        with self.assertRaisesRegex(VisualInspectionError, "observable evidence"):
            extract_report(render_report(report))

    def test_dry_run_exposes_fixed_configuration(self) -> None:
        result = subprocess.run(
            [
                str(Path(__file__).with_name("visual-inspection")),
                "--dry-run",
                "--repo",
                str(self.repo),
                "--url",
                "https://example.com",
            ],
            input="Current user request: inspect the page",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Status: DRY-RUN", result.stdout)
        self.assertIn("- Modelo: `gpt-6-luna`", result.stdout)
        self.assertIn("- Reasoning: `medium`", result.stdout)
        self.assertIn("- Tier: `fast`", result.stdout)
        self.assertIn("--enable fast_mode", result.stdout)
        self.assertIn('service_tier="fast"', result.stdout)
        self.assertIn("- Timeout: 420s", result.stdout)
        self.assertIn(f"--cd {self.repo}", result.stdout)

    def test_timeout_above_seven_minutes_is_rejected(self) -> None:
        result = subprocess.run(
            [
                str(Path(__file__).with_name("visual-inspection")),
                "--dry-run",
                "--timeout-seconds",
                "421",
                "--repo",
                str(self.repo),
                "--url",
                "https://example.com",
            ],
            input="Current user request: inspect the page",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be at most 420 seconds", result.stderr)

    def test_dry_run_exposes_fast_without_changing_model_or_reasoning(self) -> None:
        result = subprocess.run(
            [
                str(Path(__file__).with_name("visual-inspection")),
                "--dry-run",
                "--fast",
                "--repo",
                str(self.repo),
                "--url",
                "https://example.com",
            ],
            input="Current user request: inspect the page",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- Tier: `fast`", result.stdout)
        self.assertIn("--enable fast_mode", result.stdout)
        self.assertIn("service_tier=\"fast\"", result.stdout)

    def test_runner_passes_repository_environment_and_main_context(self) -> None:
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        capture = fake_bin / "capture.json"
        prompt_file = fake_bin / "prompt.txt"
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            """#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
base = pathlib.Path(__file__).parent
base.joinpath('capture.json').write_text(json.dumps({
  'args': args,
  'cwd': os.getcwd(),
  'session': os.environ.get('AGENT_BROWSER_SESSION'),
  'custom_context': os.environ.get('CUSTOM_CONTEXT')
}))
base.joinpath('prompt.txt').write_text(sys.stdin.read())
output = pathlib.Path(args[args.index('--output-last-message') + 1])
evidence = pathlib.Path(os.environ['AGENT_BROWSER_SCREENSHOT_DIR']) / 'evidence.png'
evidence.write_bytes(b'png')
output.write_text(f'''Status: PASS

# Resumo
Visible

# Preflight
Status: PASS
Ready

# Critérios
## Visible — PASS
Screenshot

# Achados
Nenhum.

# Limitações
Nenhuma.

# Evidências
- {evidence}
''')
""",
            encoding="utf-8",
        )
        fake_browser = fake_bin / "agent-browser"
        fake_browser.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        fake_browser.chmod(fake_browser.stat().st_mode | stat.S_IXUSR)

        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        env["CUSTOM_CONTEXT"] = "available"
        handoff = "Current user request: inspect settings\nRelevant conversation: Sol medium."
        result = subprocess.run(
            [
                str(Path(__file__).with_name("visual-inspection")),
                "--repo",
                str(self.repo),
                "--url",
                "https://example.com",
                "--output-root",
                str(self.root / "visual inspection tests"),
            ],
            input=handoff,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = extract_report(result.stdout)
        captured = json.loads(capture.read_text(encoding="utf-8"))
        prompt = prompt_file.read_text(encoding="utf-8")
        self.assertEqual(captured["cwd"], str(self.repo))
        self.assertEqual(captured["session"], execution_value(result.stdout, "Sessão"))
        self.assertEqual(captured["custom_context"], "available")
        self.assertIn(handoff, prompt)
        self.assertIn(str(self.repo), prompt)
        self.assertEqual(output["status"], "blocked")
        self.assertEqual(output["criteria"][-1]["status"], "blocked")
        self.assertEqual(output["criteria"][-1]["criterion"], "Browser session cleanup")
        self.assertIn("cleanup failed", output["limitations"][0])
        self.assertIn("visual-inspection [00:00] worker started", result.stderr)
        self.assertIn("tail -n 200 -f '", result.stderr)
        self.assertRegex(execution_value(result.stdout, "Início"), r"-03:00$")
        self.assertGreaterEqual(
            float(execution_value(result.stdout, "Duração").removesuffix("s")), 0
        )
        report_file = Path(execution_value(result.stdout, "Relatório"))
        self.assertEqual(stat.S_IMODE(report_file.stat().st_mode), 0o600)

    def test_worker_streams_events_and_heartbeats_before_completion(self) -> None:
        fake_bin = self.root / "stream-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            """#!/usr/bin/env python3
import json, pathlib, sys, time
args = sys.argv[1:]
sys.stdin.read()
print(json.dumps({'type': 'thread.started', 'thread_id': 'test'}), flush=True)
time.sleep(0.4)
output = pathlib.Path(args[args.index('--output-last-message') + 1])
output.write_text('''Status: BLOCKED

# Resumo
No browser needed

# Preflight
Status: BLOCKED
Synthetic run

# Critérios
## Synthetic — BLOCKED
Synthetic run

# Achados
Nenhum.

# Limitações
- Synthetic run

# Evidências
Nenhuma.
''')
print(json.dumps({'type': 'turn.completed'}), flush=True)
""",
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        evidence_dir = self.root / "stream-evidence"
        evidence_dir.mkdir()
        progress_messages: list[str] = []
        result_holder: list[object] = []

        def invoke() -> None:
            result_holder.append(
                run_worker(
                    self.repo,
                    evidence_dir,
                    "complete handoff",
                    "visual-stream",
                    timeout_seconds=2,
                    heartbeat_seconds=0.1,
                    progress=progress_messages.append,
                )
            )

        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        with patch.dict(os.environ, env, clear=True):
            worker = threading.Thread(target=invoke)
            worker.start()
            events_file = evidence_dir / "worker-events.jsonl"
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                if events_file.exists() and "thread.started" in events_file.read_text(
                    encoding="utf-8"
                ):
                    break
                time.sleep(0.02)
            self.assertTrue(worker.is_alive(), "worker finished before streaming was observed")
            self.assertIn("thread.started", events_file.read_text(encoding="utf-8"))
            worker.join(timeout=3)

        self.assertFalse(worker.is_alive())
        self.assertFalse(result_holder[0].timed_out)
        self.assertTrue(any("heartbeat" in message for message in progress_messages))
        self.assertTrue(any("worker connected" in message for message in progress_messages))

    def test_timeout_returns_blocked_markdown_and_preserves_partial_events(self) -> None:
        fake_bin = self.root / "timeout-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            """#!/usr/bin/env python3
import json, os, pathlib, sys, time
sys.stdin.read()
pathlib.Path(os.environ['AGENT_BROWSER_SCREENSHOT_DIR'], 'progress.md').write_text(
    '## C1 — PASS\\n\\nPrimeiro critério registrado antes da interrupção.\\n'
)
print(json.dumps({'type': 'thread.started', 'thread_id': 'timeout-test'}), flush=True)
time.sleep(10)
""",
            encoding="utf-8",
        )
        fake_browser = fake_bin / "agent-browser"
        fake_browser.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        fake_browser.chmod(fake_browser.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        result = subprocess.run(
            [
                str(Path(__file__).with_name("visual-inspection")),
                "--repo",
                str(self.repo),
                "--url",
                "https://example.com",
                "--output-root",
                str(self.root / "timeout-runs"),
                "--timeout-seconds",
                "0.3",
                "--heartbeat-seconds",
                "0.1",
            ],
            input="Current user request: synthetic timeout",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = extract_report(result.stdout)
        self.assertEqual(output["status"], "blocked")
        self.assertEqual(output["preflight"]["status"], "blocked")
        self.assertLess(
            float(execution_value(result.stdout, "Duração").removesuffix("s")), 3
        )
        self.assertIn("timed out after 0.3s", output["limitations"][0])
        self.assertIn("heartbeat", result.stderr)
        self.assertIn("timeout reached", result.stderr)
        self.assertIn("Primeiro critério registrado antes da interrupção", result.stdout)
        self.assertIn("não prova conclusão de toda a inspeção", result.stdout)
        events = Path(execution_value(result.stdout, "Diretório de evidências")) / "worker-events.jsonl"
        self.assertIn("thread.started", events.read_text(encoding="utf-8"))

    def test_timeout_kills_worker_descendants_that_ignore_sigterm(self) -> None:
        fake_bin = self.root / "descendant-bin"
        fake_bin.mkdir()
        child_pid_file = fake_bin / "child.pid"
        fake_codex = fake_bin / "codex"
        child_program = (
            "import os, pathlib, signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"pathlib.Path({str(child_pid_file)!r}).write_text(str(os.getpid())); "
            "time.sleep(10)"
        )
        fake_codex.write_text(
            f"""#!/usr/bin/env python3
import json, pathlib, subprocess, sys, time
sys.stdin.read()
subprocess.Popen([
  sys.executable,
  '-c',
  {json.dumps(child_program)}
])
print(json.dumps({{'type': 'thread.started', 'thread_id': 'descendant-test'}}), flush=True)
time.sleep(10)
""",
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        evidence_dir = self.root / "descendant-evidence"
        evidence_dir.mkdir()
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "visual_inspection_lib.engine.TERMINATION_GRACE_SECONDS",
                0.2,
            ),
        ):
            run = run_worker(
                self.repo,
                evidence_dir,
                "complete handoff",
                "visual-descendant",
                timeout_seconds=0.8,
                heartbeat_seconds=0.1,
            )

        self.assertTrue(run.timed_out)
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)

    def test_worker_failure_returns_blocked_markdown_without_replaying_raw_events(self) -> None:
        fake_bin = self.root / "failure-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            """#!/usr/bin/env python3
import json, sys
sys.stdin.read()
print(json.dumps({
  'type': 'item.started',
  'item': {
    'id': 'secret-step',
    'type': 'command_execution',
    'command': 'SECRET_COMMAND_MUST_STAY_IN_PROTECTED_LOG'
  }
}), flush=True)
raise SystemExit(7)
""",
            encoding="utf-8",
        )
        fake_browser = fake_bin / "agent-browser"
        fake_browser.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        fake_browser.chmod(fake_browser.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        result = subprocess.run(
            [
                str(Path(__file__).with_name("visual-inspection")),
                "--repo",
                str(self.repo),
                "--url",
                "https://example.com",
                "--output-root",
                str(self.root / "failure-runs"),
            ],
            input="Current user request: synthetic worker failure",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = extract_report(result.stdout)
        self.assertEqual(output["status"], "blocked")
        self.assertEqual(output["preflight"]["status"], "blocked")
        self.assertIn("failed with exit code 7", output["limitations"][0])
        self.assertNotIn("SECRET_COMMAND", result.stderr)
        self.assertNotIn("SECRET_COMMAND", result.stdout)
        events = Path(execution_value(result.stdout, "Diretório de evidências")) / "worker-events.jsonl"
        self.assertIn("SECRET_COMMAND", events.read_text(encoding="utf-8"))

    def test_invalid_pass_still_writes_final_report_and_lists_preserved_artifacts(self) -> None:
        fake_bin = self.root / "invalid-report-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            """#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
sys.stdin.read()
evidence = pathlib.Path(os.environ['AGENT_BROWSER_SCREENSHOT_DIR']) / 'captured.png'
evidence.write_bytes(b'png')
output = pathlib.Path(args[args.index('--output-last-message') + 1])
output.write_text('''Status: PASS

# Resumo
Captured but not linked

# Preflight
Status: PASS
Ready

# Critérios
## Visible — PASS
Captured

# Achados
Nenhum.

# Limitações
Nenhuma.

# Evidências
Nenhuma.
''')
""",
            encoding="utf-8",
        )
        fake_browser = fake_bin / "agent-browser"
        fake_browser.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        fake_browser.chmod(fake_browser.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        result = subprocess.run(
            [
                str(Path(__file__).with_name("visual-inspection")),
                "--repo",
                str(self.repo),
                "--url",
                "https://example.com",
                "--output-root",
                str(self.root / "invalid-report-runs"),
            ],
            input="Current user request: synthetic invalid pass",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("Status: BLOCKED"))
        self.assertIn("PASS report must cite evidence", result.stdout)
        self.assertIn("Captured but not linked", result.stdout)
        self.assertIn("resposta de texto", result.stdout)
        evidence_dir = Path(execution_value(result.stdout, "Diretório de evidências"))
        self.assertIn(str(evidence_dir / "captured.png"), result.stdout)
        report_file = Path(execution_value(result.stdout, "Relatório"))
        self.assertTrue(report_file.is_file())
        self.assertTrue(report_file.read_text(encoding="utf-8").startswith("Status: BLOCKED"))


if __name__ == "__main__":
    unittest.main()
