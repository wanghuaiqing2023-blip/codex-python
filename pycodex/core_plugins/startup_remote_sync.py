"""One-shot startup reconciliation for legacy remote plugins.

Rust owner: ``codex-core-plugins::startup_remote_sync``.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

from .startup_sync import has_local_curated_plugins_snapshot

STARTUP_REMOTE_PLUGIN_SYNC_MARKER_FILE = ".tmp/app-server-remote-plugin-sync-v1"
STARTUP_REMOTE_PLUGIN_SYNC_PREREQUISITE_TIMEOUT = 10.0


def start_startup_remote_plugin_sync_once(
    manager: Any,
    codex_home: Path,
    config: Any,
    auth_manager: Any,
) -> asyncio.Task[None] | None:
    codex_home = Path(codex_home)
    marker = _startup_remote_plugin_sync_marker_path(codex_home)
    if marker.is_file():
        return None

    async def run() -> None:
        if marker.is_file():
            return
        if not await _wait_for_prerequisites(codex_home):
            return
        auth = await _maybe_await(auth_manager.auth())
        await _maybe_await(
            manager.sync_plugins_from_remote(
                config,
                auth,
                True,
            )
        )
        marker.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(marker.write_text, "ok\n", encoding="utf-8")

    return asyncio.create_task(run())


def _startup_remote_plugin_sync_marker_path(codex_home: Path) -> Path:
    return codex_home / STARTUP_REMOTE_PLUGIN_SYNC_MARKER_FILE


async def _wait_for_prerequisites(codex_home: Path) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + STARTUP_REMOTE_PLUGIN_SYNC_PREREQUISITE_TIMEOUT
    while True:
        if has_local_curated_plugins_snapshot(codex_home):
            return True
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(0.05)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "STARTUP_REMOTE_PLUGIN_SYNC_MARKER_FILE",
    "STARTUP_REMOTE_PLUGIN_SYNC_PREREQUISITE_TIMEOUT",
    "start_startup_remote_plugin_sync_once",
]
