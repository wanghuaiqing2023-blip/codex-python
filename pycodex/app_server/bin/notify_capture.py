"""Projection for Rust ``codex-app-server/src/bin/notify_capture.rs``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Sequence


class NotifyCaptureError(ValueError):
    """Raised when the notify-capture binary arguments are invalid."""


def notify_capture_temp_path(output_path: str | os.PathLike[str]) -> Path:
    """Mirror Rust's ``format!("{}.tmp", output_path.display())`` temp path."""

    return Path(f"{Path(output_path)}.tmp")


def payload_to_lossy_text(payload: str | bytes | os.PathLike[str]) -> str:
    """Mirror Rust ``OsString::to_string_lossy`` for the payload argument."""

    if isinstance(payload, bytes):
        return payload.decode(errors="replace")
    return os.fspath(payload)


def write_notify_capture_payload(
    output_path: str | os.PathLike[str],
    payload: str | bytes | os.PathLike[str],
) -> Path:
    """Write payload through a synced temp file before moving into place."""

    destination = Path(output_path)
    temp_path = notify_capture_temp_path(destination)
    payload_text = payload_to_lossy_text(payload)

    with open(temp_path, "wb") as file:
        file.write(payload_text.encode())
        file.flush()
        os.fsync(file.fileno())

    os.replace(temp_path, destination)
    return destination


def run_notify_capture(argv: Sequence[str | bytes | os.PathLike[str]]) -> Path:
    """Run the Rust-shaped binary argument contract.

    ``argv`` mirrors ``env::args_os()`` and therefore includes the program name
    at index 0.
    """

    args = list(argv)
    remaining = args[1:]
    if not remaining:
        raise NotifyCaptureError("expected output path as first argument")
    output_path = remaining.pop(0)

    if not remaining:
        raise NotifyCaptureError("expected payload as final argument")
    payload = remaining.pop(0)

    if remaining:
        raise NotifyCaptureError("expected payload as final argument")

    return write_notify_capture_payload(output_path, payload)


def main(argv: Iterable[str | bytes | os.PathLike[str]] | None = None) -> int:
    """Small CLI wrapper for local parity use."""

    import sys

    try:
        run_notify_capture(list(sys.argv if argv is None else argv))
    except NotifyCaptureError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


__all__ = [
    "NotifyCaptureError",
    "main",
    "notify_capture_temp_path",
    "payload_to_lossy_text",
    "run_notify_capture",
    "write_notify_capture_payload",
]

