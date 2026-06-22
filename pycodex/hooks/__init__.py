"""Python port of source-verified ``codex-hooks`` public interfaces.

Rust reference:
- ``codex/codex-rs/hooks/src/lib.rs``
- ``codex/codex-rs/hooks/src/types.rs``
- ``codex/codex-rs/hooks/src/registry.rs``
- ``codex/codex-rs/hooks/src/events/*.rs``
"""

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

HOOK_EVENT_NAMES = (
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SessionStart",
    "UserPromptSubmit",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)

HOOK_EVENT_NAMES_WITH_MATCHERS = (
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SessionStart",
    "SubagentStart",
    "SubagentStop",
)

HOOK_OUTPUTS_DIR = "hook_outputs"
HOOK_OUTPUT_TOKEN_LIMIT = 2_500


def hook_event_key_label(event_name: HookEventName | str) -> str:
    return HookEventName(event_name).value


def hook_key(key_source: str, event_name: HookEventName | str, group_index: int, handler_index: int) -> str:
    return f"{key_source}:{hook_event_key_label(event_name)}:{group_index}:{handler_index}"


@dataclass(frozen=True)
class PluginHookDeclaration:
    key: str
    event_name: HookEventName


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _plugin_key(plugin_id: Any) -> str:
    if hasattr(plugin_id, "as_key"):
        return str(plugin_id.as_key())
    return str(plugin_id)


def plugin_hook_declarations(hook_sources: Sequence[Any]) -> list[PluginHookDeclaration]:
    declarations: list[PluginHookDeclaration] = []
    for source in hook_sources:
        key_source = f"{_plugin_key(_field(source, 'plugin_id'))}:{_field(source, 'source_relative_path', '')}"
        hooks = _field(source, "hooks", {})
        if hasattr(hooks, "into_matcher_groups"):
            groups_by_event = hooks.into_matcher_groups()
        elif isinstance(hooks, Mapping):
            groups_by_event = hooks.items()
        else:
            groups_by_event = ()
        for event_name, groups in groups_by_event:
            event = HookEventName(event_name)
            for group_index, group in enumerate(groups):
                handlers = _field(group, "hooks", ())
                for handler_index, _handler in enumerate(handlers):
                    declarations.append(
                        PluginHookDeclaration(
                            hook_key(key_source, event, group_index, handler_index),
                            event,
                        )
                    )
    return declarations


@dataclass
class SubagentHookContext:
    agent_id: str
    agent_type: str


def join_text_chunks(chunks: Sequence[str]) -> str | None:
    if not chunks:
        return None
    return "\n\n".join(chunks)


def trimmed_non_empty(text: str) -> str | None:
    trimmed = text.strip()
    if not trimmed:
        return None
    return trimmed


def append_additional_context(
    entries: list[HookOutputEntry],
    additional_contexts_for_model: list[str],
    additional_context: str,
) -> None:
    entries.append(
        HookOutputEntry(
            HookOutputEntryKind.CONTEXT,
            additional_context,
        )
    )
    additional_contexts_for_model.append(additional_context)


def flatten_additional_contexts(
    additional_contexts: Sequence[Sequence[str]],
) -> list[str]:
    return [
        additional_context
        for chunk in additional_contexts
        for additional_context in chunk
    ]


def _handler_event_name_label(event_name: HookEventName | str) -> str:
    return HookEventName(event_name).value.replace("_", "-")


@dataclass(frozen=True)
class CommandShell:
    program: str
    args: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConfiguredHandler:
    event_name: HookEventName
    matcher: str | None
    command: str
    timeout_sec: int
    status_message: str | None
    source_path: Path
    source: HookSource
    display_order: int
    env: Mapping[str, str] = field(default_factory=dict)

    def run_id(self) -> str:
        return f"{_handler_event_name_label(self.event_name)}:{self.display_order}:{self.source_path}"


@dataclass(frozen=True)
class CommandRunResult:
    started_at: int
    completed_at: int
    duration_ms: int
    exit_code: int | None
    stdout: str
    stderr: str
    error: str | None = None


@dataclass
class ParsedHandler:
    completed: HookCompletedEvent
    data: Any
    completion_order: int = 0


def scope_for_event(event_name: HookEventName | str) -> HookScope:
    event = HookEventName(event_name)
    if event in {HookEventName.SESSION_START, HookEventName.SUBAGENT_START}:
        return HookScope.THREAD
    return HookScope.TURN


def _running_summary(handler: Any) -> HookRunSummary:
    event_name = HookEventName(_field(handler, "event_name"))
    raw_source_path = _field(handler, "source_path", "")
    source_path = raw_source_path if hasattr(raw_source_path, "__fspath__") else Path(str(raw_source_path))
    display_order = int(_field(handler, "display_order", 0))
    run_id = f"{_handler_event_name_label(event_name)}:{display_order}:{source_path}"
    return HookRunSummary(
        id=run_id,
        event_name=event_name,
        handler_type=HookHandlerType.COMMAND,
        execution_mode=HookExecutionMode.SYNC,
        scope=scope_for_event(event_name),
        source_path=source_path,
        source=HookSource(_field(handler, "source", HookSource.UNKNOWN)),
        display_order=display_order,
        status=HookRunStatus.RUNNING,
        status_message=_field(handler, "status_message"),
        started_at=int(_field(handler, "started_at", 0)),
    )


def running_summary(handler: Any) -> HookRunSummary:
    return _running_summary(handler)


def select_handlers(
    handlers: Sequence[ConfiguredHandler],
    event_name: HookEventName | str,
    matcher_input: str | None,
) -> list[ConfiguredHandler]:
    matcher_inputs = [] if matcher_input is None else [matcher_input]
    return select_handlers_for_matcher_inputs(handlers, event_name, matcher_inputs)


def select_handlers_for_matcher_inputs(
    handlers: Sequence[ConfiguredHandler],
    event_name: HookEventName | str,
    matcher_inputs: Sequence[str],
) -> list[ConfiguredHandler]:
    event = HookEventName(event_name)
    selected: list[ConfiguredHandler] = []
    for handler in handlers:
        if HookEventName(handler.event_name) != event:
            continue
        if event in {
            HookEventName.PRE_TOOL_USE,
            HookEventName.PERMISSION_REQUEST,
            HookEventName.POST_TOOL_USE,
            HookEventName.SESSION_START,
            HookEventName.SUBAGENT_START,
            HookEventName.SUBAGENT_STOP,
            HookEventName.PRE_COMPACT,
            HookEventName.POST_COMPACT,
        }:
            if not matcher_inputs:
                if not matches_matcher(handler.matcher, None):
                    continue
            elif not any(matches_matcher(handler.matcher, matcher_input) for matcher_input in matcher_inputs):
                continue
        selected.append(handler)
    return selected


def completed_summary(
    handler: Any,
    run_result: Any,
    status: HookRunStatus,
    entries: Sequence[HookOutputEntry],
) -> HookRunSummary:
    event_name = HookEventName(_field(handler, "event_name"))
    raw_source_path = _field(handler, "source_path", "")
    source_path = raw_source_path if hasattr(raw_source_path, "__fspath__") else Path(str(raw_source_path))
    display_order = int(_field(handler, "display_order", 0))
    return HookRunSummary(
        id=f"{_handler_event_name_label(event_name)}:{display_order}:{source_path}",
        event_name=event_name,
        handler_type=HookHandlerType.COMMAND,
        execution_mode=HookExecutionMode.SYNC,
        scope=scope_for_event(event_name),
        source_path=source_path,
        source=HookSource(_field(handler, "source", HookSource.UNKNOWN)),
        display_order=display_order,
        status=status,
        status_message=_field(handler, "status_message"),
        started_at=int(_field(run_result, "started_at")),
        completed_at=int(_field(run_result, "completed_at")),
        duration_ms=int(_field(run_result, "duration_ms")),
        entries=tuple(entries),
    )


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


async def execute_handlers(
    shell: CommandShell,
    handlers: Sequence[ConfiguredHandler],
    input_json: str,
    cwd: Path,
    turn_id: str | None,
    parse: Callable[[ConfiguredHandler, CommandRunResult, str | None], ParsedHandler],
    run_command_func: Callable[
        [CommandShell, ConfiguredHandler, str, Path],
        Awaitable[CommandRunResult],
    ]
    | None = None,
) -> list[ParsedHandler]:
    if run_command_func is None:
        run_command_func = run_command

    async def run_one(configured_order: int, handler: ConfiguredHandler) -> tuple[int, ParsedHandler]:
        result = await run_command_func(shell, handler, input_json, cwd)
        return configured_order, parse(handler, result, turn_id)

    tasks = [
        asyncio.create_task(run_one(configured_order, handler))
        for configured_order, handler in enumerate(handlers)
    ]
    completed: list[tuple[int, ParsedHandler]] = []
    completion_order = 0
    for task in asyncio.as_completed(tasks):
        configured_order, parsed = await task
        object.__setattr__(parsed, "completion_order", completion_order)
        completion_order += 1
        completed.append((configured_order, parsed))
    completed.sort(key=lambda item: item[0])
    return [parsed for _, parsed in completed]


def serialization_failure_hook_events(
    handlers: Sequence[Any],
    turn_id: str | None,
    error_message: str,
) -> list[HookCompletedEvent]:
    events: list[HookCompletedEvent] = []
    for handler in handlers:
        run = _running_summary(handler)
        events.append(
            HookCompletedEvent(
                turn_id=turn_id,
                run=replace(
                    run,
                    status=HookRunStatus.FAILED,
                    completed_at=run.started_at,
                    duration_ms=0,
                    entries=(
                        HookOutputEntry(
                            HookOutputEntryKind.ERROR,
                            error_message,
                        ),
                    ),
                ),
            )
        )
    return events


def serialization_failure_hook_events_for_tool_use(
    handlers: Sequence[Any],
    turn_id: str | None,
    error_message: str,
    tool_use_id: str,
) -> list[HookCompletedEvent]:
    return [
        hook_completed_for_tool_use(event, tool_use_id)
        for event in serialization_failure_hook_events(
            handlers,
            turn_id,
            error_message,
        )
    ]


def hook_completed_for_tool_use(
    event: HookCompletedEvent,
    tool_use_id: str,
) -> HookCompletedEvent:
    return replace(event, run=hook_run_for_tool_use(event.run, tool_use_id))


def hook_run_for_tool_use(
    run: HookRunSummary,
    tool_use_id: str,
) -> HookRunSummary:
    return replace(run, id=f"{run.id}:{tool_use_id}")


def matcher_pattern_for_event(
    event_name: HookEventName | str,
    matcher: str | None,
) -> str | None:
    event = HookEventName(event_name)
    if event in {
        HookEventName.PRE_TOOL_USE,
        HookEventName.PERMISSION_REQUEST,
        HookEventName.POST_TOOL_USE,
        HookEventName.SESSION_START,
        HookEventName.SUBAGENT_START,
        HookEventName.SUBAGENT_STOP,
        HookEventName.PRE_COMPACT,
        HookEventName.POST_COMPACT,
    }:
        return matcher
    return None


def _is_match_all_matcher(matcher: str) -> bool:
    return matcher == "" or matcher == "*"


def _is_exact_matcher(matcher: str) -> bool:
    return all(ch.isascii() and (ch.isalnum() or ch in "_|") for ch in matcher)


def validate_matcher_pattern(matcher: str) -> None:
    if _is_match_all_matcher(matcher) or _is_exact_matcher(matcher):
        return None
    re.compile(matcher)
    return None


def matches_matcher(matcher: str | None, input: str | None) -> bool:
    if matcher is None:
        return True
    if _is_match_all_matcher(matcher):
        return True
    if _is_exact_matcher(matcher):
        if input is None:
            return False
        return any(candidate == input for candidate in matcher.split("|"))
    if input is None:
        return False
    try:
        return re.search(matcher, input) is not None
    except re.error:
        return False


def matcher_inputs(tool_name: str, matcher_aliases: Sequence[str]) -> list[str]:
    return [tool_name, *matcher_aliases]


class HookResultKind(str, Enum):
    SUCCESS = "success"
    FAILED_CONTINUE = "failed_continue"
    FAILED_ABORT = "failed_abort"


@dataclass(frozen=True)
class HookResult:
    kind: HookResultKind
    error: Exception | str | None = None

    @classmethod
    def Success(cls) -> "HookResult":
        return cls(HookResultKind.SUCCESS)

    @classmethod
    def FailedContinue(cls, error: Exception | str) -> "HookResult":
        return cls(HookResultKind.FAILED_CONTINUE, error)

    @classmethod
    def FailedAbort(cls, error: Exception | str) -> "HookResult":
        return cls(HookResultKind.FAILED_ABORT, error)

    def should_abort_operation(self) -> bool:
        return self.kind == HookResultKind.FAILED_ABORT


@dataclass
class HookResponse:
    hook_name: str
    result: HookResult


HookFunc = Callable[["HookPayload"], Awaitable[HookResult] | HookResult]


async def _default_hook_func(_payload: "HookPayload") -> HookResult:
    return HookResult.Success()


@dataclass
class Hook:
    name: str = "default"
    func: HookFunc = _default_hook_func

    async def execute(self, payload: "HookPayload") -> HookResponse:
        result = self.func(payload)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[assignment]
        if not isinstance(result, HookResult):
            raise TypeError("hook func must return HookResult")
        return HookResponse(self.name, result)


@dataclass
class HookEventAfterAgent:
    thread_id: ThreadId | str
    turn_id: str
    input_messages: list[str]
    last_assistant_message: str | None


@dataclass
class HookEvent:
    after_agent: HookEventAfterAgent

    @classmethod
    def AfterAgent(cls, event: HookEventAfterAgent) -> "HookEvent":
        return cls(event)

    def to_mapping(self) -> dict[str, Any]:
        event = self.after_agent
        return {
            "event_type": "after_agent",
            "thread_id": str(event.thread_id),
            "turn_id": event.turn_id,
            "input_messages": list(event.input_messages),
            "last_assistant_message": event.last_assistant_message,
        }


@dataclass
class HookPayload:
    session_id: ThreadId | str
    cwd: Path
    client: str | None
    triggered_at: datetime
    hook_event: HookEvent

    def to_mapping(self) -> dict[str, Any]:
        data = {
            "session_id": str(self.session_id),
            "cwd": str(self.cwd),
            "triggered_at": self.triggered_at.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "hook_event": self.hook_event.to_mapping(),
        }
        if self.client is not None:
            data["client"] = self.client
        return data


def legacy_notify_json(payload: HookPayload) -> str:
    event = payload.hook_event.after_agent
    return json.dumps(
        {
            "type": "agent-turn-complete",
            "thread-id": str(event.thread_id),
            "turn-id": event.turn_id,
            "cwd": str(payload.cwd),
            **({"client": payload.client} if payload.client is not None else {}),
            "input-messages": list(event.input_messages),
            "last-assistant-message": event.last_assistant_message,
        },
        separators=(",", ":"),
    )


def command_from_argv(argv: Sequence[str]) -> list[str] | None:
    if not argv or not argv[0]:
        return None
    return list(argv)


def notify_hook(argv: Sequence[str]) -> Hook:
    async def run(payload: HookPayload) -> HookResult:
        command = command_from_argv(argv)
        if command is None:
            return HookResult.Success()
        try:
            subprocess.Popen(
                [*command, legacy_notify_json(payload)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            return HookResult.FailedContinue(exc)
        return HookResult.Success()

    return Hook("legacy_notify", run)


def _hook_output_path(output_dir: Path, thread_id: ThreadId | str) -> Path:
    return output_dir / str(thread_id) / f"{uuid.uuid4()}.txt"


def _spilled_hook_output_preview(text: str, path: Path) -> str:
    footer = f"\n\nFull hook output saved to: {path}"
    preview_limit = max(HOOK_OUTPUT_TOKEN_LIMIT - approx_token_count(footer), 0)
    preview = formatted_truncate_text(
        text,
        TruncationPolicyConfig.tokens(preview_limit),
    )
    return f"{preview}{footer}"


@dataclass
class HookOutputSpiller:
    output_dir: Path = field(
        default_factory=lambda: Path(tempfile.gettempdir()) / HOOK_OUTPUTS_DIR
    )

    @classmethod
    def new(cls) -> "HookOutputSpiller":
        return cls()

    async def maybe_spill_text(self, thread_id: ThreadId | str, text: str) -> str:
        if approx_token_count(text) <= HOOK_OUTPUT_TOKEN_LIMIT:
            return text

        path = _hook_output_path(self.output_dir, thread_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError:
            return formatted_truncate_text(
                text,
                TruncationPolicyConfig.tokens(HOOK_OUTPUT_TOKEN_LIMIT),
            )
        return _spilled_hook_output_preview(text, path)

    async def maybe_spill_texts(
        self,
        thread_id: ThreadId | str,
        texts: Sequence[str],
    ) -> list[str]:
        spilled: list[str] = []
        for text in texts:
            spilled.append(await self.maybe_spill_text(thread_id, text))
        return spilled

    async def maybe_spill_prompt_fragments(
        self,
        thread_id: ThreadId | str,
        fragments: Sequence[HookPromptFragment],
    ) -> list[HookPromptFragment]:
        spilled: list[HookPromptFragment] = []
        for fragment in fragments:
            spilled.append(
                HookPromptFragment(
                    text=await self.maybe_spill_text(thread_id, fragment.text),
                    hook_run_id=fragment.hook_run_id,
                )
            )
        return spilled


@dataclass
class PreToolUseRequest:
    session_id: ThreadId | str
    turn_id: str
    subagent: SubagentHookContext | None
    cwd: Path
    transcript_path: Path | None
    model: str
    permission_mode: str
    tool_name: str
    matcher_aliases: Sequence[str]
    run_id_suffix: str | None
    tool_use_id: str
    tool_input: Any


@dataclass
class PreToolUseOutcome:
    hook_events: list[HookCompletedEvent]
    should_block: bool
    block_reason: str | None
    additional_contexts: list[str]
    updated_input: Any | None


@dataclass(frozen=True)
class PreToolUseHandlerData:
    should_block: bool = False
    block_reason: str | None = None
    additional_contexts_for_model: list[str] = field(default_factory=list)
    updated_input: Any | None = None


@dataclass(frozen=True)
class ParsedPreToolUseHandler:
    completed: HookCompletedEvent
    data: PreToolUseHandlerData
    completion_order: int = 0


def pre_tool_use_command_input_json(request: PreToolUseRequest) -> str:
    payload: dict[str, Any] = {
        "session_id": str(request.session_id),
        "turn_id": request.turn_id,
        "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
        "cwd": str(request.cwd),
        "hook_event_name": "PreToolUse",
        "model": request.model,
        "permission_mode": request.permission_mode,
        "tool_name": request.tool_name,
        "tool_input": request.tool_input,
        "tool_use_id": request.tool_use_id,
    }
    if request.subagent is not None:
        payload["agent_id"] = request.subagent.agent_id
        payload["agent_type"] = request.subagent.agent_type
    return json.dumps(payload, separators=(",", ":"))


def _pre_tool_use_invalid_universal(parsed: Mapping[str, Any]) -> str | None:
    if parsed.get("continue", True) is False:
        return "PreToolUse hook returned unsupported continue:false"
    if parsed.get("stopReason") is not None:
        return "PreToolUse hook returned unsupported stopReason"
    if parsed.get("suppressOutput", False) is True:
        return "PreToolUse hook returned unsupported suppressOutput"
    return None


@dataclass(frozen=True)
class UniversalOutput:
    continue_processing: bool = True
    stop_reason: str | None = None
    suppress_output: bool = False
    system_message: str | None = None


@dataclass(frozen=True)
class SessionStartOutput:
    universal: UniversalOutput
    additional_context: str | None = None


@dataclass(frozen=True)
class PreToolUseOutput:
    universal: UniversalOutput
    block_reason: str | None = None
    additional_context: str | None = None
    updated_input: Any | None = None
    invalid_reason: str | None = None


@dataclass(frozen=True)
class PermissionRequestOutput:
    universal: UniversalOutput
    decision: "PermissionRequestDecision | None" = None
    invalid_reason: str | None = None


@dataclass(frozen=True)
class PostToolUseOutput:
    universal: UniversalOutput
    should_block: bool = False
    reason: str | None = None
    invalid_block_reason: str | None = None
    additional_context: str | None = None
    invalid_reason: str | None = None


@dataclass(frozen=True)
class UserPromptSubmitOutput:
    universal: UniversalOutput
    should_block: bool = False
    reason: str | None = None
    invalid_block_reason: str | None = None
    additional_context: str | None = None


@dataclass(frozen=True)
class StopOutput:
    universal: UniversalOutput
    should_block: bool = False
    reason: str | None = None
    invalid_block_reason: str | None = None


@dataclass(frozen=True)
class PreCompactOutput:
    universal: UniversalOutput
    invalid_reason: str | None = None


@dataclass(frozen=True)
class StatelessHookOutput:
    universal: UniversalOutput
    invalid_reason: str | None = None


_UNIVERSAL_OUTPUT_FIELDS = {"continue", "stopReason", "suppressOutput", "systemMessage"}
_HOOK_EVENT_NAME_WIRE_VALUES = {
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SessionStart",
    "UserPromptSubmit",
    "SubagentStart",
    "SubagentStop",
    "Stop",
}


def looks_like_json(stdout: str) -> bool:
    return _looks_like_json(stdout)


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _output_parser_trimmed_reason(reason: Any) -> str | None:
    if not isinstance(reason, str):
        return None
    trimmed = reason.strip()
    return trimmed or None


def _invalid_block_message(event_name: str) -> str:
    return f"{event_name} hook returned decision:block without a non-empty reason"


def _wire_object(
    stdout: str,
    allowed_fields: set[str],
    hook_specific_allowed: set[str] | None = None,
    decision_allowed: set[str] | None = None,
    top_level_decisions: set[str] | None = None,
) -> Mapping[str, Any] | None:
    parsed = _parse_hook_json_output(stdout.strip())
    if parsed is None:
        return None
    if not set(parsed).issubset(_UNIVERSAL_OUTPUT_FIELDS | allowed_fields):
        return None
    if "continue" in parsed and not isinstance(parsed["continue"], bool):
        return None
    if "suppressOutput" in parsed and not isinstance(parsed["suppressOutput"], bool):
        return None
    if "stopReason" in parsed and parsed["stopReason"] is not None and not isinstance(parsed["stopReason"], str):
        return None
    if (
        "systemMessage" in parsed
        and parsed["systemMessage"] is not None
        and not isinstance(parsed["systemMessage"], str)
    ):
        return None
    if "decision" in parsed:
        decision = parsed["decision"]
        if top_level_decisions is not None and decision is not None and decision not in top_level_decisions:
            return None
    if "reason" in parsed and parsed["reason"] is not None and not isinstance(parsed["reason"], str):
        return None
    specific = parsed.get("hookSpecificOutput")
    if specific is not None:
        if hook_specific_allowed is None or not isinstance(specific, Mapping):
            return None
        if not set(specific).issubset(hook_specific_allowed):
            return None
        hook_event_name = specific.get("hookEventName")
        if hook_event_name not in _HOOK_EVENT_NAME_WIRE_VALUES:
            return None
        if "additionalContext" in specific and specific["additionalContext"] is not None and not isinstance(specific["additionalContext"], str):
            return None
        if "permissionDecision" in specific:
            permission_decision = specific["permissionDecision"]
            if permission_decision is not None and permission_decision not in {"allow", "deny", "ask"}:
                return None
        if (
            "permissionDecisionReason" in specific
            and specific["permissionDecisionReason"] is not None
            and not isinstance(specific["permissionDecisionReason"], str)
        ):
            return None
        decision_value = specific.get("decision")
        if decision_value is not None:
            if not isinstance(decision_value, Mapping):
                return None
            if decision_allowed is None or not set(decision_value).issubset(decision_allowed):
                return None
            behavior = decision_value.get("behavior")
            if behavior not in {"allow", "deny"}:
                return None
            if "message" in decision_value and decision_value["message"] is not None and not isinstance(decision_value["message"], str):
                return None
            if "interrupt" in decision_value and not isinstance(decision_value["interrupt"], bool):
                return None
    return parsed


def _universal_output(parsed: Mapping[str, Any]) -> UniversalOutput:
    return UniversalOutput(
        continue_processing=parsed.get("continue", True),
        stop_reason=_string_or_none(parsed.get("stopReason")),
        suppress_output=parsed.get("suppressOutput", False),
        system_message=_string_or_none(parsed.get("systemMessage")),
    )


def parse_session_start(stdout: str) -> SessionStartOutput | None:
    parsed = _wire_object(
        stdout,
        {"hookSpecificOutput"},
        hook_specific_allowed={"hookEventName", "additionalContext"},
    )
    if parsed is None:
        return None
    specific = parsed.get("hookSpecificOutput")
    additional_context = specific.get("additionalContext") if isinstance(specific, Mapping) else None
    return SessionStartOutput(_universal_output(parsed), _string_or_none(additional_context))


def parse_subagent_start(stdout: str) -> SessionStartOutput | None:
    return parse_session_start(stdout)


def parse_pre_tool_use(stdout: str) -> PreToolUseOutput | None:
    parsed = _wire_object(
        stdout,
        {"decision", "reason", "hookSpecificOutput"},
        hook_specific_allowed={
            "hookEventName",
            "permissionDecision",
            "permissionDecisionReason",
            "updatedInput",
            "additionalContext",
        },
        top_level_decisions={"approve", "block"},
    )
    if parsed is None:
        return None
    universal = _universal_output(parsed)
    specific = parsed.get("hookSpecificOutput")
    specific_mapping = specific if isinstance(specific, Mapping) else None
    additional_context = specific_mapping.get("additionalContext") if specific_mapping is not None else None
    use_hook_specific_decision = specific_mapping is not None and (
        specific_mapping.get("permissionDecision") is not None
        or specific_mapping.get("permissionDecisionReason") is not None
        or specific_mapping.get("updatedInput") is not None
    )
    invalid_reason = _pre_tool_use_invalid_universal(parsed)
    if invalid_reason is None:
        if use_hook_specific_decision and specific_mapping is not None:
            invalid_reason = _pre_tool_use_unsupported_hook_specific(specific_mapping)
        else:
            invalid_reason = _pre_tool_use_unsupported_legacy_decision(
                parsed.get("decision"),
                parsed.get("reason"),
            )
    block_reason = None
    updated_input = None
    if invalid_reason is None:
        if use_hook_specific_decision and specific_mapping is not None:
            if specific_mapping.get("permissionDecision") == "deny":
                block_reason = _output_parser_trimmed_reason(specific_mapping.get("permissionDecisionReason"))
            elif specific_mapping.get("permissionDecision") == "allow":
                updated_input = specific_mapping.get("updatedInput")
        elif parsed.get("decision") == "block":
            block_reason = _output_parser_trimmed_reason(parsed.get("reason"))
    return PreToolUseOutput(
        universal=universal,
        block_reason=block_reason,
        additional_context=_string_or_none(additional_context),
        updated_input=updated_input,
        invalid_reason=invalid_reason,
    )


def parse_permission_request(stdout: str) -> PermissionRequestOutput | None:
    parsed = _wire_object(
        stdout,
        {"hookSpecificOutput"},
        hook_specific_allowed={"hookEventName", "decision"},
        decision_allowed={"behavior", "updatedInput", "updatedPermissions", "message", "interrupt"},
    )
    if parsed is None:
        return None
    universal = _universal_output(parsed)
    specific = parsed.get("hookSpecificOutput")
    decision_mapping = None
    if isinstance(specific, Mapping):
        raw_decision = specific.get("decision")
        decision_mapping = raw_decision if isinstance(raw_decision, Mapping) else None
    invalid_reason = _permission_request_invalid_universal(parsed)
    if invalid_reason is None:
        invalid_reason = _permission_request_invalid_decision(decision_mapping)
    decision = _permission_request_decision(decision_mapping) if invalid_reason is None and decision_mapping is not None else None
    return PermissionRequestOutput(universal, decision, invalid_reason)


def parse_post_tool_use(stdout: str) -> PostToolUseOutput | None:
    parsed = _wire_object(
        stdout,
        {"decision", "reason", "hookSpecificOutput"},
        hook_specific_allowed={"hookEventName", "additionalContext", "updatedMCPToolOutput"},
        top_level_decisions={"block"},
    )
    if parsed is None:
        return None
    universal = _universal_output(parsed)
    invalid_reason = _post_tool_use_invalid_universal(parsed)
    specific = parsed.get("hookSpecificOutput")
    specific_mapping = specific if isinstance(specific, Mapping) else None
    if invalid_reason is None and specific_mapping is not None and specific_mapping.get("updatedMCPToolOutput") is not None:
        invalid_reason = "PostToolUse hook returned unsupported updatedMCPToolOutput"
    should_block_candidate = parsed.get("decision") == "block"
    invalid_block_reason = None
    if should_block_candidate and _output_parser_trimmed_reason(parsed.get("reason")) is None:
        invalid_block_reason = _invalid_block_message("PostToolUse")
    elif not should_block_candidate and universal.continue_processing and parsed.get("reason") is not None:
        invalid_block_reason = "PostToolUse hook returned reason without decision"
    additional_context = specific_mapping.get("additionalContext") if specific_mapping is not None else None
    return PostToolUseOutput(
        universal=universal,
        should_block=should_block_candidate and invalid_reason is None and invalid_block_reason is None,
        reason=_string_or_none(parsed.get("reason")),
        invalid_block_reason=invalid_block_reason,
        additional_context=_string_or_none(additional_context),
        invalid_reason=invalid_reason,
    )


def parse_pre_compact(stdout: str) -> PreCompactOutput | None:
    parsed = _wire_object(stdout, set())
    return None if parsed is None else PreCompactOutput(_universal_output(parsed))


def parse_post_compact(stdout: str) -> StatelessHookOutput | None:
    parsed = _wire_object(stdout, set())
    return None if parsed is None else StatelessHookOutput(_universal_output(parsed))


def parse_user_prompt_submit(stdout: str) -> UserPromptSubmitOutput | None:
    parsed = _wire_object(
        stdout,
        {"decision", "reason", "hookSpecificOutput"},
        hook_specific_allowed={"hookEventName", "additionalContext"},
        top_level_decisions={"block"},
    )
    if parsed is None:
        return None
    should_block_candidate = parsed.get("decision") == "block"
    invalid_block_reason = (
        _invalid_block_message("UserPromptSubmit")
        if should_block_candidate and _output_parser_trimmed_reason(parsed.get("reason")) is None
        else None
    )
    specific = parsed.get("hookSpecificOutput")
    additional_context = specific.get("additionalContext") if isinstance(specific, Mapping) else None
    return UserPromptSubmitOutput(
        universal=_universal_output(parsed),
        should_block=should_block_candidate and invalid_block_reason is None,
        reason=_string_or_none(parsed.get("reason")),
        invalid_block_reason=invalid_block_reason,
        additional_context=_string_or_none(additional_context),
    )


def _stop_output(parsed: Mapping[str, Any], event_name: str) -> StopOutput:
    should_block_candidate = parsed.get("decision") == "block"
    invalid_block_reason = (
        _invalid_block_message(event_name)
        if should_block_candidate and _output_parser_trimmed_reason(parsed.get("reason")) is None
        else None
    )
    return StopOutput(
        universal=_universal_output(parsed),
        should_block=should_block_candidate and invalid_block_reason is None,
        reason=_string_or_none(parsed.get("reason")),
        invalid_block_reason=invalid_block_reason,
    )


def parse_stop(stdout: str) -> StopOutput | None:
    parsed = _wire_object(stdout, {"decision", "reason"}, top_level_decisions={"block"})
    return None if parsed is None else _stop_output(parsed, "Stop")


def parse_subagent_stop(stdout: str) -> StopOutput | None:
    parsed = _wire_object(stdout, {"decision", "reason"}, top_level_decisions={"block"})
    return None if parsed is None else _stop_output(parsed, "SubagentStop")


def _pre_tool_use_unsupported_hook_specific(specific: Mapping[str, Any]) -> str | None:
    permission_decision = specific.get("permissionDecision")
    permission_reason = specific.get("permissionDecisionReason")
    has_updated_input = specific.get("updatedInput") is not None

    if has_updated_input and permission_decision != "allow":
        return "PreToolUse hook returned updatedInput without permissionDecision:allow"
    if permission_decision == "allow":
        if not has_updated_input:
            return "PreToolUse hook returned unsupported permissionDecision:allow"
    elif permission_decision == "ask":
        return "PreToolUse hook returned unsupported permissionDecision:ask"
    elif permission_decision == "deny":
        if _non_empty_string(permission_reason) is None:
            return (
                "PreToolUse hook returned permissionDecision:deny without a non-empty "
                "permissionDecisionReason"
            )
    elif permission_decision is None:
        if permission_reason is not None:
            return "PreToolUse hook returned permissionDecisionReason without permissionDecision"
    return None


def _pre_tool_use_unsupported_legacy_decision(
    decision: Any,
    reason: Any,
) -> str | None:
    if decision == "approve":
        return "PreToolUse hook returned unsupported decision:approve"
    if decision == "block":
        if _non_empty_string(reason) is None:
            return "PreToolUse hook returned decision:block without a non-empty reason"
    elif decision is None:
        if reason is not None:
            return "PreToolUse hook returned reason without decision"
    return None


def parse_pre_tool_use_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedPreToolUseHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_block = False
    block_reason = None
    additional_contexts_for_model: list[str] = []
    updated_input = None

    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.PRE_TOOL_USE:
        raise ValueError(f"expected pre tool use hook event, got {event_name}")

    error = _field(run_result, "error")
    exit_code = _field(run_result, "exit_code")
    stdout = str(_field(run_result, "stdout", ""))
    stderr = str(_field(run_result, "stderr", ""))

    if error is not None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, str(error)))
    elif exit_code == 0:
        trimmed_stdout = stdout.strip()
        if not trimmed_stdout:
            pass
        else:
            parsed = _parse_hook_json_output(stdout)
            if parsed is not None:
                system_message = parsed.get("systemMessage")
                if isinstance(system_message, str):
                    entries.append(HookOutputEntry(HookOutputEntryKind.WARNING, system_message))

                specific = parsed.get("hookSpecificOutput")
                specific_mapping = specific if isinstance(specific, Mapping) else None
                use_hook_specific_decision = (
                    specific_mapping is not None
                    and (
                        specific_mapping.get("permissionDecision") is not None
                        or specific_mapping.get("permissionDecisionReason") is not None
                        or specific_mapping.get("updatedInput") is not None
                    )
                )
                invalid_reason = _pre_tool_use_invalid_universal(parsed)
                if invalid_reason is None:
                    if use_hook_specific_decision and specific_mapping is not None:
                        invalid_reason = _pre_tool_use_unsupported_hook_specific(specific_mapping)
                    else:
                        invalid_reason = _pre_tool_use_unsupported_legacy_decision(
                            parsed.get("decision"),
                            parsed.get("reason"),
                        )

                if invalid_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_reason))
                else:
                    additional_context = (
                        specific_mapping.get("additionalContext")
                        if specific_mapping is not None
                        else None
                    )
                    if isinstance(additional_context, str):
                        append_additional_context(
                            entries,
                            additional_contexts_for_model,
                            additional_context,
                        )

                    if use_hook_specific_decision and specific_mapping is not None:
                        if specific_mapping.get("permissionDecision") == "deny":
                            block_reason = _non_empty_string(
                                specific_mapping.get("permissionDecisionReason")
                            )
                        elif specific_mapping.get("permissionDecision") == "allow":
                            updated_input = specific_mapping.get("updatedInput")
                    elif parsed.get("decision") == "block":
                        block_reason = _non_empty_string(parsed.get("reason"))

                    if block_reason is not None:
                        status = HookRunStatus.BLOCKED
                        should_block = True
                        entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, block_reason))
                        updated_input = None
            elif _looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        "hook returned invalid pre-tool-use JSON output",
                    )
                )
    elif exit_code == 2:
        reason = trimmed_non_empty(stderr)
        if reason is not None:
            status = HookRunStatus.BLOCKED
            should_block = True
            block_reason = reason
            entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
        else:
            status = HookRunStatus.FAILED
            entries.append(
                HookOutputEntry(
                    HookOutputEntryKind.ERROR,
                    "PreToolUse hook exited with code 2 but did not write a blocking reason to stderr",
                )
            )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    return ParsedPreToolUseHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=_completed_summary(handler, run_result, status, entries),
        ),
        data=PreToolUseHandlerData(
            should_block=should_block,
            block_reason=block_reason,
            additional_contexts_for_model=additional_contexts_for_model,
            updated_input=updated_input,
        ),
    )


def latest_pre_tool_use_updated_input(
    results: Sequence[ParsedPreToolUseHandler],
) -> Any | None:
    candidates = [
        (result.completion_order, result.data.updated_input)
        for result in results
        if result.data.updated_input is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[0])[1]


class PermissionRequestDecisionKind(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class PermissionRequestDecision:
    kind: PermissionRequestDecisionKind
    message: str | None = None

    @classmethod
    def Allow(cls) -> "PermissionRequestDecision":
        return cls(PermissionRequestDecisionKind.ALLOW)

    @classmethod
    def Deny(cls, message: str) -> "PermissionRequestDecision":
        return cls(PermissionRequestDecisionKind.DENY, message)


@dataclass
class PermissionRequestRequest:
    session_id: ThreadId | str
    turn_id: str
    subagent: SubagentHookContext | None
    cwd: Path
    transcript_path: Path | None
    model: str
    permission_mode: str
    tool_name: str
    matcher_aliases: Sequence[str]
    run_id_suffix: str | None
    tool_input: Any


@dataclass
class PermissionRequestOutcome:
    hook_events: list[HookCompletedEvent]
    decision: PermissionRequestDecision | None


@dataclass(frozen=True)
class PermissionRequestHandlerData:
    decision: PermissionRequestDecision | None = None


@dataclass(frozen=True)
class ParsedPermissionRequestHandler:
    completed: HookCompletedEvent
    data: PermissionRequestHandlerData
    completion_order: int = 0


def permission_request_command_input_json(request: PermissionRequestRequest) -> str:
    payload: dict[str, Any] = {
        "session_id": str(request.session_id),
        "turn_id": request.turn_id,
        "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
        "cwd": str(request.cwd),
        "hook_event_name": "PermissionRequest",
        "model": request.model,
        "permission_mode": request.permission_mode,
        "tool_name": request.tool_name,
        "tool_input": request.tool_input,
    }
    if request.subagent is not None:
        payload["agent_id"] = request.subagent.agent_id
        payload["agent_type"] = request.subagent.agent_type
    return json.dumps(payload, separators=(",", ":"))


def _permission_request_invalid_universal(parsed: Mapping[str, Any]) -> str | None:
    if parsed.get("continue", True) is False:
        return "PermissionRequest hook returned unsupported continue:false"
    if parsed.get("stopReason") is not None:
        return "PermissionRequest hook returned unsupported stopReason"
    if parsed.get("suppressOutput", False) is True:
        return "PermissionRequest hook returned unsupported suppressOutput"
    return None


def _permission_request_invalid_decision(decision: Mapping[str, Any] | None) -> str | None:
    if decision is None:
        return None
    if decision.get("updatedInput") is not None:
        return "PermissionRequest hook returned unsupported updatedInput"
    if decision.get("updatedPermissions") is not None:
        return "PermissionRequest hook returned unsupported updatedPermissions"
    if decision.get("interrupt", False) is True:
        return "PermissionRequest hook returned unsupported interrupt:true"
    return None


def _permission_request_decision(decision: Mapping[str, Any]) -> PermissionRequestDecision | None:
    behavior = decision.get("behavior")
    if behavior == "allow":
        return PermissionRequestDecision.Allow()
    if behavior == "deny":
        message = _non_empty_string(decision.get("message")) or "PermissionRequest hook denied approval"
        return PermissionRequestDecision.Deny(message)
    return None


def parse_permission_request_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedPermissionRequestHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    decision = None

    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.PERMISSION_REQUEST:
        raise ValueError(f"expected permission request hook event, got {event_name}")

    error = _field(run_result, "error")
    exit_code = _field(run_result, "exit_code")
    stdout = str(_field(run_result, "stdout", ""))
    stderr = str(_field(run_result, "stderr", ""))

    if error is not None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, str(error)))
    elif exit_code == 0:
        trimmed_stdout = stdout.strip()
        if not trimmed_stdout:
            pass
        else:
            parsed = _parse_hook_json_output(stdout)
            if parsed is not None:
                system_message = parsed.get("systemMessage")
                if isinstance(system_message, str):
                    entries.append(HookOutputEntry(HookOutputEntryKind.WARNING, system_message))

                specific = parsed.get("hookSpecificOutput")
                specific_mapping = specific if isinstance(specific, Mapping) else None
                raw_decision = (
                    specific_mapping.get("decision")
                    if specific_mapping is not None
                    else None
                )
                decision_mapping = raw_decision if isinstance(raw_decision, Mapping) else None
                invalid_reason = _permission_request_invalid_universal(parsed)
                if invalid_reason is None:
                    invalid_reason = _permission_request_invalid_decision(decision_mapping)

                if invalid_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_reason))
                elif decision_mapping is not None:
                    parsed_decision = _permission_request_decision(decision_mapping)
                    if parsed_decision == PermissionRequestDecision.Allow():
                        decision = parsed_decision
                    elif parsed_decision is not None and parsed_decision.kind == PermissionRequestDecisionKind.DENY:
                        status = HookRunStatus.BLOCKED
                        message = parsed_decision.message or "PermissionRequest hook denied approval"
                        entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, message))
                        decision = parsed_decision
            elif _looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        "hook returned invalid permission-request JSON output",
                    )
                )
    elif exit_code == 2:
        message = trimmed_non_empty(stderr)
        if message is not None:
            status = HookRunStatus.BLOCKED
            entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, message))
            decision = PermissionRequestDecision.Deny(message)
        else:
            status = HookRunStatus.FAILED
            entries.append(
                HookOutputEntry(
                    HookOutputEntryKind.ERROR,
                    (
                        "PermissionRequest hook exited with code 2 but did not write a "
                        "denial reason to stderr"
                    ),
                )
            )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    return ParsedPermissionRequestHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=_completed_summary(handler, run_result, status, entries),
        ),
        data=PermissionRequestHandlerData(decision=decision),
    )


def resolve_permission_request_decision(
    decisions: Sequence[PermissionRequestDecision],
) -> PermissionRequestDecision | None:
    resolved_allow = None
    for decision in decisions:
        if decision.kind == PermissionRequestDecisionKind.ALLOW:
            resolved_allow = PermissionRequestDecision.Allow()
        elif decision.kind == PermissionRequestDecisionKind.DENY:
            return PermissionRequestDecision.Deny(decision.message or "")
    return resolved_allow


@dataclass
class PostToolUseRequest:
    session_id: ThreadId | str
    turn_id: str
    subagent: SubagentHookContext | None
    cwd: Path
    transcript_path: Path | None
    model: str
    permission_mode: str
    tool_name: str
    matcher_aliases: Sequence[str]
    run_id_suffix: str | None
    tool_use_id: str
    tool_input: Any
    tool_response: Any


@dataclass
class PostToolUseOutcome:
    hook_events: list[HookCompletedEvent]
    should_stop: bool
    stop_reason: str | None
    additional_contexts: list[str]
    feedback_message: str | None


@dataclass(frozen=True)
class PostToolUseHandlerData:
    should_stop: bool = False
    stop_reason: str | None = None
    additional_contexts_for_model: list[str] = field(default_factory=list)
    feedback_messages_for_model: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedPostToolUseHandler:
    completed: HookCompletedEvent
    data: PostToolUseHandlerData
    completion_order: int = 0


def post_tool_use_command_input_json(request: PostToolUseRequest) -> str:
    payload: dict[str, Any] = {
        "session_id": str(request.session_id),
        "turn_id": request.turn_id,
        "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
        "cwd": str(request.cwd),
        "hook_event_name": "PostToolUse",
        "model": request.model,
        "permission_mode": request.permission_mode,
        "tool_name": request.tool_name,
        "tool_input": request.tool_input,
        "tool_response": request.tool_response,
        "tool_use_id": request.tool_use_id,
    }
    if request.subagent is not None:
        payload["agent_id"] = request.subagent.agent_id
        payload["agent_type"] = request.subagent.agent_type
    return json.dumps(payload, separators=(",", ":"))


def _post_tool_use_invalid_universal(parsed: Mapping[str, Any]) -> str | None:
    if parsed.get("suppressOutput", False) is True:
        return "PostToolUse hook returned unsupported suppressOutput"
    return None


def _post_tool_use_invalid_hook_specific(specific: Mapping[str, Any] | None) -> str | None:
    if specific is not None and specific.get("updatedMCPToolOutput") is not None:
        return "PostToolUse hook returned unsupported updatedMCPToolOutput"
    return None


def _post_tool_use_invalid_block_reason(parsed: Mapping[str, Any]) -> str | None:
    should_block = parsed.get("decision") == "block"
    reason = parsed.get("reason")
    if should_block and _non_empty_string(reason) is None:
        return "PostToolUse hook returned decision:block without a non-empty reason"
    if not should_block and parsed.get("continue", True) is True and reason is not None:
        return "PostToolUse hook returned reason without decision"
    return None


def parse_post_tool_use_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedPostToolUseHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_stop = False
    stop_reason = None
    additional_contexts_for_model: list[str] = []
    feedback_messages_for_model: list[str] = []

    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.POST_TOOL_USE:
        raise ValueError(f"expected post tool use hook event, got {event_name}")

    error = _field(run_result, "error")
    exit_code = _field(run_result, "exit_code")
    stdout = str(_field(run_result, "stdout", ""))
    stderr = str(_field(run_result, "stderr", ""))

    if error is not None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, str(error)))
    elif exit_code == 0:
        trimmed_stdout = stdout.strip()
        if not trimmed_stdout:
            pass
        else:
            parsed = _parse_hook_json_output(stdout)
            if parsed is not None:
                system_message = parsed.get("systemMessage")
                if isinstance(system_message, str):
                    entries.append(HookOutputEntry(HookOutputEntryKind.WARNING, system_message))

                specific = parsed.get("hookSpecificOutput")
                specific_mapping = specific if isinstance(specific, Mapping) else None
                invalid_reason = _post_tool_use_invalid_universal(parsed)
                if invalid_reason is None:
                    invalid_reason = _post_tool_use_invalid_hook_specific(specific_mapping)
                invalid_block_reason = _post_tool_use_invalid_block_reason(parsed)

                additional_context = (
                    specific_mapping.get("additionalContext")
                    if specific_mapping is not None
                    else None
                )
                if (
                    invalid_reason is None
                    and invalid_block_reason is None
                    and isinstance(additional_context, str)
                ):
                    append_additional_context(
                        entries,
                        additional_contexts_for_model,
                        additional_context,
                    )

                if parsed.get("continue", True) is False:
                    status = HookRunStatus.STOPPED
                    should_stop = True
                    raw_stop_reason = parsed.get("stopReason")
                    stop_reason = raw_stop_reason if isinstance(raw_stop_reason, str) else None
                    stop_text = stop_reason or "PostToolUse hook stopped execution"
                    entries.append(HookOutputEntry(HookOutputEntryKind.STOP, stop_text))
                    feedback = _non_empty_string(parsed.get("reason")) or stop_text
                    feedback_messages_for_model.append(feedback)
                elif invalid_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_reason))
                elif invalid_block_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_block_reason))
                elif parsed.get("decision") == "block":
                    status = HookRunStatus.BLOCKED
                    reason = parsed.get("reason")
                    if isinstance(reason, str):
                        entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
                        feedback_messages_for_model.append(reason)
            elif _looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        "hook returned invalid post-tool-use JSON output",
                    )
                )
    elif exit_code == 2:
        reason = trimmed_non_empty(stderr)
        if reason is not None:
            entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
            feedback_messages_for_model.append(reason)
        else:
            status = HookRunStatus.FAILED
            entries.append(
                HookOutputEntry(
                    HookOutputEntryKind.ERROR,
                    "PostToolUse hook exited with code 2 but did not write feedback to stderr",
                )
            )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    return ParsedPostToolUseHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=_completed_summary(handler, run_result, status, entries),
        ),
        data=PostToolUseHandlerData(
            should_stop=should_stop,
            stop_reason=stop_reason,
            additional_contexts_for_model=additional_contexts_for_model,
            feedback_messages_for_model=feedback_messages_for_model,
        ),
    )


def post_tool_use_feedback_message(results: Sequence[PostToolUseHandlerData]) -> str | None:
    return join_text_chunks(
        [
            feedback
            for result in results
            for feedback in result.feedback_messages_for_model
        ]
    )


@dataclass
class PreCompactRequest:
    session_id: ThreadId | str
    turn_id: str
    subagent: SubagentHookContext | None
    cwd: Path
    transcript_path: Path | None
    model: str
    trigger: str


@dataclass
class PostCompactRequest(PreCompactRequest):
    pass


@dataclass
class StatelessHookOutcome:
    hook_events: list[HookCompletedEvent]
    should_stop: bool
    stop_reason: str | None


@dataclass
class PreCompactOutcome(StatelessHookOutcome):
    pass


@dataclass(frozen=True)
class CompactHandlerData:
    should_stop: bool = False
    stop_reason: str | None = None


@dataclass(frozen=True)
class ParsedCompactHandler:
    completed: HookCompletedEvent
    data: CompactHandlerData
    completion_order: int = 0


def _compact_command_input_payload(
    request: PreCompactRequest | PostCompactRequest,
    hook_event_name: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": str(request.session_id),
        "turn_id": request.turn_id,
        "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
        "cwd": str(request.cwd),
        "hook_event_name": hook_event_name,
        "model": request.model,
        "trigger": request.trigger,
    }
    if request.subagent is not None:
        payload["agent_id"] = request.subagent.agent_id
        payload["agent_type"] = request.subagent.agent_type
    return payload


def pre_compact_command_input_json(request: PreCompactRequest) -> str:
    return json.dumps(
        _compact_command_input_payload(request, "PreCompact"),
        separators=(",", ":"),
    )


def post_compact_command_input_json(request: PostCompactRequest) -> str:
    return json.dumps(
        _compact_command_input_payload(request, "PostCompact"),
        separators=(",", ":"),
    )


_COMPACT_OUTPUT_FIELDS = frozenset(
    {
        "continue",
        "stopReason",
        "suppressOutput",
        "systemMessage",
    }
)


def _parse_compact_json_output(text: str) -> Mapping[str, Any] | None:
    parsed = _parse_hook_json_output(text)
    if parsed is None:
        return None
    if set(parsed) - _COMPACT_OUTPUT_FIELDS:
        return None
    continue_processing = parsed.get("continue", True)
    suppress_output = parsed.get("suppressOutput", False)
    if not isinstance(continue_processing, bool):
        return None
    if not isinstance(suppress_output, bool):
        return None
    if parsed.get("stopReason") is not None and not isinstance(parsed.get("stopReason"), str):
        return None
    if parsed.get("systemMessage") is not None and not isinstance(parsed.get("systemMessage"), str):
        return None
    return parsed


def _parse_compact_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
    event_label: str,
) -> ParsedCompactHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_stop = False
    stop_reason = None

    error = _field(run_result, "error")
    exit_code = _field(run_result, "exit_code")
    stdout = str(_field(run_result, "stdout", ""))
    stderr = str(_field(run_result, "stderr", ""))

    if error is not None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, str(error)))
    elif exit_code == 0:
        trimmed_stdout = stdout.strip()
        if not trimmed_stdout:
            pass
        else:
            parsed = _parse_compact_json_output(stdout)
            if parsed is not None:
                system_message = parsed.get("systemMessage")
                if isinstance(system_message, str):
                    entries.append(HookOutputEntry(HookOutputEntryKind.WARNING, system_message))

                if parsed.get("continue", True) is False:
                    status = HookRunStatus.STOPPED
                    should_stop = True
                    raw_stop_reason = parsed.get("stopReason")
                    stop_reason = raw_stop_reason if isinstance(raw_stop_reason, str) else None
                    stop_text = stop_reason or f"{event_label} hook stopped execution"
                    entries.append(HookOutputEntry(HookOutputEntryKind.STOP, stop_text))
            elif _looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        f"hook returned invalid {event_label} hook JSON output",
                    )
                )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(
            HookOutputEntry(
                HookOutputEntryKind.ERROR,
                "hook process terminated without an exit code",
            )
        )
    else:
        status = HookRunStatus.FAILED
        entries.append(
            HookOutputEntry(
                HookOutputEntryKind.ERROR,
                trimmed_non_empty(stderr) or f"hook exited with code {exit_code}",
            )
        )

    return ParsedCompactHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=_completed_summary(handler, run_result, status, entries),
        ),
        data=CompactHandlerData(
            should_stop=should_stop,
            stop_reason=stop_reason,
        ),
    )


def parse_pre_compact_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedCompactHandler:
    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.PRE_COMPACT:
        raise ValueError(f"expected pre compact hook event, got {event_name}")
    return _parse_compact_completed(handler, run_result, turn_id, "PreCompact")


def parse_post_compact_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedCompactHandler:
    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.POST_COMPACT:
        raise ValueError(f"expected post compact hook event, got {event_name}")
    return _parse_compact_completed(handler, run_result, turn_id, "PostCompact")


class SessionStartSource(str, Enum):
    STARTUP = "startup"
    RESUME = "resume"
    CLEAR = "clear"
    COMPACT = "compact"

    def as_str(self) -> str:
        return self.value


@dataclass(frozen=True)
class StartHookTarget:
    event_name: HookEventName
    source: SessionStartSource | None = None
    turn_id: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None

    @classmethod
    def SessionStart(cls, source: SessionStartSource) -> "StartHookTarget":
        return cls(HookEventName.SESSION_START, source=source)

    @classmethod
    def SubagentStart(cls, turn_id: str, agent_id: str, agent_type: str) -> "StartHookTarget":
        return cls(HookEventName.SUBAGENT_START, turn_id=turn_id, agent_id=agent_id, agent_type=agent_type)

    def matcher_input(self) -> str:
        if self.event_name == HookEventName.SESSION_START:
            if self.source is None:
                raise ValueError("SessionStart target requires source")
            return self.source.as_str()
        if self.event_name == HookEventName.SUBAGENT_START:
            if self.agent_type is None:
                raise ValueError("SubagentStart target requires agent_type")
            return self.agent_type
        raise ValueError(f"unsupported start hook event: {self.event_name}")


@dataclass
class SessionStartRequest:
    session_id: ThreadId | str
    cwd: Path
    transcript_path: Path | None
    model: str
    permission_mode: str
    target: StartHookTarget


@dataclass
class SessionStartOutcome:
    hook_events: list[HookCompletedEvent]
    should_stop: bool
    stop_reason: str | None
    additional_contexts: list[str]


@dataclass(frozen=True)
class SessionStartHandlerData:
    should_stop: bool = False
    stop_reason: str | None = None
    additional_contexts_for_model: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedSessionStartHandler:
    completed: HookCompletedEvent
    data: SessionStartHandlerData
    completion_order: int = 0


def session_start_command_input_json(request: SessionStartRequest) -> tuple[str, str | None]:
    if request.target.event_name == HookEventName.SESSION_START:
        payload = {
            "session_id": str(request.session_id),
            "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
            "cwd": str(request.cwd),
            "hook_event_name": "SessionStart",
            "model": request.model,
            "permission_mode": request.permission_mode,
            "source": request.target.matcher_input(),
        }
        return json.dumps(payload, separators=(",", ":")), None
    if request.target.event_name == HookEventName.SUBAGENT_START:
        if request.target.turn_id is None or request.target.agent_id is None or request.target.agent_type is None:
            raise ValueError("SubagentStart target requires turn_id, agent_id, and agent_type")
        payload = {
            "session_id": str(request.session_id),
            "turn_id": request.target.turn_id,
            "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
            "cwd": str(request.cwd),
            "hook_event_name": "SubagentStart",
            "model": request.model,
            "permission_mode": request.permission_mode,
            "agent_id": request.target.agent_id,
            "agent_type": request.target.agent_type,
        }
        return json.dumps(payload, separators=(",", ":")), request.target.turn_id
    raise ValueError(f"unsupported start hook event: {request.target.event_name}")


def _looks_like_json(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") or stripped.startswith("[")


def _parse_hook_json_output(text: str) -> Mapping[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, Mapping):
        return parsed
    return None


def _completed_summary(
    handler: Any,
    run_result: Any,
    status: HookRunStatus,
    entries: Sequence[HookOutputEntry],
) -> HookRunSummary:
    run = _running_summary(handler)
    return replace(
        run,
        status=status,
        completed_at=int(_field(run_result, "completed_at", _field(run_result, "started_at", run.started_at))),
        duration_ms=int(_field(run_result, "duration_ms", 0)),
        entries=tuple(entries),
    )


def parse_session_start_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedSessionStartHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_stop = False
    stop_reason = None
    additional_contexts_for_model: list[str] = []
    event_name = HookEventName(_field(handler, "event_name"))
    if event_name not in {HookEventName.SESSION_START, HookEventName.SUBAGENT_START}:
        raise ValueError(f"expected start hook event, got {event_name}")

    error = _field(run_result, "error")
    exit_code = _field(run_result, "exit_code")
    stdout = str(_field(run_result, "stdout", ""))
    if error is not None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, str(error)))
    elif exit_code == 0:
        trimmed_stdout = stdout.strip()
        if not trimmed_stdout:
            pass
        else:
            parsed = _parse_hook_json_output(stdout)
            if parsed is not None:
                system_message = parsed.get("systemMessage")
                if isinstance(system_message, str):
                    entries.append(HookOutputEntry(HookOutputEntryKind.WARNING, system_message))
                specific = parsed.get("hookSpecificOutput")
                additional_context = (
                    specific.get("additionalContext")
                    if isinstance(specific, Mapping)
                    else None
                )
                if isinstance(additional_context, str):
                    append_additional_context(
                        entries,
                        additional_contexts_for_model,
                        additional_context,
                    )
                continue_processing = parsed.get("continue", True)
                if event_name == HookEventName.SESSION_START and continue_processing is False:
                    status = HookRunStatus.STOPPED
                    should_stop = True
                    raw_stop_reason = parsed.get("stopReason")
                    stop_reason = raw_stop_reason if isinstance(raw_stop_reason, str) else None
                    if stop_reason is not None:
                        entries.append(HookOutputEntry(HookOutputEntryKind.STOP, stop_reason))
            elif _looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        (
                            "hook returned invalid session start JSON output"
                            if event_name == HookEventName.SESSION_START
                            else "hook returned invalid subagent start JSON output"
                        ),
                    )
                )
            else:
                append_additional_context(
                    entries,
                    additional_contexts_for_model,
                    trimmed_stdout,
                )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    return ParsedSessionStartHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=_completed_summary(handler, run_result, status, entries),
        ),
        data=SessionStartHandlerData(
            should_stop=should_stop,
            stop_reason=stop_reason,
            additional_contexts_for_model=additional_contexts_for_model,
        ),
    )


@dataclass(frozen=True)
class StopHookTarget:
    event_name: HookEventName
    agent_id: str | None = None
    agent_type: str | None = None
    agent_transcript_path: Path | None = None

    @classmethod
    def Stop(cls) -> "StopHookTarget":
        return cls(HookEventName.STOP)

    @classmethod
    def SubagentStop(cls, agent_id: str, agent_type: str, agent_transcript_path: Path | None) -> "StopHookTarget":
        return cls(HookEventName.SUBAGENT_STOP, agent_id, agent_type, agent_transcript_path)

    def matcher_input(self) -> str | None:
        if self.event_name == HookEventName.STOP:
            return None
        if self.event_name == HookEventName.SUBAGENT_STOP:
            return self.agent_type
        raise ValueError(f"expected stop hook event, got {self.event_name}")


@dataclass
class StopRequest:
    session_id: ThreadId | str
    turn_id: str
    cwd: Path
    transcript_path: Path | None
    model: str
    permission_mode: str
    stop_hook_active: bool
    last_assistant_message: str | None
    target: StopHookTarget


@dataclass
class StopOutcome:
    hook_events: list[HookCompletedEvent] = field(default_factory=list)
    should_stop: bool = False
    stop_reason: str | None = None
    should_block: bool = False
    block_reason: str | None = None
    continuation_fragments: list[HookPromptFragment] = field(default_factory=list)


@dataclass(frozen=True)
class StopHandlerData:
    should_stop: bool = False
    stop_reason: str | None = None
    should_block: bool = False
    block_reason: str | None = None
    continuation_fragments: list[HookPromptFragment] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedStopHandler:
    completed: HookCompletedEvent
    data: StopHandlerData
    completion_order: int = 0


def stop_command_input_json(request: StopRequest) -> str:
    if request.target.event_name == HookEventName.STOP:
        payload: dict[str, Any] = {
            "session_id": str(request.session_id),
            "turn_id": request.turn_id,
            "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
            "cwd": str(request.cwd),
            "hook_event_name": "Stop",
            "model": request.model,
            "permission_mode": request.permission_mode,
            "stop_hook_active": request.stop_hook_active,
            "last_assistant_message": request.last_assistant_message,
        }
    elif request.target.event_name == HookEventName.SUBAGENT_STOP:
        payload = {
            "session_id": str(request.session_id),
            "turn_id": request.turn_id,
            "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
            "agent_transcript_path": (
                str(request.target.agent_transcript_path)
                if request.target.agent_transcript_path is not None
                else None
            ),
            "cwd": str(request.cwd),
            "hook_event_name": "SubagentStop",
            "model": request.model,
            "permission_mode": request.permission_mode,
            "stop_hook_active": request.stop_hook_active,
            "agent_id": request.target.agent_id,
            "agent_type": request.target.agent_type,
            "last_assistant_message": request.last_assistant_message,
        }
    else:
        raise ValueError(f"expected stop hook event, got {request.target.event_name}")
    return json.dumps(payload, separators=(",", ":"))


def _stop_hook_label(event_name: HookEventName) -> str:
    if event_name == HookEventName.STOP:
        return "Stop"
    if event_name == HookEventName.SUBAGENT_STOP:
        return "SubagentStop"
    raise ValueError(f"expected stop hook event, got {event_name}")


def _stop_invalid_json_message(event_name: HookEventName) -> str:
    if event_name == HookEventName.STOP:
        return "hook returned invalid stop hook JSON output"
    if event_name == HookEventName.SUBAGENT_STOP:
        return "hook returned invalid subagent stop hook JSON output"
    raise ValueError(f"expected stop hook event, got {event_name}")


def parse_stop_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedStopHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_stop = False
    stop_reason = None
    should_block = False
    block_reason = None
    continuation_prompt = None

    event_name = HookEventName(_field(handler, "event_name"))
    label = _stop_hook_label(event_name)
    error = _field(run_result, "error")
    exit_code = _field(run_result, "exit_code")
    stdout = str(_field(run_result, "stdout", ""))
    stderr = str(_field(run_result, "stderr", ""))

    if error is not None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, str(error)))
    elif exit_code == 0:
        trimmed_stdout = stdout.strip()
        if not trimmed_stdout:
            pass
        else:
            parsed = _parse_hook_json_output(stdout)
            if parsed is not None:
                system_message = parsed.get("systemMessage")
                if isinstance(system_message, str):
                    entries.append(HookOutputEntry(HookOutputEntryKind.WARNING, system_message))

                decision = parsed.get("decision")
                reason = _non_empty_string(parsed.get("reason"))
                invalid_block_reason = None
                parsed_should_block = False
                if decision == "block":
                    if reason is None:
                        invalid_block_reason = (
                            f"{label} hook returned decision:block without a non-empty reason"
                        )
                    else:
                        parsed_should_block = True

                continue_processing = parsed.get("continue", True)
                if continue_processing is False:
                    status = HookRunStatus.STOPPED
                    should_stop = True
                    raw_stop_reason = parsed.get("stopReason")
                    stop_reason = raw_stop_reason if isinstance(raw_stop_reason, str) else None
                    if stop_reason is not None:
                        entries.append(HookOutputEntry(HookOutputEntryKind.STOP, stop_reason))
                elif invalid_block_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_block_reason))
                elif parsed_should_block:
                    status = HookRunStatus.BLOCKED
                    should_block = True
                    block_reason = reason
                    continuation_prompt = reason
                    if reason is not None:
                        entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
            else:
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        _stop_invalid_json_message(event_name),
                    )
                )
    elif exit_code == 2:
        reason = trimmed_non_empty(stderr)
        if reason is not None:
            status = HookRunStatus.BLOCKED
            should_block = True
            block_reason = reason
            continuation_prompt = reason
            entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
        else:
            status = HookRunStatus.FAILED
            entries.append(
                HookOutputEntry(
                    HookOutputEntryKind.ERROR,
                    f"{label} hook exited with code 2 but did not write a continuation prompt to stderr",
                )
            )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    completed = HookCompletedEvent(
        turn_id=turn_id,
        run=_completed_summary(handler, run_result, status, entries),
    )
    continuation_fragments = (
        [HookPromptFragment.from_single_hook(continuation_prompt, completed.run.id)]
        if continuation_prompt is not None
        else []
    )
    return ParsedStopHandler(
        completed=completed,
        data=StopHandlerData(
            should_stop=should_stop,
            stop_reason=stop_reason,
            should_block=should_block,
            block_reason=block_reason,
            continuation_fragments=continuation_fragments,
        ),
    )


def aggregate_stop_results(results: Sequence[StopHandlerData]) -> StopHandlerData:
    should_stop = any(result.should_stop for result in results)
    stop_reason = next((result.stop_reason for result in results if result.stop_reason is not None), None)
    should_block = (not should_stop) and any(result.should_block for result in results)
    block_reason = (
        join_text_chunks([result.block_reason for result in results if result.block_reason is not None])
        if should_block
        else None
    )
    continuation_fragments = (
        [
            fragment
            for result in results
            if result.should_block
            for fragment in result.continuation_fragments
        ]
        if should_block
        else []
    )
    return StopHandlerData(
        should_stop=should_stop,
        stop_reason=stop_reason,
        should_block=should_block,
        block_reason=block_reason,
        continuation_fragments=continuation_fragments,
    )


@dataclass
class UserPromptSubmitRequest:
    session_id: ThreadId | str
    turn_id: str
    subagent: SubagentHookContext | None
    cwd: Path
    transcript_path: Path | None
    model: str
    permission_mode: str
    prompt: str


@dataclass
class UserPromptSubmitOutcome:
    hook_events: list[HookCompletedEvent]
    should_stop: bool
    stop_reason: str | None
    additional_contexts: list[str]


@dataclass(frozen=True)
class UserPromptSubmitHandlerData:
    should_stop: bool = False
    stop_reason: str | None = None
    additional_contexts_for_model: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedUserPromptSubmitHandler:
    completed: HookCompletedEvent
    data: UserPromptSubmitHandlerData
    completion_order: int = 0


def user_prompt_submit_command_input_json(request: UserPromptSubmitRequest) -> str:
    payload: dict[str, Any] = {
        "session_id": str(request.session_id),
        "turn_id": request.turn_id,
        "transcript_path": str(request.transcript_path) if request.transcript_path is not None else None,
        "cwd": str(request.cwd),
        "hook_event_name": "UserPromptSubmit",
        "model": request.model,
        "permission_mode": request.permission_mode,
        "prompt": request.prompt,
    }
    if request.subagent is not None:
        payload["agent_id"] = request.subagent.agent_id
        payload["agent_type"] = request.subagent.agent_type
    return json.dumps(payload, separators=(",", ":"))


def _non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


def parse_user_prompt_submit_completed(
    handler: Any,
    run_result: Any,
    turn_id: str | None,
) -> ParsedUserPromptSubmitHandler:
    entries: list[HookOutputEntry] = []
    status = HookRunStatus.COMPLETED
    should_stop = False
    stop_reason = None
    additional_contexts_for_model: list[str] = []

    event_name = HookEventName(_field(handler, "event_name"))
    if event_name != HookEventName.USER_PROMPT_SUBMIT:
        raise ValueError(f"expected user prompt submit hook event, got {event_name}")

    error = _field(run_result, "error")
    exit_code = _field(run_result, "exit_code")
    stdout = str(_field(run_result, "stdout", ""))
    stderr = str(_field(run_result, "stderr", ""))
    if error is not None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, str(error)))
    elif exit_code == 0:
        trimmed_stdout = stdout.strip()
        if not trimmed_stdout:
            pass
        else:
            parsed = _parse_hook_json_output(stdout)
            if parsed is not None:
                system_message = parsed.get("systemMessage")
                if isinstance(system_message, str):
                    entries.append(HookOutputEntry(HookOutputEntryKind.WARNING, system_message))

                decision = parsed.get("decision")
                reason = _non_empty_string(parsed.get("reason"))
                invalid_block_reason = None
                should_block = False
                if decision == "block":
                    if reason is None:
                        invalid_block_reason = (
                            "UserPromptSubmit hook returned decision:block without a non-empty reason"
                        )
                    else:
                        should_block = True

                specific = parsed.get("hookSpecificOutput")
                additional_context = (
                    specific.get("additionalContext")
                    if isinstance(specific, Mapping)
                    else None
                )
                if invalid_block_reason is None and isinstance(additional_context, str):
                    append_additional_context(
                        entries,
                        additional_contexts_for_model,
                        additional_context,
                    )

                continue_processing = parsed.get("continue", True)
                if continue_processing is False:
                    status = HookRunStatus.STOPPED
                    should_stop = True
                    raw_stop_reason = parsed.get("stopReason")
                    stop_reason = raw_stop_reason if isinstance(raw_stop_reason, str) else None
                    if stop_reason is not None:
                        entries.append(HookOutputEntry(HookOutputEntryKind.STOP, stop_reason))
                elif invalid_block_reason is not None:
                    status = HookRunStatus.FAILED
                    entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, invalid_block_reason))
                elif should_block:
                    status = HookRunStatus.BLOCKED
                    should_stop = True
                    stop_reason = reason
                    if reason is not None:
                        entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
            elif _looks_like_json(stdout):
                status = HookRunStatus.FAILED
                entries.append(
                    HookOutputEntry(
                        HookOutputEntryKind.ERROR,
                        "hook returned invalid user prompt submit JSON output",
                    )
                )
            else:
                append_additional_context(
                    entries,
                    additional_contexts_for_model,
                    trimmed_stdout,
                )
    elif exit_code == 2:
        reason = trimmed_non_empty(stderr)
        if reason is not None:
            status = HookRunStatus.BLOCKED
            should_stop = True
            stop_reason = reason
            entries.append(HookOutputEntry(HookOutputEntryKind.FEEDBACK, reason))
        else:
            status = HookRunStatus.FAILED
            entries.append(
                HookOutputEntry(
                    HookOutputEntryKind.ERROR,
                    (
                        "UserPromptSubmit hook exited with code 2 but did not write a blocking "
                        "reason to stderr"
                    ),
                )
            )
    elif exit_code is None:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, "hook exited without a status code"))
    else:
        status = HookRunStatus.FAILED
        entries.append(HookOutputEntry(HookOutputEntryKind.ERROR, f"hook exited with code {exit_code}"))

    return ParsedUserPromptSubmitHandler(
        completed=HookCompletedEvent(
            turn_id=turn_id,
            run=_completed_summary(handler, run_result, status, entries),
        ),
        data=UserPromptSubmitHandlerData(
            should_stop=should_stop,
            stop_reason=stop_reason,
            additional_contexts_for_model=additional_contexts_for_model,
        ),
    )


@dataclass
class HookListEntry:
    key: str
    event_name: HookEventName
    handler_type: HookHandlerType
    matcher: str | None
    command: str | None
    timeout_sec: int
    status_message: str | None
    source_path: Path
    source: HookSource
    plugin_id: str | None
    display_order: int
    enabled: bool
    is_managed: bool
    current_hash: str
    trust_status: HookTrustStatus


@dataclass
class HooksConfig:
    legacy_notify_argv: list[str] | None = None
    feature_enabled: bool = False
    bypass_hook_trust: bool = False
    config_layer_stack: Any | None = None
    plugin_hook_sources: list[Any] = field(default_factory=list)
    plugin_hook_load_warnings: list[str] = field(default_factory=list)
    shell_program: str | None = None
    shell_args: list[str] = field(default_factory=list)


@dataclass
class HookListOutcome:
    hooks: list[HookListEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    handlers: list[ConfiguredHandler] = field(default_factory=list)
    hook_entries: list[HookListEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _HookHandlerSource:
    path: Path
    key_source: str
    source: HookSource
    is_managed: bool
    bypass_hook_trust: bool
    hook_states: Mapping[str, HookStateToml]
    env: Mapping[str, str] = field(default_factory=dict)
    plugin_id: str | None = None


@dataclass(frozen=True)
class _HookDiscoveryPolicy:
    allow_managed_hooks_only: bool
    bypass_hook_trust: bool

    def allows(self, source: _HookHandlerSource) -> bool:
        return (not self.allow_managed_hooks_only) or source.is_managed


@dataclass(frozen=True)
class _CommandShell:
    program: str
    args: list[str]


class _ClaudeHooksEngine:
    def __init__(
        self,
        handlers: Sequence[ConfiguredHandler] = (),
        warnings: Sequence[str] = (),
        shell: _CommandShell | CommandShell | None = None,
        output_spiller: HookOutputSpiller | None = None,
    ) -> None:
        self.handlers = list(handlers)
        self._warnings = list(warnings)
        raw_shell = shell or _CommandShell("", [])
        self.shell = CommandShell(
            program=str(_field(raw_shell, "program", "")),
            args=list(_field(raw_shell, "args", [])),
        )
        self.output_spiller = output_spiller or HookOutputSpiller.new()

    @classmethod
    def new(
        cls,
        enabled: bool,
        bypass_hook_trust: bool,
        config_layer_stack: Any | None,
        plugin_hook_sources: Sequence[Any],
        plugin_hook_load_warnings: Sequence[str],
        _shell: _CommandShell,
    ) -> "_ClaudeHooksEngine":
        if not enabled:
            return cls(shell=_shell)
        generated_hook_schemas()
        discovered = discover_handlers(
            config_layer_stack,
            plugin_hook_sources,
            plugin_hook_load_warnings,
            bypass_hook_trust,
        )
        return cls(discovered.handlers, discovered.warnings, shell=_shell)

    def warnings(self) -> list[str]:
        return list(self._warnings)

    def preview_session_start(self, request: SessionStartRequest) -> list[HookRunSummary]:
        return [
            running_summary(handler)
            for handler in select_handlers(
                self.handlers,
                request.target.event_name,
                request.target.matcher_input(),
            )
        ]

    def preview_pre_tool_use(self, request: PreToolUseRequest) -> list[HookRunSummary]:
        return [
            hook_run_for_tool_use(running_summary(handler), request.tool_use_id)
            for handler in select_handlers_for_matcher_inputs(
                self.handlers,
                HookEventName.PRE_TOOL_USE,
                matcher_inputs(request.tool_name, request.matcher_aliases),
            )
        ]

    def preview_permission_request(self, request: PermissionRequestRequest) -> list[HookRunSummary]:
        summaries = [
            running_summary(handler)
            for handler in select_handlers_for_matcher_inputs(
                self.handlers,
                HookEventName.PERMISSION_REQUEST,
                matcher_inputs(request.tool_name, request.matcher_aliases),
            )
        ]
        if request.run_id_suffix is None:
            return summaries
        return [hook_run_for_tool_use(summary, request.run_id_suffix) for summary in summaries]

    def preview_post_tool_use(self, request: PostToolUseRequest) -> list[HookRunSummary]:
        return [
            hook_run_for_tool_use(running_summary(handler), request.tool_use_id)
            for handler in select_handlers_for_matcher_inputs(
                self.handlers,
                HookEventName.POST_TOOL_USE,
                matcher_inputs(request.tool_name, request.matcher_aliases),
            )
        ]

    def preview_pre_compact(self, request: PreCompactRequest) -> list[HookRunSummary]:
        return [
            running_summary(handler)
            for handler in select_handlers(
                self.handlers,
                HookEventName.PRE_COMPACT,
                request.trigger,
            )
        ]

    def preview_post_compact(self, request: PostCompactRequest) -> list[HookRunSummary]:
        return [
            running_summary(handler)
            for handler in select_handlers(
                self.handlers,
                HookEventName.POST_COMPACT,
                request.trigger,
            )
        ]

    def preview_user_prompt_submit(self, _request: UserPromptSubmitRequest) -> list[HookRunSummary]:
        return [
            running_summary(handler)
            for handler in select_handlers(self.handlers, HookEventName.USER_PROMPT_SUBMIT, None)
        ]

    def preview_stop(self, request: StopRequest) -> list[HookRunSummary]:
        return [
            running_summary(handler)
            for handler in select_handlers(
                self.handlers,
                request.target.event_name,
                request.target.matcher_input(),
            )
        ]

    async def run_session_start(
        self,
        request: SessionStartRequest,
        turn_id: str | None,
    ) -> SessionStartOutcome:
        matched = select_handlers(
            self.handlers,
            request.target.event_name,
            request.target.matcher_input(),
        )
        if not matched:
            return SessionStartOutcome([], False, None, [])
        input_json, target_turn_id = session_start_command_input_json(request)
        run_turn_id = target_turn_id if target_turn_id is not None else turn_id
        results = await execute_handlers(
            self.shell,
            matched,
            input_json,
            request.cwd,
            run_turn_id,
            parse_session_start_completed,
        )
        additional_contexts = flatten_additional_contexts(
            [result.data.additional_contexts_for_model for result in results]
        )
        return SessionStartOutcome(
            [result.completed for result in results],
            any(result.data.should_stop for result in results),
            next((result.data.stop_reason for result in results if result.data.stop_reason is not None), None),
            await self.output_spiller.maybe_spill_texts(request.session_id, additional_contexts),
        )

    async def run_pre_tool_use(self, request: PreToolUseRequest) -> PreToolUseOutcome:
        matched = select_handlers_for_matcher_inputs(
            self.handlers,
            HookEventName.PRE_TOOL_USE,
            matcher_inputs(request.tool_name, request.matcher_aliases),
        )
        if not matched:
            return PreToolUseOutcome([], False, None, [], None)
        results = await execute_handlers(
            self.shell,
            matched,
            pre_tool_use_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_pre_tool_use_completed,
        )
        data = [result.data for result in results]
        additional_contexts = flatten_additional_contexts(
            [item.additional_contexts_for_model for item in data]
        )
        return PreToolUseOutcome(
            [hook_completed_for_tool_use(result.completed, request.tool_use_id) for result in results],
            any(item.should_block for item in data),
            next((item.block_reason for item in data if item.block_reason is not None), None),
            await self.output_spiller.maybe_spill_texts(request.session_id, additional_contexts),
            latest_pre_tool_use_updated_input(results),
        )

    async def run_permission_request(
        self,
        request: PermissionRequestRequest,
    ) -> PermissionRequestOutcome:
        matched = select_handlers_for_matcher_inputs(
            self.handlers,
            HookEventName.PERMISSION_REQUEST,
            matcher_inputs(request.tool_name, request.matcher_aliases),
        )
        if not matched:
            return PermissionRequestOutcome([], None)
        results = await execute_handlers(
            self.shell,
            matched,
            permission_request_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_permission_request_completed,
        )
        hook_events = [result.completed for result in results]
        if request.run_id_suffix is not None:
            hook_events = [
                hook_completed_for_tool_use(event, request.run_id_suffix)
                for event in hook_events
            ]
        return PermissionRequestOutcome(
            hook_events,
            resolve_permission_request_decision(
                [result.data.decision for result in results if result.data.decision is not None]
            ),
        )

    async def run_post_tool_use(self, request: PostToolUseRequest) -> PostToolUseOutcome:
        matched = select_handlers_for_matcher_inputs(
            self.handlers,
            HookEventName.POST_TOOL_USE,
            matcher_inputs(request.tool_name, request.matcher_aliases),
        )
        if not matched:
            return PostToolUseOutcome([], False, None, [], None)
        results = await execute_handlers(
            self.shell,
            matched,
            post_tool_use_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_post_tool_use_completed,
        )
        data = [result.data for result in results]
        additional_contexts = flatten_additional_contexts(
            [item.additional_contexts_for_model for item in data]
        )
        feedback = post_tool_use_feedback_message(data)
        return PostToolUseOutcome(
            [hook_completed_for_tool_use(result.completed, request.tool_use_id) for result in results],
            any(item.should_stop for item in data),
            next((item.stop_reason for item in data if item.stop_reason is not None), None),
            await self.output_spiller.maybe_spill_texts(request.session_id, additional_contexts),
            (
                await self.output_spiller.maybe_spill_text(request.session_id, feedback)
                if feedback is not None
                else None
            ),
        )

    async def run_pre_compact(self, request: PreCompactRequest) -> PreCompactOutcome:
        matched = select_handlers(self.handlers, HookEventName.PRE_COMPACT, request.trigger)
        if not matched:
            return PreCompactOutcome([], False, None)
        results = await execute_handlers(
            self.shell,
            matched,
            pre_compact_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_pre_compact_completed,
        )
        return PreCompactOutcome(
            [result.completed for result in results],
            any(result.data.should_stop for result in results),
            next((result.data.stop_reason for result in results if result.data.stop_reason is not None), None),
        )

    async def run_post_compact(self, request: PostCompactRequest) -> StatelessHookOutcome:
        matched = select_handlers(self.handlers, HookEventName.POST_COMPACT, request.trigger)
        if not matched:
            return StatelessHookOutcome([], False, None)
        results = await execute_handlers(
            self.shell,
            matched,
            post_compact_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_post_compact_completed,
        )
        return StatelessHookOutcome(
            [result.completed for result in results],
            any(result.data.should_stop for result in results),
            next((result.data.stop_reason for result in results if result.data.stop_reason is not None), None),
        )

    async def run_user_prompt_submit(
        self,
        request: UserPromptSubmitRequest,
    ) -> UserPromptSubmitOutcome:
        matched = select_handlers(self.handlers, HookEventName.USER_PROMPT_SUBMIT, None)
        if not matched:
            return UserPromptSubmitOutcome([], False, None, [])
        results = await execute_handlers(
            self.shell,
            matched,
            user_prompt_submit_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_user_prompt_submit_completed,
        )
        additional_contexts = flatten_additional_contexts(
            [result.data.additional_contexts_for_model for result in results]
        )
        return UserPromptSubmitOutcome(
            [result.completed for result in results],
            any(result.data.should_stop for result in results),
            next((result.data.stop_reason for result in results if result.data.stop_reason is not None), None),
            await self.output_spiller.maybe_spill_texts(request.session_id, additional_contexts),
        )

    async def run_stop(self, request: StopRequest) -> StopOutcome:
        matched = select_handlers(
            self.handlers,
            request.target.event_name,
            request.target.matcher_input(),
        )
        if not matched:
            return StopOutcome()
        results = await execute_handlers(
            self.shell,
            matched,
            stop_command_input_json(request),
            request.cwd,
            request.turn_id,
            parse_stop_completed,
        )
        aggregate = aggregate_stop_results([result.data for result in results])
        return StopOutcome(
            hook_events=[result.completed for result in results],
            should_stop=aggregate.should_stop,
            stop_reason=aggregate.stop_reason,
            should_block=aggregate.should_block,
            block_reason=aggregate.block_reason,
            continuation_fragments=await self.output_spiller.maybe_spill_prompt_fragments(
                request.session_id,
                aggregate.continuation_fragments,
            ),
        )


class Hooks:
    def __init__(self, config: HooksConfig | None = None) -> None:
        self.config = config or HooksConfig()
        self.after_agent = []
        if self.config.legacy_notify_argv and self.config.legacy_notify_argv[0]:
            self.after_agent.append(notify_hook(self.config.legacy_notify_argv))
        self.engine = _ClaudeHooksEngine.new(
            self.config.feature_enabled,
            self.config.bypass_hook_trust,
            self.config.config_layer_stack,
            self.config.plugin_hook_sources,
            self.config.plugin_hook_load_warnings,
            _CommandShell(
                self.config.shell_program or "",
                list(self.config.shell_args),
            ),
        )

    @classmethod
    def new(cls, config: HooksConfig) -> "Hooks":
        return cls(config)

    def startup_warnings(self) -> list[str]:
        return self.engine.warnings()

    async def dispatch(self, hook_payload: HookPayload) -> list[HookResponse]:
        outcomes: list[HookResponse] = []
        for hook in self.after_agent:
            outcome = await hook.execute(hook_payload)
            outcomes.append(outcome)
            if outcome.result.should_abort_operation():
                break
        return outcomes

    def preview_session_start(self, request: SessionStartRequest) -> list[Any]:
        return self.engine.preview_session_start(request)

    def preview_pre_tool_use(self, request: PreToolUseRequest) -> list[Any]:
        return self.engine.preview_pre_tool_use(request)

    def preview_permission_request(self, request: PermissionRequestRequest) -> list[Any]:
        return self.engine.preview_permission_request(request)

    def preview_post_tool_use(self, request: PostToolUseRequest) -> list[Any]:
        return self.engine.preview_post_tool_use(request)

    def preview_pre_compact(self, request: PreCompactRequest) -> list[Any]:
        return self.engine.preview_pre_compact(request)

    def preview_post_compact(self, request: PostCompactRequest) -> list[Any]:
        return self.engine.preview_post_compact(request)

    def preview_user_prompt_submit(self, request: UserPromptSubmitRequest) -> list[Any]:
        return self.engine.preview_user_prompt_submit(request)

    def preview_stop(self, request: StopRequest) -> list[Any]:
        return self.engine.preview_stop(request)

    async def run_session_start(self, request: SessionStartRequest, turn_id: str | None) -> SessionStartOutcome:
        return await self.engine.run_session_start(request, turn_id)

    async def run_pre_tool_use(self, request: PreToolUseRequest) -> PreToolUseOutcome:
        return await self.engine.run_pre_tool_use(request)

    async def run_permission_request(self, request: PermissionRequestRequest) -> PermissionRequestOutcome:
        return await self.engine.run_permission_request(request)

    async def run_post_tool_use(self, request: PostToolUseRequest) -> PostToolUseOutcome:
        return await self.engine.run_post_tool_use(request)

    async def run_pre_compact(self, request: PreCompactRequest) -> PreCompactOutcome:
        return await self.engine.run_pre_compact(request)

    async def run_post_compact(self, request: PostCompactRequest) -> StatelessHookOutcome:
        return await self.engine.run_post_compact(request)

    async def run_user_prompt_submit(self, request: UserPromptSubmitRequest) -> UserPromptSubmitOutcome:
        return await self.engine.run_user_prompt_submit(request)

    async def run_stop(self, request: StopRequest) -> StopOutcome:
        return await self.engine.run_stop(request)


def _source_type(source: Any) -> str:
    return str(_field(source, "type", source))


def _synthetic_layer_path(path: str) -> Path:
    if os.name == "nt":
        return Path("C:/") / path.replace("\\", "/")
    return Path("/") / path


def _config_toml_source_path(layer: Any) -> Path:
    name = _field(layer, "name")
    name_type = _source_type(name)
    file = _field(name, "file")
    if name_type in {"system", "user", "legacy_managed_config_toml_from_file"} and file is not None:
        return Path(file)
    if name_type == "project":
        folder = _call_or_field(layer, "hooks_config_folder")
        if folder is None:
            folder = _field(name, "dot_codex_folder", ".")
        return Path(folder) / "config.toml"
    if name_type == "session_flags":
        return _synthetic_layer_path("<session-flags>/config.toml")
    if name_type == "mdm":
        return _synthetic_layer_path(
            f"<mdm:{_field(name, 'domain', '')}:{_field(name, 'key', '')}>/config.toml"
        )
    if name_type == "legacy_managed_config_toml_from_mdm":
        return _synthetic_layer_path("<legacy-managed-config.toml-mdm>/managed_config.toml")
    return _synthetic_layer_path(f"<{name_type}>/config.toml")


def _call_or_field(source: Any, name: str, default: Any = None) -> Any:
    value = _field(source, name, default)
    if callable(value):
        return value()
    return value


def _hook_metadata_for_config_layer_source(source: Any) -> tuple[HookSource, bool]:
    source_type = _source_type(source)
    if source_type == "system":
        return HookSource.SYSTEM, True
    if source_type == "user":
        return HookSource.USER, False
    if source_type == "project":
        return HookSource.PROJECT, False
    if source_type == "mdm":
        return HookSource.MDM, True
    if source_type == "session_flags":
        return HookSource.SESSION_FLAGS, False
    if source_type == "legacy_managed_config_toml_from_file":
        return HookSource.LEGACY_MANAGED_CONFIG_FILE, True
    if source_type == "legacy_managed_config_toml_from_mdm":
        return HookSource.LEGACY_MANAGED_CONFIG_MDM, True
    return HookSource.UNKNOWN, False


def _hook_source_for_requirement_source(source: Any | None) -> HookSource:
    source_type = _source_type(source) if source is not None else "unknown"
    if source_type == "mdm_managed_preferences":
        return HookSource.MDM
    if source_type == "system_requirements_toml":
        return HookSource.SYSTEM
    if source_type == "legacy_managed_config_toml_from_file":
        return HookSource.LEGACY_MANAGED_CONFIG_FILE
    if source_type == "legacy_managed_config_toml_from_mdm":
        return HookSource.LEGACY_MANAGED_CONFIG_MDM
    if source_type == "cloud_requirements":
        return HookSource.CLOUD_REQUIREMENTS
    return HookSource.UNKNOWN


def _load_hooks_json(
    config_folder: Path | str | None,
    warnings: list[str],
) -> tuple[Path, HookEventsToml] | None:
    if config_folder is None:
        return None
    source_path = Path(config_folder) / "hooks.json"
    if not source_path.is_file():
        return None
    try:
        contents = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(f"failed to read hooks config {source_path}: {exc}")
        return None
    try:
        parsed_json = json.loads(contents)
        parsed = HooksFile.from_mapping(parsed_json)
    except Exception as exc:
        warnings.append(f"failed to parse hooks config {source_path}: {exc}")
        return None
    if parsed.hooks.is_empty():
        return None
    return source_path, parsed.hooks


def _load_toml_hooks_from_layer(
    layer: Any,
    warnings: list[str],
) -> tuple[Path, HookEventsToml] | None:
    source_path = _config_toml_source_path(layer)
    config = _field(layer, "config", {})
    hook_value = config.get("hooks") if isinstance(config, Mapping) else _field(config, "hooks")
    if hook_value is None:
        return None
    try:
        parsed = HookEventsToml.from_mapping(hook_value)
    except Exception as exc:
        warnings.append(f"failed to parse TOML hooks in {source_path}: {exc}")
        return None
    if parsed.is_empty():
        return None
    return source_path, parsed


def _normalized_hook_identity_mapping(
    event_name: HookEventName,
    matcher: str | None,
    group: MatcherGroup,
    normalized_handler: HookHandlerConfig,
) -> dict[str, Any]:
    group_mapping = group.to_mapping()
    if matcher is None:
        group_mapping.pop("matcher", None)
    else:
        group_mapping["matcher"] = matcher
    group_mapping["hooks"] = [normalized_handler.to_mapping()]
    return {
        "event_name": hook_event_key_label(event_name),
        **group_mapping,
    }


def _command_hook_hash(
    event_name: HookEventName,
    matcher: str | None,
    group: MatcherGroup,
    normalized_handler: HookHandlerConfig,
) -> str:
    return version_for_toml(
        _normalized_hook_identity_mapping(
            event_name,
            matcher,
            group,
            normalized_handler,
        )
    )


def _hook_trust_status(
    is_managed: bool,
    current_hash: str,
    trusted_hash: str | None,
) -> HookTrustStatus:
    if is_managed:
        return HookTrustStatus.MANAGED
    if trusted_hash == current_hash:
        return HookTrustStatus.TRUSTED
    if trusted_hash is not None:
        return HookTrustStatus.MODIFIED
    return HookTrustStatus.UNTRUSTED


def _hook_enabled(is_managed: bool, state: HookStateToml | None) -> bool:
    return is_managed or (None if state is None else state.enabled) is not False


def _hook_trusted_hash(is_managed: bool, state: HookStateToml | None) -> str | None:
    if is_managed or state is None:
        return None
    return state.trusted_hash


def _append_matcher_groups(
    handlers: list[ConfiguredHandler],
    hook_entries: list[HookListEntry],
    warnings: list[str],
    display_order: list[int],
    source: _HookHandlerSource,
    event_name: HookEventName | str,
    groups: Sequence[MatcherGroup],
) -> None:
    event = HookEventName(event_name)
    for group_index, group in enumerate(groups):
        matcher = matcher_pattern_for_event(event, group.matcher)
        if matcher is not None:
            try:
                validate_matcher_pattern(matcher)
            except re.error as exc:
                warnings.append(f"invalid matcher {matcher!r} in {source.path}: {exc}")
                continue
        for handler_index, handler in enumerate(group.hooks):
            if handler.type == "command":
                command = handler.command or ""
                if os.name == "nt" and handler.command_windows is not None:
                    command = handler.command_windows
                if handler.async_:
                    warnings.append(
                        f"skipping async hook in {source.path}: async hooks are not supported yet"
                    )
                    continue
                if command.strip() == "":
                    warnings.append(f"skipping empty hook command in {source.path}")
                    continue
                timeout_sec = max(handler.timeout_sec or 600, 1)
                normalized_handler = HookHandlerConfig.command_handler(
                    command,
                    timeout_sec=timeout_sec,
                    async_=handler.async_,
                    status_message=handler.status_message,
                )
                current_hash = _command_hook_hash(
                    event,
                    matcher,
                    group,
                    normalized_handler,
                )
                for key, value in source.env.items():
                    command = command.replace(f"${{{key}}}", value)
                key = hook_key(source.key_source, event, group_index, handler_index)
                state = source.hook_states.get(key)
                enabled = _hook_enabled(source.is_managed, state)
                trust_status = _hook_trust_status(
                    source.is_managed,
                    current_hash,
                    _hook_trusted_hash(source.is_managed, state),
                )
                entry = HookListEntry(
                    key=key,
                    event_name=event,
                    handler_type=HookHandlerType.COMMAND,
                    matcher=matcher,
                    command=command,
                    timeout_sec=timeout_sec,
                    status_message=handler.status_message,
                    source_path=source.path,
                    source=source.source,
                    plugin_id=source.plugin_id,
                    display_order=display_order[0],
                    enabled=enabled,
                    is_managed=source.is_managed,
                    current_hash=current_hash,
                    trust_status=trust_status,
                )
                hook_entries.append(entry)
                if enabled and (
                    source.bypass_hook_trust
                    or trust_status in {HookTrustStatus.MANAGED, HookTrustStatus.TRUSTED}
                ):
                    handlers.append(
                        ConfiguredHandler(
                            event_name=event,
                            matcher=matcher,
                            command=command,
                            timeout_sec=timeout_sec,
                            status_message=handler.status_message,
                            source_path=source.path,
                            source=source.source,
                            display_order=display_order[0],
                            env=dict(source.env),
                        )
                    )
                display_order[0] += 1
            elif handler.type == "prompt":
                warnings.append(
                    f"skipping prompt hook in {source.path}: prompt hooks are not supported yet"
                )
            elif handler.type == "agent":
                warnings.append(
                    f"skipping agent hook in {source.path}: agent hooks are not supported yet"
                )


def _append_hook_events(
    handlers: list[ConfiguredHandler],
    hook_entries: list[HookListEntry],
    warnings: list[str],
    display_order: list[int],
    source: _HookHandlerSource,
    hook_events: HookEventsToml,
    policy: _HookDiscoveryPolicy,
) -> None:
    if not policy.allows(source):
        return
    for event_name, groups in hook_events.into_matcher_groups():
        _append_matcher_groups(
            handlers,
            hook_entries,
            warnings,
            display_order,
            source,
            event_name,
            groups,
        )


def _append_plugin_hook_sources(
    handlers: list[ConfiguredHandler],
    hook_entries: list[HookListEntry],
    warnings: list[str],
    display_order: list[int],
    plugin_hook_sources: Sequence[Any],
    hook_states: Mapping[str, HookStateToml],
    policy: _HookDiscoveryPolicy,
) -> None:
    for plugin_source in plugin_hook_sources:
        plugin_root = Path(_field(plugin_source, "plugin_root", ""))
        plugin_data_root = Path(_field(plugin_source, "plugin_data_root", ""))
        plugin_id = _plugin_key(_field(plugin_source, "plugin_id", ""))
        source_relative_path = str(_field(plugin_source, "source_relative_path", ""))
        hooks = _field(plugin_source, "hooks", HookEventsToml())
        if isinstance(hooks, Mapping):
            hooks = HookEventsToml.from_mapping(hooks)
        env = {
            "PLUGIN_ROOT": str(plugin_root),
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "PLUGIN_DATA": str(plugin_data_root),
            "CLAUDE_PLUGIN_DATA": str(plugin_data_root),
        }
        _append_hook_events(
            handlers,
            hook_entries,
            warnings,
            display_order,
            _HookHandlerSource(
                path=Path(_field(plugin_source, "source_path", plugin_root / source_relative_path)),
                key_source=f"{plugin_id}:{source_relative_path}",
                source=HookSource.PLUGIN,
                is_managed=False,
                bypass_hook_trust=policy.bypass_hook_trust,
                hook_states=hook_states,
                env=env,
                plugin_id=plugin_id,
            ),
            hooks,
            policy,
        )


def _requirements_value(config_layer_stack: Any | None) -> Any | None:
    if config_layer_stack is None:
        return None
    requirements = _field(config_layer_stack, "requirements", None)
    if callable(requirements):
        return requirements()
    return requirements


def _allow_managed_hooks_only(config_layer_stack: Any | None) -> bool:
    requirements = _requirements_value(config_layer_stack)
    managed_only = _field(requirements, "allow_managed_hooks_only", None)
    value = _field(managed_only, "value", managed_only)
    return bool(value) if value is not None else False


def discover_handlers(
    config_layer_stack: Any | None,
    plugin_hook_sources: Sequence[Any],
    plugin_hook_load_warnings: Sequence[str],
    bypass_hook_trust: bool,
) -> DiscoveryResult:
    handlers: list[ConfiguredHandler] = []
    hook_entries: list[HookListEntry] = []
    warnings = list(plugin_hook_load_warnings)
    display_order = [0]
    hook_states = hook_states_from_stack(config_layer_stack)
    policy = _HookDiscoveryPolicy(
        allow_managed_hooks_only=_allow_managed_hooks_only(config_layer_stack),
        bypass_hook_trust=bypass_hook_trust,
    )

    if config_layer_stack is not None:
        if hasattr(config_layer_stack, "get_layers"):
            layers = config_layer_stack.get_layers(
                ConfigLayerStackOrdering.LOWEST_PRECEDENCE_FIRST,
                False,
            )
        elif isinstance(config_layer_stack, Sequence):
            layers = config_layer_stack
        else:
            layers = []
        for layer in layers:
            hook_source, is_managed = _hook_metadata_for_config_layer_source(_field(layer, "name"))
            source_path = _config_toml_source_path(layer)
            if not policy.allows(
                _HookHandlerSource(
                    path=source_path,
                    key_source=str(source_path),
                    source=hook_source,
                    is_managed=is_managed,
                    bypass_hook_trust=False,
                    hook_states=hook_states,
                )
            ):
                continue
            json_hooks = _load_hooks_json(_call_or_field(layer, "hooks_config_folder"), warnings)
            toml_hooks = _load_toml_hooks_from_layer(layer, warnings)
            if (
                json_hooks is not None
                and toml_hooks is not None
                and not json_hooks[1].is_empty()
                and not toml_hooks[1].is_empty()
            ):
                warnings.append(
                    "loading hooks from both "
                    f"{json_hooks[0]} and {toml_hooks[0]}; "
                    "prefer a single representation for this layer"
                )
            for source_path, hook_events in (item for item in (json_hooks, toml_hooks) if item is not None):
                _append_hook_events(
                    handlers,
                    hook_entries,
                    warnings,
                    display_order,
                    _HookHandlerSource(
                        path=source_path,
                        key_source=str(source_path),
                        source=hook_source,
                        is_managed=is_managed,
                        bypass_hook_trust=policy.bypass_hook_trust,
                        hook_states=hook_states,
                    ),
                    hook_events,
                    policy,
                )

    _append_plugin_hook_sources(
        handlers,
        hook_entries,
        warnings,
        display_order,
        plugin_hook_sources,
        hook_states,
        policy,
    )
    return DiscoveryResult(handlers, hook_entries, warnings)


def _discover_handlers(config: HooksConfig) -> HookListOutcome:
    discovered = discover_handlers(
        config.config_layer_stack,
        config.plugin_hook_sources,
        config.plugin_hook_load_warnings,
        config.bypass_hook_trust,
    )
    return HookListOutcome(discovered.hook_entries, discovered.warnings)



def list_hooks(config: HooksConfig) -> HookListOutcome:
    if not config.feature_enabled:
        return HookListOutcome()
    return _discover_handlers(config)


def hook_states_from_stack(config_layer_stack: Any | None) -> dict[str, HookStateToml]:
    if config_layer_stack is None:
        return {}
    if hasattr(config_layer_stack, "get_layers"):
        layers = config_layer_stack.get_layers(
            ConfigLayerStackOrdering.LOWEST_PRECEDENCE_FIRST,
            True,
        )
    elif isinstance(config_layer_stack, Sequence):
        layers = config_layer_stack
    else:
        return {}

    states: dict[str, HookStateToml] = {}
    for layer in layers:
        name = _field(layer, "name")
        name_type = _field(name, "type", name)
        if name_type not in ("user", "session_flags"):
            continue
        config = _field(layer, "config", {})
        hooks = _field(config, "hooks", {}) if not isinstance(config, Mapping) else config.get("hooks", {})
        state_by_key = _field(hooks, "state", {}) if not isinstance(hooks, Mapping) else hooks.get("state", {})
        if not isinstance(state_by_key, Mapping):
            continue
        for key, state in state_by_key.items():
            key = str(key).strip()
            if not key:
                continue
            try:
                parsed = state if isinstance(state, HookStateToml) else HookStateToml.from_mapping(state)
            except (TypeError, ValueError):
                continue
            effective = states.get(key, HookStateToml())
            states[key] = HookStateToml(
                enabled=parsed.enabled if parsed.enabled is not None else effective.enabled,
                trusted_hash=(
                    parsed.trusted_hash
                    if parsed.trusted_hash is not None
                    else effective.trusted_hash
                ),
            )
    return states


GENERATED_SCHEMA_DIR = "generated"
POST_TOOL_USE_INPUT_FIXTURE = "post-tool-use.command.input.schema.json"
POST_TOOL_USE_OUTPUT_FIXTURE = "post-tool-use.command.output.schema.json"
PERMISSION_REQUEST_INPUT_FIXTURE = "permission-request.command.input.schema.json"
PERMISSION_REQUEST_OUTPUT_FIXTURE = "permission-request.command.output.schema.json"
POST_COMPACT_INPUT_FIXTURE = "post-compact.command.input.schema.json"
POST_COMPACT_OUTPUT_FIXTURE = "post-compact.command.output.schema.json"
PRE_TOOL_USE_INPUT_FIXTURE = "pre-tool-use.command.input.schema.json"
PRE_TOOL_USE_OUTPUT_FIXTURE = "pre-tool-use.command.output.schema.json"
PRE_COMPACT_INPUT_FIXTURE = "pre-compact.command.input.schema.json"
PRE_COMPACT_OUTPUT_FIXTURE = "pre-compact.command.output.schema.json"
SESSION_START_INPUT_FIXTURE = "session-start.command.input.schema.json"
SESSION_START_OUTPUT_FIXTURE = "session-start.command.output.schema.json"
USER_PROMPT_SUBMIT_INPUT_FIXTURE = "user-prompt-submit.command.input.schema.json"
USER_PROMPT_SUBMIT_OUTPUT_FIXTURE = "user-prompt-submit.command.output.schema.json"
SUBAGENT_START_INPUT_FIXTURE = "subagent-start.command.input.schema.json"
SUBAGENT_START_OUTPUT_FIXTURE = "subagent-start.command.output.schema.json"
SUBAGENT_STOP_INPUT_FIXTURE = "subagent-stop.command.input.schema.json"
SUBAGENT_STOP_OUTPUT_FIXTURE = "subagent-stop.command.output.schema.json"
STOP_INPUT_FIXTURE = "stop.command.input.schema.json"
STOP_OUTPUT_FIXTURE = "stop.command.output.schema.json"

SCHEMA_FIXTURE_NAMES = (
    POST_TOOL_USE_INPUT_FIXTURE,
    POST_TOOL_USE_OUTPUT_FIXTURE,
    PERMISSION_REQUEST_INPUT_FIXTURE,
    PERMISSION_REQUEST_OUTPUT_FIXTURE,
    POST_COMPACT_INPUT_FIXTURE,
    POST_COMPACT_OUTPUT_FIXTURE,
    PRE_COMPACT_INPUT_FIXTURE,
    PRE_COMPACT_OUTPUT_FIXTURE,
    PRE_TOOL_USE_INPUT_FIXTURE,
    PRE_TOOL_USE_OUTPUT_FIXTURE,
    SESSION_START_INPUT_FIXTURE,
    SESSION_START_OUTPUT_FIXTURE,
    USER_PROMPT_SUBMIT_INPUT_FIXTURE,
    USER_PROMPT_SUBMIT_OUTPUT_FIXTURE,
    SUBAGENT_START_INPUT_FIXTURE,
    SUBAGENT_START_OUTPUT_FIXTURE,
    SUBAGENT_STOP_INPUT_FIXTURE,
    SUBAGENT_STOP_OUTPUT_FIXTURE,
    STOP_INPUT_FIXTURE,
    STOP_OUTPUT_FIXTURE,
)

HOOK_EVENT_NAME_WIRE_VALUES = (
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SessionStart",
    "UserPromptSubmit",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)
PERMISSION_MODE_SCHEMA_VALUES = (
    "default",
    "acceptEdits",
    "plan",
    "dontAsk",
    "bypassPermissions",
)
SESSION_START_SOURCE_SCHEMA_VALUES = ("startup", "resume", "clear", "compact")
COMPACTION_TRIGGER_SCHEMA_VALUES = ("manual", "auto")


@dataclass(frozen=True)
class SubagentCommandInputFields:
    agent_id: str | None = None
    agent_type: str | None = None

    @classmethod
    def from_context(
        cls,
        context: SubagentHookContext | None,
    ) -> "SubagentCommandInputFields":
        if context is None:
            return cls()
        return cls(context.agent_id, context.agent_type)

    def apply_to(self, payload: dict[str, Any]) -> None:
        if self.agent_id is not None:
            payload["agent_id"] = self.agent_id
        if self.agent_type is not None:
            payload["agent_type"] = self.agent_type


def nullable_string_from_path(path: Path | str | None) -> str | None:
    return None if path is None else str(path)


def nullable_string_from_string(value: str | None) -> str | None:
    return value


def canonicalize_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: canonicalize_json(value[key])
            for key in sorted(value)
        }
    if isinstance(value, list):
        return [canonicalize_json(item) for item in value]
    return value


def _string_schema() -> dict[str, str]:
    return {"type": "string"}


def _boolean_schema(default: bool | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "boolean"}
    if default is not None:
        schema["default"] = default
    return schema


def _const_string_schema(value: str) -> dict[str, Any]:
    return {"const": value, "type": "string"}


def _enum_string_schema(values: Sequence[str]) -> dict[str, Any]:
    return {"enum": list(values), "type": "string"}


def _nullable_string_ref() -> dict[str, str]:
    return {"$ref": "#/definitions/NullableString"}


def _base_schema(title: str, properties: Mapping[str, Any], required: Sequence[str]) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "additionalProperties": False,
        "properties": dict(properties),
        "required": list(required),
        "title": title,
        "type": "object",
    }
    if any(value == _nullable_string_ref() for value in properties.values()):
        schema["definitions"] = {"NullableString": {"type": ["string", "null"]}}
    return schema


def _turn_id_schema() -> dict[str, str]:
    return {
        "description": "Codex extension: expose the active turn id to internal turn-scoped hooks.",
        "type": "string",
    }


def _common_input_properties(hook_event_name: str) -> dict[str, Any]:
    return {
        "session_id": _string_schema(),
        "turn_id": _turn_id_schema(),
        "transcript_path": _nullable_string_ref(),
        "cwd": _string_schema(),
        "hook_event_name": _const_string_schema(hook_event_name),
        "model": _string_schema(),
    }


def _with_optional_subagent(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": _string_schema(),
        "agent_type": _string_schema(),
        **properties,
    }


def _input_schema_for_fixture(fixture: str) -> dict[str, Any]:
    permission_mode = {"permission_mode": _enum_string_schema(PERMISSION_MODE_SCHEMA_VALUES)}
    common_required = ["cwd", "hook_event_name", "model", "session_id", "transcript_path", "turn_id"]
    if fixture == PRE_TOOL_USE_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("PreToolUse"),
                **permission_mode,
                "tool_name": _string_schema(),
                "tool_input": True,
                "tool_use_id": _string_schema(),
            }
        )
        required = ["cwd", "hook_event_name", "model", "permission_mode", "session_id", "tool_input", "tool_name", "tool_use_id", "transcript_path", "turn_id"]
        return _base_schema("pre-tool-use.command.input", props, required)
    if fixture == PERMISSION_REQUEST_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("PermissionRequest"),
                **permission_mode,
                "tool_name": _string_schema(),
                "tool_input": True,
            }
        )
        required = ["cwd", "hook_event_name", "model", "permission_mode", "session_id", "tool_input", "tool_name", "transcript_path", "turn_id"]
        return _base_schema("permission-request.command.input", props, required)
    if fixture == POST_TOOL_USE_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("PostToolUse"),
                **permission_mode,
                "tool_name": _string_schema(),
                "tool_input": True,
                "tool_response": True,
                "tool_use_id": _string_schema(),
            }
        )
        required = ["cwd", "hook_event_name", "model", "permission_mode", "session_id", "tool_input", "tool_name", "tool_response", "tool_use_id", "transcript_path", "turn_id"]
        return _base_schema("post-tool-use.command.input", props, required)
    if fixture == PRE_COMPACT_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("PreCompact"),
                "trigger": _enum_string_schema(COMPACTION_TRIGGER_SCHEMA_VALUES),
            }
        )
        return _base_schema("pre-compact.command.input", props, [*common_required, "trigger"])
    if fixture == POST_COMPACT_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("PostCompact"),
                "trigger": _enum_string_schema(COMPACTION_TRIGGER_SCHEMA_VALUES),
            }
        )
        return _base_schema("post-compact.command.input", props, [*common_required, "trigger"])
    if fixture == SESSION_START_INPUT_FIXTURE:
        props = {
            "session_id": _string_schema(),
            "transcript_path": _nullable_string_ref(),
            "cwd": _string_schema(),
            "hook_event_name": _const_string_schema("SessionStart"),
            "model": _string_schema(),
            **permission_mode,
            "source": _enum_string_schema(SESSION_START_SOURCE_SCHEMA_VALUES),
        }
        return _base_schema("session-start.command.input", props, ["cwd", "hook_event_name", "model", "permission_mode", "session_id", "source", "transcript_path"])
    if fixture == USER_PROMPT_SUBMIT_INPUT_FIXTURE:
        props = _with_optional_subagent(
            {
                **_common_input_properties("UserPromptSubmit"),
                **permission_mode,
                "prompt": _string_schema(),
            }
        )
        return _base_schema("user-prompt-submit.command.input", props, [*common_required, "permission_mode", "prompt"])
    if fixture == SUBAGENT_START_INPUT_FIXTURE:
        props = {
            **_common_input_properties("SubagentStart"),
            **permission_mode,
            "agent_id": _string_schema(),
            "agent_type": _string_schema(),
        }
        return _base_schema("subagent-start.command.input", props, [*common_required, "permission_mode", "agent_id", "agent_type"])
    if fixture == STOP_INPUT_FIXTURE:
        props = {
            **_common_input_properties("Stop"),
            **permission_mode,
            "stop_hook_active": _boolean_schema(),
            "last_assistant_message": _nullable_string_ref(),
        }
        return _base_schema("stop.command.input", props, [*common_required, "permission_mode", "stop_hook_active", "last_assistant_message"])
    if fixture == SUBAGENT_STOP_INPUT_FIXTURE:
        props = {
            **_common_input_properties("SubagentStop"),
            "agent_transcript_path": _nullable_string_ref(),
            **permission_mode,
            "stop_hook_active": _boolean_schema(),
            "agent_id": _string_schema(),
            "agent_type": _string_schema(),
            "last_assistant_message": _nullable_string_ref(),
        }
        return _base_schema("subagent-stop.command.input", props, [*common_required, "agent_transcript_path", "permission_mode", "stop_hook_active", "agent_id", "agent_type", "last_assistant_message"])
    raise KeyError(f"unknown hook input schema fixture: {fixture}")


def _universal_output_properties() -> dict[str, Any]:
    return {
        "continue": _boolean_schema(True),
        "stopReason": {"default": None, "type": "string"},
        "suppressOutput": _boolean_schema(False),
        "systemMessage": {"default": None, "type": "string"},
    }


def _hook_event_name_wire_definition() -> dict[str, Any]:
    return {"enum": list(HOOK_EVENT_NAME_WIRE_VALUES), "type": "string"}


def _output_schema_for_fixture(fixture: str) -> dict[str, Any]:
    properties = _universal_output_properties()
    definitions: dict[str, Any] = {}
    title_by_fixture = {
        PRE_TOOL_USE_OUTPUT_FIXTURE: "pre-tool-use.command.output",
        POST_TOOL_USE_OUTPUT_FIXTURE: "post-tool-use.command.output",
        PERMISSION_REQUEST_OUTPUT_FIXTURE: "permission-request.command.output",
        PRE_COMPACT_OUTPUT_FIXTURE: "pre-compact.command.output",
        POST_COMPACT_OUTPUT_FIXTURE: "post-compact.command.output",
        SESSION_START_OUTPUT_FIXTURE: "session-start.command.output",
        USER_PROMPT_SUBMIT_OUTPUT_FIXTURE: "user-prompt-submit.command.output",
        SUBAGENT_START_OUTPUT_FIXTURE: "subagent-start.command.output",
        STOP_OUTPUT_FIXTURE: "stop.command.output",
        SUBAGENT_STOP_OUTPUT_FIXTURE: "subagent-stop.command.output",
    }
    if fixture not in title_by_fixture:
        raise KeyError(f"unknown hook output schema fixture: {fixture}")

    if fixture in {PRE_TOOL_USE_OUTPUT_FIXTURE, POST_TOOL_USE_OUTPUT_FIXTURE, USER_PROMPT_SUBMIT_OUTPUT_FIXTURE, STOP_OUTPUT_FIXTURE, SUBAGENT_STOP_OUTPUT_FIXTURE}:
        properties["decision"] = {"default": None, "type": "string"}
        properties["reason"] = {"default": None, "type": "string"}
    if fixture in {PRE_TOOL_USE_OUTPUT_FIXTURE, POST_TOOL_USE_OUTPUT_FIXTURE, PERMISSION_REQUEST_OUTPUT_FIXTURE, SESSION_START_OUTPUT_FIXTURE, USER_PROMPT_SUBMIT_OUTPUT_FIXTURE, SUBAGENT_START_OUTPUT_FIXTURE}:
        definitions["HookEventNameWire"] = _hook_event_name_wire_definition()
        properties["hookSpecificOutput"] = {"default": None}
    if fixture == PERMISSION_REQUEST_OUTPUT_FIXTURE:
        definitions["PermissionRequestBehaviorWire"] = {"enum": ["allow", "deny"], "type": "string"}
        definitions["PermissionRequestDecisionWire"] = {
            "additionalProperties": False,
            "properties": {
                "behavior": {"$ref": "#/definitions/PermissionRequestBehaviorWire"},
                "updatedInput": {"default": None},
                "updatedPermissions": {"default": None},
                "message": {"default": None, "type": "string"},
                "interrupt": _boolean_schema(False),
            },
            "required": ["behavior"],
            "type": "object",
        }
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "additionalProperties": False,
        "properties": properties,
        "title": title_by_fixture[fixture],
        "type": "object",
    }
    if definitions:
        schema["definitions"] = definitions
    return schema


def schema_for_fixture(fixture: str) -> dict[str, Any]:
    if fixture.endswith(".command.input.schema.json"):
        return _input_schema_for_fixture(fixture)
    if fixture.endswith(".command.output.schema.json"):
        return _output_schema_for_fixture(fixture)
    raise KeyError(f"unknown hook schema fixture: {fixture}")


def schema_json(fixture: str) -> str:
    value = canonicalize_json(schema_for_fixture(fixture))
    return json.dumps(value, indent=2, separators=(",", ": ")) + "\n"


@dataclass(frozen=True)
class GeneratedHookSchemas:
    post_tool_use_command_input: dict[str, Any]
    post_tool_use_command_output: dict[str, Any]
    permission_request_command_input: dict[str, Any]
    permission_request_command_output: dict[str, Any]
    post_compact_command_input: dict[str, Any]
    post_compact_command_output: dict[str, Any]
    pre_tool_use_command_input: dict[str, Any]
    pre_tool_use_command_output: dict[str, Any]
    pre_compact_command_input: dict[str, Any]
    pre_compact_command_output: dict[str, Any]
    session_start_command_input: dict[str, Any]
    session_start_command_output: dict[str, Any]
    subagent_start_command_input: dict[str, Any]
    subagent_start_command_output: dict[str, Any]
    subagent_stop_command_input: dict[str, Any]
    subagent_stop_command_output: dict[str, Any]
    user_prompt_submit_command_input: dict[str, Any]
    user_prompt_submit_command_output: dict[str, Any]
    stop_command_input: dict[str, Any]
    stop_command_output: dict[str, Any]


_GENERATED_HOOK_SCHEMAS: GeneratedHookSchemas | None = None


def parse_json_schema(name: str, schema: str) -> dict[str, Any]:
    try:
        parsed = json.loads(schema)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid generated hooks schema {name}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"invalid generated hooks schema {name}: expected object")
    return parsed


def _schema_value(fixture: str) -> dict[str, Any]:
    return parse_json_schema(fixture.removesuffix(".schema.json"), schema_json(fixture))


def generated_hook_schemas() -> GeneratedHookSchemas:
    global _GENERATED_HOOK_SCHEMAS
    if _GENERATED_HOOK_SCHEMAS is None:
        _GENERATED_HOOK_SCHEMAS = GeneratedHookSchemas(
            post_tool_use_command_input=_schema_value(POST_TOOL_USE_INPUT_FIXTURE),
            post_tool_use_command_output=_schema_value(POST_TOOL_USE_OUTPUT_FIXTURE),
            permission_request_command_input=_schema_value(PERMISSION_REQUEST_INPUT_FIXTURE),
            permission_request_command_output=_schema_value(PERMISSION_REQUEST_OUTPUT_FIXTURE),
            post_compact_command_input=_schema_value(POST_COMPACT_INPUT_FIXTURE),
            post_compact_command_output=_schema_value(POST_COMPACT_OUTPUT_FIXTURE),
            pre_tool_use_command_input=_schema_value(PRE_TOOL_USE_INPUT_FIXTURE),
            pre_tool_use_command_output=_schema_value(PRE_TOOL_USE_OUTPUT_FIXTURE),
            pre_compact_command_input=_schema_value(PRE_COMPACT_INPUT_FIXTURE),
            pre_compact_command_output=_schema_value(PRE_COMPACT_OUTPUT_FIXTURE),
            session_start_command_input=_schema_value(SESSION_START_INPUT_FIXTURE),
            session_start_command_output=_schema_value(SESSION_START_OUTPUT_FIXTURE),
            subagent_start_command_input=_schema_value(SUBAGENT_START_INPUT_FIXTURE),
            subagent_start_command_output=_schema_value(SUBAGENT_START_OUTPUT_FIXTURE),
            subagent_stop_command_input=_schema_value(SUBAGENT_STOP_INPUT_FIXTURE),
            subagent_stop_command_output=_schema_value(SUBAGENT_STOP_OUTPUT_FIXTURE),
            user_prompt_submit_command_input=_schema_value(USER_PROMPT_SUBMIT_INPUT_FIXTURE),
            user_prompt_submit_command_output=_schema_value(USER_PROMPT_SUBMIT_OUTPUT_FIXTURE),
            stop_command_input=_schema_value(STOP_INPUT_FIXTURE),
            stop_command_output=_schema_value(STOP_OUTPUT_FIXTURE),
        )
    return _GENERATED_HOOK_SCHEMAS


def write_schema_fixtures(schema_root: Path | str) -> None:
    generated_dir = Path(schema_root) / GENERATED_SCHEMA_DIR
    if generated_dir.exists():
        for child in generated_dir.iterdir():
            if child.is_dir():
                import shutil

                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        generated_dir.mkdir(parents=True, exist_ok=True)

    for fixture in SCHEMA_FIXTURE_NAMES:
        (generated_dir / fixture).write_text(schema_json(fixture), encoding="utf-8")


__all__ = [name for name in globals() if not name.startswith("_")]
