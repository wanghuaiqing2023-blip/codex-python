from pathlib import Path
import asyncio
import io

import pytest

from pycodex.tui import (
    AppServerTarget,
    ExitReason,
    ExitReasonPayload,
    RemoteAppServerEndpoint,
    app_server_target_for_launch,
    config_cwd_for_app_server_target,
    latest_session_cwd_filter,
    remote_addr_supports_auth_token,
    resolve_remote_addr,
    run_main,
)
from pycodex.tui.app.runtime import ExecFunctionActiveThreadRuntime


def test_resolve_remote_addr_accepts_websocket_with_explicit_port_and_unix_paths(tmp_path: Path) -> None:
    # Rust: codex-tui/src/lib.rs::resolve_remote_addr.
    websocket = resolve_remote_addr("ws://127.0.0.1:4500")
    assert websocket == RemoteAppServerEndpoint.websocket("ws://127.0.0.1:4500")

    default_unix = resolve_remote_addr("unix://", codex_home=tmp_path)
    assert default_unix.kind == "unix_socket"
    assert default_unix.socket_path == tmp_path / "app-server-control" / "app-server-control.sock"

    relative_unix = resolve_remote_addr("unix://codex.sock", cwd=tmp_path)
    assert relative_unix == RemoteAppServerEndpoint.unix_socket(tmp_path / "codex.sock")


def test_resolve_remote_addr_rejects_missing_port_path_query_and_fragment() -> None:
    # Rust requires ws/wss host plus explicit port, root path, and no query/fragment.
    for value in [
        "ws://127.0.0.1",
        "wss://codex.example/rpc",
        "ws://127.0.0.1:4500/rpc",
        "ws://127.0.0.1:4500/?x=1",
        "ws://127.0.0.1:4500/#frag",
        "http://127.0.0.1:4500",
    ]:
        with pytest.raises(ValueError, match="invalid remote address"):
            resolve_remote_addr(value)


def test_remote_addr_supports_auth_token_matches_tui_rules() -> None:
    # Rust: websocket_url_supports_auth_token allows wss and loopback ws only.
    assert remote_addr_supports_auth_token(RemoteAppServerEndpoint.websocket("wss://codex.example:443/")) is True
    assert remote_addr_supports_auth_token(RemoteAppServerEndpoint.websocket("ws://localhost:4500/")) is True
    assert remote_addr_supports_auth_token(RemoteAppServerEndpoint.websocket("ws://127.0.0.1:4500/")) is True
    assert remote_addr_supports_auth_token(RemoteAppServerEndpoint.websocket("ws://[::1]:4500/")) is True
    assert remote_addr_supports_auth_token(RemoteAppServerEndpoint.websocket("ws://codex.example:4500/")) is False
    assert remote_addr_supports_auth_token(RemoteAppServerEndpoint.unix_socket("codex.sock")) is False


def test_app_server_target_for_launch_matches_rust_target_selection(tmp_path: Path) -> None:
    # Rust: app_server_target_for_launch chooses explicit remote, reusable daemon, else embedded.
    endpoint = RemoteAppServerEndpoint.websocket("wss://codex.example:443/")
    assert app_server_target_for_launch(endpoint, tmp_path / "sock", True) == AppServerTarget.remote(endpoint)

    local = app_server_target_for_launch(None, tmp_path / "sock", True)
    assert local.kind == "LocalDaemon"
    assert local.thread_params_mode() == "Embedded"

    embedded = app_server_target_for_launch(None, tmp_path / "sock", False)
    assert embedded == AppServerTarget.embedded()
    assert embedded.uses_remote_workspace() is False


def test_latest_session_cwd_filter_respects_scope_options(tmp_path: Path) -> None:
    # Rust: codex-tui/src/lib.rs::tests::latest_session_cwd_filter_respects_scope_options.
    config = {"cwd": tmp_path / "local"}
    remote_cwd = Path("repo/on/server")

    assert latest_session_cwd_filter(False, None, config, False) == tmp_path / "local"
    assert latest_session_cwd_filter(False, None, config, True) is None
    assert latest_session_cwd_filter(True, remote_cwd, config, False) == remote_cwd


def test_config_cwd_for_app_server_target_canonicalizes_or_omits_remote(tmp_path: Path) -> None:
    # Rust: config_cwd_for_app_server_target_* tests.
    project = tmp_path / "project"
    project.mkdir()

    assert config_cwd_for_app_server_target(project, AppServerTarget.embedded()) == project.resolve()
    assert config_cwd_for_app_server_target(project, AppServerTarget.local_daemon(RemoteAppServerEndpoint.unix_socket("codex.sock"))) == project.resolve()
    assert config_cwd_for_app_server_target(project, AppServerTarget.remote(RemoteAppServerEndpoint.unix_socket("codex.sock"))) is None

    with pytest.raises(FileNotFoundError):
        config_cwd_for_app_server_target(tmp_path / "missing", AppServerTarget.embedded())


def test_run_main_uses_injected_prompt_runner_and_reports_fatal_without_one() -> None:
    # Rust: codex-tui/src/lib.rs::run_main owns the crate-root TUI launch boundary.
    stdout = io.StringIO()
    stderr = io.StringIO()
    prompts = []

    def execute_prompt(prompt: str) -> tuple[int, str]:
        prompts.append(prompt)
        return 0, "pong"

    ok = asyncio.run(
        run_main(
            stdout=stdout,
            stderr=stderr,
            stdin=io.StringIO("ping\n/quit\n"),
            active_thread_runtime=ExecFunctionActiveThreadRuntime(execute_prompt),
            no_alt_screen=True,
        )
    )
    assert ok.exit_reason == ExitReason.USER_REQUESTED
    assert prompts == ["ping"]
    assert "pong" in stdout.getvalue()

    fatal = asyncio.run(run_main(stdout=io.StringIO(), stderr=stderr, stdin=io.StringIO("")))
    assert isinstance(fatal.exit_reason, ExitReasonPayload)
    assert fatal.exit_reason.reason == ExitReason.FATAL
