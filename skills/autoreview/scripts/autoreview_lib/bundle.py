from __future__ import annotations

import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


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


def _path_is_selected(relative: str, selected: tuple[str, ...]) -> bool:
    return not selected or any(
        relative == path or relative.startswith(f"{path.rstrip('/')}/")
        for path in selected
    )


def _screen_changed_provenance(
    name_status: str,
    label: str,
    selected: tuple[str, ...],
) -> bool:
    fields = name_status.split("\0")
    index = 0
    matched_scope = False
    while index < len(fields) and fields[index]:
        status = fields[index]
        index += 1
        path_count = 2 if status[:1] in {"R", "C"} else 1
        changed_paths = fields[index : index + path_count]
        if len(changed_paths) != path_count or any(not path for path in changed_paths):
            raise BundleError(f"cannot parse changed path provenance for {label}")
        index += path_count
        if any(_path_is_selected(path, selected) for path in changed_paths):
            matched_scope = True
            for path in changed_paths:
                if _sensitive_path(path):
                    raise BundleError(f"sensitive tracked path in {label}: {path}")
    return matched_scope


def _normalized_paths(paths: list[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw in paths or []:
        value = raw.strip()
        path = PurePosixPath(value)
        if (
            not value
            or "\\" in value
            or path.is_absolute()
            or value == "."
            or ".." in path.parts
            or path.parts[:1] == (".git",)
            or any(unicodedata.category(character).startswith("C") for character in value)
        ):
            raise BundleError(f"review path must be repository-relative: {raw}")
        canonical = path.as_posix()
        if canonical not in normalized:
            normalized.append(canonical)
    return tuple(normalized)


def _pathspecs(paths: tuple[str, ...]) -> list[str]:
    return [f":(top,literal){path}" for path in paths]


def _scoped_label(label: str, paths: tuple[str, ...]) -> str:
    return f"{label}; paths: {', '.join(paths)}" if paths else label


def _untracked(repo: Path, max_file_bytes: int, paths: tuple[str, ...]) -> str:
    sections: list[str] = []
    listed = git(
        repo,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        *_pathspecs(paths),
    )
    for relative in listed.split("\0"):
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


def _initial_worktree(repo: Path, max_file_bytes: int, paths: tuple[str, ...]) -> str:
    sections: list[str] = []
    listed = git(
        repo,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        *_pathspecs(paths),
    )
    for relative in listed.split("\0"):
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


def _local(repo: Path, max_file_bytes: int, paths: tuple[str, ...]) -> ReviewBundle:
    if not _has_head(repo):
        return ReviewBundle(
            _scoped_label("initial working tree (no HEAD)", paths),
            _initial_worktree(repo, max_file_bytes, paths),
        )
    pathspecs = _pathspecs(paths)
    _screen_changed_provenance(
        git(
            repo,
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            "--find-copies",
            "--find-copies-harder",
            "HEAD",
            "--",
        ),
        "local changes",
        paths,
    )
    patch = git(repo, "diff", "--no-ext-diff", "--unified=80", "HEAD", "--", *pathspecs)
    patch += _untracked(repo, max_file_bytes, paths)
    return ReviewBundle(_scoped_label("local changes", paths), patch)


def _resolve_base(repo: Path, requested: str | None) -> str:
    candidates = [requested] if requested else ["origin/main", "main"]
    for candidate in candidates:
        if candidate and git(repo, "rev-parse", "--verify", candidate, check=False).strip():
            return candidate
    raise BundleError("cannot resolve review base; pass --base <ref>")


def _branch(repo: Path, base: str | None, paths: tuple[str, ...]) -> ReviewBundle:
    resolved = _resolve_base(repo, base)
    merge_base = git(repo, "merge-base", "HEAD", resolved).strip()
    pathspecs = _pathspecs(paths)
    _screen_changed_provenance(
        git(
            repo,
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            "--find-copies",
            "--find-copies-harder",
            merge_base,
            "HEAD",
            "--",
        ),
        f"branch against {resolved}",
        paths,
    )
    patch = git(
        repo,
        "diff",
        "--no-ext-diff",
        "--unified=80",
        merge_base,
        "HEAD",
        "--",
        *pathspecs,
    )
    return ReviewBundle(_scoped_label(f"branch against {resolved}", paths), patch)


def _commit(repo: Path, commit: str, paths: tuple[str, ...]) -> ReviewBundle:
    revision = git(repo, "rev-list", "--parents", "-n", "1", commit).split()
    if len(revision) > 2:
        raise BundleError(
            "merge commits require an explicit comparison; use --mode branch --base <first-parent>"
        )
    matched_scope = _screen_changed_provenance(
        git(
            repo,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-z",
            "--find-renames",
            "--find-copies",
            "--find-copies-harder",
            commit,
        ),
        f"commit {commit}",
        paths,
    )
    if paths and not matched_scope:
        raise BundleError(
            f"empty review target: {_scoped_label(f'commit {commit}', paths)}"
        )
    patch = git(
        repo,
        "show",
        "--format=fuller",
        "--find-renames",
        "--unified=80",
        commit,
        "--",
        *_pathspecs(paths),
    )
    return ReviewBundle(_scoped_label(f"commit {commit}", paths), patch)


def build_bundle(
    repo: Path,
    mode: str,
    base: str | None,
    commit: str,
    max_bundle_bytes: int,
    max_file_bytes: int = 256 * 1024,
    paths: list[str] | None = None,
) -> ReviewBundle:
    require_repository(repo)
    selected_paths = _normalized_paths(paths)
    selected = mode
    if mode == "auto":
        dirty = bool(git(repo, "status", "--porcelain").strip())
        branch = git(repo, "branch", "--show-current").strip()
        selected = "local" if dirty else "branch" if branch and branch != "main" else ""
    if selected == "local":
        bundle = _local(repo, max_file_bytes, selected_paths)
    elif selected == "branch":
        bundle = _branch(repo, base, selected_paths)
    elif selected == "commit":
        bundle = _commit(repo, commit, selected_paths)
    else:
        raise BundleError("no review target: clean main checkout; pass --mode and an explicit target")
    if not bundle.content.strip():
        raise BundleError(f"empty review target: {bundle.label}")
    _screen(bundle.label, bundle.content)
    size = len(bundle.content.encode("utf-8"))
    if size > max_bundle_bytes:
        raise BundleError(f"review bundle exceeds limit: {size} > {max_bundle_bytes} bytes")
    return bundle
