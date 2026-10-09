#!/usr/bin/env python3
"""Laboratório portátil: acesso de leitura, consultas e contexto de replay."""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

SKILL = Path(__file__).resolve().parents[1]
SP = ZoneInfo("America/Sao_Paulo")
SECRET_KEYS = re.compile(r"(?:token|password|passwd|secret|authorization|cookie|api.?key|credential|headers|request.?body|response.?body)", re.I)
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


class LabError(Exception):
    pass


def sanitize(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if SECRET_KEYS.search(k) else sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        value = JWT.sub("[REDACTED]", value)
        value = re.sub(r"\bBearer\s+\S+", "Bearer [REDACTED]", value, flags=re.I)
        return re.sub(r"https?://[^\s<>\"']+", lambda m: safe_url(m.group()), value)
    return value


def safe_url(value):
    parts = urllib.parse.urlsplit(value)
    # Nenhuma query string, fragmento ou credencial de URL entra no relatório.
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def safe_rows(columns, rows):
    return [["[REDACTED]" if SECRET_KEYS.search(column) else sanitize(value) for column, value in zip(columns, row)] for row in rows]


def command(argv, env=None, timeout=45):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=timeout)
    except FileNotFoundError:
        raise LabError(f"Ferramenta ausente: {argv[0]}") from None
    except subprocess.TimeoutExpired:
        raise LabError(f"Tempo de espera esgotado: {argv[0]}") from None
    if result.returncode:
        raw = result.stderr + result.stdout
        if re.search(r"invalid_(?:grant|rapt)|Reauthentication failed", raw, re.I):
            reason = "Autenticação expirada; refaça o login indicado no onboarding."
        elif re.search(r"403|PERMISSION_DENIED|permission denied|access denied", raw, re.I):
            reason = "Acesso negado; confira conta, projeto e permissões."
        elif re.search(r"401|not authenticated|not logged|credentials|authenticate|login", raw, re.I):
            reason = "Autenticação ausente ou inválida; consulte o onboarding."
        else:
            reason = "Falha no comando; consulte o diagnóstico local da ferramenta."
        # Nunca devolver stderr: pode conter segredo, URL assinada ou payload.
        raise LabError(f"{argv[0]}: {reason}")
    return result.stdout


def load_config(path):
    config = json.loads(Path(path).read_text())
    for section in ("gcp", "clickhouse", "mysql", "posthog"):
        if not isinstance(config.get(section), dict):
            raise LabError(f"Configuração ausente: {section}")
    for url in (config["clickhouse"]["url"], config["posthog"]["host"]):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise LabError("Endpoints exigem HTTPS, sem credenciais ou parâmetros na URL.")
    if not isinstance(config["posthog"]["project_id"], int) or config["posthog"]["project_id"] <= 0:
        raise LabError("project_id precisa ser inteiro positivo.")
    return config


def assert_read_only(sql):
    """Guarda conservadora; a autorização de leitura também precisa existir no servidor."""
    tokens, i, ended = [], 0, False
    while i < len(sql):
        char = sql[i]
        if char.isspace():
            i += 1
            continue
        if ended:
            raise LabError("Envie exatamente uma instrução SQL.")
        if sql.startswith(("--", "/*"), i) or char == "#":
            raise LabError("Remova comentários SQL, incluindo comentários executáveis.")
        if char in "'\"`":
            quote = char
            i += 1
            while i < len(sql):
                if sql[i] == "\\":
                    i += 2
                elif sql[i] == quote:
                    i += 1
                    if i < len(sql) and sql[i] == quote:
                        i += 1
                    else:
                        break
                else:
                    i += 1
            else:
                raise LabError("Literal ou identificador SQL não terminado.")
            continue
        if char == ";":
            ended = True
            i += 1
            continue
        match = re.match(r"[A-Za-z_][A-Za-z_0-9]*", sql[i:])
        if match:
            tokens.append(match.group().upper())
            i += len(match.group())
        else:
            i += 1
    if not tokens or tokens[0] not in {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}:
        raise LabError("Consulta recusada: use SELECT, WITH, SHOW, DESCRIBE ou EXPLAIN.")
    banned = {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE", "CALL", "SET", "SETTINGS", "FORMAT", "INTO", "OUTFILE", "DUMPFILE", "LOAD_FILE", "SLEEP", "BENCHMARK", "GET_LOCK", "URL", "S3", "REMOTE", "FILE"}
    if banned.intersection(tokens):
        raise LabError("Consulta recusada: escrita, efeitos externos ou opções de execução.")
    return sql.strip().removesuffix(";")


def secret(config):
    value = os.environ.get("INCIDENT_CLICKHOUSE_PASSWORD")
    if value:
        return value
    cfg = config["clickhouse"]
    return command(["gcloud", "secrets", "versions", "access", "latest", "--secret", cfg["password_secret"], "--project", config["gcp"]["secret_project"]]).rstrip("\r\n")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Não encaminhar Basic Auth para outro host nem fazer downgrade de TLS.
        return None


def clickhouse(config, sql, limit):
    sql = assert_read_only(sql)
    cfg = config["clickhouse"]
    params = {"readonly": 2, "max_execution_time": 30, "max_result_rows": limit + 1, "result_overflow_mode": "throw", "default_format": "JSONCompact"}
    auth = base64.b64encode(f"{cfg['user']}:{secret(config)}".encode()).decode()
    request = urllib.request.Request(cfg["url"].rstrip("/") + "/?" + urllib.parse.urlencode(params), data=sql.encode(), headers={"Authorization": "Basic " + auth})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=40) as response:
            data = response.read(8_000_001)
    except urllib.error.HTTPError as error:
        raise LabError(f"ClickHouse: HTTP {error.code}; resposta privada omitida.") from None
    except (urllib.error.URLError, TimeoutError):
        raise LabError("ClickHouse: falha de rede/TLS ou tempo esgotado.") from None
    if len(data) > 8_000_000:
        raise LabError("Resposta excedeu 8 MB; reduza colunas e janela.")
    result = json.loads(data)
    rows = result["data"]
    columns = [m["name"] for m in result["meta"]]
    return {"source": "clickhouse", "columns": columns, "rows": safe_rows(columns, rows[:limit]), "truncated": len(rows) > limit, "limit": limit}


@contextmanager
def mysql_proxy(config):
    # Porta própria, proxy próprio; nunca reutilizar um listener desconhecido.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    cfg = config["mysql"]
    env = dict(os.environ)
    env.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    argv = ["cloud-sql-proxy", "--address", "127.0.0.1", "--auto-iam-authn", "--impersonate-service-account=" + cfg["service_account"], "--port", str(port), cfg["instance"]]
    try:
        process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    except FileNotFoundError:
        raise LabError("Instale cloud-sql-proxy; consulte o onboarding.") from None
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise LabError("Proxy falhou; confira ADC e permissão de impersonação no onboarding.")
            with socket.socket() as probe:
                probe.settimeout(0.2)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    yield port
                    return
            time.sleep(0.1)
        raise LabError("Proxy não iniciou em 30 segundos; confira rede e autenticação.")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def mysql(config, sql, limit):
    sql = assert_read_only(sql)
    if not re.match(r"^(SELECT|WITH)\b", sql, re.I):
        raise LabError("MySQL neste laboratório usa SELECT/WITH; descubra schema via information_schema.")
    try:
        import pymysql
    except ImportError:
        raise LabError("Instale a dependência opcional PyMySQL no ambiente virtual.") from None
    env = dict(os.environ)
    env.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    command(["gcloud", "auth", "application-default", "print-access-token"], env=env)
    with mysql_proxy(config) as port:
        conn = None
        try:
            conn = pymysql.connect(host="127.0.0.1", port=port, user=config["mysql"]["user"], password="", connect_timeout=15, read_timeout=35, write_timeout=10, autocommit=False)
            with conn.cursor() as cursor:
                cursor.execute("SELECT CURRENT_USER()")
                identity = cursor.fetchone()[0]
                if identity.split("@", 1)[0] != config["mysql"]["user"]:
                    raise LabError("MySQL: identidade diferente da conta de leitura configurada.")
                cursor.execute("SET SESSION MAX_EXECUTION_TIME=30000")
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                cursor.execute("START TRANSACTION READ ONLY")
            # LIMIT no servidor evita buffering ilimitado e drenagem de SSCursor.
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT * FROM ({sql}) AS incident_lab_rows LIMIT {limit + 1}")
                columns = [entry[0] for entry in cursor.description]
                rows = cursor.fetchmany(limit + 1)
            return {"source": "mysql", "columns": columns, "rows": safe_rows(columns, rows[:limit]), "truncated": len(rows) > limit, "limit": limit}
        except pymysql.MySQLError as error:
            raise LabError(f"MySQL: erro {error.args[0]}; mensagem privada omitida.") from None
        finally:
            if conn is not None and conn.open:
                conn.close()


def posthog(config, tool, payload):
    env = dict(os.environ)
    cfg = config["posthog"]
    env["POSTHOG_CLI_PROJECT_ID"] = str(cfg["project_id"])
    env["POSTHOG_CLI_HOST"] = cfg["host"]
    # O CLI mantém a credencial no seu próprio armazenamento ou recebe env injetado.
    result = json.loads(command(["posthog-cli", "--host", cfg["host"], "api", "call", "--json", tool, json.dumps(payload)], env=env, timeout=90))
    if isinstance(result, dict) and (result.get("isError") or result.get("error")):
        raise LabError("PostHog retornou erro; conteúdo privado omitido.")
    return result


def project_probe(config):
    result = posthog(config, "project-get", {})
    if result.get("id") != config["posthog"]["project_id"]:
        raise LabError("PostHog: projeto ativo diferente do configurado.")
    return {k: result.get(k) for k in ("id", "name", "timezone", "session_recording_opt_in")}


def replay_metadata(config, session):
    uuid.UUID(session)
    project_probe(config)
    result = posthog(config, "session-recording-get", {"id": session})
    fields = ("id", "found", "reason", "start_time", "end_time", "recording_duration", "ongoing", "event_count", "console_error_count", "click_count", "snapshot_source")
    return {k: result[k] for k in fields if k in result}


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise LabError("Inclua fuso no timestamp (Z ou -03:00).")
    return parsed


def replay_link(base_url, start, error, end=None, before=10):
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme != "https" or parts.username or parts.password or parts.fragment:
        raise LabError("Use a URL HTTPS da sessão retornada pelo PostHog.")
    match = re.fullmatch(r"/project/(\d+)/replay/([a-fA-F0-9-]{36})", parts.path)
    if not match:
        raise LabError("Use a URL canônica /project/<id>/replay/<UUID>.")
    uuid.UUID(match.group(2))
    origin, incident = parse_time(start), parse_time(error)
    if not math.isfinite(before) or before < 0 or incident < origin or (end and incident > parse_time(end)):
        raise LabError("Erro fora da gravação ou antecedência inválida.")
    seconds = max(0, math.floor((incident - origin).total_seconds() - before))
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    if any(k != "t" for k, _ in query):
        raise LabError("A URL base só pode conter o parâmetro de tempo t.")
    url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "t=" + str(seconds), ""))
    return {"url": url, "project_id": int(match.group(1)), "session_id": match.group(2), "offset_seconds": seconds, "error_sp": incident.astimezone(SP).strftime("%d/%m/%Y %H:%M:%S"), "bounds_verified": end is not None, "note": "t posiciona o início; não limita o fim da reprodução."}


def replay_summary(path):
    windows = json.loads(Path(path).read_text())
    if not isinstance(windows, dict):
        raise LabError("events.json deve mapear window_id para eventos rrweb.")
    result = []
    for window, events in windows.items():
        if not events:
            continue
        ordered = sorted(events, key=lambda event: event["timestamp"])
        timeline = []
        for event in ordered:
            data = event.get("data")
            if event["type"] == 3 and isinstance(data, dict) and data.get("source") in (2, 5, 12):
                timeline.append({"timestamp_ms": event["timestamp"], "source": data["source"], "interaction_type": data.get("type"), "node_id": data.get("id")})
        result.append({"window_id": window, "snapshots": len(events), "full_snapshots": sum(e["type"] == 2 for e in events), "first_timestamp_ms": ordered[0]["timestamp"], "last_timestamp_ms": ordered[-1]["timestamp"], "timeline": timeline})
    return {"windows": result, "visual_review": False, "limitations": ["Contagens e interações estruturais; não prova o que foi visto na tela.", "Sem manifesto de download, completude não foi verificada.", "Horários absolutos por janela; não usar seu primeiro evento como origem do link."]}


def doctor(config, live):
    tools = {name: bool(shutil.which(name)) for name in ("gcloud", "cloud-sql-proxy", "posthog-cli")}
    report = {"time_sp": datetime.now(SP).strftime("%d/%m/%Y %H:%M:%S"), "python": sys.version.split()[0], "tools": tools, "pymysql": importlib.util.find_spec("pymysql") is not None, "venv_bootstrap_available": importlib.util.find_spec("ensurepip") is not None, "infisical_required": False, "google_application_credentials_set": bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")), "clickhouse_password_injected": bool(os.environ.get("INCIDENT_CLICKHOUSE_PASSWORD")), "checks": {}}
    checks = report["checks"]
    if not live:
        report["live_verified"] = False
        return report
    probes = {
        "gcloud_login": lambda: {"authenticated": bool(command(["gcloud", "auth", "print-access-token"]).strip())},
        "adc": lambda: {"authenticated": bool(command(["gcloud", "auth", "application-default", "print-access-token"]).strip())},
        "clickhouse": lambda: clickhouse(config, "SELECT 1 AS ok, currentUser() AS identity", 2),
        "mysql": lambda: mysql(config, "SELECT 1 AS ok, CURRENT_USER() AS identity", 2),
        "posthog": lambda: project_probe(config),
    }
    for project in config["gcp"]["log_projects"]:
        probes["logs:" + project] = lambda project=project: {"read_authorized": True, "sample_records": len(json.loads(command(["gcloud", "logging", "read", 'timestamp>="' + datetime.now().astimezone().isoformat() + '"', "--project", project, "--limit", "1", "--format=json(timestamp)"]))) }
    for name, probe in probes.items():
        try:
            checks[name] = {"status": "ok", "detail": probe()}
        except (LabError, ValueError, KeyError, OSError) as error:
            checks[name] = {"status": "blocked", "detail": str(error) if isinstance(error, LabError) else "Resposta incompatível; conferir configuração/schema."}
    report["live_verified"] = all(check["status"] == "ok" for check in checks.values())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(SKILL / "config.example.json"))
    sub = parser.add_subparsers(dest="action", required=True)
    diag = sub.add_parser("doctor")
    diag.add_argument("--live", action="store_true")
    for name in ("clickhouse", "mysql"):
        query = sub.add_parser(name)
        query.add_argument("--limit", type=int, default=100)
        query.add_argument("--sql-file", help="Sem este argumento, SQL vem de stdin.")
    meta = sub.add_parser("replay-metadata")
    meta.add_argument("session_id")
    link = sub.add_parser("replay-link")
    link.add_argument("--base-url", required=True)
    link.add_argument("--start", required=True)
    link.add_argument("--error", required=True)
    link.add_argument("--end")
    link.add_argument("--before", type=float, default=10)
    summary = sub.add_parser("replay-summary")
    summary.add_argument("events_file")
    args = parser.parse_args()
    try:
        if args.action == "replay-link":
            result = replay_link(args.base_url, args.start, args.error, args.end, args.before)
        elif args.action == "replay-summary":
            result = replay_summary(args.events_file)
        else:
            config = load_config(args.config)
            if args.action == "doctor":
                result = doctor(config, args.live)
            elif args.action == "replay-metadata":
                result = replay_metadata(config, args.session_id)
            else:
                if not 1 <= args.limit <= 1000:
                    raise LabError("limit deve estar entre 1 e 1000.")
                sql = Path(args.sql_file).read_text() if args.sql_file else sys.stdin.read()
                result = globals()[args.action](config, sql, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        if args.action == "doctor" and args.live and not result["live_verified"]:
            return 2
    except (LabError, ValueError, KeyError, OSError):
        # Traceback e respostas privadas não entram no output de uma automação.
        error = sys.exception()
        print(json.dumps({"status": "blocked", "error": str(error) if isinstance(error, LabError) else "Entrada ou resposta inválida; confira configuração/schema."}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
