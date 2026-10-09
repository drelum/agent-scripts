#!/usr/bin/env python3
"""Baixar recordings web do PostHog e preparar player rrweb local, somente leitura."""

import argparse
import base64
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

PLAYER_VERSION = "2.1.7"
LOTE = 21          # máximo de blocos por requisição com personal API key; a cota conta requisições, não bytes
RITMO_S = 5        # intervalo entre requisições: 12/min, o burst do plano mais restrito
PRAZO_S = 900      # leituras de snapshots por sessão
MAX_RESPONSE = 64 * 1024 * 1024
SENSITIVE = re.compile(r"(?i)^(?:.*token.*|.*password.*|senha|authorization|cookie|set-cookie|secret|api[_-]?key)$")
URL = re.compile(r"https?://[^\s\"'<>\\)]+")
SECRET_TEXT = re.compile(r"(?i)(?:phx_[\w-]+|eyJ[\w-]+\.[\w-]+\.[\w-]+|Bearer\s+\S+)")


class DownloadError(Exception):
    pass


def origin(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise DownloadError("Host deve ser uma origem HTTPS, sem caminho ou credenciais.")
    return value.rstrip("/")


def credentials(host, project, env=None, home=None):
    """Mesmas fontes públicas do CLI; nunca procurar credenciais de outra pessoa."""
    env = os.environ if env is None else env
    key = env.get("POSTHOG_CLI_API_KEY") or env.get("POSTHOG_CLI_TOKEN")
    ident = env.get("POSTHOG_CLI_PROJECT_ID") or env.get("POSTHOG_CLI_ENV_ID")
    if key or ident:
        if not key or not ident:
            raise DownloadError("Ambiente incompleto: precisa de API_KEY e PROJECT_ID; não combinar fontes.")
        data = {"token": key, "env_id": ident, "host": env.get("POSTHOG_CLI_HOST")}
        provider = "environment"
    else:
        root = Path(env.get("POSTHOG_HOME") or (Path.home() if home is None else home) / ".posthog")
        try:
            data = json.loads((root / "credentials.json").read_text())
        except (OSError, ValueError):
            raise DownloadError("Sem login local utilizável. Execute posthog-cli --host <host> login.") from None
        provider = "cli-login"
    if str(data.get("env_id")) != str(project) or origin(data.get("host") or "https://us.posthog.com") != host:
        raise DownloadError("Host/projeto da credencial diferem do solicitado; conferir login ou ambiente.")
    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        raise DownloadError("Credencial ausente; refazer login individual.")
    return token, provider


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl)[:2] != urllib.parse.urlsplit(req.full_url)[:2]:
            raise DownloadError("Redirect para outra origem recusado; token não encaminhado.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_bounded(response, maximum=MAX_RESPONSE):
    body = response.read(maximum + 1)
    if len(body) > maximum:
        raise DownloadError("Resposta excede limite de bytes; reduzir escopo ou ajustar limite explícito.")
    return body


def lotes(lo, hi):
    return [(a, min(a + LOTE - 1, hi)) for a in range(lo, hi + 1, LOTE)]


class Client:
    """GET de snapshots com ritmo fixo, prazo e contagem de requisições; 429 traz o Retry-After na mensagem."""

    def __init__(self, host, project, token, max_bytes, max_blocks, sleep=time.sleep, clock=time.monotonic):
        self.host, self.project, self.token = host, project, token
        self.max_bytes, self.max_blocks = max_bytes, max_blocks
        self.sleep, self.clock = sleep, clock
        self.requests, self.last = 0, None
        self.nova_sessao()
        self.opener = urllib.request.build_opener(SameOriginRedirect())

    def nova_sessao(self):
        """Orçamento de bytes e prazo valem por sessão; o ritmo entre requisições continua."""
        self.downloaded = 0
        self.limit = self.clock() + PRAZO_S

    def get(self, path):
        if self.last is not None:
            self.sleep(max(0.0, self.last + RITMO_S - self.clock()))
        if self.clock() >= self.limit:
            raise DownloadError(f"Download excedeu {PRAZO_S // 60} minutos; saída incompleta.")
        self.requests += 1
        request = urllib.request.Request(self.host + path, headers={"Authorization": "Bearer " + self.token})
        try:
            with self.opener.open(request, timeout=40) as response:
                body = read_bounded(response, min(MAX_RESPONSE, self.max_bytes - self.downloaded))
        except urllib.error.HTTPError as exc:
            action = {401: "renovar login", 403: "conferir session_recording:read/projeto",
                      404: "gravação ausente ou fora da retenção", 429: "limite de requisições; repetir depois"}
            retry = exc.headers.get("Retry-After", "") if exc.code == 429 and exc.headers else ""
            wait = f" Retry-After: {retry} s." if retry.isdigit() else ""
            raise DownloadError(f"Snapshots: HTTP {exc.code}; {action.get(exc.code, 'leitura falhou')}.{wait}") from None
        except (urllib.error.URLError, TimeoutError):
            raise DownloadError("Snapshots: rede/timeout; download não concluído.") from None
        finally:
            self.last = self.clock()
        self.downloaded += len(body)
        return body

    def cli(self, tool, payload):
        env = dict(os.environ, POSTHOG_CLI_API_KEY=self.token, POSTHOG_CLI_PROJECT_ID=str(self.project), POSTHOG_CLI_HOST=self.host)
        try:
            result = subprocess.run(["posthog-cli", "--host", self.host, "api", "call", "--json", tool,
                                     json.dumps(payload)], env=env, capture_output=True, text=True, timeout=90)
            if result.returncode:
                code = re.search(r"Status Code:\s*(\d{3})", result.stderr + result.stdout)
                if code:
                    status = int(code[1])
                    action = {401: "renovar login", 403: "conferir escopo/projeto",
                              429: "limite de requisições", 503: "PostHog temporariamente ocupado"}
                    raise DownloadError(f"CLI: HTTP {status}; {action.get(status, 'leitura falhou')}. Conteúdo privado omitido.")
                raise DownloadError("CLI: leitura falhou; saída privada omitida.")
            data = json.loads(result.stdout)
            if not isinstance(data, dict) or data.get("isError") or data.get("error"):
                raise DownloadError("CLI retornou erro; conteúdo privado omitido.")
            return data
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            raise DownloadError("CLI ausente, resposta inválida ou timeout; conferir posthog-cli api.") from None

    def sources(self, session):
        base = f"/api/environments/{self.project}/session_recordings/{session}/snapshots"
        path, seen, sources = base + "?blob_v2=true", set(), []
        while path:
            if path in seen:
                raise DownloadError("Paginação de snapshots repetiu cursor.")
            seen.add(path)
            data = json.loads(self.get(path))
            batch = data.get("sources")
            if not isinstance(batch, list):
                raise DownloadError("Resposta de fontes mudou de formato; atualizar leitor.")
            for item in batch:
                if item.get("source") != "blob_v2" or not re.fullmatch(r"\d+", str(item.get("blob_key", ""))):
                    raise DownloadError("Fonte de snapshots não suportada; nenhum fallback aplicado.")
                sources.append({k: item.get(k) for k in ("source", "blob_key", "start_timestamp", "end_timestamp")})
            if len(sources) > self.max_blocks or len(seen) > self.max_blocks:
                raise DownloadError("Limite de blocos/páginas excedido.")
            next_url = data.get("next")
            if next_url:
                target = urllib.parse.urlsplit(urllib.parse.urljoin(self.host + path, next_url))
                if target.scheme + "://" + target.netloc != self.host or target.path.rstrip("/") != base:
                    raise DownloadError("Paginação saiu da origem/gravação solicitada.")
                path = target.path + "?" + target.query
            else:
                path = None
        if len({str(x["blob_key"]) for x in sources}) != len(sources):
            raise DownloadError("Lista de fontes contém chaves repetidas.")
        return sorted(sources, key=lambda x: int(x["blob_key"]))


def unpack(value):
    if not isinstance(value, str):
        return value
    try:
        body = value.encode("latin1")
        if body[:2] != b"\x1f\x8b":
            raise DownloadError("Compressão interna não suportada (gzip esperado); atualizar decodificador.")
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
            return json.loads(read_bounded(stream))
    except (EOFError, OSError, ValueError):
        raise DownloadError("Evento comprimido inválido; download não concluído.") from None


def sanitize(value):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if SENSITIVE.fullmatch(key) or key.lower().startswith("on") and key.lower() in ("onclick", "onload", "onerror"):
                result[key] = "[REDACTED]"
            else:
                result[key] = sanitize(child)
        # Mutações rrweb têm ID/attributes, sem tagName. Redação conservadora.
        if "value" in result.get("attributes", {}):
            result["attributes"]["value"] = "[REDACTED]"
        if str(value.get("tagName", "")).lower() == "textarea":
            result["childNodes"] = []
        if str(value.get("tagName", "")).lower() in ("script", "iframe"):
            result.get("attributes", {}).pop("src", None)
        return result
    if isinstance(value, list):
        return [sanitize(child) for child in value]
    if isinstance(value, str):
        def clean_url(match):
            url = urllib.parse.urlsplit(match.group())
            return urllib.parse.urlunsplit((url.scheme, url.netloc.rsplit("@", 1)[-1], url.path, "", ""))
        return SECRET_TEXT.sub("[REDACTED]", URL.sub(clean_url, value))
    return value


def normalize(body, windows, seen, stats):
    for raw in body.splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if isinstance(row, list) and len(row) == 2:
            window, events = row[0], [row[1]]
        elif isinstance(row, dict):
            window = row.get("windowId", row.get("window_id"))
            events = [row] if "timestamp" in row else row.get("data")
        else:
            raise DownloadError("Linha de snapshots não suportada.")
        if not window or not isinstance(events, list):
            raise DownloadError("Snapshot sem janela/eventos; origem temporal desconhecida.")
        for event in events:
            stats["raw_events"] += 1
            if stats["raw_events"] > 500000:
                raise DownloadError("Limite de eventos excedido.")
            if event.get("cv"):
                data = event["data"]
                if isinstance(data, str):
                    event["data"] = unpack(data)
                else:
                    for field in ("adds", "removes", "texts", "attributes"):
                        if field in data:
                            data[field] = unpack(data[field])
                event.pop("cv", None)
                stats["compressed_events"] += 1
            if event.get("type") == 5 and event.get("data", {}).get("tag") in ("window hidden", "window visible", "$session_idle"):
                # Visibilidade é contexto da jornada; nenhum payload de plugin.
                event["data"] = {"tag": event["data"]["tag"], "payload": {}}
            elif event.get("type") in (5, 6):
                stats["plugin_events_excluded"] += 1
                continue
            if event.get("type") not in (0, 1, 2, 3, 4, 5) or not isinstance(event.get("timestamp"), (int, float)):
                raise DownloadError("Tipo/horário de evento não suportado; revisar leitor.")
            digest = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).digest()
            if digest in seen[str(window)]:
                stats["duplicates"] += 1
                continue
            seen[str(window)].add(digest)
            event = sanitize(event)
            if event.get("type") == 3 and event.get("data", {}).get("source") == 5:
                event["data"]["text"] = "[REDACTED]"
            windows[str(window)].append(event)


def player_assets():
    """Pacote oficial, sem instalação; verificar integridade antes de embutir JS."""
    with urllib.request.urlopen(f"https://registry.npmjs.org/rrweb-player/{PLAYER_VERSION}", timeout=30) as response:
        metadata = json.loads(read_bounded(response))
    expected = metadata["dist"]["integrity"]
    url = f"https://registry.npmjs.org/rrweb-player/-/rrweb-player-{PLAYER_VERSION}.tgz"
    with urllib.request.urlopen(url, timeout=30) as response:
        body = read_bounded(response)
    actual = "sha512-" + base64.b64encode(hashlib.sha512(body).digest()).decode()
    if expected != actual:
        raise DownloadError("Integridade do rrweb-player não confere.")
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as archive:
        js = archive.extractfile("package/dist/rrweb-player.umd.min.cjs").read().decode()
        css = archive.extractfile("package/dist/style.min.css").read().decode()
    return js, css, actual


def player_html(windows, js, css):
    events = json.dumps(windows, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return ('''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gravação local</title><style>body{margin:0;background:#18232e;color:#f4f6f8;font:16px Georgia,serif}header{padding:12px}#player{margin:auto;width:fit-content}''' + css + '''</style>
<header><label>Janela <select id="window"></select></label><span id="status"></span></header><div id="player"></div>
<script>''' + js.replace("</script", "<\\/script") + '''</script><script id="events" type="application/json">''' + events + '''</script><script>
const windows=JSON.parse(document.getElementById('events').textContent);
window.replayErrors=[];window.replayWarnings=[];window.replayReady=false;
window.addEventListener('error',e=>replayErrors.push(e.message));
const warn=console.warn;console.warn=(...args)=>{replayWarnings.push(String(args[0]));warn(...args)};
const selector=document.getElementById('window');
Object.keys(windows).forEach((id,i)=>{const option=document.createElement('option');option.value=id;option.textContent='Janela '+(i+1);selector.append(option)});
function mount(){window.replayReady=false;if(typeof window.player?.getReplayer==='function')window.player.getReplayer().destroy();document.getElementById('player').replaceChildren();
window.player=new rrwebPlayer.Player({target:document.getElementById('player'),props:{events:windows[selector.value],width:Math.min(1280,innerWidth-24),height:Math.min(620,innerHeight-120),autoPlay:false,skipInactive:false,showWarning:true,showController:true}});
window.replayer=player.getReplayer();document.getElementById('status').textContent=' · '+windows[selector.value].length+' eventos';window.replayReady=true;}
selector.onchange=mount;mount();</script></html>''')


def write_private(path, data):
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        stream.write(data)


def download(client, session, output, assets):
    session = str(uuid.UUID(session))
    destination = output / session
    if destination.exists() or destination.is_symlink():
        raise DownloadError("Destino da sessão já existe; escolher uma saída nova.")
    project = client.cli("project-get", {})
    if project.get("id") != client.project:
        raise DownloadError("Projeto ativo do CLI não confere.")
    metadata = client.cli("session-recording-get", {"id": session})
    if metadata.get("found") is False or not metadata.get("start_time"):
        raise DownloadError("Gravação não encontrada; verificar retenção/permissão.")
    if metadata.get("id") != session:
        raise DownloadError("ID retornado nos metadados difere da sessão solicitada.")
    if metadata.get("snapshot_source") not in (None, "web"):
        raise DownloadError("Este leitor reconstrói gravações web; fonte não suportada.")
    before = client.sources(session)
    if not before:
        raise DownloadError("Gravação sem blocos disponíveis; não tratar como sessão saudável.")
    windows, seen, lots = defaultdict(list), defaultdict(set), []
    stats = dict(raw_events=0, compressed_events=0, duplicates=0, plugin_events_excluded=0)
    for a, b in lotes(0, len(before) - 1):
        first, last = before[a]["blob_key"], before[b]["blob_key"]
        path = (f"/api/environments/{client.project}/session_recordings/{session}/snapshots"
                f"?source=blob_v2&start_blob_key={first}&end_blob_key={last}&decompress=true")
        body = client.get(path)
        normalize(body, windows, seen, stats)
        lots.append({"keys": [first, last], "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
    after = client.sources(session)
    for events in windows.values():
        events.sort(key=lambda event: event["timestamp"])
        if not any(event["type"] == 2 for event in events):
            raise DownloadError("Janela sem snapshot completo; player não pode ser validado.")
    if not windows:
        raise DownloadError("Nenhum evento visual suportado.")
    js, css, integrity = assets()
    stable = before == after
    manifest = {"session_id": session, "project_id": client.project, "host": client.host,
                "start_time": metadata["start_time"], "end_time": metadata.get("end_time"),
                "ongoing": metadata.get("ongoing"), "source_list_stable": stable,
                "all_listed_sources_downloaded": True, "capture_completeness": "not_proven",
                "partial": not stable or metadata.get("ongoing") is not False,
                "api_event_count": metadata.get("event_count"), **stats,
                "lots": lots, "sources_before": before, "sources_after": after,
                "player_version": PLAYER_VERSION, "player_integrity": integrity,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "windows": [{"id": ident, "events": len(events), "full_snapshots": sum(e["type"] == 2 for e in events),
                             "first_timestamp_ms": events[0]["timestamp"], "last_timestamp_ms": events[-1]["timestamp"]}
                            for ident, events in windows.items()],
                "limitations": ["Dados sanitizados podem alterar campos visíveis; imagens/estilos externos dependem da rede.",
                                "Fontes estáveis não comprovam captura integral nem revisão visual."]}
    destination.mkdir(mode=0o700, parents=True)
    write_private(destination / "events.json", json.dumps(windows, ensure_ascii=False, separators=(",", ":")))
    write_private(destination / "reproducao.html", player_html(windows, js, css))
    write_private(destination / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return {"session_id": session, "blocks": len(before), "lots": len(lots), "windows": len(windows),
            "normalized_events": sum(len(events) for events in windows.values()), "partial": manifest["partial"]}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_ids", nargs="+", help="IDs das gravações localizadas pelo CLI")
    parser.add_argument("--output", type=Path, required=True, help="Pasta privada, excluída do Git")
    parser.add_argument("--host", default="https://us.posthog.com")
    parser.add_argument("--project-id", type=int, default=331102)
    parser.add_argument("--max-bytes", type=int, default=256 * 1024 * 1024)
    parser.add_argument("--max-blocks", type=int, default=1000)
    args = parser.parse_args()
    try:
        if args.max_bytes < 1 or args.max_blocks < 1 or args.project_id < 1:
            raise DownloadError("Limites/projeto devem ser positivos.")
        host = origin(args.host)
        token, provider = credentials(host, args.project_id)
        print(json.dumps({"credential_provider": provider, "project_id": args.project_id,
                          "transport": "CLI metadata + snapshot REST GET"}), flush=True)
        assets_cache = []
        def assets():
            if not assets_cache:
                assets_cache.append(player_assets())
            return assets_cache[0]
        partial = False
        client = Client(host, args.project_id, token, args.max_bytes, args.max_blocks)
        for session in args.session_ids:
            client.nova_sessao()
            result = download(client, session, args.output, assets)
            partial = partial or result["partial"]
            print(json.dumps(result), flush=True)
        return 2 if partial else 0
    except (DownloadError, ValueError, OSError, KeyError, TypeError) as exc:
        message = str(exc) if isinstance(exc, DownloadError) else "Resposta/arquivo inválido; saída incompleta, conteúdo privado omitido."
        print("replay-download: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
