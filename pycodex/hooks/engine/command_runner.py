"""Python port of ``codex-hooks::engine.command_runner``."""


from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import replace
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import (
    HookCompletedEvent,
    HookEventName,
    HookExecutionMode,
    HookHandlerType,
    HookOutputEntry,
    HookOutputEntryKind,
    HookPromptFragment,
    HookRunStatus,
    HookRunSummary,
    HookScope,
    HookSource,
    HookTrustStatus,
    ThreadId,
    TruncationPolicyConfig,
)
from pycodex.config.hook_config import HookStateToml
from pycodex.config.hook_config import HookEventsToml
from pycodex.config.hook_config import HookHandlerConfig
from pycodex.config.hook_config import HooksFile
from pycodex.config.hook_config import MatcherGroup
from pycodex.config.fingerprint import version_for_toml
from pycodex.config.state import ConfigLayerStackOrdering
from pycodex.utils.output_truncation import approx_token_count
from pycodex.utils.output_truncation import formatted_truncate_text

from . import CommandShell, ConfiguredHandler

@dataclass(frozen=True)
class CommandRunResult:
    started_at: int
    completed_at: int
    duration_ms: int
    exit_code: int | None
    stdout: str
    stderr: str
    error: str | None = None


def default_shell_command_argv() -> list[str]:
    if os.name == "nt":
        return [os.environ.get("COMSPEC") or "cmd.exe", "/C"]
    return [os.environ.get("SHELL") or "/bin/sh", "-lc"]


def build_command_argv(shell: CommandShell, handler: ConfiguredHandler) -> list[str]:
    if not shell.program:
        return [*default_shell_command_argv(), handler.command]
    return [shell.program, *shell.args, handler.command]


async def run_command(
    shell: CommandShell,
    handler: ConfiguredHandler,
    input_json: str,
    cwd: Path,
) -> CommandRunResult:
    started_at = int(datetime.now(timezone.utc).timestamp())
    started = time.monotonic()

    argv = build_command_argv(shell, handler)
    env = os.environ.copy()
    env.update(dict(handler.env))
    try:
        child = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return CommandRunResult(
            started_at=started_at,
            completed_at=int(datetime.now(timezone.utc).timestamp()),
            duration_ms=int((time.monotonic() - started) * 1000),
            exit_code=None,
            stdout="",
            stderr="",
            error=str(exc),
        )

    try:
        stdout, stderr = await asyncio.wait_for(
            child.communicate(input_json.encode()),
            timeout=handler.timeout_sec,
        )
    except BrokenPipeError as exc:
        with contextlib.suppress(ProcessLookupError):
            child.kill()
        await child.wait()
        return CommandRunResult(
            started_at=started_at,
            completed_at=int(datetime.now(timezone.utc).timestamp()),
            duration_ms=int((time.monotonic() - started) * 1000),
            exit_code=None,
            stdout="",
            stderr="",
            error=f"failed to write hook stdin: {exc}",
        )
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            child.kill()
        await child.wait()
        return CommandRunResult(
            started_at=started_at,
            completed_at=int(datetime.now(timezone.utc).timestamp()),
            duration_ms=int((time.monotonic() - started) * 1000),
            exit_code=None,
            stdout="",
            stderr="",
            error=f"hook timed out after {handler.timeout_sec}s",
        )
    except OSError as exc:
        return CommandRunResult(
            started_at=started_at,
            completed_at=int(datetime.now(timezone.utc).timestamp()),
            duration_ms=int((time.monotonic() - started) * 1000),
            exit_code=None,
            stdout="",
            stderr="",
            error=str(exc),
        )

    return CommandRunResult(
        started_at=started_at,
        completed_at=int(datetime.now(timezone.utc).timestamp()),
        duration_ms=int((time.monotonic() - started) * 1000),
        exit_code=child.returncode,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
        error=None,
    )
