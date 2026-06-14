from __future__ import annotations

from io import StringIO

import pytest

from pycodex.tui.notifications.osc9 import (
    BEL,
    ESC,
    Osc9Backend,
    PostNotification,
    default,
    detect_tmux_dcs_passthrough,
    escape_tmux_dcs_passthrough_payload,
    execute_winapi,
    is_ansi_code_supported,
    post_notification_escapes_escape_bytes_inside_tmux_payload,
    post_notification_writes_plain_osc9_sequence,
    post_notification_writes_tmux_dcs_wrapped_osc9_sequence,
    write_ansi,
)


def test_post_notification_writes_plain_osc9_sequence() -> None:
    assert post_notification_writes_plain_osc9_sequence() == "\x1b]9;hello\x07"


def test_post_notification_writes_tmux_dcs_wrapped_osc9_sequence() -> None:
    assert post_notification_writes_tmux_dcs_wrapped_osc9_sequence() == "\x1bPtmux;\x1b\x1b]9;done\x07\x1b\\"


def test_post_notification_escapes_escape_bytes_inside_tmux_payload() -> None:
    assert post_notification_escapes_escape_bytes_inside_tmux_payload() == "\x1bPtmux;\x1b\x1b]9;danger\x1b\x1b[31m\x07\x1b\\"


def test_escape_tmux_dcs_passthrough_payload_doubles_only_escape_bytes() -> None:
    assert escape_tmux_dcs_passthrough_payload(f"a{ESC}b{BEL}") == f"a{ESC}{ESC}b{BEL}"


def test_write_ansi_helper_delegates_to_command() -> None:
    stream = StringIO()

    write_ansi(PostNotification("hello", False), stream)

    assert stream.getvalue() == "\x1b]9;hello\x07"


def test_osc9_backend_notify_uses_passthrough_flag_and_flushes() -> None:
    class FlushRecordingStringIO(StringIO):
        def __init__(self) -> None:
            super().__init__()
            self.flushed = False

        def flush(self) -> None:
            self.flushed = True

    stream = FlushRecordingStringIO()
    backend = Osc9Backend.new(dcs_passthrough=True, stream=stream)

    backend.notify("done")

    assert stream.getvalue() == "\x1bPtmux;\x1b\x1b]9;done\x07\x1b\\"
    assert stream.flushed is True


def test_osc9_backend_notify_emits_one_sequence_per_call() -> None:
    stream = StringIO()
    backend = Osc9Backend.new(dcs_passthrough=False, stream=stream)

    backend.notify("first")
    backend.notify("second")

    assert stream.getvalue() == "\x1b]9;first\x07\x1b]9;second\x07"


def test_default_backend_is_plain_osc9_until_parent_detection_sets_tmux_flag() -> None:
    backend = default()

    assert backend.dcs_passthrough is False


def test_backend_new_detects_tmux_passthrough_semantics_from_environment() -> None:
    assert detect_tmux_dcs_passthrough({"TMUX": "/tmp/tmux-1000/default,1,0"}) is True
    assert detect_tmux_dcs_passthrough({}) is False


def test_windows_winapi_path_is_explicitly_rejected_and_ansi_supported() -> None:
    assert is_ansi_code_supported() is True
    with pytest.raises(OSError, match="use ANSI instead"):
        execute_winapi()
