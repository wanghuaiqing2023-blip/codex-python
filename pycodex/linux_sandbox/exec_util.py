"""Low-level exec helpers for the linux sandbox.

Port of ``codex/codex-rs/linux-sandbox/src/exec_util.rs``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class HasFileno(Protocol):
    def fileno(self) -> int: ...


FileDescriptorLike = int | HasFileno


def argv_to_cstrings(argv: Sequence[str]) -> list[bytes]:
    """Convert argv strings to CString-compatible byte payloads.

    Rust returns ``Vec<CString>`` and panics when any argument contains an
    interior NUL. Python represents the converted values as UTF-8 bytes without
    an appended trailing NUL; callers that need a C ABI can add it at the edge.
    """

    cstrings: list[bytes] = []
    for arg in argv:
        if not isinstance(arg, str):
            raise TypeError("argv entries must be strings")
        if "\x00" in arg:
            raise ValueError("failed to convert argv to CString: nul byte found in provided data")
        cstrings.append(arg.encode())
    return cstrings


def make_files_inheritable(files: Sequence[FileDescriptorLike]) -> None:
    for file in files:
        clear_cloexec(_fileno(file))


def clear_cloexec(fd: int) -> None:
    if not isinstance(fd, int):
        raise TypeError("fd must be an integer")
    try:
        os.set_inheritable(fd, True)
    except OSError as err:
        raise RuntimeError(
            f"failed to clear CLOEXEC for preserved bubblewrap file descriptor {fd}: {err}"
        ) from err


def _fileno(file: FileDescriptorLike) -> int:
    if isinstance(file, int):
        return file
    if not isinstance(file, HasFileno):
        raise TypeError("files must contain file descriptors or objects with fileno()")
    return file.fileno()


__all__ = [
    "FileDescriptorLike",
    "argv_to_cstrings",
    "clear_cloexec",
    "make_files_inheritable",
]
