import pytest

from pycodex.tui.workspace_command import (
    AppServerWorkspaceCommandRunner,
    WorkspaceCommand,
    WorkspaceCommandError,
    WorkspaceCommandOutput,
    fmt,
)


def test_workspace_command_new_uses_rust_defaults() -> None:
    # Rust source: workspace_command.rs::WorkspaceCommand::new.
    command = WorkspaceCommand.new(["git", "status"])
    assert command.argv == ["git", "status"]
    assert command.cwd_path is None
    assert command.env_overrides == {}
    assert command.timeout_seconds == 5.0
    assert command.output_bytes_cap == 64 * 1024
    assert command.disable_output_cap_flag is False


def test_workspace_command_builders_are_immutable_and_chainable(tmp_path) -> None:
    command = (
        WorkspaceCommand.new(["cmd"])
        .cwd(tmp_path)
        .env("A", "1")
        .remove_env("B")
        .timeout(2.5)
        .disable_output_cap()
    )
    assert command.argv == ["cmd"]
    assert command.cwd_path == tmp_path
    assert command.env_overrides == {"A": "1", "B": None}
    assert command.timeout_seconds == 2.5
    assert command.disable_output_cap_flag is True
    assert WorkspaceCommand.new(["cmd"]).env_overrides == {}


def test_workspace_command_output_success_and_error_display() -> None:
    assert WorkspaceCommandOutput(exit_code=0, stdout="ok", stderr="").success()
    assert not WorkspaceCommandOutput(exit_code=1, stdout="", stderr="no").success()
    error = WorkspaceCommandError.new("transport failed")
    assert str(error) == "transport failed"
    assert fmt(error) == "transport failed"


@pytest.mark.asyncio
async def test_app_server_runner_builds_one_off_command_request(tmp_path) -> None:
    class Handle:
        def __init__(self) -> None:
            self.request = None

        async def request_typed(self, request):
            self.request = request
            return {"exit_code": 0, "stdout": "out", "stderr": "err"}

    handle = Handle()
    runner = AppServerWorkspaceCommandRunner.new(handle)
    output = await runner.run(
        WorkspaceCommand.new(["git", "diff"])
        .cwd(tmp_path)
        .env("LANG", "C")
        .timeout(3)
    )

    assert output == WorkspaceCommandOutput(exit_code=0, stdout="out", stderr="err")
    assert handle.request["type"] == "OneOffCommandExec"
    assert handle.request["request_id"].startswith("workspace-command-")
    params = handle.request["params"]
    assert params["command"] == ["git", "diff"]
    assert params["process_id"] is None
    assert params["tty"] is False
    assert params["stream_stdin"] is False
    assert params["stream_stdout_stderr"] is False
    assert params["output_bytes_cap"] == 64 * 1024
    assert params["disable_output_cap"] is False
    assert params["disable_timeout"] is False
    assert params["timeout_ms"] == 3000
    assert params["cwd"] == tmp_path
    assert params["env"] == {"LANG": "C"}
    assert params["sandbox_policy"] is None
    assert params["permission_profile"] is None


@pytest.mark.asyncio
async def test_app_server_runner_disables_output_cap_and_wraps_errors() -> None:
    class FailingHandle:
        def request_typed(self, _request):
            raise RuntimeError("boom")

    request = AppServerWorkspaceCommandRunner._build_request(WorkspaceCommand.new(["diff"]).disable_output_cap())
    assert request["params"]["output_bytes_cap"] is None
    assert request["params"]["disable_output_cap"] is True

    with pytest.raises(WorkspaceCommandError) as exc:
        await AppServerWorkspaceCommandRunner.new(FailingHandle()).run(WorkspaceCommand.new(["cmd"]))
    assert str(exc.value) == "boom"
