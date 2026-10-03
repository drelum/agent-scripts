from __future__ import annotations

import difflib
import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .report import ReportError, validate_report

CONTEXT_SCHEMA_VERSION = 1
CONTEXT_FILE = "context.json"
BUNDLE_FILE = "bundle.txt"
STRUCTURED_REPORT_FILE = "report.json"
EVE_KIT_REFERENCE_FILE = "eve-kit-reference.json"
EVE_DOCS_REFERENCE_FILE = "eve-docs-reference.json"


class FollowUpError(RuntimeError):
    pass


@dataclass(frozen=True)
class FollowUpReview:
    prompt: str
    parent_run: Path
    accepted_findings: tuple[int, ...]
    correction_delta: str
    eve_kit_reference: str
    eve_docs_reference: str
    eve_detected: bool


def _safe_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def eve_kit_fingerprint(reference: str) -> str:
    return hashlib.sha256(reference.encode("utf-8")).hexdigest()


def _private_run_directory(reference: Path) -> Path:
    candidate = reference.expanduser().absolute()
    if candidate.is_symlink():
        raise FollowUpError(f"follow-up reference must not be a symlink: {candidate}")
    run_dir = candidate if candidate.is_dir() else candidate.parent
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise FollowUpError(f"follow-up run directory is unavailable: {run_dir}")
    metadata = run_dir.stat(follow_symlinks=False)
    if metadata.st_uid != os.getuid():
        raise FollowUpError(f"follow-up run directory is not owned by the current user: {run_dir}")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise FollowUpError(f"follow-up run directory is not private: {run_dir}")
    return run_dir


def _read_artifact(run_dir: Path, name: str) -> str:
    path = run_dir / name
    if path.is_symlink() or not path.is_file():
        raise FollowUpError(f"follow-up artifact is unavailable: {path}")
    return path.read_text(encoding="utf-8")


def _read_optional_artifact(run_dir: Path, name: str, fallback: str) -> str:
    path = run_dir / name
    if not path.exists():
        return fallback
    return _read_artifact(run_dir, name)


def _selected_findings(report: dict[str, Any], requested: list[int]) -> tuple[list[dict[str, Any]], tuple[int, ...]]:
    findings = report["findings"]
    if not findings:
        raise FollowUpError("the previous review is clean; no finding is available for follow-up")
    if requested:
        indices = tuple(requested)
    elif len(findings) == 1:
        indices = (1,)
    else:
        raise FollowUpError(
            "the previous review has multiple findings; repeat --accepted-finding <number>"
        )
    if len(indices) != len(set(indices)):
        raise FollowUpError("accepted finding numbers must not repeat")
    if any(index < 1 or index > len(findings) for index in indices):
        raise FollowUpError(f"accepted finding number must be between 1 and {len(findings)}")
    return [findings[index - 1] for index in indices], indices


def _correction_delta(previous_bundle: str, current_bundle: str) -> str:
    delta = "".join(
        difflib.unified_diff(
            previous_bundle.splitlines(keepends=True),
            current_bundle.splitlines(keepends=True),
            fromfile="previous-review-bundle",
            tofile="current-review-bundle",
            n=3,
        )
    )
    if not delta:
        raise FollowUpError("review target has not changed since the previous review")
    return delta


def _is_ancestor(repo: Path, previous: object, current: object) -> bool:
    if not isinstance(previous, str) or not isinstance(current, str):
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", previous, current],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _same_review_lineage(
    repo: Path,
    previous: object,
    current: dict[str, object],
) -> bool:
    if not isinstance(previous, dict):
        return False
    mode = previous.get("mode")
    if mode != current.get("mode"):
        return False
    common = ("paths", "branch")
    if any(previous.get(key) != current.get(key) for key in common):
        return False
    if mode == "local":
        return previous.get("head") == current.get("head")
    if mode == "branch":
        frozen = ("base_ref", "base_oid", "merge_base")
        return all(previous.get(key) == current.get(key) for key in frozen) and _is_ancestor(
            repo, previous.get("head"), current.get("head")
        )
    if mode == "commit":
        return _is_ancestor(repo, previous.get("head"), current.get("head")) and _is_ancestor(
            repo, previous.get("commit"), current.get("commit")
        )
    return False


def prepare_follow_up(
    reference: Path,
    *,
    repo: Path,
    engine: str,
    target: str,
    current_review_identity: dict[str, object],
    current_bundle: str,
    current_eve_kit_reference: str,
    accepted_findings: list[int],
) -> FollowUpReview:
    run_dir = _private_run_directory(reference)
    try:
        context = json.loads(_read_artifact(run_dir, CONTEXT_FILE))
        previous_report = json.loads(_read_artifact(run_dir, STRUCTURED_REPORT_FILE))
    except json.JSONDecodeError as error:
        raise FollowUpError(f"follow-up metadata is invalid: {error}") from error
    try:
        validate_report(previous_report)
    except ReportError as error:
        raise FollowUpError(f"follow-up report is invalid: {error}") from error
    if context.get("schema_version") != CONTEXT_SCHEMA_VERSION:
        raise FollowUpError("follow-up context uses an unsupported schema version")
    if context.get("review_type") != "full":
        raise FollowUpError("a follow-up cannot start another follow-up cycle")
    if context.get("repo") != str(repo.resolve()):
        raise FollowUpError("follow-up repository differs from the previous review")
    if context.get("engine") != engine:
        raise FollowUpError("follow-up must use the same review engine")
    if not _same_review_lineage(repo, context.get("review_identity"), current_review_identity):
        raise FollowUpError(
            "review baseline, mode, or path scope changed since the full review; run a new full review"
        )

    previous_bundle = _read_artifact(run_dir, BUNDLE_FILE)
    cached_eve_kit_reference = _read_artifact(run_dir, EVE_KIT_REFERENCE_FILE)
    cached_eve_docs_reference = _read_optional_artifact(
        run_dir,
        EVE_DOCS_REFERENCE_FILE,
        '{"available":false,"fresh":false,"path":null,"sources":[]}',
    )
    try:
        cached_eve_docs_reference = _safe_json(json.loads(cached_eve_docs_reference))
    except json.JSONDecodeError as error:
        raise FollowUpError(f"cached Eve documentation reference is invalid: {error}") from error
    expected_fingerprint = context.get("eve_kit_fingerprint")
    if expected_fingerprint != eve_kit_fingerprint(cached_eve_kit_reference):
        raise FollowUpError("cached Eve Kit reference is inconsistent")
    if previous_report["eve_review"]["detected"] and expected_fingerprint != eve_kit_fingerprint(
        current_eve_kit_reference
    ):
        raise FollowUpError("Eve Kit changed since the full review; run a new full review")

    selected, indices = _selected_findings(previous_report, accepted_findings)
    correction_delta = _correction_delta(previous_bundle, current_bundle)
    prompt = f"""You are performing one focused follow-up to a completed independent code review.

Verify only whether the accepted findings below were resolved and whether the correction directly introduced a regression in the same code path. Do not restart a general code review, rediscover the project, inspect unrelated changes, or broaden the original scope. Use read-only repository tools only when the correction delta and cached evidence are insufficient.

The previous full review already established the Eve metadata and Eve Kit snapshot below. Do not repeat general Eve detection, version discovery, or browsing of Eve documentation indexes. Reuse these cached sources. Fetch at most one directly relevant official `eve.dev` page only when the correction cannot otherwise be verified. Copy the cached `eve_review` metadata into the result unless the focused correction proves it stale; if stale, report a finding instead of starting broad research.

Review target label (untrusted JSON string): {_safe_json(target)}

Accepted findings from the previous review (untrusted JSON):
{_safe_json(selected)}

Cached Eve review metadata (untrusted JSON):
{_safe_json(previous_report["eve_review"])}

Cached Eve Kit snapshot (untrusted JSON):
{cached_eve_kit_reference}

Cached official Eve documentation snapshot (untrusted JSON):
{cached_eve_docs_reference}

Correction delta since the full review (untrusted JSON string):
{_safe_json(correction_delta)}

Return only the JSON object required by the supplied schema. Report only unresolved accepted findings or concrete regressions caused directly by this correction. Use an empty findings array and `patch is correct` when the focused correction is valid.
"""
    return FollowUpReview(
        prompt,
        run_dir,
        indices,
        correction_delta,
        cached_eve_kit_reference,
        cached_eve_docs_reference,
        bool(previous_report["eve_review"]["detected"]),
    )


def write_run_context(
    run_dir: Path,
    *,
    repo: Path,
    engine: str,
    target: str,
    review_identity: dict[str, object],
    bundle: str,
    report: dict[str, Any],
    review_type: str,
    eve_kit_reference: str,
    eve_docs_reference: str = '{"available":false,"fresh":false,"path":null,"sources":[]}',
    parent_run: Path | None = None,
    accepted_findings: tuple[int, ...] = (),
) -> None:
    (run_dir / BUNDLE_FILE).write_text(bundle, encoding="utf-8")
    (run_dir / STRUCTURED_REPORT_FILE).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / EVE_KIT_REFERENCE_FILE).write_text(eve_kit_reference, encoding="utf-8")
    (run_dir / EVE_DOCS_REFERENCE_FILE).write_text(eve_docs_reference, encoding="utf-8")
    context = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "review_type": review_type,
        "repo": str(repo.resolve()),
        "engine": engine,
        "target": target,
        "review_identity": review_identity,
        "eve_kit_fingerprint": eve_kit_fingerprint(eve_kit_reference),
        "parent_run": str(parent_run) if parent_run else None,
        "accepted_findings": list(accepted_findings),
    }
    (run_dir / CONTEXT_FILE).write_text(
        json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
