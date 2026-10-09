#!/usr/bin/env python3
"""Reconstruir a gravação de um erro e preparar o laboratório local para investigação com agent-browser.

Somente leitura. Baixa os blocos em lotes de 21 (máximo por requisição) para um cache local e monta
`lab_T<de>_T<ate>.html` para um intervalo em volta do erro, começando no snapshot completo anterior, com relógio
relativo ao erro e a API `window.lab`. Outro intervalo reaproveita o cache, sem nova requisição.
"""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
from zoneinfo import ZoneInfo

import replay_download as rd
from replay_evidence import analyze_window

DE_S, ATE_S = -300, 120    # intervalo padrão do laboratório; a sessão inteira pesa centenas de MB no player
LACUNA_MS = 30_000          # intervalo sem eventos que o laboratório sinaliza
TOCAR_MAX_S = 20            # reprodução contínua por chamada de `lab.tocar`
AQUECIMENTO_MS = 2000       # `lab.ir` reproduz esse trecho antes do alvo para animações CSS terminarem
SP = ZoneInfo("America/Sao_Paulo")


class Modo:
    INTEIRA = "inteira"
    BANDA = "banda"


def parse_at(text):
    """Epoch em ms, ou ISO 8601; ISO sem fuso é horário de São Paulo."""
    text = str(text).strip()
    if text.isdigit():
        value = int(text)
        if value < 10**12:
            raise rd.DownloadError("Epoch deve estar em milissegundos.")
        return value
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise rd.DownloadError("Horário do erro inválido; usar ISO 8601 ou epoch em ms.") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=SP)
    return int(moment.timestamp() * 1000)


def ts_ms(value):
    if isinstance(value, (int, float)):
        return int(value)
    return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)


def hora_sp(ms):
    return datetime.fromtimestamp(ms / 1000, SP).strftime("%H:%M:%S")


def banda_inicial(sources, at_ms, ate_ms):
    starts = [ts_ms(s["start_timestamp"]) for s in sources]
    candidates = [i for i, start in enumerate(starts) if start <= ate_ms]
    if not candidates:
        raise rd.DownloadError("O erro é anterior ao primeiro bloco da gravação; conferir sessão e horário.")
    hi = max(candidates)
    return max(0, hi - rd.LOTE + 1), hi


def tem_base(events, at_ms):
    return (any(e["type"] == 2 and e["timestamp"] <= at_ms for e in events)
            and any(e["type"] == 4 and e["timestamp"] <= at_ms for e in events))


def escolher_janela(windows, at_ms, wanted=None):
    if wanted:
        if wanted not in windows:
            raise rd.DownloadError("Janela pedida não aparece nos blocos baixados.")
        return wanted, "informada"
    if not windows:
        raise rd.DownloadError("Nenhum evento visual nos blocos baixados.")
    nearest = min((min(abs(e["timestamp"] - at_ms) for e in events), ident) for ident, events in windows.items())
    return nearest[1], "evento gravado mais próximo do erro"


def recortar(events, de_ms, ate_ms):
    """Do Meta anterior ao último snapshot completo até `de` (ou ao primeiro até `ate`) até `ate`.

    Sem snapshot completo na base, o player mostra tela vazia; por isso nunca começar num evento incremental."""
    events = sorted(events, key=lambda e: e["timestamp"])
    full = [i for i, e in enumerate(events) if e["type"] == 2 and e["timestamp"] <= ate_ms]
    if not full:
        return None, len(events)
    anchor = max((i for i in full if events[i]["timestamp"] <= de_ms), default=full[0])
    start = max((i for i in range(anchor) if events[i]["type"] == 4), default=anchor)
    return [e for e in events[start:] if e["timestamp"] <= ate_ms], start


def lacunas(events, at_ms):
    found = []
    for previous, current in zip(events, events[1:]):
        if current["timestamp"] - previous["timestamp"] > LACUNA_MS:
            found.append({"de_s": round((previous["timestamp"] - at_ms) / 1000, 1),
                          "ate_s": round((current["timestamp"] - at_ms) / 1000, 1)})
    return found


def cobertura(events, at_ms):
    before = [e["timestamp"] for e in events if e["timestamp"] <= at_ms]
    after = [e["timestamp"] for e in events if e["timestamp"] > at_ms]
    last = round((max(before) - at_ms) / 1000, 1) if before else None
    first = round((min(after) - at_ms) / 1000, 1) if after else None
    sem_gravacao = last is None or last < -LACUNA_MS / 1000 and (first is None or first > LACUNA_MS / 1000)
    return {"ultimo_evento_antes_s": last, "primeiro_evento_depois_s": first, "sem_gravacao_no_erro": sem_gravacao}


def coletar(client, session, at_ms, modo, wanted, cache, ate_ms=None, reuse_sources=False, de_ms=None):
    """Busca lotes (com cache por faixa de blob_key) até a janela do erro ter snapshot completo e Meta antes de `de`."""
    listed = cache / "sources.json"
    if reuse_sources and listed.exists():
        sources = json.loads(listed.read_text())
    else:
        sources = client.sources(session)
        if reuse_sources:
            rd.write_private(listed, json.dumps(sources))
    if not sources:
        raise rd.DownloadError("Gravação sem blocos disponíveis.")
    windows, seen = defaultdict(list), defaultdict(set)
    stats = dict(raw_events=0, compressed_events=0, duplicates=0, plugin_events_excluded=0)
    fetched = []
    base = f"/api/environments/{client.project}/session_recordings/{session}/snapshots"

    def fetch(lo, hi):
        for a, b in rd.lotes(lo, hi):
            first, last = sources[a]["blob_key"], sources[b]["blob_key"]
            path = cache / f"{first}-{last}.jsonl"
            cached = path.exists()
            if cached:
                body = path.read_bytes()
            else:
                body = client.get(f"{base}?source=blob_v2&start_blob_key={first}&end_blob_key={last}&decompress=true")
                with path.open("xb") as stream:
                    os.chmod(path, 0o600)
                    stream.write(body)
            rd.normalize(body, windows, seen, stats)  # bytes: str.splitlines quebraria em U+2028 dentro de textos
            fetched.append({"indices": [a, b], "blob_keys": [first, last], "bytes": len(body),
                            "sha256": hashlib.sha256(body).hexdigest(), "cache": cached})

    if modo == Modo.INTEIRA:
        fetch(0, len(sources) - 1)
        janela, criterio = escolher_janela(windows, at_ms, wanted)
    else:
        lo, hi = banda_inicial(sources, at_ms, at_ms + ATE_S * 1000 if ate_ms is None else ate_ms)
        fetch(lo, hi)
        base_ms = min(at_ms, at_ms + DE_S * 1000 if de_ms is None else de_ms)

        def falta_base():
            # Lote sem evento visual ou janela informada só em lotes anteriores: continuar recuando.
            if not windows or wanted and wanted not in windows:
                return True
            return not tem_base(windows[escolher_janela(windows, at_ms, wanted)[0]], base_ms)

        while lo > 0 and falta_base():
            fetch(max(0, lo - rd.LOTE), lo - 1)
            lo = max(0, lo - rd.LOTE)
        janela, criterio = escolher_janela(windows, at_ms, wanted)
    if not tem_base(windows[janela], at_ms):
        raise rd.DownloadError("Janela do erro sem snapshot completo e Meta antes do erro, mesmo desde o início da sessão.")
    return sources, windows, stats, fetched, janela, criterio


def montar(windows, at_ms, janela, de_ms, ate_ms):
    """Recorta as janelas no intervalo, mede lacunas e monta a linha do tempo relativa ao erro."""
    rel = lambda ms: round((ms - at_ms) / 1000, 1)
    trimmed, info, linha, sessao = {}, {}, {}, {}
    for ident, events in windows.items():
        events = sorted(events, key=lambda e: e["timestamp"])
        cut, _ = recortar(events, de_ms, ate_ms)
        incluida = cut is not None and (ident == janela or cut[-1]["timestamp"] >= de_ms)
        sessao[ident] = {"inicio_s": rel(events[0]["timestamp"]), "fim_s": rel(events[-1]["timestamp"]),
                         "eventos": len(events), "snapshots_completos": sum(e["type"] == 2 for e in events),
                         "no_laboratorio": incluida}
        if not incluida:
            continue
        trimmed[ident] = cut
        start = cut[0]["timestamp"]
        info[ident] = {"inicio_s": rel(start), "fim_s": rel(cut[-1]["timestamp"]), "eventos": len(cut),
                       "snapshots_completos_s": [rel(e["timestamp"]) for e in cut if e["type"] == 2],
                       "lacunas": lacunas(cut, at_ms)}
        linha[ident] = [{**{k: v for k, v in item.items() if k != "s"}, "rel_s": rel(start + item["s"] * 1000)}
                        for item in analyze_window(cut)["timeline"]]
    if janela not in trimmed:
        raise rd.DownloadError("Janela do erro sem snapshot completo até o fim do intervalo.")
    trimmed = {janela: trimmed[janela], **{k: v for k, v in trimmed.items() if k != janela}}
    return trimmed, info, linha, sessao


def lab_html(windows, meta, js, css, lab_js):
    def embed(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return ('''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Laboratório da gravação</title><style>body{margin:0;background:#18232e;color:#f4f6f8;font:16px Georgia,serif}
header{padding:12px}#player{margin:auto;width:fit-content}
#rel{position:fixed;top:8px;right:16px;z-index:99;background:#14532d;color:#fff;font:bold 16px monospace;padding:4px 10px;border-radius:4px;max-width:70vw}
#rel[data-aviso=sim]{background:#b00020}''' + css + '''</style>
<header><label>Janela <select id="window"></select></label></header><div id="rel"></div><div id="player"></div>
<script>''' + js.replace("</script", "<\\/script") + '''</script>
<script id="events" type="application/json">''' + embed(windows) + '''</script>
<script id="lab-meta" type="application/json">''' + embed(meta) + '''</script>
<script>''' + lab_js.replace("</script", "<\\/script") + '''</script></html>''')


def nome_lab(de_s, ate_s):
    return f"lab_T{de_s:+d}_T{ate_s:+d}"


def leia_me(lab, sessao_browser):
    ab = f"agent-browser --session {sessao_browser} --allow-file-access"
    return f"""# Laboratório da gravação

Cada `lab_T<de>_T<ate>.html` reconstrói um intervalo em volta do erro (segundos relativos a `T`), com o
manifesto de mesmo nome. Os comandos abaixo abrem o último laboratório montado (`{lab.name}`). Investigar com `agent-browser`, numa sessão própria com prefixo `replay-`. A faixa no
topo mostra `T±s` e fica vermelha quando a tela não corresponde a um momento gravado.

```bash
{ab} set viewport 1366 768
{ab} open {lab.as_uri()}
{ab} wait --fn "window.labReady"                # HTML grande: o open pode acusar timeout antes
echo 'lab.info()' | {ab} eval --stdin          # erro, janelas, lacunas, cobertura
echo 'lab.ir(-5)' | {ab} eval --stdin          # posiciona em T-5 s, pausado
{ab} screenshot /caminho/privado/T-5.png
{ab} snapshot                                  # DOM gravado (iframe do player)
echo 'lab.tocar(-10, 2)' | {ab} eval --stdin   # reproduz de T-10 a T+2 (máx. {TOCAR_MAX_S} s)
echo 'lab.linha(-30, 5)' | {ab} eval --stdin   # cliques, rotas e visibilidade no trecho
echo 'lab.janela("<id>")' | {ab} eval --stdin  # outra janela/aba incluída no intervalo
{ab} close
```

Outro intervalo: rodar `replay_lab.py` de novo com `--de`/`--ate`; usa o cache `.lotes`, sem requisição nova.
`lab.info().sessao_janelas` lista todas as janelas da sessão, inclusive as que ficaram fora do intervalo.

Limites: o DOM é a gravação sanitizada (inputs e URLs redigidos), sem executar a aplicação; cliques no player
não fazem nada. Texto visível pode conter dados pessoais: não transcrever sem necessidade. Lacuna sem eventos
pode ser inatividade ou falha de captura; cruzar com os eventos do PostHog antes de concluir.
"""


def resumo(lab, manifest, browser, reutilizado):
    return {"lab": str(lab.resolve()), "leia_me": str((lab.parent / "LEIA-ME.md").resolve()),
            "abrir": f"agent-browser --session {browser} --allow-file-access open {lab.resolve().as_uri()}",
            "janela_erro": manifest["janela_erro"], "cobertura_erro": manifest["cobertura_erro"],
            "janelas_no_laboratorio": len(manifest["janelas"]), "janelas_na_sessao": len(manifest["sessao_janelas"]),
            "requisicoes_snapshots": 0 if reutilizado else manifest["requisicoes_snapshots"],
            "blocos": f"{manifest['blocos_baixados']}/{manifest['blocos_na_sessao']}", "reutilizado": reutilizado}


def preparar(client, session, at_ms, output, modo=Modo.INTEIRA, wanted=None, de_s=DE_S, ate_s=ATE_S,
             assets=rd.player_assets):
    session = str(uuid.UUID(session))
    if not de_s < ate_s or ate_s - de_s > 3600:
        raise rd.DownloadError("Intervalo inválido: --de menor que --ate e no máximo 3600 s.")
    # Milissegundos no nome: dois erros no mesmo segundo não podem compartilhar o relógio do laboratório.
    destination = output / f"{session}-{datetime.fromtimestamp(at_ms / 1000, SP):%Y%m%d-%H%M%S}{at_ms % 1000:03d}"
    lab = destination / (nome_lab(de_s, ate_s) + ".html")
    browser = "replay-" + session[:8]
    if lab.exists():
        manifest = json.loads(lab.with_suffix(".json").read_text())
        if manifest.get("erro_ms") != at_ms or manifest.get("janela_informada") != wanted or manifest.get("modo") != modo:
            raise rd.DownloadError("Laboratório existente foi feito com outra janela/modo; usar outra saída.")
        return resumo(lab, manifest, browser, True)
    project = client.cli("project-get", {})
    if project.get("id") != client.project:
        raise rd.DownloadError("Projeto ativo do CLI não confere.")
    metadata = client.cli("session-recording-get", {"id": session})
    if metadata.get("found") is False or metadata.get("id") != session:
        raise rd.DownloadError("Gravação não encontrada; verificar retenção/permissão.")
    if metadata.get("snapshot_source") not in (None, "web"):
        raise rd.DownloadError("Este leitor reconstrói gravações web; fonte não suportada.")
    cache = destination / ".lotes"
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    de_ms, ate_ms = at_ms + de_s * 1000, at_ms + ate_s * 1000
    sources, windows, stats, fetched, janela, criterio = coletar(
        client, session, at_ms, modo, wanted, cache, ate_ms, reuse_sources=metadata.get("ongoing") is False,
        de_ms=de_ms)
    trimmed, info, linha, sessao = montar(windows, at_ms, janela, de_ms, ate_ms)
    js, css, integrity = assets()
    meta = {"sessao": session, "erro_ms": at_ms, "erro_hora_sp": hora_sp(at_ms),
            "erro_iso_sp": datetime.fromtimestamp(at_ms / 1000, SP).isoformat(timespec="milliseconds"),
            "intervalo_s": [de_s, ate_s], "janela_erro": janela, "janela_criterio": criterio, "janelas": info,
            "sessao_janelas": sessao, "cobertura_erro": cobertura(sorted(windows[janela], key=lambda e: e["timestamp"]), at_ms),
            "tocar_max_s": TOCAR_MAX_S, "aquecimento_ms": AQUECIMENTO_MS, "linha": linha}
    manifest = {**{k: v for k, v in meta.items() if k != "linha"}, "modo": modo, "janela_informada": wanted,
                "host": client.host, "projeto": client.project, "gravacao_inicio": metadata.get("start_time"),
                "gravacao_fim": metadata.get("end_time"), "em_andamento": metadata.get("ongoing"),
                "blocos_na_sessao": len(sources), "blocos_baixados": sum(f["indices"][1] - f["indices"][0] + 1 for f in fetched),
                "requisicoes_snapshots": client.requests, "lotes": fetched, **stats,
                "player_version": rd.PLAYER_VERSION, "player_integrity": integrity,
                "criado_em": datetime.now(timezone.utc).isoformat(),
                "limitacoes": ["Gravação sanitizada; inputs e URLs redigidos podem alterar a tela.",
                               "Lacuna sem eventos pode ser inatividade ou falha de captura.",
                               "Modo banda só baixa os lotes necessários para a janela do erro; outras janelas podem faltar."]}
    lab_js = Path(__file__).with_name("replay_lab.js").read_text()
    rd.write_private(lab.with_suffix(".json"), json.dumps(manifest, ensure_ascii=False, indent=2))
    rd.write_private(lab, lab_html(trimmed, meta, js, css, lab_js))
    (destination / "LEIA-ME.md").unlink(missing_ok=True)  # gerado pelo script; aponta para o último laboratório
    rd.write_private(destination / "LEIA-ME.md", leia_me(lab.resolve(), browser))
    return resumo(lab, manifest, browser, False)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("session_id")
    parser.add_argument("--at", required=True, help="Horário do erro: ISO 8601 (sem fuso = São Paulo) ou epoch ms")
    parser.add_argument("--output", type=Path, required=True, help="Pasta privada, fora do Git")
    parser.add_argument("--de", type=int, default=DE_S, help=f"Início do laboratório, s relativos ao erro (padrão {DE_S})")
    parser.add_argument("--ate", type=int, default=ATE_S, help=f"Fim do laboratório, s relativos ao erro (padrão {ATE_S})")
    parser.add_argument("--window-id", help="$window_id do evento de erro; sem ele, a janela com evento mais próximo")
    parser.add_argument("--modo", choices=[Modo.INTEIRA, Modo.BANDA], default=Modo.INTEIRA,
                        help="inteira (padrão): todos os blocos no cache; banda: só os lotes necessários")
    parser.add_argument("--host", default="https://us.posthog.com")
    parser.add_argument("--project-id", type=int, default=331102)
    parser.add_argument("--max-bytes", type=int, default=512 * 1024 * 1024)
    args = parser.parse_args()
    try:
        host = rd.origin(args.host)
        token, _ = rd.credentials(host, args.project_id)
        client = rd.Client(host, args.project_id, token, args.max_bytes, 10_000)
        result = preparar(client, args.session_id, parse_at(args.at), args.output, args.modo, args.window_id,
                          args.de, args.ate)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (rd.DownloadError, ValueError, OSError, KeyError, TypeError) as exc:
        message = str(exc) if isinstance(exc, rd.DownloadError) else f"{type(exc).__name__}; saída incompleta, conteúdo privado omitido."
        print("replay-lab: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
