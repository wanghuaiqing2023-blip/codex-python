from pathlib import Path

import pytest

from pycodex.app_server.bin.notify_capture import (
    NotifyCaptureError,
    notify_capture_temp_path,
    payload_to_lossy_text,
    run_notify_capture,
    write_notify_capture_payload,
)


def test_notify_capture_temp_path_matches_rust_display_format(tmp_path: Path) -> None:
    # Rust: codex-app-server/src/bin/notify_capture.rs uses
    # format!("{}.tmp", output_path.display()) instead of with_extension.
    output_path = tmp_path / "capture.json"

    assert notify_capture_temp_path(output_path) == Path(f"{output_path}.tmp")


def test_run_notify_capture_requires_output_path_argument() -> None:
    # Rust: missing first argument returns "expected output path as first argument".
    with pytest.raises(NotifyCaptureError, match="expected output path as first argument"):
        run_notify_capture(["codex-app-server-test-notify-capture"])


def test_run_notify_capture_requires_payload_argument(tmp_path: Path) -> None:
    # Rust: missing payload returns "expected payload as final argument".
    with pytest.raises(NotifyCaptureError, match="expected payload as final argument"):
        run_notify_capture(["codex-app-server-test-notify-capture", tmp_path / "capture.json"])


def test_run_notify_capture_rejects_extra_arguments(tmp_path: Path) -> None:
    # Rust: extra arguments reuse the final-payload error string.
    with pytest.raises(NotifyCaptureError, match="expected payload as final argument"):
        run_notify_capture(
            [
                "codex-app-server-test-notify-capture",
                tmp_path / "capture.json",
                '{"ok":true}',
                "extra",
            ]
        )


def test_write_notify_capture_payload_moves_synced_temp_file(tmp_path: Path) -> None:
    # Rust: write payload bytes to output.tmp, sync, then rename into output.
    output_path = tmp_path / "capture.json"

    assert write_notify_capture_payload(output_path, '{"method":"notify"}') == output_path

    assert output_path.read_text() == '{"method":"notify"}'
    assert not notify_capture_temp_path(output_path).exists()


def test_run_notify_capture_accepts_pathlike_output_and_payload(tmp_path: Path) -> None:
    output_path = tmp_path / "capture.json"

    assert run_notify_capture(["codex-app-server-test-notify-capture", output_path, "payload"]) == output_path

    assert output_path.read_text() == "payload"


def test_payload_to_lossy_text_replaces_invalid_bytes() -> None:
    # Rust: OsString payload is converted with to_string_lossy().
    assert payload_to_lossy_text(b"ok\xff") == "ok\ufffd"

