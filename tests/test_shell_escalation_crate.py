import asyncio
import os
import socket
import sys
from pathlib import Path

import pytest

from pycodex.shell_escalation import (
    ESCALATE_SOCKET_ENV_VAR,
    EXEC_WRAPPER_ENV_VAR,
    MAX_FDS_PER_MESSAGE,
    AsyncSocket,
    CancellationToken,
    EscalateAction,
    EscalateRequest,
    EscalateResponse,
    EscalationDecision,
    EscalationPolicy,
    EscalateServer,
    ExecParams,
    ExecResult,
    ExecveWrapperCli,
    PreparedExec,
    ShellCommandExecutor,
    Stopwatch,
    SuperExecMessage,
    SuperExecResult,
    codex_execve_wrapper_main,
    duplicate_fd_for_transfer,
    encode_length,
    shell_escalation_request_env,
)


def test_protocol_constants_and_length_encoding_match_rust() -> None:
    assert ESCALATE_SOCKET_ENV_VAR == "CODEX_ESCALATE_SOCKET"
    assert EXEC_WRAPPER_ENV_VAR == "EXEC_WRAPPER"
    assert MAX_FDS_PER_MESSAGE == 16
    assert encode_length(5) == b"\x05\x00\x00\x00"
    with pytest.raises(ValueError):
        encode_length(0x1_0000_0000)


def test_execve_wrapper_cli_parse_and_non_unix_main(capsys: pytest.CaptureFixture[str]) -> None:
    parsed = ExecveWrapperCli.parse(["/bin/echo", "echo", "ok"])
    assert parsed.file == "/bin/echo"
    assert parsed.argv == ("echo", "ok")
    assert codex_execve_wrapper_main(["/bin/echo"], platform="nt") == 1
    assert "only implemented for UNIX" in capsys.readouterr().err


def test_protocol_records_round_trip_mappings() -> None:
    request = EscalateRequest("bin/tool", ["tool"], "/work", {"A": "B"})
    assert EscalateRequest.from_mapping(request.to_mapping()) == request
    action = EscalateAction.deny("blocked")
    assert EscalateAction.from_mapping(action.to_mapping()) == action
    response = EscalateResponse(action)
    assert EscalateResponse.from_mapping(response.to_mapping()) == response
    assert SuperExecMessage.from_mapping(SuperExecMessage([0, 1]).to_mapping()).fds == (0, 1)
    assert SuperExecResult.from_mapping(SuperExecResult(7).to_mapping()).exit_code == 7


def test_request_env_filters_protocol_vars() -> None:
    env = {
        "A": "B",
        ESCALATE_SOCKET_ENV_VAR: "4",
        EXEC_WRAPPER_ENV_VAR: "/tmp/wrapper",
    }
    assert shell_escalation_request_env(env) == {"A": "B"}


@pytest.mark.skipif(os.name != "posix", reason="fd duplication parity is Unix-only")
def test_duplicate_fd_for_transfer_does_not_close_original() -> None:
    left, right = socket.socketpair()
    try:
        duplicate = duplicate_fd_for_transfer(left.fileno(), "test fd")
        os.close(duplicate)
        left.getsockname()
    finally:
        left.close()
        right.close()


@pytest.mark.skipif(
    not hasattr(socket, "socketpair") or not hasattr(socket, "AF_UNIX"),
    reason="AF_UNIX socketpair unavailable",
)
def test_async_socket_round_trips_payload() -> None:
    async def run() -> None:
        server, client = AsyncSocket.pair()
        payload = EscalateRequest("/bin/sh", ["/bin/sh"], Path.cwd(), {"A": "B"})
        await client.send(payload)
        received = await server.receive(EscalateRequest)
        assert received == payload
        server.into_inner().close()
        client.into_inner().close()

    asyncio.run(run())


def test_stopwatch_unlimited_never_cancels_quickly() -> None:
    async def run() -> None:
        token = Stopwatch.unlimited().cancellation_token()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(token.cancelled(), timeout=0.01)

    asyncio.run(run())


def test_escalation_policy_base_is_not_permissive() -> None:
    async def run() -> None:
        with pytest.raises(NotImplementedError):
            await EscalationPolicy().determine_action(Path("/bin/sh"), ["sh"], Path.cwd())

    asyncio.run(run())


def test_escalate_server_session_env_overlay() -> None:
    class RunPolicy(EscalationPolicy):
        async def determine_action(self, file: Path, argv: list[str], workdir: Path) -> EscalationDecision:
            return EscalationDecision.run()

    class Executor(ShellCommandExecutor):
        async def run(
            self,
            command: list[str],
            cwd: Path,
            env_overlay: dict[str, str],
            cancel_rx: CancellationToken,
            after_spawn=None,
        ) -> ExecResult:
            if after_spawn is not None:
                after_spawn()
            return ExecResult(0)

        async def prepare_escalated_exec(
            self,
            program: Path,
            argv: list[str],
            workdir: Path,
            env: dict[str, str],
            execution,
        ) -> PreparedExec:
            return PreparedExec((program.as_posix(),), workdir, env)

    async def run() -> None:
        server = EscalateServer("/bin/sh", "/tmp/wrapper", RunPolicy())
        result = await server.exec(ExecParams("true", str(Path.cwd()), login=False), CancellationToken(), Executor())
        assert result.exit_code == 0

    if sys.platform == "win32":
        pytest.skip("AF_UNIX socketpair behavior is platform-specific")
    asyncio.run(run())
