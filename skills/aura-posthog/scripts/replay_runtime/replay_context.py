"""Contexto auxiliar do replay, sem DOM, headers ou valores de busca.

Adaptado dos contratos navigation.py/network_capture.py do PostHog f65db4f.
O decoder upstream permanece intacto. Captura ausente/parcial nunca vira rede limpa.
"""
from enum import StrEnum
import json
import re
from urllib.parse import urlsplit, urlunsplit


class NetworkState(StrEnum):
    AVAILABLE = 'available'
    NONE = 'none'


def safe_url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value) or '`' in value:
        return ''
    try:
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or not url.hostname:
            return ''
        host = url.hostname
        if ':' in host:
            host = f'[{host}]'
        authority = host + (f':{url.port}' if url.port else '')
        path = re.sub(r'(?i)(phx_[\w-]+|eyJ[\w.-]+|[^/]*@[^/]*)', '[REDACTED]', url.path)
        return urlunsplit((url.scheme, authority, path, '', ''))[:200]
    except ValueError:
        return ''


def integer(value):
    if isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError, OverflowError):
        return None


class NetworkCollector:
    def __init__(self):
        self.requests = []
        self.captured = False
        self.truncated = False
        self.unknown_outcomes = False

    def feed(self, event, window):
        if event.get('type') != 6:
            return
        data = event.get('data', {})
        plugin, payload = data.get('plugin'), data.get('payload')
        if plugin not in ('posthog/network@1', 'rrweb/network@1'):
            return
        self.captured = True
        if not isinstance(payload, dict):
            self.unknown_outcomes = True
            return
        requests = [payload] if plugin == 'posthog/network@1' else payload.get('requests')
        if not isinstance(requests, list):
            self.unknown_outcomes = True
            return
        for raw in requests:
            if not isinstance(raw, dict):
                self.unknown_outcomes = True
                continue
            url = safe_url(raw.get('name') or raw.get('url') or raw.get('2'))
            status = integer(raw.get('status', raw.get('responseStatus', raw.get('21'))))
            if 'status' not in raw and status == 0 and 'method' not in raw:
                status = None  # PerformanceObserver 0 pode esconder status cross-origin.
            duration = integer(raw.get('duration', raw.get('39')))
            # SDK: timestamp individual ou timeOrigin + startTime; o envelope pode vir em lote.
            stamp = integer(raw.get('timestamp', raw.get('40')))
            if stamp is None:
                origin = integer(raw.get('timeOrigin', raw.get('1')))
                start = integer(raw.get('startTime', raw.get('3')))
                stamp = origin + start if origin is not None and start is not None else None
            if status is None or not url or stamp is None:
                self.unknown_outcomes = True
            interesting = status is not None and (status == 0 or status >= 400)
            if not interesting and (duration is None or duration < 1000):
                continue
            if not url:
                continue
            if len(self.requests) >= 500:
                self.truncated = True
                continue
            method = raw.get('method')
            method = method.upper() if isinstance(method, str) else None
            if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'):
                method = None
            self.requests.append({'id': f'network-{len(self.requests)}', 'client_ms': stamp,
                'window': str(window), 'url': url, 'method': method, 'status': status, 'duration_ms': duration})

    def finish(self):
        return {'requests': sorted(self.requests, key=lambda row: row['client_ms'] if row['client_ms'] is not None else float('inf')),
                'captured': self.captured, 'truncated': self.truncated,
                'unknown_outcomes': self.unknown_outcomes,
                'partial': True,
                'limitation': 'Metadados dos plugins recebidos; não comprova captura de toda a rede do navegador.'}


def network_rows(source, manifest, first, end, fps):
    frames = manifest['frames']
    rows = []
    by_window = {}
    from bisect import bisect_left
    for index in range(first, end):
        frame = frames[index]
        if frame.get('visual_state') != 'missing_recording':
            by_window.setdefault(frame['window'], []).append(frame)
    clocks = {key: [frame['session_ms'] for frame in values] for key, values in by_window.items()}
    payload = source.get('network', {})
    for request in payload.get('requests', []):
        window = request['window']
        if window not in clocks or request['client_ms'] is None:
            continue
        index = bisect_left(clocks[window], request['client_ms'])
        candidates = by_window[window][max(0, index - 1):index + 1]
        near = min(candidates, key=lambda frame: abs(frame['session_ms'] - request['client_ms']))
        if abs(near['session_ms'] - request['client_ms']) > 1000 / fps + 5:
            continue
        rows.append({**request, 'source': 'rrweb network plugin', 'event': 'network',
            'vid_t': (near['index'] - first) / fps, 'url': safe_url(request['url']),
            'clock': 'client, nearest observed frame'})
    state = NetworkState.AVAILABLE if rows else NetworkState.NONE
    return rows, {**{key: value for key, value in payload.items() if key != 'requests'},
                  'state': state, 'mapped_requests': len(rows),
                  'unmapped_requests': len(payload.get('requests', [])) - len(rows),
                  'note': 'Somente falhas/lentidão capturadas; resultado vazio não prova ausência de falha.'}


def navigation(frames, first, end, fps):
    """Só a aba efetivamente exibida; estado desconhecido encerra a visita anterior."""
    entries, last, seen = [], None, set()
    for index in range(first, end):
        frame = frames[index]
        url = safe_url(frame.get('url'))
        key = (frame['window'], url) if frame.get('visual_state') != 'missing_recording' and url else None
        if key == last:
            continue
        t = (index - first) / fps
        if entries and entries[-1]['end_t'] is None:
            entries[-1]['end_t'] = t
        last = key
        if key is None:
            continue
        entries.append({'vid_t': t, 'end_t': None, 'tab': frame['window'], 'url': url,
                        'new_window': bool(seen) and frame['window'] not in seen})
        seen.add(frame['window'])
    return entries[:100], max(0, len(entries) - 100)


def chapter_target(duration):
    return max(3, min(20, round(duration / 90)))


def event_descriptions(rows, path):
    taxonomy = json.loads(path.read_text())
    descriptions = taxonomy['events']
    return {name: descriptions.get(name, 'Sem definição verificada; o nome isolado não comprova ação, resultado ou persistência.')
            for name in dict.fromkeys(row['event'] for row in rows if row.get('event'))}, taxonomy
