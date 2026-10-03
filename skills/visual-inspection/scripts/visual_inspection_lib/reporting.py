from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contract import (
    CLIENT_REVIEW_NOTICE,
    ENTRY_PATTERN,
    FINDING_PATTERN,
    VisualInspectionError,
    evidence_paths,
    extract_report,
    render_report,
    validate_evidence,
)


@dataclass
class ReportAssessment:
    raw: str
    status: str
    report: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)


def assess_report(raw: str, evidence_dir: Path) -> ReportAssessment:
    """Formato é orientação; evidência inválida e contradições continuam explícitas."""
    text = raw.strip()
    match = re.search(r"^\s*(?:\*\*)?Status:\s*(PASS|FAIL|BLOCKED)(?:\*\*)?\s*$", text, re.I | re.M)
    # Status dentro de Preflight não substitui uma conclusão geral ausente.
    declared = match.group(1).lower() if match else "blocked"
    if match and re.search(r"^#+\s+Preflight\b", text[:match.start()], re.I | re.M):
        declared = "blocked"
        match = None
    result = ReportAssessment(raw=text, status=declared)
    try:
        result.report = extract_report(text)
    except VisualInspectionError as error:
        result.warnings.append(f"Estrutura para revisão: {error}")

    if result.report is not None:
        candidates = result.report["evidence_paths"]
    else:
        # Recupera referências de artefatos no texto livre sem tratar cada frase como caminho.
        candidates = evidence_paths("\n".join(re.findall(
            r"/[^\n`<>]*?\.(?:png|jpe?g|webp|mp4|webm|txt|json|har)(?=$|[\s)`.,\]])",
            text, re.I | re.M,
        )))
    invalid = False
    for path in candidates:
        try:
            validate_evidence({"evidence_paths": [path]}, evidence_dir.resolve())
            result.paths.append(path)
        except VisualInspectionError as error:
            invalid = True
            result.warnings.append(f"Evidência para revisão: {error}")

    # Sem interpretar a prosa: conservamos falhas expressamente registradas nos critérios/achados.
    lines = [line.strip() for line in text.splitlines()]
    entries = [m for line in lines if (m := ENTRY_PATTERN.fullmatch(line))]
    findings = [m for line in lines if (m := FINDING_PATTERN.fullmatch(line))]
    failed = any(m.group(2).lower() == "fail" for m in entries)
    severe = any(m.group(1).lower() != "low" for m in findings)
    if failed or severe:
        if result.status != "fail":
            result.warnings.append("Conclusão ajustada para FAIL: critério falhou ou há achado não LOW.")
        result.status = "fail"
    elif result.status == "pass" and (
        invalid or not result.paths or any(m.group(2).lower() == "blocked" for m in entries)
        or re.search(
            r"^#+\s+Preflight\s+(?:\*\*)?Status:\s*BLOCKED\b",
            text, re.I | re.M,
        )
    ):
        result.status = "blocked"
        result.warnings.append("PASS não aceito automaticamente: evidência ausente/inválida ou critério bloqueado.")
    if not match:
        result.warnings.append("Conclusão geral ausente: o cliente deve avaliar o texto.")
    return result


def render_assessment(result: ReportAssessment, execution: dict[str, str]) -> str:
    if result.report is not None:
        report = {
            **result.report,
            "status": result.status,
            "evidence_paths": result.paths,
            "limitations": list(dict.fromkeys([*result.report["limitations"], *result.warnings])),
        }
        return render_report(report, execution=execution)
    lines = [f"Status: {result.status.upper()}", "", "# Execução", ""]
    lines.extend(f"- {key}: {value}" for key, value in execution.items())
    lines.extend(["", "# Avaliação pelo cliente", "", CLIENT_REVIEW_NOTICE, ""])
    lines.extend(f"- {warning}" for warning in result.warnings)
    lines.extend(["", "# Laudo do worker", ""])
    # Citação preserva a resposta sem confundir seu status/seções com os do envelope do runner.
    lines.extend(f"> {line}" for line in result.raw.splitlines())
    lines.extend(["", "# Evidências verificadas", ""])
    lines.extend(f"- {path}" for path in result.paths)
    return "\n".join(lines).rstrip() + "\n"


def append_progress(rendered: str, evidence_dir: Path) -> str:
    progress_file = evidence_dir / "progress.md"
    if not progress_file.is_file() or progress_file.is_symlink():
        return rendered
    try:
        text = progress_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return (
            rendered + "\n# Registro parcial do worker\n\n"
            "Não foi possível ler progress.md; o laudo final foi preservado.\n"
        )
    if not text:
        return rendered
    quote = "\n".join(f"> {line}" for line in text.splitlines())
    return (
        rendered + "\n# Registro parcial do worker\n\n"
        "Registro incremental para avaliação do cliente; não prova conclusão de toda a inspeção.\n\n"
        + quote + "\n"
    )
