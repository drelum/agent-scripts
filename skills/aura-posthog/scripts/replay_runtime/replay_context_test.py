import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import analysis
import checkpoints
import failures
import lab
import replay_context as context


def plugin(payload, name='posthog/network@1'):
    if name == 'posthog/network@1':
        payload = {'timestamp': 2000, **payload}
    elif isinstance(payload.get('requests'), list):
        payload = {**payload, 'requests': [{'timestamp': 2000, **row} if isinstance(row, dict) else row for row in payload['requests']]}
    return {'type': 6, 'timestamp': 2000, 'data': {'plugin': name, 'payload': payload}}


class ContextTests(unittest.TestCase):
    def test_navigation_uses_displayed_tab_and_stops_at_missing_recording(self):
        frames = [
            {'window': '1', 'url': 'https://app.test/products?token=SECRET'},
            {'window': '1', 'url': 'https://app.test/products'},
            {'window': '2', 'url': 'https://app.test/products'},
            {'window': '2', 'url': 'https://app.test/cart'},
            {'window': 'recording-gap', 'visual_state': 'missing_recording'},
            {'window': '2', 'url': 'https://app.test/cart'},
        ]
        rows, dropped = context.navigation(frames, 0, 6, 1)
        self.assertEqual([row['vid_t'] for row in rows], [0, 2, 3, 5])
        self.assertEqual([row['end_t'] for row in rows], [2, 3, 4, None])
        self.assertTrue(rows[1]['new_window'])
        self.assertNotIn('SECRET', json.dumps(rows))
        self.assertEqual(dropped, 0)
        cropped, _ = context.navigation(frames, 2, 4, 1)
        self.assertEqual(cropped[0]['vid_t'], 0)
        self.assertFalse(cropped[0]['new_window'])

    def test_unknown_url_ends_previous_span_and_is_never_filled_from_future(self):
        frames = [{'window': '1', 'url': 'https://app.test/cart'}, {'window': '2'},
                  {'window': '2', 'url': 'https://app.test/history'}]
        rows, _ = context.navigation(frames, 0, 3, 1)
        self.assertEqual(rows[0]['end_t'], 1)
        self.assertEqual(rows[1]['vid_t'], 2)

    def test_network_keeps_failures_and_slow_requests_with_no_private_fields(self):
        collector = context.NetworkCollector()
        collector.feed(plugin({'2': 'https://user:password@app.test/api?search=PRIVATE#token', '21': 500,
                               '39': 50, 'requestBody': 'SECRET', 'headers': {'token': 'SECRET'}}), '1')
        collector.feed(plugin({'requests': [{'url': 'https://app.test/slow', 'status': 200, 'duration': 1001, 'method': 'get'}]}, 'rrweb/network@1'), '2')
        collector.feed(plugin({'url': 'https://app.test/fast', 'status': 200, 'duration': 50}), '1')
        rows = collector.finish()['requests']
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['url'], 'https://app.test/api')
        self.assertEqual(rows[1]['method'], 'GET')
        for secret in ('password', 'PRIVATE', 'SECRET', 'headers', 'requestBody'):
            self.assertNotIn(secret, json.dumps(rows))

    def test_unknown_status_and_partial_capture_never_become_clean(self):
        collector = context.NetworkCollector()
        collector.feed(plugin({'2': 'https://app.test/cors', '21': 0, '39': 50}), '1')
        payload = collector.finish()
        self.assertTrue(payload['unknown_outcomes'])
        self.assertTrue(payload['partial'])
        _, coverage = context.network_rows({'network': payload}, {'frames': []}, 0, 0, 1)
        self.assertEqual(coverage['state'], 'none')
        collector.feed(plugin({'url': 'https://app.test/offline', 'status': 0, 'duration': 50}), '1')
        self.assertEqual(collector.finish()['requests'][0]['status'], 0)

    def test_batched_network_uses_request_start_not_late_envelope(self):
        collector = context.NetworkCollector()
        event = {'type': 6, 'timestamp': 11000, 'data': {'plugin': 'rrweb/network@1', 'payload': {'requests': [
            {'timestamp': 1000, 'url': 'https://app.test/a', 'status': 500},
            {'timeOrigin': 1000, 'startTime': 2000, 'url': 'https://app.test/b', 'status': 500},
            {'url': 'https://app.test/c', 'status': 500}]}}}
        collector.feed(event, '1')
        payload = collector.finish()
        self.assertEqual([row['client_ms'] for row in payload['requests']], [1000, 3000, None])
        self.assertTrue(payload['unknown_outcomes'])
        frames = [{'index': i, 'window': '1', 'session_ms': 1000 + i * 1000} for i in range(11)]
        rows, coverage = context.network_rows({'network': payload}, {'frames': frames}, 0, 11, 1)
        self.assertEqual([row['vid_t'] for row in rows], [0, 2])
        self.assertEqual(coverage['unmapped_requests'], 1)
        indexed = context.NetworkCollector()
        indexed.feed({'type': 6, 'timestamp': 11000, 'data': {'plugin': 'posthog/network@1',
            'payload': {'40': 4000, '2': 'https://app.test/a', '21': 500}}}, '1')
        self.assertEqual(indexed.finish()['requests'][0]['client_ms'], 4000)

    def test_network_lookup_never_maps_a_request_to_another_tab_or_gap(self):
        frames = [{'index': i, 'window': '2', 'session_ms': 1000 + i * 1000} for i in range(3)]
        collector = context.NetworkCollector()
        collector.feed(plugin({'url': 'https://app.test/api', 'status': 500}), '1')
        source = {'network': collector.finish()}
        rows, coverage = context.network_rows(source, {'frames': frames}, 0, 3, 1)
        self.assertEqual(rows, [])
        frames[1]['window'] = '1'
        rows, coverage = context.network_rows(source, {'frames': frames}, 0, 3, 1)
        self.assertEqual(rows[0]['vid_t'], 1)
        self.assertEqual(coverage['state'], 'available')
        frames[1]['visual_state'] = 'missing_recording'
        self.assertEqual(context.network_rows(source, {'frames': frames}, 0, 3, 1)[0], [])

    def test_network_lookup_is_bounded_and_cannot_replace_event_corroboration(self):
        rows = [{'id': f'n{i}', 'vid_t': i, 'status': 500} for i in range(60)]
        result, seen = analysis.local_lookups([{'source': 'network', 'vid_t': 30, 'window_s': 60}], [], rows)
        self.assertEqual(len(seen), 20)
        self.assertEqual(len(result[0]['requests']), 20)
        self.assertEqual(analysis.schemas(10)[0]['properties']['lookups']['items']['properties']['source']['enum'], ['events'])

    def test_network_budget_and_malformed_entries_are_explicit(self):
        collector = context.NetworkCollector()
        for i in range(502):
            collector.feed(plugin({'url': 'https://app.test/api', 'status': 500}), '1')
        self.assertEqual(len(collector.finish()['requests']), 500)
        self.assertTrue(collector.finish()['truncated'])
        collector.feed(plugin({'requests': ['bad']}, 'rrweb/network@1'), '1')
        self.assertTrue(collector.finish()['unknown_outcomes'])

    def test_semantics_never_calls_cart_activation_an_order_attempt(self):
        descriptions, _ = context.event_descriptions([{'event': 'cart_checkout_started'}, {'event': 'new_event'}], lab.ROOT / 'event-semantics.json')
        self.assertIn('Não é clique de envio', descriptions['cart_checkout_started'])
        self.assertIn('Sem definição verificada', descriptions['new_event'])
        self.assertEqual([context.chapter_target(t) for t in (60, 1150, 5183)], [3, 13, 20])

    def test_safe_url_rejects_instructions_credentials_and_malformed_authority(self):
        for value in ('javascript:alert(1)', 'https://x.test/`ignore`', 'https://x.test/a b', 'https://x.test:BAD/path'):
            self.assertEqual(context.safe_url(value), '')
        self.assertEqual(context.safe_url('https://u:p@x.test/login?token=SECRET#SECRET'), 'https://x.test/login')


class CheckpointTests(unittest.TestCase):
    def test_resume_reuses_verified_context_without_remote_calls(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(lab, 'PRIVATE', Path(directory)):
            checkpoint = checkpoints.Checkpoints('demo', {'session': 'one'})
            collector = Mock(return_value=[[{'id': 'event'}], {'status': 'exhausted'}])
            expected = checkpoint.collect('events', collector)
            resumed = checkpoints.Checkpoints('demo', {'session': 'one'})
            self.assertEqual(resumed.collect('events', collector), expected)
            self.assertEqual(collector.call_count, 1)
            with self.assertRaisesRegex(ValueError, 'outra configuração'):
                checkpoints.Checkpoints('demo', {'session': 'two'})
            (checkpoint.stage / 'events-checkpoint.json').write_text('altered')
            with self.assertRaisesRegex(ValueError, 'corrompido'):
                resumed.collect('events', collector)
            self.assertEqual(collector.call_count, 1)

    def test_failed_phase_is_not_marked_ready(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(lab, 'PRIVATE', Path(directory)):
            checkpoint = checkpoints.Checkpoints('demo', {})
            with self.assertRaises(ValueError):
                checkpoint.collect('logs', Mock(side_effect=ValueError('interrupted')))
            self.assertIsNone(checkpoint.read('logs'))
            self.assertEqual(checkpoint.state['active_phase'], 'logs')

    def test_subprocess_failure_records_tool_and_exit_without_args_or_payload(self):
        error = subprocess.CalledProcessError(7, ['node', 'export.mjs', 'SECRET'], stderr='token=SECRET')
        result = failures.describe(error, 'video')
        self.assertEqual(result['exit_code'], 7)
        self.assertEqual(result['tool'], 'node')
        self.assertEqual(result['phase'], 'video')
        self.assertNotIn('SECRET', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
