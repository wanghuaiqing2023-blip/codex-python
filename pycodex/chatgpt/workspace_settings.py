"""Workspace setting lookup and cache owned by ``workspace_settings.rs``."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

from .chatgpt_client import chatgpt_get_request_with_timeout

WORKSPACE_SETTINGS_TIMEOUT = 10.0
WORKSPACE_SETTINGS_CACHE_TTL = 15.0 * 60.0
CODEX_PLUGINS_BETA_SETTING = "enable_plugins"


@dataclass(frozen=True)
class _WorkspaceSettingsCacheKey:
    chatgpt_base_url: str
    account_id: str


@dataclass(frozen=True)
class _CachedWorkspaceSettings:
    key: _WorkspaceSettingsCacheKey
    expires_at: float
    codex_plugins_enabled: bool


class WorkspaceSettingsCache:
    def __init__(self) -> None:
        self._entry: _CachedWorkspaceSettings | None = None
        self._lock = threading.RLock()

    def get_codex_plugins_enabled(
        self,
        key: _WorkspaceSettingsCacheKey,
    ) -> bool | None:
        with self._lock:
            now = time.monotonic()
            if (
                self._entry is not None
                and now < self._entry.expires_at
                and self._entry.key == key
            ):
                return self._entry.codex_plugins_enabled
            if (
                self._entry is not None
                and (now >= self._entry.expires_at or self._entry.key != key)
            ):
                self._entry = None
            return None

    def set_codex_plugins_enabled(
        self,
        key: _WorkspaceSettingsCacheKey,
        enabled: bool,
    ) -> None:
        with self._lock:
            self._entry = _CachedWorkspaceSettings(
                key=key,
                expires_at=time.monotonic() + WORKSPACE_SETTINGS_CACHE_TTL,
                codex_plugins_enabled=bool(enabled),
            )

    async def codex_plugins_enabled_for_workspace(
        self,
        config: Any,
        auth: Any | None,
    ) -> bool:
        return await codex_plugins_enabled_for_workspace(config, auth, self)


async def codex_plugins_enabled_for_workspace(
    config: Any,
    auth: Any | None,
    cache: WorkspaceSettingsCache | None,
) -> bool:
    if auth is None or not auth.is_chatgpt_auth():
        return True

    try:
        token_data = auth.get_token_data()
    except Exception as exc:
        raise RuntimeError("ChatGPT token data is not available") from exc
    if not token_data.id_token.is_workspace_account():
        return True

    account_id = token_data.account_id
    if not isinstance(account_id, str) or not account_id:
        return True

    cache_key = _WorkspaceSettingsCacheKey(
        chatgpt_base_url=str(getattr(config, "chatgpt_base_url")),
        account_id=account_id,
    )
    if cache is not None:
        cached = cache.get_codex_plugins_enabled(cache_key)
        if cached is not None:
            return cached

    settings = await chatgpt_get_request_with_timeout(
        config,
        f"/accounts/{encode_path_segment(account_id)}/settings",
        WORKSPACE_SETTINGS_TIMEOUT,
    )
    if not isinstance(settings, Mapping):
        raise TypeError("workspace settings response must be an object")
    beta_settings = settings.get("beta_settings", {})
    if not isinstance(beta_settings, Mapping):
        beta_settings = {}
    enabled = bool(beta_settings.get(CODEX_PLUGINS_BETA_SETTING, True))
    if cache is not None:
        cache.set_codex_plugins_enabled(cache_key, enabled)
    return enabled


def encode_path_segment(value: str) -> str:
    encoded: list[str] = []
    for byte in value.encode("utf-8"):
        char = chr(byte)
        if (
            0x30 <= byte <= 0x39
            or 0x41 <= byte <= 0x5A
            or 0x61 <= byte <= 0x7A
            or char in "-._~"
        ):
            encoded.append(char)
        else:
            encoded.append(f"%{byte:02X}")
    return "".join(encoded)


__all__ = [
    "CODEX_PLUGINS_BETA_SETTING",
    "WORKSPACE_SETTINGS_CACHE_TTL",
    "WORKSPACE_SETTINGS_TIMEOUT",
    "WorkspaceSettingsCache",
    "codex_plugins_enabled_for_workspace",
    "encode_path_segment",
]
