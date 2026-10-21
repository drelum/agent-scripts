"""Rotas locais: evidências publicadas, streaming e exportação do mesmo vídeo."""
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlsplit

import bundles


def send(handler, value, code=200):
    body = json.dumps(value, ensure_ascii=False).encode()
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.end_headers()
    handler.wfile.write(body)


def file_response(handler, file, mime):
    size = file.stat().st_size
    start, end = 0, size - 1
    requested = handler.headers.get('Range')
    if requested:
        match = re.fullmatch(r'bytes=(\d+)-(\d*)', requested)
        if not match:
            handler.send_error(416)
            return
        start = int(match[1])
        end = min(int(match[2]) if match[2] else end, end)
        if start > end:
            handler.send_error(416)
            return
    handler.send_response(206 if requested else 200)
    handler.send_header('Content-Type', mime)
    handler.send_header('Content-Length', str(end - start + 1))
    handler.send_header('Accept-Ranges', 'bytes')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; media-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'")
    if requested:
        handler.send_header('Content-Range', f'bytes {start}-{end}/{size}')
    handler.end_headers()
    with file.open('rb') as stream:
        stream.seek(start)
        remaining = end - start + 1
        while remaining:
            data = stream.read(min(remaining, 256 * 1024))
            if not data:
                break
            handler.wfile.write(data)
            remaining -= len(data)


def get(handler, root, private):
    parsed = urlsplit(handler.path)
    path = unquote(parsed.path)
    try:
        if path in ('/', '/investigate', '/investigator.js'):
            is_page = path != '/investigator.js'
            file = root / 'investigate.html' if is_page else private / 'investigator.js'
            file_response(handler, file, 'text/html; charset=utf-8' if is_page else 'text/javascript; charset=utf-8')
        elif path == '/api/bundles':
            result = []
            for file in sorted((private / 'bundles').glob('*/bundle.json')):
                try:
                    _, item = bundles.bundle(private, file.parent.name)
                    result.append({'name': item['name']})
                except ValueError:
                    continue
            send(handler, result)
        elif match := re.fullmatch(r'/api/bundles/([a-z0-9-]+)(/context)?', path):
            _, manifest = bundles.bundle(private, match[1])
            if match[2]:
                event_id = parse_qs(parsed.query).get('event', [''])[0]
                event = next(e for e in manifest['events'] if e['id'] == event_id)
                send(handler, {'event': event, 'related': bundles.correlate(event, manifest['events'])})
            else:
                send(handler, manifest)
        elif match := re.fullmatch(r'/bundles/([a-z0-9-]+)/(clip\.mp4|snapshots/frame-\d{6}\.(?:png|json)|tickets/[a-f0-9]{32}/(?:ticket\.md|ticket\.zip|evidence\.json))', path):
            folder, _ = bundles.bundle(private, match[1])
            file = folder / match[2]
            if not file.is_file():
                raise ValueError('Arquivo indisponível.')
            mime = {'.mp4':'video/mp4', '.png':'image/png', '.json':'application/json', '.md':'text/plain; charset=utf-8', '.zip':'application/zip'}[file.suffix]
            file_response(handler, file, mime)
        else:
            return False
    except (ValueError, OSError, KeyError, StopIteration):
        handler.send_error(404)
    return True


def post(handler, private):
    match = re.fullmatch(r'/api/bundles/([a-z0-9-]+)/(snapshot|ticket)', urlsplit(handler.path).path)
    if not match:
        handler.send_error(404)
        return
    origin = handler.headers.get('Origin')
    if (origin and urlsplit(origin).netloc != handler.headers.get('Host')) or handler.headers.get('Content-Type') != 'application/json':
        handler.send_error(403)
        return
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 8192:
            raise ValueError('Corpo inválido.')
        body = json.loads(handler.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError('Objeto obrigatório.')
        if match[2] == 'snapshot':
            result = bundles.snapshot(private, match[1], body['index'])
        else:
            result = bundles.ticket(private, match[1], body['index'], body.get('title', 'Evidência da sessão'))
        send(handler, result)
    except (ValueError, OSError, KeyError, TypeError, bundles.subprocess.SubprocessError):
        send(handler, {'error':'Evidência indisponível; pacote não alterado.'}, 400)
