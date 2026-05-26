"""Session rollout initialization error mapping ported from ``core/src/session_rollout_init_error.rs``."""

from __future__ import annotations

import errno
from pathlib import Path

from pycodex.protocol import CodexErr

from .rollout import SESSIONS_SUBDIR


def map_session_init_error(error: BaseException, codex_home: Path | str) -> CodexErr:
    for cause in _exception_chain(error):
        if isinstance(cause, OSError):
            mapped = map_rollout_io_error(cause, codex_home)
            if mapped is not None:
                return mapped

    return CodexErr.fatal(f"Failed to initialize session: {_format_exception_chain(error)}")


def map_rollout_io_error(error: OSError, codex_home: Path | str) -> CodexErr | None:
    codex_home_path = Path(codex_home)
    sessions_dir = codex_home_path / SESSIONS_SUBDIR
    error_kind = _normalized_errno(error)

    if error_kind in {errno.EACCES, errno.EPERM}:
        hint = (
            f"Codex cannot access session files at {sessions_dir} (permission denied). "
            "If sessions were created using sudo, fix ownership: "
            f"sudo chown -R $(whoami) {codex_home_path}"
        )
    elif error_kind == errno.ENOENT:
        hint = (
            f"Session storage missing at {sessions_dir}. "
            "Create the directory or choose a different Codex home."
        )
    elif error_kind == errno.EEXIST:
        hint = (
            f"Session storage path {sessions_dir} is blocked by an existing file. "
            "Remove or rename it so Codex can create sessions."
        )
    elif error_kind in _INVALID_DATA_ERRNOS:
        hint = (
            f"Session data under {sessions_dir} looks corrupt or unreadable. "
            "Clearing the sessions directory may help (this will remove saved threads)."
        )
    elif error_kind in {errno.EISDIR, errno.ENOTDIR}:
        hint = (
            f"Session storage path {sessions_dir} has an unexpected type. "
            "Ensure it is a directory Codex can use for session files."
        )
    else:
        return None

    return CodexErr.fatal(f"{hint} (underlying error: {error})")


def _exception_chain(error: BaseException) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return tuple(chain)


def _format_exception_chain(error: BaseException) -> str:
    return ": ".join(str(cause) for cause in _exception_chain(error))


def _normalized_errno(error: OSError) -> int | None:
    if error.errno is not None:
        return error.errno
    if isinstance(error, PermissionError):
        return errno.EACCES
    if isinstance(error, FileNotFoundError):
        return errno.ENOENT
    if isinstance(error, FileExistsError):
        return errno.EEXIST
    if isinstance(error, IsADirectoryError):
        return errno.EISDIR
    if isinstance(error, NotADirectoryError):
        return errno.ENOTDIR
    return None


_INVALID_DATA_ERRNOS = {
    errno.EINVAL,
    *(code for name in ("EILSEQ", "EBADMSG") if (code := getattr(errno, name, None)) is not None),
}


__all__ = [
    "map_rollout_io_error",
    "map_session_init_error",
]
