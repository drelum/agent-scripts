from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class BundleError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReviewBundle:
    label: str
    content: str


SENSITIVE_PATH = re.compile(
    r"(^|/)(id_rsa|id_ed25519|credentials(?:\.json)?|auth\.json|secrets?)(/|$)|"
    r"(^|/)(\.npmrc|\.pypirc|\.netrc|\.git-credentials)$|"
    r"(^|/)\.docker/config\.json$|\.(pem|p12|pfx|key)$",
    re.IGNORECASE,
)
SECRET_TEXT = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?i:(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"aws_access_key_id|aws_secret_access_key|aws_session_token|token))"
    r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{20,}['\"]?|"
    r"(?i:authorization)\s*:\s*['\"]?bearer\s+[A-Za-z0-9._~+/=-]{20,}"
)


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise BundleError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def require_repository(repo: Path) -> None:
    if git(repo, "rev-parse", "--is-inside-work-tree", check=False).strip() != "true":
        raise BundleError(f"not a Git repository: {repo}")


def _sensitive_path(relative: str) -> bool:
    return bool(SENSITIVE_PATH.search(relative.replace("\\", "/")))


def _screen(label: str, content: str) -> None:
    if SECRET_TEXT.search(content):
        raise BundleError(f"secret-like content found in {label}; refusing review bundle")


def _screen_changed_paths(paths: str, label: str) -> None:
    for relative in paths.split("\0"):
        if relative and _sensitive_path(relative):
            raise BundleError(f"sensitive tracked path in {label}: {relative}")


def _untracked(repo: Path, max_file_bytes: int) -> str:
    sections: list[str] = []
    for relative in git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if not relative:
            continue
        if _sensitive_path(relative):
            raise BundleError(f"sensitive untracked path: {relative}")
        file = repo / relative
        if file.is_symlink():
            raise BundleError(f"untracked symlink cannot enter review bundle: {relative}")
        if not file.is_file():
            continue
        size = file.stat().st_size
        if size > max_file_bytes:
            raise BundleError(f"untracked file exceeds limit: {relative} ({size} bytes)")
        with file.open("rb") as handle:
            data = handle.read(max_file_bytes + 1)
        if len(data) > max_file_bytes:
            raise BundleError(f"untracked file exceeds limit while reading: {relative}")
        if b"\0" in data:
            raise BundleError(f"binary untracked file cannot enter review bundle: {relative}")
        text = data.decode("utf-8", errors="strict")
        _screen(relative, text)
        sections.append(f"\n--- untracked file: {relative} ---\n{text}")
    return "".join(sections)


def _has_head(repo: Path) -> bool:
    return bool(git(repo, "rev-parse", "--verify", "HEAD", check=False).strip())


def _initial_worktree(repo: Path, max_file_bytes: int) -> str:
    sections: list[str] = []
    paths = git(
        repo,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    )
    for relative in paths.split("\0"):
        if not relative:
            continue
        if _sensitive_path(relative):
            raise BundleError(f"sensitive path in initial working tree: {relative}")
        file = repo / relative
        if file.is_symlink():
            raise BundleError(f"symlink cannot enter initial review bundle: {relative}")
        if not file.is_file():
            continue
        size = file.stat().st_size
        if size > max_file_bytes:
            raise BundleError(f"initial file exceeds limit: {relative} ({size} bytes)")
        with file.open("rb") as handle:
            data = handle.read(max_file_bytes + 1)
        if len(data) > max_file_bytes:
            raise BundleError(f"initial file exceeds limit while reading: {relative}")
        if b"\0" in data:
            raise BundleError(f"binary initial file cannot enter review bundle: {relative}")
        text = data.decode("utf-8", errors="strict")
        _screen(relative, text)
        sections.append(f"\n--- initial file: {relative} ---\n{text}")
    return "".join(sections)


def _local(repo: Path, max_file_bytes: int) -> ReviewBundle:
    if not _has_head(repo):
        return ReviewBundle(
            "initial working tree (no HEAD)",
            _initial_worktree(repo, max_file_bytes),
        )
    _screen_changed_paths(
        git(repo, "diff", "--name-only", "--no-renames", "-z", "HEAD", "--"),
        "local changes",
    )
    patch = git(repo, "diff", "--no-ext-diff", "--unified=80", "HEAD", "--")
    patch += _untracked(repo, max_file_bytes)
    return ReviewBundle("local changes", patch)


def _resolve_base(repo: Path, requested: str | None) -> str:
    candidates = [requested] if requested else ["origin/main", "main"]
    for candidate in candidates:
        if candidate and git(repo, "rev-parse", "--verify", candidate, check=False).strip():
            return candidate
    raise BundleError("cannot resolve review base; pass --base <ref>")


def _branch(repo: Path, base: str | None) -> ReviewBundle:
    resolved = _resolve_base(repo, base)
    merge_base = git(repo, "merge-base", "HEAD", resolved).strip()
    _screen_changed_paths(
        git(repo, "diff", "--name-only", "--no-renames", "-z", merge_base, "HEAD", "--"),
        f"branch against {resolved}",
    )
    patch = git(repo, "diff", "--no-ext-diff", "--unified=80", merge_base, "HEAD", "--")
    return ReviewBundle(f"branch against {resolved}", patch)


def _commit(repo: Path, commit: str) -> ReviewBundle:
    revision = git(repo, "rev-list", "--parents", "-n", "1", commit).split()
    if len(revision) > 2:
        raise BundleError(
            "merge commits require an explicit comparison; use --mode branch --base <first-parent>"
        )
    _screen_changed_paths(
        git(
            repo,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "--no-renames",
            "-r",
            "-z",
            commit,
        ),
        f"commit {commit}",
    )
    patch = git(repo, "show", "--format=fuller", "--find-renames", "--unified=80", commit, "--")
    return ReviewBundle(f"commit {commit}", patch)


def build_bundle(
    repo: Path,
    mode: str,
    base: str | None,
    commit: str,
    max_bundle_bytes: int,
    max_file_bytes: int = 256 * 1024,
) -> ReviewBundle:
    require_repository(repo)
    selected = mode
    if mode == "auto":
        dirty = bool(git(repo, "status", "--porcelain").strip())
        branch = git(repo, "branch", "--show-current").strip()
        selected = "local" if dirty else "branch" if branch and branch != "main" else ""
    if selected == "local":
        bundle = _local(repo, max_file_bytes)
    elif selected == "branch":
        bundle = _branch(repo, base)
    elif selected == "commit":
        bundle = _commit(repo, commit)
    else:
        raise BundleError("no review target: clean main checkout; pass --mode and an explicit target")
    if not bundle.content.strip():
        raise BundleError(f"empty review target: {bundle.label}")
    _screen(bundle.label, bundle.content)
    size = len(bundle.content.encode("utf-8"))
    if size > max_bundle_bytes:
        raise BundleError(f"review bundle exceeds limit: {size} > {max_bundle_bytes} bytes")
    return bundle
