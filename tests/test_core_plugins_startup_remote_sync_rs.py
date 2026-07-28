from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest


class _Manager:
    def __init__(self) -> None:
        self.calls = 0

    async def sync_plugins_from_remote(
        self,
        config: object,
        auth: object,
        additive_only: bool,
    ) -> object:
        self.calls += 1
        assert additive_only is True
        return SimpleNamespace()


class _AuthManager:
    async def auth(self) -> object:
        return object()


@pytest.mark.asyncio
async def test_startup_remote_sync_writes_marker_and_only_runs_once(
    tmp_path: Path,
) -> None:
    from pycodex.core_plugins.startup_remote_sync import (
        STARTUP_REMOTE_PLUGIN_SYNC_MARKER_FILE,
        start_startup_remote_plugin_sync_once,
    )

    manifest = (
        tmp_path / ".tmp" / "plugins" / ".agents" / "plugins" / "marketplace.json"
    )
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}\n", encoding="utf-8")
    (tmp_path / ".tmp" / "plugins.sha").write_text("abc\n", encoding="utf-8")

    manager = _Manager()
    task = start_startup_remote_plugin_sync_once(
        manager,
        tmp_path,
        object(),
        _AuthManager(),
    )
    assert task is not None
    await task

    marker = tmp_path / STARTUP_REMOTE_PLUGIN_SYNC_MARKER_FILE
    assert marker.read_text(encoding="utf-8") == "ok\n"
    assert manager.calls == 1
    assert (
        start_startup_remote_plugin_sync_once(
            manager,
            tmp_path,
            object(),
            _AuthManager(),
        )
        is None
    )
    await asyncio.sleep(0)
    assert manager.calls == 1
