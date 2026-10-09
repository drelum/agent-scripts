#!/usr/bin/env python3
"""Evidências locais de rrweb; não infere emoção nem consulta APIs."""

import argparse
from collections import Counter
from enum import IntEnum
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit


class Event(IntEnum):
    SNAPSHOT = 2
    INCREMENTAL = 3
    META = 4
    CUSTOM = 5


class Source(IntEnum):
    MUTATION = 0
    INTERACTION = 2
    INPUT = 5


def clean(text):
    text = re.sub(r"https?://[^\s]+", "[URL]", str(text))
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    text = re.sub(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", "[CNPJ]", text)
    text = re.sub(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+\b", "[JWT]", text)
    text = re.sub(r"(?i)(token|password|senha|authorization)\s*[:=]\s*\S+", r"\1=[REDIGIDO]", text)
    return " ".join(text.split())[:180]


class Mirror:
    def __init__(self):
        self.nodes = {}

    def add(self, node, parent=None, next_id=None):
        ident = node.get("id")
        if ident is None:
            return
        attrs = {k: v for k, v in node.get("attributes", {}).items()
                 if k in ("aria-label", "title", "placeholder", "role", "disabled", "aria-disabled")
                 and v is not None}
        self.nodes[ident] = {"parent": parent, "children": [], "tag": node.get("tagName"),
                             "text": node.get("textContent", ""), "attrs": attrs}
        if parent in self.nodes:
            children = self.nodes[parent]["children"]
            if ident in children:
                children.remove(ident)
            children.insert(children.index(next_id) if next_id in children else len(children), ident)
        for child in node.get("childNodes", []):
            self.add(child, ident)

    def remove(self, ident):
        node = self.nodes.pop(ident, None)
        if node:
            parent = self.nodes.get(node["parent"])
            if parent and ident in parent["children"]:
                parent["children"].remove(ident)
            for child in node["children"][:]:
                self.remove(child)

    def mutate(self, data):
        for item in data.get("removes", []):
            self.remove(item["id"])
        for item in data.get("adds", []):
            self.add(item["node"], item.get("parentId"), item.get("nextId"))
        for item in data.get("texts", []):
            if item["id"] in self.nodes:
                self.nodes[item["id"]]["text"] = item.get("value", "")
        for item in data.get("attributes", []):
            if item["id"] not in self.nodes:
                continue
            attrs = self.nodes[item["id"]]["attrs"]
            for key, value in item.get("attributes", {}).items():
                if value is None:
                    attrs.pop(key, None)
                elif key in ("aria-label", "title", "placeholder", "role", "disabled", "aria-disabled"):
                    attrs[key] = value

    def label(self, ident):
        seen = set()
        while ident in self.nodes and ident not in seen:
            seen.add(ident)
            node = self.nodes[ident]
            if node["tag"] in ("button", "a", "input", "select", "textarea") or node["attrs"].get("role") == "button":
                attrs = node["attrs"]
                text = attrs.get("aria-label") or attrs.get("placeholder") or attrs.get("title")
                if not text:
                    todo, parts, budget = [ident], [], 100
                    while todo and budget:
                        budget -= 1
                        current = self.nodes.get(todo.pop())
                        if current and current["tag"] not in ("style", "script"):
                            parts.append(current["text"])
                            todo.extend(reversed(current["children"]))
                    text = " ".join(parts)
                return {"control": clean(text) or "[controle sem rótulo]", "tag": node["tag"],
                        "disabled_attribute": "disabled" in attrs,
                        "aria_disabled": attrs.get("aria-disabled") == "true"}
            ident = node["parent"]
        return {"control": "[alvo sem controle identificado]", "tag": None}


def analyze_window(events):
    if not events:
        raise ValueError("Janela sem eventos")
    events = sorted(events, key=lambda e: e["timestamp"])
    start, end = events[0]["timestamp"], events[-1]["timestamp"]
    mirror, timeline, input_counts = Mirror(), [], Counter()
    snapshots = 0
    for event in events:
        data = event.get("data", {})
        seconds = round((event["timestamp"] - start) / 1000, 3)
        entry = {"s": seconds}
        if event["type"] == Event.SNAPSHOT:
            snapshots += 1
            mirror = Mirror()
            mirror.add(data["node"])
        elif event["type"] == Event.META:
            url = urlsplit(data.get("href", ""))
            entry.update(kind="location_snapshot", host=url.hostname, path=url.path)
        elif event["type"] == Event.CUSTOM and data.get("tag") in ("window hidden", "window visible", "$session_idle"):
            entry.update(kind="visibility_or_idle", state=data["tag"])
        elif event["type"] == Event.INCREMENTAL:
            if data.get("source") == Source.MUTATION:
                mirror.mutate(data)
            elif data.get("source") == Source.INTERACTION and data.get("type") == 2:
                entry.update(kind="click", node_id=data.get("id"), **mirror.label(data.get("id")))
            elif data.get("source") == Source.INPUT:
                input_counts[mirror.label(data.get("id"))["control"]] += 1
        if "kind" in entry:
            timeline.append(entry)
    clicks = [e for e in timeline if e["kind"] == "click"]
    repeats, run = [], []
    for click in clicks:
        if run and (click["control"] != run[-1]["control"] or click["s"] - run[-1]["s"] > 1.5):
            if len(run) >= 3:
                repeats.append({"start_s": run[0]["s"], "end_s": run[-1]["s"], "count": len(run), "control": run[0]["control"]})
            run = []
        run.append(click)
    if len(run) >= 3:
        repeats.append({"start_s": run[0]["s"], "end_s": run[-1]["s"], "count": len(run), "control": run[0]["control"]})
    return {"start_ms": start, "end_ms": end, "snapshots": snapshots, "clicks": len(clicks),
            "timeline": timeline, "input_updates_by_control": dict(input_counts),
            "rapid_repetitions_not_frustration": repeats}


def write_private(path, text):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        stream.write(text)


def analyze_sample(root, output):
    started = time.monotonic()
    analytics = json.loads((root / "analytics-events.json").read_text())
    sessions = []
    for item in json.loads((root / "index.json").read_text()):
        windows = json.loads((root / item["id"] / "events.json").read_text())
        evidence = {ident: analyze_window(events) for ident, events in windows.items()}
        first = min(w["start_ms"] for w in evidence.values())
        last = max(w["end_ms"] for w in evidence.values())
        events = []
        for event in analytics:
            if event["session_id"] == item["id"]:
                stamp = int(event["ts_ms"])
                events.append({"event": clean(event["event"]), "timestamp_ms": stamp,
                               "relative_to_replay_s": round((stamp - first) / 1000, 3),
                               "inside_visual_bounds": first <= stamp <= last})
        sessions.append({"session_id": item["id"], "user": item["user"], "windows": evidence,
                         "analytics": events, "analytics_counts": dict(Counter(e["event"] for e in events))})
    result = {"limitations": ["Intenção, emoção e sucesso não são calculados automaticamente.",
                              "Inputs são atualizações, não teclas; valores não são exportados.",
                              "Relógios de analytics e rrweb não são alinhados; tempos são de cada fonte.",
                              "Atributos e texto do DOM não comprovam visibilidade.",
                              "Pacotes com iframe ou mutações fora de ordem exigem conferir o player."],
              "sessions": sessions, "elapsed_seconds": round(time.monotonic() - started, 3)}
    write_private(output / "evidence.json", json.dumps(result, ensure_ascii=False, indent=2))
    lines = ["# Linha do tempo das gravações", "", *result["limitations"], ""]
    for number, session in enumerate(sessions, 1):
        lines.extend([f"## Sessão {number} — usuário {session['user']}", "", f"ID: {session['session_id']}", ""])
        for ident, window in session["windows"].items():
            lines.extend([f"Janela {ident}: {window['snapshots']} snapshots; {window['clicks']} cliques.", ""])
            for event in window["timeline"]:
                content = event.get("control") or event.get("state") or event.get("path") or "[local desconhecido]"
                content = content.replace("|", " ").replace("<", "&lt;").replace(">", "&gt;")
                lines.append(f"- {event['s']:.3f}s · {event['kind']} · {content}")
            lines.append("")
        lines.extend(["Analytics: " + json.dumps(session["analytics_counts"], ensure_ascii=False), ""])
    write_private(output / "timeline.md", "\n".join(lines))
    return result


def frame(session_dir, seconds, browser_session, output, window_id=None):
    if not browser_session.startswith("replay-"):
        raise ValueError("Use uma sessão própria com prefixo replay-")
    player = (session_dir / "reproducao.html").resolve(strict=True)
    if not 0 <= seconds < float("inf"):
        raise ValueError("Tempo inválido")
    command = ["agent-browser", "--session", browser_session, "--allow-file-access"]
    subprocess.run(command + ["set", "viewport", "1366", "768"], check=True, capture_output=True, text=True)
    subprocess.run(command + ["open", player.as_uri()], check=True, capture_output=True, text=True)
    js = (Path(__file__).with_name("replay_frame.js").read_text()
          .replace("__TARGET_MS__", str(round(seconds * 1000)))
          .replace("__WINDOW_ID__", json.dumps(window_id)))
    result = subprocess.run(command + ["eval", "--stdin"], input=js, capture_output=True, text=True, check=True)
    proof = json.loads(result.stdout)
    output = output.resolve()
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("Destino já existe; escolha outro nome")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    subprocess.run(command + ["screenshot", str(output)], check=True, capture_output=True, text=True)
    os.chmod(output, 0o600)
    write_private(output.with_suffix(".json"), json.dumps(proof, ensure_ascii=False, indent=2))
    return proof


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    analysis = sub.add_parser("analyze")
    analysis.add_argument("sample_dir", type=Path)
    analysis.add_argument("--output", type=Path, required=True)
    capture = sub.add_parser("frame")
    capture.add_argument("session_dir", type=Path)
    capture.add_argument("--at", type=float, required=True)
    capture.add_argument("--browser-session", required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--window-id", help="Janela específica do manifest.json; tempo relativo a essa janela")
    args = parser.parse_args()
    if args.command == "analyze":
        result = analyze_sample(args.sample_dir, args.output)
        print(f"{len(result['sessions'])} sessões; {result['elapsed_seconds']}s; saída privada em {args.output.resolve()}")
    else:
        proof = frame(args.session_dir, args.at, args.browser_session, args.output, args.window_id)
        print(json.dumps(proof, ensure_ascii=False))
        print(f"Fechar somente esta sessão: agent-browser --session {args.browser_session} close")


if __name__ == "__main__":
    main()
