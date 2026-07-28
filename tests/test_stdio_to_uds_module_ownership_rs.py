from __future__ import annotations

import importlib

from pycodex import stdio_to_uds


def test_main_rs_has_a_distinct_python_owner() -> None:
    # Rust: codex-stdio-to-uds/src/main.rs owns the binary main function.
    binary = importlib.import_module("pycodex.stdio_to_uds.__main__")

    assert binary.main.__module__ == binary.__name__
    assert not hasattr(stdio_to_uds, "main")


def test_cli_dispatches_through_the_crate_run_api(monkeypatch) -> None:
    # Rust: codex-cli/src/main.rs invokes codex_stdio_to_uds::run.
    cli = importlib.import_module("pycodex.cli.main")
    seen: list[str] = []

    async def fake_run(socket_path: str) -> None:
        seen.append(socket_path)

    monkeypatch.setattr(stdio_to_uds, "run", fake_run)

    assert cli._run_stdio_to_uds(
        ("socket-path",),
        stdout=cli.io.StringIO(),
        stderr=cli.io.StringIO(),
        stdin=b"",
    ) == 0
    assert seen == ["socket-path"]
