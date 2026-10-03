from __future__ import annotations

import codecs
import json
import re
from pathlib import Path, PurePosixPath

EVE_PACKAGES = frozenset({"eve", "@aitrus/eve-kit"})
MANIFEST_LIMIT_BYTES = 256 * 1024
DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)
_CHANGED_PATH = re.compile(
    r'^(?:(?:\+\+\+|---) (?P<diff>(?:[ab]/[^\t\n]+|"[ab]/(?:[^"\\]|\\.)*"))\t?|--- (?:untracked|initial) (?:file|symlink): (?P<file>.+?) ---)$',
    re.MULTILINE,
)
_EVE_IMPORT = re.compile(
    r"""^[+ -]?\s*(?:import|export)\b[^\n]*?["'](?:eve|@aitrus/eve-kit)(?:/[^"'\n]*)?["']""",
    re.MULTILINE,
)


def changed_paths(bundle: str) -> tuple[str, ...]:
    paths: list[str] = []
    for match in _CHANGED_PATH.finditer(bundle):
        value = match.group("diff")
        if value:
            if value.startswith('"'):
                value = codecs.escape_decode(value[1:-1].encode("utf-8"))[0].decode("utf-8", "surrogateescape")
            value = value[2:]
        else:
            value = (match.group("file") or "").split(" -> ", 1)[0]
        if value and value not in paths:
            paths.append(value)
    return tuple(paths)


def _manifest_declares_eve(manifest: Path) -> bool:
    if manifest.is_symlink() or not manifest.is_file():
        return False
    if manifest.stat().st_size > MANIFEST_LIMIT_BYTES:
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    if data.get("name") in EVE_PACKAGES:
        return True
    return any(
        isinstance(data.get(section), dict) and EVE_PACKAGES & data[section].keys()
        for section in DEPENDENCY_SECTIONS
    )


def detect_eve(repo: Path, bundle: str) -> bool:
    """Detecta EVE pelos manifests que governam os arquivos alterados ou por imports no diff."""
    if _EVE_IMPORT.search(bundle):
        return True
    root = repo.resolve()
    checked: dict[Path, bool] = {}
    for relative in changed_paths(bundle):
        parts = PurePosixPath(relative).parts
        if ".." in parts or PurePosixPath(relative).is_absolute():
            continue
        for depth in range(len(parts) - 1, -1, -1):
            directory = root.joinpath(*parts[:depth])
            if directory not in checked:
                checked[directory] = _manifest_declares_eve(directory / "package.json")
            if checked[directory]:
                return True
    return False
