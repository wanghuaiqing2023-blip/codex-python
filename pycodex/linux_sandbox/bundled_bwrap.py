"""Bundled bubblewrap discovery and digest verification.

Port of ``codex/codex-rs/linux-sandbox/src/bundled_bwrap.rs``.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from pycodex.install_context import InstallContext

from . import bazel_bwrap
from .exec_util import argv_to_cstrings, make_files_inheritable

SHA256_HEX_LEN = 64
NULL_SHA256_DIGEST = bytes(32)


@dataclass(frozen=True)
class BundledBwrapLauncher:
    program: Path

    def exec(self, argv: list[str], preserved_files: list[object] | None = None) -> None:
        preserved_files = [] if preserved_files is None else preserved_files
        expected = expected_sha256()
        with self.program.open("rb") as bwrap_file:
            verify_digest(bwrap_file, expected, self.program)
            make_files_inheritable(preserved_files)
            argv_to_cstrings(argv)
            fd_path = f"/proc/self/fd/{bwrap_file.fileno()}"
            try:
                os.execv(fd_path, argv)
            except OSError as err:
                raise RuntimeError(
                    f"failed to exec bundled bubblewrap {self.program} via {fd_path}: {err}"
                ) from err


def launcher(
    context: InstallContext | None = None,
    current_exe: Path | str | None = None,
) -> BundledBwrapLauncher | None:
    context = InstallContext.current() if context is None else context
    exe = Path(sys.executable) if current_exe is None else Path(current_exe)
    program = find_for_install_context(context) or find_legacy_for_exe(exe)
    return BundledBwrapLauncher(program) if program is not None else None


def find_for_install_context(context: InstallContext) -> Path | None:
    resource = context.bundled_resource("bwrap")
    if resource is None:
        return None
    path = _as_path(resource)
    return path if is_executable_file(path) else None


def find_legacy_for_exe(exe: Path | str) -> Path | None:
    for candidate in legacy_candidates_for_exe(Path(exe)):
        if is_executable_file(candidate):
            if not candidate.is_absolute():
                raise RuntimeError(f"failed to normalize bundled bubblewrap path {candidate}")
            return candidate
    return None


def legacy_candidates_for_exe(
    exe: Path,
    *,
    bazel_candidate: Path | None | object = ...,
) -> list[Path]:
    exe_dir = exe.parent
    if str(exe_dir) == "":
        return []

    candidates = [
        exe_dir / "codex-resources" / "bwrap",
    ]
    package_target_dir = exe_dir.parent
    if package_target_dir != exe_dir:
        candidates.append(package_target_dir / "codex-resources" / "bwrap")
    candidates.append(exe_dir / "bwrap")

    if bazel_candidate is ...:
        bazel_candidate = bazel_bwrap.candidate()
    if isinstance(bazel_candidate, Path):
        candidates.append(bazel_candidate)
    return candidates


def is_executable_file(path: Path | str) -> bool:
    path = Path(path)
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    if not stat.S_ISREG(mode):
        return False
    if os.name == "nt":
        return True
    return bool(mode & 0o111)


def expected_sha256(raw_digest: str | None = None) -> bytes | None:
    raw_digest = os.environ.get("CODEX_BWRAP_SHA256") if raw_digest is None else raw_digest
    if raw_digest is None:
        return None
    digest = parse_sha256_hex(raw_digest)
    return None if digest == NULL_SHA256_DIGEST else digest


def verify_digest(file: BinaryIO, expected: bytes | None, path: Path | str) -> None:
    if expected is None:
        return
    try:
        current = file.tell()
        file.seek(0)
        actual = hashlib.sha256(file.read()).digest()
        file.seek(current)
    except OSError as err:
        raise RuntimeError(f"failed to read bundled bubblewrap {path} for digest verification: {err}") from err
    if actual != expected:
        raise ValueError(
            f"bundled bubblewrap digest mismatch for {path}: "
            f"expected sha256:{bytes_to_hex(expected)}, got sha256:{bytes_to_hex(actual)}"
        )


def parse_sha256_hex(raw: str) -> bytes:
    if len(raw) != SHA256_HEX_LEN:
        raise ValueError(f"expected {SHA256_HEX_LEN} hex characters, got {len(raw)}")
    try:
        return bytes.fromhex(raw)
    except ValueError as err:
        # Match Rust's offset-oriented wording closely enough for diagnostics.
        for index in range(0, len(raw), 2):
            try:
                bytes.fromhex(raw[index : index + 2])
            except ValueError as byte_err:
                raise ValueError(f"invalid hex byte at offset {index}: {byte_err}") from err
        raise


def bytes_to_hex(value: bytes) -> str:
    if len(value) != 32:
        raise ValueError("sha256 digest must be 32 bytes")
    return value.hex()


def _as_path(value: object) -> Path:
    if isinstance(value, Path):
        return value
    as_path = getattr(value, "as_path", None)
    if callable(as_path):
        return Path(as_path())
    return Path(value)  # type: ignore[arg-type]


__all__ = [
    "BundledBwrapLauncher",
    "NULL_SHA256_DIGEST",
    "SHA256_HEX_LEN",
    "bytes_to_hex",
    "expected_sha256",
    "find_for_install_context",
    "find_legacy_for_exe",
    "is_executable_file",
    "launcher",
    "legacy_candidates_for_exe",
    "parse_sha256_hex",
    "verify_digest",
]
