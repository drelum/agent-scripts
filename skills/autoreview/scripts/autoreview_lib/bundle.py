from __future__ import annotations

import json
import os
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
    identity: dict[str, object]


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


def _path_is_selected(relative: str, selected: tuple[str, ...]) -> bool:
    return not selected or any(
        relative == path or relative.startswith(f"{path.rstrip('/')}/")
        for path in selected
    )


def _changed_provenance_matches_scope(
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


def _symlink_section(kind: str, relative: str, file: Path) -> str:
    # Registra só o alvo do link; o conteúdo apontado nunca entra no bundle.
    target = json.dumps(os.readlink(file), ensure_ascii=True)
    return f"\n--- {kind} symlink: {relative} -> {target} (target content not included) ---\n"


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
        file = repo / relative
        if file.is_symlink():
            sections.append(_symlink_section("untracked", relative, file))
            continue
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
        file = repo / relative
        if file.is_symlink():
            sections.append(_symlink_section("initial", relative, file))
            continue
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
        sections.append(f"\n--- initial file: {relative} ---\n{text}")
    return "".join(sections)


def _local(repo: Path, max_file_bytes: int, paths: tuple[str, ...]) -> ReviewBundle:
    branch = git(repo, "branch", "--show-current").strip() or None
    if not _has_head(repo):
        return ReviewBundle(
            _scoped_label("initial working tree (no HEAD)", paths),
            _initial_worktree(repo, max_file_bytes, paths),
            {"mode": "local", "paths": list(paths), "head": None, "branch": branch},
        )
    head = git(repo, "rev-parse", "HEAD").strip()
    pathspecs = _pathspecs(paths)
    _changed_provenance_matches_scope(
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
    return ReviewBundle(
        _scoped_label("local changes", paths),
        patch,
        {"mode": "local", "paths": list(paths), "head": head, "branch": branch},
    )


def _resolve_base(repo: Path, requested: str | None) -> str:
    candidates = [requested] if requested else ["origin/main", "main"]
    for candidate in candidates:
        if candidate and git(repo, "rev-parse", "--verify", candidate, check=False).strip():
            return candidate
    raise BundleError("cannot resolve review base; pass --base <ref>")


def _branch(
    repo: Path,
    base: str | None,
    paths: tuple[str, ...],
    max_file_bytes: int,
) -> ReviewBundle:
    resolved = _resolve_base(repo, base)
    head = git(repo, "rev-parse", "HEAD").strip()
    branch = git(repo, "branch", "--show-current").strip() or None
    base_oid = git(repo, "rev-parse", f"{resolved}^{{commit}}").strip()
    merge_base = git(repo, "merge-base", "HEAD", resolved).strip()
    pathspecs = _pathspecs(paths)
    _changed_provenance_matches_scope(
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
    patch += git(repo, "diff", "--no-ext-diff", "--unified=80", "HEAD", "--", *pathspecs)
    patch += _untracked(repo, max_file_bytes, paths)
    return ReviewBundle(
        _scoped_label(f"branch against {resolved}", paths),
        patch,
        {
            "mode": "branch",
            "paths": list(paths),
            "head": head,
            "branch": branch,
            "base_ref": resolved,
            "base_oid": base_oid,
            "merge_base": merge_base,
        },
    )


def _commit(repo: Path, commit: str, paths: tuple[str, ...]) -> ReviewBundle:
    commit_oid = git(repo, "rev-parse", f"{commit}^{{commit}}").strip()
    head = git(repo, "rev-parse", "HEAD").strip()
    branch = git(repo, "branch", "--show-current").strip() or None
    revision = git(repo, "rev-list", "--parents", "-n", "1", commit).split()
    if len(revision) > 2:
        raise BundleError(
            "merge commits require an explicit comparison; use --mode branch --base <first-parent>"
        )
    matched_scope = _changed_provenance_matches_scope(
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
    return ReviewBundle(
        _scoped_label(f"commit {commit}", paths),
        patch,
        {
            "mode": "commit",
            "paths": list(paths),
            "head": head,
            "branch": branch,
            "commit": commit_oid,
        },
    )


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
        bundle = _branch(repo, base, selected_paths, max_file_bytes)
    elif selected == "commit":
        bundle = _commit(repo, commit, selected_paths)
    else:
        raise BundleError("no review target: clean main checkout; pass --mode and an explicit target")
    if not bundle.content.strip():
        raise BundleError(f"empty review target: {bundle.label}")
    size = len(bundle.content.encode("utf-8"))
    if size > max_bundle_bytes:
        raise BundleError(f"review bundle exceeds limit: {size} > {max_bundle_bytes} bytes")
    return bundle
