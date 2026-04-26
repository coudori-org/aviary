"""Loader for the project-root config.yaml ``secrets:`` section.

Used as a Vault fallback when ``VAULT_ADDR`` is unset (single-machine dev
without an actual Vault). Layout mirrors the Vault path convention
``secret/aviary/credentials/{sub}/{namespace}/{key_name}``::

    secrets:
      dev-user:
        aviary:
          anthropic-api-key: sk-...
          github-token: ghp_...
        jira:
          jira-token: you@example.com:atlassian-api-token
"""

from __future__ import annotations

from pathlib import Path

import yaml


class ConfigSecrets:
    def __init__(self, table: dict[str, dict[str, dict[str, str]]]) -> None:
        self._table = table

    def lookup(self, user_external_id: str, namespace: str, key_name: str) -> str | None:
        user = self._table.get(user_external_id) or {}
        ns = user.get(namespace) or {}
        return ns.get(key_name)

    def list_namespaces(self, user_external_id: str) -> list[str]:
        return list((self._table.get(user_external_id) or {}).keys())

    def list_keys(self, user_external_id: str, namespace: str) -> list[str]:
        ns = (self._table.get(user_external_id) or {}).get(namespace) or {}
        return list(ns.keys())


def load_secrets(path: str | Path) -> ConfigSecrets:
    p = Path(path)
    if not p.exists():
        return ConfigSecrets({})
    raw = yaml.safe_load(p.read_text()) or {}
    table = raw.get("secrets") or {}
    if not isinstance(table, dict):
        return ConfigSecrets({})
    cleaned: dict[str, dict[str, dict[str, str]]] = {}
    for sub, namespaces in table.items():
        if not isinstance(namespaces, dict):
            continue
        per_user: dict[str, dict[str, str]] = {}
        for ns, entries in namespaces.items():
            if isinstance(entries, dict):
                per_user[str(ns)] = {str(k): str(v) for k, v in entries.items()}
        cleaned[str(sub)] = per_user
    return ConfigSecrets(cleaned)
