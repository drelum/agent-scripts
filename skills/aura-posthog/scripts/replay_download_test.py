import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import shutil
from collections import defaultdict
import urllib.request

import replay_download as replay
from replay_evidence import analyze_window

SID = "00000000-0000-4000-8000-000000000001"
HOST = "https://us.posthog.com"
SOURCE = {"source": "blob_v2", "blob_key": "0", "start_timestamp": None, "end_timestamp": None}


class FakeClient:
    host, project = HOST, 331102

    def __init__(self, changed=False, full=True):
        self.changed, self.full, self.source_calls = changed, full, 0

    def cli(self, tool, payload):
        if tool == "project-get":
            return {"id": self.project}
        return {"id": SID, "start_time": "2026-10-08T12:00:00Z", "end_time": "2026-10-08T12:01:00Z", "ongoing": False}

    def sources(self, session):
        self.source_calls += 1
        return [SOURCE] + ([dict(SOURCE, blob_key="1")] if self.changed and self.source_calls == 2 else [])

    def get(self, path):
        return json.dumps(["window", {"type": 2 if self.full else 4, "timestamp": 1000,
                                     "data": {"node": {"id": 1, "tagName": "html"}}}]).encode()


class DownloadTests(unittest.TestCase):
    def test_credentials_do_not_combine_partial_env_with_login(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(replay.DownloadError, "Ambiente incompleto"):
                replay.credentials(HOST, 331102, {"POSTHOG_CLI_API_KEY": "phx_fake"}, Path(root))

    def test_credentials_match_host_and_project(self):
        env = {"POSTHOG_CLI_API_KEY": "phx_fake", "POSTHOG_CLI_PROJECT_ID": "331102"}
        self.assertEqual(replay.credentials(HOST, 331102, env), ("phx_fake", "environment"))
        with self.assertRaises(replay.DownloadError):
            replay.credentials("https://eu.posthog.com", 331102, env)
        with self.assertRaises(replay.DownloadError):
            replay.credentials(HOST, 1, env)

    def test_cli_login_uses_posthog_home(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "credentials.json").write_text(json.dumps({"host": HOST, "env_id": "331102", "token": "phx_fake"}))
            self.assertEqual(replay.credentials(HOST, 331102, {"POSTHOG_HOME": root}), ("phx_fake", "cli-login"))

    def test_external_redirect_never_forwards_token(self):
        request = urllib.request.Request(HOST + "/api/", headers={"Authorization": "Bearer phx_fake"})
        with self.assertRaises(replay.DownloadError):
            replay.SameOriginRedirect().redirect_request(request, None, 302, "", {}, "https://other.example/api/")

    def test_cli_busy_is_not_classified_as_login_failure_or_leaked(self):
        client = replay.Client(HOST, 331102, "phx_fake", 1000, 10, sleep=lambda _: None)
        failed = subprocess.CompletedProcess([], 1, "", "Status Code: 503\nprivate payload phx_fake")
        with patch.object(replay.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(replay.DownloadError, "HTTP 503; PostHog temporariamente ocupado") as caught:
                client.cli("session-recording-get", {"id": SID})
            self.assertNotIn("phx_fake", str(caught.exception))
            self.assertNotIn("private payload", str(caught.exception))

    def test_transient_read_retries_are_bounded_and_access_errors_are_not_retried(self):
        sleeps = []
        client = replay.Client(HOST, 331102, "phx_fake", 1000, 10, sleep=sleeps.append)
        busy = subprocess.CompletedProcess([], 1, '', 'Status Code: 503')
        success = subprocess.CompletedProcess([], 0, '{"id":331102}', '')
        with patch.object(replay.subprocess, 'run', side_effect=[busy, busy, success]) as call:
            self.assertEqual(client.cli('project-get', {})['id'], 331102)
            self.assertEqual(call.call_count, 3)
            self.assertEqual(sleeps, [2, 4])
        denied = subprocess.CompletedProcess([], 1, '', 'Status Code: 403')
        with patch.object(replay.subprocess, 'run', return_value=denied) as call:
            with self.assertRaises(replay.DownloadError) as caught:
                client.cli('project-get', {})
            self.assertEqual(call.call_count, 1)
            self.assertEqual(caught.exception.status, 403)
            self.assertEqual(caught.exception.tool, 'project-get')
        with patch.object(replay.subprocess, 'run', return_value=busy) as call:
            with self.assertRaises(replay.DownloadError):
                client.cli('unknown-or-write-tool', {})
            self.assertEqual(call.call_count, 1)

    def test_sources_follow_pagination_and_reject_other_recording(self):
        client = replay.Client(HOST, 331102, "fake", 1000, 10)
        base = f"/api/environments/331102/session_recordings/{SID}/snapshots"
        pages = [{"sources": [SOURCE], "next": HOST + base + "?cursor=2"},
                 {"sources": [dict(SOURCE, blob_key="1")]}]
        with patch.object(client, "get", side_effect=[json.dumps(p).encode() for p in pages]) as get:
            self.assertEqual(len(client.sources(SID)), 2)
            self.assertEqual(get.call_count, 2)
        with patch.object(client, "get", return_value=json.dumps({"sources": [], "next": "https://other.example/api/"}).encode()):
            with self.assertRaises(replay.DownloadError):
                client.sources(SID)

    def test_unknown_source_and_repeated_cursor_are_failures(self):
        client = replay.Client(HOST, 331102, "fake", 1000, 10)
        with patch.object(client, "get", return_value=b'{"sources":[{"source":"mobile"}]}'):
            with self.assertRaises(replay.DownloadError):
                client.sources(SID)
        base = f"/api/environments/331102/session_recordings/{SID}/snapshots?blob_v2=true"
        with patch.object(client, "get", return_value=json.dumps({"sources": [], "next": base}).encode()):
            with self.assertRaisesRegex(replay.DownloadError, "repetiu"):
                client.sources(SID)

    def test_normalize_gzip_deduplicate_windows_and_redact_input(self):
        windows, seen = defaultdict(list), defaultdict(set)
        stats = dict(raw_events=0, compressed_events=0, duplicates=0, plugin_events_excluded=0)
        event = {"type": 3, "timestamp": 2000, "cv": "gzip", "data": gzip.compress(json.dumps({"source": 5, "text": "private input"}).encode()).decode("latin1")}
        rows = [["one", event], ["one", event], ["two", {"type": 6, "timestamp": 3000, "data": {"body": "secret payload"}}],
                ["two", {"type": 4, "timestamp": 1000, "data": {"href": "https://app.example/login?token=private#fragment"}}]]
        replay.normalize(b"\n".join(json.dumps(x).encode() for x in rows), windows, seen, stats)
        self.assertEqual(stats["duplicates"], 1)
        self.assertEqual(stats["plugin_events_excluded"], 1)
        self.assertEqual(windows["one"][0]["data"]["text"], "[REDACTED]")
        self.assertEqual(windows["two"][0]["data"]["href"], "https://app.example/login")
        self.assertNotIn("private input", json.dumps(windows))
        self.assertNotIn("secret payload", json.dumps(windows))

    def test_unknown_compression_and_oversized_gzip_fail(self):
        with self.assertRaises(replay.DownloadError):
            replay.unpack("unknown")
        with patch.object(replay, "read_bounded", side_effect=replay.DownloadError("too large")):
            with self.assertRaises(replay.DownloadError):
                replay.unpack(gzip.compress(b"{}").decode("latin1"))

    def test_sanitized_dom_and_html_cannot_close_json_script(self):
        node = {"tagName": "input", "attributes": {"value": "private input", "token": "private token"}}
        clean = replay.sanitize(node)
        self.assertEqual(clean["attributes"]["value"], "[REDACTED]")
        self.assertEqual(clean["attributes"]["token"], "[REDACTED]")
        html = replay.player_html({"w": [{"text": "</script><script>evil()</script>"}]}, "library", "css")
        self.assertNotIn("<script>evil()", html)
        self.assertIn("\\u003c/script>", html)

    @unittest.skipUnless(shutil.which("node"), "Node necessário para a regressão de inicialização JS")
    def test_player_initializes_when_window_player_is_the_named_dom_element(self):
        html = replay.player_html({"w": [{"type": 2, "timestamp": 1000, "data": {}}]}, "", "")
        script = html.rsplit("<script>", 1)[1].split("</script>", 1)[0]
        code = '''const vm=require('node:vm');
const elements={events:{textContent:JSON.stringify({w:[{type:2,timestamp:1000,data:{}}]})},
window:{value:null,append(option){this.value??=option.value}},player:{replaceChildren(){}},status:{}};
const context={console:{warn(){}},innerWidth:1366,innerHeight:768,addEventListener(){},
document:{getElementById(id){return elements[id]},createElement(){return {}}},
rrwebPlayer:{Player:class{getReplayer(){return {destroy(){}}}}}};
context.window=context;context.player=elements.player;
vm.runInNewContext(SCRIPT,context);
if(!context.replayReady||typeof context.player.getReplayer!=='function')throw Error('not initialized');
elements.window.onchange();
if(!context.replayReady)throw Error('window switch failed');'''.replace("SCRIPT", json.dumps(script))
        result = subprocess.run(["node", "-e", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_incremental_attribute_mutation_cannot_restore_input_value(self):
        windows, seen = defaultdict(list), defaultdict(set)
        stats = dict(raw_events=0, compressed_events=0, duplicates=0, plugin_events_excluded=0)
        events = [{"type": 2, "timestamp": 1000, "data": {"node": {"id": 1, "tagName": "input", "attributes": {"value": "initial private"}}}},
                  {"type": 3, "timestamp": 2000, "data": {"source": 0, "attributes": [{"id": 1, "attributes": {"value": "later private"}}]}}]
        replay.normalize(b"\n".join(json.dumps(["w", e]).encode() for e in events), windows, seen, stats)
        output = json.dumps(windows) + replay.player_html(windows, "library", "css")
        self.assertNotIn("initial private", output)
        self.assertNotIn("later private", output)
        self.assertEqual(windows["w"][1]["data"]["attributes"][0]["attributes"]["value"], "[REDACTED]")

    def test_visibility_survives_download_without_custom_payload(self):
        windows, seen = defaultdict(list), defaultdict(set)
        stats = dict(raw_events=0, compressed_events=0, duplicates=0, plugin_events_excluded=0)
        events = [{"type": 2, "timestamp": 1000, "data": {"node": {"id": 1}}},
                  {"type": 5, "timestamp": 2000, "data": {"tag": "window hidden", "payload": {"private": "do not retain"}}},
                  {"type": 5, "timestamp": 3000, "data": {"tag": "window visible", "payload": {"private": "do not retain"}}}]
        replay.normalize(b"\n".join(json.dumps(["w", e]).encode() for e in events), windows, seen, stats)
        timeline = analyze_window(windows["w"])["timeline"]
        self.assertEqual([e["state"] for e in timeline], ["window hidden", "window visible"])
        self.assertEqual(windows["w"][-1]["timestamp"], 3000)
        self.assertNotIn("do not retain", json.dumps(windows))

    def test_private_outputs_changed_sources_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            result = replay.download(FakeClient(changed=True), SID, output, lambda: ("library", "css", "hash"))
            self.assertTrue(result["partial"])
            manifest = json.loads((output / SID / "manifest.json").read_text())
            self.assertEqual(manifest["capture_completeness"], "not_proven")
            self.assertFalse(manifest["source_list_stable"])
            self.assertEqual((output / SID / "events.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((output / SID).stat().st_mode & 0o777, 0o700)
            with self.assertRaises(replay.DownloadError):
                replay.download(FakeClient(), SID, output, lambda: ("library", "css", "hash"))

    def test_download_fetches_lots_of_21_blocks(self):
        client = FakeClient()
        client.sources = lambda session: [dict(SOURCE, blob_key=str(i)) for i in range(45)]
        paths = []
        fetch = client.get
        client.get = lambda path: paths.append(path) or fetch(path)
        with tempfile.TemporaryDirectory() as root:
            result = replay.download(client, SID, Path(root), lambda: ("library", "css", "hash"))
            manifest = json.loads(Path(root, SID, "manifest.json").read_text())
        self.assertEqual([p.split("start_blob_key=")[1].split("&decompress")[0] for p in paths],
                         ["0&end_blob_key=20", "21&end_blob_key=41", "42&end_blob_key=44"])
        self.assertEqual((result["blocks"], result["lots"]), (45, 3))
        self.assertEqual([lot["keys"] for lot in manifest["lots"]], [["0", "20"], ["21", "41"], ["42", "44"]])

    def test_missing_full_snapshot_does_not_publish_player(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(replay.DownloadError):
                replay.download(FakeClient(full=False), SID, Path(root), lambda: ("library", "css", "hash"))
            self.assertFalse(Path(root, SID).exists())


if __name__ == "__main__":
    unittest.main()
