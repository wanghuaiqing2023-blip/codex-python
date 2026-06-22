"""Directory disk cache aligned with ``codex-rs/connectors/src/directory_cache.rs``."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server_protocol.apps import AppInfo

JsonValue = Any

CONNECTOR_DIRECTORY_DISK_CACHE_SCHEMA_VERSION = 1
CONNECTOR_DIRECTORY_DISK_CACHE_DIR = "cache/codex_app_directory"


@dataclass(frozen=True)
class ConnectorDirectoryCacheKey:
    chatgpt_base_url: str
    account_id: str | None
    chatgpt_user_id: str | None
    is_workspace_account: bool

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "chatgpt_base_url": self.chatgpt_base_url,
            "account_id": self.account_id,
            "chatgpt_user_id": self.chatgpt_user_id,
            "is_workspace_account": self.is_workspace_account,
        }


@dataclass(frozen=True)
class ConnectorDirectoryCacheContext:
    codex_home: Path
    cache_key: ConnectorDirectoryCacheKey

    def __init__(self, codex_home: str | Path, cache_key: ConnectorDirectoryCacheKey) -> None:
        object.__setattr__(self, "codex_home", Path(codex_home))
        object.__setattr__(self, "cache_key", cache_key)

    def cache_path(self) -> Path:
        cache_key_json = json.dumps(
            self.cache_key.to_mapping(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        cache_key_hash = hashlib.sha1(cache_key_json.encode("utf-8")).hexdigest()
        return self.codex_home / CONNECTOR_DIRECTORY_DISK_CACHE_DIR / f"{cache_key_hash}.json"


def load_cached_directory_connectors_from_disk(
    cache_context: ConnectorDirectoryCacheContext,
) -> list[AppInfo] | None:
    cache_path = cache_context.cache_path()
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        _remove_file(cache_path)
        return None
    if not isinstance(data, dict):
        _remove_file(cache_path)
        return None
    if data.get("schema_version") != CONNECTOR_DIRECTORY_DISK_CACHE_SCHEMA_VERSION:
        _remove_file(cache_path)
        return None
    try:
        return [AppInfo.from_mapping(item) for item in data.get("connectors", ())]
    except Exception:
        _remove_file(cache_path)
        return None


def write_cached_directory_connectors_to_disk(
    cache_context: ConnectorDirectoryCacheContext,
    connectors: list[AppInfo],
) -> None:
    cache_path = cache_context.cache_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "schema_version": CONNECTOR_DIRECTORY_DISK_CACHE_SCHEMA_VERSION,
                    "connectors": [connector.to_mapping() for connector in connectors],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        return


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


__all__ = [
    "CONNECTOR_DIRECTORY_DISK_CACHE_DIR",
    "CONNECTOR_DIRECTORY_DISK_CACHE_SCHEMA_VERSION",
    "ConnectorDirectoryCacheContext",
    "ConnectorDirectoryCacheKey",
    "load_cached_directory_connectors_from_disk",
    "write_cached_directory_connectors_to_disk",
]
