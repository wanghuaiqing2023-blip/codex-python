from datetime import timedelta

import pytest

from pycodex.core.exec import (
    DEFAULT_EXEC_COMMAND_TIMEOUT_MS,
    EXEC_OUTPUT_MAX_BYTES,
    EXEC_TIMEOUT_EXIT_CODE,
    ExecCapturePolicy,
    ExecExpiration,
    ExecSandboxDenied,
    ExecSandboxSignal,
    ExecSandboxTimeout,
    RawExecToolCallOutput,
    aggregate_output,
    append_capped,
    finalize_exec_result,
    is_likely_sandbox_denied,
)
from pycodex.protocol import ExecToolCallOutput, StreamOutput


def test_capture_policy_matches_shell_tool_defaults():
    assert ExecCapturePolicy.SHELL_TOOL.retained_bytes_cap() == EXEC_OUTPUT_MAX_BYTES
    assert ExecCapturePolicy.FULL_BUFFER.retained_bytes_cap() is None
    assert ExecCapturePolicy.SHELL_TOOL.uses_expiration() is True
    assert ExecCapturePolicy.FULL_BUFFER.uses_expiration() is False


def test_exec_expiration_from_optional_timeout():
    assert ExecExpiration.from_timeout_ms(None).timeout_ms() == DEFAULT_EXEC_COMMAND_TIMEOUT_MS
    assert ExecExpiration.from_timeout_ms(250).timeout_ms() == 250


def test_append_capped_stops_at_limit():
    data = bytearray(b"ab")

    append_capped(data, b"cdef", 4)

    assert bytes(data) == b"abcd"


def test_aggregate_output_rebalances_stdout_and_stderr():
    stdout = StreamOutput(b"abcdef")
    stderr = StreamOutput(b"123456789")

    output = aggregate_output(stdout, stderr, 9)

    assert output.text == b"abc123456"


def test_finalize_exec_result_converts_bytes_and_timeout():
    raw = RawExecToolCallOutput(
        exit_code=0,
        stdout=StreamOutput(b"out"),
        stderr=StreamOutput(b"err"),
        aggregated_output=StreamOutput(b"outerr"),
        timed_out=True,
    )

    with pytest.raises(ExecSandboxTimeout) as exc_info:
        finalize_exec_result(raw, "linux_seccomp", timedelta(milliseconds=5))

    assert exc_info.value.output.exit_code == EXEC_TIMEOUT_EXIT_CODE
    assert exc_info.value.output.timed_out is True


def test_finalize_exec_result_reports_non_timeout_signal():
    raw = RawExecToolCallOutput(
        exit_code=None,
        signal=9,
        stdout=StreamOutput(b""),
        stderr=StreamOutput(b""),
        aggregated_output=StreamOutput(b""),
    )

    with pytest.raises(ExecSandboxSignal):
        finalize_exec_result(raw, "linux_seccomp", timedelta())


def test_likely_sandbox_denied_uses_keywords_and_rejects_command_not_found():
    denied = ExecToolCallOutput(exit_code=1, stderr=StreamOutput.new("operation not permitted"))
    command_not_found = ExecToolCallOutput(exit_code=127, stderr=StreamOutput.new("not found"))

    assert is_likely_sandbox_denied("linux_seccomp", denied) is True
    assert is_likely_sandbox_denied("linux_seccomp", command_not_found) is False


def test_finalize_exec_result_raises_denied_for_sandbox_keyword():
    raw = RawExecToolCallOutput(
        exit_code=1,
        stdout=StreamOutput(b""),
        stderr=StreamOutput(b"permission denied"),
        aggregated_output=StreamOutput(b"permission denied"),
    )

    with pytest.raises(ExecSandboxDenied):
        finalize_exec_result(raw, "linux_seccomp", timedelta())
