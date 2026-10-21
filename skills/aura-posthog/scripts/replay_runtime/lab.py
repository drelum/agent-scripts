#!/usr/bin/env python3
"""Laboratórios locais: download web, preparação upstream, evidência e servidor loopback."""
import argparse
from collections import defaultdict
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import replay_download as download
from replay_evidence import analyze_window

PRIVATE = ROOT / 'private'
LABEL = re.compile(r'^[a-z0-9][a-z0-9-]{0,60}$')


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + '.pending')
    with temp.open('wb') as stream:
        os.chmod(temp, 0o600)
        stream.write(content if isinstance(content, bytes) else content.encode())
    temp.replace(path)


def write_json(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def digest(value):
    return hashlib.sha256(value).hexdigest()


def valid_name(value):
    if not LABEL.fullmatch(value):
        raise ValueError('Nome local: letras minúsculas, números e hífen, até 61 caracteres.')
    return value


def published(root, name):
    catalog = root / 'catalog.json'
    if not catalog.is_file():
        return False
    return any(item['name'] == name for item in json.loads(catalog.read_text()))


def cached_block(root, source, fetch, force=False):
    """Chave por metadados; hash verifica disco; cauda sempre revalidada pelo chamador."""
    key = str(source['blob_key'])
    if not key.isdigit():
        raise ValueError('Blob key não suportada.')
    fingerprint = digest(json.dumps(source, sort_keys=True).encode())
    path, metadata = root / f'{key}.jsonl', root / f'{key}.cache.json'
    if not force and path.is_file() and metadata.is_file():
        stored = json.loads(metadata.read_text())
        body = path.read_bytes()
        if stored.get('source_fingerprint') == fingerprint and stored.get('sha256') == digest(body):
            return body, True
    body = fetch()
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        raise ValueError('Bloco vazio; não publicado no cache.')
    for line in lines:
        row = json.loads(line)
        if not isinstance(row, (list, dict)):
            raise ValueError('Formato do bloco inválido; cache recusado.')
    atomic(path, body)
    write_json(metadata, {'source_fingerprint': fingerprint, 'sha256': digest(body), 'bytes': len(body)})
    return body, False


def prepare(input_path, name, provenance):
    started = time.monotonic()
    name = valid_name(name)
    target = PRIVATE / 'datasets' / name
    parser_hash = digest(b''.join(path.read_bytes() for path in (Path(__file__), ROOT / 'replay_context.py', PRIVATE / 'core.cjs', Path(download.__file__), ROOT.parent / 'replay_evidence.py')))
    input_hash = digest(input_path.read_bytes())
    if published(PRIVATE, name) and (target / 'manifest.json').is_file():
        stored = json.loads((target / 'manifest.json').read_text())
        if (stored.get('input_sha256') == input_hash and stored.get('parser_sha256') == parser_hash
                and stored.get('events_sha256') == digest((target / 'events.json').read_bytes())):
            # Manifesto publicado é evidência imutável; novas métricas pertencem à nova execução.
            return {'name': name, 'prepare_cache_hit': True, 'duration_s':stored['duration_s']}
    final_target = target
    # Preparar isoladamente: falha não torna evidências anteriores inacessíveis.
    target = PRIVATE / 'preparations' / f'{name}-{uuid.uuid4().hex}'
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    catalog = PRIVATE / 'catalog.json'
    items = json.loads(catalog.read_text()) if catalog.is_file() else []
    decoded = target / 'decoded.private.json'
    completed = subprocess.run(['node', str(PRIVATE / 'core.cjs'), str(input_path), str(decoded)],
                               capture_output=True, text=True, timeout=120)
    if completed.returncode:
        raise ValueError('Parser upstream recusou a sessão; payload privado omitido.')
    result = json.loads(decoded.read_text())
    windows = defaultdict(list)
    from replay_context import NetworkCollector
    network = NetworkCollector()
    excluded = 0
    for original in result['events']:
        network.feed(original, original['windowId'])
        event = download.sanitize(original)
        event.pop('cv', None)
        ident = str(event.pop('windowId'))
        if event['type'] == 5:
            custom_payload = event.get('data', {}).get('payload')
            if isinstance(custom_payload, dict) and isinstance(custom_payload.get('href'), str):
                from replay_context import safe_url
                payload = event['data'].get('payload', {})
                event['data'] = {'tag': '$pageview', 'payload': {'href': safe_url(payload.get('href', ''))}}
            elif event.get('data', {}).get('tag') not in ('window hidden', 'window visible', '$session_idle', 'sessionIdle', 'sessionNoLongerIdle'):
                excluded += 1
                continue
            else:
                event['data'] = {'tag': event['data']['tag'], 'payload': {}}
        elif event['type'] == 6:
            excluded += 1
            continue
        if event['type'] == 3 and event.get('data', {}).get('source') == 5:
            event['data']['text'] = '[REDACTED]'
        windows[ident].append(event)
    if not windows or any(not any(e['type'] == 2 for e in events) for events in windows.values()):
        raise ValueError('Aba sem snapshot completo; reprodução não publicada.')
    first = min(e['timestamp'] for events in windows.values() for e in events)
    last = max(e['timestamp'] for events in windows.values() for e in events)
    evidence = []
    summaries = []
    for ident, events in windows.items():
        analyzed = analyze_window(events)
        for item in analyzed['timeline']:
            evidence.append({**item, 'window': ident, 'session_s': round(item['s'] + (analyzed['start_ms'] - first) / 1000, 3)})
        summaries.append({'id': ident, 'events': len(events), 'start': analyzed['start_ms'], 'end': analyzed['end_ms'],
                          'snapshots': analyzed['snapshots'], 'clicks': analyzed['clicks'],
                          'input_updates': sum(analyzed['input_updates_by_control'].values()),
                          'repetitions': analyzed['rapid_repetitions_not_frustration']})
    evidence.sort(key=lambda entry: entry['session_s'])
    events_path = target / 'events.json'
    write_json(events_path, windows)
    manifest = {'name': name, 'start': first, 'end': last, 'duration_s': (last - first) / 1000,
                'window_id_map': result.get('window_id_map', {}),
                'input_sha256': input_hash, 'parser_sha256':parser_hash,
                'windows': summaries, 'provenance': provenance, 'events_sha256': digest(events_path.read_bytes()),
                'diagnostics': result['diagnostics'], 'preparation_ms': result['preparation_ms'], 'preparation_total_ms':(time.monotonic() - started) * 1000, 'plugins_excluded': excluded,
                'segments': result['segments'], 'evidence': evidence, 'network': network.finish(),
                'limitations': ['Texto do DOM não comprova visibilidade.', 'Repetições não comprovam frustração.',
                               'Inputs contam atualizações; valores foram removidos.',
                               'Não comprova pedido persistido, intenção ou causa de erro.',
                               'Frames são reconstruções do rrweb; assets externos bloqueados.']}
    write_json(target / 'manifest.json', manifest)
    lines = [f'# Evidências — {name}', '', *manifest['limitations'], '', '## Linha do tempo (relógio do cliente)', '']
    for item in evidence:
        text = item.get('control') or item.get('path') or item.get('state') or ''
        lines.append(f"- {item['session_s']:.3f}s · aba {item['window']} · {item['kind']} · {text}")
    atomic(target / 'insights.md', '\n'.join(lines))
    previous = None
    if final_target.exists():
        if (PRIVATE / 'bundles' / name / 'package.json').is_file():
            raise ValueError('Dataset de pacote integral publicado é imutável; escolher outro nome para reprocessar.')
        consumers = [json.loads(file.read_text()) for file in (PRIVATE / 'bundles').glob('*/bundle.json')]
        if any(item.get('status') == 'complete' and item.get('dataset') == name
               and item.get('events_sha256') != manifest['events_sha256'] for item in consumers):
            raise ValueError('Novos eventos divergem de evidências publicadas; escolher outro nome.')
        previous = PRIVATE / 'preparation-backups' / target.name
        previous.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        final_target.rename(previous)
    final_target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        target.rename(final_target)
    except OSError:
        if previous is not None and not final_target.exists():
            previous.rename(final_target)
        raise
    write_json(catalog, [item for item in items if item['name'] != name] + [
        {'name': name, 'duration_s': manifest['duration_s'], 'windows': len(windows), 'events': sum(map(len, windows.values()))}])
    return {**{key: manifest[key] for key in ('name', 'duration_s', 'preparation_ms', 'preparation_total_ms', 'diagnostics')}, 'prepare_cache_hit':False}


def fetch_session(args):
    host = download.origin(args.host)
    token, _ = download.credentials(host, args.project)
    client = download.Client(host, args.project, token, 256 * 1024 * 1024, 1000)
    if client.cli('project-get', {}).get('id') != args.project:
        raise ValueError('Projeto ativo não confere.')
    session = str(uuid.UUID(args.session))
    meta = client.cli('session-recording-get', {'id': session})
    if meta.get('found') is False or meta.get('id') != session or meta.get('snapshot_source') not in (None, 'web'):
        raise ValueError('Gravação web não disponível.')
    sources = client.sources(session)
    if not sources:
        raise ValueError('Sessão sem fontes; não tratar como saudável.')
    cache = PRIVATE / 'cache' / str(args.project) / session
    bodies, hits = [], 0
    started = time.monotonic()
    # Lotes fechados de 21 + cauda isolada: repetir transfere só a parte ainda mutável.
    groups = download.lotes(0, len(sources) - 2) + [(len(sources) - 1, len(sources) - 1)]
    for lo, hi in groups:
        source = {**sources[lo], 'batch_sources': sources[lo:hi + 1]}
        path = (f'/api/environments/{args.project}/session_recordings/{session}/snapshots'
                f"?source=blob_v2&start_blob_key={sources[lo]['blob_key']}&end_blob_key={sources[hi]['blob_key']}&decompress=true")
        body, hit = cached_block(cache / 'batches', source, lambda: client.get(path), force=hi == len(sources) - 1)
        bodies.append(body)
        hits += (hi - lo + 1) if hit else 0
    after = client.sources(session)
    if after != sources:
        raise ValueError('Fontes mudaram durante download; executar novamente para atualizar a cauda.')
    combined = cache / 'combined.private.jsonl'
    combined_bytes = b'\n'.join(bodies)
    source_fingerprint = digest(json.dumps(sources, sort_keys=True).encode())
    published_bundle = PRIVATE / 'bundles' / args.name / 'bundle.json'
    previous = PRIVATE / 'datasets' / args.name / 'manifest.json'
    if published_bundle.is_file() and previous.is_file():
        stored = json.loads(previous.read_text())
        if (stored.get('provenance', {}).get('source_fingerprint') != source_fingerprint
                or stored.get('input_sha256') != digest(combined_bytes)):
            raise ValueError('Fontes de pacote publicado mudaram; escolher outro nome para preservar evidências.')
    atomic(combined, combined_bytes)
    provenance = {'kind': 'api_snapshots', 'blocks': len(sources), 'cache_hits': hits, 'requests': client.requests,
                  'session_id': session, 'project_id': args.project, 'host': host,
                  'downloaded_bytes': client.downloaded, 'download_s': round(time.monotonic() - started, 3),
                  'source_fingerprint': source_fingerprint}
    return prepare(combined, args.name, provenance)


def serve():
    import routes
    # Caminhos explicitamente permitidos; cache bruto e credenciais jamais servidos.
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if routes.get(self, ROOT, PRIVATE):
                return
            self.send_error(404)

        def do_POST(self):
            routes.post(self, PRIVATE)

        def log_message(self, fmt, *values):
            # Não registrar query string que possa conter dados privados.
            print(f'HTTP {self.command} {urlsplit(self.path).path}', flush=True)

    port = int(os.environ.get('PORT', '8767'))
    print(f'Investigação local em http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    local = sub.add_parser('prepare')
    local.add_argument('input', type=Path)
    local.add_argument('--name', required=True)
    fetch = sub.add_parser('download')
    fetch.add_argument('session')
    fetch.add_argument('--name', required=True)
    fetch.add_argument('--host', default='https://us.posthog.com')
    fetch.add_argument('--project', type=int, default=331102)
    plan = sub.add_parser('plan')
    plan.add_argument('name')
    plan.add_argument('--at', type=float, required=True)
    plan.add_argument('--window', type=int, default=1)
    sub.add_parser('serve')
    args = parser.parse_args()
    try:
        if args.command == 'serve':
            serve()
        elif args.command == 'download':
            valid_name(args.name)
            print(json.dumps(fetch_session(args), ensure_ascii=False))
        elif args.command == 'plan':
            target = PRIVATE / 'datasets' / valid_name(args.name)
            manifest = json.loads((target / 'manifest.json').read_text())
            if not 0 <= args.at <= manifest['duration_s'] or args.window < 1:
                raise ValueError('Instante/aba inválidos.')
            subprocess.run(['node', str(PRIVATE / 'core.cjs'), 'plan', str(target / 'events.json'),
                            str(manifest['start'] + args.at * 1000), str(args.window)], check=True, timeout=20)
        else:
            print(json.dumps(prepare(args.input, args.name, {'kind': 'local', 'input_sha256': digest(args.input.read_bytes())}), ensure_ascii=False))
    except (ValueError, OSError, subprocess.SubprocessError, download.DownloadError) as error:
        # Mensagens de erros locais não incluem corpo/URL/segredos.
        print(f'Laboratório interrompido: {error if isinstance(error, (ValueError, download.DownloadError)) else type(error).__name__}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
