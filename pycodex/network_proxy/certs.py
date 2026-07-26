"""Rust-aligned projection of ``codex-network-proxy::certs``."""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import fnmatch
import json
import os
import re
import socket
import stat
import sys
import time
from datetime import UTC, datetime
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlparse
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, Mapping, Sequence

JsonValue = Any

MANAGED_MITM_CA_DIR = "proxy"


MANAGED_MITM_CA_CERT = "ca.pem"


MANAGED_MITM_CA_KEY = "ca.key"


@dataclass(frozen=True)
class ManagedMitmCaPaths:
    cert_path: Path
    key_path: Path


def managed_ca_paths(codex_home: str | os.PathLike[str] | None = None) -> ManagedMitmCaPaths:
    if codex_home is None:
        home = os.environ.get("CODEX_HOME")
        if not home:
            home = str(Path.home() / ".codex")
        codex_home_path = Path(home)
    else:
        codex_home_path = Path(codex_home)
    proxy_dir = codex_home_path / MANAGED_MITM_CA_DIR
    return ManagedMitmCaPaths(
        cert_path=proxy_dir / MANAGED_MITM_CA_CERT,
        key_path=proxy_dir / MANAGED_MITM_CA_KEY,
    )


def validate_existing_ca_key_file(path: str | os.PathLike[str], *, unix: bool | None = None) -> None:
    check_unix = (os.name == "posix") if unix is None else bool(unix)
    if not check_unix:
        return

    key_path = Path(path)
    try:
        metadata = os.lstat(key_path)
    except OSError as exc:
        raise OSError(f"failed to stat CA key {key_path}") from exc

    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"refusing to use symlink for managed MITM CA key {key_path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"managed MITM CA key is not a regular file: {key_path}")

    mode = stat.S_IMODE(metadata.st_mode) & 0o777
    if mode & 0o077:
        raise PermissionError(
            f"managed MITM CA key {key_path} must not be group/world accessible "
            f"(mode={mode:o}; expected <= 600)"
        )


def write_atomic_create_new(path: str | os.PathLike[str], contents: bytes | str, mode: int = 0o600) -> None:
    target = Path(path)
    parent = target.parent
    if str(parent) in {"", "."}:
        raise ValueError("missing parent directory")
    if not parent.exists():
        raise FileNotFoundError(parent)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing file {target}")

    payload = contents.encode() if isinstance(contents, str) else bytes(contents)
    nanos = time.time_ns()
    pid = os.getpid()
    tmp_path = parent / f".{target.name}.tmp.{pid}.{nanos}"
    fd: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(tmp_path, flags, mode)
        with os.fdopen(fd, "wb") as file:
            fd = None
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(tmp_path, target)
            tmp_path.unlink()
        except FileExistsError:
            tmp_path.unlink(missing_ok=True)
            raise FileExistsError(f"refusing to overwrite existing file {target}")
        except OSError:
            if target.exists() or target.is_symlink():
                tmp_path.unlink(missing_ok=True)
                raise FileExistsError(f"refusing to overwrite existing file {target}")
            tmp_path.replace(target)
        try:
            dir_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except Exception:
        if fd is not None:
            os.close(fd)
        tmp_path.unlink(missing_ok=True)
        raise

__all__ = [
    "MANAGED_MITM_CA_CERT",
    "MANAGED_MITM_CA_DIR",
    "MANAGED_MITM_CA_KEY",
    "ManagedMitmCaPaths",
    "managed_ca_paths",
    "validate_existing_ca_key_file",
    "write_atomic_create_new",
]
