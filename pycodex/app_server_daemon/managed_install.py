from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path


def managed_codex_bin(codex_home: Path) -> Path:
    file_name = "codex.exe" if os.name == "nt" else "codex"
    return codex_home / "packages" / "standalone" / "current" / file_name


async def resolved_managed_codex_bin(codex_bin: Path) -> Path:
    try:
        return await asyncio.to_thread(codex_bin.resolve, True)
    except OSError as exc:
        raise RuntimeError(
            f"failed to resolve managed Codex binary {codex_bin}: {exc}"
        ) from exc


async def managed_codex_version(codex_bin: Path) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            str(codex_bin),
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await process.communicate()
    except OSError as exc:
        raise RuntimeError(
            f"failed to invoke managed Codex binary {codex_bin}: {exc}"
        ) from exc
    if process.returncode != 0:
        raise RuntimeError(
            f"managed Codex binary {codex_bin} exited with status {process.returncode}"
        )
    try:
        return parse_codex_version(stdout.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"managed Codex version was not utf-8: {codex_bin}") from exc


def parse_codex_version(output: str) -> str:
    parts = output.split()
    if len(parts) < 2 or not parts[1]:
        raise ValueError("managed Codex version output was malformed")
    return parts[1]


@dataclass(frozen=True)
class ExecutableIdentity:
    digest: bytes


async def executable_identity(executable: Path) -> ExecutableIdentity:
    try:
        contents = await asyncio.to_thread(executable.read_bytes)
    except OSError as exc:
        raise RuntimeError(f"failed to read executable {executable}: {exc}") from exc
    return executable_identity_from_bytes(contents)


def executable_identity_from_bytes(contents: bytes) -> ExecutableIdentity:
    return ExecutableIdentity(hashlib.sha256(contents).digest())


__all__ = [
    "ExecutableIdentity",
    "executable_identity",
    "executable_identity_from_bytes",
    "managed_codex_bin",
    "managed_codex_version",
    "parse_codex_version",
    "resolved_managed_codex_bin",
]
