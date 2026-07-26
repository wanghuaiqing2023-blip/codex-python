"""Locate and materialize bundled helper executables for sandbox launch."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
from enum import Enum
from pathlib import Path

from .logging import log_note
from .setup import sandbox_bin_dir, sandbox_dir


DEV_BUILD_VERSION_SENTINEL = "0.0.0"
BIN_DIRNAME = "bin"
RESOURCES_DIRNAME = "codex-resources"
_HELPER_PATH_CACHE: dict[str, Path] = {}
_CACHE_LOCK = threading.Lock()


class HelperExecutable(str, Enum):
    COMMAND_RUNNER = "codex-command-runner.exe"

    @property
    def label(self) -> str:
        return "command-runner"


def helper_bin_dir(codex_home: str | Path) -> Path:
    return sandbox_bin_dir(codex_home)


def legacy_lookup(kind: HelperExecutable) -> Path:
    candidate = bundled_executable_path_for_exe(
        Path(sys.executable),
        kind.value,
    )
    return candidate if candidate is not None else Path(kind.value)


def resolve_helper_for_launch(
    kind: HelperExecutable,
    codex_home: str | Path,
    log_dir: str | Path | None = None,
) -> Path:
    try:
        return copy_helper_if_needed(kind, codex_home, log_dir)
    except OSError as exc:
        fallback = legacy_lookup(kind)
        log_note(
            f"helper copy failed for {kind.label}: {exc}; "
            f"falling back to legacy path {fallback}",
            log_dir,
        )
        return fallback


def resolve_current_exe_for_launch(
    codex_home: str | Path,
    fallback_executable: str,
) -> Path:
    source = Path(sys.executable)
    if not source.is_file():
        return Path(fallback_executable)
    # A copied CPython executable cannot reliably locate its runtime DLL and
    # stdlib. The current interpreter is therefore the Python counterpart of
    # Rust's already-materialized current executable.
    if source.name.lower().startswith(("python", "pypy")):
        return source
    destination = helper_bin_dir(codex_home) / source.name
    try:
        _copy_from_source_if_needed(source, destination)
        return destination
    except OSError as exc:
        log_note(
            f"helper copy failed for current executable: {exc}; "
            f"falling back to legacy path {source}",
            sandbox_dir(codex_home),
        )
        return source


def copy_helper_if_needed(
    kind: HelperExecutable,
    codex_home: str | Path,
    log_dir: str | Path | None = None,
) -> Path:
    key = f"{kind.value}|{Path(codex_home)}"
    with _CACHE_LOCK:
        cached = _HELPER_PATH_CACHE.get(key)
    if cached is not None:
        return cached
    source = bundled_executable_path_for_exe(
        Path(sys.executable),
        kind.value,
    )
    if source is None:
        raise FileNotFoundError(kind.value)
    suffix = _helper_version_suffix(source)
    destination = helper_bin_dir(codex_home) / _materialized_file_name(
        kind,
        suffix,
    )
    _copy_from_source_if_needed(source, destination)
    with _CACHE_LOCK:
        _HELPER_PATH_CACHE[key] = destination
    log_note(
        f"helper copy: resolved {kind.label} source={source} "
        f"destination={destination}",
        log_dir,
    )
    return destination


def bundled_executable_path_for_exe(
    executable: str | Path,
    file_name: str,
) -> Path | None:
    directory = Path(executable).parent
    direct = directory / file_name
    if direct.is_file():
        return direct
    if directory.name == BIN_DIRNAME:
        packaged = directory.parent / RESOURCES_DIRNAME / file_name
        if packaged.is_file():
            return packaged
    resource = directory / RESOURCES_DIRNAME / file_name
    return resource if resource.is_file() else None


def _materialized_file_name(kind: HelperExecutable, suffix: str) -> str:
    source = Path(kind.value)
    return f"{source.stem}-{suffix}{source.suffix}"


def _helper_version_suffix(source: Path) -> str:
    version = os.environ.get("PYCODEX_VERSION", DEV_BUILD_VERSION_SENTINEL)
    if version != DEV_BUILD_VERSION_SENTINEL:
        return version
    stat = source.stat()
    return f"{stat.st_size}-{int(stat.st_mtime):x}"


def _copy_from_source_if_needed(source: Path, destination: Path) -> bool:
    if _destination_is_fresh(source, destination):
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _destination_is_fresh(source: Path, destination: Path) -> bool:
    try:
        source_stat = source.stat()
        destination_stat = destination.stat()
    except FileNotFoundError:
        return False
    return (
        source_stat.st_size == destination_stat.st_size
        and destination_stat.st_mtime >= source_stat.st_mtime
    )


__all__ = [
    "BIN_DIRNAME",
    "RESOURCES_DIRNAME",
    "HelperExecutable",
    "bundled_executable_path_for_exe",
    "copy_helper_if_needed",
    "helper_bin_dir",
    "legacy_lookup",
    "resolve_current_exe_for_launch",
    "resolve_helper_for_launch",
]
