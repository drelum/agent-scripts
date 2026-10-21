#!/usr/bin/env python3
"""Imprime o token (JWT) do Aura para a gravação.

Credenciais só por ambiente: AURA_USERNAME (CPF, sem pontuação) e AURA_PASSWORD, preenchidas por
quem chama a partir do Infisical (projeto Aitrus Apps, pasta /aura), sem arquivo e sem imprimir.
Login em POST {NOV_API}/auth/login (a única rota sem /api/v1). O token sai só no stdout, para quem
chamou guardar em variável. Não repete depois de 401: credencial expirada ou conta travada.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

API = os.environ.get("NOV_API", "https://aura.apis.localhost")


def main() -> None:
    usuario, senha = os.environ.get("AURA_USERNAME", "").strip(), os.environ.get("AURA_PASSWORD", "")
    if not usuario or not senha:
        sys.exit("aura_token: defina AURA_USERNAME e AURA_PASSWORD (Infisical, Aitrus Apps, /aura); ver referencias/gravador.md")
    corpo = json.dumps({"username": usuario, "password": senha}).encode()
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
