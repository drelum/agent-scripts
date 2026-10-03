"""Contrato do gerador: CLI simulada, composição e decodificação reais com FFmpeg."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from video_artifacts import signature


SOURCE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg necessário")
class NativeVideoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.skill = self.root / "skill"
        self.skill.mkdir()
        for name in ("aura-novidades-video", "mascara.js", "video-overlay.js", "video_artifacts.py"):
            shutil.copy2(SOURCE / name, self.skill / name)
        self.nov = self.root / "novidades"
        (self.nov / "entradas/roteiros").mkdir(parents=True)
        (self.root / "scripts").mkdir()
        self.executable(self.root / "scripts/beta-api-token.sh", "#!/bin/sh\nprintf 'fixture-token'\n")
        (self.nov / "vinheta.json").write_text(json.dumps({"video": {"largura": 320, "altura": 200}, "som": {"logoSonoro": True}}))
        (self.nov / "entradas/piloto.md").write_text("---\ntitulo: Piloto\ndata: 2026-09-20\narea: mix\n---\n")
        (self.nov / "entradas/roteiros/piloto.sh").write_text(
            "ROTA=/inicio\nENTRADA_TIPO=menu\nENTRADA_DESTINO=Destino\n"
            'roteiro() { passo 1 "Onde encontrar" "Destino"; entrar_destino Destino; '
            'passo 2 "Resultado" "Pronto" "CARD_READY"; sem_passo; }\n'
        )
        self.executable(self.skill / "aura-novidades-vinheta", """#!/bin/bash
set -euo pipefail
mkdir -p "$3"
printf 'render\n' >> "$FIXTURE_ROOT/renders.log"
for kind in abertura encerramento; do
  ffmpeg -v error -y -f lavfi -i color=c=white:s=320x200:r=30 -t 0.2 -c:v libx264 -threads 1 -pix_fmt yuv420p "$3/$kind.mp4"
done
ffmpeg -v error -y -f lavfi -i sine=frequency=500:duration=0.3 -ar 48000 -ac 2 "$3/logo-sonoro.wav"
""")
        self.executable(self.bin / "agent-browser", """#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
a=sys.argv[1:]
if a[:1]==['--allowed-domains']: a=a[2:]
r=pathlib.Path(os.environ['FIXTURE_ROOT'])
with (r/'calls.jsonl').open('a') as f: f.write(json.dumps(a)+'\\n')
mode=os.environ.get('FIXTURE_MODE','ok')
if a==['record','--help']: print('--cursor --contact-sheet'); sys.exit()
if a[:2]==['session','id']: print('fixture-session'); sys.exit()
if a[:2]==['get','url']: print('https://ui.beta.aura.localhost/inicio'); sys.exit()
if a[:2]==['find','role'] and 'click' in a:
    if mode=='action-fail': sys.exit(1)
    (r/'entered').touch()
if a[:1]==['eval']:
    s=sys.stdin.read() if '--stdin' in a else a[1]
    if 'links.length' in s: print('true' if (r/'entered').exists() else 'false')
    elif '__mascara' in s: print(json.dumps({'restos': ['sensitive'] if mode=='mask-fail' else []}))
    else: print('true')
if a[:1]==['wait'] and mode=='prepare-fail': sys.exit(1)
if a[:1]==['wait'] and 'CARD_PENDING' in a: sys.exit(1)
if a[:2]==['record','start']:
    if mode=='start-fail': sys.exit(1)
    (r/'record-path').write_text(a[2])
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x200:r=30','-t','2','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',a[2]],check=True)
if a[:2]==['record','stop'] and mode=='stop-fail': sys.exit(1)
""")

    def executable(self, path, text):
        path.write_text(text)
        path.chmod(0o755)

    def run_video(self, mode="ok", *options):
        env = os.environ | {"PATH": f"{self.bin}:{os.environ['PATH']}", "AURA_BETA_ROOT": str(self.root), "FIXTURE_ROOT": str(self.root), "FIXTURE_MODE": mode, "NOV_VIDEO_CACHE": str(self.root / "cache")}
        return subprocess.run([str(self.skill / "aura-novidades-video"), "piloto", *options], env=env, text=True, capture_output=True, timeout=45)

    def calls(self):
        return [json.loads(s) for s in (self.root / "calls.jsonl").read_text().splitlines()]

    def test_native_capture_composes_valid_media(self):
        result = self.run_video()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        start = next(a for a in calls if a[:2] == ["record", "start"])
        self.assertEqual(start[3:], ["--fps", "30", "--cursor"])
        self.assertLess(calls.index(["record", "stop"]), calls.index(["close"]))
        cards = [i for i, a in enumerate(calls) if a[:1] == ["eval"] and "AuraDemo.passo(" in a[1]]
        hidden = next(i for i, a in enumerate(calls) if a[:1] == ["eval"] and "AuraDemo.esconderPasso(" in a[1])
        self.assertEqual(len(cards), 2)
        self.assertLess(calls.index(["wait", "--fn", "CARD_READY"]), cards[1])
        self.assertLess(cards[1], hidden)
        final = self.nov / "entradas/video/piloto.mp4"
        probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(final)]))
        self.assertEqual({s["codec_name"] for s in probe["streams"]}, {"h264", "aac"})
        self.assertGreater(float(probe["format"]["duration"]), 2)
        self.assertTrue((final.parent / "piloto-capa.png").exists())

    def test_failed_action_stops_recording_and_preserves_destination(self):
        dest = self.nov / "entradas/video/piloto.mp4"
        dest.parent.mkdir()
        dest.write_bytes(b"accepted-video")
        result = self.run_video("action-fail")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(dest.read_bytes(), b"accepted-video")
        self.assertIn(["record", "stop"], self.calls())
        self.assertIn(["close"], self.calls())

    def test_stop_failure_does_not_promote_media(self):
        result = self.run_video("stop-fail")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.nov / "entradas/video/piloto.mp4").exists())
        self.assertIn(["close"], self.calls())
        self.assertEqual(self.calls().count(["record", "stop"]), 1)
        self.assertFalse((self.root / "renders.log").exists())

    def test_mask_failure_prevents_capture(self):
        result = self.run_video("mask-fail")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(a[:2] == ["record", "start"] for a in self.calls()))
        self.assertNotIn("sensitive", result.stderr)

    def capture_directory(self, output):
        return Path(next(line.split(": ", 1)[1] for line in output.splitlines() if line.startswith("artefatos desta execução:")))

    def test_preparation_does_not_record_or_render(self):
        result = self.run_video("ok", "--preparar")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(a[:2] == ["record", "start"] for a in self.calls()))
        self.assertFalse((self.root / "renders.log").exists())
        failed = self.run_video("prepare-fail", "--preparar")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("etapa=preparação", failed.stderr)
        self.assertNotIn("fixture-token", failed.stderr)

    def test_capture_then_compose_reuses_cache_without_browser(self):
        captured = self.run_video("ok", "--capturar")
        self.assertEqual(captured.returncode, 0, captured.stderr)
        directory = self.capture_directory(captured.stdout)
        self.assertFalse((self.root / "renders.log").exists())
        before = self.calls()
        for _ in range(2):
            composed = self.run_video("ok", "--compor", str(directory))
            self.assertEqual(composed.returncode, 0, composed.stderr)
        self.assertEqual(before, self.calls())
        self.assertEqual((self.root / "renders.log").read_text().count("render"), 1)
        self.assertIn("cache validado", composed.stdout)

    def test_modified_capture_is_rejected_before_composition(self):
        captured = self.run_video("ok", "--capturar")
        directory = self.capture_directory(captured.stdout)
        (directory / "demo.mp4").write_bytes(b"corrupt")
        result = self.run_video("ok", "--compor", str(directory))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "renders.log").exists())

    def test_changed_script_invalidates_capture(self):
        captured = self.run_video("ok", "--capturar")
        directory = self.capture_directory(captured.stdout)
        with (self.nov / "entradas/roteiros/piloto.sh").open("a") as f:
            f.write("# roteiro revisado\n")
        result = self.run_video("ok", "--compor", str(directory))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "renders.log").exists())

    def test_corrupted_cache_is_rendered_again(self):
        captured = self.run_video("ok", "--capturar")
        directory = self.capture_directory(captured.stdout)
        first = self.run_video("ok", "--compor", str(directory))
        self.assertEqual(first.returncode, 0, first.stderr)
        cached = next((self.root / "cache").glob("*/manifest.json")).parent
        (cached / "abertura.mp4").write_bytes(b"corrupt")
        second = self.run_video("ok", "--compor", str(directory))
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((self.root / "renders.log").read_text().count("render"), 2)

    def test_preparation_and_capture_execute_same_hook(self):
        with (self.nov / "entradas/roteiros/piloto.sh").open("a") as f:
            f.write('preparar_antes_mascara() { aguardar "destino pronto" "true"; echo hook >> "$raiz/hooks.log"; }\n')
        for option in ("--preparar", "--capturar"):
            result = self.run_video("ok", option)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "hooks.log").read_text().splitlines(), ["hook", "hook"])
        self.assertFalse((self.root / "renders.log").exists())

    def test_card_wait_failure_does_not_render_or_accept_capture(self):
        with (self.nov / "entradas/roteiros/piloto.sh").open("a") as f:
            f.write('roteiro() { entrar_destino Destino; passo 1 "Resultado" "Texto" "CARD_PENDING"; }\n')
        result = self.run_video("ok", "--capturar")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cartão 1: Resultado", result.stderr)
        self.assertEqual(self.calls().count(["record", "stop"]), 1)
        self.assertFalse((self.capture_directory(result.stdout) / "manifest.json").exists())

    def test_vinheta_signature_changes_with_each_input(self):
        (self.nov / "vinheta/assets").mkdir(parents=True)
        asset = self.nov / "vinheta/assets/logo.png"
        asset.write_bytes(b"image")
        model = self.nov / "vinheta/vinheta.html"
        model.write_text("model")
        logo = self.nov / "som/logo.wav"
        logo.parent.mkdir()
        logo.write_bytes(b"audio")
        cfg = self.nov / "vinheta.json"
        config = json.loads(cfg.read_text())
        config["som"]["logo"] = "som/logo.wav"
        cfg.write_text(json.dumps(config))
        previous = signature("vinheta", self.root, self.skill, "piloto")
        for path in (asset, model, logo, cfg, self.nov / "entradas/piloto.md", self.skill / "aura-novidades-vinheta"):
            with path.open("ab") as f:
                f.write(b"\n ")
            current = signature("vinheta", self.root, self.skill, "piloto")
            self.assertNotEqual(previous, current, str(path))
            previous = current


if __name__ == "__main__":
    unittest.main()
