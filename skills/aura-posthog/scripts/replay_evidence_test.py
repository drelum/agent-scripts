"""Regressões de extração: DOM, privacidade, repetição e arquivos privados."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

from replay_evidence import Mirror, analyze_sample, analyze_window, clean, frame, write_private


def snapshot(timestamp=1000):
    return {"type": 2, "timestamp": timestamp, "data": {"node": {
        "id": 1, "type": 0, "childNodes": [{"id": 2, "tagName": "button",
        "attributes": {"disabled": ""}, "childNodes": [{"id": 3, "type": 3, "textContent": "Buscar"}]}]}}}


class EvidenceTest(unittest.TestCase):
    def test_mutation_updates_click_label_and_removes_disabled(self):
        events = [snapshot(), {"type": 3, "timestamp": 1100, "data": {"source": 0,
                  "texts": [{"id": 3, "value": "Finalizar pedido"}],
                  "attributes": [{"id": 2, "attributes": {"disabled": None}}]}},
                  {"type": 3, "timestamp": 1200, "data": {"source": 2, "type": 2, "id": 3}}]
        click = analyze_window(events)["timeline"][0]
        self.assertEqual(click["control"], "Finalizar pedido")
        self.assertFalse(click["disabled_attribute"])

    def test_removed_target_does_not_resolve_stale_control(self):
        mirror = Mirror()
        mirror.add(snapshot()["data"]["node"])
        mirror.remove(2)
        self.assertEqual(mirror.label(3)["tag"], None)

    def test_input_values_never_enter_export(self):
        events = [snapshot(), {"type": 3, "timestamp": 1050,
                  "data": {"source": 5, "id": 2, "text": "private-sensitive-input"}}]
        result = analyze_window(events)
        self.assertNotIn("private-sensitive-input", json.dumps(result))
        self.assertEqual(sum(result["input_updates_by_control"].values()), 1)

    def test_privacy_redaction(self):
        value = clean("a@farmacia.com https://host/login?token=abc 03.346.822/0001-17 token=secret")
        for secret in ("a@farmacia.com", "?token=abc", "03.346.822/0001-17", "secret"):
            self.assertNotIn(secret, value)

    def test_repetition_is_evidence_not_emotional_score(self):
        clicks = [{"type": 3, "timestamp": 1100 + i * 200,
                   "data": {"source": 2, "type": 2, "id": 2}} for i in range(4)]
        result = analyze_window([snapshot(), *clicks])
        self.assertEqual(result["rapid_repetitions_not_frustration"][0]["count"], 4)
        self.assertNotIn("frustration_score", result)

    def test_multiple_windows_and_analytics_outside_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "s").mkdir()
            (root / "index.json").write_text(json.dumps([{"id": "s", "user": "10"}]))
            (root / "s/events.json").write_text(json.dumps({"w1": [snapshot()], "w2": [snapshot(2000)]}))
            (root / "analytics-events.json").write_text(json.dumps([
                {"session_id": "s", "ts_ms": 3000, "event": "$pageleave"}]))
            result = analyze_sample(root, root / "out")
            self.assertEqual(len(result["sessions"][0]["windows"]), 2)
            self.assertFalse(result["sessions"][0]["analytics"][0]["inside_visual_bounds"])
            self.assertEqual((root / "out/evidence.json").stat().st_mode & 0o777, 0o600)

    def test_private_writer_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            write_private(path, "one")
            with self.assertRaises(FileExistsError):
                write_private(path, "two")
            self.assertEqual(path.read_text(), "one")

    def test_frame_enables_file_access_before_launch_and_sets_viewport_before_mount(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if "screenshot" in command:
                Path(command[-1]).write_bytes(b"test-png")
            return subprocess.CompletedProcess(command, 0, stdout='{"actual_ms": 1000}')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "reproducao.html").write_text("local-player")
            with patch("replay_evidence.subprocess.run", side_effect=run):
                frame(root, 1, "replay-test", root / "frame.png")
            self.assertEqual(calls[0][-4:], ["set", "viewport", "1366", "768"])
            self.assertIn("--allow-file-access", calls[0])
            self.assertIn("open", calls[1])


if __name__ == "__main__":
    unittest.main()
