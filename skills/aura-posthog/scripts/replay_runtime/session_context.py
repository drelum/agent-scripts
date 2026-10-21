"""Contexto paginado e sanitizado de uma sessão; nenhum julgamento por LLM."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
import base64
import binascii
import json
import math
import os
import re
import statistics
import subprocess

import lab
from replay_evidence import clean

PAGE = 500
MAX_PAGES = 200
FIELDS = (
    'http_status', 'status_code', 'error_type', 'error_code', 'failure_reason',
    'operation', 'operation_title', 'source', 'result_count', 'item_count',
    'request_id', 'trace_id', 'span_id', 'app_version', '$lib',
    '$exception_issue_id', '$exception_handled', 'cart_id', 'order_id',
    'product_id', 'ean', 'quantity', 'store_id', 'user_role',
)
SPAN_FIELDS = ('sessionId', 'http.response.status_code', 'http.request.method',
               'http.route', 'exception.type', 'exception.message')
EVENT_COLUMNS = {'uuid', 'event', 'properties', 'timestamp'}
SPAN_COLUMNS = {'uuid', 'trace_id', 'span_id', 'parent_span_id', 'name',
                'timestamp', 'duration_nano', 'status_code', 'service_name', 'attributes'}


class Category(StrEnum):
    NAVIGATION = 'navigation'
    IDENTITY = 'identity_context'
    PERFORMANCE = 'performance'
    LIFECYCLE = 'lifecycle'
    ACTION = 'product_action'
    EXCEPTION = 'exception'
    FAILURE = 'business_failure'


def category(name):
    if name == '$exception':
        return Category.EXCEPTION
    if name.endswith('_failed'):
        return Category.FAILURE
    if name in ('$pageview', '$pageleave'):
        return Category.NAVIGATION
    if name in ('$identify', '$set', '$groupidentify'):
        return Category.IDENTITY
    if name == '$web_vitals':
        return Category.PERFORMANCE
    if name.startswith('$session'):
        return Category.LIFECYCLE
    return Category.ACTION


def scalar(value):
    if isinstance(value, str):
        return diagnostic_text(value)
    if isinstance(value, (int, float, bool)) and (not isinstance(value, float) or math.isfinite(value)):
        return value
    return None


def identifier(value, size):
    text = str(value or '')
    if re.fullmatch(rf'[0-9a-fA-F]{{{size}}}', text):
        return text.lower() if text.strip('0') else None
    try:
        decoded = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error):
        return None
    return decoded.hex() if len(decoded) == size // 2 and any(decoded) else None


def diagnostic_text(value):
    """Corpos estruturados viram apenas diagnóstico, sem copiar headers/payload/inputs."""
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else str(value)
    if '{' in text or '[' in text:
        try:
            parsed = json.loads(text)
        except ValueError:
            # Texto com JSON embutido não é um formato seguro de diagnóstico exportável.
            return '[Conteúdo estruturado omitido]'
        if isinstance(parsed, dict):
            allowed = ('message', 'msg', 'type', 'code', 'level', 'severity', 'logger', 'exception', 'error')
            safe = {key: diagnostic_text(item) for key, item in parsed.items()
                    if key in allowed and isinstance(item, (str, int, float, bool, dict))}
            return clean(json.dumps(safe, ensure_ascii=False)) if safe else '[Conteúdo estruturado omitido]'
        return '[Conteúdo estruturado omitido]'
    if re.search(r'(?i)\b(headers?|payload|inputs?|search_text|request_body|response_body)\s*[:=]', text):
        return '[Conteúdo estruturado omitido]'
    # Authorization pode ter Basic/Bearer/Digest e múltiplos parâmetros: excluir a linha inteira.
    text = re.sub(r'(?i)\b(authorization|cookie)\s*[:=]\s*[^\r\n]*', r'\1=[REDIGIDO]', text)
    text = re.sub(r'''(?i)\b(api[_-]?key|secret|token|password|senha)\s*[:=]\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\S+)''', r'\1=[REDIGIDO]', text)
    return clean(text)


def sql(client, query):
    result = client.cli('execute-sql', {'query': query, 'truncate': False,
                        'context': 'Preparação determinística read-only; contexto sanitizado da sessão.'})
    if not isinstance(result.get('results'), str):
        raise ValueError('Contrato SQL inesperado; pacote não publicado.')
    return result['results'].splitlines()[1:]


def discover(client, service):
    """Uma descoberta por lote, reutilizada por todas as sessões."""
    def contract(tool):
        return subprocess.run(['posthog-cli', 'api', 'info', '--json', tool], check=True,
                              capture_output=True, timeout=90)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(contract, tool) for tool in ('query-session-recordings-list', 'execute-sql',
            'read-data-schema', 'query-logs', 'logs-count', 'logs-attributes-list', 'logs-attribute-values-list')]
        for future in futures:
            future.result()
    columns = sql(client, "SELECT table_name,column_name FROM system.information_schema.columns "
                  "WHERE table_name IN ('events','posthog.trace_spans')")
    tables = {}
    for line in columns:
        table, column = line.split('|', 1)
        tables.setdefault(table, set()).add(column)
    if not EVENT_COLUMNS <= tables.get('events', set()):
        raise ValueError('Esquema events incompatível.')
    catalog = read_schema(client, {'kind': 'events', 'limit': 500})
    names = re.findall(r'`([^`]+)`', json.dumps(catalog))
    if not names:
        raise ValueError('Catálogo de eventos vazio.')
    # O filtro por sessão precisa de uma propriedade confirmada, não de uma suposição do SDK.
    reference = '$pageview' if '$pageview' in names else names[0]
    props = read_schema(client, {'kind': 'event_properties', 'event_name': reference})
    # O catálogo omite propriedades internas de transporte ($session_id/$time/$window_id).
    # Descobrir suas chaves efetivamente presentes, sem consultar ou salvar valores pessoais.
    if not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*', reference):
        raise ValueError('Nome de evento de referência inválido.')
    transport_keys = sql(client, "SELECT DISTINCT arrayJoin(JSONExtractKeys(properties)) "
                         f"FROM events WHERE timestamp >= now() - INTERVAL 7 DAY AND event = '{reference}' LIMIT 500")
    if '$session_id' not in transport_keys and '$session_id' not in json.dumps(props):
        raise ValueError('Propriedade de sessão não confirmada nos dados.')
    period = {'date_from': '-7d'}
    services = client.cli('logs-attribute-values-list',
                         {'key': 'service.name', 'attribute_type': 'resource', 'dateRange': period})
    resources = client.cli('logs-attributes-list', {'attribute_type': 'resource', 'dateRange': period})
    attributes = client.cli('logs-attributes-list',
                            {'attribute_type': 'log', 'keys': 'sessionId', 'serviceNames': [service], 'dateRange': period})
    logs_available = (service in {row.get('name') for row in services.get('results', [])}
                      and 'service.name' in {row.get('name') for row in resources.get('results', [])}
                      and 'sessionId' in {row.get('name') for row in attributes.get('results', [])})
    spans_available = SPAN_COLUMNS <= tables.get('posthog.trace_spans', set())
    if spans_available:
        keys = sql(client, "SELECT DISTINCT arrayJoin(JSONExtractKeys(toJSONString(attributes))) "
                   "FROM posthog.trace_spans WHERE timestamp >= now() - INTERVAL 7 DAY LIMIT 500")
        spans_available = 'sessionId' in keys
    return {'logs_available': logs_available, 'spans_available': spans_available, 'service': service}


def read_schema(client, query):
    # Esta ferramenta retorna Markdown/JSON string, diferente das respostas dict de dados.
    env = dict(os.environ, POSTHOG_CLI_API_KEY=client.token, POSTHOG_CLI_PROJECT_ID=str(client.project), POSTHOG_CLI_HOST=client.host)
    result = subprocess.run(['posthog-cli', '--host', client.host, 'api', 'call', '--json',
                             'read-data-schema', json.dumps({'query': query})],
                            env=env, check=True, capture_output=True, text=True, timeout=90)
    data = json.loads(result.stdout)
    if isinstance(data, dict) and (data.get('isError') or data.get('error')):
        raise ValueError('Descoberta de esquema recusada; saída privada omitida.')
    return data


def period_for(session, events=()):
    bounds = [datetime.fromisoformat(session[key]).timestamp() * 1000 for key in ('start_time', 'end_time')]
    bounds.extend(e['server_ms'] for e in events)
    return {key: datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
            for key, value in zip(('date_from', 'date_to'), (min(bounds) - 300000, max(bounds) + 300000))}


def time_filter(period):
    # Reconstrução ISO após parsing; nenhum literal SQL vem diretamente do usuário.
    dates = [datetime.fromisoformat(period[key]).isoformat() for key in ('date_from', 'date_to')]
    return f"timestamp >= toDateTime('{dates[0]}') AND timestamp <= toDateTime('{dates[1]}')"


def paginate(client, select, where, order, cursor):
    rows, seen, previous = [], set(), None
    for _ in range(MAX_PAGES):
        condition = where + (f' AND ({cursor(previous)})' if previous is not None else '')
        page = sql(client, f'SELECT {select} WHERE {condition} ORDER BY {order} LIMIT {PAGE}')
        for encoded in page:
            key = encoded.split('|', 1)[0]
            if key in seen:
                raise ValueError('Paginação repetiu identificador; cobertura inválida.')
            seen.add(key)
            rows.append(encoded)
        if len(page) < PAGE:
            return rows
        previous = page[-1]
    raise ValueError('Limite de paginação atingido; não declarar contexto completo.')


def collect_events(client, session, source):
    session_id = session['id']
    # Margem de um dia para desvio de relógio do cliente; registrada no manifesto de cobertura.
    start = datetime.fromisoformat(session['start_time']) - timedelta(days=1)
    end = datetime.fromisoformat(session['end_time']) + timedelta(days=1)
    period = {'date_from': start.isoformat(), 'date_to': end.isoformat()}
    where = f"{time_filter(period)} AND properties.$session_id = '{session_id}'"
    count = int(sql(client, f'SELECT count() FROM events WHERE {where}')[0])
    def cursor(previous):
        ident, _, ms, _ = previous.split('|', 3)
        import uuid
        ident = str(uuid.UUID(ident))
        return f"toUnixTimestamp64Milli(timestamp) > {int(ms)} OR (toUnixTimestamp64Milli(timestamp) = {int(ms)} AND uuid > '{ident}')"
    lines = paginate(client, 'uuid,event,toUnixTimestamp64Milli(timestamp),properties FROM events',
                     where, 'toUnixTimestamp64Milli(timestamp),uuid', cursor)
    after_count = int(sql(client, f'SELECT count() FROM events WHERE {where}')[0])
    if count != len(lines) or after_count != count:
        raise ValueError('Eventos mudaram durante coleta; pacote não publicado.')
    rows, offsets = [], []
    for line in lines:
        ident, name, server, encoded = line.split('|', 3)
        props = json.loads(encoded)
        if props.get('$session_id') != session_id:
            raise ValueError('Evento de outra sessão.')
        client_time = props.get('$time')
        client_ms = float(client_time) * 1000 if isinstance(client_time, (int, float)) and not isinstance(client_time, bool) and math.isfinite(client_time) else None
        row = {'id': ident, 'event': clean(name), 'category': category(name).value,
               'kind': 'error' if category(name) in (Category.EXCEPTION, Category.FAILURE) else 'analytics',
               'session_id': session_id, 'server_ms': int(server), 'client_ms': client_ms,
               'source': 'PostHog events', 'summary': clean(name), 'window': props.get('$window_id'),
               'pathname': clean(str(props.get('$pathname', '')).split('?')[0].split('#')[0]),
               'properties': {key: scalar(props[key]) for key in FIELDS if key in props and scalar(props[key]) is not None},
               'omitted_property_names': sorted(key for key in props if key not in FIELDS and key not in ('$time', '$window_id', '$session_id', '$pathname', '$exception_list'))}
        row['exceptions'] = []
        for key in ('request_id', 'trace_id', 'span_id'):
            if props.get(key) and re.fullmatch(r'[A-Za-z0-9:_\-]{1,150}', str(props[key])):
                row[key] = str(props[key])
        for exc in props.get('$exception_list', []) or []:
            if isinstance(exc, dict):
                # Stack preservado sem variáveis, valores locais, headers ou payload.
                stack = exc.get('stacktrace', {}).get('frames', []) if isinstance(exc.get('stacktrace'), dict) else []
                row['exceptions'].append({'type': diagnostic_text(exc.get('type', '')), 'value': diagnostic_text(exc.get('value', '')),
                    'frames': [{key: scalar(frame[key]) for key in ('filename', 'function', 'lineno', 'colno', 'in_app') if key in frame and scalar(frame[key]) is not None} for frame in stack if isinstance(frame, dict)]})
        for key in ('$exception_types', '$exception_values'):
            values = props.get(key)
            if isinstance(values, list):
                row[key] = [diagnostic_text(value) for value in values]
        details = [row['summary']]
        if props.get('operation_title') or props.get('operation'):
            details.append(clean(props.get('operation_title') or props['operation']))
        if props.get('http_status') is not None:
            details.append(f'HTTP {scalar(props["http_status"])}')
        details.extend(exc['value'] for exc in row['exceptions'] if exc['value'])
        row['summary'] = ' · '.join(details)
        if client_ms is not None:
            row['session_s'] = (client_ms - source['start']) / 1000
        else:
            row['session_s'] = None
        if client_ms is not None and name == '$pageview':
            offsets.append(int(server) - client_ms)
        rows.append(row)
    clock = {'samples': len(offsets), 'offset_ms': statistics.median(offsets) if offsets else None,
             'spread_ms': max(offsets) - min(offsets) if offsets else None}
    clock['usable_for_approximation'] = len(offsets) >= 2 and clock['spread_ms'] <= 500
    return rows, {'status': 'exhausted', 'rows': len(rows), 'period': period, 'clock': clock,
                  'properties': 'diagnostic_allowlist; omitted names retained; secrets/input values excluded'}


def collect_logs(client, session, events, capability):
    if not capability['logs_available']:
        return [], {'status': 'unavailable', 'reason': 'service/session attribute not discovered'}
    period = period_for(session, events)
    base = {'serviceNames': [capability['service']], 'dateRange': period,
            'filterGroup': [{'key': 'sessionId', 'type': 'log_attribute', 'operator': 'exact', 'value': session['id']}]}
    count = client.cli('logs-count', {'query': base}).get('count')
    if not isinstance(count, int) or count < 0:
        raise ValueError('Contagem de logs inválida.')
    rows, cursor, seen = [], None, set()
    if count:
        for _ in range(MAX_PAGES):
            query = {**base, 'sessionId': session['id'], 'limit': 1000, 'orderBy': 'earliest'}
            if cursor:
                query['after'] = cursor
            result = client.cli('query-logs', {'query': query})
            entries = result.get('results')
            if not isinstance(entries, list):
                raise ValueError('Formato de logs inesperado.')
            for entry in entries:
                attrs = entry.get('attributes', {})
                if attrs.get('sessionId') != session['id']:
                    raise ValueError('Log sem correlação explícita da sessão.')
                ident = entry.get('uuid')
                if not ident or ident in seen:
                    raise ValueError('Log sem identificador único.')
                seen.add(ident)
                rows.append({'id': ident, 'kind': 'backend', 'session_id': session['id'],
                    'timestamp': entry.get('timestamp'), 'severity_text': clean(entry.get('severity_text', '')),
                    'service_name': clean(entry.get('service_name', capability['service'])),
                    'body': diagnostic_text(entry.get('body', entry.get('message', ''))),
                    'trace_id': identifier(entry.get('trace_id'), 32), 'span_id': identifier(entry.get('span_id'), 16),
                    'attributes': {key: scalar(value) for key, value in attrs.items() if key in SPAN_FIELDS and scalar(value) is not None}})
            next_cursor = result.get('nextCursor') or result.get('next_cursor') or result.get('next')
            if not next_cursor:
                break
            if next_cursor == cursor:
                raise ValueError('Cursor de logs repetido.')
            cursor = next_cursor
        else:
            raise ValueError('Limite de paginação de logs atingido.')
        after_count = client.cli('logs-count', {'query': base}).get('count')
        if after_count != count or len(rows) != count:
            raise ValueError('Logs mudaram ou paginação incompleta.')
    return rows, {'status': 'exhausted', 'rows': len(rows), 'period': period, 'service': capability['service']}


def collect_spans(client, session, events, capability):
    if not capability['spans_available']:
        return [], {'status': 'unavailable', 'reason': 'trace table/session attribute not discovered'}
    period = period_for(session, events)
    # IDs armazenados como Base64; preservar a chave original no filtro e exportar W3C hexadecimal.
    select = 'uuid,trace_id,span_id,parent_span_id,name,toUnixTimestamp64Milli(timestamp),duration_nano,status_code,service_name,toJSONString(attributes) FROM posthog.trace_spans'
    def cursor(previous):
        import uuid
        return f"uuid > '{uuid.UUID(previous.split('|', 1)[0])}'"
    tagged = paginate(client, select, f"{time_filter(period)} AND attributes.sessionId = '{session['id']}'", 'uuid', cursor)
    traces = sorted({line.split('|', 2)[1] for line in tagged})
    if any(identifier(trace, 32) is None for trace in traces):
        raise ValueError('Trace de sessão inválido.')
    expanded = []
    for offset in range(0, len(traces), 100):
        ids = ','.join("'" + trace + "'" for trace in traces[offset:offset + 100])
        # Filhos podem estar em outro serviço, sem sessionId e fora do intervalo do root.
        expanded.extend(paginate(client, select, f"{time_filter(period)} AND trace_id IN ({ids})", 'uuid', cursor))
    rows = []
    for encoded in expanded:
        ident, trace, span, parent, name, stamp, duration, status, service, attrs_json = encoded.split('|', 9)
        attrs = json.loads(attrs_json)
        normalized_trace, normalized_span = identifier(trace, 32), identifier(span, 16)
        if not normalized_trace or not normalized_span:
            raise ValueError('Identificador de span inválido.')
        rows.append({'id': ident, 'trace_id': normalized_trace, 'span_id': normalized_span, 'parent_span_id': identifier(parent, 16),
            'name': clean(name), 'server_ms': int(stamp), 'duration_nano': int(duration), 'status_code': int(status),
            'service_name': clean(service), 'session_id': session['id'],
            'correlation': 'session_attribute' if attrs.get('sessionId') == session['id'] else 'confirmed_trace_child',
            'attributes': {key: scalar(value) for key, value in attrs.items() if key in SPAN_FIELDS and scalar(value) is not None}})
    return rows, {'status': 'exhausted', 'rows': len(rows), 'session_tagged_spans': len(tagged),
                  'traces': len(traces), 'period': period, 'scope': 'session roots plus all services in confirmed traces within period'}
