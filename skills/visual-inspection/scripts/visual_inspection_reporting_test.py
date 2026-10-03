from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from visual_inspection_lib.contract import extract_report, render_report, validate_evidence
from visual_inspection_lib.reporting import append_progress, assess_report, render_assessment
from visual_inspection_test import sample_report


class ReportingCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="visual-report-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / "captura com espaço.png"
        self.image.write_bytes(b"fixture")
        self.report = sample_report()
        self.report["evidence_paths"] = [str(self.image)]
        self.helper = Path(__file__).with_name("visual-inspection-report")

    def test_realistic_markdown_references_keep_same_evidence(self) -> None:
        for reference in [
            f"[Screenshot]({self.image})", f"Busca: `{self.image}`",
            f"`{self.image}` — tela autenticada", f"{self.image} — estado final",
        ]:
            with self.subTest(reference=reference):
                raw = render_report(self.report).replace(f"- {self.image}", f"- {reference}")
                parsed = extract_report(raw)
                validate_evidence(parsed, self.root)
                self.assertEqual(parsed["evidence_paths"], [str(self.image)])
                self.assertEqual(assess_report(raw, self.root).status, "pass")

    def test_missing_evidence_section_preserves_useful_text(self) -> None:
        raw = render_report(self.report).split("# Evidências", 1)[0]
        raw = raw.replace("Screenshot captured.", f"Screenshot capturado: `{self.image}`")
        result = assess_report(raw, self.root)
        output = render_assessment(result, {})
        self.assertEqual(result.status, "pass")
        self.assertTrue(result.warnings)
        self.assertIn("Screenshot capturado", output)
        self.assertIn("resposta de texto", output)
        self.assertIn(str(self.image), output)

    def test_plain_report_is_available_for_caller_assessment(self) -> None:
        raw = f"Concluí a inspeção.\n\nStatus: FAIL\n\nO botão está encoberto.\nEvidência: `{self.image}`"
        result = assess_report(raw, self.root)
        self.assertEqual(result.status, "fail")
        self.assertIn("botão está encoberto", render_assessment(result, {}))

    def test_bad_reference_blocks_pass_without_discarding_observation(self) -> None:
        for image in [self.root / "ausente.png", self.root.parent / "fora.png"]:
            with self.subTest(image=image):
                self.report["evidence_paths"] = [str(image)]
                result = assess_report(render_report(self.report), self.root)
                self.assertEqual(result.status, "blocked")
                self.assertIn("rendered correctly", render_assessment(result, {}))
                self.assertTrue(result.warnings)

    def test_symlink_outside_run_is_not_accepted(self) -> None:
        link = self.root / "atalho.png"
        link.symlink_to(Path(__file__).resolve())
        result = assess_report(f"Status: PASS\nEvidência: `{link}`", self.root)
        self.assertEqual(result.status, "blocked")

    def test_failed_criterion_survives_broken_structure(self) -> None:
        raw = f"Status: PASS\n\n## Botão — FAIL\nNão funcionou.\n`{self.image}`"
        result = assess_report(raw, self.root)
        self.assertEqual(result.status, "fail")
        self.assertIn("Não funcionou", render_assessment(result, {}))

    def test_preflight_status_does_not_supply_missing_overall_conclusion(self) -> None:
        raw = f"# Preflight\nStatus: PASS\nPronto.\n`{self.image}`"
        self.assertEqual(assess_report(raw, self.root).status, "blocked")

    def test_emphasized_blocked_preflight_cannot_retain_overall_pass(self) -> None:
        for status in (
            "Status: BLOCKED", "**Status: BLOCKED**",
            "Status: BLOCKED — autenticação indisponível",
            "**Status: BLOCKED** — autenticação indisponível",
        ):
            with self.subTest(status=status):
                raw = f"Status: PASS\n\n# Preflight\n{status}\nSem acesso.\n`{self.image}`"
                result = assess_report(raw, self.root)
                self.assertEqual(result.status, "blocked")
                self.assertIn("Sem acesso", render_assessment(result, {}))

    def test_check_allows_worker_to_correct_using_existing_evidence(self) -> None:
        draft = self.root / "draft-report.md"
        draft.write_text("Status: PASS\n# Resumo\nTela aberta.")
        args = [str(self.helper), "check", str(draft), "--evidence-dir", str(self.root)]
        result = subprocess.run(args, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        draft.write_text(render_report(self.report))
        result = subprocess.run(args, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cliente deve avaliar", result.stdout)

    def test_checkpoint_appends_and_survives_interruption(self) -> None:
        args = [str(self.helper), "checkpoint", "--evidence-dir", str(self.root)]
        for text in ["C1 — PASS\nBusca confirmada.", "C2 — FAIL\nFiltro não ativou."]:
            result = subprocess.run(args, input=text, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        progress = self.root / "progress.md"
        self.assertEqual(progress.stat().st_mode & 0o777, 0o600)
        output = append_progress("Status: BLOCKED\nPrazo esgotado.\n", self.root)
        self.assertTrue(output.startswith("Status: BLOCKED"))
        self.assertIn("C1 — PASS", output)
        self.assertIn("C2 — FAIL", output)
        self.assertIn("não prova conclusão", output)

    def test_checkpoint_does_not_write_through_symlink(self) -> None:
        outside = self.root / "original.txt"
        outside.write_text("preservado")
        (self.root / "progress.md").symlink_to(outside)
        result = subprocess.run(
            [str(self.helper), "checkpoint", "--evidence-dir", str(self.root)],
            input="registro", text=True, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(outside.read_text(), "preservado")

    def test_unreadable_checkpoint_does_not_invalidate_final_report(self) -> None:
        (self.root / "progress.md").write_bytes(b"\xff")
        output = append_progress("Status: FAIL\nDefeito observado.\n", self.root)
        self.assertTrue(output.startswith("Status: FAIL"))
        self.assertIn("Defeito observado", output)
        self.assertIn("Não foi possível ler progress.md", output)

    def test_runner_delivers_free_text_without_restarting_worker(self) -> None:
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        codex = fake_bin / "codex"
        codex.write_text('''#!/usr/bin/env python3
import os, pathlib, sys
sys.stdin.read()
root = pathlib.Path(os.environ['AGENT_BROWSER_SCREENSHOT_DIR'])
(root / 'evidence.png').write_bytes(b'fixture')
args = sys.argv
pathlib.Path(args[args.index('--output-last-message') + 1]).write_text(
    f"Status: FAIL\\n\\nO filtro não ligou. Evidência: `{root / 'evidence.png'}`\\n"
)
''')
        browser = fake_bin / "agent-browser"
        browser.write_text("#!/bin/sh\nexit 0\n")
        for path in (codex, browser):
            path.chmod(0o700)
        result = subprocess.run(
            [str(self.helper.with_name("visual-inspection")), "--repo", str(repo),
             "--url", "https://example.com", "--output-root", str(self.root / "runs")],
            input="Inspecionar filtro.", text=True, capture_output=True,
            env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "VISUAL_INSPECTION_AUTO_OPEN": "0"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("Status: FAIL"))
        self.assertIn("O filtro não ligou", result.stdout)
        self.assertIn("não uma aprovação automática", result.stdout)
        self.assertIn("Estrutura para revisão", result.stdout)
        self.assertEqual(len(list((self.root / "runs").glob("*/worker-report.md"))), 1)


if __name__ == "__main__":
    unittest.main()
