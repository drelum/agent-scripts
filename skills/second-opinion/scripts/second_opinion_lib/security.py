from __future__ import annotations

import re


SECRET_TEXT = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:sk-(?:proj-|ant-|svcacct-)?[A-Za-z0-9_-]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}|AIza[A-Za-z0-9_-]{30,})\b|"
    r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b|"
    r"(?i:(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|"
    r"aws_access_key_id|aws_secret_access_key|aws_session_token|token))"
    r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{20,}['\"]?|"
    r"(?i:authorization)\s*:\s*['\"]?bearer\s+[A-Za-z0-9._~+/=-]{20,}"
)


def contains_secret_like_text(content: str) -> bool:
    return bool(SECRET_TEXT.search(content))
