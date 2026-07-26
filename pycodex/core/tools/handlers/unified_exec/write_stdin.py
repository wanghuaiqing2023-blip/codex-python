"""Unified exec tool handler facades ported from Codex core.

This module mirrors the argument, command-resolution, spec, hook payload, and
lightweight local execution behavior from
``core/src/tools/handlers/unified_exec``. Full PTY/session process management
is still delegated to a unified exec manager when available.
"""

from __future__ import annotations

import json
import inspect
import shlex
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pycodex.core.exec import DEFAULT_EXEC_COMMAND_TIMEOUT_MS
from pycodex.core.exec_env import create_env
from pycodex.core.unified_exec import (
    DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS,
    MAX_YIELD_TIME_MS,
    MIN_EMPTY_YIELD_TIME_MS,
    MIN_YIELD_TIME_MS,
    UnifiedExecError,
    apply_unified_exec_env,
    clamp_yield_time,
    generate_chunk_id,
    resolve_write_stdin_yield_time,
    should_emit_terminal_interaction,
    terminal_interaction_process_id,
)
from pycodex.features import Feature
from pycodex.core.tools.handlers import (
    apply_granted_turn_permissions,
    implicit_granted_permissions,
    normalize_and_validate_additional_permissions,
    resolve_tool_environment,
)
from pycodex.core.tools.hook_names import HookToolName
from pycodex.core.shell import Shell, ShellType, default_user_shell, get_shell_by_model_provided_path
from pycodex.protocol.exec_output import bytes_to_string_smart
from pycodex.shell_command.powershell import prefix_powershell_script_with_utf8
from pycodex.utils.string import approx_token_count
from pycodex.core.tools.context import ExecCommandToolOutput
from pycodex.core.tools.handlers.shell_spec import (
    CommandToolOptions,
    create_exec_command_tool_with_environment_id,
    create_write_stdin_tool,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.core.tools.registry import PostToolUsePayload, PreToolUsePayload, ToolInvocation
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    EventMsg,
    GranularApprovalConfig,
    SandboxPermissions,
    ShellEnvironmentPolicy,
    TerminalInteractionEvent,
    ThreadId,
    ToolName,
    TruncationPolicyConfig,
)

JsonValue = Any

DEFAULT_EXEC_YIELD_TIME_MS = 10_000
DEFAULT_WRITE_STDIN_YIELD_TIME_MS = 250
I32_MIN = -(2**31)
I32_MAX = 2**31 - 1
U64_MAX = 2**64 - 1
USIZE_MAX = 2**64 - 1



from . import (
    _ensure_i32,
    _ensure_u64,
    _ensure_usize,
    _json_mapping,
    _optional_int,
)

@dataclass(frozen=True)
class WriteStdinArgs:
    session_id: int
    chars: str = ""
    yield_time_ms: int = DEFAULT_WRITE_STDIN_YIELD_TIME_MS
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.session_id, bool) or not isinstance(self.session_id, int):
            raise TypeError("session_id must be an integer")
        _ensure_i32(self.session_id, "session_id")
        if not isinstance(self.chars, str):
            raise TypeError("chars must be a string")
        if isinstance(self.yield_time_ms, bool) or not isinstance(self.yield_time_ms, int):
            raise TypeError("yield_time_ms must be an integer")
        _ensure_u64(self.yield_time_ms, "yield_time_ms")
        if self.max_output_tokens is not None and (
            isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int)
        ):
            raise TypeError("max_output_tokens must be an integer")
        if self.max_output_tokens is not None:
            _ensure_usize(self.max_output_tokens, "max_output_tokens")

    @classmethod
    def from_json(cls, arguments: str) -> "WriteStdinArgs":
        data = _json_mapping(arguments, "write_stdin arguments")
        session_id = data.get("session_id")
        if isinstance(session_id, bool) or not isinstance(session_id, int):
            raise TypeError("session_id must be an integer")
        return cls(
            session_id=session_id,
            chars=data.get("chars", ""),
            yield_time_ms=data.get("yield_time_ms", DEFAULT_WRITE_STDIN_YIELD_TIME_MS),
            max_output_tokens=_optional_int(data, "max_output_tokens"),
        )

