"""Python counterpart of the Rust ``core_test_support`` crate."""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

from pycodex.core.shell import default_user_shell

T = TypeVar("T")

CODEX_SANDBOX_ENV_VAR = "CODEX_SANDBOX"
CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR = "CODEX_SANDBOX_NETWORK_DISABLED"
REMOTE_ENV_ENV_VAR = "CODEX_TEST_REMOTE_ENV"


def assert_regex_match(pattern: str, actual: str) -> re.Match[str]:
    match = re.search(pattern, actual)
    if match is None:
        raise AssertionError(f"regex {pattern!r} did not match {actual!r}")
    return match


def test_path_buf_with_windows(unix_path: str, windows_path: str | None = None) -> Path:
    if os.name == "nt":
        if windows_path is not None:
            return Path(windows_path)
        return Path("C:/", *filter(None, unix_path.removeprefix("/").split("/")))
    return Path(unix_path)


def test_path_buf(unix_path: str) -> Path:
    return test_path_buf_with_windows(unix_path)


def test_absolute_path_with_windows(unix_path: str, windows_path: str | None = None) -> Path:
    path = test_path_buf_with_windows(unix_path, windows_path)
    if not path.is_absolute():
        raise ValueError(f"test path should be absolute: {path}")
    return path


def test_absolute_path(unix_path: str) -> Path:
    return test_absolute_path_with_windows(unix_path)


def test_tmp_path() -> Path:
    return test_absolute_path_with_windows(
        "/tmp",
        str(Path(tempfile.gettempdir()).resolve()) if os.name == "nt" else None,
    )


def test_tmp_path_buf() -> Path:
    return test_tmp_path()


def fetch_dotslash_file(dotslash_file: str | Path, dotslash_cache: str | Path | None = None) -> Path:
    command = ["dotslash", "--", "fetch", os.fspath(dotslash_file)]
    env = os.environ.copy()
    if dotslash_cache is not None:
        env["DOTSLASH_CACHE"] = os.fspath(dotslash_cache)
    completed = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"dotslash fetch failed for {dotslash_file}: {completed.stderr.strip()}"
        )
    path = Path(completed.stdout.strip())
    if not path.is_file():
        raise RuntimeError(f"dotslash returned non-file path: {path}")
    return path


async def wait_for_event(
    codex: Any,
    predicate: Callable[[Any], bool],
    *,
    timeout: float = 10.0,
) -> Any:
    while True:
        event = await asyncio.wait_for(codex.next_event(), timeout=timeout)
        payload = getattr(event, "msg", event)
        if predicate(payload):
            return payload


async def wait_for_event_match(
    codex: Any,
    matcher: Callable[[Any], T | None],
    *,
    timeout: float = 10.0,
) -> T:
    event = await wait_for_event(codex, lambda value: matcher(value) is not None, timeout=timeout)
    matched = matcher(event)
    if matched is None:
        raise AssertionError("event matcher changed result")
    return matched


async def wait_for_event_with_timeout(
    codex: Any,
    predicate: Callable[[Any], bool],
    wait_time: float,
) -> Any:
    return await wait_for_event(codex, predicate, timeout=max(wait_time, 10.0))


def sandbox_env_var() -> str:
    return CODEX_SANDBOX_ENV_VAR


def sandbox_network_env_var() -> str:
    return CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR


def remote_env_env_var() -> str:
    return REMOTE_ENV_ENV_VAR


def get_remote_test_env() -> str | None:
    value = os.environ.get(REMOTE_ENV_ENV_VAR)
    if value is None:
        return None
    if not value.strip():
        raise AssertionError(f"{REMOTE_ENV_ENV_VAR} must not be empty")
    return value


def format_with_current_shell(command: str) -> list[str]:
    return default_user_shell().derive_exec_args(command, use_login_shell=True)


def format_with_current_shell_non_login(command: str) -> list[str]:
    return default_user_shell().derive_exec_args(command, use_login_shell=False)


def format_with_current_shell_display(command: str) -> str:
    return shlex.join(format_with_current_shell(command))


def format_with_current_shell_display_non_login(command: str) -> str:
    return shlex.join(format_with_current_shell_non_login(command))


def stdio_server_bin() -> str:
    executable = shutil.which("test_stdio_server")
    if executable is None:
        raise FileNotFoundError("test_stdio_server")
    return executable


for _pytest_helper in (
    test_path_buf_with_windows,
    test_path_buf,
    test_absolute_path_with_windows,
    test_absolute_path,
    test_tmp_path,
    test_tmp_path_buf,
):
    _pytest_helper.__test__ = False


from . import fs_wait as fs_wait

__all__ = [
    "assert_regex_match",
    "fetch_dotslash_file",
    "format_with_current_shell",
    "format_with_current_shell_display",
    "format_with_current_shell_display_non_login",
    "format_with_current_shell_non_login",
    "fs_wait",
    "get_remote_test_env",
    "remote_env_env_var",
    "sandbox_env_var",
    "sandbox_network_env_var",
    "stdio_server_bin",
    "test_absolute_path",
    "test_absolute_path_with_windows",
    "test_path_buf",
    "test_path_buf_with_windows",
    "test_tmp_path",
    "test_tmp_path_buf",
    "wait_for_event",
    "wait_for_event_match",
    "wait_for_event_with_timeout",
]
