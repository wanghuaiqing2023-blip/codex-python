from __future__ import annotations

from io import StringIO

import pytest

from pycodex.tui.notifications.bel import (
    BEL,
    BelBackend,
    PostNotification,
    execute_winapi,
    is_ansi_code_supported,
    write_ansi,
)


def test_post_notification_write_ansi_emits_bel() -> None:
    stream = StringIO()

    PostNotification().write_ansi(stream)

    assert stream.getvalue() == BEL


def test_module_write_ansi_helper_emits_bel() -> None:
    stream = StringIO()

    write_ansi(stream)

    assert stream.getvalue() == "\x07"


def test_bel_backend_notify_ignores_message_and_flushes_stream() -> None:
    class FlushRecordingStringIO(StringIO):
        def __init__(self) -> None:
            super().__init__()
            self.flushed = False

        def flush(self) -> None:
            self.flushed = True

    stream = FlushRecordingStringIO()
    backend = BelBackend(stream)

    backend.notify("hello")

    assert stream.getvalue() == BEL
    assert stream.flushed is True


def test_bel_backend_notify_emits_one_bel_per_call() -> None:
    stream = StringIO()
    backend = BelBackend(stream)

    backend.notify("first")
    backend.notify("second")

    assert stream.getvalue() == BEL * 2


def test_windows_winapi_path_is_explicitly_rejected_and_ansi_supported() -> None:
    assert is_ansi_code_supported() is True
    with pytest.raises(OSError, match="use ANSI instead"):
        execute_winapi()
