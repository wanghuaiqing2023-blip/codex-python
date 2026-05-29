"""Local in-process runtime bridge for ``codex exec`` user turns."""

from __future__ import annotations

import os
import json
import queue
import subprocess
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

from pycodex.core.apply_patch import create_apply_patch_freeform_tool, parse_patch, verify_apply_patch_args
from pycodex.core.client import ModelClient
from pycodex.core.http_transport import run_user_turn_http_sampling_from_session
from pycodex.core.session_runtime import InMemoryCodexSession
from pycodex.core.turn_runtime import UserTurnSamplingResult
from pycodex.protocol import AskForApproval, BaseInstructions, ResponseInputItem, ResponseItem
from pycodex.protocol.models import FunctionCallOutputPayload

from .event_processor import HumanEventProcessor, JsonEventProcessor
from .events import ExecThreadItem, ThreadErrorEvent, ThreadEvent, Usage, agent_message_item, reasoning_item
from .run import ExecRunPlan
from .session import ExecSessionConfig


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5"
LOCAL_HTTP_EXEC_ENV = "PYCODEX_EXEC_LOCAL_HTTP"
LOCAL_HTTP_EXEC_SHELL_TOOLS_ENV = "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"
LOCAL_HTTP_EXEC_MAX_TOOL_ROUNDS_ENV = "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS"
LOCAL_HTTP_EXEC_TOOL_OUTPUT_MAX_CHARS_ENV = "PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS"


_SESSION_COUNTER = count(1)


@dataclass(frozen=True)
class LocalHttpModelInfo:
    """Minimal model metadata needed by the local exec HTTP path."""

    slug: str
    base_instructions: str = "You are Codex, a coding agent."
    supports_reasoning_summaries: bool = False
    support_verbosity: bool = False

    def service_tier_for_request(self, service_tier: str | None) -> str | None:
        return service_tier


@dataclass(frozen=True)
class LocalHttpProvider:
    """Small provider value compatible with the stdlib HTTP transport."""

    base_url: str = DEFAULT_OPENAI_BASE_URL
    auth: Any = None

    def is_azure_responses_endpoint(self) -> bool:
        return False


@dataclass(frozen=True)
class LocalHttpShellInvocation:
    """Shell tool invocation parsed from Responses function-call arguments."""

    command: str
    workdir: Path | None = None
    timeout: float | None = None
    login: bool | None = None
    shell: str | None = None
    tty: bool | None = None
    yield_time_ms: float | None = None
    max_output_tokens: int | None = None
    sandbox_permissions: str | None = None
    justification: str | None = None
    prefix_rule: tuple[str, ...] | None = None


@dataclass(frozen=True)
class LocalHttpWriteStdinInvocation:
    """write_stdin invocation parsed from Responses function-call arguments."""

    session_id: int
    chars: str = ""
    yield_time: float | None = None
    max_output_tokens: int | None = None


class LocalHttpExecSession:
    """Small stdlib process session used by local HTTP ``exec_command``."""

    def __init__(self, session_id: int, process: subprocess.Popen[str]) -> None:
        self.session_id = session_id
        self.process = process
        self._output: queue.Queue[str] = queue.Queue()
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        stream = self.process.stdout
        if stream is None:
            return
        try:
            for chunk in iter(stream.readline, ""):
                if chunk == "":
                    break
                self._output.put(chunk)
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def write(self, chars: str) -> None:
        if self.process.stdin is None or self.process.poll() is not None:
            return
        self.process.stdin.write(chars)
        self.process.stdin.flush()

    def snapshot(self, *, yield_time: float | None = None, output_max_chars: int | None = None) -> tuple[str, bool]:
        started = time.monotonic()
        if yield_time:
            time.sleep(yield_time)
        output = self._drain_output()
        elapsed = time.monotonic() - started
        exit_code = self.process.poll()
        running = exit_code is None
        body = _format_exec_session_output(
            output,
            wall_time_seconds=elapsed,
            session_id=self.session_id if running else None,
            exit_code=exit_code,
            output_max_chars=output_max_chars,
        )
        return body, not running and exit_code == 0

    def close(self) -> None:
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
        except OSError:
            pass
        try:
            if self.process.stdout is not None:
                self.process.stdout.close()
        except OSError:
            pass

    def _drain_output(self) -> str:
        parts: list[str] = []
        while True:
            try:
                parts.append(self._output.get_nowait())
            except queue.Empty:
                break
        return "".join(parts)


class LocalHttpExecSessionManager:
    """Manage local stdlib exec sessions for explicit local HTTP tool calls."""

    def __init__(self) -> None:
        self._sessions: dict[int, LocalHttpExecSession] = {}

    def start(
        self,
        command: str,
        *,
        cwd: Path,
        yield_time: float | None = None,
        output_max_chars: int | None = None,
    ) -> tuple[str, bool]:
        session_id = next(_SESSION_COUNTER)
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        session = LocalHttpExecSession(session_id, process)
        self._sessions[session_id] = session
        output, success = session.snapshot(yield_time=yield_time, output_max_chars=output_max_chars)
        if process.poll() is not None:
            self._sessions.pop(session_id, None)
            session.close()
        return output, success

    def write(
        self,
        session_id: int,
        chars: str,
        *,
        yield_time: float | None = None,
        output_max_chars: int | None = None,
    ) -> tuple[str, bool]:
        session = self._sessions.get(session_id)
        if session is None:
            return local_http_write_stdin_unknown_session_output(session_id), False
        session.write(chars)
        output, success = session.snapshot(yield_time=yield_time, output_max_chars=output_max_chars)
        if session.process.poll() is not None:
            self._sessions.pop(session_id, None)
            session.close()
        return output, success


_DEFAULT_EXEC_SESSION_MANAGER = LocalHttpExecSessionManager()


class LocalHttpShellToolRouter:
    """Minimal model-visible shell tool router for the local HTTP exec path."""

    def __init__(self, base_router: Any = None) -> None:
        self._base_router = base_router

    def model_visible_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        if self._base_router is not None:
            base_specs = getattr(self._base_router, "model_visible_specs", None)
            if callable(base_specs):
                for spec in base_specs():
                    if isinstance(spec, Mapping):
                        specs.append(dict(spec))
        if not any(_local_http_shell_tool_spec_matches(spec) for spec in specs):
            specs.append(local_http_shell_tool_spec())
        if not any(_local_http_write_stdin_tool_spec_matches(spec) for spec in specs):
            specs.append(local_http_write_stdin_tool_spec())
        if not any(_local_http_apply_patch_tool_spec_matches(spec) for spec in specs):
            specs.append(local_http_apply_patch_tool_spec())
        return specs


def local_http_shell_tool_spec() -> dict[str, Any]:
    """Return the Responses function tool spec used by local HTTP exec loop."""

    return {
        "type": "function",
        "name": "exec_command",
        "description": (
            "Runs a command in a PTY, returning output or a session ID for ongoing interaction."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "Shell command to execute."},
                "workdir": {
                    "type": "string",
                    "description": "Optional working directory to run the command in; defaults to the turn cwd.",
                },
                "shell": {
                    "type": "string",
                    "description": "Shell binary to launch. Defaults to the user's default shell.",
                },
                "tty": {
                    "type": "boolean",
                    "description": (
                        "Whether to allocate a TTY for the command. Defaults to false (plain pipes); "
                        "set to true to open a PTY and access TTY process."
                    ),
                },
                "yield_time_ms": {
                    "type": "number",
                    "description": "How long to wait (in milliseconds) for output before yielding.",
                },
                "max_output_tokens": {
                    "type": "number",
                    "description": "Maximum number of tokens to return. Excess output will be truncated.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Compatibility alias for command timeout in milliseconds.",
                },
                "login": {"type": "boolean", "description": "Whether a login shell should be requested."},
                "sandbox_permissions": {
                    "type": "string",
                    "description": "Optional sandbox permission request metadata.",
                },
                "justification": {
                    "type": "string",
                    "description": "Optional reason for elevated or sandbox-changing execution.",
                },
                "prefix_rule": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional approved command prefix metadata.",
                },
            },
            "required": ["cmd"],
            "additionalProperties": False,
        },
        "output_schema": local_http_exec_command_output_schema(),
    }


def local_http_exec_command_output_schema() -> dict[str, Any]:
    """Return the Rust Codex ``exec_command`` output schema."""

    return {
        "type": "object",
        "properties": {
            "chunk_id": {
                "type": "string",
                "description": "Chunk identifier included when the response reports one.",
            },
            "wall_time_seconds": {
                "type": "number",
                "description": "Elapsed wall time spent waiting for output in seconds.",
            },
            "exit_code": {
                "type": "number",
                "description": "Process exit code when the command finished during this call.",
            },
            "session_id": {
                "type": "number",
                "description": "Session identifier to pass to write_stdin when the process is still running.",
            },
            "original_token_count": {
                "type": "number",
                "description": "Approximate token count before output truncation.",
            },
            "output": {
                "type": "string",
                "description": "Command output text, possibly truncated.",
            },
        },
        "required": ["wall_time_seconds", "output"],
        "additionalProperties": False,
    }


def local_http_write_stdin_tool_spec() -> dict[str, Any]:
    """Return the Rust Codex ``write_stdin`` companion tool spec."""

    return {
        "type": "function",
        "name": "write_stdin",
        "description": "Writes characters to an existing unified exec session and returns recent output.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "number",
                    "description": "Identifier of the running unified exec session.",
                },
                "chars": {
                    "type": "string",
                    "description": "Bytes to write to stdin (may be empty to poll).",
                },
                "yield_time_ms": {
                    "type": "number",
                    "description": "How long to wait (in milliseconds) for output before yielding.",
                },
                "max_output_tokens": {
                    "type": "number",
                    "description": "Maximum number of tokens to return. Excess output will be truncated.",
                },
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
        "output_schema": local_http_exec_command_output_schema(),
    }


def local_http_apply_patch_tool_spec() -> dict[str, Any]:
    """Return the Responses custom tool spec for apply_patch."""

    return dict(create_apply_patch_freeform_tool(False).to_mapping())


def local_http_shell_tools_built_tools(base_built_tools: Any = None) -> Any:
    """Wrap an optional built-tools callback with the local shell tool spec."""

    def build(session: Any, turn_context: Any) -> LocalHttpShellToolRouter:
        base_router = base_built_tools(session, turn_context) if callable(base_built_tools) else base_built_tools
        return LocalHttpShellToolRouter(base_router)

    return build


def _local_http_shell_tool_spec_matches(spec: Mapping[str, Any]) -> bool:
    return spec.get("type") == "function" and spec.get("name") in {
        "exec_command",
        "shell_command",
        "shell",
        "local_shell",
        "exec",
    }


def _local_http_write_stdin_tool_spec_matches(spec: Mapping[str, Any]) -> bool:
    return spec.get("type") == "function" and spec.get("name") == "write_stdin"


def _local_http_apply_patch_tool_spec_matches(spec: Mapping[str, Any]) -> bool:
    return spec.get("name") == "apply_patch" and spec.get("type") in {"custom", "function"}


def local_http_exec_enabled(env: Any = None) -> bool:
    """Return true when the experimental local HTTP exec path is enabled."""

    source = os.environ if env is None else env
    return str(source.get(LOCAL_HTTP_EXEC_ENV, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "enable",
        "enabled",
    }


def local_http_exec_shell_tools_enabled(env: Any = None) -> bool:
    """Return true when local HTTP exec should run the shell tool loop."""

    source = os.environ if env is None else env
    return str(source.get(LOCAL_HTTP_EXEC_SHELL_TOOLS_ENV, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "enable",
        "enabled",
    }


def local_http_exec_max_tool_rounds(env: Any = None, default: int = 1) -> int:
    """Resolve the local HTTP exec shell tool loop round limit."""

    if isinstance(default, bool) or not isinstance(default, int):
        raise TypeError("default must be an integer")
    if default < 0:
        raise ValueError("default must be non-negative")
    source = os.environ if env is None else env
    raw = source.get(LOCAL_HTTP_EXEC_MAX_TOOL_ROUNDS_ENV)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw).strip(), 10)
    except ValueError as exc:
        raise ValueError(f"{LOCAL_HTTP_EXEC_MAX_TOOL_ROUNDS_ENV} must be a non-negative integer") from exc
    if value < 0:
        raise ValueError(f"{LOCAL_HTTP_EXEC_MAX_TOOL_ROUNDS_ENV} must be a non-negative integer")
    return value


def local_http_exec_tool_output_max_chars(env: Any = None) -> int | None:
    """Resolve the local HTTP exec shell tool output truncation limit."""

    source = os.environ if env is None else env
    raw = source.get(LOCAL_HTTP_EXEC_TOOL_OUTPUT_MAX_CHARS_ENV)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(str(raw).strip(), 10)
    except ValueError as exc:
        raise ValueError(f"{LOCAL_HTTP_EXEC_TOOL_OUTPUT_MAX_CHARS_ENV} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{LOCAL_HTTP_EXEC_TOOL_OUTPUT_MAX_CHARS_ENV} must be a positive integer")
    return value


def default_local_http_exec_auth(
    *,
    auth: Any = None,
    env: Any = None,
    config_toml: Mapping[str, Any] | None = None,
    provider_id: str | None = None,
) -> Any:
    """Resolve auth for the default local HTTP exec runtime."""

    source = os.environ if env is None else env
    api_key = source.get("OPENAI_API_KEY")
    if isinstance(api_key, str) and api_key:
        return api_key
    provider_env_key = _config_provider_env_key(config_toml, provider_id)
    if provider_env_key is not None:
        provider_api_key = source.get(provider_env_key)
        if isinstance(provider_api_key, str) and provider_api_key:
            return provider_api_key
    auth_api_key = getattr(auth, "openai_api_key", None) or getattr(auth, "api_key", None)
    if isinstance(auth_api_key, str) and auth_api_key:
        return auth
    if isinstance(auth, str) and auth:
        return auth
    return None


def build_default_local_http_exec_runtime(
    config: ExecSessionConfig,
    *,
    auth: Any = None,
    env: Any = None,
    config_toml: Mapping[str, Any] | None = None,
) -> tuple[ModelClient, LocalHttpProvider, LocalHttpModelInfo, Any]:
    """Build the default OpenAI Responses runtime for local ``codex exec``."""

    source = os.environ if env is None else env
    provider_id = config.model_provider_id or _config_model_provider(config_toml) or "openai"
    resolved_auth = default_local_http_exec_auth(
        auth=auth,
        env=source,
        config_toml=config_toml,
        provider_id=provider_id,
    )
    if resolved_auth is None or resolved_auth == "":
        raise ValueError("OPENAI_API_KEY is required for PYCODEX_EXEC_LOCAL_HTTP=1")

    model = default_local_http_exec_model(config, env=source, config_toml=config_toml)
    base_url = default_local_http_exec_base_url(env=source, config_toml=config_toml, provider_id=provider_id)
    provider = LocalHttpProvider(base_url=base_url, auth=resolved_auth)
    model_info = LocalHttpModelInfo(slug=model)
    client = ModelClient(
        session_id=str(uuid4()),
        thread_id=str(uuid4()),
        installation_id=source.get("CODEX_INSTALLATION_ID") or "pycodex-local-exec",
        provider=provider,
    )
    return client, provider, model_info, resolved_auth


def default_local_http_exec_model(
    config: ExecSessionConfig,
    *,
    env: Any = None,
    config_toml: Mapping[str, Any] | None = None,
) -> str:
    """Resolve the default local HTTP exec model using CLI/config/env precedence."""

    source = os.environ if env is None else env
    return (
        config.model
        or source.get("PYCODEX_EXEC_MODEL")
        or source.get("OPENAI_MODEL")
        or _config_model(config_toml)
        or DEFAULT_OPENAI_MODEL
    )


def default_local_http_exec_base_url(
    *,
    env: Any = None,
    config_toml: Mapping[str, Any] | None = None,
    provider_id: str | None = None,
) -> str:
    """Resolve the default local HTTP exec provider base URL."""

    source = os.environ if env is None else env
    return source.get("OPENAI_BASE_URL") or _config_provider_base_url(config_toml, provider_id) or DEFAULT_OPENAI_BASE_URL


def _config_model(config_toml: Mapping[str, Any] | None) -> str | None:
    if config_toml is None:
        return None
    model = config_toml.get("model")
    return model if isinstance(model, str) and model else None


def _config_model_provider(config_toml: Mapping[str, Any] | None) -> str | None:
    if config_toml is None:
        return None
    provider = config_toml.get("model_provider")
    return provider if isinstance(provider, str) and provider else None


def _config_provider_base_url(config_toml: Mapping[str, Any] | None, provider_id: str | None) -> str | None:
    if config_toml is None or provider_id is None:
        return None
    providers = config_toml.get("model_providers")
    if not isinstance(providers, Mapping):
        return None
    provider = providers.get(provider_id)
    if not isinstance(provider, Mapping):
        return None
    base_url = provider.get("base_url")
    return base_url if isinstance(base_url, str) and base_url else None


def _config_provider_env_key(config_toml: Mapping[str, Any] | None, provider_id: str | None) -> str | None:
    if config_toml is None or provider_id is None:
        return None
    providers = config_toml.get("model_providers")
    if not isinstance(providers, Mapping):
        return None
    provider = providers.get(provider_id)
    if not isinstance(provider, Mapping):
        return None
    env_key = provider.get("env_key")
    return env_key if isinstance(env_key, str) and env_key else None


def local_http_exec_config_summary(
    config: ExecSessionConfig,
    *,
    model: str | None = None,
    provider_id: str | None = None,
    session_id: str = "local-http",
    thread_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build config/session-configured mappings for exec config summaries."""

    resolved_model = model or default_local_http_exec_model(config)
    resolved_provider = provider_id or config.model_provider_id or "openai"
    resolved_thread_id = thread_id or session_id
    approval = getattr(config.approval_policy, "value", str(config.approval_policy))
    permission_profile = config.permission_profile.to_mapping()
    config_mapping = {
        "cwd": str(config.cwd),
        "workspace_roots": [str(root) for root in config.workspace_roots],
        "model": resolved_model,
        "model_provider_id": resolved_provider,
        "approval_policy": approval,
        "permission_profile": permission_profile,
    }
    session_configured = {
        "session_id": session_id,
        "thread_id": resolved_thread_id,
        "model": resolved_model,
        "model_provider_id": resolved_provider,
        "cwd": str(config.cwd),
        "approval_policy": approval,
        "permission_profile": permission_profile,
    }
    return config_mapping, session_configured


async def run_exec_user_turn_default_local_http_sampling(
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    *,
    auth: Any = None,
    env: Any = None,
    config_toml: Mapping[str, Any] | None = None,
    opener: Any = None,
    built_tools: Any = None,
) -> UserTurnSamplingResult:
    """Run a prepared exec user turn through the default local HTTP runtime."""

    client, provider, model_info, resolved_auth = build_default_local_http_exec_runtime(
        config,
        auth=auth,
        env=env,
        config_toml=config_toml,
    )
    return await run_exec_user_turn_http_sampling(
        config,
        plan,
        client,
        provider,
        model_info,
        auth=resolved_auth,
        opener=opener,
        built_tools=built_tools,
    )


async def run_exec_user_turn_http_sampling(
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    opener: Any = None,
    built_tools: Any = None,
) -> Any:
    """Run a prepared ``codex exec`` user turn through the HTTP core path."""

    operation = plan.initial_operation
    if operation.kind != "user_turn":
        raise ValueError("local exec HTTP runtime currently supports only user_turn operations")
    session = InMemoryCodexSession(
        cwd=config.cwd,
        model_info=model_info,
        user_instructions=config.user_instructions,
        base_instructions=_base_instructions_from_model_info(model_info),
    )
    return await run_user_turn_http_sampling_from_session(
        session,
        operation.items,
        model_client,
        provider,
        model_info,
        auth=auth,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        built_tools=built_tools,
        effort=config.reasoning_effort,
        output_schema=operation.output_schema,
    )


async def run_exec_tool_output_http_sampling(
    config: ExecSessionConfig,
    previous_result: UserTurnSamplingResult,
    tool_outputs: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    opener: Any = None,
    built_tools: Any = None,
) -> Any:
    """Run a follow-up model turn with tool output items in history."""

    session = InMemoryCodexSession(
        cwd=config.cwd,
        model_info=model_info,
        user_instructions=config.user_instructions,
        base_instructions=_base_instructions_from_model_info(model_info),
    )
    turn_context = await session.new_default_turn()
    if previous_result.response_items:
        await session.record_conversation_items(turn_context, previous_result.response_items)
    tool_response_items = response_items_from_local_http_tool_outputs(tool_outputs)
    if tool_response_items:
        await session.record_conversation_items(turn_context, tool_response_items)
    return await run_user_turn_http_sampling_from_session(
        session,
        (),
        model_client,
        provider,
        model_info,
        auth=auth,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        built_tools=built_tools,
        effort=config.reasoning_effort,
    )


async def run_exec_user_turn_with_shell_tools_http_sampling(
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    opener: Any = None,
    built_tools: Any = None,
    runner: Any = None,
    tool_timeout: float | None = 30.0,
    tool_output_max_chars: int | None = None,
    max_tool_rounds: int = 1,
) -> Any:
    """Run a user turn and feed shell tool outputs back to the model."""

    if isinstance(max_tool_rounds, bool) or not isinstance(max_tool_rounds, int):
        raise TypeError("max_tool_rounds must be an integer")
    if max_tool_rounds < 0:
        raise ValueError("max_tool_rounds must be non-negative")
    shell_built_tools = local_http_shell_tools_built_tools(built_tools)
    result = await run_exec_user_turn_http_sampling(
        config,
        plan,
        model_client,
        provider,
        model_info,
        auth=auth,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        built_tools=shell_built_tools,
    )
    for _round in range(max_tool_rounds):
        tool_outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            runner=runner,
            timeout=tool_timeout,
            output_max_chars=tool_output_max_chars,
        )
        if not tool_outputs:
            return result
        result = await run_exec_tool_output_http_sampling(
            config,
            result,
            tool_outputs,
            model_client,
            provider,
            model_info,
            auth=auth,
            endpoint=endpoint,
            timeout=timeout,
            opener=opener,
            built_tools=shell_built_tools,
        )
    return result


def response_items_from_local_http_tool_outputs(
    tool_outputs: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> tuple[ResponseItem, ...]:
    """Convert Responses tool output mappings into prompt-visible items."""

    if isinstance(tool_outputs, (str, bytes)) or not isinstance(tool_outputs, (list, tuple)):
        raise TypeError("tool_outputs must be a list or tuple of mappings")
    items: list[ResponseItem] = []
    for output in tool_outputs:
        if not isinstance(output, Mapping):
            raise TypeError("tool output entries must be mappings")
        item_type = output.get("type")
        call_id = output.get("call_id")
        if not isinstance(item_type, str):
            raise TypeError("tool output type must be a string")
        if not isinstance(call_id, str):
            raise TypeError("tool output call_id must be a string")
        response_output = output.get("output")
        success = output.get("success")
        tool_name = output.get("name")
        if success is not None and not isinstance(success, bool):
            raise TypeError("tool output success must be a bool or None")
        if tool_name is not None and not isinstance(tool_name, str):
            raise TypeError("tool output name must be a string or None")
        if item_type in {"function_call_output", "custom_tool_call_output"} and success is not None:
            payload = FunctionCallOutputPayload.from_value(response_output)
            response_output = FunctionCallOutputPayload(payload.body, success=success)
        input_item = ResponseInputItem(
            type=item_type,
            call_id=call_id,
            name=tool_name if item_type == "custom_tool_call_output" else None,
            output=response_output,
        )
        items.append(ResponseItem.from_response_input_item(input_item))
    return tuple(items)


def _base_instructions_from_model_info(model_info: Any) -> BaseInstructions:
    value = getattr(model_info, "base_instructions", None)
    if value is None:
        get_model_instructions = getattr(model_info, "get_model_instructions", None)
        if callable(get_model_instructions):
            value = get_model_instructions(None)
    if value is None:
        return BaseInstructions.default()
    if isinstance(value, BaseInstructions):
        return value
    return BaseInstructions(str(value))


def final_text_from_response_items(items: tuple[ResponseItem, ...] | list[ResponseItem]) -> str:
    """Collect assistant-visible text from Responses output items."""

    parts: list[str] = []
    for item in items:
        content = getattr(item, "content", None)
        if not isinstance(content, (list, tuple)):
            continue
        for part in content:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text:
                parts.append(text)
    return "".join(parts)


def emit_local_http_exec_result(
    processor: HumanEventProcessor | JsonEventProcessor,
    result: UserTurnSamplingResult,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdout_is_terminal: bool | None = None,
    stderr_is_terminal: bool | None = None,
) -> str:
    """Render a local HTTP exec result through the normal exec processors."""

    final_text = final_text_from_response_items(result.response_items)
    usage = usage_from_local_http_exec_result(result)
    if isinstance(processor, JsonEventProcessor):
        events = [ThreadEvent.turn_started()]
        for reasoning_text in reasoning_texts_from_local_http_exec_result(result):
            events.append(ThreadEvent.item_completed(reasoning_item(processor.next_item_id(), reasoning_text)))
        for tool_item in tool_call_items_from_local_http_exec_result(result, processor):
            events.append(ThreadEvent.item_completed(tool_item))
        for tool_output_item in tool_output_items_from_local_http_exec_result(result, processor):
            events.append(ThreadEvent.item_completed(tool_output_item))
        if final_text:
            processor.final_message = final_text
            events.append(ThreadEvent.item_completed(agent_message_item(processor.next_item_id(), final_text)))
        processor.emit_final_message_on_shutdown = True
        events.append(ThreadEvent.turn_completed(usage))
        processor.emit_json_lines(events, stdout)
        processor.print_final_output(stderr=stderr)
        return final_text

    if final_text:
        processor.final_message = final_text
    processor.final_message_rendered = False
    processor.emit_final_message_on_shutdown = True
    processor.last_usage = usage
    processor.print_final_output(
        stdout=stdout,
        stderr=stderr,
        stdout_is_terminal=stdout_is_terminal,
        stderr_is_terminal=stderr_is_terminal,
    )
    return final_text


def tool_call_items_from_local_http_exec_result(
    result: UserTurnSamplingResult,
    processor: JsonEventProcessor,
) -> tuple[ExecThreadItem, ...]:
    """Extract read-only tool/function call items from a local HTTP Responses payload."""

    payload = _raw_responses_payload(result)
    if not isinstance(payload, Mapping):
        return ()
    output = payload.get("output")
    if isinstance(output, Mapping):
        output_items = (output,)
    elif isinstance(output, (list, tuple)):
        output_items = tuple(item for item in output if isinstance(item, Mapping))
    else:
        return ()

    items: list[ExecThreadItem] = []
    for item in output_items:
        item_type = str(item.get("type") or "")
        if item_type not in {"function_call", "custom_tool_call", "mcp_tool_call"}:
            continue
        tool = _tool_name_from_item(item)
        arguments = _tool_arguments_from_item(item)
        items.append(
            ExecThreadItem(
                processor.next_item_id(),
                "mcp_tool_call",
                {
                    "server": "responses",
                    "tool": tool,
                    "arguments": arguments,
                    "result": None,
                    "error": None,
                    "status": "in_progress",
                },
            )
        )
    return tuple(items)


def tool_output_items_from_local_http_exec_result(
    result: UserTurnSamplingResult,
    processor: JsonEventProcessor,
) -> tuple[ExecThreadItem, ...]:
    """Extract read-only tool/function output items from a local HTTP Responses payload."""

    payload = _raw_responses_payload(result)
    if not isinstance(payload, Mapping):
        return ()
    output = payload.get("output")
    if isinstance(output, Mapping):
        output_items = (output,)
    elif isinstance(output, (list, tuple)):
        output_items = tuple(item for item in output if isinstance(item, Mapping))
    else:
        return ()

    items: list[ExecThreadItem] = []
    for item in output_items:
        item_type = str(item.get("type") or "")
        if item_type not in {"function_call_output", "custom_tool_call_output", "mcp_tool_call_output"}:
            continue
        items.append(
            ExecThreadItem(
                processor.next_item_id(),
                "mcp_tool_call",
                {
                    "server": "responses",
                    "tool": _tool_name_from_item(item),
                    "arguments": {},
                    "result": _tool_output_from_item(item),
                    "error": None,
                    "status": "completed",
                },
            )
        )
    return tuple(items)


def shell_tool_outputs_from_local_http_exec_result(
    result: UserTurnSamplingResult,
    config: ExecSessionConfig,
    *,
    runner: Any = None,
    session_manager: LocalHttpExecSessionManager | None = None,
    timeout: float | None = 30.0,
    output_max_chars: int | None = None,
) -> tuple[dict[str, Any], ...]:
    """Execute shell function calls from a local HTTP Responses payload.

    This helper intentionally only returns Responses ``function_call_output``
    mappings. The caller decides whether and when to feed them into another
    model request so approval/sandbox policy can be inserted before automatic
    execution in the CLI path.
    """

    payload = _raw_responses_payload(result)
    if not isinstance(payload, Mapping):
        return ()
    output = payload.get("output")
    if isinstance(output, Mapping):
        output_items = (output,)
    elif isinstance(output, (list, tuple)):
        output_items = tuple(item for item in output if isinstance(item, Mapping))
    else:
        return ()

    run = subprocess.run if runner is None else runner
    sessions = _DEFAULT_EXEC_SESSION_MANAGER if session_manager is None else session_manager
    outputs: list[dict[str, Any]] = []
    for item in output_items:
        item_type = str(item.get("type") or "")
        if item_type not in {"function_call", "custom_tool_call"}:
            continue
        tool = _tool_name_from_item(item)
        call_id = item.get("call_id") or item.get("id") or ""
        if tool == "apply_patch":
            patch_text = _apply_patch_text_from_arguments(_tool_arguments_from_item(item))
            if patch_text is None:
                continue
            if not local_http_shell_tool_auto_execute_allowed(config):
                outputs.append(
                    {
                        "type": "custom_tool_call_output" if item_type == "custom_tool_call" else "function_call_output",
                        "call_id": str(call_id),
                        "name": "apply_patch",
                        "output": local_http_apply_patch_approval_required_output(config),
                        "success": False,
                    }
                )
                continue
            output_text, success = _apply_local_http_apply_patch(patch_text, config.cwd)
            outputs.append(
                {
                    "type": "custom_tool_call_output" if item_type == "custom_tool_call" else "function_call_output",
                    "call_id": str(call_id),
                    "name": "apply_patch",
                    "output": output_text,
                    "success": success,
                }
            )
            continue
        if tool == "write_stdin":
            stdin_invocation = _write_stdin_invocation_from_arguments(_tool_arguments_from_item(item))
            if not local_http_shell_tool_auto_execute_allowed(config):
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call_id),
                        "output": local_http_write_stdin_approval_required_output(config),
                        "success": False,
                    }
                )
                continue
            if stdin_invocation is not None:
                output_text, success = sessions.write(
                    stdin_invocation.session_id,
                    stdin_invocation.chars,
                    yield_time=stdin_invocation.yield_time,
                    output_max_chars=_effective_shell_output_max_chars(
                        output_max_chars,
                        stdin_invocation.max_output_tokens,
                    ),
                )
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call_id),
                        "output": output_text,
                        "success": success,
                    }
                )
                continue
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "output": local_http_write_stdin_unavailable_output(_tool_arguments_from_item(item)),
                    "success": False,
                }
            )
            continue
        if tool not in {"exec_command", "shell_command", "shell", "local_shell", "exec"}:
            continue
        invocation = _shell_invocation_from_arguments(
            _tool_arguments_from_item(item),
            default_cwd=config.cwd,
            default_timeout=timeout,
        )
        if invocation is None:
            continue
        if not local_http_shell_tool_auto_execute_allowed(config):
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "output": local_http_shell_tool_approval_required_output(invocation, config),
                    "success": False,
                }
            )
            continue
        effective_output_max_chars = _effective_shell_output_max_chars(output_max_chars, invocation.max_output_tokens)
        if runner is None and _should_start_local_http_exec_session(invocation):
            output_text, success = sessions.start(
                invocation.command,
                cwd=invocation.workdir or config.cwd,
                yield_time=invocation.yield_time_ms,
                output_max_chars=effective_output_max_chars,
            )
        else:
            output_text, success = _run_shell_tool_command_result(
                invocation.command,
                cwd=invocation.workdir or config.cwd,
                runner=run,
                timeout=invocation.timeout,
                login=invocation.login,
                output_max_chars=effective_output_max_chars,
            )
        outputs.append(
            {
                "type": "function_call_output",
                "call_id": str(call_id),
                "output": output_text,
                "success": success,
            }
        )
    return tuple(outputs)


def local_http_apply_patch_approval_required_output(config: ExecSessionConfig) -> str:
    approval = getattr(config.approval_policy, "value", str(config.approval_policy))
    return (
        "apply_patch: approval_required\n"
        f"approval_policy: {approval}\n"
        "stderr:\nPatch application requires approval and was not run by the local HTTP helper."
    )


def local_http_write_stdin_approval_required_output(config: ExecSessionConfig) -> str:
    approval = getattr(config.approval_policy, "value", str(config.approval_policy))
    return (
        "exit_code: approval_required\n"
        f"approval_policy: {approval}\n"
        "output:\nwrite_stdin requires approval and was not run by the local HTTP helper."
    )


def local_http_write_stdin_unavailable_output(arguments: Any) -> str:
    session_id = _write_stdin_session_id_from_arguments(arguments)
    session_text = "unknown" if session_id is None else str(session_id)
    return (
        "exit_code: unavailable\n"
        "wall_time_seconds: 0\n"
        f"session_id: {session_text}\n"
        "output:\nwrite_stdin is declared for protocol parity, but no local exec session runtime is active yet."
    )


def local_http_write_stdin_unknown_session_output(session_id: int) -> str:
    return (
        "exit_code: unknown_session\n"
        "wall_time_seconds: 0\n"
        f"session_id: {session_id}\n"
        "output:\nNo active local exec session exists for this session_id."
    )


def _write_stdin_invocation_from_arguments(arguments: Any) -> LocalHttpWriteStdinInvocation | None:
    session_id = _write_stdin_session_id_from_arguments(arguments)
    if session_id is None or not isinstance(arguments, Mapping):
        return None
    chars = arguments.get("chars")
    return LocalHttpWriteStdinInvocation(
        session_id=session_id,
        chars=chars if isinstance(chars, str) else "",
        yield_time=_shell_yield_time_from_arguments(arguments),
        max_output_tokens=_shell_max_output_tokens_from_arguments(arguments),
    )


def _write_stdin_session_id_from_arguments(arguments: Any) -> int | None:
    if not isinstance(arguments, Mapping):
        return None
    value = arguments.get("session_id")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _should_start_local_http_exec_session(invocation: LocalHttpShellInvocation) -> bool:
    return bool(invocation.tty) or invocation.yield_time_ms is not None


def _format_exec_session_output(
    output: str,
    *,
    wall_time_seconds: float,
    session_id: int | None,
    exit_code: int | None,
    output_max_chars: int | None,
) -> str:
    rendered_output = _truncate_shell_tool_output(output.rstrip(), output_max_chars)
    lines = [
        f"wall_time_seconds: {wall_time_seconds:.3f}",
    ]
    if exit_code is not None:
        lines.append(f"exit_code: {exit_code}")
    if session_id is not None:
        lines.append(f"session_id: {session_id}")
    lines.append("output:")
    lines.append(rendered_output)
    return "\n".join(lines).rstrip()


def _apply_patch_text_from_arguments(arguments: Any) -> str | None:
    if isinstance(arguments, str):
        return arguments if arguments.strip() else None
    if not isinstance(arguments, Mapping):
        return None
    for key in ("patch", "input", "content"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _apply_local_http_apply_patch(patch_text: str, cwd: Path) -> tuple[str, bool]:
    try:
        verified = verify_apply_patch_args(parse_patch(patch_text), cwd)
    except Exception as exc:
        return f"apply_patch failed: {exc}", False
    if verified.type != "body" or verified.body is None:
        return f"apply_patch failed: {verified.error}", False
    try:
        changed_paths = _write_apply_patch_action(verified.body.changes)
    except OSError as exc:
        return f"apply_patch failed: {exc}", False
    changed = "\n".join(str(path) for path in changed_paths)
    return ("apply_patch succeeded" if not changed else f"apply_patch succeeded\nchanged files:\n{changed}"), True


def _write_apply_patch_action(changes: Mapping[Path, Any]) -> tuple[Path, ...]:
    changed: list[Path] = []
    for path, change in changes.items():
        target = Path(path)
        if change.type == "add":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content or change.new_content or "", encoding="utf-8")
            changed.append(target)
        elif change.type == "delete":
            target.unlink()
            changed.append(target)
        elif change.type == "update":
            new_content = change.new_content if change.new_content is not None else change.content
            if new_content is None:
                raise OSError(f"missing new content for {target}")
            if change.move_path is not None:
                move_target = Path(change.move_path)
                move_target.parent.mkdir(parents=True, exist_ok=True)
                move_target.write_text(new_content, encoding="utf-8")
                target.unlink()
                changed.append(move_target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(new_content, encoding="utf-8")
                changed.append(target)
    return tuple(changed)


def local_http_shell_tool_auto_execute_allowed(config: ExecSessionConfig) -> bool:
    """Return true when the local helper may auto-run shell commands."""

    return config.approval_policy is AskForApproval.NEVER or config.approval_policy == AskForApproval.NEVER


def local_http_shell_tool_approval_required_output(
    invocation: LocalHttpShellInvocation | str,
    config: ExecSessionConfig,
) -> str:
    """Build a tool output explaining that approval is required."""

    approval = getattr(config.approval_policy, "value", str(config.approval_policy))
    if isinstance(invocation, LocalHttpShellInvocation):
        command = invocation.command
        sandbox_permissions = invocation.sandbox_permissions
        justification = invocation.justification
        prefix_rule = invocation.prefix_rule
    else:
        command = invocation
        sandbox_permissions = None
        justification = None
        prefix_rule = None
    metadata = ""
    if sandbox_permissions:
        metadata += f"sandbox_permissions: {sandbox_permissions}\n"
    if justification:
        metadata += f"justification: {justification}\n"
    if prefix_rule:
        metadata += f"prefix_rule: {json.dumps(list(prefix_rule), ensure_ascii=False, separators=(',', ':'))}\n"
    return (
        "exit_code: approval_required\n"
        f"approval_policy: {approval}\n"
        f"{metadata}"
        f"command:\n{command}\n"
        "stderr:\nCommand execution requires approval and was not run by the local HTTP helper."
    )


def _shell_invocation_from_arguments(
    arguments: Any,
    *,
    default_cwd: Path,
    default_timeout: float | None,
) -> LocalHttpShellInvocation | None:
    command = _shell_command_from_arguments(arguments)
    if not command:
        return None
    if not isinstance(arguments, Mapping):
        return LocalHttpShellInvocation(command, timeout=default_timeout)
    return LocalHttpShellInvocation(
        command,
        workdir=_shell_workdir_from_arguments(arguments, default_cwd=default_cwd),
        timeout=_shell_timeout_from_arguments(arguments, default_timeout=default_timeout),
        login=_shell_login_from_arguments(arguments),
        shell=_optional_str_argument(arguments, "shell"),
        tty=_optional_bool_argument(arguments, "tty"),
        yield_time_ms=_shell_yield_time_from_arguments(arguments),
        max_output_tokens=_shell_max_output_tokens_from_arguments(arguments),
        sandbox_permissions=_optional_str_argument(arguments, "sandbox_permissions"),
        justification=_optional_str_argument(arguments, "justification"),
        prefix_rule=_shell_prefix_rule_from_arguments(arguments),
    )


def _shell_command_from_arguments(arguments: Any) -> str | None:
    if isinstance(arguments, str):
        return arguments if arguments else None
    if not isinstance(arguments, Mapping):
        return None
    for key in ("command", "cmd", "script"):
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return value
    argv = arguments.get("argv")
    if isinstance(argv, (list, tuple)) and all(isinstance(item, str) for item in argv):
        return subprocess.list2cmdline(list(argv))
    return None


def _shell_workdir_from_arguments(arguments: Mapping[str, Any], *, default_cwd: Path) -> Path | None:
    value = arguments.get("workdir")
    if value is None:
        value = arguments.get("cwd")
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else Path(default_cwd) / path


def _shell_timeout_from_arguments(arguments: Mapping[str, Any], *, default_timeout: float | None) -> float | None:
    value = arguments.get("timeout_ms")
    if value is None:
        value = arguments.get("timeout")
    if value is None:
        return default_timeout
    if isinstance(value, bool):
        return default_timeout
    if isinstance(value, int | float):
        if value < 0:
            return default_timeout
        return float(value) / 1000.0
    return default_timeout


def _shell_login_from_arguments(arguments: Mapping[str, Any]) -> bool | None:
    value = arguments.get("login")
    return value if isinstance(value, bool) else None


def _optional_bool_argument(arguments: Mapping[str, Any], key: str) -> bool | None:
    value = arguments.get(key)
    return value if isinstance(value, bool) else None


def _optional_str_argument(arguments: Mapping[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    return value if isinstance(value, str) and value else None


def _shell_yield_time_from_arguments(arguments: Mapping[str, Any]) -> float | None:
    value = arguments.get("yield_time_ms")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float) and value >= 0:
        return float(value) / 1000.0
    return None


def _shell_max_output_tokens_from_arguments(arguments: Mapping[str, Any]) -> int | None:
    value = arguments.get("max_output_tokens")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float) and value > 0:
        return int(value)
    return None


def _effective_shell_output_max_chars(global_max_chars: int | None, max_output_tokens: int | None) -> int | None:
    token_max_chars = None if max_output_tokens is None else max_output_tokens * 4
    if global_max_chars is None:
        return token_max_chars
    if token_max_chars is None:
        return global_max_chars
    return min(global_max_chars, token_max_chars)


def _shell_prefix_rule_from_arguments(arguments: Mapping[str, Any]) -> tuple[str, ...] | None:
    value = arguments.get("prefix_rule")
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _run_shell_tool_command(
    command: str,
    *,
    cwd: Any,
    runner: Any,
    timeout: float | None,
    login: bool | None = None,
    output_max_chars: int | None = None,
) -> str:
    output, _success = _run_shell_tool_command_result(
        command,
        cwd=cwd,
        runner=runner,
        timeout=timeout,
        login=login,
        output_max_chars=output_max_chars,
    )
    return output


def _run_shell_tool_command_result(
    command: str,
    *,
    cwd: Any,
    runner: Any,
    timeout: float | None,
    login: bool | None = None,
    output_max_chars: int | None = None,
) -> tuple[str, bool]:
    try:
        kwargs = {
            "shell": True,
            "cwd": str(cwd),
            "capture_output": True,
            "text": True,
            "timeout": timeout,
        }
        if login is not None and runner is not subprocess.run:
            kwargs["login"] = login
        completed = runner(command, **kwargs)
    except subprocess.TimeoutExpired as exc:
        return (
            _truncate_shell_tool_output(
                f"exit_code: timeout\nstdout:\n{exc.stdout or ''}\nstderr:\n{exc.stderr or ''}".rstrip(),
                output_max_chars,
            ),
            False,
        )
    stdout = getattr(completed, "stdout", "") or ""
    stderr = getattr(completed, "stderr", "") or ""
    returncode = getattr(completed, "returncode", 0)
    return (
        _truncate_shell_tool_output(
            f"exit_code: {returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}".rstrip(),
            output_max_chars,
        ),
        returncode == 0,
    )


def _truncate_shell_tool_output(output: str, max_chars: int | None) -> str:
    if max_chars is None or len(output) <= max_chars:
        return output
    omitted = len(output) - max_chars
    return f"{output[:max_chars]}\n[truncated {omitted} chars]"


def _tool_name_from_item(item: Mapping[str, Any]) -> str:
    value = item.get("name") or item.get("tool") or item.get("server_label")
    return str(value or "")


def _tool_arguments_from_item(item: Mapping[str, Any]) -> Any:
    value = item.get("arguments")
    if value is None:
        value = item.get("input")
    if isinstance(value, str):
        try:
            import json

            return json.loads(value)
        except ValueError:
            return value
    return value if value is not None else {}


def _tool_output_from_item(item: Mapping[str, Any]) -> Any:
    value = item.get("output")
    if value is None:
        value = item.get("result")
    if value is None:
        value = item.get("content")
    return value if value is not None else ""


def reasoning_texts_from_local_http_exec_result(result: UserTurnSamplingResult) -> tuple[str, ...]:
    """Extract reasoning summary text from a local HTTP Responses payload."""

    payload = _raw_responses_payload(result)
    if not isinstance(payload, Mapping):
        return ()
    output = payload.get("output")
    if isinstance(output, Mapping):
        output_items = (output,)
    elif isinstance(output, (list, tuple)):
        output_items = tuple(item for item in output if isinstance(item, Mapping))
    else:
        return ()

    texts: list[str] = []
    for item in output_items:
        item_type = str(item.get("type") or "")
        if item_type not in {"reasoning", "reasoning_summary"}:
            continue
        text = _reasoning_text_from_item(item)
        if text:
            texts.append(text)
    return tuple(texts)


def _reasoning_text_from_item(item: Mapping[str, Any]) -> str:
    direct = _text_from_value(item.get("text") or item.get("content"))
    summary = _text_from_value(item.get("summary"))
    combined = "\n".join(part for part in (direct, summary) if part)
    return combined.strip()


def _text_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for name in ("text", "summary", "content"):
            text = _text_from_value(value.get(name))
            if text:
                return text
        return ""
    if isinstance(value, (list, tuple)):
        parts = tuple(_text_from_value(item) for item in value)
        return "\n".join(part for part in parts if part)
    return ""


def usage_from_local_http_exec_result(result: UserTurnSamplingResult) -> Usage:
    """Extract exec usage from a local HTTP sampling result."""

    payload = _raw_responses_payload(result)
    if not isinstance(payload, Mapping):
        return Usage()
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        usage = payload.get("token_usage")
    if not isinstance(usage, Mapping):
        usage = payload.get("tokenUsage")
    if not isinstance(usage, Mapping):
        return Usage()

    input_details = _mapping_field(usage, "input_tokens_details", "inputTokensDetails")
    output_details = _mapping_field(usage, "output_tokens_details", "outputTokensDetails")
    return Usage(
        input_tokens=_int_field(usage, "input_tokens", "inputTokens"),
        cached_input_tokens=_int_field(input_details, "cached_tokens", "cachedTokens"),
        output_tokens=_int_field(usage, "output_tokens", "outputTokens"),
        reasoning_output_tokens=_int_field(output_details, "reasoning_tokens", "reasoningTokens"),
    )


def _raw_responses_payload(result: UserTurnSamplingResult) -> Any:
    raw = getattr(result, "raw_result", None)
    while raw is not None and not isinstance(raw, Mapping):
        nested = getattr(raw, "raw_result", None)
        if nested is None or nested is raw:
            break
        raw = nested
    return raw


def _mapping_field(value: Any, *names: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    for name in names:
        item = value.get(name)
        if isinstance(item, Mapping):
            return item
    return {}


def _int_field(value: Any, *names: str) -> int:
    if not isinstance(value, Mapping):
        return 0
    for name in names:
        item = value.get(name)
        if isinstance(item, bool):
            return 0
        if isinstance(item, int):
            return item
        if isinstance(item, float):
            return int(item)
    return 0


def emit_local_http_exec_error(
    processor: HumanEventProcessor | JsonEventProcessor,
    message: str,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """Render a local HTTP exec failure through the normal exec processors."""

    if isinstance(processor, JsonEventProcessor):
        processor.emit_json_lines(
            (
                ThreadEvent.turn_started(),
                ThreadEvent.turn_failed(ThreadErrorEvent(message)),
            ),
            stdout,
        )
        return

    processor.process_server_notification(
        {
            "method": "turn/completed",
            "params": {
                "turn": {
                    "status": "failed",
                    "error": {"message": message},
                }
            },
        },
        stderr=stderr,
    )


__all__ = [
    "DEFAULT_OPENAI_BASE_URL",
    "DEFAULT_OPENAI_MODEL",
    "LOCAL_HTTP_EXEC_ENV",
    "LOCAL_HTTP_EXEC_MAX_TOOL_ROUNDS_ENV",
    "LOCAL_HTTP_EXEC_SHELL_TOOLS_ENV",
    "LOCAL_HTTP_EXEC_TOOL_OUTPUT_MAX_CHARS_ENV",
    "LocalHttpShellInvocation",
    "LocalHttpWriteStdinInvocation",
    "LocalHttpExecSessionManager",
    "LocalHttpModelInfo",
    "LocalHttpProvider",
    "local_http_exec_command_output_schema",
    "local_http_write_stdin_tool_spec",
    "local_http_write_stdin_unavailable_output",
    "local_http_shell_tools_built_tools",
    "local_http_shell_tool_spec",
    "local_http_apply_patch_approval_required_output",
    "local_http_apply_patch_tool_spec",
    "LocalHttpShellToolRouter",
    "build_default_local_http_exec_runtime",
    "default_local_http_exec_auth",
    "default_local_http_exec_base_url",
    "default_local_http_exec_model",
    "emit_local_http_exec_error",
    "emit_local_http_exec_result",
    "final_text_from_response_items",
    "local_http_exec_enabled",
    "local_http_exec_max_tool_rounds",
    "local_http_exec_shell_tools_enabled",
    "local_http_exec_tool_output_max_chars",
    "local_http_exec_config_summary",
    "local_http_shell_tool_approval_required_output",
    "local_http_shell_tool_auto_execute_allowed",
    "reasoning_texts_from_local_http_exec_result",
    "response_items_from_local_http_tool_outputs",
    "run_exec_user_turn_default_local_http_sampling",
    "run_exec_tool_output_http_sampling",
    "run_exec_user_turn_http_sampling",
    "run_exec_user_turn_with_shell_tools_http_sampling",
    "shell_tool_outputs_from_local_http_exec_result",
    "tool_call_items_from_local_http_exec_result",
    "tool_output_items_from_local_http_exec_result",
    "usage_from_local_http_exec_result",
]


