import re
from datetime import timedelta

from pycodex.core.user_shell_command import format_exec_output_for_model
from pycodex.protocol import ExecToolCallOutput, ShellCommandToolCallParams, StreamOutput, TruncationPolicyConfig


def _exec_output(text: str, *, exit_code: int = 0, millis: int = 25, timed_out: bool = False) -> ExecToolCallOutput:
    return ExecToolCallOutput(
        exit_code=exit_code,
        aggregated_output=StreamOutput.new(text),
        duration=timedelta(milliseconds=millis),
        timed_out=timed_out,
    )


def _model_output(text: str, *, exit_code: int = 0, millis: int = 25, timed_out: bool = False) -> str:
    return format_exec_output_for_model(
        _exec_output(text, exit_code=exit_code, millis=millis, timed_out=timed_out),
        TruncationPolicyConfig.bytes(4096),
    )


def _assert_shell_command_output(output: str, expected: str) -> None:
    normalized = output.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    pattern = rf"(?s)^Exit code: 0\nWall time: [0-9]+(?:\.[0-9]+)? seconds\nOutput:\n{re.escape(expected)}\n?$"
    assert re.match(pattern, normalized), normalized


def test_shell_command_works():
    # Rust: core/tests/suite/shell_command.rs
    # test `shell_command_works`.
    params = ShellCommandToolCallParams.from_mapping({"command": "echo 'hello, world'"})

    assert params.command == "echo 'hello, world'"
    assert params.login is None
    _assert_shell_command_output(_model_output("hello, world"), "hello, world")


def test_output_with_login():
    # Rust: core/tests/suite/shell_command.rs
    # test `output_with_login`.
    params = ShellCommandToolCallParams.from_mapping(
        {"command": "echo 'hello, world'", "login": True}
    )

    assert params.login is True
    _assert_shell_command_output(_model_output("hello, world"), "hello, world")


def test_output_without_login():
    # Rust: core/tests/suite/shell_command.rs
    # test `output_without_login`.
    params = ShellCommandToolCallParams.from_mapping(
        {"command": "echo 'hello, world'", "login": False}
    )

    assert params.login is False
    _assert_shell_command_output(_model_output("hello, world"), "hello, world")


def test_multi_line_output_with_login():
    # Rust: core/tests/suite/shell_command.rs
    # test `multi_line_output_with_login`.
    params = ShellCommandToolCallParams.from_mapping(
        {"command": "echo 'first line\nsecond line'", "login": True}
    )

    assert params.login is True
    _assert_shell_command_output(_model_output("first line\nsecond line"), "first line\nsecond line")


def test_pipe_output_with_login():
    # Rust: core/tests/suite/shell_command.rs
    # test `pipe_output_with_login`.
    params = ShellCommandToolCallParams.from_mapping(
        {"command": "echo 'hello, world' | cat"}
    )

    assert "|" in params.command
    assert params.login is None
    _assert_shell_command_output(_model_output("hello, world"), "hello, world")


def test_pipe_output_without_login():
    # Rust: core/tests/suite/shell_command.rs
    # test `pipe_output_without_login`.
    params = ShellCommandToolCallParams.from_mapping(
        {"command": "echo 'hello, world' | cat", "login": False}
    )

    assert "|" in params.command
    assert params.login is False
    _assert_shell_command_output(_model_output("hello, world"), "hello, world")


def test_shell_command_times_out_with_timeout_ms():
    # Rust: core/tests/suite/shell_command.rs
    # test `shell_command_times_out_with_timeout_ms`.
    params = ShellCommandToolCallParams.from_mapping(
        {"command": "sleep 5", "timeout_ms": 200}
    )

    output = _model_output("", exit_code=124, millis=params.timeout_ms or 0, timed_out=True)

    assert params.timeout_ms == 200
    assert re.match(
        r"(?s)^Exit code: 124\nWall time: [0-9]+(?:\.[0-9]+)? seconds\nOutput:\ncommand timed out after [0-9]+ milliseconds\n?$",
        output,
    )


def test_unicode_output():
    # Rust: core/tests/suite/shell_command.rs
    # test `unicode_output` with both login modes.
    for login in (True, False):
        params = ShellCommandToolCallParams.from_mapping(
            {"command": 'echo "naïve_café"', "login": login}
        )

        assert params.login is login
        _assert_shell_command_output(_model_output("naïve_café"), "naïve_café")


def test_unicode_output_with_newlines():
    # Rust: core/tests/suite/shell_command.rs
    # test `unicode_output_with_newlines` with both login modes.
    for login in (True, False):
        params = ShellCommandToolCallParams.from_mapping(
            {"command": "echo 'line1\nnaïve café\nline3'", "login": login}
        )

        assert params.login is login
        _assert_shell_command_output(
            _model_output("line1\\nnaïve café\\nline3"),
            "line1\\nnaïve café\\nline3",
        )
