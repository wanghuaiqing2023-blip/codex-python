"""Behavior port for Rust ``codex-tui::get_git_diff``.

Upstream source: ``codex/codex-rs/tui/src/get_git_diff.rs``.
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Iterable, Sequence

from ._porting import RustTuiModule
from .workspace_command import WorkspaceCommand, WorkspaceCommandExecutor, WorkspaceCommandOutput

RUST_MODULE = RustTuiModule(crate="codex-tui", module="get_git_diff", source="codex/codex-rs/tui/src/get_git_diff.rs")

DIFF_COMMAND_TIMEOUT = 30.0


async def get_git_diff(runner: WorkspaceCommandExecutor, cwd: str | Path) -> tuple[bool, str]:
    cwd_path = Path(cwd)
    if not await inside_git_repo(runner, cwd_path):
        return False, ""

    tracked_diff = await run_git_capture_diff(runner, cwd_path, ["diff", "--color"])
    untracked_output = await run_git_capture_stdout(
        runner,
        cwd_path,
        ["ls-files", "--others", "--exclude-standard"],
    )

    untracked_diff = ""
    null_path = null_device()
    for file in (line.strip() for line in untracked_output.split("\n")):
        if not file:
            continue
        untracked_diff += await run_git_capture_diff(
            runner,
            cwd_path,
            ["diff", "--color", "--no-index", "--", null_path, file],
        )

    return True, f"{tracked_diff}{untracked_diff}"


async def run_git_capture_stdout(
    runner: WorkspaceCommandExecutor,
    cwd: str | Path,
    args: Sequence[str],
) -> str:
    output = await run_git_command(runner, cwd, args)
    if output.success():
        return output.stdout
    raise RuntimeError(f"git {_format_args_debug(args)} failed with status {output.exit_code}")


async def run_git_capture_diff(
    runner: WorkspaceCommandExecutor,
    cwd: str | Path,
    args: Sequence[str],
) -> str:
    output = await run_git_command(runner, cwd, args)
    if output.success() or output.exit_code == 1:
        return output.stdout
    raise RuntimeError(f"git {_format_args_debug(args)} failed with status {output.exit_code}")


async def inside_git_repo(runner: WorkspaceCommandExecutor, cwd: str | Path) -> bool:
    output = await run_git_command(runner, cwd, ["rev-parse", "--is-inside-work-tree"])
    return output.success()


async def run_git_command(
    runner: WorkspaceCommandExecutor,
    cwd: str | Path,
    args: Sequence[str],
) -> WorkspaceCommandOutput:
    argv = ["git", *[str(arg) for arg in args]]
    command = WorkspaceCommand.new(argv).cwd(Path(cwd)).timeout(DIFF_COMMAND_TIMEOUT).disable_output_cap()
    try:
        return await runner.run(command)
    except Exception as exc:
        raise RuntimeError(str(exc)) from None


def null_device() -> str:
    return "NUL" if os.name == "nt" else "/dev/null"


def _format_args_debug(args: Sequence[str]) -> str:
    return "[" + ", ".join(f'"{arg}"' for arg in args) + "]"


@dataclass(frozen=True)
class FakeResponse:
    argv: list[str]
    output: WorkspaceCommandOutput


@dataclass
class FakeRunner:
    responses: Deque[FakeResponse] = field(default_factory=deque)
    captured_commands: list[WorkspaceCommand] = field(default_factory=list)

    @classmethod
    def new(cls, responses: Iterable[FakeResponse]) -> "FakeRunner":
        return cls(responses=deque(responses))

    def commands(self) -> list[WorkspaceCommand]:
        return list(self.captured_commands)

    async def run(self, command: WorkspaceCommand) -> WorkspaceCommandOutput:
        if not self.responses:
            raise RuntimeError("missing fake response")
        response = self.responses.popleft()
        if command.argv != response.argv:
            raise AssertionError(f"expected argv {response.argv!r}, got {command.argv!r}")
        self.captured_commands.append(command)
        return response.output


def response(argv: Sequence[str], exit_code: int, stdout: str) -> FakeResponse:
    return FakeResponse(
        argv=[str(arg) for arg in argv],
        output=WorkspaceCommandOutput(exit_code=int(exit_code), stdout=str(stdout), stderr=""),
    )


def assert_commands(commands: Sequence[WorkspaceCommand], expected: Sequence[Sequence[str]], cwd: str | Path) -> None:
    expected_argv = [[str(arg) for arg in argv] for argv in expected]
    actual_argv = [command.argv for command in commands]
    assert actual_argv == expected_argv
    cwd_path = Path(cwd)
    for command in commands:
        assert command.cwd_path == cwd_path
        assert command.timeout_seconds == DIFF_COMMAND_TIMEOUT
        assert command.disable_output_cap_flag is True


async def get_git_diff_returns_not_git_for_non_git_cwd(*args: Any, **kwargs: Any) -> Any:
    return await get_git_diff(*args, **kwargs)


async def get_git_diff_concatenates_tracked_and_untracked_diffs(*args: Any, **kwargs: Any) -> Any:
    return await get_git_diff(*args, **kwargs)


async def get_git_diff_accepts_diff_exit_code_one(*args: Any, **kwargs: Any) -> Any:
    return await get_git_diff(*args, **kwargs)


async def get_git_diff_rejects_unexpected_git_diff_status(*args: Any, **kwargs: Any) -> Any:
    return await get_git_diff(*args, **kwargs)


def run(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError("WorkspaceCommandExecutor.run is implemented by the supplied runner")


__all__ = [
    "DIFF_COMMAND_TIMEOUT",
    "FakeResponse",
    "FakeRunner",
    "RUST_MODULE",
    "assert_commands",
    "get_git_diff",
    "get_git_diff_accepts_diff_exit_code_one",
    "get_git_diff_concatenates_tracked_and_untracked_diffs",
    "get_git_diff_rejects_unexpected_git_diff_status",
    "get_git_diff_returns_not_git_for_non_git_cwd",
    "inside_git_repo",
    "null_device",
    "response",
    "run",
    "run_git_capture_diff",
    "run_git_capture_stdout",
    "run_git_command",
]
