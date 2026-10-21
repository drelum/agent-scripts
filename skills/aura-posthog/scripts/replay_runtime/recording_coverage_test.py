import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bundles
import lab
import preparation
import recording_coverage as coverage


def dataset():
    source = {'name': 'demo', 'start': 1000, 'end': 21000, 'duration_s': 20, 'events_sha256': 'source'}
    windows = {'1': [{'type': 4, 'timestamp': 1000}, {'type': 2, 'timestamp': 1009}, {'type': 3, 'timestamp': 6000}],
               '2': [{'type': 4, 'timestamp': 14000}, {'type': 2, 'timestamp': 14020}, {'type': 3, 'timestamp': 21000}]}
    return source, windows


class CoverageTests(unittest.TestCase):
    def test_plan_keeps_idle_and_marks_only_missing_visual_intervals(self):
        source, windows = dataset()
        jobs, gaps = coverage.plan(source, windows, 300)
        self.assertEqual([job['kind'] for job in jobs], ['recording', 'recording_gap', 'recording'])
        self.assertEqual(gaps, [{'kind': 'recording_gap', 'from_ms': 6000, 'to_ms': 14020}])
        self.assertAlmostEqual(sum(job['duration'] for job in jobs), 19.991)
        self.assertEqual(jobs[2]['start'], 13.02)

    def test_overlap_has_no_gap_and_missing_snapshot_remains_failure(self):
        source, windows = dataset()
        windows['2'][1]['timestamp'] = 5900
        windows['2'][0]['timestamp'] = 5800
        self.assertEqual(coverage.plan(source, windows, 300)[1], [])
        windows['2'] = [windows['2'][0]]
        with self.assertRaisesRegex(ValueError, 'sem snapshot completo'):
            coverage.plan(source, windows, 300)

    def test_gap_cannot_hide_recorded_ui_or_a_renderer_failure(self):
        source, windows = dataset()
        with tempfile.TemporaryDirectory() as directory, patch.object(coverage.subprocess, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'lacuna comprovada'):
                coverage.render_gap(source, windows, {'start': 0, 'duration': 2}, 3, Path(directory) / 'stage', 'renderer')
            command.assert_not_called()

    def test_real_gap_encoder_preserves_count_duration_and_no_observed_dom_identity(self):
        source, windows = dataset()
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / 'stage'
            result = coverage.render_gap(source, windows, {'start': 5, 'duration': 2}, 3, stage, 'renderer')
            self.assertEqual(len(result['frames']), 6)
            self.assertEqual(result['encoded_duration_s'], 2)
            self.assertEqual(result['video_sha256'], bundles.sha(stage / 'clip.mp4'))
            self.assertTrue(all(frame['capture_sha256'] is None and frame['visual_state'] == 'missing_recording' and frame['window'] == 'recording-gap' for frame in result['frames']))
            self.assertEqual(result['frames'][-1]['session_ms'], 6000 + 5 * 1000 / 3)
            events = [{'window': 'w1', 'client_ms': 7000}]
            preparation.map_frames(events, result['frames'], {'w1': 1}, 3)
            self.assertIsNone(events[0]['frame_index'])


if __name__ == '__main__':
    unittest.main()
