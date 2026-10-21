"""Diagnóstico por etapa sem argumentos, payloads ou saída bruta de subprocessos."""
from enum import StrEnum
from pathlib import Path
import re
import subprocess


class FailureCode(StrEnum):
    TRANSIENT = 'transient_read'
    ACCESS = 'access_denied'
    TIMEOUT = 'timeout'
    SUBPROCESS = 'subprocess_failed'
    INVALID = 'invalid_data_or_integrity'


def describe(error, phase):
    from session_context import diagnostic_text
    status = getattr(error, 'status', None)
    if status is None:
        match = re.search(r'HTTP (\d{3})', str(error))
        status = int(match[1]) if match else None
    command = getattr(error, 'cmd', None)
    tool = getattr(error, 'tool', None)
    if isinstance(command, (list, tuple)) and command:
        tool = Path(command[0]).name
    code = FailureCode.INVALID
    if status in (429, 500, 502, 503, 504):
        code = FailureCode.TRANSIENT
    elif status in (401, 403):
        code = FailureCode.ACCESS
    elif isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
        code = FailureCode.TIMEOUT
    elif isinstance(error, subprocess.SubprocessError):
        code = FailureCode.SUBPROCESS
    elif getattr(error, 'retryable', False):
        code = FailureCode.TIMEOUT if 'timeout' in str(error).lower() else FailureCode.TRANSIENT
    # subprocess.args pode conter JSON e credenciais: nunca usar str(error) nesse caso.
    reason = diagnostic_text(str(error)) if isinstance(error, ValueError) or status else type(error).__name__
    return {'phase': phase, 'code': code, 'tool': tool, 'http_status': status,
            'exit_code': getattr(error, 'returncode', None), 'error_type': type(error).__name__,
            'reason': reason[:600], 'retryable': code in (FailureCode.TRANSIENT, FailureCode.TIMEOUT)}
