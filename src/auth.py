"""
Autenticação OAuth2 para a Google Analytics 4 Data API.
Todas as credenciais são lidas de variáveis de ambiente — nunca hard-coded.
"""

import os
from dataclasses import dataclass
from typing import Optional

import httpx

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
REQUIRED_ENV_VARS = [
    "GOOGLE_ANALYTICS_CLIENT_ID",
    "GOOGLE_ANALYTICS_CLIENT_SECRET",
    "GOOGLE_ANALYTICS_REFRESH_TOKEN",
]


@dataclass
class GoogleAnalyticsAuth:
    client_id: str
    client_secret: str
    refresh_token: str

    # Cache em memória do access token (válido por ~1h)
    _access_token: Optional[str] = None

    @classmethod
    def from_env(cls) -> "GoogleAnalyticsAuth":
        """Cria instância a partir das variáveis de ambiente.

        Lança ValueError descritivo se alguma variável obrigatória estiver ausente.
        """
        missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
        if missing:
            raise ValueError(
                f"Variáveis de ambiente obrigatórias não encontradas: {', '.join(missing)}. "
                "Configure-as antes de iniciar o servidor MCP."
            )

        return cls(
            client_id=os.environ["GOOGLE_ANALYTICS_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_ANALYTICS_CLIENT_SECRET"],
            refresh_token=os.environ["GOOGLE_ANALYTICS_REFRESH_TOKEN"],
        )

    def get_access_token(self) -> str:
        """Troca o refresh_token por um access_token. Usa cache simples em memória."""
        if self._access_token:
            return self._access_token

        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
            timeout=15,
        )
        response.raise_for_status()
        self._access_token = response.json()["access_token"]
        return self._access_token

    def invalidate_token(self) -> None:
        """Limpa o cache do access_token (use após 401)."""
        self._access_token = None

    def build_headers(self) -> dict[str, str]:
        """Headers padrão para chamadas à GA4 Data API."""
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json",
        }
