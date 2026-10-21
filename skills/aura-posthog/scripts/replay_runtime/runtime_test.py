from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import investigate
import lab
import runtime


class RuntimeTests(unittest.TestCase):
    def test_wrapper_runs_from_a_relocated_skill_without_experiments(self):
        import shutil
        skill = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'skill com espaço'
            shutil.copytree(skill, target, ignore=shutil.ignore_patterns('node_modules', 'private', '__pycache__'))
            result = subprocess.run([str(target / 'scripts/replay_investigate'), '--help'],
                                    cwd=folder, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = subprocess.run([str(target / 'scripts/replay_investigate'), 'doctor'],
                                    cwd=folder, capture_output=True, text=True,
                                    env={'PATH':'/usr/bin:/bin'})
            self.assertEqual(report.returncode, 1)
            self.assertFalse(json.loads(report.stdout)['ready'])

    def test_doctor_rejects_a_corrupt_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            private = root / 'private'
            private.mkdir()
            hashes = {}
            for name in ('core.cjs', 'headless.js', 'investigator.js'):
                (private / name).write_bytes(b'valid')
                hashes[name] = lab.digest(b'valid')
            lab.write_json(private / 'build.json', {'hashes':hashes})
            (root / 'node_modules/esbuild').mkdir(parents=True)
            (root / 'node_modules/esbuild/package.json').write_text('{}')
            with patch.object(runtime, 'ROOT', root), patch.object(runtime, 'prerequisites', return_value={'tools':True}), patch.object(runtime, 'analysis_ready', return_value=True), patch.object(runtime, 'capture_preflight', return_value=True):
                self.assertTrue(runtime.doctor()['ready'])
                (private / 'headless.js').write_bytes(b'corrupt')
                self.assertFalse(runtime.doctor()['ready'])

    def test_preflight_rejects_version_only_chrome_before_collection(self):
        with patch.object(runtime.subprocess, 'run', return_value=type('Result', (), {'returncode': 1, 'stdout': '{"ready":false}'})()):
            self.assertFalse(runtime.capture_preflight())
            with self.assertRaisesRegex(ValueError, 'chrome-headless-shell'):
                runtime.require_capture()

    def test_changed_local_input_is_refused_before_preparation(self):
        import argparse
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = root / 'raw.jsonl'
            raw.write_bytes(b'new')
            lab.write_json(root / 'datasets/demo/manifest.json', {'input_sha256':lab.digest(b'old')})
            args = argparse.Namespace(name='demo', input=raw, session=None)
            with patch.object(lab, 'PRIVATE', root):
                with self.assertRaises(ValueError):
                    investigate.guard_dataset(args)


if __name__ == '__main__':
    unittest.main()
