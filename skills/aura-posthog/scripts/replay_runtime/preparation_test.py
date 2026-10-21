import argparse
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import bundles
import lab
import investigate
import preparation
import session_context

SESSION = '00000000-0000-0000-0000-000000000001'


def closed(ident=SESSION):
    return {'id': ident, 'ongoing': False, 'start_time': '2026-10-11T17:00:00+00:00',
            'end_time': '2026-10-11T17:00:20+00:00'}


class PreparationTests(unittest.TestCase):
    def test_long_batch_prefix_rejected_before_auth_or_queries(self):
        args = argparse.Namespace(fps=3, latest=1, name='investigacao-checkout-outubro')
        with patch.object(lab.download, 'credentials') as auth:
            with self.assertRaisesRegex(ValueError, '24 caracteres'):
                preparation.run(args)
            auth.assert_not_called()

    def test_video_failure_keeps_collected_context_without_publishing_ready_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lab.write_json(root / 'datasets/demo/manifest.json', {'start': 1000, 'end': 3000, 'duration_s': 2,
                'provenance': {'session_id': SESSION, 'project_id': 1, 'host': 'https://us.posthog.com'}})
            lab.write_json(root / 'datasets/demo/events.json', {})
            args = argparse.Namespace(fps=3, host='https://us.posthog.com', project=1, date_from='-3d')
            with patch.object(lab, 'PRIVATE', root), patch.object(preparation, 'config', return_value={}), patch.object(preparation, 'select', return_value=([closed()], {})), patch.object(lab, 'fetch_session') as fetch, patch.object(preparation.context, 'collect_events', return_value=([{'id': 'e1'}], {'status': 'exhausted'})) as collect, patch.object(preparation.context, 'collect_logs', return_value=([], {'status': 'exhausted'})), patch.object(preparation.context, 'collect_spans', return_value=([], {'status': 'exhausted'})), patch.object(preparation, 'video', side_effect=ValueError('lacuna')):
                with self.assertRaises(ValueError): preparation.prepare_one(args, Mock(), closed(), {}, 'demo')
                with self.assertRaises(ValueError): preparation.prepare_one(args, Mock(), closed(), {}, 'demo')
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(collect.call_count, 1)
            pending = list((root / 'packages-staging').glob('*/context-pending.json'))
            self.assertEqual(len(pending), 1)
            self.assertEqual(bundles.read(pending[0])['events'][0]['id'], 'e1')
            self.assertEqual(bundles.read(pending[0])['status'], 'context_ready_video_pending')
            self.assertFalse((root / 'bundles/demo/package.json').exists())

    def test_selection_skips_open_and_unknown_then_paginates(self):
        client = Mock()
        client.cli.side_effect = [
            {'results': [{'id': 'open', 'ongoing': True}, {'id': 'unknown'}], 'next_cursor': 'p2'},
            {'results': [closed()]},
        ]
        rows, coverage = preparation.select(client, 1, '-3d')
        self.assertEqual(rows[0]['id'], SESSION)
        self.assertEqual(coverage['skipped_open_or_unknown'], 2)
        self.assertEqual(client.cli.call_args.args[1]['after'], 'p2')

    def test_open_session_is_rejected_before_download(self):
        client = Mock()
        client.cli.return_value = {'results': [{**closed(), 'ongoing': True}]}
        with patch.object(lab, 'fetch_session') as download:
            with self.assertRaises(ValueError):
                preparation.select(client, 1, '-3d', SESSION)
            download.assert_not_called()

    def test_pagination_keeps_equal_timestamps_with_distinct_ids(self):
        client = Mock()
        client.cli.side_effect = [{'results': 'id|ms\na|10\nb|10'}, {'results': 'id|ms\nc|10'},]
        with patch.object(session_context, 'PAGE', 2):
            rows = session_context.paginate(client, 'id,ms FROM events', 'valid', 'ms,id',
                                           lambda previous: f"id > '{previous.split('|')[0]}'")
        self.assertEqual(rows, ['a|10', 'b|10', 'c|10'])
        self.assertIn("id > 'b'", client.cli.call_args.args[1]['query'])

    def test_pagination_refuses_silent_page_repetition(self):
        client = Mock()
        client.cli.return_value = {'results': 'id\na'}
        with patch.object(session_context, 'PAGE', 1), patch.object(session_context, 'MAX_PAGES', 3):
            with self.assertRaises(ValueError):
                session_context.paginate(client, 'id FROM events', 'valid', 'id', lambda _: 'valid')

    def test_event_count_change_never_becomes_complete_context(self):
        client = Mock()
        client.cli.side_effect = [{'results': 'count\n1'}, {'results': 'id|event|ms|properties'}, {'results': 'count\n2'}]
        with self.assertRaises(ValueError):
            session_context.collect_events(client, closed(), {'start': 1})

    def test_diagnostic_context_preserves_error_but_excludes_values(self):
        props = {'$session_id': SESSION, '$time': 1.0, '$window_id': 'w', 'http_status': 500,
                 'password': 'SECRET', 'search_text': 'PRIVATE INPUT',
                 '$exception_list': [{'type': 'HttpError', 'value': 'token=SECRET HTTP 500',
                                      'stacktrace': {'frames': [{'function': 'request', 'lineno': 7, 'vars': {'password': 'SECRET'}}]}}]}
        client = Mock()
        client.cli.side_effect = [{'results': 'count\n1'},
            {'results': 'id|event|ms|props\ne1|$exception|1000|' + json.dumps(props)}, {'results': 'count\n1'}]
        rows, coverage = session_context.collect_events(client, closed(), {'start': 1000})
        encoded = json.dumps(rows)
        self.assertNotIn('SECRET', encoded)
        self.assertNotIn('PRIVATE INPUT', encoded)
        self.assertEqual(rows[0]['category'], 'exception')
        self.assertEqual(rows[0]['properties']['http_status'], 500)
        self.assertEqual(rows[0]['exceptions'][0]['frames'][0]['lineno'], 7)
        self.assertEqual(coverage['status'], 'exhausted')

    def test_logs_camel_case_cursor_and_zero_trace_are_supported(self):
        entry = {'uuid': 'l1', 'timestamp': '2026-10-11T17:00:01Z', 'severity_text': 'error',
                 'attributes': {'sessionId': SESSION}, 'trace_id': '0' * 32}
        client = Mock()
        client.cli.side_effect = [{'count': 2}, {'results': [entry], 'nextCursor': 'p2'},
                                 {'results': [{**entry, 'uuid': 'l2'}]}, {'count': 2}]
        rows, _ = session_context.collect_logs(client, closed(), [], {'logs_available': True, 'service': 'aura'})
        self.assertEqual(client.cli.call_args_list[2].args[1]['query']['after'], 'p2')
        self.assertIsNone(rows[0]['trace_id'])

    def test_full_trace_expansion_keeps_child_without_session_attribute(self):
        trace = 'a' * 32
        row = f's1|{trace}|{"b" * 16}|{"0" * 16}|HTTP|1000|100|0|aura|{{"sessionId":"{SESSION}"}}'
        child = f's2|{trace}|{"c" * 16}|{"b" * 16}|DB|1001|50|0|database|{{}}'
        client = Mock()
        client.cli.side_effect = [{'results': 'columns\n' + row}, {'results': 'columns\n' + row + '\n' + child}]
        rows, coverage = session_context.collect_spans(client, closed(), [], {'spans_available': True})
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['correlation'], 'confirmed_trace_child')
        self.assertEqual(coverage['traces'], 1)
        self.assertNotIn('service_name =', client.cli.call_args.args[1]['query'])
        self.assertIn("trace_id IN ('" + trace + "')", client.cli.call_args.args[1]['query'])

    def test_base64_trace_ids_normalize_to_w3c_and_zero_ids_stay_unset(self):
        value = base64.b64encode(bytes.fromhex('58d24c2b048beac6cc4bf4bfb7a2f830')).decode()
        self.assertEqual(session_context.identifier(value, 32), '58d24c2b048beac6cc4bf4bfb7a2f830')
        self.assertIsNone(session_context.identifier('AAAAAAAAAAA=', 16))
        self.assertIsNone(session_context.identifier("invalid'ID", 32))

    def test_structured_log_bodies_exclude_payload_headers_and_credentials(self):
        body = json.dumps({'message': 'HTTP 500', 'password': 'SECRET', 'headers': {'Authorization': 'Bearer ABC'},
                           'payload': {'search_text': 'PRIVATE INPUT'}, 'exception': {'type': 'HttpError', 'message': 'Failed'}})
        result = session_context.diagnostic_text(body)
        for private in ('SECRET', 'ABC', 'PRIVATE INPUT', 'password', 'headers', 'payload'):
            self.assertNotIn(private, result)
        self.assertIn('HTTP 500', result)
        self.assertIn('HttpError', result)
        self.assertNotIn('ABC', session_context.diagnostic_text('Authorization: Bearer ABC'))
        for authorization in ('Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==', 'Digest username="SECRET", nonce="ABC"'):
            result = session_context.diagnostic_text(json.dumps({'message': 'Authorization: ' + authorization}))
            for private in ('QWxhZGRpbjpvcGVuIHNlc2FtZQ==', 'SECRET', 'ABC'):
                self.assertNotIn(private, result)
        self.assertNotIn('two words', session_context.diagnostic_text('password="two words"'))
        self.assertNotIn('SECRET', session_context.diagnostic_text('Error {"password":"SECRET"}'))

    def test_changed_context_preserves_published_annotations_and_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'bundles/demo'
            folder.mkdir(parents=True)
            (folder / 'clip.mp4').write_bytes(b'video fixture')
            lab.write_json(root / 'datasets/demo/manifest.json', {'events_sha256': 'events',
                'start': 1000, 'provenance': {'session_id': SESSION}, 'evidence': [], 'limitations': []})
            lab.write_json(folder / 'export.json', {'status': 'complete', 'events_sha256': 'events',
                'video_sha256': bundles.sha(folder / 'clip.mp4'), 'frames': [], 'limitations': []})
            path = root / 'context.json'
            row = {'kind': 'analytics', 'session_id': SESSION, 'client_ms': 1100, 'summary': 'Original'}
            lab.write_json(path, [row])
            bundles.publish(root, 'demo', 'demo', folder, path)
            manifest = bundles.read(folder / 'bundle.json')
            manifest['findings'] = [{'observation': 'Evidência já revisada'}]
            lab.write_json(folder / 'bundle.json', manifest)
            before = (folder / 'bundle.json').read_bytes()
            lab.write_json(path, [{**row, 'summary': 'Contexto novo'}])
            with self.assertRaises(ValueError):
                bundles.publish(root, 'demo', 'demo', folder, path)
            self.assertEqual((folder / 'bundle.json').read_bytes(), before)

    def test_missing_window_and_before_snapshot_events_remain_unmapped(self):
        frames = [{'index': 0, 'window': '1', 'session_ms': 1009}, {'index': 1, 'window': '1', 'session_ms': 1342}]
        events = [{'client_ms': 1000, 'window': 'w'}, {'client_ms': 1100, 'window': None},
                  {'client_ms': 1100, 'window': 'w'}]
        preparation.map_frames(events, frames, {'w': 1}, 3)
        self.assertEqual([e['frame_index'] for e in events], [None, None, 0])

    def test_cached_package_hashes_checked_before_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'context.json').write_text('original')
            manifest = {'events_sha256': 'hash', 'video_sha256': 'video', 'frames': [], 'events': []}
            lab.write_json(folder / 'package.json', {'status': 'ready', 'config': {}, 'name': 'demo',
                'events_sha256': 'hash', 'bundle_evidence_sha256': preparation.evidence_hash(manifest),
                'files': {'context.json': {'sha256': bundles.sha(folder / 'context.json')}}})
            with patch.object(bundles, 'bundle', return_value=(folder, manifest)):
                preparation.verify(folder, {})
                manifest['findings'] = [{'observation': 'Análise posterior'}]
                preparation.verify(folder, {})
                (folder / 'context.json').write_text('corrupted')
                with self.assertRaises(ValueError):
                    preparation.verify(folder, {})

    def test_schema_markdown_contract_is_supported_without_data_fallback(self):
        client = Mock(token='fixture', project=1, host='https://us.posthog.com')
        with patch.object(session_context.subprocess, 'run', return_value=Mock(stdout=json.dumps('events:\n- `$pageview`'))):
            value = session_context.read_schema(client, {'kind': 'events'})
        self.assertIn('$pageview', value)
        client.cli.assert_not_called()

    def test_integral_video_keeps_inactivity_and_joins_continuous_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / 'packages-staging/demo'
            stage.mkdir(parents=True)
            lab.write_json(root / 'datasets/demo/events.json', {'1': [{'type': 2, 'timestamp': 1009}, {'type': 3, 'timestamp': 303250}]})
            captured = []
            def render(dataset, jobs, fps):
                captured.extend(jobs)
                return [{'cache_hit': False} for job in jobs], {'total_ms': 1}
            def command(args, **_):
                if args[0] == 'ffprobe':
                    return Mock(stdout=json.dumps({'streams': [{'codec_type': 'video', 'nb_read_frames': '303', 'duration': '303'}]}))
                if args[0] == 'ffmpeg' and '-c' in args:
                    (stage / 'clip.mp4').write_bytes(b'validated fixture')
                return Mock()
            chunks = []
            for base, count in ((0, 300), (300, 3)):
                frames = [{'index': i, 'video_s': i, 'session_ms': 1009 + (base + i) * 1000,
                           'session_s': (base + i) + 0.009, 'window': '1'} for i in range(count)]
                chunks.append((root, {'frames': frames, 'timeline_gaps': [], 'status': 'complete', 'limitations': []}))
            args = argparse.Namespace(fps=1)
            source = {'start': 1000, 'end': 303250, 'duration_s': 302.25,
                      'segments': [{'isActive': False, 'durationMs': 200000}]}
            with patch.object(lab, 'PRIVATE', root), patch.object(preparation.subprocess, 'run', side_effect=command), patch.object(bundles, 'bundle', side_effect=chunks), patch.object(investigate, 'render_chunks', side_effect=render), patch.object(investigate, 'renderer_hash', return_value='renderer'):
                export, coverage = preparation.video(args, 'demo', source, stage)
            self.assertEqual(len(captured), 2)
            self.assertEqual(captured[0]['duration'], 300)
            self.assertAlmostEqual(captured[1]['duration'], 2.241)
            self.assertFalse(coverage['inactive_periods_removed'])
            self.assertEqual(coverage['pre_snapshot_unrenderable_ms'], 9)
            self.assertEqual(len(export['frames']), 303)


if __name__ == '__main__':
    unittest.main()
