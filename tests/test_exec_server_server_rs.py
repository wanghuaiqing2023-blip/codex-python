from __future__ import annotations

import asyncio

import pycodex.exec_server as exec_server
from pycodex.exec_server import (
    DEFAULT_LISTEN_URL,
    ExecServerListenUrlParseError,
    ExecServerRuntimePaths,
    run_main,
)


def test_server_reexports_transport_public_surface() -> None:
    # Rust crate/module:
    # codex-exec-server/src/server.rs
    # Contract: server.rs publicly re-exports DEFAULT_LISTEN_URL and
    # ExecServerListenUrlParseError from server/transport.rs.
    assert DEFAULT_LISTEN_URL == "ws://127.0.0.1:0"
    assert ExecServerListenUrlParseError is exec_server.ExecServerListenUrlParseError


def test_run_main_forwards_to_transport(monkeypatch, tmp_path) -> None:
    # Rust crate/module:
    # codex-exec-server/src/server.rs::run_main.
    # Contract: run_main is a thin async wrapper over transport::run_transport
    # and forwards the listen URL and runtime paths unchanged.
    calls: list[tuple[str, ExecServerRuntimePaths]] = []

    async def fake_run_transport(listen_url: str, runtime_paths: ExecServerRuntimePaths) -> None:
        calls.append((listen_url, runtime_paths))

    monkeypatch.setattr(exec_server, "run_transport", fake_run_transport)
    runtime_paths = ExecServerRuntimePaths.new(tmp_path / "codex", None)

    asyncio.run(run_main("stdio", runtime_paths))

    assert calls == [("stdio", runtime_paths)]
