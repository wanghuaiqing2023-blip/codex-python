from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.exec_server import (
    DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT,
    DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
    DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT_SECONDS,
    ExecServerClientConnectOptions,
    ExecServerTransportKind,
    ExecServerTransportParams,
    HttpClient,
    HttpRequestParams,
    RemoteExecServerConnectArgs,
    StdioExecServerCommand,
    StdioExecServerConnectArgs,
)


def test_remote_timeout_constants_match_rust_durations() -> None:
    # Rust crate/module: codex-exec-server/src/client_api.rs.
    # Contract: DEFAULT_REMOTE_EXEC_SERVER_*_TIMEOUT are Duration::from_secs(10).
    assert DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT == 10
    assert DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT == 10
    assert DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT_SECONDS == 10
    assert DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT_SECONDS == 10


def test_client_connect_options_default_matches_client_impl() -> None:
    # Rust source: codex-exec-server/src/client.rs.
    # Contract: Default for ExecServerClientConnectOptions uses client
    # "codex-core", initialize timeout 10s, and no resume session id.
    assert ExecServerClientConnectOptions() == ExecServerClientConnectOptions(
        client_name="codex-core",
        initialize_timeout=10,
        resume_session_id=None,
    )


def test_remote_connect_args_new_and_into_options() -> None:
    # Rust source: codex-exec-server/src/client.rs.
    # Contract: RemoteExecServerConnectArgs::new supplies 10s connect and
    # initialize timeouts and Into<ExecServerClientConnectOptions> drops the
    # websocket-specific connect timeout while preserving shared fields.
    args = RemoteExecServerConnectArgs.new("ws://127.0.0.1:7777", "codex-environment")

    assert args == RemoteExecServerConnectArgs(
        websocket_url="ws://127.0.0.1:7777",
        client_name="codex-environment",
        connect_timeout=10,
        initialize_timeout=10,
        resume_session_id=None,
    )
    assert args.to_client_connect_options() == ExecServerClientConnectOptions(
        client_name="codex-environment",
        initialize_timeout=10,
        resume_session_id=None,
    )


def test_stdio_connect_args_into_options_and_command_normalization() -> None:
    # Rust modules: codex-exec-server/src/client_api.rs and src/client.rs.
    # Contract: stdio command transport stores program/args/env/cwd and
    # Into<ExecServerClientConnectOptions> preserves shared client fields.
    command = StdioExecServerCommand(
        program="codex-exec-server",
        args=["serve", 12],
        env={"RUST_LOG": "debug", "PORT": 7777},
        cwd="workspace",
    )
    args = StdioExecServerConnectArgs(
        command=command,
        client_name="codex-environment",
        initialize_timeout=15,
        resume_session_id="session-1",
    )

    assert command.program == "codex-exec-server"
    assert command.args == ["serve", "12"]
    assert command.env == {"RUST_LOG": "debug", "PORT": "7777"}
    assert command.cwd == Path("workspace")
    assert args.to_client_connect_options() == ExecServerClientConnectOptions(
        client_name="codex-environment",
        initialize_timeout=15,
        resume_session_id="session-1",
    )


def test_transport_params_websocket_constructor_matches_rust_helper() -> None:
    # Rust source: codex-exec-server/src/client_api.rs.
    # Contract: ExecServerTransportParams::websocket_url fills the default
    # remote connect and initialize timeouts for the WebSocketUrl variant.
    params = ExecServerTransportParams.websocket_url_params("wss://example.test/exec")

    assert params.kind is ExecServerTransportKind.WEBSOCKET_URL
    assert params.websocket_url == "wss://example.test/exec"
    assert params.connect_timeout == 10
    assert params.initialize_timeout == 10
    assert params.command is None


def test_transport_params_reject_wrong_variant_fields() -> None:
    # Rust module: codex-exec-server/src/client_api.rs.
    # Contract: ExecServerTransportParams variants are disjoint; Python raises
    # ValueError when callers combine fields from both variants.
    with pytest.raises(ValueError, match="websocket_url is required"):
        ExecServerTransportParams(kind=ExecServerTransportKind.WEBSOCKET_URL)
    with pytest.raises(ValueError, match="command is required"):
        ExecServerTransportParams(kind=ExecServerTransportKind.STDIO_COMMAND)
    with pytest.raises(ValueError, match="connect_timeout is only valid"):
        ExecServerTransportParams.stdio_command(
            StdioExecServerCommand(program="server"),
            initialize_timeout=10,
        ).__class__(
            kind=ExecServerTransportKind.STDIO_COMMAND,
            command=StdioExecServerCommand(program="server"),
            connect_timeout=10,
        )


def test_http_client_trait_boundary_is_explicitly_unported() -> None:
    # Rust module: codex-exec-server/src/client_api.rs.
    # Contract: HttpClient defines buffered and streamed request capabilities;
    # Python keeps the trait boundary explicit without implementing transport.
    params = HttpRequestParams(method="GET", url="https://example.test", headers=[], request_id="req-1")
    client = HttpClient()

    with pytest.raises(NotImplementedError, match="HTTP transport is not ported"):
        client.http_request(params)
    with pytest.raises(NotImplementedError, match="streamed HTTP transport is not ported"):
        client.http_request_stream(params)
