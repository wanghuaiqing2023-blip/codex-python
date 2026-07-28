"""MCP OAuth credential persistence."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pycodex.config.types import OAuthCredentialsStoreMode
from pycodex.keyring_store import CredentialStoreError, DefaultKeyringStore
from pycodex.utils.home_dir import find_codex_home

KEYRING_SERVICE = "Codex MCP Credentials"
REFRESH_SKEW_MILLIS = 30_000
FALLBACK_FILENAME = ".credentials.json"
MCP_SERVER_TYPE = "http"

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class OAuthTokenResponse:
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scopes: tuple[str, ...] = ()
    extra_fields: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WrappedOAuthTokenResponse:
    response: OAuthTokenResponse


@dataclass(frozen=True)
class StoredOAuthTokens:
    server_name: str
    url: str
    client_id: str
    token_response: WrappedOAuthTokenResponse
    expires_at: int | None = None


def _store_mode(value: OAuthCredentialsStoreMode | str | None) -> OAuthCredentialsStoreMode:
    return OAuthCredentialsStoreMode(value or OAuthCredentialsStoreMode.AUTO)


def _token_to_dict(response: OAuthTokenResponse) -> dict[str, Any]:
    value: dict[str, Any] = {
        "access_token": response.access_token,
        "token_type": response.token_type,
    }
    if response.expires_in is not None:
        value["expires_in"] = response.expires_in
    if response.refresh_token is not None:
        value["refresh_token"] = response.refresh_token
    if response.scopes:
        value["scopes"] = list(response.scopes)
    if response.extra_fields:
        value["extra_fields"] = dict(response.extra_fields)
    return value


def _token_from_dict(value: Mapping[str, Any]) -> OAuthTokenResponse:
    scopes = value.get("scopes", ())
    if isinstance(scopes, str):
        scopes = scopes.split()
    return OAuthTokenResponse(
        access_token=str(value["access_token"]),
        token_type=str(value.get("token_type", "Bearer")),
        expires_in=(
            None
            if value.get("expires_in") is None
            else int(value["expires_in"])
        ),
        refresh_token=(
            None
            if value.get("refresh_token") is None
            else str(value["refresh_token"])
        ),
        scopes=tuple(str(scope) for scope in scopes),
        extra_fields=(
            dict(value["extra_fields"])
            if isinstance(value.get("extra_fields"), Mapping)
            else None
        ),
    )


def _stored_to_dict(tokens: StoredOAuthTokens) -> dict[str, Any]:
    return {
        "server_name": tokens.server_name,
        "url": tokens.url,
        "client_id": tokens.client_id,
        "token_response": _token_to_dict(tokens.token_response.response),
        "expires_at": tokens.expires_at,
    }


def _stored_from_dict(value: Mapping[str, Any]) -> StoredOAuthTokens:
    return StoredOAuthTokens(
        server_name=str(value["server_name"]),
        url=str(value["url"]),
        client_id=str(value["client_id"]),
        token_response=WrappedOAuthTokenResponse(
            _token_from_dict(value["token_response"])
        ),
        expires_at=(
            None
            if value.get("expires_at") is None
            else int(value["expires_at"])
        ),
    )


def compute_expires_at_millis(response: OAuthTokenResponse) -> int | None:
    if response.expires_in is None:
        return None
    return min(
        (1 << 64) - 1,
        int(time.time() * 1000) + max(0, int(response.expires_in)) * 1000,
    )


def _refresh_expires_in_from_timestamp(tokens: StoredOAuthTokens) -> StoredOAuthTokens:
    if tokens.expires_at is None:
        return tokens
    remaining_ms = tokens.expires_at - int(time.time() * 1000)
    expires_in = remaining_ms // 1000 if remaining_ms > 0 else None
    response = replace(tokens.token_response.response, expires_in=expires_in)
    return replace(
        tokens,
        token_response=WrappedOAuthTokenResponse(response),
    )


def token_needs_refresh(expires_at: int | None) -> bool:
    return (
        expires_at is not None
        and int(time.time() * 1000) + REFRESH_SKEW_MILLIS >= expires_at
    )


def compute_store_key(server_name: str, server_url: str) -> str:
    payload = {
        "type": MCP_SERVER_TYPE,
        "url": str(server_url),
        "headers": {},
    }
    serialized = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )
    prefix = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"{server_name}|{prefix}"


def _fallback_file_path() -> Path:
    return find_codex_home() / FALLBACK_FILENAME


def _read_fallback_file() -> dict[str, Any] | None:
    path = _fallback_file_path()
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"credentials file at {path} must contain an object")
    return value


def _write_fallback_file(store: Mapping[str, Any]) -> None:
    path = _fallback_file_path()
    if not store:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(store, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    if os.name != "nt":
        path.chmod(0o600)


def _load_oauth_tokens_from_file(
    server_name: str,
    url: str,
) -> StoredOAuthTokens | None:
    store = _read_fallback_file()
    if store is None:
        return None
    key = compute_store_key(server_name, url)
    for entry in store.values():
        if not isinstance(entry, Mapping):
            continue
        entry_name = str(entry.get("server_name", ""))
        entry_url = str(entry.get("server_url", ""))
        if compute_store_key(entry_name, entry_url) != key:
            continue
        response = OAuthTokenResponse(
            access_token=str(entry["access_token"]),
            refresh_token=(
                None
                if entry.get("refresh_token") is None
                else str(entry["refresh_token"])
            ),
            expires_in=None,
            scopes=tuple(str(scope) for scope in entry.get("scopes", ())),
        )
        return _refresh_expires_in_from_timestamp(
            StoredOAuthTokens(
                entry_name,
                entry_url,
                str(entry.get("client_id", "")),
                WrappedOAuthTokenResponse(response),
                (
                    None
                    if entry.get("expires_at") is None
                    else int(entry["expires_at"])
                ),
            )
        )
    return None


def _save_oauth_tokens_to_file(tokens: StoredOAuthTokens) -> None:
    key = compute_store_key(tokens.server_name, tokens.url)
    store = _read_fallback_file() or {}
    response = tokens.token_response.response
    store[key] = {
        "server_name": tokens.server_name,
        "server_url": tokens.url,
        "client_id": tokens.client_id,
        "access_token": response.access_token,
        "expires_at": (
            tokens.expires_at
            if tokens.expires_at is not None
            else compute_expires_at_millis(response)
        ),
        "refresh_token": response.refresh_token,
        "scopes": list(response.scopes),
    }
    _write_fallback_file(store)


def _delete_oauth_tokens_from_file(key: str) -> bool:
    store = _read_fallback_file()
    if store is None:
        return False
    removed = store.pop(key, None) is not None
    if removed:
        _write_fallback_file(store)
    return removed


def _load_from_keyring(
    keyring_store: Any,
    server_name: str,
    url: str,
) -> StoredOAuthTokens | None:
    serialized = keyring_store.load(
        KEYRING_SERVICE,
        compute_store_key(server_name, url),
    )
    if serialized is None:
        return None
    return _refresh_expires_in_from_timestamp(
        _stored_from_dict(json.loads(serialized))
    )


def load_oauth_tokens(
    server_name: str,
    url: str,
    store_mode: OAuthCredentialsStoreMode | str = OAuthCredentialsStoreMode.AUTO,
) -> StoredOAuthTokens | None:
    mode = _store_mode(store_mode)
    keyring = DefaultKeyringStore()
    if mode is OAuthCredentialsStoreMode.FILE:
        return _load_oauth_tokens_from_file(server_name, url)
    if mode is OAuthCredentialsStoreMode.KEYRING:
        return _load_from_keyring(keyring, server_name, url)
    try:
        tokens = _load_from_keyring(keyring, server_name, url)
        return tokens if tokens is not None else _load_oauth_tokens_from_file(server_name, url)
    except Exception as exc:
        _LOG.warning("failed to read OAuth tokens from keyring: %s", exc)
        return _load_oauth_tokens_from_file(server_name, url)


def has_oauth_tokens(
    server_name: str,
    url: str,
    store_mode: OAuthCredentialsStoreMode | str = OAuthCredentialsStoreMode.AUTO,
) -> bool:
    return load_oauth_tokens(server_name, url, store_mode) is not None


def _save_to_keyring(
    keyring_store: Any,
    server_name: str,
    tokens: StoredOAuthTokens,
) -> None:
    key = compute_store_key(server_name, tokens.url)
    keyring_store.save(
        KEYRING_SERVICE,
        key,
        json.dumps(
            _stored_to_dict(tokens),
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    )
    try:
        _delete_oauth_tokens_from_file(key)
    except Exception as exc:
        _LOG.warning(
            "failed to remove OAuth tokens from fallback storage: %s",
            exc,
        )


def save_oauth_tokens(
    server_name: str,
    tokens: StoredOAuthTokens,
    store_mode: OAuthCredentialsStoreMode | str = OAuthCredentialsStoreMode.AUTO,
) -> None:
    mode = _store_mode(store_mode)
    if mode is OAuthCredentialsStoreMode.FILE:
        _save_oauth_tokens_to_file(tokens)
        return
    keyring = DefaultKeyringStore()
    if mode is OAuthCredentialsStoreMode.KEYRING:
        _save_to_keyring(keyring, server_name, tokens)
        return
    try:
        _save_to_keyring(keyring, server_name, tokens)
    except Exception as exc:
        _LOG.warning(
            "falling back to file storage for OAuth tokens: %s",
            exc,
        )
        _save_oauth_tokens_to_file(tokens)


def delete_oauth_tokens(
    server_name: str,
    url: str,
    store_mode: OAuthCredentialsStoreMode | str = OAuthCredentialsStoreMode.AUTO,
) -> bool:
    mode = _store_mode(store_mode)
    key = compute_store_key(server_name, url)
    keyring_removed = False
    try:
        keyring_removed = DefaultKeyringStore().delete(KEYRING_SERVICE, key)
    except Exception:
        if mode is not OAuthCredentialsStoreMode.FILE:
            raise
    file_removed = _delete_oauth_tokens_from_file(key)
    return keyring_removed or file_removed


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class OAuthPersistor:
    def __init__(
        self,
        server_name: str,
        url: str,
        authorization_manager: Any,
        store_mode: OAuthCredentialsStoreMode | str,
        initial_credentials: StoredOAuthTokens | None,
    ) -> None:
        self.server_name = str(server_name)
        self.url = str(url)
        self.authorization_manager = authorization_manager
        self.store_mode = _store_mode(store_mode)
        self.last_credentials = initial_credentials

    async def persist_if_needed(self) -> None:
        client_id, credentials = await _maybe_await(
            self.authorization_manager.get_credentials()
        )
        if credentials is None:
            if self.last_credentials is not None:
                self.last_credentials = None
                try:
                    delete_oauth_tokens(
                        self.server_name,
                        self.url,
                        self.store_mode,
                    )
                except Exception as exc:
                    _LOG.warning(
                        "failed to remove OAuth tokens for server %s: %s",
                        self.server_name,
                        exc,
                    )
            return
        wrapped = WrappedOAuthTokenResponse(credentials)
        same_token = (
            self.last_credentials is not None
            and self.last_credentials.token_response == wrapped
        )
        expires_at = (
            self.last_credentials.expires_at
            if same_token and self.last_credentials is not None
            else compute_expires_at_millis(credentials)
        )
        stored = StoredOAuthTokens(
            self.server_name,
            self.url,
            str(client_id),
            wrapped,
            expires_at,
        )
        if stored != self.last_credentials:
            save_oauth_tokens(self.server_name, stored, self.store_mode)
            self.last_credentials = stored

    async def refresh_if_needed(self) -> None:
        expires_at = (
            None
            if self.last_credentials is None
            else self.last_credentials.expires_at
        )
        if not token_needs_refresh(expires_at):
            return
        await _maybe_await(self.authorization_manager.refresh_token())
        await self.persist_if_needed()


__all__ = [
    "OAuthPersistor",
    "OAuthTokenResponse",
    "StoredOAuthTokens",
    "WrappedOAuthTokenResponse",
    "compute_expires_at_millis",
    "compute_store_key",
    "delete_oauth_tokens",
    "has_oauth_tokens",
    "load_oauth_tokens",
    "save_oauth_tokens",
    "token_needs_refresh",
]
