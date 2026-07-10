from __future__ import annotations

import json
from typing import Any


REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings", "overall_correctness", "summary"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "severity", "body", "file", "line"],
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                    "body": {"type": "string"},
                    "file": {"type": ["string", "null"]},
                    "line": {"type": ["integer", "null"], "minimum": 1},
                },
            },
        },
        "overall_correctness": {
            "type": "string",
            "enum": ["patch is correct", "patch is incorrect"],
        },
        "summary": {"type": "string"},
    },
}


class ReportError(RuntimeError):
    pass


def _decode(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def extract_report(raw: str) -> dict[str, Any]:
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ReportError(f"reviewer returned invalid JSON: {error}") from error

    for candidate in (
        parsed,
        parsed.get("structured_output") if isinstance(parsed, dict) else None,
        parsed.get("result") if isinstance(parsed, dict) else None,
    ):
        candidate = _decode(candidate)
        if isinstance(candidate, dict) and isinstance(candidate.get("findings"), list):
            validate_report(candidate)
            return candidate
    raise ReportError("reviewer output does not contain a structured findings report")


def validate_report(report: dict[str, Any]) -> None:
    required = {"findings", "overall_correctness", "summary"}
    missing = required - report.keys()
    if missing:
        raise ReportError(f"review report missing fields: {', '.join(sorted(missing))}")
    if report["overall_correctness"] not in {"patch is correct", "patch is incorrect"}:
        raise ReportError("review report has invalid overall_correctness")
    has_findings = bool(report["findings"])
    is_correct = report["overall_correctness"] == "patch is correct"
    if has_findings == is_correct:
        raise ReportError("review report has contradictory findings and overall_correctness")
    for index, finding in enumerate(report["findings"]):
        if not isinstance(finding, dict):
            raise ReportError(f"finding {index} is not an object")
        if finding.get("severity") not in {"P0", "P1", "P2", "P3"}:
            raise ReportError(f"finding {index} has invalid severity")
        for field in ("title", "body"):
            if not isinstance(finding.get(field), str) or not finding[field].strip():
                raise ReportError(f"finding {index} has invalid {field}")
