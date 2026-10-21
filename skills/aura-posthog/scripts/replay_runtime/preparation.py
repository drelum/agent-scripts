"""Um pacote reutilizável: sessão encerrada, contexto tipado e vídeo integral disponível."""
from bisect import bisect_left
from datetime import datetime, timezone
import fcntl
import json
import math
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
import uuid

import bundles
import lab
import session_context as context
import recording_coverage
import checkpoints
import failures
import runtime

CHUNK_SECONDS = 300


def metadata(row):
    keys = ('id', 'start_time', 'end_time', 'ongoing', 'recording_duration', 'active_seconds',
            'inactive_seconds', 'click_count', 'keypress_count', 'console_error_count', 'snapshot_source')
    result = {key: row.get(key) for key in keys}
    result['id'] = str(uuid.UUID(result['id']))
    if result['ongoing'] is not False:
        raise ValueError('Preparação exige sessão encerrada: ongoing exatamente false.')
    for key in ('start_time', 'end_time'):
        stamp = datetime.fromisoformat(result[key])
        if stamp.tzinfo is None:
            raise ValueError('Horário de sessão sem timezone.')
        result[key] = stamp.isoformat()
    if datetime.fromisoformat(result['end_time']) < datetime.fromisoformat(result['start_time']):
        raise ValueError('Fim da sessão anterior ao início.')
    return result


def select(client, latest, date_from, session_id=None):
    if session_id:
        ids = [str(uuid.UUID(session_id))]
        result = client.cli('query-session-recordings-list', {'session_ids': ids, 'limit': 1})
        rows = [row for row in result.get('results', []) if row.get('id') in ids]
        if len(rows) != 1:
            raise ValueError('Sessão não encontrada na seleção.')
        return [metadata(rows[0])], {'skipped_open_or_unknown': 0, 'pages': 1}
    cutoff = datetime.now(timezone.utc).isoformat()
    selected, skipped, cursor, seen = [], 0, None, set()
    for page in range(1, 101):
        query = {'date_from': date_from, 'date_to': cutoff, 'order': 'start_time',
                 'order_direction': 'DESC', 'limit': max(20, latest), 'filter_test_accounts': False}
        if cursor:
            query['after'] = cursor
        result = client.cli('query-session-recordings-list', query)
        for row in result.get('results', []):
            ident = row.get('id')
            if ident in seen:
                raise ValueError('Seleção repetiu sessão; paginação inválida.')
            seen.add(ident)
            if row.get('ongoing') is not False:
                skipped += 1
                continue
            selected.append(metadata(row))
            if len(selected) == latest:
                return selected, {'skipped_open_or_unknown': skipped, 'pages': page, 'cutoff': cutoff}
        next_cursor = result.get('next_cursor') or result.get('nextCursor')
        if not next_cursor:
            raise ValueError('Sessões encerradas insuficientes no período; ampliar --date-from.')
        if next_cursor == cursor:
            raise ValueError('Cursor de seleção repetido.')
        cursor = next_cursor
    raise ValueError('Limite de páginas de seleção atingido.')


def config(args, session_id):
    paths = ('preparation.py', 'checkpoints.py', 'failures.py', 'runtime.py', 'session_context.py', 'lab.py', 'replay_context.py', 'investigate.py', 'export.mjs', 'browser.mjs',
             'capture-batch.mjs', 'capture-proof.mjs', 'recording_coverage.py', 'package-lock.json', 'private/headless.js', 'private/core.cjs')
    return {'session_id': session_id, 'host': lab.download.origin(args.host), 'project': args.project,
            'fps': args.fps, 'service': args.service,
            'pipeline_sha256': lab.digest(b''.join((lab.ROOT / path).read_bytes() for path in paths) + Path(lab.download.__file__).read_bytes())}


def verify(folder, expected=None):
    package = bundles.read(folder / 'package.json')
    if package.get('status') != 'ready' or (expected is not None and package.get('config') != expected):
        raise ValueError('Pacote/configuração divergente; usar outro nome.')
    for filename, proof in package['files'].items():
        if Path(filename).name != filename or bundles.sha(folder / filename) != proof['sha256']:
            raise ValueError('Artefato corrompido; pacote preservado.')
    _, manifest = bundles.bundle(lab.PRIVATE, package['name'])
    if manifest['events_sha256'] != package['events_sha256']:
        raise ValueError('Dataset do pacote mudou.')
    if evidence_hash(manifest) != package['bundle_evidence_sha256']:
        raise ValueError('Índice/contexto do pacote mudou; evidências preservadas.')
    if package.get('dataset_manifest_sha256') and bundles.sha(lab.PRIVATE / 'datasets' / package['name'] / 'manifest.json') != package['dataset_manifest_sha256']:
        raise ValueError('Contexto auxiliar do dataset mudou; pacote preservado.')
    return package


def evidence_hash(bundle):
    evidence = {key: bundle[key] for key in ('events', 'frames', 'video_sha256', 'events_sha256')}
    return lab.digest(json.dumps(evidence, sort_keys=True, separators=(',', ':')).encode())


def map_frames(events, frames, window_map, fps):
    by_window = {}
    for frame in frames:
        by_window.setdefault(frame['window'], []).append(frame)
    clocks = {key: [frame['session_ms'] for frame in values] for key, values in by_window.items()}
    for event in events:
        original = event.get('window')
        event['source_window'] = original
        window = str(window_map[original]) if original in window_map else None
        event['window'] = window
        event['frame_index'] = None
        # Falta de aba/relógio não permite colar o evento em outra tela.
        if window is None or event.get('client_ms') is None or window not in clocks:
            continue
        tick = event['client_ms']
        index = bisect_left(clocks[window], tick)
        candidates = by_window[window][max(0, index - 1):index + 1]
        near = min(candidates, key=lambda frame: abs(frame['session_ms'] - tick)) if candidates else None
        if near and frames[0]['session_ms'] <= tick <= frames[-1]['session_ms'] + 1000 / fps and abs(near['session_ms'] - tick) <= 1000 / fps + 5:
            event['frame_index'] = near['index']


def video(args, name, source, stage):
    import investigate
    windows = bundles.read(lab.PRIVATE / 'datasets' / name / 'events.json')
    first_snapshot = min(event['timestamp'] for events in windows.values() for event in events if event['type'] == 2)
    planned, recording_gaps = recording_coverage.plan(source, windows, CHUNK_SECONDS)
    del windows
    start = (first_snapshot - source['start']) / 1000
    until = source['duration_s']
    if until <= start:
        raise ValueError('Sessão sem intervalo visual reproduzível.')
    frames, chunks, offset, jobs, video_limits = [], [], 0, [], []
    chunk_key = lab.digest(f'{name}:{args.fps}:{investigate.renderer_hash()}'.encode())[:10]
    for job in planned:
        chunk_name = lab.valid_name(f'{name[:35]}-{chunk_key}-v{len(jobs):03}')
        jobs.append({'name': chunk_name, **job})
    started = time.monotonic()
    rendered, batch_metrics = investigate.render_chunks(name, jobs, args.fps)
    phase_timings = {'render_batch_s': time.monotonic() - started, 'batch': batch_metrics}
    for job, result in zip(jobs, rendered, strict=True):
        chunk_name = job['name']
        chunk_folder, chunk = bundles.bundle(lab.PRIVATE, chunk_name)
        if chunk['timeline_gaps']:
            raise ValueError('Vídeo saltou um intervalo; não declarar gravação integral.')
        video_limits.extend(chunk['limitations'])
        for frame in chunk['frames']:
            frames.append({**frame, 'index': offset + frame['index'], 'video_s': (offset + frame['index']) / args.fps,
                           'chunk': chunk_name, 'chunk_frame': frame['index']})
        chunks.append({'name': chunk_name, 'start_s': job['start'], 'duration_s': job['duration'],
                       'kind': job['kind'], 'frames': len(chunk['frames']), 'cache_hit': result['cache_hit']})
        offset += len(chunk['frames'])
    for i, frame in enumerate(frames):
        if i and (frame['session_ms'] <= frames[i - 1]['session_ms'] or frame['session_ms'] - frames[i - 1]['session_ms'] > 2000 / args.fps + 5):
            raise ValueError('Junção de vídeos perdeu/regrediu intervalo.')
    if source['end'] - frames[-1]['session_ms'] > 1000 / args.fps + 5:
        raise ValueError('Vídeo não alcançou o fim da gravação.')
    concat = stage / 'concat.private.txt'
    lab.atomic(concat, '\n'.join(f"file '{(lab.PRIVATE / 'bundles' / item['name'] / 'clip.mp4').as_posix()}'" for item in chunks))
    output = stage / 'clip.mp4'
    if output.exists():
        output.rename(stage / f'clip-incomplete-{uuid.uuid4().hex}.mp4')
    started = time.monotonic()
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'concat', '-safe', '0', '-i', str(concat),
                    '-c', 'copy', str(output)], check=True, capture_output=True, timeout=240)
    phase_timings['concat_s'] = time.monotonic() - started
    started = time.monotonic()
    probe = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams',
                      '-of', 'json', str(output)], check=True, capture_output=True, text=True, timeout=240).stdout)
    stream = next(row for row in probe['streams'] if row['codec_type'] == 'video')
    if int(stream['nb_read_frames']) != len(frames) or abs(float(stream['duration']) - len(frames) / args.fps) > 0.05:
        raise ValueError('Vídeo concatenado diverge do índice.')
    phase_timings['frame_validation_s'] = time.monotonic() - started
    started = time.monotonic()
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(output), '-f', 'null', '-'],
                   check=True, capture_output=True, timeout=240)
    phase_timings['decode_validation_s'] = time.monotonic() - started
    export = {**chunk, 'dataset': name, 'fps': args.fps, 'start_s': (first_snapshot - source['start']) / 1000,
              'requested_duration_s': (source['end'] - first_snapshot) / 1000,
              'encoded_duration_s': len(frames) / args.fps, 'frames': frames, 'timeline_gaps': [],
              'recording_gaps': recording_gaps,
              'limitations': list(dict.fromkeys([*video_limits, *([recording_coverage.GAP_LIMIT] if recording_gaps else [])])),
              'video_sha256': bundles.sha(output), 'chunks': chunks, 'total_ms': None, 'timings': phase_timings}
    lab.write_json(stage / 'export.json', export)
    lab.write_json(stage / 'video-index.json', {'fps': args.fps, 'frames': frames, 'chunks': chunks})
    return export, {'mode': 'integral_available_recording', 'inactive_periods_removed': False,
                    'visual_complete': not recording_gaps, 'recording_gaps': recording_gaps,
                    'gap_duration_s': sum((gap['to_ms'] - gap['from_ms']) / 1000 for gap in recording_gaps),
                    'pre_snapshot_unrenderable_ms': first_snapshot - source['start'],
                    'sampling_tail_ms': source['end'] - frames[-1]['session_ms'],
                    'source_start_ms': source['start'], 'source_end_ms': source['end'],
                    'frames': len(frames), 'encoded_duration_s': len(frames) / args.fps}


def prepare_one(args, client, session, capabilities, name):
    import investigate
    name = lab.valid_name(name)
    expected = config(args, session['id'])
    output = lab.PRIVATE / 'bundles' / name
    if (output / 'package.json').exists():
        started = time.monotonic()
        package = verify(output, expected)
        return {'name': name, 'session_id': session['id'], 'status': 'ready', 'cache_hit': True,
                'total_s': time.monotonic() - started, 'original_metrics': package['metrics']}
    if output.exists():
        raise ValueError('Nome de pacote já ocupado; escolher outro nome.')
    total = time.monotonic()
    timings = {}
    checkpoint = checkpoints.Checkpoints(name, expected)
    stage = checkpoint.stage
    dataset_args = SimpleNamespace(name=name, session=session['id'], project=args.project, host=args.host)
    investigate.guard_dataset(dataset_args)
    # Revalidar imediatamente antes de baixar, sem depender do estado observado na seleção.
    session = select(client, 1, args.date_from, session['id'])[0][0]
    started = time.monotonic()
    if checkpoint.read('dataset') is None:
        checkpoint.begin('dataset')
        print(f'{name}: download e parser', flush=True)
        lab.fetch_session(dataset_args)
        dataset = lab.PRIVATE / 'datasets' / name
        checkpoint.save('dataset', {'ready': True}, [dataset / 'manifest.json', dataset / 'events.json'])
    else:
        print(f'{name}: retomada do dataset verificado', flush=True)
    timings['download_prepare_s'] = time.monotonic() - started
    source = bundles.read(lab.PRIVATE / 'datasets' / name / 'manifest.json')
    print(f'{name}: eventos, logs e traces', flush=True)
    started = time.monotonic()
    events, event_coverage = checkpoint.collect('events', lambda: context.collect_events(client, session, source))
    timings['events_s'] = time.monotonic() - started
    started = time.monotonic()
    logs, log_coverage = checkpoint.collect('logs', lambda: context.collect_logs(client, session, events, capabilities))
    spans, span_coverage = checkpoint.collect('spans', lambda: context.collect_spans(client, session, events, capabilities))
    timings['backend_s'] = time.monotonic() - started
    # Preservar o contexto coletado mesmo quando o renderer rejeita uma lacuna.
    lab.write_json(stage / 'context-pending.json', {'schema': 1, 'status': 'context_ready_video_pending',
        'session': session, 'events': events, 'backend_logs': logs, 'backend_spans': spans,
        'coverage': {'events': event_coverage, 'logs': log_coverage, 'spans': span_coverage},
        'limitations': ['Vídeo ainda não validado; este staging não é um pacote pronto.']})
    print(f'{name}: vídeo integral, {source["duration_s"]:.1f}s', flush=True)
    started = time.monotonic()
    checkpoint.begin('video')
    cached_video = checkpoint.read('video')
    if cached_video is None:
        export, video_coverage = video(args, name, source, stage)
        checkpoint.save('video', [export, video_coverage], [stage / 'clip.mp4', stage / 'export.json', stage / 'video-index.json'])
    else:
        export, video_coverage = cached_video
    timings['video_validate_s'] = time.monotonic() - started
    map_frames(events, export['frames'], source.get('window_id_map', {}), args.fps)
    checkpoint.begin('finalize')
    errors = {'frontend': [row for row in events if row['kind'] == 'error'],
              'backend_logs': [row for row in logs if row['severity_text'].lower() in ('error', 'fatal')],
              'backend_spans': [row for row in spans if row['status_code'] == 2 or int(row['attributes'].get('http.response.status_code', 0)) >= 400]}
    coverage = {'events': event_coverage, 'logs': log_coverage, 'spans': span_coverage, 'video': video_coverage,
                'telemetry_complete': all(item['status'] == 'exhausted' for item in (event_coverage, log_coverage, span_coverage)),
                'limitations': ['Completo significa fontes disponíveis dentro dos períodos declarados; não comprova cobertura de instrumentação.',
                    'Propriedades diagnósticas sanitizadas; variáveis, headers, payloads e inputs excluídos.',
                    'Spans podem ser amostrados; Cloud Run conserva logs de plataforma ausentes no PostHog.',
                    'Eventos sem aba/relógio compatível permanecem sem frame; backend correlacionado por trace, não por relógio presumido.',
                    *export['limitations'],
                    *source['limitations']]}
    full_context = {'schema': 1, 'session': session, 'events': events, 'errors': errors,
                    'backend_logs': logs, 'backend_spans': spans, 'coverage': coverage}
    for filename, value in (('context.json', full_context), ('events.json', events), ('errors.json', errors),
                            ('backend-logs.json', logs), ('backend-spans.json', spans)):
        lab.write_json(stage / filename, value)
    timings['total_s'] = time.monotonic() - total
    files = {file.name: {'sha256': bundles.sha(file), 'bytes': file.stat().st_size}
             for file in stage.iterdir() if file.suffix in ('.json', '.mp4')}
    package = {'schema': 1, 'name': name, 'status': 'ready', 'config': expected,
               'created_at': datetime.now(timezone.utc).isoformat(), 'session_id': session['id'],
               'events_sha256': source['events_sha256'], 'files': files, 'metrics': timings, 'coverage': coverage,
               'dataset_manifest_sha256': bundles.sha(lab.PRIVATE / 'datasets' / name / 'manifest.json'),
               'analysis': 'separate: context.json + clip.mp4 + video-index.json + task prompt/problem context'}
    # Nenhum pacote final fica visível antes de contexto, encoder e hashes serem validados.
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    bundles.publish(lab.PRIVATE, name, name, stage)
    bundle = bundles.read(stage / 'bundle.json')
    bundle['events'].extend(events)
    for row in spans:
        bundle['events'].append({**row, 'id': f'span-{row["id"]}', 'kind': 'backend',
                                'source': 'PostHog traces', 'summary': row['name'],
                                'session_s': None, 'frame_index': None})
    for row in logs:
        stamp = row.get('timestamp')
        try:
            server_ms = datetime.fromisoformat(stamp).timestamp() * 1000 if isinstance(stamp, str) else None
        except ValueError:
            server_ms = None
        bundle['events'].append({**row, 'id': f'log-{row["id"]}', 'source': 'PostHog logs',
                                'summary': f'{row["severity_text"]} · {row["body"]}',
                                'server_ms': server_ms, 'session_s': None, 'frame_index': None})
    bundle['events'].sort(key=lambda row: (row.get('session_s') if row.get('session_s') is not None else math.inf, row['id']))
    bundle['context_imported'] = True
    bundle['context_sha256'] = files['context.json']['sha256']
    bundle['limits'].extend(coverage['limitations'])
    lab.write_json(stage / 'bundle.json', bundle)
    package['bundle_evidence_sha256'] = evidence_hash(bundle)
    lab.write_json(stage / 'package.json', package)
    stage.rename(output)
    verify(output, expected)
    return {'name': name, 'session_id': session['id'], 'status': 'ready', 'cache_hit': False,
            'metrics': timings, 'frames': len(export['frames']), 'events': len(events), 'logs': len(logs),
            'spans': len(spans), 'telemetry_complete': coverage['telemetry_complete']}


def run(args):
    if not 1 <= args.fps <= 30 or (args.latest is not None and not 1 <= args.latest <= 100):
        raise ValueError('FPS 1–30; lote de 1–100 sessões.')
    lab.valid_name(args.name)
    if args.latest and len(args.name) > 24:
        raise ValueError('Prefixo de lote aceita até 24 caracteres; uma sessão específica aceita 61.')
    if not args.session or not (lab.PRIVATE / 'bundles' / args.name / 'package.json').exists():
        runtime.require_capture()
    host = lab.download.origin(args.host)
    token, _ = lab.download.credentials(host, args.project)
    client = lab.download.Client(host, args.project, token, 256 * 1024 * 1024, 1000)
    if client.cli('project-get', {}).get('id') != args.project:
        raise ValueError('Projeto ativo não confere.')
    lock = lab.PRIVATE / 'preparation.lock'
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Outra preparação está ativa; aguardar sua conclusão.') from None
        started = time.monotonic()
        sessions, selection = select(client, args.latest, args.date_from, args.session)
        selection['duration_s'] = time.monotonic() - started
        names = [args.name if args.session else lab.valid_name(f'{args.name}-{row["id"]}') for row in sessions]
        needs_fetch = any(not (lab.PRIVATE / 'bundles' / name / 'package.json').exists()
                          and not all(phase in checkpoints.Checkpoints(name, config(args, session['id'])).state['phases']
                                      for phase in ('events', 'logs', 'spans'))
                          for session, name in zip(sessions, names))
        started = time.monotonic()
        if needs_fetch:
            print('Descoberta de contratos e fontes, uma vez por lote', flush=True)
        capabilities = context.discover(client, args.service) if needs_fetch else None
        discovery_s = time.monotonic() - started
        results = []
        for session, name in zip(sessions, names):
            try:
                results.append(prepare_one(args, client, session, capabilities, name))
            except (ValueError, OSError, subprocess.SubprocessError, lab.download.DownloadError) as error:
                stage = lab.PRIVATE / 'packages-staging' / name
                phase = bundles.read(stage / 'checkpoint.json').get('active_phase', 'prepare') if (stage / 'checkpoint.json').exists() else 'prepare'
                detail = failures.describe(error, phase)
                if stage.exists():
                    lab.write_json(stage / f'failure-{uuid.uuid4().hex}.json', detail)
                results.append({'name': name, 'session_id': session['id'], 'status': 'failed',
                                **detail})
                print(f'{name}: falhou; diagnóstico privado preservado ({type(error).__name__})', flush=True)
                break
        result = {'selection': selection, 'discovery_s': discovery_s, 'sessions': results,
                  'requested': len(sessions), 'ready': sum(row['status'] == 'ready' for row in results)}
        file = lab.PRIVATE / 'runs' / f'{args.name}-{uuid.uuid4().hex}.json'
        lab.write_json(file, result)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['ready'] == len(sessions) else 1
