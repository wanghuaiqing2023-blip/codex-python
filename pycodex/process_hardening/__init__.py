"""Port of Rust ``codex-process-hardening`` public API.

Rust source:
- ``codex/codex-rs/process-hardening/src/lib.rs``

The Rust crate is intended for pre-main process hardening. Python cannot
install a Rust-style ``#[ctor]`` hook from this module alone, so the same
operations are exposed as explicit functions.
"""

from __future__ import annotations

import ctypes
import os
import platform
import resource
from typing import Iterable


PRCTL_FAILED_EXIT_CODE = 5
PTRACE_DENY_ATTACH_FAILED_EXIT_CODE = 6
SET_RLIMIT_CORE_FAILED_EXIT_CODE = 7

PR_SET_DUMPABLE = 4


def pre_main_hardening() -> None:
    system = platform.system().lower()
    if system == "linux" or "android" in system:
        pre_main_hardening_linux()
    elif system == "darwin":
        pre_main_hardening_macos()
    elif system in {"freebsd", "openbsd"}:
        pre_main_hardening_bsd()
    elif system == "windows":
        pre_main_hardening_windows()


def pre_main_hardening_linux() -> None:
    try:
        disable_process_dumping()
    except OSError as exc:
        raise SystemExit(PRCTL_FAILED_EXIT_CODE) from exc
    set_core_file_size_limit_to_zero()
    remove_env_vars_with_prefix(b"LD_")


def disable_process_dumping() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    ret_code = libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)
    if ret_code != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))


def pre_main_hardening_bsd() -> None:
    set_core_file_size_limit_to_zero()
    remove_env_vars_with_prefix(b"LD_")


def pre_main_hardening_macos() -> None:
    set_core_file_size_limit_to_zero()
    remove_env_vars_with_prefix(b"DYLD_")


def pre_main_hardening_windows() -> None:
    return None


def set_core_file_size_limit_to_zero() -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (OSError, ValueError) as exc:
        raise SystemExit(SET_RLIMIT_CORE_FAILED_EXIT_CODE) from exc


def remove_env_vars_with_prefix(prefix: bytes) -> None:
    if hasattr(os, "environb"):
        for key in env_keys_with_prefix(os.environb.items(), prefix):
            os.environb.pop(key, None)
        return

    text_prefix = prefix.decode("utf-8", errors="surrogateescape")
    for key in [key for key in os.environ if key.startswith(text_prefix)]:
        os.environ.pop(key, None)


def env_keys_with_prefix(vars: Iterable[tuple[bytes | str, bytes | str]], prefix: bytes) -> list[bytes | str]:
    keys: list[bytes | str] = []
    for key, _ in vars:
        key_bytes = key if isinstance(key, bytes) else key.encode("utf-8", errors="surrogateescape")
        if key_bytes.startswith(prefix):
            keys.append(key)
    return keys


__all__ = [
    "PRCTL_FAILED_EXIT_CODE",
    "PTRACE_DENY_ATTACH_FAILED_EXIT_CODE",
    "SET_RLIMIT_CORE_FAILED_EXIT_CODE",
    "disable_process_dumping",
    "env_keys_with_prefix",
    "pre_main_hardening",
    "pre_main_hardening_bsd",
    "pre_main_hardening_linux",
    "pre_main_hardening_macos",
    "pre_main_hardening_windows",
    "remove_env_vars_with_prefix",
    "set_core_file_size_limit_to_zero",
]
