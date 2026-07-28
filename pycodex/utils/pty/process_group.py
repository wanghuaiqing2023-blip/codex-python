"""Process-group helpers from codex-utils-pty/src/process_group.rs."""

from __future__ import annotations

import ctypes
import errno
import os
import signal
import sys
from typing import Any

_SIGKILL = getattr(signal, "SIGKILL", 9)
_SIGTERM = getattr(signal, "SIGTERM", 15)


def _is_not_found_error(exc: OSError) -> bool:
    return isinstance(exc, ProcessLookupError) or exc.errno in {errno.ESRCH, errno.ENOENT}


def set_parent_death_signal(parent_pid: int) -> None:
    if not sys.platform.startswith("linux"):
        return
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    if prctl(1, _SIGTERM, 0, 0, 0) == -1:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))
    if os.getppid() != int(parent_pid):
        os.kill(os.getpid(), _SIGTERM)


def detach_from_tty() -> None:
    if os.name == "nt":
        return
    try:
        os.setsid()
    except OSError as exc:
        if exc.errno == errno.EPERM:
            set_process_group()
        else:
            raise


def set_process_group() -> None:
    if os.name != "nt":
        os.setpgid(0, 0)


def kill_process_group_by_pid(pid: int) -> None:
    if os.name == "nt":
        return
    try:
        process_group_id = os.getpgid(pid)
    except OSError as exc:
        if _is_not_found_error(exc):
            return
        raise
    _killpg(process_group_id, _SIGKILL)


def _killpg(process_group_id: int, sig: int) -> None:
    try:
        os.killpg(process_group_id, sig)
    except OSError as exc:
        if not _is_not_found_error(exc):
            raise


def terminate_process_group(process_group_id: int) -> bool:
    if os.name == "nt":
        return False
    try:
        os.killpg(process_group_id, _SIGTERM)
        return True
    except OSError as exc:
        if _is_not_found_error(exc):
            return False
        raise


def kill_process_group(process_group_id: int) -> None:
    if os.name != "nt":
        _killpg(process_group_id, _SIGKILL)


def kill_child_process_group(child: Any) -> None:
    pid = getattr(child, "pid", None)
    if pid is not None:
        kill_process_group_by_pid(pid)


__all__ = [
    "detach_from_tty",
    "kill_child_process_group",
    "kill_process_group",
    "kill_process_group_by_pid",
    "set_parent_death_signal",
    "set_process_group",
    "terminate_process_group",
]
