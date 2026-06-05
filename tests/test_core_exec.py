import asyncio
from datetime import timedelta

import pytest

from pycodex import core as core_exports
from pycodex.core.exec import (
    DEFAULT_EXEC_COMMAND_TIMEOUT_MS,
    EXEC_OUTPUT_MAX_BYTES,
    EXEC_TIMEOUT_EXIT_CODE,
    EXIT_CODE_SIGNAL_BASE,
    CancellationToken,
    ExecCapturePolicy,
    ExecExpiration,
    ExecExpirationKind,
    ExecExpirationOutcome,
    ExecSandboxDenied,
    ExecSandboxSignal,
    ExecSandboxTimeout,
    RawExecToolCallOutput,
    aggregate_output,
    append_capped,
    cancel_when_either,
    finalize_exec_result,
    is_likely_sandbox_denied,
    unified_exec_sandbox_denial_message,
)
from pycodex.utils.string import approx_token_count
from pycodex.core.unified_exec import UNIFIED_EXEC_OUTPUT_MAX_TOKENS
from pycodex.protocol import ExecToolCallOutput, StreamOutput


def test_capture_policy_matches_shell_tool_defaults():
    assert ExecCapturePolicy.SHELL_TOOL.retained_bytes_cap() == EXEC_OUTPUT_MAX_BYTES
    assert ExecCapturePolicy.FULL_BUFFER.retained_bytes_cap() is None
    assert ExecCapturePolicy.SHELL_TOOL.uses_expiration() is True
    assert ExecCapturePolicy.FULL_BUFFER.uses_expiration() is False


def test_exec_expiration_from_optional_timeout():
    assert ExecExpiration.from_timeout_ms(None).timeout_ms() == DEFAULT_EXEC_COMMAND_TIMEOUT_MS
    assert ExecExpiration.from_timeout_ms(250).timeout_ms() == 250


def test_exec_expiration_rejects_negative_timeout_durations():
    with pytest.raises(ValueError, match="timeout must be non-negative"):
        ExecExpiration.timeout_after(timedelta(milliseconds=-1))

    with pytest.raises(ValueError, match="timeout must be non-negative"):
        ExecExpiration.timeout_or_cancellation(timedelta(milliseconds=-1), CancellationToken())

    with pytest.raises(ValueError, match="timeout must be non-negative"):
        ExecExpiration(ExecExpiration.kind if False else ExecExpirationKind.TIMEOUT, timeout=timedelta(milliseconds=-1))


def test_cancel_when_either_is_lazy_and_observes_either_parent():
    first = CancellationToken()
    second = CancellationToken()

    combined = cancel_when_either(first, second)

    assert combined.is_cancelled() is False
    second.cancel()
    assert combined.is_cancelled() is True
    asyncio.run(combined.cancelled())


def test_exec_expiration_with_cancellation_can_combine_without_running_loop():
    first = CancellationToken()
    second = CancellationToken()

    expiration = ExecExpiration.cancellation(first).with_cancellation(second)

    assert expiration.timeout_ms() is None
    assert expiration.cancellation is not None
    assert expiration.cancellation.is_cancelled() is False
    first.cancel()
    assert expiration.cancellation.is_cancelled() is True


def test_timeout_or_cancellation_prefers_pre_cancelled_token():
    token = CancellationToken()
    token.cancel()
    expiration = ExecExpiration.timeout_or_cancellation(timedelta(seconds=60), token)

    assert asyncio.run(expiration.wait_with_outcome()) is ExecExpirationOutcome.CANCELLED


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


def test_unified_exec_sandbox_denial_message_matches_process_boundary():
    assert unified_exec_sandbox_denial_message("none", True, 1, "permission denied") is None
    assert unified_exec_sandbox_denial_message("linux_seccomp", False, 1, "permission denied") is None
    assert unified_exec_sandbox_denial_message("linux_seccomp", True, 127, "not found") is None
    assert (
        unified_exec_sandbox_denial_message("linux_seccomp", True, 1, "permission denied")
        == "permission denied"
    )
    assert (
        unified_exec_sandbox_denial_message("linux_seccomp", True, None, "operation not permitted")
        == "operation not permitted"
    )


def test_unified_exec_sandbox_denial_message_falls_back_to_exit_code_when_empty():
    assert (
        unified_exec_sandbox_denial_message("linux_seccomp", True, EXIT_CODE_SIGNAL_BASE + 31, "")
        == "Process exited with code 159"
    )


def test_unified_exec_sandbox_denial_message_truncates_long_output():
    text = "permission denied\n" + ("x" * ((UNIFIED_EXEC_OUTPUT_MAX_TOKENS * 4) + 128))

    message = unified_exec_sandbox_denial_message("linux_seccomp", True, 1, text)

    assert message is not None
    assert message != text
    assert message.startswith("Total output lines: 2\n\n")
    assert "tokens truncated" in message
    assert approx_token_count(message) < approx_token_count(text)


def test_unified_exec_sandbox_denial_message_is_exported_from_core():
    assert core_exports.unified_exec_sandbox_denial_message is unified_exec_sandbox_denial_message
