#!/usr/bin/env python3
"""Sessões locais: setup, doctor, build, serve, search, context, snapshot, annotate e ticket."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import bundles
import lab
import runtime
import recording_coverage


def guard_dataset(args):
    """Recusar colisão antes de qualquer download/preparação."""
    name = lab.valid_name(args.name)
    if getattr(args, 'input', None):
        stored = lab.PRIVATE / 'datasets' / name / 'manifest.json'
        if stored.exists() and bundles.read(stored).get('input_sha256') != lab.digest(args.input.read_bytes()):
            raise ValueError('Nome de dataset já pertence a outro input. Escolha um nome novo.')
    if args.session:
        session = str(uuid.UUID(args.session))
        stored = lab.PRIVATE / 'datasets' / name / 'manifest.json'
        if stored.exists():
            provenance = bundles.read(stored).get('provenance', {})
            if (provenance.get('session_id') != session or provenance.get('project_id') != args.project
                    or provenance.get('host', lab.download.origin(args.host)) != lab.download.origin(args.host)):
                raise ValueError('Nome de dataset já pertence a outra origem/sessão. Escolha um nome novo.')


def render_export(output, command):
    """Captura isolada; diretório final só muda após sucesso validado."""
    stage = lab.PRIVATE / 'captures' / f'{output.name}-{uuid.uuid4().hex}'
    stage.parent.mkdir(mode=0o700, exist_ok=True)
    subprocess.run([*command, '--output', str(stage)], check=True, timeout=220)
    publish_capture(stage, output)


def publish_capture(stage, output):
    exported = bundles.read(stage / 'export.json')
    if exported.get('status') != 'complete' or bundles.sha(stage / 'clip.mp4') != exported.get('video_sha256'):
        raise ValueError('Captura incompleta; pacote final preservado.')
    if output.exists():
        # Artefatos parciais continuam privados para diagnóstico; nunca remover dados anteriores.
        incomplete = lab.PRIVATE / 'incomplete' / stage.name
        incomplete.parent.mkdir(mode=0o700, exist_ok=True)
        output.rename(incomplete)
    stage.rename(output)


def renderer_hash():
    return lab.digest(b''.join(path.read_bytes() for path in
        (lab.ROOT / 'export.mjs', lab.ROOT / 'browser.mjs', lab.ROOT / 'capture-batch.mjs', lab.PRIVATE / 'headless.js',
         lab.ROOT / 'capture-proof.mjs', lab.ROOT / 'recording_coverage.py', lab.ROOT / 'package-lock.json')))


def render_chunks(dataset, jobs, fps):
    """Uma leitura do dataset; dois browsers; cada recorte continua verificável/cacheável."""
    dataset = lab.valid_name(dataset)
    source = bundles.read(lab.PRIVATE / 'datasets' / dataset / 'manifest.json')
    renderer = renderer_hash()
    pending, results = [], []
    token = uuid.uuid4().hex
    gap_metrics = []
    gap_windows = (bundles.read(lab.PRIVATE / 'datasets' / dataset / 'events.json')
                   if any(job.get('kind') == 'recording_gap' for job in jobs) else None)
    for job in jobs:
        name = lab.valid_name(job['name'])
        output = lab.PRIVATE / 'bundles' / name
        expected = {'dataset': dataset, 'start_s': job['start'], 'requested_duration_s': job['duration'],
                    'fps': fps, 'selected_window': None, 'events_sha256': source['events_sha256'],
                    'renderer_sha256': renderer}
        stored = cached_export(output)
        if stored is not None:
            if any(stored.get(key) != value for key, value in expected.items()) or bundles.sha(output / 'clip.mp4') != stored['video_sha256']:
                raise ValueError('Recorte já pertence a outra versão/configuração; evidência preservada.')
            results.append({'name': name, 'cache_hit': True})
        else:
            if (output / 'bundle.json').exists():
                raise ValueError('Recorte publicado perdeu seu manifesto; evidência preservada.')
            stage = lab.PRIVATE / 'captures' / f'{name}-{token}'
            if job.get('kind') == 'recording_gap':
                exported = recording_coverage.render_gap(source, gap_windows, job, fps, stage, renderer)
                output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                publish_capture(stage, output)
                bundles.publish(lab.PRIVATE, name, dataset, output)
                gap_metrics.append({'name': name, 'total_ms': exported['total_ms'], 'timings': exported['timings']})
                results.append({'name': name, 'cache_hit': False})
                continue
            pending.append({**job, 'fps': fps, 'output': str(stage), 'expected': expected})
            results.append({'name': name, 'cache_hit': False})
    if pending:
        jobfile = lab.PRIVATE / 'captures' / f'batch-{token}.json'
        lab.write_json(jobfile, [{key: item[key] for key in ('start', 'duration', 'fps', 'output')} for item in pending])
        command = ['node', str(lab.ROOT / 'export.mjs'), '--dataset', dataset, '--batch', str(jobfile)]
        try:
            completed = subprocess.run(command, check=True, capture_output=True, text=True,
                                       timeout=240 * ((len(pending) + 1) // 2) + 60)
        except subprocess.CalledProcessError as error:
            lab.atomic(jobfile.with_suffix('.stderr.txt'), error.stderr or '')
            lab.atomic(jobfile.with_suffix('.stdout.txt'), error.stdout or '')
            raise
        finally:
            # Mesmo numa falha, preservar os recortes concluídos; parciais ficam no staging.
            for item in pending:
                stage = Path(item['output'])
                exported = cached_export(stage)
                if exported is not None:
                    if any(exported.get(key) != value for key, value in item['expected'].items()):
                        raise ValueError('Renderer devolveu configuração divergente.')
                    output = lab.PRIVATE / 'bundles' / item['name']
                    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    publish_capture(stage, output)
                    bundles.publish(lab.PRIVATE, item['name'], dataset, output)
        metrics = json.loads(completed.stdout.splitlines()[-1])
    else:
        metrics = {'total_ms': 0, 'chunks': [], 'browsers': [], 'dataset_ms': 0}
    metrics['gap_chunks'] = gap_metrics
    return results, metrics


def cached_export(output):
    file = output / 'export.json'
    if not file.is_file():
        return None
    try:
        stored = bundles.read(file)
        if isinstance(stored, dict) and stored.get('status') == 'complete':
            return stored
    except (ValueError, OSError):
        pass
    if (output / 'bundle.json').exists():
        raise ValueError('Manifesto de captura corrompido; pacote publicado preservado.')
    return None


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('setup', help='Instalar dependências fixadas e compilar as fontes incluídas')
    sub.add_parser('doctor', help='Verificar ferramentas, Chrome configurado e build')
    sub.add_parser('serve', help='Abrir o painel local em loopback (PORT ou 8767)')
    prepare = sub.add_parser('prepare', help='Pacote completo de sessões encerradas, sem chamada LLM')
    selection = prepare.add_mutually_exclusive_group(required=True)
    selection.add_argument('--session')
    selection.add_argument('--latest', type=int)
    prepare.add_argument('--name', required=True)
    prepare.add_argument('--date-from', default='-3d')
    prepare.add_argument('--host', default='https://us.posthog.com')
    prepare.add_argument('--project', type=int, default=331102)
    prepare.add_argument('--service', default='aura')
    prepare.add_argument('--fps', type=int, default=3)
    analyze = sub.add_parser('analyze', help='Gemini: pacote verificado + missão → análise com referências')
    analyze.add_argument('bundle')
    analyze.add_argument('--name', required=True)
    analyze.add_argument('--mission', type=Path, required=True)
    analyze.add_argument('--problem', type=Path)
    analyze.add_argument('--model', default='google/gemini-3-flash-preview')
    analyze.add_argument('--start', type=float, default=0)
    analyze.add_argument('--duration', type=float)
    analyze.add_argument('--timeout', type=int, default=180)
    build = sub.add_parser('build')
    origin = build.add_mutually_exclusive_group(required=True)
    origin.add_argument('--dataset')
    origin.add_argument('--session')
    origin.add_argument('--input', type=Path, help='Snapshots JSONL já baixados; mesma preparação e captura')
    build.add_argument('--host', default='https://us.posthog.com')
    build.add_argument('--project', type=int, default=331102)
    build.add_argument('--name', required=True)
    build.add_argument('--start', type=float, default=0)
    build.add_argument('--duration', type=float, default=10)
    build.add_argument('--fps', type=int, default=12)
    build.add_argument('--window')
    build.add_argument('--context', type=Path)
    for name in ('search', 'context', 'snapshot', 'ticket', 'annotate'):
        cmd = sub.add_parser(name)
        cmd.add_argument('bundle')
        if name == 'search':
            cmd.add_argument('query', nargs='?', default='')
        elif name == 'context':
            cmd.add_argument('event_id')
        elif name == 'annotate':
            cmd.add_argument('--input', type=Path, required=True)
        else:
            cmd.add_argument('--frame', type=int, required=True)
            if name == 'ticket':
                cmd.add_argument('--title', default='Evidência da sessão')
    args = parser.parse_args()
    try:
        if args.command == 'setup':
            return runtime.setup()
        if args.command == 'doctor':
            result = runtime.doctor()
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result['ready'] else 1
        if args.command == 'serve':
            lab.serve()
            return 0
        if args.command == 'prepare':
            import preparation
            return preparation.run(args)
        if args.command == 'analyze':
            command = [str(runtime.analysis_python()), str(lab.ROOT / 'analysis.py'), args.bundle,
                '--name', args.name, '--mission', str(args.mission), '--model', args.model,
                '--start', str(args.start), '--timeout', str(args.timeout)]
            if args.problem:
                command.extend(['--problem', str(args.problem)])
            if args.duration is not None:
                command.extend(['--duration', str(args.duration)])
            return subprocess.run(command).returncode
        if args.command == 'build':
            guard_dataset(args)
            if args.input:
                args.dataset = args.name
                lab.prepare(args.input, args.name, {'kind':'local', 'input_sha256':lab.digest(args.input.read_bytes())})
            if args.session:
                args.dataset = args.name
                lab.fetch_session(args)
            name, dataset = lab.valid_name(args.name), lab.valid_name(args.dataset)
            output = lab.PRIVATE / 'bundles' / name
            output.parent.mkdir(mode=0o700, exist_ok=True)
            source = bundles.read(lab.PRIVATE / 'datasets' / dataset / 'manifest.json')
            context_info = None
            if args.session and not args.context:
                import context_api
                args.context, context_info = context_api.fetch(args, source)
            renderer = renderer_hash()
            if args.context:
                bundles.context_rows(args.context, source['start'], source.get('provenance', {}).get('session_id'), source.get('window_id_map'))
            command = ['node', str(lab.ROOT / 'export.mjs'), '--dataset', dataset, '--start', str(args.start),
                       '--duration', str(args.duration), '--fps', str(args.fps)]
            if args.window:
                command += ['--window', args.window]
            reused = False
            stored = cached_export(output)
            if stored is not None:
                expected = {'dataset':dataset, 'start_s':args.start, 'requested_duration_s':args.duration,
                            'fps':args.fps, 'selected_window':args.window, 'events_sha256':source['events_sha256'],
                            'renderer_sha256':renderer}
                if any(stored.get(key) != value for key, value in expected.items()) or bundles.sha(output / 'clip.mp4') != stored['video_sha256']:
                    raise ValueError('Nome já usado por outra versão/configuração. Escolha outro nome; evidências preservadas.')
                reused = True
            else:
                if (output / 'bundle.json').exists():
                    raise ValueError('Pacote publicado perdeu seu manifesto de captura; evidências preservadas.')
                render_export(output, command)
            result = bundles.publish(lab.PRIVATE, name, dataset, output, args.context)
            result['render_cache_hit'] = reused
            result['context'] = context_info
        else:
            folder, manifest = bundles.bundle(lab.PRIVATE, args.bundle)
            if args.command == 'search':
                query = args.query.casefold()
                result = [e for e in manifest['events'] if query in json.dumps(e, ensure_ascii=False).casefold()]
            elif args.command == 'context':
                event = next(e for e in manifest['events'] if e['id'] == args.event_id)
                result = {'event': event, 'related': bundles.correlate(event, manifest['events'])}
            elif args.command == 'snapshot':
                result = bundles.snapshot(lab.PRIVATE, args.bundle, args.frame)
                result['path'] = str(folder / 'snapshots' / result['file'])
            elif args.command == 'annotate':
                result = bundles.annotate(lab.PRIVATE, args.bundle, args.input)
            else:
                result = bundles.ticket(lab.PRIVATE, args.bundle, args.frame, args.title)
                result['path'] = str(folder / 'tickets' / result['id'])
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, StopIteration, OSError, subprocess.SubprocessError, lab.download.DownloadError) as error:
        print(f'Investigação interrompida: {error if isinstance(error, (ValueError, lab.download.DownloadError)) else type(error).__name__}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
