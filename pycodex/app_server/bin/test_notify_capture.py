"""Projection for Rust ``codex-app-server/src/bin/test_notify_capture.rs``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Sequence


class TestNotifyCaptureError(ValueError):
    """Raised when the test notify-capture helper arguments are invalid."""


def test_notify_capture_temp_path(output_path: str | os.PathLike[str]) -> Path:
    """Mirror Rust ``PathBuf::with_extension("json.tmp")``."""

    return Path(output_path).with_suffix(".json.tmp")


TestNotifyCaptureError.__test__ = False
test_notify_capture_temp_path.__test__ = False


def payload_to_utf8_text(payload: str | bytes | os.PathLike[str]) -> str:
    """Mirror Rust ``OsString::into_string`` for the payload argument."""

    if isinstance(payload, bytes):
        try:
            return payload.decode()
        except UnicodeDecodeError as exc:
            raise TestNotifyCaptureError("payload must be valid UTF-8") from exc
    value = os.fspath(payload)
    if isinstance(value, bytes):
        try:
            return value.decode()
        except UnicodeDecodeError as exc:
            raise TestNotifyCaptureError("payload must be valid UTF-8") from exc
    return value


def write_test_notify_capture_payload(
    output_path: str | os.PathLike[str],
    payload: str | bytes | os.PathLike[str],
) -> Path:
    """Write payload to ``output.with_extension("json.tmp")`` then move it."""

    destination = Path(output_path)
    temp_path = test_notify_capture_temp_path(destination)
    temp_path.write_text(payload_to_utf8_text(payload))
    os.replace(temp_path, destination)
    return destination


def run_test_notify_capture(argv: Sequence[str | bytes | os.PathLike[str]]) -> Path:
    """Run the Rust-shaped helper argument contract.

    ``argv`` includes the program name. Extra arguments are ignored, matching
    the Rust helper, which reads only the first two post-program arguments.
    """

    args = list(argv)[1:]
    if not args:
        raise TestNotifyCaptureError("missing output path argument")
    output_path = args[0]
    if len(args) < 2:
        raise TestNotifyCaptureError("missing payload argument")
    return write_test_notify_capture_payload(output_path, args[1])


def main(argv: Iterable[str | bytes | os.PathLike[str]] | None = None) -> int:
    """Small CLI wrapper for local parity use."""

    import sys

    try:
        run_test_notify_capture(list(sys.argv if argv is None else argv))
    except TestNotifyCaptureError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


__all__ = [
    "TestNotifyCaptureError",
    "main",
    "payload_to_utf8_text",
    "run_test_notify_capture",
    "test_notify_capture_temp_path",
    "write_test_notify_capture_payload",
]
