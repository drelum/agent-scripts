import email.message
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

import replay_download as rd
import replay_lab as lab

SID = "00000000-0000-4000-8000-000000000001"
HOST = "https://us.posthog.com"
T0 = 1_791_470_000_000
BLOCK_MS = 10_000


def event(kind, ts, **data):
    if kind == 2:
        data = {"node": {"id": 1, "type": 0, "childNodes": [{"id": 2, "tagName": "html", "type": 2, "childNodes": []}]}}
    elif kind == 4:
        data = {"href": "https://app.example/x", "width": 1366, "height": 768}
    elif not data:
        data = {"source": 1, "positions": [{"x": 1, "y": 1, "id": 2, "timeOffset": 0}]}
    return {"type": kind, "timestamp": ts, "data": data}


class FakeClient:
    host, project = HOST, 331102

    def __init__(self, blocks=61, base_blocks=(0,), window="w1", empty=()):
        self.blocks, self.base_blocks, self.window, self.empty = blocks, set(base_blocks), window, set(empty)
        self.requests, self.paths = 0, []

    def cli(self, tool, payload):
        if tool == "project-get":
            return {"id": self.project}
        return {"id": SID, "start_time": "2026-10-08T14:00:00Z", "end_time": "2026-10-08T15:00:00Z", "ongoing": False}

    def sources(self, session):
        return [{"source": "blob_v2", "blob_key": str(i), "start_timestamp": T0 + i * BLOCK_MS,
                 "end_timestamp": T0 + i * BLOCK_MS + BLOCK_MS - 1} for i in range(self.blocks)]

    def get(self, path):
        self.requests += 1
        self.paths.append(path)
        query = dict(part.split("=") for part in path.split("?")[1].split("&"))
        lines = []
        for i in range(int(query["start_blob_key"]), int(query["end_blob_key"]) + 1):
            start = T0 + i * BLOCK_MS
            if i in self.empty:
                continue
            if i in self.base_blocks:
                lines += [[self.window, event(4, start)], [self.window, event(2, start + 1)]]
            lines += [[self.window, event(3, start + 5_000 + k)] for k in range(2)]
        return "\n".join(json.dumps(line) for line in lines).encode()


def fake_assets():
    return "/* player */", "/* css */", "sha512-fake"


class ReplayLabTests(unittest.TestCase):
    def test_lotes_respect_api_maximum(self):
        self.assertEqual(rd.lotes(0, 44), [(0, 20), (21, 41), (42, 44)])
        self.assertEqual(rd.lotes(5, 5), [(5, 5)])

    def test_parse_at_accepts_utc_sao_paulo_and_epoch_ms(self):
        expected = 1791470627879
        self.assertEqual(lab.parse_at("2026-10-08T14:43:47.879Z"), expected)
        self.assertEqual(lab.parse_at("2026-10-08T11:43:47.879"), expected)
        self.assertEqual(lab.parse_at(str(expected)), expected)
        with self.assertRaisesRegex(rd.DownloadError, "milissegundos"):
            lab.parse_at("1791470627")

    def test_initial_band_ends_at_last_block_starting_until_t_plus_30s(self):
        sources = FakeClient().sources(SID)
        at = T0 + 40 * BLOCK_MS
        self.assertEqual(lab.banda_inicial(sources, at, at + 30_000), (23, 43))
        with self.assertRaisesRegex(rd.DownloadError, "anterior"):
            lab.banda_inicial(sources, T0 - 60_000, T0 - 30_000)

    def test_band_steps_back_one_lot_at_a_time_until_full_snapshot(self):
        client = FakeClient(blocks=61, base_blocks=(0,))
        with tempfile.TemporaryDirectory() as root:
            *_, fetched, janela, _ = lab.coletar(client, SID, T0 + 58 * BLOCK_MS, lab.Modo.BANDA, None, Path(root),
                                                 T0 + 58 * BLOCK_MS + 30_000)
        self.assertEqual([f["indices"] for f in fetched], [[40, 60], [19, 39], [0, 18]])
        self.assertEqual((client.requests, janela), (3, "w1"))

    def test_band_stops_when_first_lot_has_base_before_requested_start(self):
        client = FakeClient(blocks=61, base_blocks=(0, 50))
        at = T0 + 58 * BLOCK_MS
        with tempfile.TemporaryDirectory() as root:
            lab.coletar(client, SID, at, lab.Modo.BANDA, None, Path(root), de_ms=at - 60_000)
        self.assertEqual(client.requests, 1)

    def test_band_steps_back_until_requested_window_appears(self):
        client = FakeClient(blocks=61, base_blocks=(0, 50))
        get = client.get
        client.get = lambda path: get(path).replace(b'"w1"', b'"antes"') if "start_blob_key=0&" in path else get(path)
        with tempfile.TemporaryDirectory() as root:
            *_, janela, criterio = lab.coletar(client, SID, T0 + 58 * BLOCK_MS, lab.Modo.BANDA, "antes", Path(root),
                                               T0 + 58 * BLOCK_MS + 30_000)
        self.assertEqual((janela, criterio, client.requests), ("antes", "informada", 3))

    def test_band_steps_back_until_base_before_requested_start(self):
        client = FakeClient(blocks=61, base_blocks=(0, 50))
        at = T0 + 58 * BLOCK_MS
        with tempfile.TemporaryDirectory() as root:
            *_, fetched, _, _ = lab.coletar(client, SID, at, lab.Modo.BANDA, None, Path(root), at + 30_000,
                                            de_ms=at - 300_000)
        self.assertEqual([f["indices"] for f in fetched], [[40, 60], [19, 39], [0, 18]])

    def test_band_steps_back_past_lots_without_visual_events(self):
        client = FakeClient(blocks=61, base_blocks=(0,), empty=range(40, 61))
        with tempfile.TemporaryDirectory() as root:
            *_, janela, _ = lab.coletar(client, SID, T0 + 58 * BLOCK_MS, lab.Modo.BANDA, None, Path(root),
                                        T0 + 58 * BLOCK_MS + 30_000)
        self.assertEqual((janela, client.requests), ("w1", 3))

    def test_band_fails_explicitly_without_full_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(rd.DownloadError, "sem snapshot completo"):
                lab.coletar(FakeClient(base_blocks=()), SID, T0 + 58 * BLOCK_MS, lab.Modo.BANDA, None, Path(root))

    def test_whole_session_uses_lots_and_cache_avoids_new_requests(self):
        with tempfile.TemporaryDirectory() as root:
            first = FakeClient(blocks=45)
            lab.coletar(first, SID, T0 + 30 * BLOCK_MS, lab.Modo.INTEIRA, None, Path(root))
            again = FakeClient(blocks=45)
            *_, fetched, _, _ = lab.coletar(again, SID, T0 + 30 * BLOCK_MS, lab.Modo.INTEIRA, None, Path(root))
            modes = {stat.S_IMODE(p.stat().st_mode) for p in Path(root).iterdir()}
        self.assertEqual((first.requests, again.requests), (3, 0))
        self.assertTrue(all(f["cache"] for f in fetched))
        self.assertEqual(modes, {0o600})

    def test_unicode_line_separator_inside_text_does_not_split_rows(self):
        client = FakeClient(blocks=1)
        body = client.get("/x?start_blob_key=0&end_blob_key=0")
        row = json.dumps(["w1", event(3, T0 + 9_000, source=0, texts=[{"id": 2, "value": "a\u2028b\x85c"}])],
                         ensure_ascii=False).encode()
        client.get = lambda path: body + b"\n" + row
        with tempfile.TemporaryDirectory() as root:
            _, windows, *_ = lab.coletar(client, SID, T0 + 9_000, lab.Modo.INTEIRA, None, Path(root))
        self.assertEqual(windows["w1"][-1]["data"]["texts"][0]["value"], "a\u2028b\x85c")

    def test_window_choice_uses_nearest_event_or_requested_id(self):
        windows = {"a": [event(3, 1_000)], "b": [event(3, 9_000)]}
        self.assertEqual(lab.escolher_janela(windows, 8_000), ("b", "evento gravado mais próximo do erro"))
        self.assertEqual(lab.escolher_janela(windows, 8_000, "a"), ("a", "informada"))
        with self.assertRaisesRegex(rd.DownloadError, "não aparece"):
            lab.escolher_janela(windows, 8_000, "c")

    def test_cut_starts_at_meta_before_full_snapshot_preceding_interval(self):
        events = [event(3, 1), event(4, 2), event(2, 3), event(3, 4), event(4, 10), event(2, 11), event(3, 15),
                  event(3, 30)]
        cut, dropped = lab.recortar(events, 12, 20)
        self.assertEqual(([e["timestamp"] for e in cut], dropped), ([10, 11, 15], 4))
        cut, _ = lab.recortar(events, 0, 20)  # nenhum snapshot completo antes de `de`: usa o primeiro
        self.assertEqual(cut[0]["timestamp"], 2)
        self.assertEqual(lab.recortar([event(3, 1)], 0, 5), (None, 1))
        self.assertEqual(lab.recortar(events, 0, 2)[0], None)

    def test_coverage_flags_error_inside_recording_gap(self):
        at = 1_000_000
        gap = [event(4, at - 200_000), event(2, at - 199_000), event(3, at - 136_000), event(3, at + 144_000)]
        self.assertTrue(lab.cobertura(gap, at)["sem_gravacao_no_erro"])
        self.assertEqual(lab.lacunas(gap, at)[-1], {"de_s": -136.0, "ate_s": 144.0})
        covered = [event(4, at - 10_000), event(2, at - 9_000), event(3, at - 900), event(3, at + 500)]
        self.assertEqual(lab.cobertura(covered, at), {"ultimo_evento_antes_s": -0.9, "primeiro_evento_depois_s": 0.5,
                                                      "sem_gravacao_no_erro": False})

    def test_client_waits_between_requests_and_enforces_deadline(self):
        now, slept = [100.0], []
        client = rd.Client(HOST, 331102, "phx_fake", 1 << 20, 10, sleep=slept.append, clock=lambda: now[0])
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"{}"
        with patch.object(client.opener, "open", return_value=response):
            client.get("/a")
            now[0] += 1.5
            client.get("/b")
            now[0] += rd.PRAZO_S
            with self.assertRaisesRegex(rd.DownloadError, "excedeu"):
                client.get("/c")
            client.nova_sessao()
            client.get("/d")
        self.assertEqual((client.requests, slept[0]), (3, rd.RITMO_S - 1.5))

    def test_rate_limit_reports_retry_after(self):
        headers = email.message.Message()
        headers["Retry-After"] = "2962"
        error = urllib.error.HTTPError(HOST + "/x", 429, "Too Many", headers, io.BytesIO(b""))
        client = rd.Client(HOST, 331102, "phx_fake", 1 << 20, 10)
        with patch.object(client.opener, "open", side_effect=error):
            with self.assertRaisesRegex(rd.DownloadError, "Retry-After: 2962 s"):
                client.get("/x")

    def test_prepare_writes_private_lab_relative_to_error(self):
        client = FakeClient(blocks=30, base_blocks=(0,), empty=range(14, 30))
        at = T0 + 20 * BLOCK_MS
        with tempfile.TemporaryDirectory() as root:
            result = lab.preparar(client, SID, at, Path(root), lab.Modo.INTEIRA, assets=fake_assets)
            folder = Path(result["lab"]).parent
            html = Path(result["lab"]).read_text()
            manifest = json.loads(Path(result["lab"]).with_suffix(".json").read_text())
            modes = {p.name: stat.S_IMODE(p.stat().st_mode) for p in folder.iterdir()}
            cache_mode = stat.S_IMODE((folder.parent / ".lotes").stat().st_mode)
            again = lab.preparar(FakeClient(), SID, at, Path(root), assets=fake_assets)
            with self.assertRaisesRegex(rd.DownloadError, "outra janela"):
                lab.preparar(FakeClient(), SID, at, Path(root), wanted="w1", assets=fake_assets)
        self.assertEqual(Path(result["lab"]).name, "lab_T-300_T+120.html")
        self.assertIn('id="lab-meta"', html)
        self.assertIn("window.lab", html)
        self.assertTrue(manifest["cobertura_erro"]["sem_gravacao_no_erro"])
        self.assertEqual(manifest["requisicoes_snapshots"], 2)
        self.assertEqual(manifest["janelas"]["w1"]["inicio_s"], -200.0)
        self.assertEqual((again["reutilizado"], again["requisicoes_snapshots"]), (True, 0))
        self.assertEqual(modes, {"lab_T-300_T+120.json": 0o600, "lab_T-300_T+120.html": 0o600, "LEIA-ME.md": 0o600})
        self.assertEqual(cache_mode, 0o700)

    def test_errors_in_same_second_get_distinct_labs(self):
        at = T0 + 20 * BLOCK_MS
        with tempfile.TemporaryDirectory() as root:
            first = lab.preparar(FakeClient(blocks=30), SID, at, Path(root), assets=fake_assets)
            second = lab.preparar(FakeClient(blocks=30), SID, at + 999, Path(root), assets=fake_assets)
        self.assertNotEqual(first["lab"], second["lab"])
        self.assertFalse(second["reutilizado"])

    def test_other_error_in_same_session_reuses_cache(self):
        with tempfile.TemporaryDirectory() as root:
            first = FakeClient(blocks=45, base_blocks=(0, 30))
            lab.preparar(first, SID, T0 + 40 * BLOCK_MS, Path(root), assets=fake_assets)
            second = FakeClient(blocks=45, base_blocks=(0, 30))
            result = lab.preparar(second, SID, T0 + 42 * BLOCK_MS, Path(root), assets=fake_assets)
        self.assertEqual((first.requests, second.requests), (3, 0))
        self.assertEqual(Path(result["lab"]).parent.parent.name, SID)

    def test_new_interval_reuses_cache_without_requests(self):
        at = T0 + 40 * BLOCK_MS
        with tempfile.TemporaryDirectory() as root:
            first = FakeClient(blocks=45, base_blocks=(0, 30))
            lab.preparar(first, SID, at, Path(root), assets=fake_assets)
            second = FakeClient(blocks=45, base_blocks=(0, 30))
            result = lab.preparar(second, SID, at, Path(root), de_s=-60, ate_s=10, assets=fake_assets)
            manifest = json.loads(Path(result["lab"]).with_suffix(".json").read_text())
            leia = Path(result["leia_me"]).read_text()
        self.assertEqual((first.requests, second.requests), (3, 0))
        self.assertIn(Path(result["lab"]).as_uri(), leia)
        self.assertEqual(manifest["janelas"]["w1"]["inicio_s"], -100.0)  # snapshot do bloco 30, antes de T-60
        self.assertLessEqual(manifest["janelas"]["w1"]["fim_s"], 10)

    def test_windows_outside_interval_are_listed_not_loaded(self):
        windows = {"erro": [event(4, 0), event(2, 1), event(3, 50_000)],
                   "depois": [event(4, 400_000), event(2, 400_001), event(3, 410_000)]}
        trimmed, info, _, sessao = lab.montar(windows, 60_000, "erro", -240_000, 180_000)
        self.assertEqual(list(trimmed), ["erro"])
        self.assertEqual(sessao["depois"]["no_laboratorio"], False)
        self.assertEqual(sessao["depois"]["inicio_s"], 340.0)

    def test_invalid_interval_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(rd.DownloadError, "Intervalo inválido"):
                lab.preparar(FakeClient(), SID, T0, Path(root), de_s=10, ate_s=-10, assets=fake_assets)

    def test_embedded_json_cannot_close_script(self):
        windows = {"w": [{"type": 3, "timestamp": 1, "data": {"text": "</script><script>alert(1)</script>"}}]}
        html = lab.lab_html(windows, {"x": "</script>"}, "", "", "")
        self.assertNotIn("</script><script>alert", html)


if __name__ == "__main__":
    unittest.main()
