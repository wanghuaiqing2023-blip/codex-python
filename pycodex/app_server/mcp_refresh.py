"""MCP refresh queueing for ``codex-app-server/src/mcp_refresh.rs``."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from inspect import isawaitable
from pathlib import Path
from typing import Any

from pycodex.protocol import McpServerRefreshConfig, Op

JsonValue = Any


class McpRefreshError(OSError):
    """Error wrapper mirroring Rust's ``io::Error::other`` messages."""


async def queue_strict_refresh(thread_manager: Any, config_manager: Any) -> None:
    """Reload config and queue MCP refresh for every loaded thread.

    Rust first validates/builds every per-thread refresh config, then queues the
    collected refresh ops. That two-phase shape is observable when a later
    thread fails planning: no earlier thread receives an op.
    """

    await _maybe_await(config_manager.load_latest_config(None))
    refreshes: list[tuple[str, Any, McpServerRefreshConfig]] = []
    for thread_id in await _maybe_await(thread_manager.list_thread_ids()):
        try:
            thread = await _maybe_await(thread_manager.get_thread(thread_id))
        except Exception as exc:
            raise McpRefreshError(f"failed to load thread {thread_id}: {exc}") from exc
        config = await build_refresh_config(thread_manager, config_manager, await _thread_config(thread))
        refreshes.append((str(thread_id), thread, config))

    for thread_id, thread, config in refreshes:
        await queue_refresh(thread_id, thread, config)


async def queue_best_effort_refresh(thread_manager: Any, config_manager: Any) -> None:
    """Best-effort refresh: warn/skip per-thread failures and keep going."""

    for thread_id in await _maybe_await(thread_manager.list_thread_ids()):
        try:
            thread = await _maybe_await(thread_manager.get_thread(thread_id))
        except Exception:
            continue
        try:
            config = await build_refresh_config(thread_manager, config_manager, await _thread_config(thread))
        except Exception:
            continue
        try:
            await queue_refresh(str(thread_id), thread, config)
        except Exception:
            continue


async def build_refresh_config(
    thread_manager: Any,
    config_manager: Any,
    thread_config: Any,
) -> McpServerRefreshConfig:
    """Build Rust's ``McpServerRefreshConfig`` from latest thread config."""

    config = await _maybe_await(config_manager.load_latest_config_for_thread(thread_config))
    mcp_manager = thread_manager.mcp_manager()
    mcp_servers = await _maybe_await(mcp_manager.configured_servers(config))
    return McpServerRefreshConfig(
        mcp_servers=_to_json(mcp_servers),
        mcp_oauth_credentials_store_mode=_to_json(getattr(config, "mcp_oauth_credentials_store_mode")),
    )


async def queue_refresh(thread_id: str, thread: Any, config: McpServerRefreshConfig) -> None:
    """Submit Rust's ``Op::RefreshMcpServers`` and map submit failures."""

    try:
        await _maybe_await(thread.submit(Op.refresh_mcp_servers(config)))
    except Exception as exc:
        raise McpRefreshError(f"failed to queue MCP refresh for thread {thread_id}: {exc}") from exc


async def _thread_config(thread: Any) -> Any:
    config = thread.config()
    return await _maybe_await(config)


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


def _to_json(value: Any) -> JsonValue:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        to_mapping = getattr(value, "to_mapping", None)
        if callable(to_mapping):
            return _to_json(to_mapping())
        return {key: _to_json(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _to_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_to_json(item) for item in value]
    return copy.deepcopy(value)


__all__ = [
    "McpRefreshError",
    "build_refresh_config",
    "queue_best_effort_refresh",
    "queue_refresh",
    "queue_strict_refresh",
]
