"""Small unified-exec helpers ported from ``core/src/unified_exec``."""

from __future__ import annotations

import inspect
import os
import queue
import random
import subprocess
import threading
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any, TypeVar

from pycodex.protocol import ExecToolCallOutput


MIN_YIELD_TIME_MS = 250
MIN_EMPTY_YIELD_TIME_MS = 5_000
MAX_YIELD_TIME_MS = 30_000
DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS = 300_000
DEFAULT_MAX_OUTPUT_TOKENS = 10_000
EARLY_EXIT_GRACE_PERIOD_MS = 150
TRAILING_OUTPUT_GRACE_MS = 100
UNIFIED_EXEC_OUTPUT_MAX_BYTES = 1024 * 1024
UNIFIED_EXEC_OUTPUT_MAX_TOKENS = UNIFIED_EXEC_OUTPUT_MAX_BYTES // 4
UNIFIED_EXEC_OUTPUT_DELTA_MAX_BYTES = 8192
MAX_EXEC_OUTPUT_DELTAS_PER_CALL = 10_000
MAX_UNIFIED_EXEC_PROCESSES = 64
NETWORK_ACCESS_DENIED_MESSAGE = "Network access was denied by the Codex sandbox network proxy."
LATE_NETWORK_DENIAL_GRACE_PERIOD_MS = 100
UNIFIED_EXEC_ENV = (
    ("NO_COLOR", "1"),
    ("TERM", "dumb"),
    ("LANG", "C.UTF-8"),
    ("LC_CTYPE", "C.UTF-8"),
    ("LC_ALL", "C.UTF-8"),
    ("COLORTERM", ""),
    ("PAGER", "cat"),
    ("GIT_PAGER", "cat"),
    ("GH_PAGER", "cat"),
    ("CODEX_CI", "1"),
)
_T = TypeVar("_T")
from . import (
    LATE_NETWORK_DENIAL_GRACE_PERIOD_MS,
    MAX_UNIFIED_EXEC_PROCESSES,
    MIN_YIELD_TIME_MS,
    TRAILING_OUTPUT_GRACE_MS,
    UnifiedExecError,
    _T,
    clamp_yield_time,
    generate_chunk_id,
    resolve_write_stdin_yield_time,
)

from .head_tail_buffer import (
    HeadTailBuffer,
)
from .process import UnifiedExecProcess

NETWORK_ACCESS_DENIED_MESSAGE = "Network access was denied by the Codex sandbox network proxy."
_DETERMINISTIC_PROCESS_IDS_FOR_TESTS = True


def set_deterministic_process_ids_for_tests(enabled: bool) -> None:
    """Set the process-manager-local test override, matching the Rust owner."""

    global _DETERMINISTIC_PROCESS_IDS_FOR_TESTS
    _DETERMINISTIC_PROCESS_IDS_FOR_TESTS = bool(enabled)

UNIFIED_EXEC_ENV = (
    ("NO_COLOR", "1"),
    ("TERM", "dumb"),
    ("LANG", "C.UTF-8"),
    ("LC_CTYPE", "C.UTF-8"),
    ("LC_ALL", "C.UTF-8"),
    ("COLORTERM", ""),
    ("PAGER", "cat"),
    ("GIT_PAGER", "cat"),
    ("GH_PAGER", "cat"),
    ("CODEX_CI", "1"),
)

def apply_unified_exec_env(env: dict[str, str]) -> dict[str, str]:
    merged = dict(env)
    merged.update(UNIFIED_EXEC_ENV)
    return merged

@dataclass(frozen=True)
class ExecServerEnvConfig:
    policy: Any | None
    local_policy_env: dict[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.local_policy_env, dict):
            raise TypeError("local_policy_env must be a dict")

@dataclass(frozen=True)
class ExecServerParams:
    process_id: str
    argv: tuple[str, ...]
    cwd: Any
    env_policy: Any | None
    env: dict[str, str]
    tty: bool
    pipe_stdin: bool = False
    arg0: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.process_id, str):
            raise TypeError("process_id must be a string")
        if not isinstance(self.argv, tuple):
            raise TypeError("argv must be a tuple")
        if not isinstance(self.env, dict):
            raise TypeError("env must be a dict")
        if not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool")
        if not isinstance(self.pipe_stdin, bool):
            raise TypeError("pipe_stdin must be a bool")

def env_overlay_for_exec_server(
    request_env: dict[str, str],
    local_policy_env: dict[str, str],
) -> dict[str, str]:
    return {
        key: value
        for key, value in request_env.items()
        if local_policy_env.get(key) != value
    }

def _request_env_mapping(request: Any) -> dict[str, str]:
    env = getattr(request, "env", None)
    if env is None:
        env = getattr(request, "environment", None)
    if env is None:
        return {}
    if not isinstance(env, dict):
        raise TypeError("request env must be a dict")
    return {str(key): str(value) for key, value in env.items()}

def _exec_server_env_config_fields(config: Any) -> tuple[Any | None, dict[str, str]]:
    if isinstance(config, dict):
        policy = config.get("policy")
        local_policy_env = config.get("local_policy_env", {})
    else:
        policy = getattr(config, "policy", None)
        local_policy_env = getattr(config, "local_policy_env", {})
    if not isinstance(local_policy_env, dict):
        raise TypeError("exec_server_env_config.local_policy_env must be a dict")
    return policy, {str(key): str(value) for key, value in local_policy_env.items()}

def exec_server_env_for_request(request: Any) -> tuple[Any | None, dict[str, str]]:
    request_env = _request_env_mapping(request)
    config = getattr(request, "exec_server_env_config", None)
    if config is None:
        return None, request_env
    policy, local_policy_env = _exec_server_env_config_fields(config)
    return policy, env_overlay_for_exec_server(request_env, local_policy_env)

def exec_server_process_id(process_id: int) -> str:
    return str(process_id)

def exec_server_params_for_request(
    process_id: int,
    request: Any,
    tty: bool,
) -> ExecServerParams:
    if isinstance(process_id, bool) or not isinstance(process_id, int):
        raise TypeError("process_id must be an integer")
    command = tuple(str(part) for part in (getattr(request, "command", ()) or ()))
    env_policy, env = exec_server_env_for_request(request)
    return ExecServerParams(
        process_id=exec_server_process_id(process_id),
        argv=command,
        cwd=getattr(request, "cwd", None),
        env_policy=env_policy,
        env=env,
        tty=bool(tty),
        pipe_stdin=False,
        arg0=getattr(request, "arg0", None),
    )

def _cancellation_token_is_cancelled(token: Any) -> bool:
    if token is None:
        return False
    saw_cancellation_attr = False
    for name in ("is_cancelled", "is_set"):
        value = getattr(token, name, None)
        if callable(value):
            saw_cancellation_attr = True
            result = _sync_callable_bool(value)
            if result is not None:
                return result
    value = getattr(token, "cancelled", None)
    if callable(value):
        saw_cancellation_attr = True
        result = _sync_callable_bool(value)
        if result is not None:
            return result
    if value is not None and not callable(value):
        saw_cancellation_attr = True
        return bool(value)
    if saw_cancellation_attr:
        return False
    return bool(token)

def _sync_callable_bool(value: Any) -> bool | None:
    if inspect.iscoroutinefunction(value):
        return None
    result = value()
    if inspect.isawaitable(result):
        close = getattr(result, "close", None)
        if callable(close):
            close()
        return None
    return bool(result)

def wait_for_late_network_denial(
    network_cancelled: Any,
    *,
    grace_period_ms: int = LATE_NETWORK_DENIAL_GRACE_PERIOD_MS,
) -> bool:
    if network_cancelled is None:
        return False
    if _cancellation_token_is_cancelled(network_cancelled):
        return True
    if isinstance(grace_period_ms, bool) or not isinstance(grace_period_ms, int):
        raise TypeError("grace_period_ms must be an integer")
    if grace_period_ms <= 0:
        return _cancellation_token_is_cancelled(network_cancelled)

    deadline = time.monotonic() + (grace_period_ms / 1000.0)
    while time.monotonic() < deadline:
        if _cancellation_token_is_cancelled(network_cancelled):
            return True
        remaining = deadline - time.monotonic()
        time.sleep(min(0.01, max(remaining, 0.0)))
    return _cancellation_token_is_cancelled(network_cancelled)

def network_denial_message_for_session(
    session: Any | None = None,
    deferred: Any | None = None,
) -> str:
    if session is None:
        return NETWORK_ACCESS_DENIED_MESSAGE
    finish = getattr(session, "finish_deferred_network_approval", None)
    if not callable(finish):
        return NETWORK_ACCESS_DENIED_MESSAGE
    try:
        result = finish(deferred)
    except Exception as err:
        return str(err)
    if isinstance(result, str) and result:
        return result
    return NETWORK_ACCESS_DENIED_MESSAGE

def process_id_to_prune_from_meta(meta: Iterable[tuple[int, _T, bool]]) -> int | None:
    entries = list(meta)
    if not entries:
        return None

    protected = {
        process_id
        for process_id, _, _ in sorted(entries, key=lambda entry: entry[1], reverse=True)[:8]
    }
    least_recent = sorted(entries, key=lambda entry: entry[1])
    for process_id, _, has_exited in least_recent:
        if process_id not in protected and has_exited:
            return process_id
    for process_id, _, _ in least_recent:
        if process_id not in protected:
            return process_id
    return None

@dataclass(frozen=True)
class ProcessEntry:
    process_id: int
    process: Any
    call_id: str = ""
    hook_command: str = ""
    tty: bool = False
    last_used: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int):
            raise TypeError("process_id must be an integer")
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.hook_command, str):
            raise TypeError("hook_command must be a string")
        if not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool")
        if isinstance(self.last_used, bool) or not isinstance(self.last_used, (int, float)):
            raise TypeError("last_used must be a number")

    def has_exited(self) -> bool:
        value = getattr(self.process, "has_exited", None)
        if callable(value):
            value = value()
        if value is not None:
            return bool(value)
        poll = getattr(self.process, "poll", None)
        if callable(poll):
            return poll() is not None
        return bool(getattr(self.process, "exited", False))

def _command_for_spawn(command: tuple[str, ...], shell_type: Any) -> tuple[str, ...]:
    """Apply the same last-mile PowerShell UTF-8 wrapper as Rust unified exec."""

    from pycodex.core.shell import ShellType
    from pycodex.shell_command.powershell import prefix_powershell_script_with_utf8

    if shell_type == ShellType.POWERSHELL:
        return tuple(prefix_powershell_script_with_utf8(command))
    return command

def _spawn_unified_exec_process(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str],
    tty: bool,
    attempt: Any,
) -> Any:
    """Spawn through the selected product sandbox, never by display label."""

    if os.name == "nt" and attempt is not None:
        from pycodex.core.exec import windows_sandbox_uses_elevated_backend
        from pycodex.core.sandbox_tags import SandboxType
        from pycodex.protocol import WindowsSandboxLevel

        sandbox = getattr(attempt, "sandbox", SandboxType.NONE)
        if not isinstance(sandbox, SandboxType):
            sandbox = SandboxType(str(sandbox))
        if sandbox is SandboxType.WINDOWS_RESTRICTED_TOKEN:
            level = getattr(attempt, "windows_sandbox_level", WindowsSandboxLevel.DISABLED)
            if not isinstance(level, WindowsSandboxLevel):
                level = WindowsSandboxLevel.parse(str(level))
            if level is WindowsSandboxLevel.DISABLED:
                raise OSError("Windows sandbox selected with disabled WindowsSandboxLevel; refusing unrestricted fallback")
            profile = getattr(attempt, "permissions", None)
            sandbox_cwd = Path(getattr(attempt, "sandbox_cwd", cwd))
            deny_read, deny_write = _windows_profile_deny_overrides(profile, sandbox_cwd)
            private_desktop = bool(getattr(attempt, "windows_sandbox_private_desktop", False))
            managed_network = bool(getattr(attempt, "enforce_managed_network", False))
            from pycodex.utils.home_dir import find_codex_home

            if windows_sandbox_uses_elevated_backend(level, managed_network):
                from pycodex.windows_sandbox.unified_exec import (
                    spawn_windows_sandbox_session_elevated_for_permission_profile,
                )

                return spawn_windows_sandbox_session_elevated_for_permission_profile(
                    profile,
                    sandbox_cwd,
                    find_codex_home(),
                    command,
                    cwd,
                    env,
                    None,
                    None,
                    False,
                    None,
                    deny_read,
                    deny_write,
                    tty,
                    tty,
                    private_desktop,
                )
            from pycodex.windows_sandbox.unified_exec import (
                spawn_windows_sandbox_session_legacy,
            )

            return spawn_windows_sandbox_session_legacy(
                profile,
                sandbox_cwd,
                find_codex_home(),
                command,
                cwd,
                env,
                None,
                deny_read,
                deny_write,
                tty,
                tty,
                private_desktop,
            )

    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.PIPE if tty else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
    )

def _windows_profile_deny_overrides(profile: Any, cwd: Path) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Project split filesystem restrictions into native Windows ACL inputs."""

    policy_factory = getattr(profile, "file_system_sandbox_policy", None)
    if not callable(policy_factory):
        return (), ()
    policy = policy_factory()
    unreadable = getattr(policy, "get_unreadable_roots_with_cwd", None)
    deny_read = tuple(Path(path) for path in unreadable(cwd)) if callable(unreadable) else ()
    writable = getattr(policy, "get_writable_roots_with_cwd", None)
    deny_write: list[Path] = []
    if callable(writable):
        for root in writable(cwd):
            deny_write.extend(Path(path) for path in getattr(root, "read_only_subpaths", ()) or ())
    return tuple(dict.fromkeys(deny_read)), tuple(dict.fromkeys(deny_write))

class UnifiedExecProcessManager:
    """Small stdlib manager for unified exec process ids, sessions, and pruning."""

    def __init__(
        self,
        *,
        max_processes: int = MAX_UNIFIED_EXEC_PROCESSES,
        deterministic_process_ids: bool | None = None,
    ) -> None:
        if isinstance(max_processes, bool) or not isinstance(max_processes, int):
            raise TypeError("max_processes must be an integer")
        if max_processes <= 0:
            raise ValueError("max_processes must be positive")
        if deterministic_process_ids is None:
            deterministic_process_ids = _DETERMINISTIC_PROCESS_IDS_FOR_TESTS
        if not isinstance(deterministic_process_ids, bool):
            raise TypeError("deterministic_process_ids must be a bool")
        self.max_processes = max_processes
        self.deterministic_process_ids = deterministic_process_ids
        self._processes: dict[int, ProcessEntry] = {}
        self._reserved_process_ids: set[int] = set()

    def exec_command(self, request: Any) -> Any:
        command = tuple(getattr(request, "command", ()) or ())
        process_id = getattr(request, "process_id", None)
        if not command:
            if process_id is not None:
                self.release_process_id(process_id)
            raise UnifiedExecError.missing_command_line()
        if isinstance(process_id, bool) or not isinstance(process_id, int):
            raise TypeError("request.process_id must be an integer")

        request_env = getattr(request, "environment", None)
        if bool(getattr(request, "environment_is_complete", False)):
            env = apply_unified_exec_env({})
        else:
            env = apply_unified_exec_env(os.environ)
        if isinstance(request_env, dict):
            env.update({str(key): str(value) for key, value in request_env.items()})

        cwd = getattr(request, "cwd", None) or None
        call_id = str(getattr(request, "call_id", ""))
        tty = bool(getattr(request, "tty", False))
        hook_command = str(getattr(request, "hook_command", ""))
        truncation_policy = getattr(request, "truncation_policy", None)
        max_output_tokens = getattr(request, "max_output_tokens", None)
        yield_time_ms = clamp_yield_time(int(getattr(request, "yield_time_ms", MIN_YIELD_TIME_MS)))

        # Rust core::tools::runtimes::unified_exec forces PowerShell console
        # output to UTF-8 immediately before spawning the process. Keep the
        # original request command unchanged for command lifecycle display.
        shell_type = getattr(request, "shell_type", None)
        spawn_command = _command_for_spawn(command, shell_type)

        try:
            attempt = getattr(request, "_sandbox_attempt", None)
            process = _spawn_unified_exec_process(
                spawn_command,
                cwd=Path(cwd) if cwd is not None else Path.cwd(),
                env=env,
                tty=tty,
                attempt=attempt,
            )
        except OSError as err:
            self.release_process_id(process_id)
            raise UnifiedExecError.create_process(str(err)) from err

        session = UnifiedExecProcess(
            process,
            process_id=process_id,
            hook_command=hook_command,
            tty=tty,
            truncation_policy=truncation_policy,
        )
        self.store_process(
            process_id,
            session,
            call_id=call_id,
            hook_command=hook_command,
            tty=tty,
        )
        output = session.snapshot(
            yield_time_ms=yield_time_ms,
            max_output_tokens=max_output_tokens,
            event_call_id=call_id,
        )
        if output.process_id is None and tty:
            from pycodex.core.tools.context import ExecCommandToolOutput

            output = ExecCommandToolOutput(
                event_call_id=output.event_call_id,
                chunk_id=output.chunk_id,
                wall_time_seconds=output.wall_time_seconds,
                raw_output=output.raw_output,
                truncation_policy=output.truncation_policy,
                max_output_tokens=output.max_output_tokens,
                process_id=process_id,
                exit_code=output.exit_code,
                original_token_count=output.original_token_count,
                hook_command=output.hook_command,
            )
            return output
        if output.process_id is None:
            self.release_process_id(process_id)
        return output

    def write_stdin(self, request: Any) -> Any:
        process_id = getattr(request, "process_id", None)
        if isinstance(process_id, bool) or not isinstance(process_id, int):
            raise TypeError("request.process_id must be an integer")
        entry = self.touch_process(process_id)
        if entry is None:
            raise UnifiedExecError.unknown_process_id(process_id)

        session = entry.process
        chars = str(getattr(request, "input", ""))
        if chars:
            try:
                session.write(chars)
            except UnifiedExecError:
                if not session.has_exited():
                    raise
            else:
                time.sleep(0.1)
        yield_time_ms = resolve_write_stdin_yield_time(
            chars,
            int(getattr(request, "yield_time_ms", MIN_YIELD_TIME_MS)),
        )
        output = session.snapshot(
            yield_time_ms=yield_time_ms,
            max_output_tokens=getattr(request, "max_output_tokens", None),
            event_call_id=entry.call_id,
        )
        if output.process_id is None:
            self.release_process_id(process_id)
        return output

    def allocate_process_id(self) -> int:
        while True:
            if self.deterministic_process_ids:
                process_id = max(self._reserved_process_ids, default=999) + 1
                process_id = max(process_id, 1000)
            else:
                process_id = random.randrange(1_000, 100_000)
            if process_id in self._reserved_process_ids:
                continue
            self._reserved_process_ids.add(process_id)
            return process_id

    def release_process_id(self, process_id: int) -> ProcessEntry | None:
        self._reserved_process_ids.discard(process_id)
        entry = self._processes.pop(process_id, None)
        if entry is not None:
            close = getattr(entry.process, "close", None)
            if callable(close):
                close()
        return entry

    def store_process(
        self,
        process_id: int,
        process: Any,
        *,
        call_id: str = "",
        hook_command: str = "",
        tty: bool = False,
        last_used: float | None = None,
    ) -> ProcessEntry | None:
        if last_used is None:
            last_used = time.monotonic()
        entry = ProcessEntry(
            process_id=process_id,
            process=process,
            call_id=call_id,
            hook_command=hook_command,
            tty=tty,
            last_used=last_used,
        )
        self._reserved_process_ids.add(process_id)
        self._processes[process_id] = entry
        return self.prune_processes_if_needed()

    def get_process(self, process_id: int) -> ProcessEntry | None:
        return self._processes.get(process_id)

    def touch_process(self, process_id: int, *, last_used: float | None = None) -> ProcessEntry | None:
        entry = self._processes.get(process_id)
        if entry is None:
            return None
        if last_used is None:
            last_used = time.monotonic()
        updated = ProcessEntry(
            process_id=entry.process_id,
            process=entry.process,
            call_id=entry.call_id,
            hook_command=entry.hook_command,
            tty=entry.tty,
            last_used=last_used,
        )
        self._processes[process_id] = updated
        return updated

    def prune_processes_if_needed(self) -> ProcessEntry | None:
        if len(self._processes) < self.max_processes:
            return None
        meta = [
            (process_id, entry.last_used, entry.has_exited())
            for process_id, entry in self._processes.items()
        ]
        process_id = process_id_to_prune_from_meta(meta)
        if process_id is None:
            return None
        return self.release_process_id(process_id)

    def terminate_all_processes(self) -> tuple[ProcessEntry, ...]:
        entries = tuple(self._processes.values())
        self._processes.clear()
        self._reserved_process_ids.clear()
        for entry in entries:
            terminate = getattr(entry.process, "terminate", None)
            if callable(terminate):
                terminate()
        return entries

    def process_count(self) -> int:
        return len(self._processes)

    def reserved_process_ids(self) -> frozenset[int]:
        return frozenset(self._reserved_process_ids)

