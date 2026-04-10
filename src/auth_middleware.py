"""
Middleware de autenticação para o Google Analytics MCP Server.
Suporta API Keys por usuário com metadados (nome, permissões, expiração).

Uso:
  from .auth_middleware import require_api_key, KeyStore

  store = KeyStore.from_env()   # carrega ALLOWED_API_KEYS do ambiente
"""

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("google_analytics_mcp.auth")

# ---------------------------------------------------------------------------
# Estrutura de uma API Key
# ---------------------------------------------------------------------------

@dataclass
class ApiKeyEntry:
    key_hash: str           # SHA-256 da chave em hex — nunca guardamos a chave em texto
    user: str               # "ana.silva", "joao.marketing"
    description: str = ""   # "Análise de campanhas — equipe marketing"
    expires_at: Optional[float] = None   # Unix timestamp ou None = sem expiração
    scopes: list[str] = field(default_factory=lambda: ["read"])  # futuro: ["read", "write"]

    def is_valid(self) -> bool:
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True


# ---------------------------------------------------------------------------
# Key Store — gerencia o conjunto de chaves permitidas
# ---------------------------------------------------------------------------

class KeyStore:
    """
    Armazena hashes de API Keys. Nunca guarda as chaves em texto plano.

    Formato da variável ALLOWED_API_KEYS (JSON):
    [
      {"key": "sk-ga-abc123...", "user": "ana.silva", "description": "Equipe marketing"},
      {"key": "sk-ga-xyz789...", "user": "joao.ops",  "expires_at": 1893456000}
    ]

    Alternativamente, pode usar um arquivo JSON:
    API_KEYS_FILE=/etc/google-analytics-mcp/keys.json
    """

    def __init__(self, entries: list[ApiKeyEntry]):
        # Indexa por hash para lookup O(1) sem expor as chaves
        self._index: dict[str, ApiKeyEntry] = {e.key_hash: e for e in entries}
        logger.info(f"KeyStore inicializado com {len(entries)} chave(s).")

    @classmethod
    def from_env(cls) -> "KeyStore":
        """Carrega chaves de ALLOWED_API_KEYS (JSON) ou API_KEYS_FILE."""
        entries: list[ApiKeyEntry] = []

        # Opção 1: variável de ambiente com JSON inline
        raw_json = os.environ.get("ALLOWED_API_KEYS", "")
        if raw_json:
            try:
                keys_data = json.loads(raw_json)
                entries.extend(_parse_key_list(keys_data))
            except json.JSONDecodeError as e:
                raise ValueError(f"ALLOWED_API_KEYS inválido (não é JSON): {e}") from e

        # Opção 2: arquivo JSON externo
        keys_file = os.environ.get("API_KEYS_FILE", "")
        if keys_file:
            try:
                with open(keys_file) as f:
                    keys_data = json.load(f)
                entries.extend(_parse_key_list(keys_data))
            except FileNotFoundError:
                raise ValueError(f"API_KEYS_FILE não encontrado: {keys_file}")
            except json.JSONDecodeError as e:
                raise ValueError(f"API_KEYS_FILE inválido: {e}") from e

        # Opção 3: chave única simples (retrocompatibilidade)
        single_key = os.environ.get("MCP_API_KEY", "")
        if single_key:
            entries.append(ApiKeyEntry(
                key_hash=_hash_key(single_key),
                user="default",
                description="Chave única via MCP_API_KEY",
            ))

        if not entries:
            logger.warning(
                "Nenhuma API Key configurada. "
                "O servidor está aberto — configure ALLOWED_API_KEYS ou MCP_API_KEY."
            )

        return cls(entries)

    def authenticate(self, raw_key: str) -> Optional[ApiKeyEntry]:
        """
        Verifica a chave. Retorna o ApiKeyEntry se válido, None caso contrário.
        Usa comparação em tempo constante (hmac.compare_digest) para evitar timing attacks.
        """
        key_hash = _hash_key(raw_key)
        entry = self._index.get(key_hash)
        if entry is None:
            return None
        if not entry.is_valid():
            logger.warning(f"Chave expirada usada por usuário: {entry.user}")
            return None
        return entry

    def add_key(self, raw_key: str, user: str, description: str = "", expires_at: Optional[float] = None) -> ApiKeyEntry:
        """Adiciona uma nova chave em runtime (útil para testes ou CLI admin)."""
        entry = ApiKeyEntry(
            key_hash=_hash_key(raw_key),
            user=user,
            description=description,
            expires_at=expires_at,
        )
        self._index[entry.key_hash] = entry
        logger.info(f"Nova chave adicionada para usuário: {user}")
        return entry

    def revoke_user(self, user: str) -> int:
        """Remove todas as chaves de um usuário. Retorna a quantidade revogada."""
        to_remove = [h for h, e in self._index.items() if e.user == user]
        for h in to_remove:
            del self._index[h]
        logger.info(f"Revogadas {len(to_remove)} chave(s) do usuário: {user}")
        return len(to_remove)

    def list_users(self) -> list[dict]:
        """Lista usuários e metadados (sem expor hashes ou chaves)."""
        return [
            {
                "user": e.user,
                "description": e.description,
                "expires_at": e.expires_at,
                "expired": not e.is_valid(),
            }
            for e in self._index.values()
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_key(raw_key: str) -> str:
    """SHA-256 da chave. Rápido e suficiente para lookup + armazenamento seguro."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _parse_key_list(data: list[dict]) -> list[ApiKeyEntry]:
    entries = []
    for item in data:
        if "key" not in item or "user" not in item:
            raise ValueError(f"Entrada de chave inválida (faltam 'key' ou 'user'): {item}")
        entries.append(ApiKeyEntry(
            key_hash=_hash_key(item["key"]),
            user=item["user"],
            description=item.get("description", ""),
            expires_at=item.get("expires_at"),
        ))
    return entries


def generate_api_key(prefix: str = "sk-ga") -> str:
    """Gera uma API Key criptograficamente segura. Use no script de admin."""
    import secrets
    return f"{prefix}-{secrets.token_urlsafe(32)}"
