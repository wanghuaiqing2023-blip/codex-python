from __future__ import annotations

from pycodex.app_server_test_client.__main__ import main


def test_main_rs_runs_async_entrypoint_to_completion() -> None:
    # Rust crate: codex-app-server-test-client, module: src/main.rs.
    calls: list[str] = []

    async def fake_run() -> str:
        calls.append("run")
        return "ok"

    assert main(fake_run) == "ok"
    assert calls == ["run"]


def test_main_rs_propagates_async_entrypoint_errors() -> None:
    class Boom(RuntimeError):
        pass

    async def fake_run() -> None:
        raise Boom("failed")

    try:
        main(fake_run)
    except Boom as exc:
        assert str(exc) == "failed"
    else:
        raise AssertionError("expected error to propagate")
