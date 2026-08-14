from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from windows_chrome_browser import (
    BrowserError,
    PROFILES,
    browser_command,
    cdp_status,
    clean_terminal_output,
    main,
    run_browser,
    start_profile,
    to_windows_path,
    validate_browser_args,
)


class FakePty:
    def __init__(self) -> None:
        self.events = [0, 1]
        self.before_values = [b"\x1b[?9001h", b'{"success":true}\r\n']
        self.before = b""
        self.sent: list[bytes] = []
        self.exitstatus = 0
        self.signalstatus = None
        self.terminated = False

    def expect(self) -> int:
        event = self.events.pop(0)
        self.before = self.before_values.pop(0)
        return event

    def send(self, value: bytes) -> None:
        self.sent.append(value)

    def close(self) -> None:
        return None

    def terminate(self, force: bool = False) -> None:
        self.terminated = force


class WindowsChromeBrowserCase(unittest.TestCase):
    def test_command_owns_cdp_namespace_session_and_pin(self) -> None:
        command = browser_command(
            Path("/tmp/agent-browser.exe"),
            PROFILES["aitrus"],
            "gmail-triage",
            ["tab", "list", "--json"],
        )
        self.assertEqual(command[command.index("--cdp") + 1], "9225")
        self.assertEqual(command[command.index("--session") + 1], "gmail-triage")
        self.assertEqual(
            command[command.index("--namespace") + 1],
            "windows-chrome-browser-aitrus",
        )
        self.assertIn("--pin-tab", command)

    def test_rejects_global_close_and_wrapper_overrides(self) -> None:
        with self.assertRaisesRegex(BrowserError, "not allowed"):
            validate_browser_args(["close"])
        with self.assertRaisesRegex(BrowserError, "command must be the first"):
            validate_browser_args(["--debug", "close"])
        for option in ("--cdp", "--session=other", "--no-pin-tab"):
            with self.subTest(option=option):
                with self.assertRaisesRegex(BrowserError, "wrapper-owned"):
                    validate_browser_args(["snapshot", option])

    def test_rejects_unsafe_session_name(self) -> None:
        with self.assertRaisesRegex(BrowserError, "--session"):
            browser_command(
                Path("/tmp/agent-browser.exe"),
                PROFILES["aitrus"],
                "Aitrus session",
                ["snapshot"],
            )

    def test_pty_answers_cursor_query_and_cleans_output(self) -> None:
        fake = FakePty()
        with patch("windows_chrome_browser.spawn_browser", return_value=fake):
            code, output = run_browser(["agent-browser.exe", "--version"])
        self.assertEqual(code, 0)
        self.assertEqual(fake.sent, [b"\x1b[1;1R"])
        self.assertEqual(output, '{"success":true}\n')

    def test_terminal_cleaner_preserves_utf8_and_removes_ansi(self) -> None:
        raw = "\x1b[?9001hÍon\r\n\x1b]0;title\x07Aitrus\x1b[?9001l".encode()
        self.assertEqual(clean_terminal_output(raw), "Íon\nAitrus")

    def test_converts_wsl_profile_path_for_windows(self) -> None:
        with patch("windows_chrome_browser.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "C:\\Users\\drelu\\Profile\n"
            converted = to_windows_path(Path("/mnt/c/Users/drelu/Profile"))
        self.assertEqual(converted, "C:\\Users\\drelu\\Profile")
        run.assert_called_once_with(
            ["wslpath", "-w", "/mnt/c/Users/drelu/Profile"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_start_is_idempotent_when_cdp_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with patch(
                "windows_chrome_browser.cdp_status",
                return_value={"available": True},
            ), patch("windows_chrome_browser.subprocess.Popen") as popen:
                self.assertFalse(start_profile(PROFILES["aitrus"], Path(temp)))
            popen.assert_not_called()

    def test_cdp_status_rejects_wrong_profile_owner(self) -> None:
        with patch(
            "windows_chrome_browser.to_windows_path",
            return_value=r"C:\Users\drelu\Aitrus",
        ), patch("windows_chrome_browser.subprocess.run") as run:
            run.return_value.returncode = 11
            run.return_value.stdout = "PROFILE_MISMATCH\n"
            run.return_value.stderr = ""
            status = cdp_status(PROFILES["aitrus"], Path("/mnt/c/Users/drelu"))
        self.assertFalse(status["available"])
        self.assertEqual(status["reason"], "profile_mismatch")
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")
        powershell = run.call_args.args[0][-1]
        self.assertIn("(?=\\s|$)", powershell)
        self.assertIn("$_.CommandLine -match $profilePattern", powershell)
        self.assertNotIn("IndexOf($profileArg", powershell)

    def test_start_refuses_port_owned_by_another_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with patch(
                "windows_chrome_browser.cdp_status",
                return_value={"available": False, "reason": "profile_mismatch"},
            ), patch("windows_chrome_browser.subprocess.Popen") as popen:
                with self.assertRaisesRegex(BrowserError, "different Chrome profile"):
                    start_profile(PROFILES["aitrus"], Path(temp))
            popen.assert_not_called()

    def test_start_waits_for_cdp_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            chrome = home / "chrome.exe"
            chrome.touch()
            with patch(
                "windows_chrome_browser.cdp_status",
                side_effect=[{"available": False}, {"available": True}],
            ), patch(
                "windows_chrome_browser.chrome_executable", return_value=chrome
            ), patch(
                "windows_chrome_browser.to_windows_path",
                return_value=r"C:\Users\drelu\Aitrus",
            ), patch("windows_chrome_browser.subprocess.Popen") as popen, patch(
                "windows_chrome_browser.time.sleep"
            ):
                self.assertTrue(start_profile(PROFILES["aitrus"], home))
            popen.assert_called_once()

    def test_status_json_reports_profile(self) -> None:
        with patch(
            "windows_chrome_browser.cdp_status",
            return_value={
                "available": True,
                "browser": "Chrome/151",
                "protocol": "1.3",
            },
        ), patch("sys.stdout") as stdout:
            stdout.write = unittest.mock.MagicMock()
            self.assertEqual(main(["status", "--profile", "aitrus", "--json"]), 0)
            rendered = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(rendered)
        self.assertEqual(payload["port"], 9225)
        self.assertTrue(payload["available"])


if __name__ == "__main__":
    unittest.main()
