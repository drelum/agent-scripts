"""Sessões consultáveis e snapshots do vídeo; nenhuma renderização adicional."""
from datetime import datetime
from enum import StrEnum
import hashlib
import json
import math
from pathlib import Path
import subprocess
import threading
import uuid
from zoneinfo import ZoneInfo
import zipfile

import lab
from replay_evidence import clean


class Kind(StrEnum):
    ANALYTICS = 'analytics'
    ERROR = 'error'
    NETWORK = 'network'
    BACKEND = 'backend'


LOCK = threading.Lock()


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Horário numérico finito obrigatório.')
    return value


def context_rows(path, start, session_id=None, window_map=None):
    """Contrato mínimo explícito: nunca importar payloads, headers ou inputs."""
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Contexto excede 4 MiB.')
    rows = read(path)
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Contexto deve ser uma lista de até 10.000 eventos.')
    result = []
    for i, raw in enumerate(rows):
        kind = Kind(raw['kind'])
        entry = {'id': f'ctx-{i}', 'kind': kind.value, 'summary': clean(raw.get('summary', '')),
                 'source': clean(raw.get('source', 'contexto importado'))}
        for key in ('window', 'session_id', 'request_id', 'trace_id'):
            if raw.get(key):
                value = str(raw[key])
                if not lab.re.fullmatch(r'[A-Za-z0-9:_\-]{1,150}', value):
                    raise ValueError('Identificador de contexto inválido.')
                entry[key] = value
        if window_map and entry.get('window') in window_map:
            entry['source_window'] = entry['window']
            entry['window'] = str(window_map[entry['window']])
        if kind != Kind.BACKEND:
            if session_id and entry.get('session_id') != session_id:
                raise ValueError('Evento não pertence à sessão do pacote.')
            client_ms = number(raw['client_ms'])
            entry.update(client_ms=client_ms, session_s=(client_ms - start) / 1000)
        if 'server_ms' in raw:
            entry['server_ms'] = number(raw['server_ms'])
        if kind == Kind.BACKEND and 'server_ms' not in entry:
            raise ValueError('Log de backend exige server_ms.')
        if raw.get('status') is not None:
            status = raw['status']
            if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
                raise ValueError('Status HTTP inválido.')
            entry['status'] = status
        result.append(entry)
    return result


def locate(frames, session_s, window=None):
    """Não associar uma lacuna ou outra aba ao frame temporalmente mais próximo."""
    number(session_s)
    candidates = [f for f in frames if not window or f['window'] == window]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda f: abs(f['session_s'] - session_s))
    # Um frame cobre somente um intervalo de cadência. Saltos ficam sem imagem.
    intervals = [b['video_s'] - a['video_s'] for a, b in zip(frames, frames[1:])]
    tolerance = (min(intervals) if intervals else 0.1) + 0.005
    return nearest if abs(nearest['session_s'] - session_s) <= tolerance else None


def correlate(anchor, events):
    result = []
    for candidate in events:
        if candidate['id'] == anchor['id']:
            continue
        if anchor.get('session_id') and candidate.get('session_id') and anchor['session_id'] != candidate['session_id']:
            continue
        match = next((key for key in ('trace_id', 'request_id') if anchor.get(key) and candidate.get(key) == anchor[key]), None)
        if match:
            result.append({'method': match, 'approximate': False, 'event': candidate})
        elif (anchor.get('client_ms') is not None and candidate.get('client_ms') is not None
              and anchor.get('window') and anchor['window'] == candidate.get('window')
              and abs(anchor['client_ms'] - candidate['client_ms']) <= 3000):
            result.append({'method': 'client_time_window', 'approximate': True, 'event': candidate})
        elif anchor.get('server_ms') is not None and candidate.get('server_ms') is not None and abs(anchor['server_ms'] - candidate['server_ms']) <= 3000:
            result.append({'method': 'server_time', 'approximate': True, 'event': candidate})
    return result


def bundle(root, name):
    name = lab.valid_name(name)
    folder = root / 'bundles' / name
    manifest = read(folder / 'bundle.json')
    if manifest['name'] != name or manifest['status'] != 'complete':
        raise ValueError('Pacote não publicado.')
    if not lab.published(root, manifest['dataset']):
        raise ValueError('Dataset invalidado.')
    source = read(root / 'datasets' / manifest['dataset'] / 'manifest.json')
    if source['events_sha256'] != manifest['events_sha256']:
        raise ValueError('Pacote desatualizado; eventos mudaram.')
    return folder, manifest


def publish(root, name, dataset, export_folder, context=None):
    name, dataset = lab.valid_name(name), lab.valid_name(dataset)
    source = read(root / 'datasets' / dataset / 'manifest.json')
    exported = read(export_folder / 'export.json')
    if exported['status'] != 'complete' or exported['events_sha256'] != source['events_sha256'] or sha(export_folder / 'clip.mp4') != exported['video_sha256']:
        raise ValueError('Renderização sem integridade válida.')
    session_id = source.get('provenance', {}).get('session_id')
    events = []
    for i, raw in enumerate(source['evidence']):
        summary = clean(raw.get('control') or raw.get('path') or raw.get('state') or '')
        events.append({**raw, 'id': f'rrweb-{i}', 'client_ms': source['start'] + raw['session_s'] * 1000,
                       'summary': summary, 'source': 'rrweb', 'session_id': session_id})
    if context:
        events.extend(context_rows(context, source['start'], session_id, source.get('window_id_map')))
    for event in events:
        frame = locate(exported['frames'], event.get('session_s', -1e30), event.get('window'))
        event['frame_index'] = frame['index'] if frame else None
    events.sort(key=lambda e: (e.get('session_s', float('inf')), e['id']))
    manifest = {**exported, 'name': name, 'dataset': dataset, 'session_id': session_id,
                'session_start_ms': source['start'], 'events': events,
                'context_sha256': sha(context) if context else None,
                'context_imported': bool(context), 'findings': [], 'limits': source['limitations'] + exported['limitations']}
    target = root / 'bundles' / name
    if target != export_folder:
        if export_folder.parent != root / 'packages-staging':
            raise ValueError('Exportação deve usar a pasta final ou staging privado de preparação.')
        target = export_folder
    previous = target / 'bundle.json'
    if previous.is_file():
        old = read(previous)
        if old.get('events_sha256') != manifest['events_sha256'] or old.get('context_sha256') != manifest['context_sha256']:
            raise ValueError('Contexto/eventos de pacote publicado mudaram; escolher outro nome para preservar evidências.')
        manifest['findings'] = old.get('findings', [])
    lab.write_json(target / 'bundle.json', manifest)
    return {'name': name, 'frames': len(manifest['frames']), 'events': len(events)}


def annotate(root, name, input_file):
    folder, manifest = bundle(root, name)
    items = read(input_file)
    if not isinstance(items, list) or len(items) > 50:
        raise ValueError('Até 50 observações por pacote.')
    findings = []
    event_ids = {e['id'] for e in manifest['events']}
    for item in items:
        indices, references = item['frames'], item.get('events', [])
        if (not isinstance(indices, list) or not 1 <= len(indices) <= 10 or any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(manifest['frames']) for i in indices)
                or not isinstance(references, list) or len(references) > 20 or any(e not in event_ids for e in references)):
            raise ValueError('Achado sem referências válidas.')
        for i in indices:
            snapshot(root, name, i)
        findings.append({'observation':clean(item['observation']), 'hypothesis':clean(item.get('hypothesis', '')),
                         'frames':indices, 'events':references})
    manifest['findings'] = findings
    lab.write_json(folder / 'bundle.json', manifest)
    return {'name':name, 'findings':len(findings)}


def snapshot(root, name, index):
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError('Índice inteiro obrigatório.')
    folder, manifest = bundle(root, name)
    if not 0 <= index < len(manifest['frames']):
        raise ValueError('Frame fora do vídeo.')
    if sha(folder / 'clip.mp4') != manifest['video_sha256']:
        raise ValueError('Vídeo corrompido; snapshot recusado.')
    target = folder / 'snapshots' / f'frame-{index:06}.png'
    metadata = target.with_suffix('.json')
    with LOCK:
        if target.is_file() and metadata.is_file() and read(metadata)['sha256'] == sha(target):
            return read(metadata)
        target.parent.mkdir(mode=0o700, exist_ok=True)
        temp = target.with_suffix('.pending.png')
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(folder / 'clip.mp4'),
                        '-vf', f'select=eq(n\\,{index})', '-frames:v', '1', str(temp)],
                       check=True, capture_output=True, timeout=45)
        if not temp.is_file() or temp.stat().st_size == 0:
            raise ValueError('FFmpeg não extraiu o frame pedido.')
        temp.chmod(0o600)
        temp.replace(target)
        proof = {**manifest['frames'][index], 'sha256': sha(target), 'file': target.name,
                 'video_sha256': manifest['video_sha256'], 'reconstructed': True}
        lab.write_json(metadata, proof)
        return proof


def snapshots(root, name, indices):
    """Extrair os frames citados numa única decodificação, com cache por identidade."""
    if not indices:
        return {}
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indices):
        raise ValueError('Índices inteiros obrigatórios.')
    folder, manifest = bundle(root, name)
    if any(not 0 <= index < len(manifest['frames']) for index in indices):
        raise ValueError('Frame fora do vídeo.')
    if sha(folder / 'clip.mp4') != manifest['video_sha256']:
        raise ValueError('Vídeo corrompido.')
    target = folder / 'snapshots'
    target.mkdir(mode=0o700, exist_ok=True)
    result, missing = {}, []
    with LOCK:
        for index in sorted(set(indices)):
            png = target / f'frame-{index:06}.png'
            metadata = png.with_suffix('.json')
            proof = read(metadata) if png.is_file() and metadata.is_file() else None
            if proof and proof.get('video_sha256') == manifest['video_sha256'] and proof.get('sha256') == sha(png) and all(proof.get(key) == value for key, value in manifest['frames'][index].items()):
                result[index] = proof
            else:
                missing.append(index)
        if missing:
            stage = target / f'batch-{uuid.uuid4().hex}'
            stage.mkdir(mode=0o700)
            expression = '+'.join(f'eq(n\\,{index})' for index in missing)
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(folder / 'clip.mp4'),
                '-vf', 'select=' + expression, '-fps_mode', 'passthrough', '-frames:v', str(len(missing)),
                str(stage / 'frame-%06d.png')], check=True, capture_output=True, timeout=120)
            images = sorted(stage.glob('frame-*.png'))
            if len(images) != len(missing) or any(p.stat().st_size == 0 for p in images):
                raise ValueError('Extração dos frames citados incompleta.')
            for index, png in zip(missing, images, strict=True):
                destination = target / f'frame-{index:06}.png'
                png.chmod(0o600); png.replace(destination)
                proof = {**manifest['frames'][index], 'sha256': sha(destination),
                    'file': destination.name, 'video_sha256': manifest['video_sha256'], 'reconstructed': True}
                lab.write_json(destination.with_suffix('.json'), proof)
                result[index] = proof
    return result


def ticket(root, name, index, title='Evidência da sessão'):
    folder, manifest = bundle(root, name)
    number(index)
    if not isinstance(index, int) or not 0 <= index < len(manifest['frames']):
        raise ValueError('Frame inválido.')
    anchor = manifest['frames'][index]
    selected = {index}
    for delta in (-1, 1):
        nearby = locate(manifest['frames'], anchor['session_s'] + delta, anchor['window'])
        if nearby:
            selected.add(nearby['index'])
    cited_findings = [f for f in manifest.get('findings', []) if any(abs(manifest['frames'][i]['session_s'] - anchor['session_s']) <= 3 for i in f['frames'])]
    for finding in cited_findings:
        selected.update(finding['frames'])
    if len(selected) > 30:
        raise ValueError('Ticket excede 30 snapshots; selecionar observações mais específicas.')
    snapshots = [snapshot(root, name, i) for i in sorted(selected)]
    local_events = [e for e in manifest['events'] if e.get('session_s') is not None and abs(e['session_s'] - anchor['session_s']) <= 3 and (not e.get('window') or e['window'] == anchor['window'])]
    cited_ids = {ident for finding in cited_findings for ident in finding['events']}
    local_ids = {event['id'] for event in local_events}
    local_events.extend(e for e in manifest['events'] if e['id'] in cited_ids - local_ids)
    correlated = {e['id']: correlate(e, manifest['events']) for e in local_events}
    stamp = datetime.fromtimestamp(anchor['session_ms'] / 1000, ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M:%S')
    title = clean(title) or 'Evidência da sessão'
    lines = [f'# {title}', '', f"Sessão: {manifest['session_id'] or manifest['dataset']} · aba {anchor['window']}",
             f"Instante: {anchor['session_s']:.3f}s · {stamp} (relógio do cliente, São Paulo)",
             f"Abrir localmente: /investigate?bundle={name}&frame={index}", '', '## Evidências', '']
    for shot in snapshots:
        lines.append(f"![{shot['session_s']:.3f}s · aba {shot['window']}]({shot['file']})")
    lines.extend(['', '## Eventos próximos registrados', ''])
    for event in local_events:
        clock = f"{event['session_s']:.3f}s" if event.get('session_s') is not None else 'relógio do servidor'
        lines.append(f"- {event['id']} · {clock} · {event['kind']} · {event['summary']}")
        for related in correlated[event['id']]:
            lines.append(f"  - Associação {'aproximada' if related['approximate'] else 'por identificador'} ({related['method']}): {related['event']['id']} · {related['event']['summary']}")
    lines.extend(['', '## Hipótese e confirmação', '', 'Causa e resultado de negócio ainda não confirmados por este pacote.', '', '## Limites', '', *[f'- {item}' for item in manifest['limits']]])
    if cited_findings:
        lines.extend(['', '## Observações do investigador com referências', ''])
        for finding in cited_findings:
            lines.append(f"- {finding['observation']} · frames {finding['frames']} · eventos {finding['events']}")
            if finding['hypothesis']:
                lines.append(f"  - Hipótese: {finding['hypothesis']}")
    report_id = uuid.uuid4().hex
    report = folder / 'tickets' / report_id
    report.mkdir(parents=True, mode=0o700)
    markdown = '\n'.join(lines)
    lab.atomic(report / 'ticket.md', markdown)
    proof = {'bundle': name, 'anchor': anchor, 'snapshots': snapshots, 'events': local_events, 'correlations': correlated,
             'findings': cited_findings,
             'context_sha256': manifest.get('context_sha256'),
             'events_sha256': manifest['events_sha256'], 'video_sha256': manifest['video_sha256']}
    lab.write_json(report / 'evidence.json', proof)
    with zipfile.ZipFile(report / 'ticket.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(report / 'ticket.md', 'ticket.md')
        archive.write(report / 'evidence.json', 'evidence.json')
        for shot in snapshots:
            archive.write(folder / 'snapshots' / shot['file'], shot['file'])
    return {'id': report_id, 'markdown': markdown, 'snapshots': snapshots, 'files': ['ticket.md', 'ticket.zip', 'evidence.json']}
