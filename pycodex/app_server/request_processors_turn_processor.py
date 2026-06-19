"""Turn request processor facade ported from ``app-server/src/request_processors/turn_processor.rs``."""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server_protocol import (
    AdditionalContextEntry,
    AdditionalContextKind,
    JSONRPCErrorError,
    ThreadRealtimeAppendAudioParams,
    ThreadRealtimeAppendAudioResponse,
    ThreadRealtimeAppendTextParams,
    ThreadRealtimeAppendTextResponse,
    ThreadRealtimeListVoicesResponse,
    ThreadRealtimeStartParams,
    ThreadRealtimeStartResponse,
    ThreadRealtimeStopParams,
    ThreadRealtimeStopResponse,
    TurnInterruptParams,
    TurnInterruptResponse,
    TurnStartParams,
    TurnStartResponse,
    TurnSteerParams,
    TurnSteerResponse,
)
from pycodex.protocol import RealtimeVoicesList

JsonValue = Any


@dataclass
class TurnRequestProcessorError(Exception):
    error: JSONRPCErrorError

    def __post_init__(self) -> None:
        Exception.__init__(self, self.error.message)


@dataclass(frozen=True)
class CoreAdditionalContextEntry:
    value: str
    kind: str


@dataclass(frozen=True)
class ThreadSettingsBuildParams:
    method: str
    cwd: str | None
    runtime_workspace_roots: tuple[str, ...]
    approval_policy: Any | None
    approvals_reviewer: Any | None
    sandbox_policy: Any | None
    permissions: str | None
    model: str | None
    service_tier: Any
    effort: Any | None
    summary: Any | None
    collaboration_mode: Any | None
    personality: Any | None


def resolve_runtime_workspace_roots(
    workspace_roots: tuple[str | Path, ...] | list[str | Path] | None,
    base_cwd: str | Path,
) -> tuple[str, ...]:
    """Resolve optional workspace roots against ``base_cwd`` and dedupe in Rust order."""

    if workspace_roots is None:
        return ()
    base = Path(base_cwd)
    result: list[str] = []
    seen: set[str] = set()
    for raw_path in workspace_roots:
        path = Path(raw_path)
        resolved = path if path.is_absolute() else base / path
        normalized = str(resolved)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


def map_additional_context(
    additional_context: Mapping[str, AdditionalContextEntry | Mapping[str, JsonValue]] | None,
) -> dict[str, CoreAdditionalContextEntry]:
    """Map API additional context entries into the sorted core shape used by Rust."""

    if not additional_context:
        return {}
    mapped: dict[str, CoreAdditionalContextEntry] = {}
    for key in sorted(additional_context):
        entry = additional_context[key]
        parsed = entry if isinstance(entry, AdditionalContextEntry) else AdditionalContextEntry.from_mapping(entry)
        mapped[str(key)] = CoreAdditionalContextEntry(value=parsed.value, kind=_core_additional_context_kind(parsed.kind))
    return mapped


def parse_thread_id_for_request(thread_id: str) -> str:
    try:
        return str(uuid.UUID(str(thread_id)))
    except Exception as exc:
        raise TurnRequestProcessorError(invalid_request(f"invalid thread id: {exc}")) from exc


@dataclass
class TurnRequestProcessor:
    auth_manager: Any
    thread_manager: Any
    outgoing: Any
    analytics_events_client: Any
    arg0_paths: Any
    config: Any
    config_manager: Any
    pending_thread_unloads: Any
    thread_state_manager: Any
    thread_watch_manager: Any
    thread_list_state_permit: Any
    skills_watcher: Any

    @classmethod
    def new(
        cls,
        auth_manager: Any,
        thread_manager: Any,
        outgoing: Any,
        analytics_events_client: Any,
        arg0_paths: Any,
        config: Any,
        config_manager: Any,
        pending_thread_unloads: Any,
        thread_state_manager: Any,
        thread_watch_manager: Any,
        thread_list_state_permit: Any,
        skills_watcher: Any,
    ) -> "TurnRequestProcessor":
        return cls(
            auth_manager,
            thread_manager,
            outgoing,
            analytics_events_client,
            arg0_paths,
            config,
            config_manager,
            pending_thread_unloads,
            thread_state_manager,
            thread_watch_manager,
            thread_list_state_permit,
            skills_watcher,
        )

    async def turn_start(self, request_id: Any, connection_id: Any, params: TurnStartParams | Mapping[str, JsonValue]) -> TurnStartResponse:
        parsed = params if isinstance(params, TurnStartParams) else TurnStartParams.from_mapping(params)
        return await self.turn_start_inner(request_id, connection_id, parsed)

    async def thread_inject_items(
        self,
        request_id: Any,
        connection_id: Any,
        params: Any,
    ) -> Any:
        return await self.thread_inject_items_response_inner(request_id, connection_id, params)

    async def thread_settings_update(
        self,
        request_id: Any,
        params: Any,
    ) -> Any:
        return await self.thread_settings_update_inner(request_id, params)

    async def turn_steer(self, request_id: Any, params: TurnSteerParams | Mapping[str, JsonValue]) -> TurnSteerResponse:
        parsed = params if isinstance(params, TurnSteerParams) else TurnSteerParams.from_mapping(params)
        return await self.turn_steer_inner(request_id, parsed)

    async def turn_interrupt(
        self,
        request_id: Any,
        params: TurnInterruptParams | Mapping[str, JsonValue],
    ) -> TurnInterruptResponse | None:
        parsed = params if isinstance(params, TurnInterruptParams) else TurnInterruptParams.from_mapping(params)
        return await self.turn_interrupt_inner(request_id, parsed)

    async def thread_realtime_start(
        self,
        request_id: Any,
        params: ThreadRealtimeStartParams | Mapping[str, JsonValue],
    ) -> ThreadRealtimeStartResponse:
        parsed = params if isinstance(params, ThreadRealtimeStartParams) else ThreadRealtimeStartParams.from_mapping(params)
        return await self.thread_realtime_start_inner(request_id, parsed)

    async def thread_realtime_append_audio(
        self,
        request_id: Any,
        params: ThreadRealtimeAppendAudioParams | Mapping[str, JsonValue],
    ) -> ThreadRealtimeAppendAudioResponse:
        parsed = params if isinstance(params, ThreadRealtimeAppendAudioParams) else ThreadRealtimeAppendAudioParams.from_mapping(params)
        return await self.thread_realtime_append_audio_inner(request_id, parsed)

    async def thread_realtime_append_text(
        self,
        request_id: Any,
        params: ThreadRealtimeAppendTextParams | Mapping[str, JsonValue],
    ) -> ThreadRealtimeAppendTextResponse:
        parsed = params if isinstance(params, ThreadRealtimeAppendTextParams) else ThreadRealtimeAppendTextParams.from_mapping(params)
        return await self.thread_realtime_append_text_inner(request_id, parsed)

    async def thread_realtime_stop(
        self,
        request_id: Any,
        params: ThreadRealtimeStopParams | Mapping[str, JsonValue],
    ) -> ThreadRealtimeStopResponse:
        parsed = params if isinstance(params, ThreadRealtimeStopParams) else ThreadRealtimeStopParams.from_mapping(params)
        return await self.thread_realtime_stop_inner(request_id, parsed)

    async def thread_realtime_list_voices(self) -> ThreadRealtimeListVoicesResponse:
        return ThreadRealtimeListVoicesResponse(voices=RealtimeVoicesList.builtin())

    async def review_start(self, request_id: Any, params: Any) -> None:
        await self.review_start_inner(request_id, params)

    async def load_thread(self, thread_id: str) -> tuple[str, Any]:
        parsed = parse_thread_id_for_request(thread_id)
        thread = await _maybe_await(_call_or_get(self.thread_manager, "get_thread", parsed))
        if thread is None:
            raise TurnRequestProcessorError(invalid_request(f"thread not found: {parsed}"))
        return parsed, thread

    def track_error_response(self, request_id: Any, error: JSONRPCErrorError) -> None:
        _call_or_get(self.analytics_events_client, "track_error_response", request_id, error)

    async def turn_start_inner(self, request_id: Any, connection_id: Any, params: TurnStartParams) -> TurnStartResponse:
        return await _required_inner(self, "turn_start_inner", request_id, connection_id, params)

    async def thread_settings_update_inner(self, request_id: Any, params: Any) -> Any:
        return await _required_inner(self, "thread_settings_update_inner", request_id, params)

    async def thread_inject_items_response_inner(
        self,
        request_id: Any,
        connection_id: Any,
        params: Any,
    ) -> Any:
        return await _required_inner(self, "thread_inject_items_response_inner", request_id, connection_id, params)

    async def turn_steer_inner(self, request_id: Any, params: TurnSteerParams) -> TurnSteerResponse:
        return await _required_inner(self, "turn_steer_inner", request_id, params)

    async def thread_realtime_start_inner(self, request_id: Any, params: ThreadRealtimeStartParams) -> ThreadRealtimeStartResponse:
        return await _required_inner(self, "thread_realtime_start_inner", request_id, params)

    async def thread_realtime_append_audio_inner(
        self,
        request_id: Any,
        params: ThreadRealtimeAppendAudioParams,
    ) -> ThreadRealtimeAppendAudioResponse:
        return await _required_inner(self, "thread_realtime_append_audio_inner", request_id, params)

    async def thread_realtime_append_text_inner(
        self,
        request_id: Any,
        params: ThreadRealtimeAppendTextParams,
    ) -> ThreadRealtimeAppendTextResponse:
        return await _required_inner(self, "thread_realtime_append_text_inner", request_id, params)

    async def thread_realtime_stop_inner(self, request_id: Any, params: ThreadRealtimeStopParams) -> ThreadRealtimeStopResponse:
        return await _required_inner(self, "thread_realtime_stop_inner", request_id, params)

    async def review_start_inner(self, request_id: Any, params: Any) -> None:
        await _required_inner(self, "review_start_inner", request_id, params)

    async def turn_interrupt_inner(self, request_id: Any, params: TurnInterruptParams) -> TurnInterruptResponse | None:
        return await _required_inner(self, "turn_interrupt_inner", request_id, params)

    def listener_task_context(self) -> dict[str, Any]:
        return {
            "thread_manager": self.thread_manager,
            "thread_state_manager": self.thread_state_manager,
            "outgoing": self.outgoing,
            "pending_thread_unloads": self.pending_thread_unloads,
            "thread_watch_manager": self.thread_watch_manager,
            "thread_list_state_permit": self.thread_list_state_permit,
            "fallback_model_provider": _call_or_get(self.config, "model_provider_id"),
            "codex_home": _call_or_get(self.config, "codex_home"),
            "skills_watcher": self.skills_watcher,
        }


def xcode_26_4_mcp_elicitations_auto_deny(client_name: str | None, client_version: str | None) -> bool:
    return client_name == "Xcode" and client_version is not None and client_version.startswith("26.4")


def _core_additional_context_kind(kind: AdditionalContextKind | str) -> str:
    parsed = AdditionalContextKind.parse(kind)
    if parsed is AdditionalContextKind.UNTRUSTED:
        return "Untrusted"
    if parsed is AdditionalContextKind.APPLICATION:
        return "Application"
    raise TurnRequestProcessorError(internal_error(f"unsupported additional context kind: {kind}"))


async def _required_inner(owner: Any, name: str, *args: Any) -> Any:
    override_name = f"{name}_override"
    override = owner.get(override_name) if isinstance(owner, Mapping) else getattr(owner, override_name, None)
    if override is not None:
        return await _maybe_await(override(*args))
    raise TurnRequestProcessorError(internal_error(f"{name} requires the core runtime implementation"))


def _call_or_get(obj: Any, name: str, *args: Any) -> Any:
    if obj is None:
        return None
    value = obj.get(name) if isinstance(obj, Mapping) else getattr(obj, name, None)
    if callable(value):
        return value(*args)
    return value


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "CoreAdditionalContextEntry",
    "ThreadSettingsBuildParams",
    "TurnRequestProcessor",
    "TurnRequestProcessorError",
    "map_additional_context",
    "parse_thread_id_for_request",
    "resolve_runtime_workspace_roots",
    "xcode_26_4_mcp_elicitations_auto_deny",
]
