import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import lab


class CacheTests(unittest.TestCase):
    def test_preparation_cache_reuses_valid_input_and_invalidates_changed_parser(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            private = root / 'private'
            private.mkdir()
            (private / 'core.cjs').write_text('parser')
            raw = root / 'raw.jsonl'
            raw.write_text('fixture')
            target = private / 'datasets/demo'
            target.mkdir(parents=True)
            lab.write_json(private / 'catalog.json', [{'name':'demo'}])
            events = target / 'events.json'
            events.write_text('{}')
            parser_hash = lab.digest(b''.join(p.read_bytes() for p in (Path(lab.__file__), lab.ROOT / 'replay_context.py', private / 'core.cjs', Path(lab.download.__file__), lab.ROOT.parent / 'replay_evidence.py')))
            lab.write_json(target / 'manifest.json', {'events_sha256':lab.digest(events.read_bytes()), 'input_sha256':lab.digest(raw.read_bytes()),'parser_sha256':parser_hash,'duration_s':2})
            original_manifest = (target / 'manifest.json').read_bytes()
            with patch.object(lab, 'PRIVATE', private), patch.object(lab.subprocess, 'run') as run:
                result = lab.prepare(raw, 'demo', {'kind':'fixture'})
                self.assertTrue(result['prepare_cache_hit'])
                run.assert_not_called()
                self.assertEqual((target / 'manifest.json').read_bytes(), original_manifest)
                (private / 'core.cjs').write_text('changed')
                run.return_value.returncode = 1
                with self.assertRaises(ValueError):
                    lab.prepare(raw, 'demo', {})
                self.assertTrue(lab.published(private, 'demo'))
                self.assertEqual(events.read_text(), '{}')

    def test_invalidated_dataset_not_accessible_even_if_old_files_remain(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / 'datasets' / 'old' / 'events.json'
            old.parent.mkdir(parents=True)
            old.write_text('{}')
            lab.write_json(root / 'catalog.json', [{'name':'old'}, {'name':'other'}])
            self.assertTrue(lab.published(root, 'old'))
            lab.write_json(root / 'catalog.json', [{'name':'other'}])
            self.assertTrue(old.exists())
            self.assertFalse(lab.published(root, 'old'))
            self.assertTrue(lab.published(root, 'other'))

    def test_tail_metadata_invalidates_same_blob_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = {'source': 'blob_v2', 'blob_key': '0', 'end_timestamp': 'a'}
            fetch = Mock(return_value=b'["w",{"timestamp":1}]\n')
            self.assertFalse(lab.cached_block(root, source, fetch)[1])
            self.assertTrue(lab.cached_block(root, source, fetch)[1])
            source['end_timestamp'] = 'b'
            self.assertFalse(lab.cached_block(root, source, fetch)[1])
            self.assertEqual(fetch.call_count, 2)

    def test_corrupt_disk_and_forced_tail_revalidate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = {'blob_key': '0'}
            fetch = Mock(return_value=b'["w",{"timestamp":1}]\n')
            lab.cached_block(root, source, fetch)
            (root / '0.jsonl').write_bytes(b'corrupt')
            self.assertFalse(lab.cached_block(root, source, fetch)[1])
            self.assertFalse(lab.cached_block(root, source, fetch, force=True)[1])
            self.assertEqual(fetch.call_count, 3)

    def test_invalid_response_does_not_publish_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for body in (b'', b'<html>error</html>', b'42'):
                with self.assertRaises(ValueError):
                    lab.cached_block(root, {'blob_key': '0'}, lambda: body)
            self.assertFalse((root / '0.cache.json').exists())

    def test_atomic_files_private_and_name_traversal_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.json'
            lab.write_json(path, {'ok': True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), {'ok': True})
        for name in ('../../cache', 'x/y', '', 'A B'):
            with self.assertRaises(ValueError):
                lab.valid_name(name)

    def test_sanitization_hides_input_and_credentials(self):
        event = {'authorization':'Bearer secret', 'url':'https://x.test/login?token=private', 'data':{'source':5,'text':'secret'}}
        result = lab.download.sanitize(event)
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn('Bearer secret', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
