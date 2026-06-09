"""Port of Rust ``codex-login::auth::external_bearer``.

Rust source:
- ``codex/codex-rs/login/src/auth/external_bearer.rs``
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExternalAuthTokens:
    access_token: str

    @classmethod
    def access_token_only(cls, access_token: str) -> "ExternalAuthTokens":
        return cls(access_token=access_token)


@dataclass(frozen=True)
class ExternalAuthRefreshContext:
    reason: str | None = None


@dataclass(frozen=True)
class CachedExternalBearerToken:
    access_token: str
    fetched_at: float


class BearerTokenRefresher:
    def __init__(self, config: Any) -> None:
        self.config = config
        self._cached_token: CachedExternalBearerToken | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def new(cls, config: Any) -> "BearerTokenRefresher":
        return cls(config)

    def auth_mode(self) -> str:
        return "api_key"

    async def resolve(self) -> ExternalAuthTokens | None:
        async with self._lock:
            cached = self._cached_token
            if cached is not None:
                refresh_interval = _refresh_interval_seconds(self.config)
                if refresh_interval is None or time.monotonic() - cached.fetched_at < refresh_interval:
                    return ExternalAuthTokens.access_token_only(cached.access_token)

            access_token = await run_provider_auth_command(self.config)
            self._cached_token = CachedExternalBearerToken(
                access_token=access_token,
                fetched_at=time.monotonic(),
            )
            return ExternalAuthTokens.access_token_only(access_token)

    async def refresh(self, context: ExternalAuthRefreshContext | None = None) -> ExternalAuthTokens:
        del context
        access_token = await run_provider_auth_command(self.config)
        async with self._lock:
            self._cached_token = CachedExternalBearerToken(
                access_token=access_token,
                fetched_at=time.monotonic(),
            )
        return ExternalAuthTokens.access_token_only(access_token)


async def run_provider_auth_command(config: Any) -> str:
    command = str(_get(config, "command"))
    cwd = Path(_get(config, "cwd", os.getcwd()))
    program = resolve_provider_auth_program(command, cwd)
    args = [str(arg) for arg in (_get(config, "args", []) or [])]
    timeout_seconds = _timeout_seconds(config)

    try:
        proc = await asyncio.create_subprocess_exec(
            str(program),
            *args,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise OSError(f"provider auth command `{command}` failed to start: {exc}") from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout_seconds)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        timeout_ms = int(timeout_seconds * 1000)
        raise OSError(f"provider auth command `{command}` timed out after {timeout_ms} ms") from exc

    if proc.returncode != 0:
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        stderr_suffix = f": {stderr_text}" if stderr_text else ""
        raise OSError(
            f"provider auth command `{command}` exited with status {proc.returncode}{stderr_suffix}"
        )

    try:
        stdout_text = stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OSError(f"provider auth command `{command}` wrote non-UTF-8 data to stdout") from exc

    access_token = stdout_text.strip()
    if not access_token:
        raise OSError(f"provider auth command `{command}` produced an empty token")
    return access_token


def resolve_provider_auth_program(command: str, cwd: str | os.PathLike[str]) -> Path:
    path = Path(command)
    if path.is_absolute():
        return path
    if len(path.parts) > 1:
        return Path(cwd) / path
    return path


def _timeout_seconds(config: Any) -> float:
    timeout_ms = _get(config, "timeout_ms", 5000)
    raw = getattr(timeout_ms, "value", timeout_ms)
    return float(raw) / 1000.0


def _refresh_interval_seconds(config: Any) -> float | None:
    refresh_interval_ms = _get(config, "refresh_interval_ms", 300000)
    raw = getattr(refresh_interval_ms, "value", refresh_interval_ms)
    if int(raw) == 0:
        return None
    return float(raw) / 1000.0


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "BearerTokenRefresher",
    "CachedExternalBearerToken",
    "ExternalAuthRefreshContext",
    "ExternalAuthTokens",
    "resolve_provider_auth_program",
    "run_provider_auth_command",
]
