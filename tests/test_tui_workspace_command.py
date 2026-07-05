import sys

import pytest

from pycodex.tui.get_git_diff import get_git_diff
from pycodex.tui.workspace_command import (
    AppServerWorkspaceCommandRunner,
    LocalWorkspaceCommandRunner,
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


def test_app_server_runner_saturates_timeout_ms_like_rust() -> None:
    request = AppServerWorkspaceCommandRunner._build_request(
        WorkspaceCommand.new(["cmd"]).timeout(10**30)
    )

    assert request["params"]["timeout_ms"] == 9_223_372_036_854_775_807


@pytest.mark.asyncio
async def test_local_workspace_runner_executes_argv_cwd_and_env_like_embedded_app_server(tmp_path) -> None:
    # Rust source: codex-tui/src/workspace_command.rs::WorkspaceCommandExecutor.
    # Product adaptation: Python's embedded terminal runtime has no app-server
    # request handle, so LocalWorkspaceCommandRunner preserves the same
    # argv/cwd/env/timeout/output-cap contract for TUI-owned probes.
    script = (
        "import os, pathlib; "
        "print(pathlib.Path.cwd().name); "
        "print(os.environ.get('PYCODEX_WORKSPACE_RUNNER_TEST')); "
        "print(os.environ.get('PYCODEX_WORKSPACE_RUNNER_REMOVE'))"
    )
    runner = LocalWorkspaceCommandRunner(
        base_env={"PYCODEX_WORKSPACE_RUNNER_REMOVE": "remove-me"},
    )
    output = await runner.run(
        WorkspaceCommand.new([sys.executable, "-c", script])
        .cwd(tmp_path)
        .env("PYCODEX_WORKSPACE_RUNNER_TEST", "ok")
        .remove_env("PYCODEX_WORKSPACE_RUNNER_REMOVE")
    )

    assert output.exit_code == 0
    assert output.stdout.splitlines() == [tmp_path.name, "ok", "None"]


@pytest.mark.asyncio
async def test_local_workspace_runner_feeds_get_git_diff_for_dirty_repo(tmp_path) -> None:
    # Rust source/test:
    # - codex-tui::chatwidget::slash_dispatch runs /diff through the active
    #   WorkspaceCommandExecutor.
    # - get_git_diff.rs::get_git_diff_accepts_diff_exit_code_one proves git
    #   diff status 1 is successful diff output.
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("old line\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=pycodex@example.invalid",
            "-c",
            "user.name=PyCodex Test",
            "commit",
            "-m",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked.write_text("old line\nPYCODEX_LOCAL_WORKSPACE_DIFF\n", encoding="utf-8")

    is_repo, diff_text = await get_git_diff(LocalWorkspaceCommandRunner(default_cwd=tmp_path), tmp_path)

    assert is_repo is True
    assert "PYCODEX_LOCAL_WORKSPACE_DIFF" in diff_text
