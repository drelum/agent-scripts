from __future__ import annotations

import argparse
import base64
import errno
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import tty
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, Sequence


SESSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
ANSI_CSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
ANSI_OSC_PATTERN = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")
WINDOWS_BROWSER_RELATIVE = Path(
    "AppData/Roaming/npm/node_modules/agent-browser/bin/agent-browser-win32-x64.exe"
)
BLOCKED_COMMANDS = {"close", "connect", "install", "profiles"}
BLOCKED_OPTIONS = {
    "--auto-connect",
    "--cdp",
    "--executable-path",
    "--headed",
    "--namespace",
    "--no-pin-tab",
    "--profile",
    "--session",
}
CURSOR_POSITION_QUERY = b"\x1b[6n"


@dataclass(frozen=True)
class Profile:
    name: str
    directory: str
    port: int


PROFILES = {
    "aitrus": Profile("aitrus", "Aitrus", 9225),
    "investments": Profile("investments", "Investidor10", 9224),
}


class BrowserError(RuntimeError):
    pass


class PtyProcess(Protocol):
    before: bytes
    exitstatus: int | None
    signalstatus: int | None

    def expect(self) -> int: ...

    def send(self, value: bytes) -> object: ...

    def close(self) -> None: ...

    def terminate(self, force: bool = False) -> object: ...


class StdlibPty:
    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout: float,
        dimensions: tuple[int, int],
    ) -> None:
        pid, master_fd = pty.fork()
        if pid == 0:
            try:
                tty.setraw(sys.stdin.fileno())
                os.execv(command[0], list(command))
            except BaseException:
                os._exit(127)
        rows, columns = dimensions
        fcntl.ioctl(
            master_fd,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", rows, columns, 0, 0),
        )
        self.pid = pid
        self.master_fd = master_fd
        self.deadline = time.monotonic() + timeout
        self.buffer = b""
        self.before = b""
        self.exitstatus: int | None = None
        self.signalstatus: int | None = None
        self.finished = False

    def _poll(self) -> bool:
        if self.finished:
            return True
        waited_pid, status = os.waitpid(self.pid, os.WNOHANG)
        if waited_pid == 0:
            return False
        self.finished = True
        if os.WIFEXITED(status):
            self.exitstatus = os.WEXITSTATUS(status)
            self.signalstatus = None
        elif os.WIFSIGNALED(status):
            self.exitstatus = None
            self.signalstatus = os.WTERMSIG(status)
        return True

    def _wait(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while not self._poll() and time.monotonic() < deadline:
            time.sleep(0.01)
        return self.finished

    def _finish_eof(self) -> int:
        self.before = self.buffer
        self.buffer = b""
        self._wait(1)
        return 1

    def expect(self) -> int:
        while True:
            query_at = self.buffer.find(CURSOR_POSITION_QUERY)
            if query_at >= 0:
                self.before = self.buffer[:query_at]
                self.buffer = self.buffer[query_at + len(CURSOR_POSITION_QUERY) :]
                return 0

            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                self.before = self.buffer
                self.buffer = b""
                return 2

            readable, _, _ = select.select(
                [self.master_fd], [], [], min(0.1, remaining)
            )
            if not readable:
                if self._poll():
                    return self._finish_eof()
                continue
            try:
                chunk = os.read(self.master_fd, 65536)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                chunk = b""
            if chunk:
                self.buffer += chunk
                continue
            return self._finish_eof()

    def send(self, value: bytes) -> None:
        os.write(self.master_fd, value)

    def close(self) -> None:
        try:
            os.close(self.master_fd)
        except OSError:
            pass
        self._poll()

    def terminate(self, force: bool = False) -> None:
        if not self._poll():
            os.kill(self.pid, signal.SIGTERM)
            if not self._wait(0.5) and force:
                os.kill(self.pid, signal.SIGKILL)
                self._wait(1)
        self.close()


def windows_home() -> Path:
    override = os.environ.get("WINDOWS_CHROME_BROWSER_HOME")
    if override:
        return Path(override).expanduser()
    user = os.environ.get("WINDOWS_CHROME_BROWSER_USER", "drelu")
    return Path("/mnt/c/Users") / user


def browser_executable(home: Path) -> Path:
    executable = home / WINDOWS_BROWSER_RELATIVE
    if not executable.is_file():
        raise BrowserError(f"Windows agent-browser not found: {executable}")
    return executable


def chrome_executable() -> Path:
    candidates = (
        Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BrowserError("Windows Chrome executable not found")


def to_windows_path(path: Path) -> str:
    result = subprocess.run(
        ["wslpath", "-w", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    converted = result.stdout.strip()
    if result.returncode != 0 or not converted:
        raise BrowserError(f"cannot convert WSL path for Windows: {path}")
    return converted


def powershell_executable() -> str:
    candidates = (
        "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        "powershell.exe",
    )
    for candidate in candidates:
        if candidate == "powershell.exe" or Path(candidate).is_file():
            return candidate
    raise BrowserError("powershell.exe not found; run this helper inside WSL")


def profile_for(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError as error:
        raise BrowserError(f"unknown profile: {name}") from error


def cdp_status(profile: Profile, home: Path | None = None) -> dict[str, object]:
    expected_profile = to_windows_path(
        (home or windows_home())
        / "AppData/Local/AgentBrowser"
        / profile.directory
    )
    encoded_profile = base64.b64encode(expected_profile.encode("utf-8")).decode(
        "ascii"
    )
    script = (
        "$ErrorActionPreference='Stop';"
        "$expected=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"
        f"{encoded_profile}'));"
        f"$port='{profile.port}';"
        f"$r=Invoke-RestMethod -Uri 'http://127.0.0.1:{profile.port}/json/version' -TimeoutSec 3;"
        "$portArg='--remote-debugging-port='+$port;"
        "$profileArg='--user-data-dir='+$expected;"
        "$quotedProfileArg='--user-data-dir=\"'+$expected+'\"';"
        "$profilePattern='(?:^|\\s)(?:'+[regex]::Escape($profileArg)+'|'+"
        "[regex]::Escape($quotedProfileArg)+')(?=\\s|$)';"
        "$owners=@(Get-CimInstance Win32_Process | Where-Object {"
        "$_.Name -eq 'chrome.exe' -and $_.CommandLine -notmatch '--type=' -and "
        "$_.CommandLine.IndexOf($portArg,[System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and "
        "$_.CommandLine -match $profilePattern});"
        "if($owners.Count -ne 1){Write-Output 'PROFILE_MISMATCH'; exit 11};"
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
        "Write-Output ($r.Browser+'|'+$r.'Protocol-Version')"
    )
    result = subprocess.run(
        [powershell_executable(), "-NoProfile", "-NonInteractive", "-Command", script],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=8,
    )
    if result.returncode != 0:
        reason = (
            "profile_mismatch"
            if "PROFILE_MISMATCH" in result.stdout
            else "cdp_unavailable"
        )
        return {
            "available": False,
            "browser": None,
            "protocol": None,
            "reason": reason,
        }
    browser, _, protocol = result.stdout.strip().partition("|")
    return {
        "available": bool(browser),
        "browser": browser or None,
        "protocol": protocol or None,
        "reason": None,
    }


def start_profile(profile: Profile, home: Path) -> bool:
    initial_status = cdp_status(profile, home)
    if initial_status["available"]:
        return False
    if initial_status.get("reason") == "profile_mismatch":
        raise BrowserError(
            f"CDP {profile.port} belongs to a different Chrome profile"
        )
    chrome = chrome_executable()
    profile_dir = to_windows_path(
        home / "AppData/Local/AgentBrowser" / profile.directory
    )
    command = [
        str(chrome),
        "--remote-allow-origins=*",
        f"--remote-debugging-port={profile.port}",
        f"--user-data-dir={profile_dir}",
        "--restore-last-session",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "about:blank",
    ]
    try:
        subprocess.Popen(
            command,
            cwd=home,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        raise BrowserError(f"cannot start Windows Chrome: {error}") from error
    for _ in range(20):
        time.sleep(0.5)
        status = cdp_status(profile, home)
        if status["available"]:
            return True
        if status.get("reason") == "profile_mismatch":
            raise BrowserError(
                f"CDP {profile.port} belongs to a different Chrome profile"
            )
    raise BrowserError(
        f"Windows Chrome started but CDP {profile.port} did not become available"
    )


def clean_terminal_output(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace").replace("\r", "")
    text = ANSI_CSI_PATTERN.sub("", text)
    return ANSI_OSC_PATTERN.sub("", text)


def validate_browser_args(arguments: Sequence[str]) -> None:
    if not arguments:
        raise BrowserError("missing agent-browser command after --")
    if arguments[0].startswith("-"):
        raise BrowserError("agent-browser command must be the first argument after --")
    if arguments[0] in BLOCKED_COMMANDS:
        raise BrowserError(
            f"agent-browser {arguments[0]} is not allowed for a persistent Windows Chrome; use tab operations"
        )
    for argument in arguments:
        option = argument.split("=", 1)[0]
        if option in BLOCKED_OPTIONS:
            raise BrowserError(f"wrapper-owned option is not allowed: {option}")


def browser_command(
    executable: Path,
    profile: Profile,
    session: str,
    arguments: Sequence[str],
) -> list[str]:
    if not SESSION_PATTERN.fullmatch(session):
        raise BrowserError(
            "--session must use 1-64 lowercase letters, digits, dots, underscores, or hyphens"
        )
    validate_browser_args(arguments)
    return [
        str(executable),
        "--namespace",
        f"windows-chrome-browser-{profile.name}",
        "--session",
        session,
        "--cdp",
        str(profile.port),
        "--pin-tab",
        *arguments,
    ]


def spawn_browser(command: Sequence[str]) -> PtyProcess:
    return StdlibPty(
        command,
        timeout=30,
        dimensions=(40, 10000),
    )


def run_browser(command: Sequence[str]) -> tuple[int, str]:
    child = spawn_browser(command)
    chunks: list[bytes] = []
    try:
        while True:
            matched = child.expect()
            chunks.append(child.before)
            if matched == 0:
                child.send(b"\x1b[1;1R")
                continue
            if matched == 1:
                break
            raise BrowserError("Windows agent-browser timed out after 30 seconds")
    except Exception:
        child.terminate(force=True)
        raise
    child.close()
    code = child.exitstatus
    if code is None:
        code = 128 + (child.signalstatus or 1)
    return code, clean_terminal_output(b"".join(chunks))


def profiles_result() -> list[dict[str, object]]:
    result = []
    for profile in PROFILES.values():
        result.append({**asdict(profile), **cdp_status(profile)})
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control pages and tabs in persistent Windows Chrome profiles from WSL."
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    profiles_parser = subparsers.add_parser("profiles", help="List configured profiles and CDP status.")
    profiles_parser.add_argument("--json", action="store_true")

    status_parser = subparsers.add_parser("status", help="Check one profile's CDP status.")
    status_parser.add_argument("--profile", choices=PROFILES, required=True)
    status_parser.add_argument("--json", action="store_true")

    start_parser = subparsers.add_parser("start", help="Start a profile only when CDP is unavailable.")
    start_parser.add_argument("--profile", choices=PROFILES, required=True)

    run_parser = subparsers.add_parser("run", help="Run an agent-browser page or tab command.")
    run_parser.add_argument("--profile", choices=PROFILES, required=True)
    run_parser.add_argument("--session", required=True)
    run_parser.add_argument("browser_args", nargs=argparse.REMAINDER)
    return parser


def print_status(profile: Profile, status: dict[str, object], as_json: bool) -> None:
    payload = {**asdict(profile), **status}
    if as_json:
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return
    state = "available" if status["available"] else "unavailable"
    print(f"{profile.name}: {state} (CDP {profile.port})")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "profiles":
            profiles = profiles_result()
            if args.json:
                json.dump(profiles, sys.stdout, ensure_ascii=False)
                sys.stdout.write("\n")
            else:
                for item in profiles:
                    state = "available" if item["available"] else "unavailable"
                    print(f"{item['name']}: {state} (CDP {item['port']})")
            return 0

        profile = profile_for(args.profile)
        if args.operation == "status":
            status = cdp_status(profile)
            print_status(profile, status, args.json)
            return 0 if status["available"] else 1

        home = windows_home()
        if args.operation == "start":
            started = start_profile(profile, home)
            print(f"{profile.name}: {'started' if started else 'already available'} (CDP {profile.port})")
            return 0

        status = cdp_status(profile)
        if not status["available"]:
            if status.get("reason") == "profile_mismatch":
                raise BrowserError(
                    f"CDP {profile.port} belongs to a different Chrome profile"
                )
            raise BrowserError(
                f"profile {profile.name} is unavailable on CDP {profile.port}; run start first"
            )
        browser_args = list(args.browser_args)
        if browser_args and browser_args[0] == "--":
            browser_args = browser_args[1:]
        command = browser_command(
            browser_executable(home), profile, args.session, browser_args
        )
        code, output = run_browser(command)
        sys.stdout.write(output)
        if output and not output.endswith("\n"):
            sys.stdout.write("\n")
        return code
    except (BrowserError, OSError, subprocess.SubprocessError) as error:
        print(f"windows-chrome-browser: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
