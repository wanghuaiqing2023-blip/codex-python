"""Installation ID persistence ported from ``core/src/installation_id.rs``."""

from __future__ import annotations

import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

INSTALLATION_ID_FILENAME = "installation_id"


def resolve_installation_id(codex_home: Path | str) -> str:
    """Return the stable installation UUID stored under ``codex_home``.

    The upstream implementation creates ``<codex_home>/installation_id`` when
    missing, reuses any valid UUID already present, and rewrites invalid file
    contents with a fresh UUID.
    """

    codex_home = Path(codex_home)
    path = codex_home / INSTALLATION_ID_FILENAME
    codex_home.mkdir(parents=True, exist_ok=True)

    with path.open("a+", encoding="utf-8", newline="") as file:
        with _locked_file(file):
            if sys.platform != "win32":
                os.chmod(path, 0o644)

            file.seek(0)
            contents = file.read()
            existing = _parse_uuid(contents.strip())
            if existing is not None:
                return existing

            installation_id = str(uuid.uuid4())
            file.seek(0)
            file.truncate(0)
            file.write(installation_id)
            file.flush()
            os.fsync(file.fileno())
            return installation_id


def _parse_uuid(value: str) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


@contextmanager
def _locked_file(file: TextIO) -> Iterator[None]:
    if sys.platform == "win32":
        import msvcrt

        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(file.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)


__all__ = [
    "INSTALLATION_ID_FILENAME",
    "resolve_installation_id",
]
