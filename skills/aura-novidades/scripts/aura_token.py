#!/usr/bin/env python3
"""Imprime o token (JWT) do Aura para a gravação, a partir das credenciais locais do Context.

Credenciais em ~/Projects/context/temp/aura-login.txt (AURA_LOGIN_FILE), duas linhas
`username=…` e `password=…` (CLAUDE.md do Context, "Bater na API do Aura"). Login em
POST {NOV_API}/auth/login (a única rota sem /api/v1). Nunca imprime senha; o token sai só no
stdout, para quem chamou guardar em variável. Não repete depois de 401: credencial expirada ou
conta travada, não payload errado.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("NOV_API", "https://aura.apis.localhost")
ARQUIVO = Path(os.environ.get("AURA_LOGIN_FILE", Path.home() / "Projects/context/temp/aura-login.txt"))


def main() -> None:
    if not ARQUIVO.is_file():
        sys.exit(f"aura_token: {ARQUIVO} não existe (username=… e password=…, ver CLAUDE.md do Context)")
    cred = dict(l.split("=", 1) for l in ARQUIVO.read_text(encoding="utf-8").splitlines() if "=" in l)
    if not cred.get("username") or not cred.get("password"):
        sys.exit(f"aura_token: {ARQUIVO} precisa das chaves username e password")
    corpo = json.dumps({"username": cred["username"].strip(), "password": cred["password"].strip()}).encode()
    pedido = urllib.request.Request(f"{API}/auth/login", data=corpo, headers={"Content-Type": "application/json"})
    # API local do portless: certificado da CA local, confiável via NODE_EXTRA_CA_CERTS/sistema
    contexto = ssl.create_default_context()
    try:
        with urllib.request.urlopen(pedido, context=contexto, timeout=30) as r:
            token = json.loads(r.read()).get("token")
    except urllib.error.HTTPError as erro:
        sys.exit(f"aura_token: login respondeu {erro.code}; não repito (credencial expirada ou conta travada?)")
    if not token:
        sys.exit("aura_token: resposta sem token")
    print(token)


if __name__ == "__main__":
    main()
