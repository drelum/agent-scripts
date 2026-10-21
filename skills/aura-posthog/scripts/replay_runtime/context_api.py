"""Contexto mínimo via posthog-cli; propriedades brutas existem somente em memória."""
from datetime import datetime, timezone
import json
import os
import re
import subprocess

import lab
from replay_evidence import clean


def fetch(args, manifest):
    session = manifest['provenance']['session_id']
    key, _ = lab.download.credentials(args.host, args.project)
    client = lab.download.Client(args.host, args.project, key, 128 * 1024 * 1024, 100)
    if client.cli('project-get', {}).get('id') != args.project:
        raise ValueError('Projeto ativo não confere para o contexto.')
    # Confirmar o contrato do CLI no ambiente ativo antes das chamadas.
    for tool in ('execute-sql', 'read-data-schema'):
        subprocess.run(['posthog-cli', 'api', 'info', tool], check=True, capture_output=True, timeout=90)
    schema = client.cli('execute-sql', {'query': "SELECT column_name FROM system.information_schema.columns WHERE table_name = 'events' AND column_name IN ('uuid','event','properties','timestamp')", 'context':'Descobrir colunas para pacote local.'})
    columns = set(schema['results'].splitlines()[1:])
    if columns != {'uuid','event','properties','timestamp'}:
        raise ValueError('Esquema events incompatível.')
    env = dict(os.environ, POSTHOG_CLI_API_KEY=key, POSTHOG_CLI_PROJECT_ID=str(args.project), POSTHOG_CLI_HOST=args.host)
    discovered = subprocess.run(['posthog-cli','--host',args.host,'api','call','--json','read-data-schema',json.dumps({'query':{'kind':'events','limit':500}})], env=env, capture_output=True, text=True, timeout=90, check=True)
    names = set(re.findall(r'`([^`]+)`', str(json.loads(discovered.stdout))))
    client_from = manifest['start'] + max(0, args.start - 3) * 1000
    client_to = manifest['start'] + (args.start + args.duration + 3) * 1000
    active = sorted(name for name in names if re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*', name))
    if not active:
        raise ValueError('Nenhum evento descoberto para o contexto.')
    event_filter = ','.join("'" + name + "'" for name in active)
    profile = client.cli('execute-sql', {'query':f"SELECT properties FROM events WHERE timestamp >= fromUnixTimestamp64Milli({int(client_from - 86400000)}) AND timestamp <= fromUnixTimestamp64Milli({int(client_to + 86400000)}) AND event IN ({event_filter}) ORDER BY timestamp DESC LIMIT 20", 'context':'Confirmar propriedades de sessão e relógio antes de filtrar o contexto.','truncate':False})
    samples = [json.loads(line) for line in profile['results'].splitlines()[1:] if line.strip() and line.lstrip().startswith('{')]
    if not any(isinstance(sample, dict) and all(field in sample for field in ('$session_id','$window_id','$time')) for sample in samples):
        raise ValueError('Propriedades de sessão/relógio não confirmadas; contexto não importado.')
    # Filtro temporal de servidor amplo; o recorte é pelo relógio do cliente, sem supor sincronismo.
    query = (f"SELECT uuid, event, toUnixTimestamp64Milli(timestamp) AS server_ms, properties FROM events "
             f"WHERE timestamp >= fromUnixTimestamp64Milli({int(client_from - 86400000)}) "
             f"AND timestamp <= fromUnixTimestamp64Milli({int(client_to + 86400000)}) "
             f"AND properties.$session_id = '{session}' "
             f"AND toFloat(properties.$time) >= {client_from / 1000} AND toFloat(properties.$time) <= {client_to / 1000} "
             "ORDER BY timestamp LIMIT 200")
    result = client.cli('execute-sql', {'query':query,'context':'Contexto read-only em torno do recorte local; sem dados pessoais no artefato.','truncate':False})
    rows = []
    for line in result['results'].splitlines()[1:]:
        ident, event, server_ms, encoded = line.split('|', 3)
        if event not in names:
            continue
        props = json.loads(encoded)
        if not all(key in props for key in ('$session_id','$time','$window_id')):
            continue
        # Conferência do grão antes de publicar; nunca importar outro usuário/sessão.
        if props['$session_id'] != session:
            raise ValueError('Contexto retornou outra sessão.')
        row = {'kind':'error' if event == '$exception' or event.endswith('_failed') else 'analytics',
               'source':f'PostHog / {event}', 'session_id':session, 'window':props['$window_id'],
               'client_ms':float(props['$time']) * 1000, 'server_ms':int(server_ms), 'summary':clean(event)}
        status = props.get('http_status')
        if isinstance(status, (int, float)) and 100 <= status <= 599:
            row['status'] = int(status)
            row['summary'] += f' · HTTP {int(status)}'
        for field in ('request_id','trace_id'):
            if props.get(field) and re.fullmatch(r'[A-Za-z0-9:_\-]{1,150}', str(props[field])):
                row[field] = str(props[field])
        rows.append(row)
    file = lab.PRIVATE / 'datasets' / args.dataset / 'context.json'
    lab.write_json(file, rows)
    return file, {'rows':len(rows), 'possibly_truncated':len(result['results'].splitlines()) - 1 >= 200,
                  'fetched_at':datetime.now(timezone.utc).isoformat()}
