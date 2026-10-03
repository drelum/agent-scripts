from __future__ import annotations

import difflib
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

EVE_DOC_ENDPOINTS = {
    "llms.txt": "https://eve.dev/llms.txt",
    "sitemap.md": "https://eve.dev/sitemap.md",
    "llms-full.txt": "https://eve.dev/llms-full.txt",
}
MAX_ENDPOINT_BYTES = {
    "llms.txt": 512 * 1024,
    "sitemap.md": 1024 * 1024,
    "llms-full.txt": 4 * 1024 * 1024,
}
CACHE_SCHEMA_VERSION = 6
DEFAULT_CACHE_ROOT = Path(
    os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
) / "agent-scripts" / "eve-docs"
PAGE_HEADER = re.compile(
    r"(?m)^---\ntitle:\s*(?P<title>[^\n]+)\ndescription:\s*(?P<description>[^\n]+)\n---\n"
)
LLMS_LINK = re.compile(
    r"(?m)^- \[(?P<title>[^\]]+)\]\((?P<url>https://eve\.dev/[^)]+\.md)\):\s*(?P<description>[^\n]+)"
)
SITEMAP_LINK = re.compile(
    r"(?m)^\s*- \[(?P<title>[^\]]+)\]\([^)]+\).*?\| Summary: (?P<description>.*?) \|.*?\| Canonical: (?P<path>/[^\s|]+)"
)


class EveDocsError(RuntimeError):
    pass


@dataclass(frozen=True)
class EveDocsSnapshot:
    path: Path | None
    reference: str
    fresh: bool
    warning: str | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _prepare_root(root: Path) -> Path:
    cache_root = root.expanduser().absolute()
    cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if cache_root.is_symlink() or not cache_root.is_dir():
        raise EveDocsError(f"Eve documentation cache is not a real directory: {cache_root}")
    metadata = cache_root.stat(follow_symlinks=False)
    if metadata.st_uid != os.getuid():
        raise EveDocsError(f"Eve documentation cache has a different owner: {cache_root}")
    cache_root.chmod(0o700)
    (cache_root / "snapshots").mkdir(mode=0o700, exist_ok=True)
    return cache_root


def _current_snapshot(root: Path, state: dict[str, Any]) -> Path | None:
    snapshot_id = state.get("current_snapshot")
    if not isinstance(snapshot_id, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot_id):
        return None
    path = root / "snapshots" / snapshot_id
    return path if not path.is_symlink() and path.is_dir() else None


def _download(url: str, etag: str | None, limit: int) -> tuple[bytes | None, str | None]:
    headers = {"User-Agent": "agent-scripts-eve-docs/1"}
    if etag:
        headers["If-None-Match"] = etag
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            content = response.read(limit + 1)
            if len(content) > limit:
                raise EveDocsError(f"Eve documentation endpoint exceeds limit: {url}")
            return content, response.headers.get("ETag")
    except HTTPError as error:
        if error.code == 304:
            return None, etag
        raise EveDocsError(f"Eve documentation request failed ({error.code}): {url}") from error
    except OSError as error:
        raise EveDocsError(f"Eve documentation request failed: {url}: {error}") from error


def _snapshot_id(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    digest.update(f"schema:{CACHE_SCHEMA_VERSION}\0".encode("utf-8"))
    for name in sorted(files):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[name])
        digest.update(b"\0")
    return digest.hexdigest()


def _page_path(url: str) -> PurePosixPath | None:
    parsed = urlparse(url)
    path = PurePosixPath(parsed.path.lstrip("/"))
    if parsed.scheme != "https" or parsed.hostname != "eve.dev" or not path.parts:
        return None
    if ".." in path.parts or path.suffix != ".md":
        return None
    return path


def _split_pages(llms: str, sitemap: str, full: str) -> list[tuple[str, str, str, str, str]]:
    urls: dict[str, list[str]] = {}
    exact_urls: dict[tuple[str, str], str] = {}
    records: list[tuple[str, str, str]] = []
    for match in LLMS_LINK.finditer(llms):
        title = match.group("title").strip()
        description = match.group("description").strip()
        urls.setdefault(title, []).append(match.group("url"))
        exact_urls[(title, description)] = match.group("url")
        records.append((title, description, match.group("url")))
    for match in SITEMAP_LINK.finditer(sitemap):
        title = match.group("title").strip()
        description = match.group("description").strip()
        canonical = match.group("path").rstrip("/")
        url = f"https://eve.dev{canonical}.md"
        values = urls.setdefault(title, [])
        if url not in values:
            values.append(url)
        exact_urls.setdefault((title, description), url)
        records.append((title, description, url))
    matches = list(PAGE_HEADER.finditer(full))
    pages: list[tuple[str, str, str, str, str]] = []
    for index, match in enumerate(matches):
        title = match.group("title").strip().strip('"\'')
        description = match.group("description").strip().strip('"\'')
        url = exact_urls.get((title, description), "")
        candidates = urls.get(title, [])
        if not url and len(candidates) == 1:
            url = candidates[0]
        if not url:
            normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
            normalized_description = re.sub(
                r"[^a-z0-9]+", " ", description.lower()
            ).strip()
            scored = []
            for candidate_title, candidate_description, candidate_url in records:
                title_score = difflib.SequenceMatcher(
                    None,
                    normalized_title,
                    re.sub(r"[^a-z0-9]+", " ", candidate_title.lower()).strip(),
                ).ratio()
                description_score = difflib.SequenceMatcher(
                    None,
                    normalized_description,
                    re.sub(r"[^a-z0-9]+", " ", candidate_description.lower()).strip(),
                ).ratio()
                scored.append(
                    (
                        max(
                            (title_score + description_score) / 2,
                            description_score * 0.95,
                        ),
                        candidate_url,
                    )
                )
            if scored:
                score, candidate_url = max(scored)
                if score >= 0.72:
                    url = candidate_url
        path = _page_path(url) if url else None
        if path is None:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or f"page-{index + 1}"
            path = PurePosixPath("unmapped") / f"{slug}.md"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(full)
        content = (full[match.start() : end].rstrip() + "\n").replace(
            "---\n", f"---\nsource: {url or 'unknown'}\n", 1
        )
        pages.append((title, description, url, content, path.as_posix()))
    return pages


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def _create_snapshot(root: Path, snapshot_id: str, files: dict[str, bytes]) -> Path:
    destination = root / "snapshots" / snapshot_id
    if destination.is_dir() and not destination.is_symlink():
        return destination
    temporary = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=root / "snapshots"))
    temporary.chmod(0o700)
    try:
        for name, content in files.items():
            _write_text(temporary / name, content.decode("utf-8", errors="strict"))
        pages = _split_pages(
            files["llms.txt"].decode("utf-8"),
            files["sitemap.md"].decode("utf-8"),
            files["llms-full.txt"].decode("utf-8"),
        )
        index_lines = [
            "# EVE documentation snapshot",
            "",
            f"Snapshot: `{snapshot_id}`",
            "",
            "Read only the pages relevant to the reviewed imports or behavior.",
            "",
        ]
        manifest_pages: list[dict[str, str]] = []
        for title, description, url, content, relative in pages:
            page_path = temporary / "pages" / relative
            _write_text(page_path, content)
            index_lines.append(
                f"- [{title}](pages/{relative}) — {description} — {url or 'unmapped'}"
            )
            manifest_pages.append(
                {"title": title, "description": description, "url": url, "path": f"pages/{relative}"}
            )
        _write_text(temporary / "INDEX.md", "\n".join(index_lines) + "\n")
        manifest = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "snapshot": snapshot_id,
            "created_at": _now(),
            "sources": [
                {
                    "url": EVE_DOC_ENDPOINTS[name],
                    "file": name,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content),
                }
                for name, content in files.items()
            ],
            "pages": manifest_pages,
        }
        _write_text(
            temporary / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


def _atomic_state(path: Path, state: dict[str, Any]) -> None:
    handle, temporary_name = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _reference(path: Path | None, state: dict[str, Any], fresh: bool, warning: str | None) -> str:
    payload = {
        "available": path is not None,
        "fresh": fresh,
        "snapshot": state.get("current_snapshot") if path else None,
        "path": str(path) if path else None,
        "index": str(path / "INDEX.md") if path else None,
        "checked_at": state.get("checked_at"),
        "sources": list(EVE_DOC_ENDPOINTS.values()) if path else [],
        "warning": warning,
    }
    return _safe_json(payload)


def refresh_eve_docs(
    cache_root: Path = DEFAULT_CACHE_ROOT,
    *,
    offline: bool = False,
) -> EveDocsSnapshot:
    root = _prepare_root(cache_root)
    lock_path = root / ".lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        lock_path.chmod(0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state_path = root / "state.json"
        state = _read_json(state_path)
        current = _current_snapshot(root, state)
        if offline:
            warning = None if current else "no cached EVE documentation snapshot is available"
            return EveDocsSnapshot(current, _reference(current, state, False, warning), False, warning)
        try:
            endpoint_state = state.get("endpoints") if isinstance(state.get("endpoints"), dict) else {}
            files: dict[str, bytes] = {}
            updated_endpoints: dict[str, dict[str, Any]] = {}
            for name, url in EVE_DOC_ENDPOINTS.items():
                previous = endpoint_state.get(name) if isinstance(endpoint_state.get(name), dict) else {}
                etag = previous.get("etag") if isinstance(previous.get("etag"), str) else None
                content, new_etag = _download(url, etag, MAX_ENDPOINT_BYTES[name])
                if content is None:
                    if current is None or not (current / name).is_file():
                        raise EveDocsError(f"Eve documentation returned 304 without a local file: {url}")
                    content = (current / name).read_bytes()
                content.decode("utf-8", errors="strict")
                files[name] = content
                updated_endpoints[name] = {"url": url, "etag": new_etag}
            snapshot_id = _snapshot_id(files)
            current = _create_snapshot(root, snapshot_id, files)
            state = {
                "schema_version": CACHE_SCHEMA_VERSION,
                "current_snapshot": snapshot_id,
                "checked_at": _now(),
                "endpoints": updated_endpoints,
            }
            _atomic_state(state_path, state)
            return EveDocsSnapshot(current, _reference(current, state, True, None), True)
        except (EveDocsError, OSError, UnicodeDecodeError) as error:
            warning = str(error)
            current = _current_snapshot(root, state)
            return EveDocsSnapshot(
                current,
                _reference(current, state, False, warning),
                False,
                warning,
            )


def snapshot_path_from_reference(
    reference: str,
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> Path | None:
    try:
        payload = json.loads(reference)
    except json.JSONDecodeError as error:
        raise EveDocsError(f"invalid EVE documentation reference: {error}") from error
    if not isinstance(payload, dict):
        raise EveDocsError("invalid EVE documentation reference: expected an object")
    raw = payload.get("path")
    if not payload.get("available") or not isinstance(raw, str):
        return None
    allowed_root = (cache_root.expanduser().absolute() / "snapshots").resolve()
    path = Path(raw).expanduser().absolute().resolve()
    try:
        path.relative_to(allowed_root)
    except ValueError as error:
        raise EveDocsError(f"EVE documentation snapshot is outside the canonical cache: {path}") from error
    manifest = path / "manifest.json"
    if path.is_symlink() or not path.is_dir() or manifest.is_symlink() or not manifest.is_file():
        raise EveDocsError(f"EVE documentation snapshot is unavailable: {path}")
    if path.stat(follow_symlinks=False).st_uid != os.getuid():
        raise EveDocsError(f"EVE documentation snapshot has a different owner: {path}")
    return path
