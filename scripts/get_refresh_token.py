#!/usr/bin/env python3
"""
Script interativo para obter o GOOGLE_ANALYTICS_REFRESH_TOKEN via OAuth2.

Pré-requisitos:
  1. Projeto criado no Google Cloud Console com a "Google Analytics Data API" habilitada
  2. Credenciais OAuth2 (Client ID e Client Secret) do tipo "Desktop app"
  3. Sua conta Google com acesso à propriedade GA4

Uso:
  python scripts/get_refresh_token.py
"""

import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

try:
    import httpx
except ImportError:
    print("❌ httpx não instalado. Execute: uv sync")
    sys.exit(1)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

# Variável global para capturar o code do callback
_auth_code: str | None = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        global _auth_code
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>Autorizacao concluida!</h2>"
                b"<p>Pode fechar esta aba e voltar ao terminal.</p>"
            )
        else:
            error = params.get("error", ["desconhecido"])[0]
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"Erro: {error}".encode())

    def log_message(self, *args):  # silencia logs do servidor
        pass


def main():
    print("=" * 60)
    print("  Google Analytics OAuth2 — Geração de Refresh Token")
    print("=" * 60)
    print()

    client_id = input("Client ID (do Google Cloud Console): ").strip()
    client_secret = input("Client Secret: ").strip()

    if not client_id or not client_secret:
        print("❌ Client ID e Client Secret são obrigatórios.")
        sys.exit(1)

    # Monta a URL de autorização
    auth_params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",  # garante que o refresh_token seja retornado
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(auth_params)}"

    print(f"\n🌐 Abrindo navegador para autenticação...")
    print(f"   Se não abrir automaticamente, acesse:\n   {auth_url}\n")
    webbrowser.open(auth_url)

    # Sobe servidor temporário na porta 8080 para capturar o callback
    print("⏳ Aguardando callback em http://localhost:8080/callback ...")
    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()  # processa apenas uma requisição

    if not _auth_code:
        print("❌ Não foi possível capturar o código de autorização.")
        sys.exit(1)

    print("✅ Código de autorização recebido.")

    # Troca o code pelo refresh_token
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": _auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    tokens = response.json()

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("❌ Refresh token não retornado. Verifique se 'prompt=consent' está na URL.")
        print(f"   Resposta: {tokens}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  ✅ Refresh Token obtido com sucesso!")
    print("=" * 60)
    print(f"\nAdicione ao seu .env:\n")
    print(f"GOOGLE_ANALYTICS_CLIENT_ID={client_id}")
    print(f"GOOGLE_ANALYTICS_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_ANALYTICS_REFRESH_TOKEN={refresh_token}")
    print()
    print("⚠️  Guarde o refresh token com segurança — ele não expira")
    print("   (a menos que seja revogado manualmente).")


if __name__ == "__main__":
    main()
