from __future__ import annotations

import os
import time

import pytest

from pycodex.tui.ide_context.windows_pipe import (
    FALSE,
    NULL_HANDLE,
    TRUE,
    OwnedHandle,
    OverlappedOperation,
    TokenUserBuffer,
    WindowsPipeStream,
    remaining_timeout_ms,
    timeout_io_error,
)


def test_windows_pipe_constants_match_rust_bool_and_null_handle() -> None:
    assert TRUE == 1
    assert FALSE == 0
    assert NULL_HANDLE == 0


def test_stream_deadline_wrapper_and_empty_io_branches() -> None:
    stream = WindowsPipeStream(handle=OwnedHandle(123), deadline=1.0)
    stream.set_deadline(2.0)

    assert stream.deadline == 2.0
    assert stream.read(bytearray()) == 0
    assert stream.write(b"") == 0
    assert stream.flush() is None


def test_owned_handle_raw_returns_inner_handle() -> None:
    assert OwnedHandle(42).raw() == 42


def test_windows_transport_entrypoints_are_platform_guarded_off_windows() -> None:
    if os.name == "nt":
        pytest.skip("platform guard is only observable off Windows")

    with pytest.raises(OSError, match="only available on Windows"):
        WindowsPipeStream.connect(r"\\.\pipe\codex-test", time.monotonic())

    with pytest.raises(OSError, match="only available on Windows"):
        OverlappedOperation.new()


def test_token_user_buffer_rejects_empty_buffer() -> None:
    with pytest.raises(ValueError, match="token user buffer is too small"):
        TokenUserBuffer(b"").sid()


def test_remaining_timeout_ms_clamps_deadline() -> None:
    assert remaining_timeout_ms(time.monotonic() - 1) == 0
    assert remaining_timeout_ms(time.monotonic() + 0.01) >= 1


def test_timeout_io_error_message() -> None:
    assert str(timeout_io_error()) == "timed out waiting for IDE context"
