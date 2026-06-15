"""Codex thread wrapper ported from ``core/src/codex_thread.rs``.

Rust's ``CodexThread`` is intentionally thin: it wraps a running ``Codex``
session, delegates most runtime operations to it, and exposes thread-scoped
configuration snapshots plus app-server settings overrides.  This Python module
keeps that shape while the deeper session runtime is still being ported.
"""

from __future__ import annotations

import copy
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from pycodex.protocol import CollaborationMode, ContentItem, ModeKind, Op, ResponseItem, SessionSource, Settings, ThreadMemoryMode, W3cTraceContext

SETTINGS_UNSET = object()
_UNSET = SETTINGS_UNSET


class CodexThreadError(Exception):
    """Base error for thread wrapper failures."""


class InvalidThreadRequest(CodexThreadError):
    """Raised when a caller makes a request Rust would reject as invalid."""


class ActiveTurnInjectionRejected(CodexThreadError):
    """Raised when hidden items cannot be injected into the active turn."""

    def __init__(self, items: Sequence[Any]) -> None:
        self.items = tuple(items)
        super().__init__("thread has no active turn for response item injection")


@dataclass(frozen=True, slots=True)
class ThreadConfigSnapshot:
    model: str
    model_provider_id: str
    service_tier: str | None = None
    approval_policy: Any = None
    approvals_reviewer: Any = None
    permission_profile: Any = None
    active_permission_profile: Any = None
    file_system_sandbox_policy: Any = None
    cwd: Path = field(default_factory=Path.cwd)
    workspace_roots: tuple[Path, ...] = ()
    profile_workspace_roots: tuple[Path, ...] = ()
    ephemeral: bool = False
    reasoning_effort: Any = None
    reasoning_summary: Any = None
    personality: Any = None
    collaboration_mode: Any = None
    session_source: SessionSource = field(default_factory=SessionSource.default)
    thread_source: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.model, str):
            raise TypeError("model must be a string")
        if not isinstance(self.model_provider_id, str):
            raise TypeError("model_provider_id must be a string")
        object.__setattr__(self, "cwd", Path(self.cwd))
        object.__setattr__(self, "workspace_roots", _path_tuple(self.workspace_roots))
        object.__setattr__(self, "profile_workspace_roots", _path_tuple(self.profile_workspace_roots))
        if not isinstance(self.ephemeral, bool):
            raise TypeError("ephemeral must be a bool")

    def sandbox_policy(self) -> Any:
        if self.permission_profile is None:
            raise TypeError("permission_profile is required")
        method = getattr(self.permission_profile, "to_legacy_sandbox_policy", None)
        if callable(method):
            return method(self.cwd)
        raise TypeError("permission_profile must expose to_legacy_sandbox_policy()")


@dataclass(frozen=True, slots=True)
class CodexThreadSettingsOverrides:
    cwd: Path | None = None
    workspace_roots: tuple[Path, ...] | None = None
    profile_workspace_roots: tuple[Path, ...] | None = None
    approval_policy: Any = None
    approvals_reviewer: Any = None
    sandbox_policy: Any = None
    permission_profile: Any = None
    active_permission_profile: Any = None
    windows_sandbox_level: Any = None
    model: str | None = None
    effort: Any = _UNSET
    summary: Any = None
    service_tier: str | None | object = _UNSET
    collaboration_mode: Any = None
    personality: Any = None

    def __post_init__(self) -> None:
        if self.cwd is not None:
            object.__setattr__(self, "cwd", Path(self.cwd))
        if self.workspace_roots is not None:
            object.__setattr__(self, "workspace_roots", _path_tuple(self.workspace_roots))
        if self.profile_workspace_roots is not None:
            object.__setattr__(self, "profile_workspace_roots", _path_tuple(self.profile_workspace_roots))
        if self.model is not None and not isinstance(self.model, str):
            raise TypeError("model must be a string or None")

    @classmethod
    def default(cls) -> "CodexThreadSettingsOverrides":
        return cls()

    @classmethod
    def from_thread_settings_overrides(cls, overrides: Any) -> "CodexThreadSettingsOverrides":
        """Build core settings overrides from protocol ``ThreadSettingsOverrides``.

        The protocol layer uses its own private sentinel for double-option
        fields such as ``effort`` and ``service_tier``.  Normalize that shape to
        this module's shared unset sentinel so downstream settings updates keep
        Rust's "omitted vs explicit null" distinction.
        """

        return cls(
            cwd=getattr(overrides, "cwd", None),
            workspace_roots=getattr(overrides, "workspace_roots", None),
            profile_workspace_roots=getattr(overrides, "profile_workspace_roots", None),
            approval_policy=getattr(overrides, "approval_policy", None),
            approvals_reviewer=getattr(overrides, "approvals_reviewer", None),
            sandbox_policy=getattr(overrides, "sandbox_policy", None),
            permission_profile=getattr(overrides, "permission_profile", None),
            active_permission_profile=getattr(overrides, "active_permission_profile", None),
            windows_sandbox_level=getattr(overrides, "windows_sandbox_level", None),
            model=getattr(overrides, "model", None),
            effort=_protocol_nullable_setting(getattr(overrides, "effort", SETTINGS_UNSET)),
            summary=getattr(overrides, "summary", None),
            service_tier=_protocol_nullable_setting(getattr(overrides, "service_tier", SETTINGS_UNSET)),
            collaboration_mode=getattr(overrides, "collaboration_mode", None),
            personality=getattr(overrides, "personality", None),
        )


@dataclass(frozen=True, slots=True)
class SessionSettingsUpdate:
    cwd: Path | None = None
    workspace_roots: tuple[Path, ...] | None = None
    profile_workspace_roots: tuple[Path, ...] | None = None
    environments: Any = None
    final_output_json_schema: Any = _UNSET
    approval_policy: Any = None
    approvals_reviewer: Any = None
    sandbox_policy: Any = None
    permission_profile: Any = None
    active_permission_profile: Any = None
    windows_sandbox_level: Any = None
    collaboration_mode: Any = None
    reasoning_summary: Any = None
    service_tier: Any = _UNSET
    personality: Any = None


class CodexThread:
    """Bidirectional thread conduit around a Codex-like runtime object."""

    def __init__(
        self,
        codex: Any,
        session_configured: Any,
        rollout_path: str | Path | None = None,
        session_source: SessionSource | None = None,
    ) -> None:
        self.codex = codex
        self.session_source = session_source or SessionSource.default()
        self._session_configured = session_configured
        self._rollout_path = Path(rollout_path) if rollout_path is not None else None
        self._out_of_band_elicitation_count = 0

    @classmethod
    def new(
        cls,
        codex: Any,
        session_configured: Any,
        rollout_path: str | Path | None = None,
        session_source: SessionSource | None = None,
    ) -> "CodexThread":
        return cls(codex, session_configured, rollout_path, session_source)

    async def submit(self, op: Op) -> str:
        return await _call_required(self.codex, "submit", op)

    def session_telemetry(self) -> Any:
        return _nested_get(self.codex, "session", "services", "session_telemetry")

    async def shutdown_and_wait(self) -> None:
        await _call_required(self.codex, "shutdown_and_wait")

    async def wait_until_terminated(self) -> None:
        termination = getattr(self.codex, "session_loop_termination", None)
        if inspect.isawaitable(termination):
            await termination
            return
        waiter = getattr(termination, "wait", None)
        if callable(waiter):
            await _maybe_await(waiter())

    async def emit_thread_resume_lifecycle(self) -> None:
        contributors = _call_optional(_nested_get(self.codex, "session", "services", "extensions"), "thread_lifecycle_contributors", ())
        for contributor in contributors or ():
            handler = getattr(contributor, "on_thread_resume", None)
            if callable(handler):
                await _maybe_await(handler({"session_store": None, "thread_store": None}))

    async def apply_goal_resume_runtime_effects(self) -> Any:
        return await self._apply_goal_runtime("thread_resumed")

    async def continue_active_goal_if_idle(self) -> Any:
        return await self._apply_goal_runtime("maybe_continue_if_idle")

    async def prepare_external_goal_mutation(self) -> None:
        await self._apply_goal_runtime("external_mutation_starting", swallow_errors=True)

    async def apply_external_goal_set(self, external_set: Any) -> None:
        await self._apply_goal_runtime({"external_set": external_set}, swallow_errors=True)

    async def apply_external_goal_clear(self) -> None:
        await self._apply_goal_runtime("external_clear", swallow_errors=True)

    async def ensure_rollout_materialized(self) -> Any:
        return await _call_required(_nested_get(self.codex, "session"), "ensure_rollout_materialized")

    async def flush_rollout(self) -> Any:
        return await _call_required(_nested_get(self.codex, "session"), "flush_rollout")

    async def submit_with_trace(self, op: Op, trace: W3cTraceContext | None = None) -> str:
        submit_with_trace = getattr(self.codex, "submit_with_trace", None)
        if callable(submit_with_trace):
            return await _maybe_await(submit_with_trace(op, trace))
        return await self.submit(op)

    async def set_thread_memory_mode(self, mode: ThreadMemoryMode) -> Any:
        return await _call_required(self.codex, "set_thread_memory_mode", mode)

    async def steer_input(
        self,
        input: Sequence[Any],
        additional_context: Mapping[str, Any] | None = None,
        expected_turn_id: str | None = None,
        responsesapi_client_metadata: Mapping[str, str] | None = None,
    ) -> Any:
        return await _call_required(
            self.codex,
            "steer_input",
            list(input),
            dict(additional_context or {}),
            expected_turn_id,
            dict(responsesapi_client_metadata) if responsesapi_client_metadata is not None else None,
        )

    async def inject_response_items_into_active_turn(self, items: Sequence[Any]) -> None:
        original_items = tuple(items)
        response_items = [_response_input_item_to_response_item(item) for item in original_items]
        session = _nested_get(self.codex, "session")
        injector = getattr(session, "inject_if_running", None)
        if not callable(injector):
            raise ActiveTurnInjectionRejected(original_items)
        try:
            result = await _maybe_await(injector(response_items))
        except Exception as exc:
            raise ActiveTurnInjectionRejected(original_items) from exc
        if result is False:
            raise ActiveTurnInjectionRejected(original_items)

    async def set_app_server_client_info(
        self,
        app_server_client_name: str | None,
        app_server_client_version: str | None,
        mcp_elicitations_auto_deny: bool,
    ) -> Any:
        return await _call_required(
            self.codex,
            "set_app_server_client_info",
            app_server_client_name,
            app_server_client_version,
            mcp_elicitations_auto_deny,
        )

    async def preview_thread_settings_overrides(
        self,
        overrides: CodexThreadSettingsOverrides,
    ) -> ThreadConfigSnapshot:
        updates = await self.thread_settings_update(overrides)
        return await _call_required(_nested_get(self.codex, "session"), "preview_settings", updates)

    async def thread_settings_update(self, overrides: CodexThreadSettingsOverrides) -> SessionSettingsUpdate:
        collaboration_mode = overrides.collaboration_mode
        if collaboration_mode is None:
            session = _nested_get(self.codex, "session")
            current = await _maybe_await(_call_optional(session, "collaboration_mode"))
            if current is None:
                current = _default_collaboration_mode(session, self._session_configured, overrides.model)
            updater = getattr(current, "with_updates", None)
            collaboration_mode = (
                _with_collaboration_updates(updater, overrides.model, overrides.effort)
                if callable(updater)
                else current
            )

        return SessionSettingsUpdate(
            cwd=overrides.cwd,
            workspace_roots=overrides.workspace_roots,
            profile_workspace_roots=overrides.profile_workspace_roots,
            approval_policy=overrides.approval_policy,
            approvals_reviewer=overrides.approvals_reviewer,
            sandbox_policy=overrides.sandbox_policy,
            permission_profile=overrides.permission_profile,
            active_permission_profile=overrides.active_permission_profile,
            windows_sandbox_level=overrides.windows_sandbox_level,
            collaboration_mode=collaboration_mode,
            reasoning_summary=overrides.summary,
            service_tier=overrides.service_tier,
            personality=overrides.personality,
        )

    async def submit_with_id(self, submission: Any) -> None:
        await _call_required(self.codex, "submit_with_id", submission)

    async def next_event(self) -> Any:
        return await _call_required(self.codex, "next_event")

    async def agent_status(self) -> Any:
        return await _call_required(self.codex, "agent_status")

    def subscribe_status(self) -> Any:
        subscriber = getattr(self.codex, "subscribe_status", None)
        if callable(subscriber):
            return subscriber()
        status = getattr(self.codex, "agent_status", None)
        subscribe = getattr(status, "subscribe", None)
        if callable(subscribe):
            return subscribe()
        clone = getattr(status, "clone", None)
        if callable(clone):
            return clone()
        return status

    async def token_usage_info(self) -> Any:
        return copy.deepcopy(await _call_required(_nested_get(self.codex, "session"), "token_usage_info"))

    async def inject_user_message_without_turn(self, message: str) -> None:
        if not isinstance(message, str):
            raise TypeError("message must be a string")
        session = _nested_get(self.codex, "session")
        item = ResponseItem.message("user", (ContentItem.input_text(message),))
        await _call_required(session, "inject_no_new_turn", [item], None)

    async def inject_response_items(self, items: Sequence[Any]) -> None:
        if not items:
            raise InvalidThreadRequest("items must not be empty")
        session = _nested_get(self.codex, "session")
        turn_context = await _call_required(session, "new_default_turn")
        reference = await _call_required(session, "reference_context_item")
        if reference is None:
            recorder = getattr(session, "record_context_updates_and_set_reference_context_item", None)
            if callable(recorder):
                await _maybe_await(recorder(turn_context))
        if session.__class__.__name__ == "InMemoryCodexSession":
            response_items = [_response_input_item_to_response_item(item) for item in items]
            previous_active_turn = getattr(session, "active_turn", None)
            try:
                session.active_turn = None
                await _call_required(session, "inject_no_new_turn", response_items, turn_context)
            finally:
                session.active_turn = previous_active_turn
        else:
            await _call_required(session, "inject_no_new_turn", items, turn_context)
        await _call_required(session, "flush_rollout")

    def rollout_path(self) -> Path | None:
        return Path(self._rollout_path) if self._rollout_path is not None else None

    def session_configured(self) -> Any:
        return copy.deepcopy(self._session_configured)

    def is_running(self) -> bool:
        tx_sub = getattr(self.codex, "tx_sub", None)
        is_closed = getattr(tx_sub, "is_closed", None)
        if callable(is_closed):
            return not bool(is_closed())
        return True

    async def guardian_trunk_rollout_path(self) -> Path | None:
        guardian = _nested_get(self.codex, "session", "guardian_review_session")
        path = await _maybe_await(_call_optional(guardian, "trunk_rollout_path"))
        return Path(path) if path is not None else None

    async def load_history(self, include_archived: bool) -> Any:
        live_thread = await self._live_thread_for_persistence("load history")
        return await _call_required(live_thread, "load_history", include_archived)

    async def read_thread(self, include_archived: bool, include_history: bool) -> Any:
        live_thread = await self._live_thread_for_persistence("read thread")
        return await _call_required(live_thread, "read_thread", include_archived, include_history)

    async def update_thread_metadata(self, patch: Any, include_archived: bool) -> Any:
        live_thread = await self._live_thread_for_persistence("update thread metadata")
        return await _call_required(live_thread, "update_metadata", patch, include_archived)

    def state_db(self) -> Any:
        state_db = getattr(self.codex, "state_db", None)
        return state_db() if callable(state_db) else state_db

    async def config_snapshot(self) -> ThreadConfigSnapshot:
        snapshot = _call_optional(self.codex, "thread_config_snapshot")
        if snapshot is not None:
            return copy.deepcopy(await _maybe_await(snapshot))
        return copy.deepcopy(await _call_required(_nested_get(self.codex, "session"), "thread_config_snapshot"))

    async def config(self) -> Any:
        return await _call_required(_nested_get(self.codex, "session"), "get_config")

    async def refresh_runtime_config(self, next_config: Any) -> None:
        await _call_required(_nested_get(self.codex, "session"), "refresh_runtime_config", next_config)

    async def environment_selections(self) -> Any:
        selections = await _call_required(self.codex, "thread_environment_selections")
        return list(selections or [])

    async def read_mcp_resource(self, server: str, uri: str) -> Any:
        return await _call_required(_nested_get(self.codex, "session"), "read_resource", server, uri)

    async def call_mcp_tool(self, server: str, tool: str, arguments: Any = None, meta: Any = None) -> Any:
        return await _call_required(_nested_get(self.codex, "session"), "call_tool", server, tool, arguments, meta)

    def enabled(self, feature: Any) -> bool:
        enabled = getattr(self.codex, "enabled", None)
        return bool(enabled(feature)) if callable(enabled) else False

    async def increment_out_of_band_elicitation_count(self) -> int:
        if self._out_of_band_elicitation_count >= (2**64 - 1):
            raise CodexThreadError("out-of-band elicitation count overflowed")
        was_zero = self._out_of_band_elicitation_count == 0
        self._out_of_band_elicitation_count += 1
        if was_zero:
            self._set_out_of_band_pause_state(True)
        return self._out_of_band_elicitation_count

    async def decrement_out_of_band_elicitation_count(self) -> int:
        if self._out_of_band_elicitation_count == 0:
            raise InvalidThreadRequest("out-of-band elicitation count is already zero")
        self._out_of_band_elicitation_count -= 1
        if self._out_of_band_elicitation_count == 0:
            self._set_out_of_band_pause_state(False)
        return self._out_of_band_elicitation_count

    async def _apply_goal_runtime(self, event: Any, swallow_errors: bool = False) -> Any:
        session = _nested_get(self.codex, "session")
        try:
            return await _call_required(session, "goal_runtime_apply", event)
        except Exception:
            if swallow_errors:
                return None
            raise

    async def _live_thread_for_persistence(self, reason: str) -> Any:
        session = _nested_get(self.codex, "session")
        live_thread = _call_optional(session, "live_thread_for_persistence", reason)
        return await _maybe_await(live_thread)

    def _set_out_of_band_pause_state(self, paused: bool) -> None:
        session = _nested_get(self.codex, "session")
        setter = getattr(session, "set_out_of_band_elicitation_pause_state", None)
        if callable(setter):
            setter(paused)


def _path_tuple(paths: Sequence[str | Path]) -> tuple[Path, ...]:
    if isinstance(paths, (str, bytes)):
        raise TypeError("paths must be a sequence of paths")
    return tuple(Path(path) for path in paths)


def _nested_get(value: Any, *names: str) -> Any:
    current = value
    for name in names:
        current = getattr(current, name, None)
        if current is None:
            return None
    return current


def _call_optional(target: Any, name: str, *args: Any) -> Any:
    method = getattr(target, name, None)
    if callable(method):
        return method(*args)
    if not args:
        return method
    return None


def _default_collaboration_mode(session: Any, session_configured: Any, override_model: str | None) -> CollaborationMode:
    return CollaborationMode(
        mode=ModeKind.DEFAULT,
        settings=Settings(model=_default_model(session, session_configured, override_model)),
    )


def _default_model(session: Any, session_configured: Any, override_model: str | None) -> str:
    if override_model is not None:
        return override_model
    model = _field_or_mapping(session_configured, "model")
    if model is not None:
        return str(model)
    model_info = getattr(session, "model_info", None)
    slug = getattr(model_info, "slug", None)
    if slug is not None:
        return str(slug)
    return ""


def _with_collaboration_updates(updater: Any, model: str | None, effort: Any) -> Any:
    kwargs: dict[str, Any] = {}
    if model is not None:
        kwargs["model"] = model
    if effort is not SETTINGS_UNSET:
        kwargs["effort"] = effort
    try:
        return updater(**kwargs)
    except TypeError:
        legacy_effort = None if effort is SETTINGS_UNSET else effort
        return updater(model, legacy_effort, None)


def _protocol_nullable_setting(value: Any) -> Any:
    if value is SETTINGS_UNSET or type(value) is object:
        return SETTINGS_UNSET
    return value


def _response_input_item_to_response_item(item: Any) -> ResponseItem:
    if isinstance(item, ResponseItem):
        return item
    converter = getattr(ResponseItem, "from_response_input_item", None)
    if callable(converter):
        try:
            return converter(item)
        except Exception:
            pass
    return ResponseItem.from_mapping(item)


def _field_or_mapping(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


async def _call_required(target: Any, name: str, *args: Any) -> Any:
    method = getattr(target, name, None)
    if not callable(method):
        raise CodexThreadError(f"target does not provide {name}")
    return await _maybe_await(method(*args))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "ActiveTurnInjectionRejected",
    "CodexThread",
    "CodexThreadError",
    "CodexThreadSettingsOverrides",
    "InvalidThreadRequest",
    "SessionSettingsUpdate",
    "ThreadConfigSnapshot",
]
