"""Abre no app padrão do Windows o link file:// clicado ou o path selecionado num pane do herdr."""

import json
import os
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

WINDOWS_PATH = re.compile(r"^(?:\\\\wsl(?:\.localhost|\$)\\.+|[A-Za-z]:\\.*)$")
WRAPPER_PAIRS = {"`": "`", "'": "'", '"': '"', "(": ")", "[": "]", "<": ">", "{": "}"}


def wslpath_w(linux_path: str) -> str:
    return subprocess.run(
        ["wslpath", "-w", linux_path], capture_output=True, text=True, check=False
    ).stdout.strip()


def from_file_uri(uri: str) -> str:
    """file:///C:/x, file://wsl.localhost/Ubuntu/x, file:///home/x → path Windows."""
    url = urlsplit(uri)
    path = unquote(url.path)
    if url.netloc and url.netloc.lower() != "localhost":
        return "\\\\" + url.netloc + path.replace("/", "\\")
    if re.match(r"^/[A-Za-z]:/", path):
        return path[1:].replace("/", "\\")
    return wslpath_w(path)


def from_selection(text: str, cwd: str | None) -> str | None:
    """Path selecionado (Windows, Linux absoluto, ~/ ou relativo ao cwd do pane) → path Windows."""
    text = text.strip()
    while text:
        if text.lower().startswith("file://"):
            return from_file_uri(text)
        if WINDOWS_PATH.match(text):
            return text
        if text.startswith("\\wsl"):  # markdown comeu uma barra do \\wsl...
            return "\\" + text
        path = os.path.expanduser(text)
        if os.path.isabs(path) or cwd:
            if not os.path.isabs(path):
                path = os.path.join(cwd, path)
            path = os.path.normpath(path)
            if os.path.exists(path):
                return wslpath_w(path)
        # O nome literal tem precedência; retirar somente molduras equilibradas.
        if len(text) >= 2 and WRAPPER_PAIRS.get(text[0]) == text[-1]:
            text = text[1:-1]
        elif text != text.strip():
            text = text.strip()
        else:
            break
    return None


def main() -> int:
    context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "{}")
    clicked = os.environ.get("HERDR_PLUGIN_CLICKED_URL") or context.get("clicked_url")
    if clicked:
        raw, path = clicked, from_file_uri(clicked.strip())
    else:
        raw = context.get("selected_text") or ""
        cwd = context.get("focused_pane_cwd") or context.get("workspace_cwd")
        path = from_selection(raw, cwd)
    if not path or not WINDOWS_PATH.match(path):
        print(f"path não reconhecido ou inexistente: {raw!r}", file=sys.stderr)
        return 2
    # explorer.exe abre arquivos no app padrão e pastas no Explorer; sempre sai com 1.
    subprocess.run(["explorer.exe", path], cwd="/mnt/c", check=False)
    print(f"aberto: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
