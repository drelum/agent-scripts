"""Autenticação Pluggy e delegação dos comandos gerados ao Restish."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / ".state" / "pluggy"
OPERATIONS = {
    "/items/{id}": "items-retrieve",
    "/accounts": "accounts-list",
    "/accounts/{id}": "accounts-retrieve",
    "/v2/transactions": "transactions-list-by-cursor",
    "/transactions/{id}": "transactions-retrieve",
    "/bills": "bills-list",
    "/bills/{id}": "bills-retrieve",
    "/investments": "investments-list",
    "/investments/{id}": "investments-retrieve",
    "/investments/{id}/transactions": "investment-transactions-list",
}
# Parâmetros financeiros vêm do OpenAPI. Só controles de execução seguros passam.
OPTIONS = {
    "--help": 0, "-h": 0, "--help-all": 0,
    "--type": 1, "--page": 1, "--page-size": 1,
    "--date-from": 1, "--date-to": 1, "--created-at-from": 1,
    "--ids": 1, "--after": 1,
    "--rsh-filter": 1, "-f": 1, "--rsh-filter-lang": 1,
    "--rsh-output-format": 1, "-o": 1, "--rsh-columns": 1,
    "--rsh-no-paginate": 0,
}


def clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("RSH_", "PLUGGY_")) and k != "INFISICAL_TOKEN"}


def curate(spec):
    """Manter somente dez GETs e impedir overrides de origem/extensões locais."""
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()
                    if k != "servers" and not k.startswith("x-cli-")}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    result = clean(spec)
    result["servers"] = [{"url": "https://api.pluggy.ai"}]
    result["paths"] = {}
    for path, name in OPERATIONS.items():
        original = spec["paths"][path]
        entry = clean({k: v for k, v in original.items() if k in ("parameters", "get")})
        entry["get"]["x-cli-name"] = name
        result["paths"][path] = entry
    return result


def setup():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    c = http.client.HTTPSConnection("docs.pluggy.ai", timeout=30)
    c.request("GET", "/openapi/pluggy-api.json")
    r = c.getresponse()
    if r.status != 200:
        raise RuntimeError(f"OpenAPI HTTP {r.status}")
    spec = curate(json.loads(r.read()))
    (STATE / "openapi.json").write_text(json.dumps(spec))
    apis = {}
    for name, pagination in (
        ("pluggy", {"items_path": "results", "page_param": "page"}),
        ("pluggy-cursor", {"items_path": "results", "next_path": "next"}),
    ):
        apis[name] = {
            "base_url": "https://api.pluggy.ai", "spec_files": [str(STATE / "openapi.json")],
            "pagination": pagination,
            "profiles": {"default": {"auth": {"type": "api-key", "params": {
                "in": "header", "name": "X-API-KEY", "value": "env:PLUGGY_API_KEY"}}}},
        }
    config = STATE / "restish.json"
    config.touch(mode=0o600)
    config.chmod(0o600)
    config.write_text(json.dumps({"apis": apis}))
    env = dict(clean_env(), RSH_CACHE_DIR=str(STATE / "cache"))
    for name in apis:
        subprocess.run([str(STATE / "restish"), "--rsh-config", str(config),
                        "api", "sync", name], env=env, check=True)
    print("OpenAPI atualizado: dez operações GET. Configuração sem segredos.")


def validate(args):
    if args[0] not in OPERATIONS.values():
        raise ValueError("Comando fora do escopo. Use pluggy --help.")
    i = 1
    while i < len(args):
        value = args[i]
        if value.startswith("-"):
            flag, sep, _ = value.partition("=")
            if flag not in OPTIONS:
                raise ValueError(f"Opção não permitida: {flag}")
            arity = OPTIONS[flag]
            if sep and not arity:
                raise ValueError(f"Opção sem valor: {flag}")
            if arity and not sep:
                i += 1
                if i == len(args) or args[i].startswith("-"):
                    raise ValueError(f"Falta valor para {flag}")
        i += 1


def main(args):
    injected = bool(args and args[0] == "--injected")
    if injected:
        args = args[1:]
    if args == ["setup"]:
        setup()
        return 0
    args = args or ["--help"]
    root_help = args in (["--help"], ["--help-all"])
    if not root_help:
        validate(args)
    help_only = root_help or any(a in args for a in ("--help", "-h", "--help-all"))
    if not help_only and not injected:
        return subprocess.run([
            "infisical", "run", "--profile", "andre@aitrus.com.br",
            "--project-config-dir=" + str(ROOT / "skills/pluggy/config"),
            "--env=dev", "--path=/Pluggy", "--silent", "--",
            sys.executable, str(Path(__file__).resolve()), "--injected", *args,
        ], env=clean_env()).returncode
    env = dict(clean_env(), RSH_CACHE_DIR=str(STATE / "cache"))
    if not help_only:
        for key in ("PLUGGY_CLIENT_ID", "PLUGGY_CLIENT_SECRET"):
            if not os.environ.get(key):
                raise ValueError(f"Variável ausente: {key}")
        c = http.client.HTTPSConnection("api.pluggy.ai", timeout=30)
        c.request("POST", "/auth", json.dumps({
            "clientId": os.environ["PLUGGY_CLIENT_ID"],
            "clientSecret": os.environ["PLUGGY_CLIENT_SECRET"],
        }), {"Content-Type": "application/json"})
        r = c.getresponse()
        if r.status != 200:
            raise RuntimeError(f"Autenticação HTTP {r.status}")
        env["PLUGGY_API_KEY"] = json.loads(r.read())["apiKey"]
        args = [os.environ.get("PLUGGY_ITEM_ID", "") if a == "@item" else a for a in args]
        if "" in args:
            raise ValueError("Variável ausente: PLUGGY_ITEM_ID")
    api = "pluggy-cursor" if args[0] == "transactions-list-by-cursor" else "pluggy"
    if args[0] in ("bills-list", "investments-list", "investment-transactions-list"):
        if not any(a == "--page" or a.startswith("--page=") for a in args):
            args += ["--page", "1"]
    command = [str(STATE / "restish"), "--rsh-config", str(STATE / "restish.json"),
               "--rsh-no-cache", "--rsh-print", "b", "--rsh-output-format", "json",
               "--rsh-collect", "--rsh-max-pages", "0", "--rsh-retry-max-wait", "30s",
               api, *args]
    # Buffer em memória: não entregar um extrato parcial acompanhado de warning.
    result = subprocess.run(command, env=env, capture_output=True)
    if result.returncode or (result.stderr and not help_only):
        print("Restish falhou ou emitiu aviso; resultado descartado. Confira parâmetros e cobertura.", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(result.stdout)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Falha de rede/configuração. Execute a instalação e pluggy setup.", file=sys.stderr)
        sys.exit(1)
