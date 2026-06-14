import base64
import io

import pytest

from pycodex.tui.clipboard_copy import (
    ClipboardCopyError,
    ClipboardLease,
    OSC52_MAX_RAW_BYTES,
    copy_to_clipboard_with,
    local_environment,
    local_tmux_environment,
    local_wsl_environment,
    osc52_sequence,
    remote_environment,
    remote_tmux_environment,
    tmux_clipboard_copy_ready,
    write_osc52_to_writer,
)


def _ok(_text: str) -> None:
    return None


def _err(message: str):
    def inner(_text: str) -> None:
        raise ClipboardCopyError(message)

    return inner


def test_osc52_sequence_matches_rust_encoding_tests() -> None:
    # Rust source: clipboard_copy.rs::tests::osc52_encoding_roundtrips.
    text = "# Hello\n\n```rust\nfn main() {}\n```\n"
    sequence = osc52_sequence(text, tmux=False)
    encoded = sequence.removeprefix("\x1b]52;c;").removesuffix("\x07")
    assert base64.b64decode(encoded) == text.encode()

    assert osc52_sequence("hello", tmux=True) == "\x1bPtmux;\x1b\x1b]52;c;aGVsbG8=\x07\x1b\\"

    with pytest.raises(ClipboardCopyError) as exc:
        osc52_sequence("x" * (OSC52_MAX_RAW_BYTES + 1), tmux=False)
    assert str(exc.value) == f"OSC 52 payload too large ({OSC52_MAX_RAW_BYTES + 1} bytes; max {OSC52_MAX_RAW_BYTES})"


def test_write_osc52_to_writer_emits_sequence_verbatim() -> None:
    output = io.StringIO()
    write_osc52_to_writer(output, "\x1b]52;c;aGVsbG8=\x07")
    assert output.getvalue() == "\x1b]52;c;aGVsbG8=\x07"


def test_write_osc52_to_writer_distinguishes_write_and_flush_errors() -> None:
    class WriteFailure:
        def write(self, _sequence: str) -> None:
            raise OSError("disk full")

        def flush(self) -> None:
            raise AssertionError("flush should not be called after write failure")

    class FlushFailure:
        def __init__(self) -> None:
            self.written = ""

        def write(self, sequence: str) -> None:
            self.written += sequence

        def flush(self) -> None:
            raise OSError("blocked")

    with pytest.raises(ClipboardCopyError) as exc:
        write_osc52_to_writer(WriteFailure(), "seq")
    assert str(exc.value) == "failed to write OSC 52: disk full"

    flush_failure = FlushFailure()
    with pytest.raises(ClipboardCopyError) as exc:
        write_osc52_to_writer(flush_failure, "seq")
    assert str(exc.value) == "failed to flush OSC 52: blocked"
    assert flush_failure.written == "seq"


def test_ssh_uses_terminal_clipboard_and_skips_native() -> None:
    calls: list[str] = []

    result = copy_to_clipboard_with(
        "hello",
        remote_environment(),
        lambda text: calls.append(f"tmux:{text}"),
        lambda text: calls.append(f"osc:{text}"),
        lambda text: calls.append(f"native:{text}"),
        lambda text: calls.append(f"wsl:{text}"),
    )

    assert result is None
    assert calls == ["osc:hello"]


def test_ssh_error_messages_match_rust() -> None:
    with pytest.raises(ClipboardCopyError) as exc:
        copy_to_clipboard_with("hello", remote_environment(), _ok, _err("blocked"), lambda _: None, _ok)
    assert str(exc.value) == "OSC 52 clipboard copy failed over SSH: blocked"

    with pytest.raises(ClipboardCopyError) as exc:
        copy_to_clipboard_with(
            "hello",
            remote_tmux_environment(),
            _err("tmux unavailable"),
            _err("osc blocked"),
            lambda _: None,
            _ok,
        )
    assert (
        str(exc.value)
        == "terminal clipboard copy failed over SSH: tmux clipboard: tmux unavailable; OSC 52 fallback: osc blocked"
    )


def test_ssh_inside_tmux_prefers_tmux_then_osc52_fallback() -> None:
    calls: list[str] = []
    result = copy_to_clipboard_with(
        "hello",
        remote_tmux_environment(),
        lambda text: calls.append(f"tmux:{text}"),
        lambda text: calls.append(f"osc:{text}"),
        lambda _: None,
        _ok,
    )
    assert result is None
    assert calls == ["tmux:hello"]

    calls.clear()
    result = copy_to_clipboard_with(
        "hello",
        remote_tmux_environment(),
        _err("tmux unavailable"),
        lambda text: calls.append(f"osc:{text}"),
        lambda _: None,
        _ok,
    )
    assert result is None
    assert calls == ["osc:hello"]


def test_tmux_clipboard_copy_ready_matches_rust_boundaries() -> None:
    tmux_clipboard_copy_ready(
        lambda: "external\n",
        lambda: "193: Ms: (string) \\033]52;%p1%s;%p2%s\\a\n",
    )

    with pytest.raises(ClipboardCopyError) as exc:
        tmux_clipboard_copy_ready(lambda: "off\n", lambda: "not queried")
    assert str(exc.value) == "tmux clipboard forwarding is disabled"

    with pytest.raises(ClipboardCopyError) as exc:
        tmux_clipboard_copy_ready(lambda: "external\n", lambda: "193: Ms: [missing]\n")
    assert str(exc.value) == "tmux clipboard forwarding is unavailable: missing Ms capability"


def test_local_uses_native_first_and_preserves_lease() -> None:
    lease = ClipboardLease.test()
    calls: list[str] = []

    result = copy_to_clipboard_with(
        "hello",
        local_wsl_environment(),
        _ok,
        lambda text: calls.append(f"osc:{text}"),
        lambda text: lease,
        lambda text: calls.append(f"wsl:{text}"),
    )

    assert result is lease
    assert calls == []


def test_local_fallback_order_and_errors_match_rust() -> None:
    calls: list[str] = []
    result = copy_to_clipboard_with(
        "hello",
        local_environment(),
        _ok,
        lambda text: calls.append(f"osc:{text}"),
        _err("native unavailable"),
        _ok,
    )
    assert result is None
    assert calls == ["osc:hello"]

    calls.clear()
    result = copy_to_clipboard_with(
        "hello",
        local_tmux_environment(),
        lambda text: calls.append(f"tmux:{text}"),
        lambda text: calls.append(f"osc:{text}"),
        _err("native unavailable"),
        _ok,
    )
    assert result is None
    assert calls == ["tmux:hello"]

    with pytest.raises(ClipboardCopyError) as exc:
        copy_to_clipboard_with("hello", local_environment(), _ok, _err("osc blocked"), _err("native unavailable"), _ok)
    assert str(exc.value) == "native clipboard: native unavailable; OSC 52 fallback: osc blocked"


def test_local_wsl_uses_powershell_then_terminal_fallback() -> None:
    calls: list[str] = []
    result = copy_to_clipboard_with(
        "hello",
        local_wsl_environment(),
        _ok,
        lambda text: calls.append(f"osc:{text}"),
        _err("native unavailable"),
        lambda text: calls.append(f"wsl:{text}"),
    )
    assert result is None
    assert calls == ["wsl:hello"]

    calls.clear()
    result = copy_to_clipboard_with(
        "hello",
        local_wsl_environment(),
        _ok,
        lambda text: calls.append(f"osc:{text}"),
        _err("native unavailable"),
        _err("powershell unavailable"),
    )
    assert result is None
    assert calls == ["osc:hello"]

    with pytest.raises(ClipboardCopyError) as exc:
        copy_to_clipboard_with(
            "hello",
            local_wsl_environment(),
            _ok,
            _err("osc blocked"),
            _err("native unavailable"),
            _err("powershell unavailable"),
        )
    assert (
        str(exc.value)
        == "native clipboard: native unavailable; WSL fallback: powershell unavailable; OSC 52 fallback: osc blocked"
    )


def test_local_tmux_reports_native_tmux_and_osc52_errors_when_all_fail() -> None:
    # Rust source: clipboard_copy.rs::tests::local_reports_both_errors_when_native_and_osc52_fail
    # plus the tmux terminal fallback branch in terminal_clipboard_copy_with.
    with pytest.raises(ClipboardCopyError) as exc:
        copy_to_clipboard_with(
            "hello",
            local_tmux_environment(),
            _err("tmux unavailable"),
            _err("osc blocked"),
            _err("native unavailable"),
            _ok,
        )

    assert (
        str(exc.value)
        == "native clipboard: native unavailable; terminal fallback: tmux clipboard: tmux unavailable; OSC 52 fallback: osc blocked"
    )
