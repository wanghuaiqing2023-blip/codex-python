from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from pycodex.app_server import run_main
from pycodex.app_server import analytics_utils, extensions


@pytest.mark.asyncio
async def test_stdio_startup_invokes_rust_owned_analytics_and_extension_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def wrap(module, name: str) -> None:
        original = getattr(module, name)

        def recording_wrapper(*args, **kwargs):
            calls.append(name)
            return original(*args, **kwargs)

        monkeypatch.setattr(module, name, recording_wrapper)

    wrap(analytics_utils, "analytics_events_client_from_config")
    wrap(extensions, "guardian_agent_spawner")
    wrap(extensions, "app_server_extension_event_sink")
    wrap(extensions, "thread_extensions")

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    request = {
        "id": 1,
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "chain-test", "version": "1.0"},
            "capabilities": {},
        },
    }
    stdout = StringIO()

    await run_main(
        arg0_paths=object(),
        cli_config_overrides={},
        loader_overrides={"codex_home": codex_home},
        strict_config=False,
        default_analytics_enabled=False,
        stdin=StringIO(json.dumps(request) + "\n"),
        stdout=stdout,
    )

    assert set(calls) == {
        "analytics_events_client_from_config",
        "guardian_agent_spawner",
        "app_server_extension_event_sink",
        "thread_extensions",
    }
    assert json.loads(stdout.getvalue())["id"] == 1
