import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import bundles
import lab
import routes


class BundleTests(unittest.TestCase):
    def test_snapshot_batch_decodes_once_and_preserves_each_frame_and_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); folder = self.fixture(root)
            real_run = subprocess.run
            with patch.object(bundles.subprocess, 'run', wraps=real_run) as capture:
                result = bundles.snapshots(root, 'demo', [3, 0, 2, 2])
                self.assertEqual(sum(str(folder / 'clip.mp4') in call.args[0] for call in capture.call_args_list), 1)
                for index in [0, 2, 3]:
                    proof = result[index]
                    self.assertEqual(proof['index'], index)
                    pixels = subprocess.check_output(['ffmpeg', '-v', 'error', '-i',
                        str(folder / 'snapshots' / proof['file']), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
                    self.assertGreater(pixels[0] if index == 0 else pixels[2], 200)
                again = bundles.snapshots(root, 'demo', [2, 3, 0])
                self.assertEqual(again, result)
                self.assertEqual(sum(str(folder / 'clip.mp4') in call.args[0] for call in capture.call_args_list), 1)
            (folder / 'clip.mp4').write_bytes(b'corrupt')
            with self.assertRaises(ValueError): bundles.snapshots(root, 'demo', [0])

    def test_snapshot_batch_refuses_wrong_cached_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); folder = self.fixture(root)
            result = bundles.snapshots(root, 'demo', [2])
            metadata = folder / 'snapshots' / Path(result[2]['file']).with_suffix('.json')
            bad = bundles.read(metadata); bad['index'] = 0; lab.write_json(metadata, bad)
            fixed = bundles.snapshots(root, 'demo', [2])
            self.assertEqual(fixed[2]['index'], 2)

    def test_original_window_is_mapped_to_replayer_window(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'context.json'
            lab.write_json(file, [{'kind':'error','session_id':'s','window':'original','client_ms':1100}])
            row = bundles.context_rows(file, 1000, 's', {'original':2})[0]
            self.assertEqual((row['window'], row['source_window']), ('2','original'))

    def test_ticket_carries_every_frame_and_event_cited_by_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = self.fixture(root)
            file = root / 'findings.json'
            manifest = bundles.read(folder / 'bundle.json')
            manifest['events'].append({'id':'far','session_s':100,'window':'2','kind':'click','summary':'Outra ação'})
            lab.write_json(folder / 'bundle.json', manifest)
            lab.write_json(file,[{'observation':'Mudança visível','frames':[0,3],'events':['far']}])
            bundles.annotate(root, 'demo', file)
            result = bundles.ticket(root, 'demo', 2)
            with zipfile.ZipFile(folder / 'tickets' / result['id'] / 'ticket.zip') as archive:
                for i in (0,3):
                    self.assertIn(f'frame-{i:06}.png', archive.namelist())
                proof = json.loads(archive.read('evidence.json'))
                self.assertIn('far', [e['id'] for e in proof['events']])
            lab.write_json(file,[{'observation':'Inválido','frames':[9]}])
            with self.assertRaises(ValueError):
                bundles.annotate(root, 'demo', file)

    def test_gap_and_other_tab_do_not_acquire_an_image(self):
        frames = [{'index':0,'window':'1','video_s':0,'session_s':2},
                  {'index':1,'window':'2','video_s':0.1,'session_s':20}]
        self.assertIsNone(bundles.locate(frames, 10))
        self.assertIsNone(bundles.locate(frames, 20, '1'))
        self.assertEqual(bundles.locate(frames, 20, '2')['index'], 1)

    def test_correlation_identity_precedes_time_and_clock_domains_stay_separate(self):
        anchor = {'id':'a','request_id':'r','session_id':'s','window':'1','client_ms':10000,'server_ms':50000}
        rows = [anchor, {'id':'exact','request_id':'r','server_ms':80000},
                {'id':'time','window':'1','client_ms':10001}, {'id':'other-tab','window':'2','client_ms':10001},
                {'id':'wrong-clock','server_ms':10000}, {'id':'server','server_ms':50001},
                {'id':'other-session','request_id':'r','session_id':'other'}]
        related = bundles.correlate(anchor, rows)
        self.assertEqual([e['event']['id'] for e in related], ['exact','time','server'])
        self.assertEqual([e['approximate'] for e in related], [False,True,True])

    def test_import_sanitizes_and_rejects_foreign_session_or_missing_client_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'context.json'
            raw = {'kind':'error','session_id':'s','client_ms':1100,'summary':'user@example.com token=private', 'payload':'private','authorization':'private'}
            lab.write_json(file, [raw])
            result = bundles.context_rows(file, 1000, 's')
            self.assertNotIn('private', json.dumps(result))
            self.assertNotIn('user@example.com', json.dumps(result))
            self.assertEqual(result[0]['session_s'], 0.1)
            with self.assertRaises(ValueError):
                bundles.context_rows(file, 1000, 'different')
            del raw['client_ms']
            lab.write_json(file, [raw])
            with self.assertRaises(KeyError):
                bundles.context_rows(file, 1000)

    def fixture(self, root):
        folder = root / 'bundles' / 'demo'
        folder.mkdir(parents=True)
        (root / 'datasets' / 'demo').mkdir(parents=True)
        lab.write_json(root / 'catalog.json', [{'name':'demo'}])
        lab.write_json(root / 'datasets/demo/manifest.json', {'events_sha256':'events'})
        # Dois frames vermelhos, dois azuis: detectar se o frame extraído é de outra posição.
        subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i','color=red:s=64x64:r=2:d=1',
                        '-f','lavfi','-i','color=blue:s=64x64:r=2:d=1','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0',
                        '-c:v','libx264','-pix_fmt','yuv420p',str(folder / 'clip.mp4')], check=True, capture_output=True)
        manifest = {'name':'demo','dataset':'demo','status':'complete','fps':2,'events_sha256':'events',
                    'video_sha256':bundles.sha(folder / 'clip.mp4'),'session_id':None,'limits':['Reconstrução'],
                    'frames':[{'index':i,'video_s':i/2,'session_s':i/2,'session_ms':100000+i*500,'window':'1'} for i in range(4)],
                    'events':[{'id':'e','session_s':1,'window':'1','kind':'click','summary':'Enviar','client_ms':101000}]}
        lab.write_json(folder / 'bundle.json', manifest)
        return folder

    def test_snapshot_decodes_requested_frame_and_cache_preserves_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = self.fixture(root)
            result = bundles.snapshot(root, 'demo', 2)
            image = folder / 'snapshots' / result['file']
            pixels = subprocess.check_output(['ffmpeg','-v','error','-i',str(image),'-f','rawvideo','-pix_fmt','rgb24','-'])
            red, _, blue = pixels[:3]
            self.assertGreater(blue, 200)
            self.assertLess(red, 20)
            mtime = image.stat().st_mtime_ns
            self.assertEqual(bundles.snapshot(root, 'demo', 2), result)
            self.assertEqual(image.stat().st_mtime_ns, mtime)
            (folder / 'clip.mp4').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                bundles.snapshot(root, 'demo', 2)

    def test_ticket_is_self_contained_and_unpublished_bundle_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = self.fixture(root)
            result = bundles.ticket(root, 'demo', 2, 'Falha investigada')
            with zipfile.ZipFile(folder / 'tickets' / result['id'] / 'ticket.zip') as archive:
                self.assertIn('ticket.md', archive.namelist())
                self.assertIn('evidence.json', archive.namelist())
                self.assertEqual(len([n for n in archive.namelist() if n.endswith('.png')]), 3)
                proof = json.loads(archive.read('evidence.json'))
                self.assertEqual(proof['anchor']['index'], 2)
                self.assertEqual(proof['video_sha256'], bundles.sha(folder / 'clip.mp4'))
            lab.write_json(root / 'catalog.json', [])
            with self.assertRaises(ValueError):
                bundles.bundle(root, 'demo')

    def test_video_range_serves_requested_bytes_only(self):
        class Response:
            headers = {'Range':'bytes=2-4'}
            wfile = io.BytesIO()
            output = {}
            def send_response(self, code): self.code = code
            def send_header(self, name, value): self.output[name] = value
            def end_headers(self): pass
            def send_error(self, code): self.code = code
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'video.mp4'
            file.write_bytes(b'0123456789')
            handler = Response()
            routes.file_response(handler, file, 'video/mp4')
            self.assertEqual(handler.code, 206)
            self.assertEqual(handler.wfile.getvalue(), b'234')
            self.assertEqual(handler.output['Content-Range'], 'bytes 2-4/10')


if __name__ == '__main__':
    unittest.main()
