import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import bundles
import investigate
import lab


class PublicationTests(unittest.TestCase):
    def test_batch_failure_preserves_completed_sibling_and_partial_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lab.write_json(root / 'datasets/demo/manifest.json', {'events_sha256': 'source',
                'start': 1000, 'evidence': [], 'limitations': []})
            jobs = [{'name': 'part-a', 'start': 0, 'duration': 10},
                    {'name': 'part-b', 'start': 10, 'duration': 10}]
            def fail(command, **_):
                items = bundles.read(Path(command[-1]))
                first, partial = [Path(item['output']) for item in items]
                first.mkdir(); partial.mkdir()
                (first / 'clip.mp4').write_bytes(b'complete')
                (partial / 'partial.mp4').write_bytes(b'diagnostic')
                lab.write_json(first / 'export.json', {'status': 'complete', 'dataset': 'demo',
                    'start_s': 0, 'requested_duration_s': 10, 'fps': 3, 'selected_window': None,
                    'events_sha256': 'source', 'renderer_sha256': 'renderer',
                    'video_sha256': bundles.sha(first / 'clip.mp4'), 'frames': [], 'limitations': []})
                raise subprocess.CalledProcessError(1, command)
            with patch.object(lab, 'PRIVATE', root), patch.object(investigate, 'renderer_hash', return_value='renderer'), patch.object(investigate.subprocess, 'run', side_effect=fail):
                with self.assertRaises(subprocess.CalledProcessError):
                    investigate.render_chunks('demo', jobs, 3)
                self.assertEqual(bundles.read(root / 'bundles/part-a/bundle.json')['status'], 'complete')
                self.assertFalse((root / 'bundles/part-b').exists())
                self.assertEqual(len(list((root / 'captures').glob('*/partial.mp4'))), 1)

    def test_batch_cache_rejects_changed_configuration_before_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lab.write_json(root / 'datasets/demo/manifest.json', {'events_sha256': 'source'})
            output = root / 'bundles/part-a'
            output.mkdir(parents=True)
            (output / 'clip.mp4').write_bytes(b'video')
            lab.write_json(output / 'export.json', {'status': 'complete', 'dataset': 'demo',
                'start_s': 0, 'requested_duration_s': 10, 'fps': 3, 'selected_window': None,
                'events_sha256': 'source', 'renderer_sha256': 'renderer',
                'video_sha256': bundles.sha(output / 'clip.mp4')})
            jobs = [{'name': 'part-a', 'start': 0, 'duration': 10}]
            with patch.object(lab, 'PRIVATE', root), patch.object(investigate, 'renderer_hash', return_value='renderer'), patch.object(investigate.subprocess, 'run') as run:
                cached, _ = investigate.render_chunks('demo', jobs, 3)
                self.assertTrue(cached[0]['cache_hit'])
                with self.assertRaises(ValueError):
                    investigate.render_chunks('demo', jobs, 4)
                run.assert_not_called()

    def test_recording_with_206_sources_keeps_the_previous_supported_capacity(self):
        sources = [{'source':'blob_v2', 'blob_key':str(index)} for index in range(206)]
        session = '00000000-0000-0000-0000-000000000001'
        def response(_client, path):
            if path.endswith('?blob_v2=true'):
                return json.dumps({'sources':sources}).encode()
            return b'["w",{"timestamp":1}]\n'
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(name='demo', session=session, project=1, host='https://us.posthog.com')
            with patch.object(lab, 'PRIVATE', Path(directory)), patch.object(lab.download, 'credentials', return_value=('fixture',None)), patch.object(lab.download.Client, 'cli', side_effect=[{'id':1},{'id':session}]), patch.object(lab.download.Client, 'get', autospec=True, side_effect=response), patch.object(lab, 'prepare') as prepare:
                lab.fetch_session(args)
                self.assertEqual(prepare.call_args.args[2]['blocks'], 206)

    def test_failed_or_timed_out_preparation_keeps_published_bundle_accessible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / 'input.jsonl'
            raw.write_text('fixture')
            (root / 'core.cjs').write_text('new parser')
            source = root / 'datasets/demo/manifest.json'
            lab.write_json(source, {'events_sha256':'old-hash'})
            lab.write_json(root / 'catalog.json', [{'name':'demo'}])
            lab.write_json(root / 'bundles/demo/bundle.json', {'name':'demo','dataset':'demo','status':'complete','events_sha256':'old-hash'})
            before = source.read_bytes()
            with patch.object(lab, 'PRIVATE', root):
                with patch.object(lab.subprocess, 'run', return_value=Mock(returncode=1)):
                    with self.assertRaises(ValueError):
                        lab.prepare(raw, 'demo', {})
                self.assertEqual(bundles.bundle(root, 'demo')[1]['events_sha256'], 'old-hash')
                with patch.object(lab.subprocess, 'run', side_effect=subprocess.TimeoutExpired('node',120)):
                    with self.assertRaises(subprocess.TimeoutExpired):
                        lab.prepare(raw, 'demo', {})
                self.assertEqual(bundles.bundle(root, 'demo')[1]['events_sha256'], 'old-hash')
                self.assertEqual(source.read_bytes(), before)

    def test_updated_sources_do_not_replace_dataset_of_a_published_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = '00000000-0000-0000-0000-000000000001'
            args = argparse.Namespace(name='demo',session=session,project=1,host='https://us.posthog.com')
            file = root / 'datasets/demo/manifest.json'
            lab.write_json(file, {'provenance':{'source_fingerprint':'previous'},'input_sha256':'previous'})
            lab.write_json(root / 'bundles/demo/bundle.json', {})
            before = file.read_bytes()
            client = Mock()
            client.cli.side_effect = [{'id':1},{'id':session,'snapshot_source':'web'}]
            client.sources.return_value = [{'source':'blob_v2','blob_key':'0'}]
            client.get.return_value = b'["w",{"timestamp":1}]\n'
            with patch.object(lab, 'PRIVATE', root), patch.object(lab.download, 'credentials', return_value=('fixture',None)), patch.object(lab.download, 'Client', return_value=client), patch.object(lab, 'prepare') as prepare:
                with self.assertRaises(ValueError):
                    lab.fetch_session(args)
                prepare.assert_not_called()
            self.assertEqual(file.read_bytes(), before)

    def test_other_session_or_project_is_refused_before_mutating_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = '00000000-0000-0000-0000-000000000001'
            file = root / 'datasets/demo/manifest.json'
            lab.write_json(file, {'provenance':{'session_id':session,'project_id':1,'host':'https://us.posthog.com'}})
            before = file.read_bytes()
            args = argparse.Namespace(name='demo',session=session,project=1,host='https://us.posthog.com')
            with patch.object(lab, 'PRIVATE', root):
                investigate.guard_dataset(args)
                args.session = '00000000-0000-0000-0000-000000000002'
                with self.assertRaises(ValueError):
                    investigate.guard_dataset(args)
                args.session, args.project = session, 2
                with self.assertRaises(ValueError):
                    investigate.guard_dataset(args)
            self.assertEqual(file.read_bytes(), before)

    def test_failed_capture_can_retry_and_keeps_partial_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'bundles/demo'
            output.mkdir(parents=True)
            (output / 'diagnostic.txt').write_text('partial')
            (output / 'export.json').write_text('{incomplete')
            def failed(command, **_):
                stage = Path(command[-1])
                stage.mkdir()
                (stage / 'partial.mp4').write_bytes(b'partial')
                raise subprocess.CalledProcessError(1, command)
            def completed(command, **_):
                stage = Path(command[-1])
                stage.mkdir()
                (stage / 'clip.mp4').write_bytes(b'encoded')
                lab.write_json(stage / 'export.json', {'status':'complete','video_sha256':bundles.sha(stage / 'clip.mp4')})
            with patch.object(lab, 'PRIVATE', root):
                self.assertIsNone(investigate.cached_export(output))
                with patch.object(investigate.subprocess, 'run', side_effect=failed):
                    with self.assertRaises(subprocess.CalledProcessError):
                        investigate.render_export(output, ['node'])
                self.assertEqual((output / 'diagnostic.txt').read_text(), 'partial')
                with patch.object(investigate.subprocess, 'run', side_effect=completed):
                    investigate.render_export(output, ['node'])
                self.assertEqual(investigate.cached_export(output)['status'], 'complete')
                self.assertEqual(len(list((root / 'incomplete').glob('*/diagnostic.txt'))), 1)
                self.assertEqual(len(list((root / 'captures').glob('*/partial.mp4'))), 1)

    def test_corrupt_published_manifest_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'export.json').write_text('corrupt')
            (output / 'bundle.json').write_text('{}')
            with self.assertRaises(ValueError):
                investigate.cached_export(output)
            self.assertEqual((output / 'export.json').read_text(), 'corrupt')


if __name__ == '__main__':
    unittest.main()
