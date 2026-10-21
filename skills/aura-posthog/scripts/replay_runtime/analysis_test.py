import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

import analysis
import bundles
import lab


def answer():
    return {'title': 'Busca', 'summary': 'Usuário busca produtos (t 3).',
        'chapters': [{'title': 'Busca', 'video_t': 0}],
        'intent': {'hypothesis': 'Consultar catálogo', 'video_t': 3, 'event_ids': ['search']},
        'friction': {'level': 'unknown', 'observations': 'Dados insuficientes', 'video_t': None, 'event_ids': []},
        'verdict_visible_error': 'no', 'visible_errors': [], 'telemetry_only_flags': [], 'hypotheses': [],
        'outcome': 'Desfecho não confirmado', 'notability_reason': 'Sem falha observada', 'notability': 0.1,
        'key_moment_t': 3, 'thumbnail_t': 3}


class AnalysisTests(unittest.TestCase):
    def test_gap_cards_never_become_ui_error_intent_or_friction_evidence(self):
        frames = [{'video_s': index, 'visual_state': 'missing_recording' if 3 <= index < 6 else 'recorded'} for index in range(10)]
        self.assertEqual(analysis.visual_gaps(frames, 2, 9, 1), [{'start_s': 1, 'end_s': 4}])
        valid = answer(); valid['intent']['video_t'] = 6
        analysis.validate_visual_claims(valid, frames, 0, 10, 1)
        for field in ('intent', 'friction'):
            invalid = copy.deepcopy(valid); invalid[field]['video_t'] = 3
            with self.assertRaisesRegex(ValueError, 'sem gravação'):
                analysis.validate_visual_claims(invalid, frames, 0, 10, 1)
        invalid = copy.deepcopy(valid); invalid['visible_errors'] = [{'video_t': 4}]
        with self.assertRaisesRegex(ValueError, 'sem gravação'):
            analysis.validate_visual_claims(invalid, frames, 0, 10, 1)

    def test_partial_clip_end_validates_the_exact_published_snapshot(self):
        frames = [{'visual_state': 'missing_recording' if index == 9 else 'recorded'} for index in range(15)]
        value = answer(); value['intent']['video_t'] = 0
        value['verdict_visible_error'] = 'yes'
        value['visible_errors'] = [{'video_t': 3.3, 'description': 'Erro', 'event_ids': []}]
        _, schema = analysis.schemas(10 / 3)
        Draft202012Validator(schema).validate(value)
        self.assertEqual(analysis.source_frame_index(3.3, 0, 10, 3), 9)
        with self.assertRaisesRegex(ValueError, 'sem gravação'):
            analysis.validate_visual_claims(value, frames, 0, 10, 3)
        frames[9]['visual_state'] = 'recorded'
        frames[10]['visual_state'] = 'missing_recording'
        analysis.validate_visual_claims(value, frames, 0, 10, 3)

    def test_provider_shape_preserves_local_bounds_and_rejects_confidence(self):
        _, schema = analysis.schemas(10)
        native = analysis.provider_schema(schema)
        self.assertNotIn('exclusiveMaximum', json.dumps(native))
        self.assertIn('exclusiveMaximum', json.dumps(schema))
        valid = answer(); Draft202012Validator(schema).validate(valid)
        invalid = {**valid, 'confidence': 1.0}
        with self.assertRaises(ValidationError): Draft202012Validator(schema).validate(invalid)
        invalid = {**valid, 'thumbnail_t': 10}
        Draft202012Validator(native).validate(invalid)
        with self.assertRaises(ValidationError): Draft202012Validator(schema).validate(invalid)

    def test_unknown_ids_and_uncorrelated_positive_error_are_rejected(self):
        value = answer(); value['intent']['event_ids'] = ['invented']
        with self.assertRaises(ValueError): analysis.validate_references(value, {'search'}, [], 10)
        value = answer(); value['verdict_visible_error'] = 'yes'
        with self.assertRaises(ValueError): analysis.validate_references(value, {'search'}, [], 10)
        value['visible_errors'] = [{'description': 'HTTP 500', 'video_t': 5, 'event_ids': ['search']}]
        with self.assertRaises(ValueError): analysis.validate_references(value, {'search'}, [], 10)
        self.assertIn(5, analysis.validate_references(value, {'search'}, [{'vid_t': 5, 'window_s': 1}], 10))

    def test_contradictory_negative_error_or_bad_text_citation_is_rejected(self):
        value = answer(); value['visible_errors'] = [{'description': 'HTTP 500', 'video_t': 5, 'event_ids': []}]
        with self.assertRaises(ValueError): analysis.validate_references(value, {'search'}, [], 10)

    def test_every_summary_citation_and_chapter_gets_a_snapshot_reference(self):
        value = answer()
        value['summary'] = 'Início (t 2), tentativa e resultado (t 7, t 7.5).'
        value['chapters'] = [{'title': 'Início', 'video_t': 0}, {'title': 'Busca', 'video_t': 5}]
        result = analysis.validate_references(value, {'search'}, [], 10)
        self.assertEqual(result, [0, 2, 3, 5, 7, 7.5])
        value = answer(); value['summary'] = 'Falha (t 10.5)'
        with self.assertRaises(ValueError): analysis.validate_references(value, {'search'}, [], 10)
        value = answer(); value['chapters'] = [{'title': 'Fim', 'video_t': 5}, {'title': 'Início', 'video_t': 1}]
        with self.assertRaises(ValueError): analysis.validate_references(value, {'search'}, [], 10)

    def test_empty_model_limits_do_not_remove_source_limits(self):
        result = analysis.limits({'coverage': {'limitations': ['Spans amostrados']}}, True)
        self.assertIn('Spans amostrados', result)
        self.assertTrue(any('recorte' in value for value in result))
        self.assertTrue(any('backend' in value for value in result))

    def test_backend_clock_never_gets_a_visual_frame_from_temporal_proximity(self):
        frames = [{'video_s': i, 'session_s': i, 'index': i} for i in range(10)]
        context = {'events': [{'id': 'search', 'event': 'search', 'frame_index': 3, 'session_s': 3}],
            'backend_spans': [{'id': 's1', 'server_ms': 3000, 'status_code': 2, 'name': 'HTTP POST'}],
            'backend_logs': []}
        rows = analysis.context_rows(context, {'frames': frames, 'events': []}, 2, 8, 1)
        self.assertEqual(rows[0]['vid_t'], 1)
        self.assertIsNone(rows[1]['vid_t'])
        self.assertIn('not aligned', rows[1]['clock'])
        found, seen = analysis.local_lookups([{'vid_t': 1, 'window_s': 1}, {'vid_t': 2, 'window_s': 1}], rows)
        self.assertEqual(seen, {'search', 'span-s1'})
        self.assertEqual(found[1]['events'], [])

    def test_clip_bounds_quantize_to_observed_frames_and_reject_outside_video(self):
        frames = [{'video_s': i / 3} for i in range(30)]
        self.assertEqual(analysis.clip_range(frames, 3, 0.2, 1), (1, 4))
        self.assertEqual(analysis.clip_range(frames, 3, 0, None), (0, 30))
        for start, duration in [(10, None), (9, 2), (-1, 2), (0, 0), (float('nan'), 2)]:
            with self.assertRaises(ValueError): analysis.clip_range(frames, 3, start, duration)

    def test_schema_or_reference_failure_keeps_paid_response_and_cost_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = {'model': analysis.MODEL, 'provider': 'Google', 'usage': {'cost': 0.01},
                'choices': [{'finish_reason': 'stop', 'message': {'content': '{"invalid":true}'}}]}
            class Response:
                def __enter__(self): return self
                def __exit__(self, *_): return False
                def read(self): return json.dumps(result).encode()
            with patch.dict(analysis.os.environ, {'OPENROUTER_API_KEY': 'test-key'}), patch.object(analysis.urllib.request, 'urlopen', return_value=Response()):
                with self.assertRaises(analysis.ModelOutputError):
                    analysis.request_model(analysis.MODEL, [], analysis.schemas(10)[1], root, 'answer', 30)
            self.assertEqual(bundles.read(root / 'answer-metrics.json')['usage']['cost'], 0.01)
            self.assertNotIn('test-key', (root / 'answer-response.json').read_text())

    def test_invalid_output_is_corrected_once_and_all_costs_are_counted(self):
        metrics = {'usage': {'cost': .01}, 'elapsed_s': 1}
        assistant = {'role': 'assistant', 'content': 'invalid'}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(analysis, 'request_model', side_effect=[analysis.ModelOutputError('JSON inválido', assistant, metrics), (answer(), assistant, metrics)]) as call:
                result, _, attempts = analysis.validated_model('model', [], {}, Path(directory), 'answer', 30)
                self.assertEqual(result, answer())
                self.assertEqual(sum(m['usage']['cost'] for m in attempts), .02)
                self.assertEqual(call.call_count, 2)
                self.assertIn('Corrigir', call.call_args.args[1][-1]['content'])
            with patch.object(analysis, 'request_model', side_effect=analysis.ModelOutputError('JSON inválido', assistant, metrics)) as call:
                with self.assertRaisesRegex(ValueError, 'ainda inválida'):
                    analysis.validated_model('model', [], {}, Path(directory), 'answer', 30)
                self.assertEqual(call.call_count, 2)

    def test_semantic_error_is_corrected_but_transport_or_model_switch_is_not(self):
        metrics = {'usage': {'cost': .01}, 'elapsed_s': 1}
        assistant = {'role': 'assistant', 'content': '{}'}
        invalid = answer(); invalid['intent']['event_ids'] = ['invented']
        validate = lambda value: analysis.validate_references(value, {'search'}, [], 10)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(analysis, 'request_model', side_effect=[(invalid, assistant, metrics), (answer(), assistant, metrics)]) as call:
                analysis.validated_model('model', [], {}, Path(directory), 'answer', 30, validate)
                self.assertEqual(call.call_count, 2)
            for reason in ('OpenRouter HTTP 503', 'Provider devolveu outro modelo'):
                with patch.object(analysis, 'request_model', side_effect=ValueError(reason)) as call:
                    with self.assertRaises(ValueError):
                        analysis.validated_model('model', [], {}, Path(directory), 'answer', 30)
                    self.assertEqual(call.call_count, 1)

    def test_prompts_are_portable_and_reject_tampering_without_oss_clone(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'prompts'
            shutil.copytree(analysis.PROMPTS, target)
            with patch.object(analysis, 'PROMPTS', target):
                analysis.template_environment()
                (target / 'preamble.jinja').write_text('alterado')
                with self.assertRaises(ValueError): analysis.template_environment()

    def test_analysis_cache_checks_snapshot_bytes_and_config_without_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / 'analyses/test'; output.mkdir(parents=True)
            source = root / 'bundles/demo/snapshots'; source.mkdir(parents=True)
            image = source / 'frame-000003.png'; image.write_bytes(b'original')
            config = {'bundle': 'demo', 'video_sha256': 'video'}
            lab.write_json(output / 'analysis.json', {'references': [{'source_frame': 3,
                'snapshot': {'file': image.name, 'video_sha256': 'video', 'sha256': bundles.sha(image)}}]})
            lab.write_json(output / 'analysis-manifest.json', {'config': config,
                'files': {'analysis.json': bundles.sha(output / 'analysis.json')}})
            with patch.object(lab, 'PRIVATE', root):
                self.assertTrue(analysis.cache(output, config)['cache_hit'])
                with self.assertRaises(ValueError): analysis.cache(output, {**config, 'model': 'changed'})
                image.write_bytes(b'altered')
                with self.assertRaises(ValueError): analysis.cache(output, config)


if __name__ == '__main__': unittest.main()
