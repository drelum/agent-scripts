"""Abre no app padrão do Windows o path clicado num pane do herdr."""

import os
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

WINDOWS_PATH = re.compile(r"^(?:\\\\wsl(?:\.localhost|\$)\\.+|[A-Za-z]:\\.*)$")


def to_windows_path(uri: str) -> str:
    """Converte URI file:// em path Windows (file:///C:/x, file://wsl.localhost/Ubuntu/x, file:///home/x)."""
    url = urlsplit(uri.strip())
    path = unquote(url.path)
    if url.netloc and url.netloc.lower() != "localhost":
        return "\\\\" + url.netloc + path.replace("/", "\\")
    if re.match(r"^/[A-Za-z]:/", path):
        return path[1:].replace("/", "\\")
    return subprocess.run(
        ["wslpath", "-w", path], capture_output=True, text=True, check=False
    ).stdout.strip()


def main() -> int:
    raw = os.environ.get("HERDR_PLUGIN_CLICKED_URL", "")
    path = to_windows_path(raw)
    if not WINDOWS_PATH.match(path):
        print(f"path não reconhecido: {raw!r}", file=sys.stderr)
        return 2
    # explorer.exe abre arquivos no app padrão e pastas no Explorer; sempre sai com 1.
    subprocess.run(["explorer.exe", path], cwd="/mnt/c", check=False)
    print(f"aberto: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
