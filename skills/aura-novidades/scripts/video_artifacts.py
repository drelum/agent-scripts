"""Assinaturas de tomadas e cache validado de vinhetas. Não guarda autenticação."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signature(kind, root, skill, slug):
    nov = Path(root) / "novidades"
    skill = Path(skill)
    config = json.loads((nov / "vinheta.json").read_text())
    files = [nov / "entradas" / f"{slug}.md"]
    if kind == "capture":
        files += [nov / "entradas/roteiros" / f"{slug}.sh"]
        files += [skill / name for name in ("aura-novidades-video", "mascara.js", "video-overlay.js", "video_artifacts.py")]
        context = {key: os.environ.get(key, default) for key, default in (
            ("NOV_UI", "https://ui.beta.aura.localhost"),
            ("NOV_API", "https://api.beta.aura.localhost"), ("NOV_CNPJ", "05101867000157"))}
        context["video"] = config.get("video", {})
    else:
        files += [nov / "vinheta.json", skill / "aura-novidades-vinheta", skill / "video_artifacts.py"]
        files += sorted(p for p in (nov / "vinheta").rglob("*") if p.is_file())
        logo = config.get("som", {}).get("logo")
        if logo and (nov / logo).is_file():
            files.append(nov / logo)
        context = {}
    payload = {"context": context, "files": [(p.name, digest(p)) for p in files]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def save(directory, key, names):
    directory = Path(directory)
    value = {"signature": key, "files": {name: digest(directory / name) for name in names}}
    pending = directory / "manifest.pending.json"
    pending.write_text(json.dumps(value, indent=2) + "\n")
    pending.replace(directory / "manifest.json")


def valid(directory, key, names):
    try:
        directory = Path(directory)
        manifest = json.loads((directory / "manifest.json").read_text())
        return (manifest["signature"] == key and set(manifest["files"]) == set(names)
                and all(digest(directory / name) == manifest["files"][name] for name in names))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def cached_vinheta(root, skill, slug, destination):
    key = signature("vinheta", root, skill, slug)
    base = Path(os.environ.get("NOV_VIDEO_CACHE", f"/tmp/aura-novidades-cache-{os.getuid()}"))
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = base / key
    names = ["abertura.mp4", "encerramento.mp4"]
    config = json.loads((Path(root) / "novidades/vinheta.json").read_text())
    if config.get("som", {}).get("logoSonoro"):
        names.append("logo-sonoro.wav")
    # Um renderer por assinatura; arquivos incompletos nunca são cache válido.
    with (base / f"{key}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if valid(target, key, names):
            print("vinheta: cache validado", flush=True)
        else:
            pending = Path(tempfile.mkdtemp(prefix=f"{key}.", dir=base))
            subprocess.run([str(Path(skill) / "aura-novidades-vinheta"), "--render", slug, str(pending)], check=True)
            for name in names:
                subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(pending / name), "-f", "null", "-"], check=True)
            save(pending, key, names)
            if target.exists():
                target.rename(base / f"{key}.invalid-{time.time_ns()}")
            pending.rename(target)
            print("vinheta: cache criado", flush=True)
        destination = Path(destination)
        if destination.exists():
            destination.rename(destination.with_name(f"{destination.name}.anterior-{time.time_ns()}"))
        destination.mkdir(parents=True, exist_ok=True)
        for name in names:
            shutil.copy2(target / name, destination / name)


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "signature":
        print(signature(*args))
    elif command == "save":
        save(args[0], args[1], args[2:])
    elif command == "check":
        if not valid(args[0], args[1], args[2:]):
            sys.exit("tomada ausente, alterada ou incompatível com entrada/roteiro/configuração; capture novamente")
    elif command == "vinheta":
        cached_vinheta(*args)
    else:
        sys.exit("operação de artefatos inválida")
