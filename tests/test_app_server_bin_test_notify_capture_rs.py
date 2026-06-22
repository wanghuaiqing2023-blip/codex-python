from pathlib import Path

import pytest

from pycodex.app_server.bin.test_notify_capture import (
    TestNotifyCaptureError,
    payload_to_utf8_text,
    run_test_notify_capture,
    test_notify_capture_temp_path,
    write_test_notify_capture_payload,
)


def test_test_notify_capture_temp_path_matches_rust_with_extension(tmp_path: Path) -> None:
    # Rust: codex-app-server/src/bin/test_notify_capture.rs uses
    # output_path.with_extension("json.tmp").
    assert test_notify_capture_temp_path(tmp_path / "capture.json") == tmp_path / "capture.json.tmp"
    assert test_notify_capture_temp_path(tmp_path / "capture") == tmp_path / "capture.json.tmp"


def test_run_test_notify_capture_requires_output_argument() -> None:
    # Rust: missing first argument returns "missing output path argument".
    with pytest.raises(TestNotifyCaptureError, match="missing output path argument"):
        run_test_notify_capture(["test_notify_capture"])


def test_run_test_notify_capture_requires_payload_argument(tmp_path: Path) -> None:
    # Rust: missing payload returns "missing payload argument".
    with pytest.raises(TestNotifyCaptureError, match="missing payload argument"):
        run_test_notify_capture(["test_notify_capture", tmp_path / "capture.json"])


def test_payload_to_utf8_text_rejects_invalid_bytes() -> None:
    # Rust: OsString::into_string maps invalid payload text to this anyhow error.
    with pytest.raises(TestNotifyCaptureError, match="payload must be valid UTF-8"):
        payload_to_utf8_text(b"bad\xff")


def test_write_test_notify_capture_payload_moves_json_tmp_file(tmp_path: Path) -> None:
    # Rust: std::fs::write(temp_path, payload) then std::fs::rename(temp, output).
    output_path = tmp_path / "capture.json"

    assert write_test_notify_capture_payload(output_path, '{"ok":true}') == output_path

    assert output_path.read_text() == '{"ok":true}'
    assert not test_notify_capture_temp_path(output_path).exists()


def test_run_test_notify_capture_ignores_extra_arguments(tmp_path: Path) -> None:
    # Rust reads only the first two post-program arguments.
    output_path = tmp_path / "capture.json"

    assert run_test_notify_capture(["test_notify_capture", output_path, "payload", "ignored"]) == output_path

    assert output_path.read_text() == "payload"

