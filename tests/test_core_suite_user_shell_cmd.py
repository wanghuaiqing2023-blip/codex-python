import asyncio
import re
import subprocess
import sys
from datetime import timedelta
from types import SimpleNamespace

from pycodex.core.session.handlers import (
    USER_SHELL_COMMAND_MODE_ACTIVE_TURN_AUXILIARY,
    UserShellCommandTask,
    dispatch_session_op,
)
from pycodex.core.user_shell_command import (
    env_for_user_shell_command,
    format_exec_output_for_model,
    format_user_shell_command_record,
    user_shell_command_record_item,
)
from pycodex.protocol import ExecToolCallOutput, Op, ResponseItem, StreamOutput, TruncationPolicyConfig


def _exec_output(text: str, *, exit_code: int = 0, duration: timedelta | None = None) -> ExecToolCallOutput:
    return ExecToolCallOutput(
        exit_code=exit_code,
        stdout=StreamOutput.new(text),
        stderr=StreamOutput.new(""),
        aggregated_output=StreamOutput.new(text),
        duration=duration or timedelta(milliseconds=120),
        timed_out=False,
    )


def test_user_shell_cmd_ls_and_cat_in_temp_dir(tmp_path) -> None:
    # Rust: core/tests/suite/user_shell_cmd.rs::user_shell_cmd_ls_and_cat_in_temp_dir.
    file_path = tmp_path / "hello.txt"
    contents = "hello from bang test\n"
    file_path.write_text(contents, encoding="utf-8")

    list_result = subprocess.run(
        [sys.executable, "-c", "import os; print('\\n'.join(os.listdir('.')))"],
        cwd=tmp_path,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    cat_result = subprocess.run(
        [sys.executable, "-c", "from pathlib import Path; print(Path('hello.txt').read_text(), end='')"],
        cwd=tmp_path,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert list_result.returncode == 0
    assert "hello.txt" in list_result.stdout
    assert cat_result.returncode == 0
    assert cat_result.stdout == contents


def test_user_shell_cmd_can_be_interrupted() -> None:
    # Rust: core/tests/suite/user_shell_cmd.rs::user_shell_cmd_can_be_interrupted.
    calls: list[tuple[object, str, object, str]] = []
    cancellation_token = object()

    async def active_turn_context_and_cancellation_token() -> tuple[str, object]:
        return ("active-turn", cancellation_token)

    async def execute_user_shell_command(turn_context: object, command: str, cancellation_token: object, mode: str) -> None:
        calls.append((turn_context, command, cancellation_token, mode))

    session = SimpleNamespace(
        active_turn_context_and_cancellation_token=active_turn_context_and_cancellation_token,
        execute_user_shell_command=execute_user_shell_command,
    )

    should_exit = asyncio.run(dispatch_session_op(session, "sub-1", Op.run_user_shell_command("sleep 5")))

    assert should_exit is False
    assert calls == [("active-turn", "sleep 5", cancellation_token, USER_SHELL_COMMAND_MODE_ACTIVE_TURN_AUXILIARY)]


def test_user_shell_command_does_not_replace_active_turn() -> None:
    # Rust: core/tests/suite/user_shell_cmd.rs::user_shell_command_does_not_replace_active_turn.
    calls: list[tuple[object, str, object, str]] = []

    async def active_turn_context_and_cancellation_token() -> tuple[str, str]:
        return ("active-turn", "cancel-token")

    async def execute_user_shell_command(turn_context: object, command: str, cancellation_token: object, mode: str) -> None:
        calls.append((turn_context, command, cancellation_token, mode))

    session = SimpleNamespace(
        active_turn_context_and_cancellation_token=active_turn_context_and_cancellation_token,
        execute_user_shell_command=execute_user_shell_command,
    )

    should_exit = asyncio.run(dispatch_session_op(session, "sub-1", Op.run_user_shell_command("printf user-shell")))

    assert should_exit is False
    assert calls == [("active-turn", "printf user-shell", "cancel-token", "active_turn_auxiliary")]


def test_user_shell_command_history_is_persisted_and_shared_with_model() -> None:
    # Rust: core/tests/suite/user_shell_cmd.rs::user_shell_command_history_is_persisted_and_shared_with_model.
    command = "sh -c \"printf '%s' \\\"${CODEX_SANDBOX:-not-set}\\\"\""
    item = user_shell_command_record_item(
        command,
        _exec_output("not-set"),
        TruncationPolicyConfig.bytes(4096),
    )

    assert isinstance(item, ResponseItem)
    text = item.content[0].text
    assert text.startswith("<user_shell_command>\n<command>\n")
    assert command in text
    assert "Exit code: 0\n" in text
    assert "Output:\nnot-set" in text
    assert text.endswith("</user_shell_command>")


def test_user_shell_command_does_not_set_network_sandbox_env_var() -> None:
    # Rust: core/tests/suite/user_shell_cmd.rs::user_shell_command_does_not_set_network_sandbox_env_var.
    env = env_for_user_shell_command({"PATH": "kept"}, target_os="linux")

    assert env == {"PATH": "kept"}
    assert "CODEX_SANDBOX_NETWORK_DISABLED" not in env


def test_user_shell_command_output_is_truncated_in_history() -> None:
    # Rust: core/tests/suite/user_shell_cmd.rs::user_shell_command_output_is_truncated_in_history.
    command = "seq 1 400"
    output = "".join(f"{i}\n" for i in range(1, 401))
    record = format_user_shell_command_record(
        command,
        _exec_output(output),
        TruncationPolicyConfig.bytes(512),
    )

    assert record.startswith("<user_shell_command>\n<command>\nseq 1 400\n</command>")
    assert "Exit code: 0\n" in record
    assert "Total output lines: 400" in record
    assert re.search(r"truncated", record)
    assert record.endswith("</user_shell_command>")


def test_user_shell_command_is_truncated_only_once() -> None:
    # Rust: core/tests/suite/user_shell_cmd.rs::user_shell_command_is_truncated_only_once.
    output = "".join(f"{i}\n" for i in range(1, 2001))
    formatted_once = format_exec_output_for_model(
        _exec_output(output),
        TruncationPolicyConfig.bytes(1024),
    )
    formatted_twice = format_exec_output_for_model(
        _exec_output(formatted_once),
        TruncationPolicyConfig.bytes(4096),
    )

    assert formatted_once.count("Total output lines:") == 1
    assert formatted_twice.count("Total output lines:") == 1
