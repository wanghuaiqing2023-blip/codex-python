"""Arg0 dispatch helpers ported from ``codex-rs/arg0``.

This module carries the dependency-light parts of the Rust arg0 crate: dispatch
path records, path-entry guards, linux sandbox executable preference, and stale
helper-directory cleanup.  Full process re-entry dispatch remains owned by CLI
startup integration.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import asyncio
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import IO

LOCK_FILENAME = ".lock"
APPLY_PATCH_ARG0 = "apply_patch"
MISSPELLED_APPLY_PATCH_ARG0 = "applypatch"
EXECVE_WRAPPER_ARG0 = "codex-execve-wrapper"
CODEX_LINUX_SANDBOX_ARG0 = "codex-linux-sandbox"
CODEX_FS_HELPER_ARG1 = "--codex-fs-helper"
CODEX_CORE_APPLY_PATCH_ARG1 = "--codex-run-as-apply-patch"
TOKIO_WORKER_STACK_SIZE_BYTES = 16 * 1024 * 1024
ILLEGAL_ENV_VAR_PREFIX = "CODEX_"


@dataclass(frozen=True)
class Arg0DispatchPaths:
    codex_self_exe: Path | None = None
    codex_linux_sandbox_exe: Path | None = None
    main_execve_wrapper_exe: Path | None = None

    def __post_init__(self) -> None:
        for name in ("codex_self_exe", "codex_linux_sandbox_exe", "main_execve_wrapper_exe"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Path):
                object.__setattr__(self, name, Path(value))


class Arg0PathEntryGuard:
    def __init__(self, temp_dir: tempfile.TemporaryDirectory[str], lock_file: IO[bytes], paths: Arg0DispatchPaths) -> None:
        if not isinstance(paths, Arg0DispatchPaths):
            raise TypeError("paths must be an Arg0DispatchPaths")
        self._temp_dir = temp_dir
        self._lock_file = lock_file
        self._paths = paths

    @property
    def paths(self) -> Arg0DispatchPaths:
        return self._paths

    def close(self) -> None:
        try:
            self._lock_file.close()
        finally:
            self._temp_dir.cleanup()

    def __enter__(self) -> "Arg0PathEntryGuard":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def linux_sandbox_exe_path(path_entry_guard: Arg0PathEntryGuard | None, current_exe: Path | str | None) -> Path | None:
    if path_entry_guard is not None and path_entry_guard.paths.codex_linux_sandbox_exe is not None:
        return path_entry_guard.paths.codex_linux_sandbox_exe
    return Path(current_exe) if current_exe is not None else None


def load_dotenv(codex_home: Path | str | None = None) -> None:
    home = _codex_home(codex_home)
    dotenv_path = home / ".env"
    try:
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    set_filtered(_parse_dotenv_lines(lines))


def set_filtered(items: object) -> None:
    for key, value in items:  # type: ignore[assignment]
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key.upper().startswith(ILLEGAL_ENV_VAR_PREFIX):
            continue
        os.environ[key] = value


def prepend_path_entry_for_codex_aliases(
    codex_home: Path | str | None = None,
    current_exe: Path | str | None = None,
) -> Arg0PathEntryGuard:
    home = _codex_home(codex_home)
    home.mkdir(parents=True, exist_ok=True)
    temp_root = home / "tmp" / "arg0"
    temp_root.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        temp_root.chmod(0o700)
    janitor_cleanup(temp_root)

    temp_dir = tempfile.TemporaryDirectory(prefix="codex-arg0", dir=temp_root)
    path = Path(temp_dir.name)
    lock_path = path / LOCK_FILENAME
    lock_file = lock_path.open("w+b")
    exe = Path(current_exe) if current_exe is not None else Path(sys.executable)

    names = [APPLY_PATCH_ARG0, MISSPELLED_APPLY_PATCH_ARG0]
    if sys.platform.startswith("linux"):
        names.append("codex-linux-sandbox")
    if os.name != "nt":
        names.append(EXECVE_WRAPPER_ARG0)

    for name in names:
        if os.name == "nt":
            script = path / f"{name}.bat"
            script.write_text(f'@echo off\r\n"{exe}" --codex-run-as-apply-patch %*\r\n', encoding="utf-8")
        else:
            link = path / name
            try:
                link.symlink_to(exe)
            except FileExistsError:
                pass

    existing_path = os.environ.get("PATH", "")
    separator = ";" if os.name == "nt" else ":"
    os.environ["PATH"] = str(path) if not existing_path else f"{path}{separator}{existing_path}"

    paths = Arg0DispatchPaths(
        codex_self_exe=exe,
        codex_linux_sandbox_exe=path / "codex-linux-sandbox" if sys.platform.startswith("linux") else None,
        main_execve_wrapper_exe=path / EXECVE_WRAPPER_ARG0 if os.name != "nt" else None,
    )
    return Arg0PathEntryGuard(temp_dir, lock_file, paths)


def arg0_dispatch(
    argv: list[str] | None = None,
    handlers: dict[str, object] | None = None,
    codex_home: Path | str | None = None,
    current_exe: Path | str | None = None,
) -> Arg0PathEntryGuard | None:
    argv = list(sys.argv if argv is None else argv)
    handlers = {} if handlers is None else handlers
    argv0 = Path(argv[0]).name if argv else ""
    argv1 = argv[1] if len(argv) > 1 else ""

    if argv0 == EXECVE_WRAPPER_ARG0:
        _call_required_handler(handlers, "execve_wrapper", argv[1:])
        return None
    if argv0 == CODEX_LINUX_SANDBOX_ARG0:
        _call_required_handler(handlers, "linux_sandbox", argv[1:])
        return None
    if argv0 in {APPLY_PATCH_ARG0, MISSPELLED_APPLY_PATCH_ARG0}:
        _call_required_handler(handlers, "apply_patch", argv[1:])
        return None
    if argv1 == CODEX_FS_HELPER_ARG1:
        _call_required_handler(handlers, "fs_helper", argv[2:])
        return None
    if argv1 == CODEX_CORE_APPLY_PATCH_ARG1:
        _call_required_handler(handlers, "core_apply_patch", argv[2:])
        return None

    load_dotenv(codex_home)
    return prepend_path_entry_for_codex_aliases(codex_home=codex_home, current_exe=current_exe)


def arg0_dispatch_or_else(
    main_fn: object,
    argv: list[str] | None = None,
    handlers: dict[str, object] | None = None,
    codex_home: Path | str | None = None,
    current_exe: Path | str | None = None,
) -> object:
    guard = arg0_dispatch(argv=argv, handlers=handlers, codex_home=codex_home, current_exe=current_exe)
    exe = Path(current_exe) if current_exe is not None else Path(sys.executable)
    paths = Arg0DispatchPaths(
        codex_self_exe=exe,
        codex_linux_sandbox_exe=linux_sandbox_exe_path(guard, exe) if sys.platform.startswith("linux") else None,
        main_execve_wrapper_exe=guard.paths.main_execve_wrapper_exe if guard is not None else None,
    )
    try:
        result = main_fn(paths)  # type: ignore[misc]
        if inspect.isawaitable(result):
            return asyncio.run(result)
        return result
    finally:
        if guard is not None:
            guard.close()


def janitor_cleanup(temp_root: Path | str) -> None:
    root = Path(temp_root)
    try:
        entries = list(root.iterdir())
    except FileNotFoundError:
        return
    for path in entries:
        if not path.is_dir():
            continue
        lock_file = try_lock_dir(path)
        if lock_file is None:
            continue
        try:
            lock_file.close()
            shutil.rmtree(path)
        except FileNotFoundError:
            continue


def try_lock_dir(directory: Path | str) -> IO[bytes] | None:
    lock_path = Path(directory) / LOCK_FILENAME
    try:
        lock_file = lock_path.open("r+b")
    except FileNotFoundError:
        return None
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                lock_file.close()
                return None
        else:
            import fcntl

            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                lock_file.close()
                return None
    except Exception:
        lock_file.close()
        raise
    return lock_file


def _codex_home(codex_home: Path | str | None) -> Path:
    if codex_home is not None:
        return Path(codex_home)
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured)
    return Path.home() / ".codex"


def _parse_dotenv_lines(lines: list[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            parsed.append((key, value))
    return parsed


def _call_required_handler(handlers: dict[str, object], name: str, args: list[str]) -> None:
    handler = handlers.get(name)
    if handler is None:
        raise NotImplementedError(f"arg0 dispatch handler required for {name}")
    result = handler(args)  # type: ignore[misc]
    if inspect.isawaitable(result):
        asyncio.run(result)


__all__ = [
    "APPLY_PATCH_ARG0",
    "Arg0DispatchPaths",
    "Arg0PathEntryGuard",
    "CODEX_CORE_APPLY_PATCH_ARG1",
    "CODEX_FS_HELPER_ARG1",
    "CODEX_LINUX_SANDBOX_ARG0",
    "EXECVE_WRAPPER_ARG0",
    "ILLEGAL_ENV_VAR_PREFIX",
    "LOCK_FILENAME",
    "MISSPELLED_APPLY_PATCH_ARG0",
    "TOKIO_WORKER_STACK_SIZE_BYTES",
    "arg0_dispatch",
    "arg0_dispatch_or_else",
    "janitor_cleanup",
    "linux_sandbox_exe_path",
    "load_dotenv",
    "prepend_path_entry_for_codex_aliases",
    "set_filtered",
    "try_lock_dir",
]
