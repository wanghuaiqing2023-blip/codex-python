"""Runtime composition for Rust ``codex-tui::app``.

Rust source: ``codex/codex-rs/tui/src/app.rs``.

This module owns the Python product-path equivalent of Rust's dynamic graph:
``AppCommand::UserTurn`` is routed through the active thread, the active thread
emits app-server notifications, and ``chatwidget::protocol`` consumes those
notifications to update turn, streaming, status, and redraw state.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import webbrowser
from dataclasses import dataclass, field, fields as dataclass_fields, is_dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
from types import SimpleNamespace
from typing import Any, Callable, Mapping, MutableMapping, Protocol

from pycodex.core.config.edit import ConfigEdit, ConfigEditsBuilder
from pycodex.core.event_mapping import parse_turn_item
from pycodex.exec.local_runtime import (
    _local_http_prompt_visible_rollout_items,
    final_text_from_local_http_exec_result,
    local_http_apply_patch_approval_keys,
    local_http_shell_tool_approval_keys,
    persist_core_exec_rollout,
    prewarm_exec_core_websocket_session,
    run_exec_user_turn_core_sampling_websocket_preferred,
)
from pycodex.core.tools.sandboxing import ApprovalStore
from pycodex.exec.run import ExecRunPlan, InitialOperation
from pycodex.protocol import ActivePermissionProfile, ApprovalsReviewer, AskForApproval, ExecApprovalRequestEvent, NetworkPolicyAmendment, NetworkPolicyRuleAction, PermissionProfile, ResponseInputItem, ResponseItem, ReviewDecision, ReviewRequest, ReviewTarget, ThreadGoal as ProtocolThreadGoal, ThreadGoalStatus as ProtocolThreadGoalStatus, ThreadId, TurnItem, UserInput
from pycodex.protocol.request_permissions import (
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsResponse,
)
from pycodex.utils.approval_presets import builtin_approval_presets

from ..app_command import AppCommand
from ..app_event import AppEvent, RateLimitRefreshOrigin
from ..app_server_session import app_server_rate_limit_snapshots
from ..chatwidget.input_submission import UserMessage, UserMessageHistoryRecord, submit_user_message_with_history_record
from ..chatwidget.protocol import ChatWidgetProtocolRuntime, HistoryProjectionSink, ServerNotification
from ..chatwidget.protocol_requests import ServerRequest
from ..chatwidget.replay import ReplayKind as ChatWidgetReplayKind
from ..chatwidget.replay import replay_thread_turns
from ..config_update import build_model_selection_edits, write_config_batch
from ..history_cell.notices import new_info_event
from ..status.rate_limits import RateLimitSnapshotDisplay, RateLimitWindowDisplay, rate_limit_snapshot_display_for_limit
from .agent_navigation import (
    AgentNavigationDirection,
    AgentNavigationState,
    format_agent_picker_item_name,
)
from .app_server_events import (
    AppServerEventPlan,
    plan_app_server_event,
    refresh_mcp_startup_expected_servers_from_config,
)
from .app_server_requests import AppServerRequestResolution, PendingAppServerRequests
from .event_dispatch import EventDispatchPlan, EventDispatchState, dispatch_event_plan
from .thread_routing import (
    ThreadInteractiveRequest,
    ThreadRoutingPlan,
    ThreadRoutingState,
    active_thread_event_plan,
    interactive_request_for_thread_request,
    submit_active_thread_op_plan,
)
from .thread_events import ThreadBufferedEvent, ThreadEventSnapshot, ThreadEventStore
from .side import (
    SideThreadState,
    SideUiState,
    active_side_parent_thread_id as side_active_parent_thread_id,
    side_thread_to_discard_after_switch,
)

RUST_MODULE_CRATE = "codex-tui"
RUST_MODULE = "app"
RUST_SOURCE = "codex/codex-rs/tui/src/app.rs"


@dataclass(frozen=True)
class _RateLimitsBearerAuthProvider:
    token: str
    account_id: str | None = None
    is_fedramp_account: bool = False

    def to_auth_headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.account_id:
            headers["ChatGPT-Account-ID"] = self.account_id
        if self.is_fedramp_account:
            headers["X-OpenAI-Fedramp"] = "true"
        return headers


class ActiveThreadEventStream(Protocol):
    def next_event(self, timeout: float | None = None) -> ServerNotification | None:
        ...


class ActiveThreadRuntime(Protocol):
    def submit_thread_op(self, thread_id: str, op: AppCommand) -> ActiveThreadEventStream:
        ...

    def shutdown_thread(self, thread_id: str) -> ActiveThreadEventStream:
        ...


_EOF = object()


def _first_runtime_config_source(*candidates: Any) -> Any | None:
    config_fields = {
        "hide_agent_reasoning",
        "show_raw_agent_reasoning",
        "model_reasoning_effort",
        "reasoning_effort",
        "model_reasoning_summary",
    }
    for candidate in candidates:
        if candidate is not None and any(hasattr(candidate, name) for name in config_fields):
            return candidate
    return None


def _timing_trace(event: str, **fields: Any) -> None:
    path = os.environ.get("PYCODEX_TUI_TIMING_LOG")
    if not path:
        return
    record = {"t": time.monotonic(), "event": event, **fields}
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError:
        return


def _run_coro_blocking(coro: Any) -> Any:
    """Run an async Rust-shaped helper from the sync terminal runtime."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - re-raised below
            box["error"] = exc

    thread = Thread(target=worker, name="pycodex-tui-config-write", daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _close_model_session(session: Any) -> None:
    if session is None:
        return
    reset = getattr(session, "reset_websocket_session", None)
    if callable(reset):
        reset()
    close = getattr(session, "close", None)
    if callable(close):
        close()


def _request_handle_from_runtime(runtime: Any) -> Any:
    for name in ("request_handle", "get_request_handle"):
        candidate = getattr(runtime, name, None)
        if callable(candidate):
            return candidate()
        if candidate is not None:
            return candidate
    for container_name in ("app_server", "app_server_session", "server"):
        container = getattr(runtime, container_name, None)
        if container is None:
            continue
        candidate = getattr(container, "request_handle", None)
        if callable(candidate):
            return candidate()
        if candidate is not None:
            return candidate
    return None


def _config_from_runtime(runtime: Any) -> Any:
    first_config = None
    for name in ("session_config", "config"):
        value = getattr(runtime, name, None)
        if value is None:
            continue
        if first_config is None:
            first_config = value
        if _config_has_write_target(value):
            return value
    if _config_has_write_target(runtime):
        return runtime
    codex_home = _runtime_codex_home(runtime, first_config)
    if codex_home is None:
        return first_config
    if first_config is None:
        return SimpleNamespace(codex_home=codex_home, config_layer_stack=None)
    if isinstance(first_config, MutableMapping):
        first_config.setdefault("codex_home", codex_home)
        first_config.setdefault("config_layer_stack", None)
        return first_config
    try:
        setattr(first_config, "codex_home", codex_home)
        if not hasattr(first_config, "config_layer_stack"):
            setattr(first_config, "config_layer_stack", None)
        return first_config
    except Exception:
        return SimpleNamespace(
            codex_home=codex_home,
            config_layer_stack=getattr(first_config, "config_layer_stack", None),
        )


def _config_has_write_target(config: Any) -> bool:
    if config is None:
        return False
    layer_stack = _field(config, "config_layer_stack", None)
    get_user_config_file = getattr(layer_stack, "get_user_config_file", None)
    if callable(get_user_config_file):
        try:
            if get_user_config_file() is not None:
                return True
        except Exception:
            return True
    return _field(config, "codex_home", None) is not None


def _runtime_codex_home(runtime: Any, config: Any = None) -> Path | None:
    for source in (runtime, config):
        value = _field(source, "codex_home", None)
        if value is not None:
            return Path(value)
    try:
        from pycodex.utils.home_dir import find_codex_home

        return find_codex_home()
    except Exception:
        return None


def _effort_config_value(effort: Any) -> str | None:
    if effort is None:
        return None
    if isinstance(effort, Enum):
        value = effort.value
    else:
        value = effort
    text = str(value)
    if "." in text and text.rsplit(".", 1)[-1] in {
        "Minimal",
        "Low",
        "Medium",
        "High",
        "XHigh",
        "Max",
        "Ultra",
        "None",
    }:
        text = text.rsplit(".", 1)[-1]
    normalized = text.strip().replace("-", "_").lower()
    aliases = {
        "none": None,
        "none_": None,
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "x_high": "xhigh",
        "extra_high": "xhigh",
        "extra high": "xhigh",
        "max": "max",
        "ultra": "ultra",
    }
    return aliases.get(normalized, normalized or None)


def _reasoning_label_for(model: str, effort: Any) -> str | None:
    if model.startswith("codex-auto-"):
        return None
    return _effort_config_value(effort) or "default"


def _rate_limit_origin_kind(origin: Any) -> str | None:
    if origin is None:
        return None
    if isinstance(origin, Mapping):
        return origin.get("kind") or origin.get("type") or origin.get("variant")
    return getattr(origin, "kind", None)


def _rate_limit_origin_request_id(origin: Any) -> int | None:
    if origin is None:
        return None
    if isinstance(origin, Mapping):
        value = origin.get("request_id") or origin.get("requestId")
    else:
        value = getattr(origin, "request_id", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rate_limit_result_snapshots(result: Any) -> list[Any] | None:
    if result is None or isinstance(result, BaseException):
        return None
    if isinstance(result, Mapping) and ("error" in result or "err" in result):
        return None
    if _mapping_or_attr(result, "rate_limits", "rateLimits") is not None:
        return list(app_server_rate_limit_snapshots(result))
    by_id = _mapping_or_attr(result, "rate_limits_by_limit_id", "rateLimitsByLimitId")
    if by_id:
        if isinstance(by_id, Mapping):
            return list(by_id.values())
        try:
            return list(by_id)
        except TypeError:
            return [by_id]
    primary = _mapping_or_attr(result, "rate_limits", "rateLimits")
    if primary is not None:
        return [primary]
    if isinstance(result, Mapping) and _looks_like_rate_limit_snapshot(result):
        return [result]
    if isinstance(result, (RateLimitSnapshotDisplay, RateLimitWindowDisplay)):
        return [result]
    try:
        return list(result)
    except TypeError:
        return [result]


def _rate_limit_snapshot_display(snapshot: Any) -> RateLimitSnapshotDisplay:
    if isinstance(snapshot, RateLimitSnapshotDisplay):
        return snapshot
    if isinstance(snapshot, RateLimitWindowDisplay):
        return RateLimitSnapshotDisplay("codex", datetime.now().astimezone(), primary=snapshot)
    limit_name = _mapping_or_attr(snapshot, "limit_name", "limitName", "limit_id", "limitId") or "codex"
    return rate_limit_snapshot_display_for_limit(snapshot, str(limit_name), datetime.now().astimezone())


def _store_runtime_rate_limit_snapshot(runtime: Any, snapshot: RateLimitSnapshotDisplay) -> None:
    for target in (runtime, getattr(runtime, "session_config", None), getattr(runtime, "model_client", None)):
        if target is None:
            continue
        current = getattr(target, "rate_limit_snapshots_by_limit_id", None)
        if current is None:
            current = {}
            try:
                setattr(target, "rate_limit_snapshots_by_limit_id", current)
            except Exception:
                continue
        if isinstance(current, dict):
            current[snapshot.limit_name] = snapshot
        try:
            setattr(target, "latest_rate_limits", snapshot)
        except Exception:
            pass


def _rate_limits_backend_base_url(session_config: Any, provider: Any) -> str | None:
    for source in (session_config, getattr(session_config, "config", None)):
        value = _mapping_or_attr(source, "chatgpt_base_url", "chatgptBaseUrl")
        if isinstance(value, str) and value.strip():
            return value.strip().rstrip("/")
    value = _mapping_or_attr(provider, "base_url", "baseUrl")
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().rstrip("/")
    if normalized.endswith("/backend-api/codex"):
        return normalized[: -len("/codex")]
    return normalized


def _rate_limits_auth_account_id(auth: Any) -> str | None:
    if auth is None:
        return None
    method = getattr(auth, "get_account_id", None)
    value = method() if callable(method) else _mapping_or_attr(auth, "account_id", "accountId")
    tokens = _mapping_or_attr(auth, "tokens")
    if not value and isinstance(tokens, Mapping):
        value = tokens.get("account_id") or tokens.get("accountId")
    return str(value) if value is not None else None


def _rate_limits_auth_is_fedramp(auth: Any) -> bool:
    if auth is None:
        return False
    method = getattr(auth, "is_fedramp_account", None)
    if callable(method):
        return bool(method())
    value = _mapping_or_attr(auth, "is_fedramp_account", "isFedrampAccount", "chatgpt_account_is_fedramp")
    if value is not None:
        return bool(value)
    tokens = _mapping_or_attr(auth, "tokens")
    if isinstance(tokens, Mapping):
        return bool(tokens.get("chatgpt_account_is_fedramp") or tokens.get("is_fedramp_account"))
    return False


def _rate_limits_backend_auth_provider(auth: Any) -> Any | None:
    if auth is None:
        return None
    if callable(getattr(auth, "to_auth_headers", None)) or callable(getattr(auth, "add_auth_headers", None)):
        return auth
    token_method = getattr(auth, "get_token", None)
    token = token_method() if callable(token_method) else _mapping_or_attr(auth, "token", "access_token", "accessToken")
    tokens = _mapping_or_attr(auth, "tokens")
    if not token and isinstance(tokens, Mapping):
        token = tokens.get("access_token") or tokens.get("accessToken")
    if not isinstance(token, str) or not token:
        return None
    return _RateLimitsBearerAuthProvider(
        token=token,
        account_id=_rate_limits_auth_account_id(auth),
        is_fedramp_account=_rate_limits_auth_is_fedramp(auth),
    )


def _normalized_auth_dot_json_snapshot(auth: Any) -> Any:
    try:
        from pycodex.login.auth.storage import AuthDotJson
    except Exception:
        return auth
    if not hasattr(auth, "auth_mode") and not isinstance(auth, Mapping):
        return auth
    if isinstance(auth, Mapping):
        return AuthDotJson.from_mapping(auth)
    tokens = getattr(auth, "tokens", None)
    if tokens is not None and not isinstance(tokens, Mapping):
        return auth
    data: dict[str, Any] = {}
    for attr, key in (
        ("auth_mode", "auth_mode"),
        ("openai_api_key", "OPENAI_API_KEY"),
        ("tokens", "tokens"),
        ("last_refresh", "last_refresh"),
        ("agent_identity", "agent_identity"),
    ):
        value = getattr(auth, attr, None)
        if value is not None:
            if key == "last_refresh" and isinstance(value, datetime):
                value = value.isoformat()
            data[key] = value
    return AuthDotJson.from_mapping(data)


def _models_auth_manager_from_snapshot(codex_home: Path | str, auth: Any, chatgpt_base_url: str | None) -> Any | None:
    if auth is None:
        return None
    if callable(getattr(auth, "auth", None)) and callable(getattr(auth, "auth_cached", None)):
        return auth
    try:
        from pycodex.login.auth.manager import AuthManager, CodexAuth

        if callable(getattr(auth, "auth_mode", None)) and callable(getattr(auth, "get_token", None)):
            return AuthManager.from_auth_for_testing_with_home(auth, codex_home)
        if hasattr(auth, "auth_mode"):
            codex_auth = _run_coro_blocking(
                CodexAuth.from_auth_dot_json(
                    codex_home,
                    _normalized_auth_dot_json_snapshot(auth),
                    "file",
                    chatgpt_base_url,
                )
            )
            return AuthManager.from_auth_for_testing_with_home(codex_auth, codex_home)
    except Exception:
        return None
    return None


def _mapping_or_attr(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, Mapping):
            if name in value:
                return value[name]
        else:
            candidate = getattr(value, name, None)
            if candidate is not None:
                return candidate() if callable(candidate) else candidate
    return None


def _looks_like_rate_limit_snapshot(value: Mapping[str, Any]) -> bool:
    return bool(set(value.keys()) & {"primary", "secondary", "credits", "limit_id", "limitId", "limit_name", "limitName"})


@dataclass
class QueueActiveThreadEventStream:
    queue: Queue[Any]
    closed: bool = False

    def next_event(self, timeout: float | None = None) -> ServerNotification | None:
        try:
            value = self.queue.get(timeout=timeout)
        except Empty:
            return None
        if value is _EOF:
            self.closed = True
            return None
        return value


def _closed_event_stream() -> QueueActiveThreadEventStream:
    queue: Queue[Any] = Queue()
    queue.put(_EOF)
    return QueueActiveThreadEventStream(queue)


def _apply_override_turn_context_to_runtime(runtime: Any, op: AppCommand) -> None:
    """Apply Rust ``AppCommand::OverrideTurnContext`` to cached session state.

    Rust ``codex-tui::app`` treats this as a settings update for the active
    thread, not as a model turn.  Keep the Python product path on the same
    boundary so a permissions popup selection affects the very next user turn.
    """

    payload = op.payload if isinstance(op.payload, Mapping) else {}
    updates: dict[str, Any] = {}
    for name in (
        "cwd",
        "approval_policy",
        "approvals_reviewer",
        "permission_profile",
        "active_permission_profile",
        "windows_sandbox_level",
        "model",
        "service_tier",
        "collaboration_mode",
        "personality",
    ):
        if payload.get(name) is None:
            continue
        updates[name] = payload[name]
        _set_attr_or_key_silent(runtime, name, payload[name])
    if payload.get("effort") is not None:
        updates["reasoning_effort"] = payload["effort"]
        updates["model_reasoning_effort"] = payload["effort"]
        _set_attr_or_key_silent(runtime, "reasoning_effort", payload["effort"])
        _set_attr_or_key_silent(runtime, "model_reasoning_effort", payload["effort"])
    if payload.get("summary") is not None:
        updates["reasoning_summary"] = payload["summary"]
        updates["model_reasoning_summary"] = payload["summary"]
        _set_attr_or_key_silent(runtime, "reasoning_summary", payload["summary"])
        _set_attr_or_key_silent(runtime, "model_reasoning_summary", payload["summary"])

    permission_profile = payload.get("permission_profile")
    if permission_profile is not None:
        cwd = payload.get("cwd") or getattr(getattr(runtime, "session_config", None), "cwd", None) or getattr(runtime, "cwd", ".")
        fs_policy = _call_permission_profile_method(permission_profile, "file_system_sandbox_policy")
        sandbox_policy = _call_permission_profile_method(permission_profile, "to_legacy_sandbox_policy", cwd)
        updates["file_system_sandbox_policy"] = fs_policy
        _set_attr_or_key_silent(runtime, "file_system_sandbox_policy", fs_policy)
        if sandbox_policy is not None:
            updates["sandbox_policy"] = sandbox_policy
            _set_attr_or_key_silent(runtime, "sandbox_policy", sandbox_policy)
    _apply_session_config_updates(runtime, updates)


def _apply_session_config_updates(runtime: Any, updates: Mapping[str, Any]) -> None:
    session_config = getattr(runtime, "session_config", None)
    if session_config is None or not updates:
        return
    if is_dataclass(session_config) and not isinstance(session_config, type):
        field_names = {field.name for field in dataclass_fields(session_config)}
        replace_updates = {name: value for name, value in updates.items() if name in field_names}
        if replace_updates:
            try:
                runtime.session_config = replace(session_config, **replace_updates)
                return
            except (TypeError, ValueError):
                pass
    for name, value in updates.items():
        _set_attr_or_key_silent(session_config, name, value)


def _call_permission_profile_method(profile: Any, name: str, *args: Any) -> Any:
    method = getattr(profile, name, None)
    if not callable(method):
        return None
    try:
        return method(*args)
    except Exception:
        return None


def _set_attr_or_key_silent(target: Any, name: str, value: Any) -> None:
    if target is None:
        return
    try:
        setattr(target, name, value)
        return
    except (AttributeError, TypeError):
        pass
    if isinstance(target, MutableMapping):
        target[name] = value


def _clean_background_terminals_for_runtime(runtime: Any) -> None:
    """Mirror Rust core ``session::handlers::clean_background_terminals``.

    Product TUI active-thread runtimes can be backed by a full session object,
    a session config carrying services, or a lightweight test/runtime object.
    Rust ultimately calls ``Session::close_unified_exec_processes``; Python
    follows that hook first and then falls back to the ported unified-exec
    manager when it is exposed through services.
    """

    for source in (
        runtime,
        getattr(runtime, "session", None),
        getattr(runtime, "session_config", None),
    ):
        cleaner = getattr(source, "close_unified_exec_processes", None)
        if callable(cleaner):
            result = cleaner()
            if hasattr(result, "__await__"):
                _run_coro_blocking(result)
            return

    for source in (
        runtime,
        getattr(runtime, "session", None),
        getattr(runtime, "session_config", None),
        getattr(getattr(runtime, "session_config", None), "services", None),
        getattr(getattr(runtime, "session", None), "services", None),
    ):
        manager = getattr(source, "unified_exec_manager", None)
        terminator = getattr(manager, "terminate_all_processes", None)
        if callable(terminator):
            terminator()
            return


@dataclass
class _PendingExecApproval:
    event: Event = field(default_factory=Event)
    decision: Any = None


@dataclass
class _ActiveCoreTurn:
    thread_id: str
    turn_id: str
    queue: Queue[Any]
    lock: Lock = field(default_factory=Lock)
    cancel_event: Event = field(default_factory=Event)
    terminal_sent: bool = False
    cancellation_requested: bool = False
    pending_exec_approvals: dict[str, _PendingExecApproval] = field(default_factory=dict)
    pending_permission_requests: dict[str, _PendingExecApproval] = field(default_factory=dict)
    pending_patch_approvals: dict[str, _PendingExecApproval] = field(default_factory=dict)

    def put(self, notification: Any) -> bool:
        with self.lock:
            if self.terminal_sent:
                return False
            self.queue.put(notification)
            return True

    def finish(self, notification: ServerNotification) -> bool:
        with self.lock:
            if self.terminal_sent:
                return False
            self.terminal_sent = True
            self.queue.put(notification)
            self.queue.put(_EOF)
            return True

    def interrupt(self) -> bool:
        with self.lock:
            self.cancellation_requested = True
            self.cancel_event.set()
            pending_request_ids = (
                *self.pending_exec_approvals.keys(),
                *self.pending_permission_requests.keys(),
                *self.pending_patch_approvals.keys(),
            )
            for pending in self.pending_exec_approvals.values():
                pending.decision = ReviewDecision.abort()
                pending.event.set()
            self.pending_exec_approvals.clear()
            for pending in self.pending_permission_requests.values():
                pending.decision = RequestPermissionsResponse(RequestPermissionProfile())
                pending.event.set()
            self.pending_permission_requests.clear()
            for pending in self.pending_patch_approvals.values():
                pending.decision = ReviewDecision.abort()
                pending.event.set()
            self.pending_patch_approvals.clear()
            if self.terminal_sent:
                return False
            self.terminal_sent = True
            for request_id in pending_request_ids:
                self.queue.put(
                    ServerNotification(
                        "ServerRequestResolved",
                        {"request_id": str(request_id)},
                    )
                )
            self.queue.put(_turn_interrupted_notification(self.thread_id, self.turn_id))
            self.queue.put(_EOF)
            return True

    def is_terminal_sent(self) -> bool:
        with self.lock:
            return self.terminal_sent

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    async def cancelled(self) -> None:
        # Event.wait() in asyncio.to_thread cannot be interrupted: cancelling
        # the coroutine leaves its worker thread blocked, and asyncio.run()
        # then waits for that default-executor thread during shutdown. A short
        # async poll mirrors Rust's cancellable token without leaking a waiter.
        while not self.cancel_event.is_set():
            await asyncio.sleep(0.05)

    def request_exec_approval(
        self,
        *,
        approval_id: str,
        call_id: str | None = None,
        command: Any,
        cwd: str | None,
        reason: str | None,
        network_approval_context: Any = None,
        proposed_execpolicy_amendment: Any = None,
        additional_permissions: Any = None,
        available_decisions: Any = None,
    ) -> ReviewDecision:
        effective_call_id = str(call_id or approval_id)
        command_tokens = (command,) if isinstance(command, str) else tuple(str(part) for part in command)
        network_amendments = None
        if network_approval_context is not None:
            host = str(getattr(network_approval_context, "host", ""))
            network_amendments = (
                NetworkPolicyAmendment(host, NetworkPolicyRuleAction.ALLOW),
                NetworkPolicyAmendment(host, NetworkPolicyRuleAction.DENY),
            )
        normalized_decisions = (
            None
            if available_decisions is None
            else tuple(ReviewDecision.from_mapping(item) for item in available_decisions)
        )
        request_event = ExecApprovalRequestEvent(
            call_id=effective_call_id,
            approval_id=approval_id if approval_id != effective_call_id else None,
            turn_id=self.turn_id,
            started_at_ms=int(time.time() * 1000),
            command=command_tokens,
            cwd=Path(cwd or "."),
            reason=reason,
            network_approval_context=network_approval_context,
            proposed_execpolicy_amendment=proposed_execpolicy_amendment,
            proposed_network_policy_amendments=network_amendments,
            additional_permissions=additional_permissions,
            available_decisions=normalized_decisions,
        )
        request_params = request_event.to_mapping()
        request_params["approval_id"] = approval_id
        pending = _PendingExecApproval()
        with self.lock:
            if self.terminal_sent or self.cancel_event.is_set():
                return ReviewDecision.abort()
            self.pending_exec_approvals[approval_id] = pending
            self.queue.put(
                ServerRequest(
                    "CommandExecutionRequestApproval",
                    id=approval_id,
                    params={"thread_id": self.thread_id, **request_params},
                )
            )

        while not pending.event.wait(0.1):
            if self.cancel_event.is_set():
                return ReviewDecision.abort()
        try:
            return ReviewDecision.from_mapping(pending.decision)
        except Exception:
            return ReviewDecision.abort()

    def resolve_exec_approval(self, approval_id: str, decision: Any) -> bool:
        with self.lock:
            pending = self.pending_exec_approvals.pop(str(approval_id), None)
            if pending is None:
                return False
            pending.decision = decision
            pending.event.set()
            return True

    def request_permissions(
        self,
        *,
        call_id: str,
        args: RequestPermissionsArgs,
        cwd: Path,
    ) -> RequestPermissionsResponse:
        pending = _PendingExecApproval()
        with self.lock:
            if self.terminal_sent or self.cancel_event.is_set():
                return RequestPermissionsResponse(RequestPermissionProfile())
            self.pending_permission_requests[call_id] = pending
            self.queue.put(
                ServerRequest(
                    "PermissionsRequestApproval",
                    id=call_id,
                    params={
                        "call_id": call_id,
                        "thread_id": self.thread_id,
                        "turn_id": self.turn_id,
                        "started_at_ms": 0,
                        "reason": args.reason,
                        "permissions": args.permissions.to_mapping(),
                        "cwd": str(cwd),
                    },
                )
            )
        while not pending.event.wait(0.1):
            if self.cancel_event.is_set():
                return RequestPermissionsResponse(RequestPermissionProfile())
        try:
            if isinstance(pending.decision, RequestPermissionsResponse):
                return pending.decision
            return RequestPermissionsResponse.from_mapping(pending.decision)
        except Exception:
            return RequestPermissionsResponse(RequestPermissionProfile())

    def resolve_permissions(self, call_id: str, response: Any) -> bool:
        with self.lock:
            pending = self.pending_permission_requests.pop(str(call_id), None)
            if pending is None:
                return False
            pending.decision = response
            pending.event.set()
            return True

    def request_patch_approval(
        self,
        *,
        call_id: str,
        changes: Mapping[Path, Any],
        cwd: Path,
        reason: str | None = None,
        grant_root: Path | None = None,
    ) -> ReviewDecision:
        pending = _PendingExecApproval()
        with self.lock:
            if self.terminal_sent or self.cancel_event.is_set():
                return ReviewDecision.abort()
            self.pending_patch_approvals[call_id] = pending
            self.queue.put(
                ServerRequest(
                    "FileChangeRequestApproval",
                    id=call_id,
                    params={
                        "call_id": call_id,
                        "thread_id": self.thread_id,
                        "turn_id": self.turn_id,
                        "started_at_ms": 0,
                        "changes": dict(changes),
                        "reason": reason,
                        "grant_root": None if grant_root is None else str(grant_root),
                        "cwd": str(cwd),
                    },
                )
            )
        while not pending.event.wait(0.1):
            if self.cancel_event.is_set():
                return ReviewDecision.abort()
        try:
            return ReviewDecision.from_mapping(pending.decision)
        except Exception:
            return ReviewDecision.abort()

    def resolve_patch_approval(self, call_id: str, decision: Any) -> bool:
        with self.lock:
            pending = self.pending_patch_approvals.pop(str(call_id), None)
            if pending is None:
                return False
            pending.decision = decision
            pending.event.set()
            return True


@dataclass
class ExecFunctionActiveThreadRuntime:
    """Adapt the current exec implementation to Rust-style notifications.

    The wrapped callable is intentionally below the TUI runtime boundary.  The
    TUI submits an ``AppCommand`` and observes server notifications; it no
    longer synchronously waits for the callable's final return value.
    """

    execute_prompt: Callable[[str], int | tuple[int, str]]

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> ActiveThreadEventStream:
        if op.kind == "Interrupt":
            return _closed_event_stream()
        if op.kind == "CleanBackgroundTerminals":
            _clean_background_terminals_for_runtime(self)
            return _closed_event_stream()
        if op.kind == "OverrideTurnContext":
            _apply_override_turn_context_to_runtime(self, op)
            return _closed_event_stream()
        if op.kind == "ApproveGuardianDeniedAction":
            return _closed_event_stream()
        queue: Queue[Any] = Queue()
        turn_id = "terminal-turn"
        prompt = user_turn_prompt(op)

        def worker() -> None:
            queue.put(ServerNotification("TurnStarted", {"turn": {"id": turn_id, "thread_id": thread_id}}))
            try:
                result = self.execute_prompt(prompt)
                if isinstance(result, tuple):
                    code, output = result
                else:
                    code, output = result, ""
                if output:
                    queue.put(ServerNotification("AgentMessageDelta", {"delta": str(output), "thread_id": thread_id}))
                if code == 0:
                    queue.put(
                        ServerNotification(
                            "TurnCompleted",
                            {"turn": {"id": turn_id, "thread_id": thread_id, "status": "Completed", "duration_ms": None}},
                        )
                    )
                else:
                    queue.put(
                        ServerNotification(
                            "TurnCompleted",
                            {
                                "turn": {
                                    "id": turn_id,
                                    "thread_id": thread_id,
                                    "status": "Failed",
                                    "error": {
                                        "message": str(output or f"exec exited with status {code}"),
                                        "codex_error_info": None,
                                        "exit_code": code,
                                    },
                                }
                            },
                        )
                    )
            except BaseException as exc:
                queue.put(
                    ServerNotification(
                        "TurnCompleted",
                        {
                            "turn": {
                                "id": turn_id,
                                "thread_id": thread_id,
                                "status": "Failed",
                                "error": {"message": str(exc), "codex_error_info": None, "exit_code": 1},
                            }
                        },
                    )
                )
            finally:
                queue.put(_EOF)

        Thread(target=worker, name="pycodex-tui-active-thread", daemon=True).start()
        return QueueActiveThreadEventStream(queue)

    def shutdown_thread(self, thread_id: str) -> ActiveThreadEventStream:
        queue: Queue[Any] = Queue()
        queue.put(ServerNotification("ThreadClosed", {"thread_id": thread_id}))
        queue.put(_EOF)
        return QueueActiveThreadEventStream(queue)


@dataclass
class CoreExecActiveThreadRuntime:
    """Run ``AppCommand::UserTurn`` through the core in-memory turn runtime.

    Rust ``codex-tui::app`` submits user turns to the active thread and observes
    app-server notifications.  This keeps the product TUI path on that shape:
    terminal input becomes an ``AppCommand`` and core sampling/session events
    become the notifications consumed by ``chatwidget::protocol``.
    """

    session_config: Any
    model_client: Any
    provider: Any
    model_info: Any
    auth: Any = None
    original_auth: Any = None
    codex_home: Path | str | None = None
    auth_manager: Any = None
    endpoint: str | None = None
    timeout: float | None = None
    opener: Any = None
    built_tools: Any = None
    max_tool_followups: int | None = None
    startup_prewarm_enabled: bool = False
    session_header_configured_at_startup: bool = True
    prewarmed_model_session: Any = None
    _models_manager: Any = field(default=None, init=False, repr=False)
    _startup_prewarm_ready: Event = field(default_factory=Event, init=False, repr=False)
    _startup_prewarm_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _startup_prewarm_session: Any = field(default=None, init=False, repr=False)
    _startup_prewarm_consumed: bool = field(default=False, init=False, repr=False)
    _startup_prewarm_started_at: float | None = field(default=None, init=False, repr=False)
    _startup_prewarm_timeout: float = field(default=0.0, init=False, repr=False)
    _active_turn_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _active_turn: _ActiveCoreTurn | None = field(default=None, init=False, repr=False)
    _tool_approvals_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _tool_approvals: ApprovalStore = field(default_factory=ApprovalStore, init=False, repr=False)
    _model_history_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _model_history_items: list[ResponseItem] = field(default_factory=list, init=False, repr=False)
    _rollout_path_ready: Event = field(default_factory=Event, init=False, repr=False)
    _last_worker_error: BaseException | None = field(default=None, init=False, repr=False)
    _startup_app_server_events: Queue[Any] = field(default_factory=Queue, init=False, repr=False)
    _state_runtime: Any = field(default=None, init=False, repr=False)
    rollout_path: Path | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._seed_configured_mcp_startup_events()
        if self.prewarmed_model_session is not None:
            self._startup_prewarm_session = self.prewarmed_model_session
            self._startup_prewarm_ready.set()
            return
        if self.startup_prewarm_enabled:
            self._schedule_startup_prewarm()

    def _with_cached_tool_approval(
        self,
        keys: tuple[Any, ...],
        fetch: Callable[[], ReviewDecision],
    ) -> ReviewDecision:
        """Mirror ``tools::sandboxing::with_cached_approval`` per TUI session."""

        if not keys:
            return fetch()
        approved_for_session = ReviewDecision.approved_for_session()
        with self._tool_approvals_lock:
            if all(self._tool_approvals.get(key) == approved_for_session for key in keys):
                return approved_for_session
        decision = ReviewDecision.from_mapping(fetch())
        if decision == approved_for_session:
            with self._tool_approvals_lock:
                for key in keys:
                    self._tool_approvals.put(key, approved_for_session)
        return decision

    @property
    def thread_id(self) -> str | None:
        return _model_client_state_value(self.model_client, "thread_id")

    @property
    def conversation_id(self) -> str | None:
        return self.thread_id

    @property
    def session_id(self) -> str | None:
        return _model_client_state_value(self.model_client, "session_id")

    def next_app_server_event(self, timeout: float | None = 0) -> object | None:
        try:
            wait = 0.0 if timeout is None else max(float(timeout), 0.0)
            return self._startup_app_server_events.get(timeout=wait)
        except Empty:
            return None

    def fetch_account_rate_limits(self) -> Any:
        """Fetch Codex backend rate limits through the Rust-shaped boundary.

        Rust ``codex-tui::app::background_requests::fetch_account_rate_limits``
        asks app-server for ``GetAccountRateLimits``; app-server delegates to
        codex-backend-client.  The local product TUI does not run the daemon, so
        this method provides the same active-thread request boundary directly.
        """

        auth = self.auth
        backend_auth = _rate_limits_backend_auth_provider(auth) or _rate_limits_backend_auth_provider(self.original_auth)
        base_url = _rate_limits_backend_base_url(self.session_config, self.provider)
        if backend_auth is None or not isinstance(base_url, str) or not base_url:
            raise RuntimeError("codex account authentication required to read rate limits")
        try:
            from pycodex.backend_client import Client

            client = Client.new(base_url).with_auth_provider(backend_auth)
            account_id = _rate_limits_auth_account_id(auth) or _rate_limits_auth_account_id(self.original_auth)
            if isinstance(account_id, str) and account_id:
                client = client.with_chatgpt_account_id(account_id)
            if _rate_limits_auth_is_fedramp(auth) or _rate_limits_auth_is_fedramp(self.original_auth):
                client = client.with_fedramp_routing_header()
            snapshots = client.get_rate_limits_many()
            if not snapshots:
                raise RuntimeError("failed to fetch codex rate limits: no snapshots returned")
            return snapshots
        except Exception:
            raise

    def models_manager(self) -> Any:
        """Return the Rust-shaped models manager backing TUI model pickers."""

        services = getattr(self.session_config, "services", None)
        manager = getattr(services, "models_manager", None)
        if manager is not None:
            return manager
        if self._models_manager is not None:
            return self._models_manager

        codex_home = self.codex_home or getattr(self.session_config, "codex_home", None)
        if codex_home is None:
            raise RuntimeError("codex_home is required to build the models manager")
        auth_manager = self.auth_manager or _models_auth_manager_from_snapshot(
            codex_home,
            self.original_auth or self.auth,
            getattr(self.session_config, "chatgpt_base_url", None),
        )
        try:
            from pycodex.model_provider import create_model_provider
            from pycodex.model_provider_info import ModelProviderInfo

            base_url = getattr(self.provider, "base_url", None)
            provider_info = ModelProviderInfo.create_openai_provider(
                str(base_url) if isinstance(base_url, str) and base_url else None
            )
            provider = create_model_provider(provider_info, auth_manager)
            self._models_manager = provider.models_manager(
                Path(codex_home),
                getattr(self.session_config, "model_catalog", None),
            )
        except Exception as exc:
            raise RuntimeError(f"failed to build models manager: {exc}") from exc
        return self._models_manager

    def try_list_models(self) -> list[Any]:
        """Mirror Rust ``ModelsManager::try_list_models`` for current catalog."""

        manager = self.models_manager()
        method = getattr(manager, "try_list_models", None)
        if not callable(method):
            return []
        return list(method() or [])

    def list_models(self, refresh_strategy: Any = None) -> list[Any]:
        """Mirror Rust ``ModelsManager::list_models`` with refresh support."""

        manager = self.models_manager()
        method = getattr(manager, "list_models", None)
        if not callable(method):
            return self.try_list_models()
        if refresh_strategy is None:
            try:
                from pycodex.models_manager import RefreshStrategy

                refresh_strategy = RefreshStrategy.ONLINE_IF_UNCACHED
            except Exception:
                refresh_strategy = "online_if_uncached"
        try:
            result = method(refresh_strategy)
        except TypeError:
            result = method()
        if hasattr(result, "__await__"):
            result = _run_coro_blocking(result)
        return list(result or [])

    def thread_goal_get(self, thread_id: str) -> Any:
        """Mirror Rust ``AppServerSession::thread_goal_get`` for local TUI.

        Rust TUI routes `/goal` through app-server thread goal requests backed
        by codex-state.  The local Python product path runs the core runtime
        in-process, so this facade provides the same app-server-shaped boundary
        over the local state runtime.
        """

        runtime = self._state_runtime_for_thread_goals()
        goal = _run_coro_blocking(runtime.thread_goals.get_thread_goal(_thread_goal_uuid(thread_id)))
        return None if goal is None else _app_server_thread_goal_from_state(goal)

    def thread_goal_set(
        self,
        thread_id: str,
        objective: str | None = None,
        status: Any = None,
        token_budget: Any = None,
    ) -> Any:
        """Mirror Rust ``AppServerSession::thread_goal_set`` for local TUI."""

        runtime = self._state_runtime_for_thread_goals()
        goals = runtime.thread_goals
        thread_id_text = _thread_goal_uuid(thread_id)
        state_status = _state_goal_status(status) if status is not None else None
        budget = _thread_goal_token_budget(token_budget)

        existing = _run_coro_blocking(goals.get_thread_goal(thread_id_text))
        if objective is not None:
            objective_text = str(objective).strip()
            if existing is None:
                goal = _run_coro_blocking(
                    goals.replace_thread_goal(
                        thread_id_text,
                        objective_text,
                        state_status or _default_active_goal_status(),
                        budget,
                    )
                )
            else:
                from pycodex.state.runtime.goals import GoalUpdate

                goal = _run_coro_blocking(
                    goals.update_thread_goal(
                        thread_id_text,
                        GoalUpdate(
                            objective=objective_text,
                            status=state_status,
                            token_budget=budget,
                            expected_goal_id=getattr(existing, "goal_id", None),
                        ),
                    )
                )
                if goal is None:
                    raise RuntimeError(f"cannot update goal for thread {thread_id_text}: no goal exists")
        else:
            if existing is None:
                raise RuntimeError(f"cannot update goal for thread {thread_id_text}: no goal exists")
            from pycodex.state.runtime.goals import GoalUpdate

            goal = _run_coro_blocking(
                goals.update_thread_goal(
                    thread_id_text,
                    GoalUpdate(
                        objective=None,
                        status=state_status,
                        token_budget=budget,
                        expected_goal_id=getattr(existing, "goal_id", None),
                    ),
                )
            )
            if goal is None:
                raise RuntimeError(f"cannot update goal for thread {thread_id_text}: no goal exists")

        api_goal = _app_server_thread_goal_from_state(goal)
        self._startup_app_server_events.put(
            {
                "kind": "ServerNotification",
                "notification": ServerNotification(
                    "ThreadGoalUpdated",
                    {"thread_id": thread_id_text, "turn_id": None, "goal": api_goal},
                ),
            }
        )
        return api_goal

    def goal_continuation_op(self, goal: Any) -> AppCommand | None:
        """Build Rust ``goals.rs`` idle-continuation input for an active goal.

        Rust ``GoalRuntimeEvent::ExternalSet`` calls
        ``maybe_continue_goal_if_idle_runtime`` when an externally set goal is
        active.  The continuation turn contains hidden ``<goal_context>`` user
        context, not a visible slash-command user message.  The local product
        runtime exposes the same boundary as an internal ``UserTurn`` marker
        consumed by ``exec_run_plan_for_app_command``.
        """

        protocol_goal = _protocol_thread_goal_from_any(goal)
        if protocol_goal.status is not ProtocolThreadGoalStatus.ACTIVE:
            return None
        from pycodex.core.goals import continuation_prompt

        prompt = continuation_prompt(protocol_goal)
        cwd = Path(getattr(self.session_config, "cwd", None) or Path.cwd())
        _timing_trace(
            "goal_continuation_op_created",
            objective=protocol_goal.objective,
            status=getattr(protocol_goal.status, "value", protocol_goal.status),
        )
        return _goal_continuation_app_command(prompt, cwd=cwd)

    def thread_goal_clear(self, thread_id: str) -> Any:
        """Mirror Rust ``AppServerSession::thread_goal_clear`` for local TUI."""

        runtime = self._state_runtime_for_thread_goals()
        thread_id_text = _thread_goal_uuid(thread_id)
        cleared = bool(_run_coro_blocking(runtime.thread_goals.delete_thread_goal(thread_id_text)))
        if cleared:
            self._startup_app_server_events.put(
                {
                    "kind": "ServerNotification",
                    "notification": ServerNotification(
                        "ThreadGoalCleared",
                        {"thread_id": thread_id_text},
                    ),
                }
            )
        return {"cleared": cleared}

    def _state_runtime_for_thread_goals(self) -> Any:
        if self._state_runtime is not None:
            return self._state_runtime
        codex_home = self.codex_home or getattr(self.session_config, "codex_home", None)
        if codex_home is None:
            raise RuntimeError("codex_home is required for thread goals")
        from pycodex.state.state_runtime import StateRuntime

        self._state_runtime = _run_coro_blocking(
            StateRuntime.init(
                Path(codex_home),
                _runtime_default_provider_id(self.session_config, self.provider),
            )
        )
        return self._state_runtime

    def workspace_command_runner(self) -> Any:
        """Return the Rust-shaped workspace-command runner for local TUI probes."""

        from ..workspace_command import LocalWorkspaceCommandRunner

        cwd = Path(getattr(self.session_config, "cwd", None) or Path.cwd())
        return LocalWorkspaceCommandRunner(default_cwd=cwd)

    def list_resume_threads(self) -> tuple[Any, ...]:
        """Return local thread summaries for the terminal `/resume` picker.

        Rust ownership is split here: ``codex-tui::resume_picker`` owns the
        picker UI, while ``codex-thread-store::local::list_threads`` owns the
        local rollout discovery contract.  The product runtime is the boundary
        that wires those two modules together.
        """

        try:
            from pycodex.thread_store import LocalThreadStore, LocalThreadStoreConfig
            from pycodex.thread_store import ListThreadsParams, SortDirection, ThreadSortKey

            codex_home = self.codex_home or getattr(self.session_config, "codex_home", None)
            if codex_home is None:
                return ()
            provider_id = (
                getattr(self.provider, "id", None)
                or getattr(self.provider, "name", None)
                or getattr(self.session_config, "default_model_provider_id", None)
                or getattr(self.session_config, "model_provider", None)
                or "openai"
            )
            store = LocalThreadStore(
                LocalThreadStoreConfig(
                    codex_home=Path(codex_home),
                    sqlite_home=Path(codex_home),
                    default_model_provider_id=str(provider_id),
                )
            )
            page = _run_coro_blocking(
                store.list_threads(
                    ListThreadsParams(
                        page_size=100,
                        cursor=None,
                        sort_key=ThreadSortKey.CREATED_AT,
                        sort_direction=SortDirection.DESC,
                    )
                )
            )
        except Exception:
            return ()
        return tuple(getattr(page, "items", ()) or ())

    def _message_history_config(self) -> Any | None:
        codex_home = self.codex_home or getattr(self.session_config, "codex_home", None)
        if codex_home is None:
            return None
        try:
            from pycodex.config.types import History
            from pycodex.message_history import HistoryConfig

            history = getattr(self.session_config, "history", None) or History()
            return HistoryConfig.new(Path(codex_home), history)
        except Exception:
            return None

    def message_history_metadata(self) -> tuple[int, int] | None:
        """Return Rust ``codex-message-history`` metadata for TUI session state."""

        config = self._message_history_config()
        if config is None:
            return None
        try:
            from pycodex.message_history import history_metadata

            log_id, entry_count = _run_coro_blocking(history_metadata(config))
            return (int(log_id), int(entry_count))
        except Exception:
            return None

    def lookup_message_history_entry(self, _thread_id: Any, log_id: int, offset: int) -> Any | None:
        """Lookup the persistent composer history entry requested by ``codex-tui``."""

        config = self._message_history_config()
        if config is None:
            return None
        try:
            from pycodex.message_history import lookup

            return lookup(int(log_id), int(offset), config)
        except Exception:
            return None

    def append_message_history_entry(self, text: str) -> None:
        """Persist a submitted user message to ``history.jsonl`` like Rust TUI."""

        config = self._message_history_config()
        if config is None:
            return
        conversation_id = self.conversation_id or self.session_id or "unknown"
        try:
            from pycodex.message_history import append_entry

            _run_coro_blocking(append_entry(text, conversation_id, config))
        except Exception:
            return

    def _seed_configured_mcp_startup_events(self) -> None:
        names = refresh_mcp_startup_expected_servers_from_config(self.session_config)
        for name in names:
            self._startup_app_server_events.put(
                {
                    "kind": "ServerNotification",
                    "notification": ServerNotification(
                        "McpServerStatusUpdated",
                        {"name": name, "status": "Starting"},
                    ),
                }
            )
            self._startup_app_server_events.put(
                {
                    "kind": "ServerNotification",
                    "notification": ServerNotification(
                        "McpServerStatusUpdated",
                        {
                            "name": name,
                            "status": "Failed",
                            "error": (
                                f"MCP client for `{name}` failed to start: "
                                "MCP runtime is not implemented in the PyCodex TUI"
                            ),
                        },
                    ),
                }
            )

    def submit_thread_op(self, thread_id: str, op: AppCommand) -> ActiveThreadEventStream:
        if op.kind == "Interrupt":
            with self._active_turn_lock:
                active_turn = self._active_turn
            if active_turn is not None:
                active_turn.interrupt()
            return _closed_event_stream()
        if op.kind == "ExecApproval":
            approval_id = str(op.payload.get("id", ""))
            decision = op.payload.get("decision")
            with self._active_turn_lock:
                active_turn = self._active_turn
            if active_turn is not None and approval_id:
                normalized = ReviewDecision.from_mapping(decision)
                if normalized == ReviewDecision.abort():
                    # Fixed Rust session::handlers::exec_approval interrupts
                    # the active task for Abort instead of resolving the tool
                    # waiter as an ordinary rejection.
                    active_turn.interrupt()
                else:
                    active_turn.resolve_exec_approval(approval_id, normalized)
            return _closed_event_stream()
        if op.kind == "RequestPermissionsResponse":
            call_id = str(op.payload.get("id", ""))
            response = op.payload.get("response")
            with self._active_turn_lock:
                active_turn = self._active_turn
            if active_turn is not None and call_id:
                active_turn.resolve_permissions(call_id, response)
            return _closed_event_stream()
        if op.kind == "PatchApproval":
            call_id = str(op.payload.get("id", ""))
            decision = op.payload.get("decision")
            with self._active_turn_lock:
                active_turn = self._active_turn
            if active_turn is not None and call_id:
                normalized = ReviewDecision.from_mapping(decision)
                if normalized == ReviewDecision.abort():
                    # Fixed Rust session::handlers::patch_approval shares the
                    # same turn-interrupt semantics as exec approval Abort.
                    active_turn.interrupt()
                else:
                    active_turn.resolve_patch_approval(call_id, normalized)
            return _closed_event_stream()
        if op.kind == "ApproveGuardianDeniedAction":
            from pycodex.core.session.handlers import guardian_denied_action_approval_items

            items = guardian_denied_action_approval_items(op.payload.get("event"))
            if items:
                with self._model_history_lock:
                    self._model_history_items.extend(items)
            return _closed_event_stream()
        if op.kind == "CleanBackgroundTerminals":
            _clean_background_terminals_for_runtime(self)
            return _closed_event_stream()
        if op.kind == "OverrideTurnContext":
            _apply_override_turn_context_to_runtime(self, op)
            return _closed_event_stream()
        queue: Queue[Any] = Queue()
        turn_id = "terminal-turn"
        active_turn = _ActiveCoreTurn(thread_id=thread_id, turn_id=turn_id, queue=queue)
        queue.put(_turn_started_notification(thread_id, turn_id))
        self._rollout_path_ready.clear()
        self._last_worker_error = None
        with self._active_turn_lock:
            self._active_turn = active_turn

        def worker() -> None:
            observed_delta = False
            observed_agent_message = False
            observed_error_message: str | None = None
            observed_terminal_notification: ServerNotification | None = None
            pending_commands: dict[str, dict[str, Any]] = {}
            completed_commands: set[str] = set()
            observed_live_kinds: set[str] = set()

            def observe_session_event(event: Any) -> None:
                nonlocal observed_delta, observed_agent_message, observed_error_message, observed_terminal_notification
                event_type = _field(event, "type")
                error_message = _session_event_error_message(event)
                if error_message:
                    observed_error_message = error_message
                notifications = _server_notifications_from_session_event(
                    event,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    pending_commands=pending_commands,
                    completed_commands=completed_commands,
                )
                _timing_trace(
                    "tui_session_event",
                    type=event_type,
                    notifications=tuple(notification.kind for notification in notifications),
                    items=tuple(
                        {
                            "kind": (
                                notification.payload.get("item", {}).get("kind")
                                if isinstance(notification.payload, dict)
                                and isinstance(notification.payload.get("item"), dict)
                                else None
                            ),
                            "command": (
                                notification.payload.get("item", {}).get("command")
                                if isinstance(notification.payload, dict)
                                and isinstance(notification.payload.get("item"), dict)
                                else None
                            ),
                        }
                        for notification in notifications
                    ),
                )
                for notification in notifications:
                    if notification.kind == "AgentMessageDelta":
                        observed_delta = True
                    elif notification.kind == "ItemCompleted":
                        payload = notification.payload
                        item = payload.get("item", {}) if isinstance(payload, dict) else {}
                        if isinstance(item, dict) and item.get("kind") == "AgentMessage":
                            observed_agent_message = True
                    if notification.kind == "TurnCompleted":
                        # The sampling result still has to be converted into
                        # completed tool items. Keep the terminal status, then
                        # close the queue after those items are enqueued.
                        observed_terminal_notification = notification
                        observed_live_kinds.add(notification.kind)
                        continue
                    observed_live_kinds.add(notification.kind)
                    active_turn.put(notification)

            try:
                previous_session_config = self.session_config

                def request_exec_approval(*args: Any) -> ReviewDecision:
                    if len(args) == 10:
                        (
                            _turn_context,
                            call_id,
                            approval_id,
                            command,
                            cwd_value,
                            reason,
                            network_approval_context,
                            proposed_execpolicy_amendment,
                            additional_permissions,
                            available_decisions,
                        ) = args
                        effective_approval_id = str(approval_id or call_id)
                        return active_turn.request_exec_approval(
                            approval_id=effective_approval_id,
                            call_id=str(call_id),
                            command=command,
                            cwd=str(cwd_value),
                            reason=None if reason is None else str(reason),
                            network_approval_context=network_approval_context,
                            proposed_execpolicy_amendment=proposed_execpolicy_amendment,
                            additional_permissions=additional_permissions,
                            available_decisions=available_decisions,
                        )
                    if len(args) != 4:
                        raise TypeError(
                            "exec approval callback expects either the legacy 4-argument "
                            "shell request or the typed 10-argument core request"
                        )
                    invocation, _config, requirement, meta = args
                    call_id = str(meta.get("call_id") or "exec-approval")
                    command = str(getattr(invocation, "command", "") or "")
                    cwd_value = getattr(invocation, "workdir", None) or getattr(previous_session_config, "cwd", None)
                    reason = getattr(requirement, "reason", None)
                    amendment = getattr(requirement, "proposed_execpolicy_amendment", None)
                    amendment_mapping = None
                    if amendment is not None:
                        to_mapping = getattr(amendment, "to_mapping", None)
                        amendment_mapping = to_mapping() if callable(to_mapping) else amendment
                    keys = local_http_shell_tool_approval_keys(
                        invocation,
                        _config,
                        granted_permissions=meta.get("granted_permissions"),
                    )
                    return self._with_cached_tool_approval(
                        keys,
                        lambda: active_turn.request_exec_approval(
                            approval_id=call_id,
                            call_id=call_id,
                            command=command,
                            cwd=None if cwd_value is None else str(cwd_value),
                            reason=None if reason is None else str(reason),
                            proposed_execpolicy_amendment=amendment_mapping,
                            available_decisions=None,
                        ),
                    )

                def request_permissions(
                    _parent_ctx: Any,
                    call_id: str,
                    args: RequestPermissionsArgs,
                    cwd: Path,
                    _cancel_token: Any,
                ) -> RequestPermissionsResponse:
                    return active_turn.request_permissions(
                        call_id=str(call_id),
                        args=args,
                        cwd=Path(cwd),
                    )

                def request_patch_approval(
                    call_id: str,
                    changes: Mapping[Path, Any],
                    cwd: Path,
                    reason: str | None,
                    grant_root: Path | None,
                ) -> ReviewDecision:
                    keys = local_http_apply_patch_approval_keys(changes, Path(cwd))
                    return self._with_cached_tool_approval(
                        keys,
                        lambda: active_turn.request_patch_approval(
                            call_id=str(call_id),
                            changes=changes,
                            cwd=Path(cwd),
                            reason=reason,
                            grant_root=grant_root,
                        ),
                    )

                try:
                    self.session_config = replace(
                        previous_session_config,
                        exec_approval_callback=request_exec_approval,
                        request_permissions_callback=request_permissions,
                        patch_approval_callback=request_patch_approval,
                    )
                except Exception:
                    self.session_config = previous_session_config
                model_session = self._take_startup_prewarm_session()
                result, turn_plan = asyncio.run(
                    self._run_op(
                        op,
                        session_event_observer=observe_session_event,
                        model_session=model_session,
                        cancellation_token=active_turn,
                    )
                )
                granted_session_permissions = getattr(
                    self.session_config,
                    "granted_session_permissions",
                    None,
                )
                if granted_session_permissions != getattr(
                    previous_session_config,
                    "granted_session_permissions",
                    None,
                ):
                    object.__setattr__(
                        previous_session_config,
                        "granted_session_permissions",
                        granted_session_permissions,
                    )
                self.session_config = previous_session_config
                emitted_delta = observed_delta or observed_agent_message
                for event in _server_notifications_from_session_events(
                    result,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    pending_commands=pending_commands,
                    completed_commands=completed_commands,
                ):
                    if event.kind in observed_live_kinds:
                        continue
                    if event.kind == "AgentMessageDelta":
                        emitted_delta = True
                    elif event.kind == "ItemCompleted":
                        payload = getattr(event, "payload", {})
                        item = payload.get("item", {}) if isinstance(payload, dict) else {}
                        if isinstance(item, dict) and item.get("kind") == "AgentMessage":
                            emitted_delta = True
                    active_turn.put(event)
                completion_notifications = _command_completion_notifications_from_result(
                    result,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    pending_commands=pending_commands,
                    completed_commands=completed_commands,
                )
                _timing_trace(
                    "tui_command_completion_projection",
                    pending=tuple(pending_commands),
                    completed=tuple(completed_commands),
                    tool_outputs=len(tuple(getattr(result, "tool_response_items", ()) or ())),
                    projected=len(completion_notifications),
                )
                for notification in completion_notifications:
                    active_turn.put(notification)
                final_text = final_text_from_local_http_exec_result(result)
                if final_text and not emitted_delta:
                    active_turn.put(ServerNotification("AgentMessageDelta", {"delta": final_text, "thread_id": thread_id, "turn_id": turn_id}))
                    emitted_delta = True
                if observed_error_message and not emitted_delta:
                    active_turn.finish(_turn_failed_notification(thread_id, turn_id, observed_error_message, exit_code=1))
                elif observed_terminal_notification is not None:
                    active_turn.finish(observed_terminal_notification)
                else:
                    active_turn.finish(_turn_completed_notification(thread_id, turn_id, result))
                # Rollout persistence is not part of Rust's visible event
                # ordering contract. Model-history normalization and rollout
                # I/O remain in the worker, but never hold command completion
                # or TurnCompleted behind bookkeeping.
                if not bool(op.payload.get("hidden_goal_context")):
                    self._record_model_history_from_turn(turn_plan, result)
                self._persist_rollout(turn_plan, result)
            except BaseException as exc:
                self._last_worker_error = exc
                _timing_trace("core_active_thread_worker_failed", error=str(exc))
                active_turn.finish(_turn_failed_notification(thread_id, turn_id, str(exc), exit_code=1))
            finally:
                try:
                    if "previous_session_config" in locals():
                        self.session_config = previous_session_config
                except Exception:
                    pass
                if not active_turn.is_terminal_sent():
                    active_turn.finish(_turn_failed_notification(thread_id, turn_id, "active thread event stream closed before turn completed", exit_code=1))
                with self._active_turn_lock:
                    if self._active_turn is active_turn:
                        self._active_turn = None

        Thread(target=worker, name="pycodex-tui-core-active-thread", daemon=True).start()
        return QueueActiveThreadEventStream(queue)

    def shutdown_thread(self, thread_id: str) -> ActiveThreadEventStream:
        with self._active_turn_lock:
            active_turn = self._active_turn
        if active_turn is not None:
            active_turn.interrupt()
        queue: Queue[Any] = Queue()
        queue.put(ServerNotification("ThreadClosed", {"thread_id": thread_id}))
        queue.put(_EOF)
        return QueueActiveThreadEventStream(queue)

    def close(self) -> None:
        """Release transport resources owned by the terminal active runtime.

        Rust ``codex-tui::app`` exits by dropping the app/session runtime, which
        releases websocket tasks and their receive loops.  Python keeps these
        objects behind explicit session caches, so the product TUI shutdown path
        must close them instead of relying on interpreter teardown.
        """

        with self._active_turn_lock:
            active_turn = self._active_turn
        if active_turn is not None:
            active_turn.interrupt()

        with self._startup_prewarm_lock:
            startup_session = self._startup_prewarm_session
            self._startup_prewarm_session = None
            self._startup_prewarm_consumed = True
        _close_model_session(startup_session)

        if self.prewarmed_model_session is not startup_session:
            _close_model_session(self.prewarmed_model_session)

        if self._state_runtime is not None:
            try:
                _run_coro_blocking(self._state_runtime.close())
            except Exception:
                pass
            self._state_runtime = None

        close_cached = getattr(self.model_client, "close_cached_websocket_session", None)
        if callable(close_cached):
            close_cached()

    def _schedule_startup_prewarm(self) -> None:
        new_session = getattr(self.model_client, "new_session", None)
        model = str(getattr(self.model_info, "slug", "") or "")
        if not callable(new_session) or not model:
            self._startup_prewarm_ready.set()
            return
        self._startup_prewarm_started_at = time.monotonic()
        self._startup_prewarm_timeout = self._startup_prewarm_timeout_seconds()
        _timing_trace("startup_prewarm_scheduled", timeout=self._startup_prewarm_timeout)

        def worker() -> None:
            try:
                session = new_session()
                _timing_trace("startup_prewarm_worker_started")
                session = asyncio.run(
                    prewarm_exec_core_websocket_session(
                        self.session_config,
                        self.model_client,
                        self.provider,
                        self.model_info,
                        auth=self.auth,
                        endpoint=self.endpoint,
                        timeout=self.timeout,
                        built_tools=self.built_tools,
                        auth_manager=self.auth_manager,
                        codex_home=self.codex_home,
                        model_session=session,
                    )
                )
                with self._startup_prewarm_lock:
                    if session is not None and not self._startup_prewarm_consumed:
                        self._startup_prewarm_session = session
                        _timing_trace("startup_prewarm_ready")
                        session = None
                    elif session is not None:
                        _timing_trace("startup_prewarm_ready_after_consumed")
                    else:
                        _timing_trace("startup_prewarm_unavailable")
                _close_model_session(session)
            except BaseException as exc:
                _timing_trace("startup_prewarm_failed", error=str(exc))
                pass
            finally:
                self._startup_prewarm_ready.set()

        Thread(target=worker, name="pycodex-tui-startup-prewarm", daemon=True).start()

    def _take_startup_prewarm_session(self) -> Any:
        with self._startup_prewarm_lock:
            if self._startup_prewarm_consumed:
                return None
        if self.startup_prewarm_enabled or self.prewarmed_model_session is not None:
            remaining = self._startup_prewarm_remaining_seconds()
            _timing_trace("startup_prewarm_resolve_wait", remaining=remaining)
            self._startup_prewarm_ready.wait(remaining)
        with self._startup_prewarm_lock:
            if self._startup_prewarm_consumed:
                return None
            self._startup_prewarm_consumed = True
            session = self._startup_prewarm_session
            self._startup_prewarm_session = None
            _timing_trace("startup_prewarm_resolved", ready=session is not None)
            return session

    def _startup_prewarm_remaining_seconds(self) -> float:
        if self.prewarmed_model_session is not None:
            return 0.0
        started_at = self._startup_prewarm_started_at
        if started_at is None:
            return 0.0
        age = max(time.monotonic() - started_at, 0.0)
        return max(self._startup_prewarm_timeout - age, 0.0)

    def _startup_prewarm_timeout_seconds(self) -> float:
        info_method = getattr(self.provider, "info", None)
        provider_info = info_method() if callable(info_method) else self.provider
        timeout_method = getattr(provider_info, "websocket_connect_timeout", None)
        if callable(timeout_method):
            try:
                return max(float(timeout_method()) / 1000.0, 0.0)
            except (TypeError, ValueError):
                return 0.0
        timeout_ms = getattr(provider_info, "websocket_connect_timeout_ms", None)
        try:
            return max(float(timeout_ms) / 1000.0, 0.0) if timeout_ms is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    async def _run_op(
        self,
        op: AppCommand,
        *,
        session_event_observer: Any = None,
        model_session: Any = None,
        cancellation_token: Any = None,
    ) -> tuple[Any, ExecRunPlan]:
        _timing_trace("core_run_op_started", has_model_session=model_session is not None)
        plan = exec_run_plan_for_app_command(op)
        hidden_goal_context = bool(op.payload.get("hidden_goal_context")) if isinstance(op.payload, Mapping) else False
        _timing_trace(
            "goal_core_run_op_plan",
            hidden_goal_context=hidden_goal_context,
            prompt_summary=plan.prompt_summary,
            has_model_session=model_session is not None,
        )
        history_items = self._model_history_snapshot()
        result = await run_exec_user_turn_core_sampling_websocket_preferred(
            self.session_config,
            plan,
            self.model_client,
            self.provider,
            self.model_info,
            auth=self.auth,
            endpoint=self.endpoint,
            timeout=self.timeout,
            opener=self.opener,
            built_tools=self.built_tools,
            max_tool_followups=self.max_tool_followups,
            auth_manager=self.auth_manager,
            codex_home=self.codex_home,
            session_event_observer=session_event_observer,
            model_session=model_session,
            cancellation_token=cancellation_token,
            history_items=history_items,
        )
        _timing_trace(
            "goal_core_run_op_finished",
            hidden_goal_context=hidden_goal_context,
            response_items=len(getattr(result, "response_items", ()) or ()),
            tool_response_items=len(getattr(result, "tool_response_items", ()) or ()),
            request_count=len(getattr(result, "request_plans", ()) or ()),
            last_agent_message=bool(getattr(result, "last_agent_message", None)),
        )
        return result, plan

    def _model_history_snapshot(self) -> tuple[ResponseItem, ...]:
        """Return the prompt-visible history for the next core session.

        Rust ``codex-core::session::turn`` samples from
        ``sess.clone_history().await.for_prompt(...)``.  The Python terminal
        product path creates a fresh in-memory core session per submitted turn,
        so this active-thread runtime carries the Rust-shaped history between
        those per-turn sessions.
        """

        with self._model_history_lock:
            return tuple(self._model_history_items)

    def _record_model_history_from_turn(self, plan: ExecRunPlan, result: Any) -> None:
        operation = getattr(plan, "initial_operation", None)
        if getattr(operation, "kind", None) != "user_turn":
            return
        input_items = tuple(getattr(operation, "items", ()) or ())
        turn_items: list[ResponseItem] = []
        if input_items:
            turn_items.append(ResponseItem.from_response_input_item(ResponseInputItem.from_user_inputs(input_items)))
        turn_items.extend(_local_http_prompt_visible_rollout_items(result))
        if not turn_items:
            return
        with self._model_history_lock:
            self._model_history_items.extend(turn_items)

    def _persist_rollout(self, plan: ExecRunPlan, result: Any) -> None:
        try:
            if self.codex_home is None:
                return
            operation = getattr(plan, "initial_operation", None)
            input_items = getattr(operation, "items", ()) if getattr(operation, "kind", None) == "user_turn" else ()
            path = persist_core_exec_rollout(
                Path(self.codex_home),
                self.session_config,
                result,
                self.model_client,
                input_items=input_items,
                cli_version="pycodex",
            )
            self.rollout_path = Path(path) if path is not None else None
        finally:
            self._rollout_path_ready.set()

    def wait_for_rollout_path(self, timeout_seconds: float | None = None) -> Path | None:
        """Wait for the post-turn rollout path used by Rust-style exit summaries."""

        self._rollout_path_ready.wait(timeout_seconds)
        return self.rollout_path


@dataclass
class TuiAppRuntime:
    active_thread_runtime: ActiveThreadRuntime
    thread_id: str = "primary"
    rollout_path: Path | None = None
    cwd: Path = field(default_factory=Path.cwd)
    startup_session_action: str | None = None
    startup_session_id: str | None = None
    startup_session_last: bool = False
    startup_session_show_all: bool = False
    startup_session_include_non_interactive: bool = False
    startup_session_selected_action: str | None = None
    startup_session_selected_thread_id: str | None = None
    startup_session_selected_path: Path | None = None
    startup_session_forked_thread_id: str | None = None
    startup_session_replay_history: list[Any] = field(default_factory=list)
    chat_widget: ChatWidgetProtocolRuntime = field(default_factory=ChatWidgetProtocolRuntime)
    routing_state: ThreadRoutingState = field(default_factory=lambda: ThreadRoutingState(active_thread_id="primary", primary_thread_id="primary"))
    agent_navigation: AgentNavigationState = field(default_factory=AgentNavigationState)
    side_ui_state: SideUiState = field(default_factory=SideUiState)
    submitted_ops: list[AppCommand] = field(default_factory=list)
    routing_plans: list[ThreadRoutingPlan] = field(default_factory=list)
    event_dispatch_plans: list[EventDispatchPlan] = field(default_factory=list)
    app_server_event_plans: list[AppServerEventPlan] = field(default_factory=list)
    history_cell_sink: Callable[[object], Any] | None = None
    pending_history_cells: list[object] = field(default_factory=list)
    pending_app_server_requests: PendingAppServerRequests = field(default_factory=PendingAppServerRequests)
    app_server_request_dismiss_sink: Callable[[object], bool] | None = None
    full_screen_approval_sink: Callable[[object], Any] | None = None
    thread_event_stores: dict[str, ThreadEventStore] = field(default_factory=dict)
    replayed_interactive_request_ids: set[Any] = field(default_factory=set)
    projected_interactive_request_ids: set[Any] = field(default_factory=set)
    app_server_request_resolutions: list[AppServerRequestResolution] = field(default_factory=list)
    opened_urls: list[str] = field(default_factory=list)
    auxiliary_app_events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    open_url_sink: Callable[[str], Any] = field(default_factory=lambda: webbrowser.open)
    _status_rate_limit_request_id: int = 0

    def __post_init__(self) -> None:
        if self.thread_id and (
            self.routing_state.active_thread_id,
            self.routing_state.primary_thread_id,
        ) == ("primary", "primary"):
            self.routing_state.active_thread_id = self.thread_id
            self.routing_state.primary_thread_id = self.thread_id
        self._sync_side_routing_state()
        self.sync_chat_widget_config_from_runtime()
        self.sync_message_history_metadata_from_runtime()
        self.chat_widget.info_message_sink = self.insert_info_history_message
        self.chat_widget.bind_history_projection(
            HistoryProjectionSink(
                insert_cell=self.insert_history_cell,
                set_active_cell=lambda _cell: None,
                request_redraw=lambda: None,
            )
        )

    def bind_history_cell_sink(self, sink: Callable[[object], Any]) -> None:
        """Bind Rust ``AppEvent::InsertHistoryCell`` to the terminal backend."""

        self.history_cell_sink = sink
        pending = tuple(self.pending_history_cells)
        self.pending_history_cells.clear()
        for cell in pending:
            sink(cell)

    def bind_full_screen_approval_sink(self, sink: Callable[[object], Any]) -> None:
        self.full_screen_approval_sink = sink

    def bind_app_server_request_dismiss_sink(self, sink: Callable[[object], bool]) -> None:
        """Bind Rust ``BottomPane::dismiss_app_server_request`` to the app owner."""

        self.app_server_request_dismiss_sink = sink

    def _thread_event_store(self, thread_id: str | None = None) -> ThreadEventStore:
        target = str(thread_id or self.routing_state.active_thread_id or self.thread_id)
        store = self.thread_event_stores.get(target)
        if store is None:
            store = ThreadEventStore.new(256)
            self.thread_event_stores[target] = store
        return store

    def replay_thread_snapshot(
        self,
        snapshot: ThreadEventSnapshot,
        *,
        resume_restored_queue: bool = True,
    ) -> None:
        """Replay one filtered thread snapshot in fixed-Rust app order."""

        del resume_restored_queue
        session = getattr(snapshot, "session", None)
        target_thread_id = str(
            _field(session, "thread_id", None)
            or self.routing_state.active_thread_id
            or self.thread_id
        )
        turns = list(getattr(snapshot, "turns", ()) or ())
        restored_store = ThreadEventStore.new_with_session(256, session, turns)
        for buffered in tuple(getattr(snapshot, "events", ()) or ()):
            event = buffered if isinstance(buffered, ThreadBufferedEvent) else ThreadBufferedEvent(
                str(_field(buffered, "kind", "")),
                _field(buffered, "payload", buffered),
            )
            if event.kind == "Request":
                restored_store.push_request(event.payload)
            elif event.kind == "Notification":
                restored_store.push_notification(event.payload)
        self.thread_event_stores[target_thread_id] = restored_store

        if turns:
            replay_thread_turns(self.chat_widget, turns, ChatWidgetReplayKind.THREAD_SNAPSHOT)

        for event in restored_store.snapshot().events:
            if event.kind == "Request":
                request_id = _field(event.payload, "request_id", _field(event.payload, "id", None))
                if request_id in self.replayed_interactive_request_ids:
                    continue
                self.replayed_interactive_request_ids.add(request_id)
                self.pending_app_server_requests.note_server_request(event.payload)
                self.chat_widget.handle_request(event.payload)
            elif event.kind == "Notification":
                self.chat_widget.handle(_coerce_server_notification(event.payload))

    def insert_history_cell(self, cell: object) -> None:
        if self.history_cell_sink is None:
            self.pending_history_cells.append(cell)
            return
        self.history_cell_sink(cell)

    def insert_info_history_message(self, message: str, hint: str | None = None) -> None:
        self.insert_history_cell(new_info_event(message, hint))

    def sync_chat_widget_config_from_runtime(self) -> None:
        """Project Rust ``Config`` fields needed by ``chatwidget``.

        Rust keeps these values on the loaded core ``Config`` and
        ``codex-tui::chatwidget`` reads them directly.  The Python active
        thread runtime carries the same subset on ``session_config``; mirror it
        into the chatwidget config so terminal rendering follows the configured
        reasoning visibility instead of local UI defaults.
        """

        source = _first_runtime_config_source(
            self.active_thread_runtime,
            getattr(self.active_thread_runtime, "session_config", None),
            getattr(self.active_thread_runtime, "config", None),
            getattr(self.active_thread_runtime, "model_client", None),
        )
        if source is None:
            return
        target = getattr(self.chat_widget, "config", None)
        if target is None:
            target = SimpleNamespace()
            self.chat_widget.config = target
        setattr(
            target,
            "cwd",
            getattr(getattr(self.active_thread_runtime, "session_config", None), "cwd", None)
            or self.cwd,
        )
        for name in (
            "hide_agent_reasoning",
            "show_raw_agent_reasoning",
            "model_reasoning_effort",
            "reasoning_effort",
            "model_reasoning_summary",
        ):
            if hasattr(source, name):
                setattr(target, name, getattr(source, name))

    def sync_message_history_metadata_from_runtime(self) -> None:
        metadata = None
        for source in (
            self.active_thread_runtime,
            getattr(self.active_thread_runtime, "app_server_session", None),
            getattr(self.active_thread_runtime, "app_server", None),
        ):
            if source is None:
                continue
            method = getattr(source, "message_history_metadata", None)
            if not callable(method):
                continue
            try:
                metadata = method()
                if hasattr(metadata, "__await__"):
                    metadata = _run_coro_blocking(metadata)
            except Exception:
                metadata = None
            if metadata is not None:
                break
        if metadata is None:
            return
        try:
            log_id, entry_count = metadata
        except (TypeError, ValueError):
            log_id = _field(metadata, "log_id", None)
            entry_count = _field(metadata, "entry_count", None)
        if log_id is None:
            return
        self.chat_widget.bottom_history_metadata = (
            self.current_displayed_thread_id(),
            int(log_id),
            int(entry_count or 0),
        )

    def submit_user_turn(self, prompt: str) -> ActiveThreadEventStream:
        op = app_command_for_prompt(
            prompt,
            cwd=self.cwd,
            approval_policy=_runtime_turn_context_value(self, "approval_policy"),
            active_permission_profile=_runtime_active_permission_profile_value(self),
            model=_runtime_model_for_user_turn(self),
            reasoning_effort=_runtime_reasoning_effort_for_user_turn(self),
            service_tier=_runtime_turn_context_value(self, "service_tier"),
        )
        return self.submit_op(op)

    def apply_permission_profile_selection(self, selection: Any) -> None:
        """Apply and persist Rust ``SelectPermissionProfile`` atomically."""

        profile_id = str(_field(selection, "profile_id", "") or "")
        permission_profile, active_permission_profile = _resolve_permission_profile_selection(
            profile_id,
            self.active_thread_runtime,
        )
        approval_policy = _coerce_approval_policy(
            _field(selection, "approval_policy", None)
        )
        approvals_reviewer = _coerce_approvals_reviewer(
            _field(selection, "approvals_reviewer", None)
        )
        sources = (
            self.active_thread_runtime,
            getattr(self.active_thread_runtime, "session_config", None),
            getattr(self.chat_widget, "config", None),
        )
        snapshot = [
            (
                source,
                _field(source, "active_permission_profile", None),
                _field(source, "permission_profile", None),
                _field(source, "approval_policy", None),
                _field(source, "approvals_reviewer", None),
            )
            for source in sources
            if source is not None
        ]
        edits = [ConfigEdit.set_path(("permission_profile",), profile_id)]
        if approval_policy is not None:
            edits.append(
                ConfigEdit.set_path(
                    ("approval_policy",),
                    str(getattr(approval_policy, "value", approval_policy)),
                )
            )
        if approvals_reviewer is not None:
            edits.append(
                ConfigEdit.set_path(
                    ("approvals_reviewer",),
                    approvals_reviewer.value,
                )
            )
        config = _config_from_runtime(self.active_thread_runtime)
        try:
            if config is not None and _config_has_write_target(config):
                ConfigEditsBuilder.for_config(config).with_edits(edits).apply_blocking()
            for source, _active_profile, _permission_profile, _approval, _reviewer in snapshot:
                _set_runtime_field(source, "active_permission_profile", active_permission_profile)
                _set_runtime_field(source, "permission_profile", permission_profile)
                if approval_policy is not None:
                    _set_runtime_field(source, "approval_policy", approval_policy)
                if approvals_reviewer is not None:
                    _set_runtime_field(source, "approvals_reviewer", approvals_reviewer)
            config_target = getattr(self.chat_widget, "config", None)
            permissions = getattr(config_target, "permissions", None) if config_target is not None else None
            if permissions is not None:
                _set_runtime_field(permissions, "active_permission_profile", active_permission_profile)
                _set_runtime_field(permissions, "permission_profile", permission_profile)
                if approval_policy is not None:
                    _set_runtime_field(permissions, "approval_policy", approval_policy)
            self.submit_op(
                AppCommand.override_turn_context(
                    approval_policy=approval_policy,
                    approvals_reviewer=approvals_reviewer,
                    permission_profile=permission_profile,
                    active_permission_profile=active_permission_profile,
                )
            )
            self.chat_widget.add_info_message(
                f"Permissions updated to {_field(selection, 'display_label', profile_id)}",
                None,
            )
        except Exception:
            for source, old_active_profile, old_permission_profile, old_approval, old_reviewer in snapshot:
                _set_runtime_field(source, "active_permission_profile", old_active_profile)
                _set_runtime_field(source, "permission_profile", old_permission_profile)
                _set_runtime_field(source, "approval_policy", old_approval)
                _set_runtime_field(source, "approvals_reviewer", old_reviewer)
            raise

    def persist_keymap_update(
        self,
        context: str,
        action: str,
        keymap_config: Any,
        runtime_keymap: Any,
        bindings: Any,
    ) -> None:
        """Persist one Rust keymap edit, then refresh all live keymap caches."""

        config = _config_from_runtime(self.active_thread_runtime)
        if config is not None and _config_has_write_target(config):
            edit = ConfigEdit.set_path(("tui", "keymap", str(context), str(action)), list(bindings))
            ConfigEditsBuilder.for_config(config).with_edits([edit]).apply_blocking()
        self._apply_live_keymap(keymap_config, runtime_keymap)

    def persist_full_access_warning_acknowledged(self) -> None:
        """Persist Rust's full-access confirmation acknowledgement."""

        config = _config_from_runtime(self.active_thread_runtime)
        if config is not None and _config_has_write_target(config):
            ConfigEditsBuilder.for_config(config).set_hide_full_access_warning(True).apply_blocking()
        for source in (
            self.active_thread_runtime,
            getattr(self.active_thread_runtime, "session_config", None),
            getattr(self.active_thread_runtime, "config", None),
            getattr(self.chat_widget, "config", None),
        ):
            _set_runtime_field(source, "hide_full_access_warning", True)

    def persist_keymap_clear(
        self,
        context: str,
        action: str,
        keymap_config: Any,
        runtime_keymap: Any,
    ) -> None:
        """Clear one root keymap override and refresh live key handlers."""

        config = _config_from_runtime(self.active_thread_runtime)
        if config is not None and _config_has_write_target(config):
            edit = ConfigEdit.clear_path(("tui", "keymap", str(context), str(action)))
            ConfigEditsBuilder.for_config(config).with_edits([edit]).apply_blocking()
        self._apply_live_keymap(keymap_config, runtime_keymap)

    def _apply_live_keymap(self, keymap_config: Any, runtime_keymap: Any) -> None:
        for source in (
            self.active_thread_runtime,
            getattr(self.active_thread_runtime, "session_config", None),
            getattr(self.active_thread_runtime, "config", None),
            getattr(self.chat_widget, "config", None),
        ):
            _set_runtime_field(source, "tui_keymap", keymap_config)
            _set_runtime_field(source, "runtime_keymap", runtime_keymap)
        _set_runtime_field(self, "runtime_keymap", runtime_keymap)
        _set_runtime_field(self.chat_widget, "runtime_keymap", runtime_keymap)
        bottom_pane = getattr(self.chat_widget, "bottom_pane", None)
        setter = getattr(bottom_pane, "set_keymap_bindings", None)
        if callable(setter):
            setter(runtime_keymap)

    def append_message_history_entry(self, text: str) -> None:
        append = getattr(self.active_thread_runtime, "append_message_history_entry", None)
        if not callable(append):
            return
        try:
            result = append(text)
            if hasattr(result, "__await__"):
                _run_coro_blocking(result)
        except Exception:
            return
        self.sync_message_history_metadata_from_runtime()

    def submit_op(self, op: AppCommand) -> ActiveThreadEventStream:
        plan = submit_active_thread_op_plan(self.routing_state, op)
        self.routing_plans.append(plan)
        if plan.action != "submit_thread_op" or plan.thread_id is None:
            raise RuntimeError(plan.error_message or "failed to submit active thread op")
        self.submitted_ops.append(op)
        return self.active_thread_runtime.submit_thread_op(plan.thread_id, op)

    def fork_startup_session_target(self, target: Any) -> bool:
        """Fork the selected startup session and install it as the active thread.

        Rust ``codex-tui::app::run`` handles
        ``SessionSelection::Fork(target_session)`` by calling
        ``AppServerSession::fork_thread(config, target_session.thread_id)`` and
        constructing the initial chat widget from the returned started thread.
        This sync adapter preserves that boundary for the terminal product path:
        it delegates the fork to the active runtime/app-server facade when one
        is available, then switches routing identity to the returned forked
        thread.  It intentionally does not synthesize a local ``UserTurn``.
        """

        thread_id = str(_field(target, "thread_id", "") or "").strip()
        if not thread_id:
            return False
        path = _field(target, "path", None)
        self.startup_session_selected_action = "fork"
        self.startup_session_selected_thread_id = thread_id
        self.startup_session_selected_path = Path(path) if path is not None else None

        forked = self._call_startup_fork_backend(target, thread_id)
        if forked is None:
            return False
        installed_thread_id = self._install_started_thread(forked, fallback_parent_thread_id=thread_id)
        return installed_thread_id is not None

    def _call_startup_fork_backend(self, target: Any, thread_id: str) -> Any:
        config = (
            getattr(self.active_thread_runtime, "session_config", None)
            or getattr(self.active_thread_runtime, "config", None)
        )
        sources = (
            self.active_thread_runtime,
            getattr(self.active_thread_runtime, "app_server_session", None),
            getattr(self.active_thread_runtime, "app_server", None),
        )
        for source in sources:
            if source is None:
                continue
            for name in ("fork_thread_from_selection", "fork_startup_thread", "fork_thread"):
                method = getattr(source, name, None)
                if not callable(method):
                    continue
                for args in ((target,), (config, thread_id), (thread_id,)):
                    try:
                        result = method(*args)
                    except TypeError:
                        continue
                    if hasattr(result, "__await__"):
                        result = _run_coro_blocking(result)
                    return result
        return None

    def _install_started_thread(self, started: Any, *, fallback_parent_thread_id: str | None = None) -> str | None:
        session = _field(started, "session", None)
        if session is None:
            session = _field(started, "thread", started)
        thread_id = (
            _field(session, "thread_id", None)
            or _field(session, "id", None)
            or _field(started, "thread_id", None)
            or _field(started, "id", None)
        )
        if thread_id is None:
            return None
        thread_id_text = str(thread_id)
        self.thread_id = thread_id_text
        self.routing_state.active_thread_id = thread_id_text
        self.routing_state.primary_thread_id = thread_id_text
        self.startup_session_forked_thread_id = thread_id_text

        for target in (self.active_thread_runtime, getattr(self.active_thread_runtime, "model_client", None)):
            if target is None:
                continue
            try:
                setattr(target, "thread_id", thread_id_text)
            except (AttributeError, TypeError):
                pass

        thread_name = _field(session, "thread_name", None) or _field(session, "name", None)
        if thread_name is not None:
            self.chat_widget.thread_name = str(thread_name)
        forked_from_id = (
            _field(session, "forked_from_id", None)
            or _field(session, "forked_from", None)
            or fallback_parent_thread_id
        )
        if forked_from_id is not None:
            try:
                setattr(self.chat_widget, "forked_from", str(forked_from_id))
            except (AttributeError, TypeError):
                pass
        cwd = _field(session, "cwd", None)
        if cwd is not None:
            self.cwd = Path(cwd)
        rollout_path = _field(session, "rollout_path", None) or _field(started, "rollout_path", None)
        if rollout_path is not None:
            self.rollout_path = Path(rollout_path)
        self.upsert_agent_picker_thread(thread_id_text)
        turns = list(_field(started, "turns", []) or [])
        if turns:
            self._replay_started_thread_turns(turns)
        return thread_id_text

    def _replay_started_thread_turns(self, turns: list[Any]) -> None:
        """Replay returned startup turns through the Rust-shaped chatwidget path.

        Rust ``app::thread_routing::enqueue_primary_thread_session`` installs
        the returned session, then calls
        ``ChatWidget::replay_thread_turns(turns, ReplayKind::ResumeInitialMessages)``.
        The terminal product shell consumes the semantic history emitted by that
        replay instead of reading app-server turns directly.
        """

        history = getattr(self.chat_widget.streaming, "history", None)
        before = len(history) if isinstance(history, list) else 0
        replay_thread_turns(self.chat_widget, turns, ChatWidgetReplayKind.RESUME_INITIAL_MESSAGES)
        if isinstance(history, list):
            self.startup_session_replay_history.extend(history[before:])

    def take_startup_session_replay_history(self) -> list[Any]:
        history = list(self.startup_session_replay_history)
        self.startup_session_replay_history.clear()
        return history

    def handle_app_event(self, event: AppEvent | dict[str, Any] | Any) -> EventDispatchPlan:
        """Apply the app-level side effects owned by Rust ``app::event_dispatch``.

        Most Rust ``AppEvent`` variants delegate to neighboring modules.  The
        product terminal path only executes the side effects it can faithfully
        own; unsupported variants still return a dispatch plan for tests and
        future composition work.
        """

        plan = dispatch_event_plan(
            EventDispatchState(
                active_thread_id=self.routing_state.active_thread_id,
                chat_widget_thread_id=self.current_displayed_thread_id(),
                pending_shutdown_exit_thread_id=self.routing_state.pending_shutdown_exit_thread_id,
            ),
            event,
        )
        self.event_dispatch_plans.append(plan)
        if plan.action == "update_model":
            model = plan.updates[0][1] if plan.updates else None
            self.update_model(model)
        elif plan.action == "update_reasoning_effort":
            effort = plan.updates[0][1] if plan.updates else None
            self.update_reasoning_effort(effort)
        elif plan.action == "persist_model_selection":
            payload = plan.updates[0][1] if plan.updates else {}
            model = payload.get("model") if isinstance(payload, Mapping) else None
            effort = payload.get("effort") if isinstance(payload, Mapping) else None
            self.persist_model_selection(model, effort)
        elif plan.action == "refresh_rate_limits":
            origin = plan.updates[0][1] if plan.updates else None
            self.refresh_rate_limits(origin)
        elif plan.action == "rate_limits_loaded":
            payload = plan.updates[0][1] if plan.updates else {}
            if isinstance(payload, Mapping):
                self.on_rate_limits_loaded(payload.get("origin"), payload.get("result"))
        elif plan.action == "apply_raw_output_mode":
            payload = plan.updates[0][1] if plan.updates else {}
            enabled = payload.get("enabled") if isinstance(payload, Mapping) else payload
            self.apply_raw_output_mode(enabled)
        elif plan.action == "diff_result":
            text = plan.updates[0][1] if plan.updates else ""
            self.chat_widget.on_diff_complete(text)
        return plan

    def handle_app_server_event(self, event: Any) -> AppServerEventPlan:
        """Apply Rust ``app::app_server_events`` pre-chatwidget routing.

        Rust refreshes the expected MCP startup server set before forwarding
        startup-status notifications and before settling lagged startup rounds.
        Keeping that app-owned step here lets ``chatwidget::mcp_startup`` stay
        focused on its own state machine while the product runtime preserves
        the Rust event ordering.
        """

        plan = plan_app_server_event(
            event,
            primary_thread_id=self.routing_state.primary_thread_id,
            pending_requests=self.pending_app_server_requests,
        )
        self.app_server_event_plans.append(plan)
        self._apply_app_server_event_plan(plan)
        if (
            plan.notification is not None
            and "refresh_mcp_expected_servers" in plan.actions
            and "handle_global_server_notification" not in plan.actions
        ):
            self.handle_notification(_coerce_server_notification(plan.notification))
        return plan

    def next_status_rate_limit_request_id(self) -> int:
        request_id = self._status_rate_limit_request_id
        self._status_rate_limit_request_id += 1
        return request_id

    def register_status_rate_limit_handle(self, request_id: int, handle: Any) -> None:
        add = getattr(self.chat_widget, "add_refreshing_status_output", None)
        if callable(add):
            add(request_id, handle)

    def refresh_rate_limits(self, origin: Any) -> None:
        """Start the Rust-shaped rate-limit refresh boundary when available.

        Rust spawns an app-server RPC and routes completion as
        ``RateLimitsLoaded``.  The dependency-light runtime records the dispatch
        and supports injected/fake active runtimes that can provide a result
        immediately for tests; real product paths can wire a background request
        source behind the same method without changing TUI projection code.
        """

        fetcher = getattr(self.active_thread_runtime, "fetch_account_rate_limits", None)
        if fetcher is None:
            fetcher = getattr(self.active_thread_runtime, "get_account_rate_limits", None)
        if not callable(fetcher):
            _timing_trace("rate_limits_refresh_skipped", reason="missing_fetcher", origin=_rate_limit_origin_kind(origin))
            return
        _timing_trace("rate_limits_refresh_start", origin=_rate_limit_origin_kind(origin))
        try:
            result = fetcher()
            if hasattr(result, "__await__"):
                result = _run_coro_blocking(result)
        except BaseException as exc:
            result = exc
            _timing_trace("rate_limits_refresh_error", origin=_rate_limit_origin_kind(origin), error=str(exc))
        else:
            try:
                count = len(result)  # type: ignore[arg-type]
            except TypeError:
                count = None
            _timing_trace("rate_limits_refresh_success", origin=_rate_limit_origin_kind(origin), count=count)
        self.handle_app_event(AppEvent.rate_limits_loaded(origin, result))

    def on_rate_limits_loaded(self, origin: Any, result: Any) -> None:
        snapshots = _rate_limit_result_snapshots(result)
        if snapshots is not None:
            for snapshot in snapshots:
                display = _rate_limit_snapshot_display(snapshot)
                self.chat_widget.on_rate_limit_snapshot(display)
                _store_runtime_rate_limit_snapshot(self.active_thread_runtime, display)
        if _rate_limit_origin_kind(origin) == RateLimitRefreshOrigin.STATUS_COMMAND:
            request_id = _rate_limit_origin_request_id(origin)
            if request_id is not None:
                self.chat_widget.finish_status_rate_limit_refresh(request_id)

    def refresh_mcp_startup_expected_servers(self) -> list[str]:
        expected: list[str] = []
        for config in (
            getattr(self.chat_widget, "config", None),
            getattr(self.active_thread_runtime, "session_config", None),
            getattr(self.active_thread_runtime, "config", None),
        ):
            expected = refresh_mcp_startup_expected_servers_from_config(config)
            if expected:
                break
        setter = getattr(self.chat_widget.mcp_startup, "set_mcp_startup_expected_servers", None)
        if callable(setter):
            setter(expected)
        return expected

    def finish_mcp_startup_after_lag(self) -> None:
        finish = getattr(self.chat_widget.mcp_startup, "finish_mcp_startup_after_lag", None)
        if callable(finish):
            previous_warning_count = len(getattr(self.chat_widget.mcp_startup, "warnings", []) or [])
            finish()
        else:
            previous_warning_count = 0
        self.chat_widget.turn.mcp_startup_status = self.chat_widget.mcp_startup.startup_status
        self.chat_widget.turn.update_task_running_state()
        warnings = list(getattr(self.chat_widget.mcp_startup, "warnings", []) or [])
        for warning in warnings[previous_warning_count:]:
            self.chat_widget.turn.on_warning(warning)
        self.chat_widget.request_redraw()

    def apply_raw_output_mode(self, enabled: Any) -> None:
        setter = getattr(self.chat_widget, "set_raw_output_mode", None)
        if callable(setter):
            setter(bool(enabled))
        else:
            setattr(self.chat_widget, "raw_mode", bool(enabled))
        self.chat_widget.request_redraw()

    def update_model(self, model: Any) -> None:
        model_text = "" if model is None else str(model).strip()
        if not model_text:
            return
        setter = getattr(self.chat_widget, "set_model", None)
        if callable(setter):
            setter(model_text)
        _set_runtime_model_value(self.active_thread_runtime, model_text)
        session_config = getattr(self.active_thread_runtime, "session_config", None)
        _set_runtime_model_value(session_config, model_text)
        model_client = getattr(self.active_thread_runtime, "model_client", None)
        _set_runtime_model_value(model_client, model_text)

    def update_reasoning_effort(self, effort: Any = None) -> None:
        effort_text = _effort_config_value(effort)
        setter = getattr(self.chat_widget, "set_reasoning_effort", None)
        if callable(setter):
            setter(effort_text)
        else:
            setattr(self.chat_widget.config, "model_reasoning_effort", effort_text)
        for target in (
            self.chat_widget,
            getattr(self.chat_widget, "config", None),
            self.active_thread_runtime,
            getattr(self.active_thread_runtime, "session_config", None),
            getattr(self.active_thread_runtime, "model_client", None),
        ):
            _set_runtime_reasoning_effort_value(target, effort_text)
            _set_runtime_model_details_reasoning_value(target, effort_text)

    def persist_model_selection(self, model: Any, effort: Any = None) -> bool:
        """Persist a model selection using Rust ``config_update`` semantics."""

        model_text = "" if model is None else str(model).strip()
        if not model_text:
            return False
        effort_text = _effort_config_value(effort)
        try:
            request_handle = _request_handle_from_runtime(self.active_thread_runtime)
            if request_handle is not None:
                _run_coro_blocking(write_config_batch(request_handle, build_model_selection_edits(model_text, effort_text)))
            else:
                config = _config_from_runtime(self.active_thread_runtime)
                if config is None:
                    raise RuntimeError("missing request handle or config")
                ConfigEditsBuilder.for_config(config).set_model(model_text, effort_text).apply_blocking()
        except BaseException as exc:
            self.chat_widget.add_error_message(f"Failed to save default model: {exc}")
            return False

        message = f"Model changed to {model_text}"
        label = _reasoning_label_for(model_text, effort_text)
        if label is not None:
            message = f"{message} {label}"
        self.chat_widget.add_info_message(message, None)
        return True

    def shutdown_current_thread(self, *, timeout_seconds: float = 2.0) -> bool:
        thread_id = self.routing_state.active_thread_id or self.thread_id
        self.routing_state.pending_shutdown_exit_thread_id = thread_id
        self.routing_plans.append(
            ThreadRoutingPlan(
                action="shutdown_current_thread",
                thread_id=thread_id,
                app_server_call=("thread_shutdown", thread_id),
            )
        )
        shutdown_thread = getattr(self.active_thread_runtime, "shutdown_thread", None)
        if not callable(shutdown_thread):
            self.routing_state.pending_shutdown_exit_thread_id = None
            return False
        try:
            stream = shutdown_thread(thread_id)
            deadline = time.monotonic() + max(0.0, timeout_seconds)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                event = stream.next_event(timeout=min(0.05, remaining))
                if event is None:
                    if getattr(stream, "closed", False):
                        return True
                    continue
                self.handle_notification(event)
                if event.kind == "ThreadClosed":
                    return True
        except BaseException:
            return False
        finally:
            self.routing_state.pending_shutdown_exit_thread_id = None

    def close(self) -> None:
        closer = getattr(self.active_thread_runtime, "close", None)
        if callable(closer):
            closer()

    def current_displayed_thread_id(self) -> str | None:
        if self.routing_state.active_thread_id:
            return self.routing_state.active_thread_id
        thread_id = getattr(self.chat_widget, "thread_id", None)
        thread_id = thread_id() if callable(thread_id) else thread_id
        if thread_id is None:
            return None
        text = str(thread_id).strip()
        return text or None

    def upsert_agent_picker_thread(
        self,
        thread_id: str,
        *,
        agent_nickname: str | None = None,
        agent_role: str | None = None,
        is_closed: bool = False,
    ) -> str | None:
        try:
            self.agent_navigation.upsert(
                thread_id,
                agent_nickname=agent_nickname,
                agent_role=agent_role,
                is_closed=is_closed,
            )
        except (TypeError, ValueError, AttributeError):
            return self.sync_active_agent_label()
        return self.sync_active_agent_label()

    def mark_agent_picker_thread_closed(self, thread_id: str) -> str | None:
        try:
            self.agent_navigation.mark_closed(thread_id)
        except (TypeError, ValueError, AttributeError):
            return self.sync_active_agent_label()
        return self.sync_active_agent_label()

    def sync_active_agent_label(self) -> str | None:
        try:
            label = self.agent_navigation.active_agent_label(
                self.current_displayed_thread_id(),
                self.routing_state.primary_thread_id,
            )
        except (TypeError, ValueError, AttributeError):
            label = None
        self.chat_widget.set_active_agent_label(label)
        return label

    def thread_label(self, thread_id: str) -> str:
        """Port fixed-Rust ``App::thread_label`` for approval surfaces."""

        target = str(thread_id)
        is_primary = target == self.routing_state.primary_thread_id
        fallback = (
            "Main [default]"
            if is_primary
            else f"Agent ({target[:8]})"
        )
        try:
            entry = self.agent_navigation.get(target)
        except (TypeError, ValueError, AttributeError):
            entry = None
        if entry is None:
            return fallback
        label = format_agent_picker_item_name(
            entry.agent_nickname,
            entry.agent_role,
            is_primary,
        )
        return fallback if label == "Agent" else label

    def _sync_side_routing_state(self) -> None:
        self.side_ui_state.active_thread_id = self.routing_state.active_thread_id
        self.side_ui_state.primary_thread_id = self.routing_state.primary_thread_id

    def register_side_thread(self, thread_id: str, parent_thread_id: str) -> None:
        self.side_ui_state.side_threads[str(thread_id)] = SideThreadState.new(
            str(parent_thread_id)
        )
        self._sync_side_routing_state()

    def active_side_parent_thread_id(self) -> str | None:
        self._sync_side_routing_state()
        return side_active_parent_thread_id(self.side_ui_state)

    def refresh_pending_thread_approvals(self) -> list[str]:
        side_parent = self.active_side_parent_thread_id()
        pending_ids = sorted(
            thread_id
            for thread_id, store in self.thread_event_stores.items()
            if thread_id != self.routing_state.active_thread_id
            and thread_id != side_parent
            and store.has_pending_thread_approvals()
        )
        labels = [self.thread_label(thread_id) for thread_id in pending_ids]
        self.chat_widget.set_pending_thread_approvals(labels)
        return labels

    def _push_thread_interactive_request(
        self,
        request: ThreadInteractiveRequest,
    ) -> None:
        if request.kind == "approval":
            self.chat_widget.tool_requests.push_approval_request(request.payload)
        elif request.kind == "mcp_form":
            self.chat_widget.tool_requests.push_mcp_server_elicitation_request(
                request.payload
            )
        elif request.kind == "app_link":
            self.chat_widget.tool_requests.open_app_link_view(request.payload)
        elif request.kind == "decline_elicitation":
            thread_id, server_name, request_id = request.payload
            self.handle_bottom_pane_app_event(
                AppEvent.of(
                    "ResolveElicitation",
                    thread_id=thread_id,
                    server_name=server_name,
                    request_id=request_id,
                    decision="Decline",
                    content=None,
                    meta=None,
                )
            )

    def _enqueue_server_request(self, thread_id: str, request: ServerRequest) -> None:
        store = self._thread_event_store(thread_id)
        store.push_request(request)
        request_id = _field(request, "request_id", _field(request, "id", None))
        if thread_id == self.routing_state.active_thread_id:
            self.chat_widget.handle_request(request)
            if request_id is not None:
                self.projected_interactive_request_ids.add(request_id)
        else:
            interactive = None
            if self.active_side_parent_thread_id() is None:
                interactive = interactive_request_for_thread_request(
                    thread_id,
                    self.thread_label(thread_id),
                    request,
                    fallback_cwd=self.cwd,
                )
            if interactive is not None:
                self._push_thread_interactive_request(interactive)
                if request_id is not None:
                    self.projected_interactive_request_ids.add(request_id)
        self.refresh_pending_thread_approvals()

    def _surface_unprojected_active_thread_requests(self, thread_id: str) -> None:
        store = self.thread_event_stores.get(thread_id)
        if store is None:
            return
        for request in store.pending_replay_requests():
            request_id = _field(request, "request_id", _field(request, "id", None))
            if request_id is not None and request_id in self.projected_interactive_request_ids:
                continue
            self.chat_widget.handle_request(request)
            if request_id is not None:
                self.projected_interactive_request_ids.add(request_id)

    def select_agent_thread(self, thread_id: str) -> ThreadRoutingPlan:
        target_thread_id = str(thread_id).strip()
        entry = self.agent_navigation.get(target_thread_id)
        if entry is None and target_thread_id not in self.thread_event_stores:
            error_message = f"Agent thread {target_thread_id} is no longer available."
            self.chat_widget.add_error_message(error_message)
            plan = ThreadRoutingPlan(
                action="select_agent_thread_unavailable",
                thread_id=target_thread_id,
                error_message=error_message,
            )
            self.routing_plans.append(plan)
            return plan

        if self.routing_state.active_thread_id == target_thread_id:
            label = self.sync_active_agent_label()
            self.refresh_pending_thread_approvals()
            plan = ThreadRoutingPlan(
                action="select_agent_thread_current",
                thread_id=target_thread_id,
                updates=(("active_agent_label", label),),
            )
            self.routing_plans.append(plan)
            return plan

        self.routing_state.active_thread_id = target_thread_id
        self._sync_side_routing_state()
        label = self.sync_active_agent_label()
        self._surface_unprojected_active_thread_requests(target_thread_id)
        self.refresh_pending_thread_approvals()
        plan = ThreadRoutingPlan(
            action="select_agent_thread",
            thread_id=target_thread_id,
            updates=(("active_thread_id", target_thread_id), ("active_agent_label", label)),
        )
        self.routing_plans.append(plan)
        return plan

    def select_agent_thread_and_discard_side(
        self,
        thread_id: str,
    ) -> ThreadRoutingPlan:
        target_thread_id = str(thread_id).strip()
        self._sync_side_routing_state()
        side_thread_id = side_thread_to_discard_after_switch(
            self.current_displayed_thread_id(),
            self.side_ui_state.side_threads,
            target_thread_id,
        )
        plan = self.select_agent_thread(target_thread_id)
        if plan.action not in {"select_agent_thread", "select_agent_thread_current"}:
            return plan
        if side_thread_id is not None:
            try:
                self.active_thread_runtime.shutdown_thread(side_thread_id)
            except BaseException as exc:
                self.chat_widget.add_error_message(
                    f"Failed to close side conversation {side_thread_id}; "
                    f"it is still open: {exc}"
                )
                return plan
            self.side_ui_state.side_threads.pop(side_thread_id, None)
            self.thread_event_stores.pop(side_thread_id, None)
            try:
                self.agent_navigation.remove(side_thread_id)
            except (TypeError, ValueError, AttributeError):
                pass
            self._sync_side_routing_state()
            self.sync_active_agent_label()
            self.refresh_pending_thread_approvals()
        return plan

    def maybe_return_from_side(self) -> bool:
        parent_thread_id = self.active_side_parent_thread_id()
        if parent_thread_id is None:
            return False
        plan = self.select_agent_thread_and_discard_side(parent_thread_id)
        return plan.action in {"select_agent_thread", "select_agent_thread_current"}

    def select_adjacent_agent_thread(self, direction: AgentNavigationDirection) -> ThreadRoutingPlan:
        target_thread_id = self.agent_navigation.adjacent_thread_id(
            self.current_displayed_thread_id(),
            direction,
        )
        if target_thread_id is None:
            plan = ThreadRoutingPlan(action="select_adjacent_agent_thread_skipped")
            self.routing_plans.append(plan)
            return plan
        return self.select_agent_thread(target_thread_id)

    def handle_notification(self, notification: ServerNotification) -> None:
        notification_thread_id = _notification_thread_id(notification)
        if notification.kind == "ServerRequestResolved":
            for store in self.thread_event_stores.values():
                store.push_notification(notification)
        else:
            self._thread_event_store(notification_thread_id).push_notification(notification)
        if notification.kind == "ServerRequestResolved":
            payload = notification.payload if isinstance(notification.payload, Mapping) else {}
            request_id = payload.get("request_id", payload.get("requestId"))
            self.replayed_interactive_request_ids.discard(request_id)
            self.projected_interactive_request_ids.discard(request_id)
            resolved = self.pending_app_server_requests.resolve_notification(request_id)
            if resolved is not None and self.app_server_request_dismiss_sink is not None:
                self.app_server_request_dismiss_sink(resolved)
            self.refresh_pending_thread_approvals()
        if notification.kind == "McpServerStatusUpdated":
            self.refresh_mcp_startup_expected_servers()
        if notification.kind == "ThreadClosed":
            plan = active_thread_event_plan(self.routing_state, {"notification": notification})
            self.routing_plans.append(plan)
            if plan.action == "failover_to_primary_thread" and plan.target_thread_id is not None:
                self.routing_state.active_thread_id = plan.target_thread_id
                self.mark_agent_picker_thread_closed(plan.thread_id or "")
                if plan.info_message:
                    self.chat_widget.add_info_message(plan.info_message, None)
                return
        self.chat_widget.handle(notification)

    def handle_server_request(self, request: ServerRequest) -> None:
        plan = plan_app_server_event(
            {"kind": "ServerRequest", "request": request},
            primary_thread_id=self.routing_state.primary_thread_id,
            pending_requests=self.pending_app_server_requests,
        )
        self.app_server_event_plans.append(plan)
        self._apply_app_server_event_plan(plan)

    def handle_bottom_pane_app_event(self, event: Any) -> ActiveThreadEventStream | None:
        """Execute a Rust-like app event emitted by an active bottom-pane view."""

        kind = str(getattr(event, "kind", ""))
        payload = dict(getattr(event, "payload", {}) or {})
        if kind == "ApproveRecentAutoReviewDenial":
            from ..chatwidget.permission_popups import approve_recent_auto_review_denial

            nested = approve_recent_auto_review_denial(
                self.chat_widget,
                str(payload.get("thread_id") or self.routing_state.active_thread_id or ""),
                str(payload.get("id") or ""),
            )
            result = None
            for nested_event in nested or ():
                result = self.handle_bottom_pane_app_event(nested_event)
            return result
        if kind == "InsertHistoryCell":
            self.insert_history_cell(payload["cell"])
            return None
        if kind == "OpenUrlInBrowser":
            url = str(payload.get("url") or "")
            self.opened_urls.append(url)
            if url:
                self.open_url_sink(url)
            return None
        if kind in {"RefreshConnectors", "SetAppEnabled"}:
            self.auxiliary_app_events.append((kind, payload))
            return None
        if kind == "FullScreenApprovalRequest":
            if self.full_screen_approval_sink is not None:
                self.full_screen_approval_sink(payload.get("request"))
            return None
        if kind == "SelectAgentThread":
            self.select_agent_thread_and_discard_side(
                str(payload.get("thread_id") or "")
            )
            return None
        if kind == "CodexOp":
            op = payload["op"]
            self._thread_event_store().note_outbound_op(op)
            self._record_app_server_request_resolution(op)
            return self.submit_op(op)
        if kind == "SubmitThreadOp":
            op = payload["op"]
            thread_id = str(payload.get("thread_id") or self.routing_state.active_thread_id or "")
            self._thread_event_store(thread_id).note_outbound_op(op)
            self._record_app_server_request_resolution(op)
            self.submitted_ops.append(op)
            return self.active_thread_runtime.submit_thread_op(thread_id, op)
        raise ValueError(f"unsupported AppEvent variant: {kind!r}")

    def _record_app_server_request_resolution(self, op: Any) -> None:
        resolution = self.pending_app_server_requests.take_resolution(op)
        if resolution is None:
            return
        self.replayed_interactive_request_ids.discard(resolution.request_id)
        self.projected_interactive_request_ids.discard(resolution.request_id)
        self.app_server_request_resolutions.append(resolution)
        self.refresh_pending_thread_approvals()

    def _apply_app_server_event_plan(self, plan: AppServerEventPlan) -> None:
        if "refresh_mcp_expected_servers" in plan.actions:
            self.refresh_mcp_startup_expected_servers()
        if "finish_mcp_startup_after_lag" in plan.actions:
            self.finish_mcp_startup_after_lag()
        if "handle_global_server_notification" in plan.actions and plan.notification is not None:
            self.handle_notification(_coerce_server_notification(plan.notification))
        if "enqueue_primary_thread_notification" in plan.actions and plan.notification is not None:
            self.handle_notification(_coerce_server_notification(plan.notification))
        if (
            {"enqueue_primary_thread_request", "enqueue_thread_request"}
            & set(plan.actions)
            and plan.request is not None
            and plan.thread_id is not None
        ):
            self._enqueue_server_request(plan.thread_id, plan.request)
        if "dismiss_app_server_request" in plan.actions and plan.request is not None:
            if self.app_server_request_dismiss_sink is not None:
                self.app_server_request_dismiss_sink(plan.request)
        if "add_error_message" in plan.actions and plan.message:
            self.chat_widget.add_error_message(plan.message)


def app_command_for_prompt(
    prompt: str,
    *,
    cwd: Path | str,
    approval_policy: Any = None,
    active_permission_profile: Any = None,
    model: str | None = None,
    reasoning_effort: Any = None,
    service_tier: Any = None,
) -> AppCommand:
    widget = _TerminalInputSubmissionWidget(
        cwd=Path(cwd),
        approval_policy=approval_policy,
        active_permission_profile=active_permission_profile,
        model=str(model or "terminal"),
        reasoning_effort=reasoning_effort,
        service_tier=service_tier,
    )
    accepted = submit_user_message_with_history_record(
        widget,
        UserMessage(prompt),
        UserMessageHistoryRecord.user_message_text(),
    )
    if not accepted or not widget.ops:
        raise ValueError("terminal user input was not accepted for submission")
    return widget.ops[-1]


def _runtime_turn_context_value(app_runtime: TuiAppRuntime, name: str, default: Any = None) -> Any:
    for source in (
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime.chat_widget, "config", None),
    ):
        value = getattr(source, name, None)
        value = value() if callable(value) and name != "features" else value
        if value is not None:
            return value
    return default


def _resolve_permission_profile_selection(
    profile_id: str,
    runtime: Any,
) -> tuple[PermissionProfile, ActivePermissionProfile]:
    """Resolve the menu id like Rust ``rebuild_config_for_permission_profile``."""

    preset_id_by_profile = {
        ":workspace": "auto",
        ":read-only": "read-only",
        ":danger-no-sandbox": "full-access",
    }
    preset_id = preset_id_by_profile.get(profile_id)
    if preset_id is not None:
        preset = next(
            (item for item in builtin_approval_presets() if item.id == preset_id),
            None,
        )
        if preset is None:
            raise ValueError(f"unsupported built-in permission profile `{profile_id}`")
        return preset.permission_profile, preset.active_permission_profile

    for source in (
        runtime,
        getattr(runtime, "session_config", None),
        getattr(runtime, "config", None),
    ):
        if source is None:
            continue
        resolver = getattr(source, "resolve_permission_profile", None)
        if not callable(resolver):
            continue
        resolved = resolver(profile_id)
        permission_profile = _field(resolved, "permission_profile", resolved)
        active_profile = _field(resolved, "active_permission_profile", None)
        if isinstance(permission_profile, PermissionProfile):
            if not isinstance(active_profile, ActivePermissionProfile):
                active_profile = ActivePermissionProfile.new(profile_id)
            return permission_profile, active_profile
    raise ValueError(f"unsupported permission profile `{profile_id}`")


def _coerce_approval_policy(value: Any) -> AskForApproval | Any | None:
    if value is None or isinstance(value, AskForApproval):
        return value
    try:
        return AskForApproval(str(getattr(value, "value", value)))
    except ValueError:
        return value


def _coerce_approvals_reviewer(value: Any) -> ApprovalsReviewer | None:
    if value is None or isinstance(value, ApprovalsReviewer):
        return value
    raw = str(getattr(value, "value", value)).strip()
    aliases = {
        "user": ApprovalsReviewer.USER,
        "autoreview": ApprovalsReviewer.AUTO_REVIEW,
        "auto-review": ApprovalsReviewer.AUTO_REVIEW,
        "auto_review": ApprovalsReviewer.AUTO_REVIEW,
        "guardian_subagent": ApprovalsReviewer.AUTO_REVIEW,
    }
    key = raw.rsplit(".", 1)[-1].lower()
    if key in aliases:
        return aliases[key]
    return ApprovalsReviewer.parse(raw)


def _set_runtime_field(target: Any, name: str, value: Any) -> None:
    if target is None:
        return
    if isinstance(target, MutableMapping):
        target[name] = value
        return
    try:
        setattr(target, name, value)
    except (AttributeError, TypeError):
        return


def _runtime_active_permission_profile_value(app_runtime: TuiAppRuntime) -> Any:
    for source in (
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime.chat_widget, "config", None),
    ):
        value = getattr(source, "active_permission_profile", None)
        if callable(value):
            return value()
        if value is not None:
            return value
    permissions = getattr(getattr(app_runtime.chat_widget, "config", None), "permissions", None)
    if permissions is not None:
        value = getattr(permissions, "active_permission_profile", None)
        if callable(value):
            return value()
        if value is not None:
            return value
    return None


def _runtime_model_for_user_turn(app_runtime: TuiAppRuntime) -> str:
    for source in (
        app_runtime.chat_widget,
        getattr(app_runtime.chat_widget, "config", None),
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
    ):
        for name in ("selected_model", "model", "model_slug", "requested_model"):
            value = getattr(source, name, None)
            value = value() if callable(value) else value
            if value is not None and str(value).strip():
                return str(value).strip()
    return (os.environ.get("PYCODEX_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"


def _runtime_reasoning_effort_for_user_turn(app_runtime: TuiAppRuntime) -> Any:
    for source in (
        app_runtime.chat_widget,
        getattr(app_runtime.chat_widget, "config", None),
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
    ):
        for name in ("effective_reasoning_effort", "model_reasoning_effort", "reasoning_effort"):
            value = getattr(source, name, None)
            value = value() if callable(value) else value
            if value is not None:
                return value
    return None


def _goal_continuation_app_command(prompt: str, *, cwd: Path | str) -> AppCommand:
    return AppCommand(
        "UserTurn",
        {
            "items": [{"kind": "text", "payload": {"text": str(prompt)}}],
            "cwd": Path(cwd),
            "final_output_json_schema": None,
            "hidden_goal_context": True,
        },
    )


def user_turn_prompt(op: AppCommand) -> str:
    if op.kind != "UserTurn":
        return ""
    items = op.payload.get("items") or []
    texts: list[str] = []
    for item in items:
        text = _item_text(item)
        if text is not None:
            texts.append(str(text))
    return "\n".join(texts)


def _model_client_state_value(model_client: Any, name: str) -> str | None:
    state = getattr(model_client, "state", None)
    value = getattr(state, name, None)
    value = value() if callable(value) else value
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _thread_goal_uuid(thread_id: Any) -> str:
    import uuid

    try:
        return str(uuid.UUID(str(thread_id)))
    except Exception as exc:
        raise RuntimeError(f"invalid thread id for goal command: {thread_id}") from exc


def _runtime_default_provider_id(session_config: Any, provider: Any) -> str:
    for source in (provider, session_config):
        for name in ("id", "name", "default_model_provider_id", "model_provider"):
            value = _field(source, name, None)
            if value is not None and str(value).strip():
                return str(value).strip()
    return "openai"


def _default_active_goal_status() -> Any:
    from pycodex.state.model.thread_goal import ThreadGoalStatus as StateThreadGoalStatus

    return StateThreadGoalStatus.ACTIVE


def _state_goal_status(status: Any) -> Any:
    from pycodex.state.model.thread_goal import ThreadGoalStatus as StateThreadGoalStatus

    raw = getattr(status, "value", status)
    text = str(raw)
    mapping = {
        "active": "active",
        "paused": "paused",
        "blocked": "blocked",
        "usageLimited": "usage_limited",
        "usage_limited": "usage_limited",
        "budgetLimited": "budget_limited",
        "budget_limited": "budget_limited",
        "complete": "complete",
    }
    return StateThreadGoalStatus.parse(mapping.get(text, text))


def _app_server_goal_status(status: Any) -> Any:
    from pycodex.app_server_protocol import ThreadGoalStatus as AppThreadGoalStatus

    raw = getattr(status, "value", status)
    mapping = {
        "active": AppThreadGoalStatus.ACTIVE,
        "paused": AppThreadGoalStatus.PAUSED,
        "blocked": AppThreadGoalStatus.BLOCKED,
        "usage_limited": AppThreadGoalStatus.USAGE_LIMITED,
        "usageLimited": AppThreadGoalStatus.USAGE_LIMITED,
        "budget_limited": AppThreadGoalStatus.BUDGET_LIMITED,
        "budgetLimited": AppThreadGoalStatus.BUDGET_LIMITED,
        "complete": AppThreadGoalStatus.COMPLETE,
    }
    return mapping[str(raw)]


def _thread_goal_token_budget(value: Any) -> int | None:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    if isinstance(value, bool):
        raise RuntimeError("thread goal token budget must be an integer")
    return int(value)


def _app_server_thread_goal_from_state(goal: Any) -> Any:
    from pycodex.app_server_protocol import ThreadGoal as AppThreadGoal

    created_at = _datetime_millis(_field(goal, "created_at", 0))
    updated_at = _datetime_millis(_field(goal, "updated_at", 0))
    return AppThreadGoal(
        thread_id=str(_field(goal, "thread_id")),
        objective=str(_field(goal, "objective")),
        status=_app_server_goal_status(_field(goal, "status")),
        token_budget=_field(goal, "token_budget", None),
        tokens_used=int(_field(goal, "tokens_used", 0) or 0),
        time_used_seconds=int(_field(goal, "time_used_seconds", 0) or 0),
        created_at=created_at,
        updated_at=updated_at,
    )


def _datetime_millis(value: Any) -> int:
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        return int(timestamp() * 1000)
    return int(value or 0)


def _set_runtime_model_value(target: Any, model: str) -> None:
    if target is None:
        return
    if isinstance(target, dict):
        target["model"] = model
        return
    for name in ("model", "model_slug", "requested_model"):
        if hasattr(target, name):
            try:
                setattr(target, name, model)
            except (AttributeError, TypeError):
                pass
            return
    try:
        setattr(target, "model", model)
    except (AttributeError, TypeError):
        return


def _set_runtime_reasoning_effort_value(target: Any, effort: str | None) -> None:
    if target is None:
        return
    if isinstance(target, dict):
        target["model_reasoning_effort"] = effort
        target["reasoning_effort"] = effort
        return
    wrote = False
    for name in ("model_reasoning_effort", "reasoning_effort"):
        try:
            setattr(target, name, effort)
            wrote = True
        except (AttributeError, TypeError):
            pass
    if wrote:
        return


def _set_runtime_model_details_reasoning_value(target: Any, effort: str | None) -> None:
    if target is None:
        return
    for name in ("model_details", "status_model_details"):
        current = target.get(name) if isinstance(target, dict) else getattr(target, name, None)
        updated = _model_details_with_reasoning_effort((), effort) if current is None else _model_details_with_reasoning_effort(current, effort)
        try:
            if isinstance(target, dict):
                target[name] = updated
            else:
                setattr(target, name, updated)
        except (AttributeError, TypeError):
            pass


def _model_details_with_reasoning_effort(details: Any, effort: str | None) -> tuple[str, ...]:
    retained: list[str] = []
    for detail in details if isinstance(details, (list, tuple)) else (details,):
        text = str(detail).strip()
        if not text:
            continue
        normalized = text.lower().replace("-", "_")
        if normalized.startswith("reasoning "):
            normalized = normalized.removeprefix("reasoning ").strip()
        if normalized in {
            "none",
            "none_",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "x_high",
            "extra_high",
            "extra high",
            "max",
            "ultra",
        }:
            continue
        retained.append(text)
    if effort:
        return (effort, *retained)
    return tuple(retained)


def exec_run_plan_for_app_command(op: AppCommand) -> ExecRunPlan:
    if op.kind == "Review":
        target = _review_target_for_protocol(op.payload.get("target"))
        return ExecRunPlan(InitialOperation.review(ReviewRequest(target=target)), _review_prompt_summary(target))
    if op.kind != "UserTurn":
        raise ValueError("active thread runtime supports only AppCommand::UserTurn or AppCommand::Review")
    if op.payload.get("hidden_goal_context"):
        return ExecRunPlan(
            InitialOperation.user_turn(user_inputs_for_app_command(op), op.payload.get("final_output_json_schema")),
            "Goal continuation",
        )
    return ExecRunPlan(
        InitialOperation.user_turn(user_inputs_for_app_command(op), op.payload.get("final_output_json_schema")),
        user_turn_prompt(op),
    )


def _protocol_thread_goal_from_any(goal: Any) -> ProtocolThreadGoal:
    if isinstance(goal, ProtocolThreadGoal):
        return goal
    thread_id_text = str(_field(goal, "thread_id", "") or "")
    try:
        thread_id = ThreadId.from_string(thread_id_text)
    except Exception:
        thread_id = ThreadId.new()
    status = _protocol_thread_goal_status(_field(goal, "status", ProtocolThreadGoalStatus.ACTIVE))
    return ProtocolThreadGoal(
        thread_id=thread_id,
        objective=str(_field(goal, "objective", "") or ""),
        status=status,
        tokens_used=int(_field(goal, "tokens_used", 0) or 0),
        time_used_seconds=int(_field(goal, "time_used_seconds", 0) or 0),
        created_at=int(_field(goal, "created_at", 0) or 0),
        updated_at=int(_field(goal, "updated_at", 0) or 0),
        token_budget=_field(goal, "token_budget", None),
    )


def _protocol_thread_goal_status(value: Any) -> ProtocolThreadGoalStatus:
    if isinstance(value, ProtocolThreadGoalStatus):
        return value
    raw = getattr(value, "value", value)
    mapping = {
        "active": ProtocolThreadGoalStatus.ACTIVE,
        "paused": ProtocolThreadGoalStatus.PAUSED,
        "blocked": ProtocolThreadGoalStatus.BLOCKED,
        "usage_limited": ProtocolThreadGoalStatus.USAGE_LIMITED,
        "usageLimited": ProtocolThreadGoalStatus.USAGE_LIMITED,
        "budget_limited": ProtocolThreadGoalStatus.BUDGET_LIMITED,
        "budgetLimited": ProtocolThreadGoalStatus.BUDGET_LIMITED,
        "complete": ProtocolThreadGoalStatus.COMPLETE,
    }
    return mapping[str(raw)]


def _review_target_for_protocol(value: Any) -> ReviewTarget:
    if isinstance(value, ReviewTarget):
        return value
    target_type = _field(value, "type")
    if target_type == "uncommittedChanges":
        return ReviewTarget.uncommitted_changes()
    if target_type == "baseBranch":
        return ReviewTarget.base_branch(str(_field(value, "branch") or ""))
    if target_type == "commit":
        title = _field(value, "title")
        return ReviewTarget.commit(str(_field(value, "sha") or ""), None if title is None else str(title))
    if target_type == "custom":
        return ReviewTarget.custom(str(_field(value, "instructions") or ""))
    if isinstance(value, Mapping):
        return ReviewTarget.from_mapping(dict(value))
    raise ValueError(f"unknown review target: {value!r}")


def _review_prompt_summary(target: ReviewTarget) -> str:
    if target.type == "custom":
        return str(target.instructions or "").strip()
    if target.type == "baseBranch":
        return f"Review changes against {target.branch}"
    if target.type == "commit":
        title = f": {target.title}" if target.title else ""
        return f"Review commit {target.sha}{title}"
    return "Review current changes"


def user_inputs_for_app_command(op: AppCommand) -> tuple[UserInput, ...]:
    if op.kind != "UserTurn":
        return ()
    user_inputs: list[UserInput] = []
    for item in op.payload.get("items") or ():
        raw_kind = _field(item, "kind")
        kind = str(raw_kind or "").lower()
        if kind == "text":
            user_inputs.append(UserInput.text_input(str(_item_text(item) or "")))
        elif kind in {"localimage", "local_image"}:
            path = _item_payload_field(item, "path")
            if path is not None:
                user_inputs.append(UserInput.local_image(Path(str(path))))
    if not user_inputs:
        prompt = user_turn_prompt(op)
        if prompt:
            user_inputs.append(UserInput.text_input(prompt))
    return tuple(user_inputs)


def _server_notifications_from_session_events(
    result: Any,
    *,
    thread_id: str,
    turn_id: str,
    pending_commands: dict[str, dict[str, Any]] | None = None,
    completed_commands: set[str] | None = None,
) -> tuple[ServerNotification, ...]:
    notifications: list[ServerNotification] = []
    for event in tuple(getattr(result, "session_events", ()) or ()):
        notifications.extend(
            _server_notifications_from_session_event(
                event,
                thread_id=thread_id,
                turn_id=turn_id,
                pending_commands=pending_commands,
                completed_commands=completed_commands,
            )
        )
    return tuple(notifications)


def _server_notifications_from_session_event(
    event: Any,
    *,
    thread_id: str,
    turn_id: str,
    pending_commands: dict[str, dict[str, Any]] | None = None,
    completed_commands: set[str] | None = None,
) -> tuple[ServerNotification, ...]:
    event_type = _field(event, "type")
    payload = _field(event, "payload", event)
    if event_type == "agent_message_content_delta":
        delta = getattr(payload, "delta", None)
        if isinstance(delta, str) and delta:
            return (ServerNotification("AgentMessageDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id}),)
    if event_type == "reasoning_summary_delta":
        delta = getattr(payload, "delta", None)
        if isinstance(delta, str) and delta:
            return (ServerNotification("ReasoningSummaryTextDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id}),)
    if event_type in {"reasoning_summary_part_added", "agent_reasoning_section_break"}:
        return (ServerNotification("ReasoningSummaryPartAdded", {"thread_id": thread_id, "turn_id": turn_id}),)
    if event_type in {"reasoning_content_delta", "reasoning_raw_content_delta"}:
        delta = getattr(payload, "delta", None)
        if isinstance(delta, str) and delta:
            return (ServerNotification("ReasoningTextDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id}),)
    if event_type == "response_created":
        return (ServerNotification("ResponseStarted", {"thread_id": thread_id, "turn_id": turn_id}),)
    if event_type == "token_count":
        token_usage = _thread_token_usage_from_token_count_event(payload)
        if token_usage is not None:
            return (
                ServerNotification(
                    "ThreadTokenUsageUpdated",
                    {
                        "thread_id": thread_id,
                        "token_usage": token_usage,
                    },
                ),
            )
    if event_type == "thread_goal_updated":
        goal = _field(payload, "goal", None)
        return (
            ServerNotification(
                "ThreadGoalUpdated",
                {
                    "thread_id": _thread_id_value(_field(payload, "thread_id", thread_id)),
                    "turn_id": _field(payload, "turn_id", turn_id),
                    "goal": goal,
                },
            ),
        )
    if event_type == "stream_error":
        message = _field(payload, "message", None)
        if not isinstance(message, str) or not message:
            return ()
        return (
            ServerNotification(
                "Error",
                {
                    "thread_id": _thread_id_value(_field(payload, "thread_id", thread_id)),
                    "turn_id": _field(payload, "turn_id", turn_id),
                    "will_retry": True,
                    "error": {
                        "message": message,
                        "codex_error_info": _field(payload, "codex_error_info", None),
                        "additional_details": _field(payload, "additional_details", None),
                    },
                },
            ),
        )
    if event_type == "error":
        message = _field(payload, "message", None)
        if not isinstance(message, str) or not message:
            message = "The model request failed."
        return (
            ServerNotification(
                "Error",
                {
                    "thread_id": _thread_id_value(_field(payload, "thread_id", thread_id)),
                    "turn_id": _field(payload, "turn_id", turn_id),
                    "will_retry": False,
                    "error": {
                        "message": message,
                        "codex_error_info": _field(payload, "codex_error_info", None),
                        "additional_details": _field(payload, "additional_details", None),
                    },
                },
            ),
        )
    if event_type in {"task_complete", "turn_complete"}:
        return (_turn_completed_notification(thread_id, turn_id, SimpleNamespace(turn_status="completed")),)
    if event_type in {"task_aborted", "turn_aborted"}:
        return (_turn_interrupted_notification(thread_id, turn_id),)
    if event_type in {"item_started", "item_completed"}:
        item = _chatwidget_item_from_turn_item(_field(payload, "item"))
        if item is None:
            return ()
        item_id = item.get("id")
        if item.get("kind") == "CommandExecution" and isinstance(item_id, str):
            if event_type == "item_started" and pending_commands is not None:
                pending_commands[item_id] = dict(item)
            if event_type == "item_completed" and completed_commands is not None:
                completed_commands.add(item_id)
        notification_kind = "ItemStarted" if event_type == "item_started" else "ItemCompleted"
        timestamp_name = "started_at_ms" if event_type == "item_started" else "completed_at_ms"
        timestamp_value = _field(payload, timestamp_name)
        if not isinstance(timestamp_value, int):
            timestamp_value = int(time.time() * 1000)
        return (
            ServerNotification(
                notification_kind,
                {
                    "thread_id": _thread_id_value(_field(payload, "thread_id", thread_id)),
                    "turn_id": _field(payload, "turn_id", turn_id),
                    timestamp_name: timestamp_value,
                    "item": item,
                },
            ),
        )
    if event_type == "response_output_item_done":
        item = _field(payload, "item")
        # Rust app-server does not turn the model's function_call response item
        # into a CommandExecution lifecycle event. Core tool events own the
        # canonical started/completed pair; projecting here creates two active
        # cells for the same call id and leaves the first one stuck Running.
        if _command_execution_item_from_response_item(item, status="InProgress") is not None:
            return ()
        turn_item = _turn_item_from_response_item(item)
        chat_item = _chatwidget_item_from_turn_item(turn_item)
        if chat_item is not None:
            return (
                ServerNotification(
                    "ItemCompleted",
                    {
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "completed_at_ms": int(time.time() * 1000),
                        "item": chat_item,
                    },
                ),
            )
    return ()


def _thread_token_usage_from_token_count_event(payload: Any) -> dict[str, Any] | None:
    """Project Rust ``TokenCountEvent.info`` into app-server token usage shape."""

    info = _field(payload, "info", payload)
    if info is None:
        return None
    total = _field(info, "total_token_usage", None)
    last = _field(info, "last_token_usage", None)
    if total is None and last is None:
        return None
    return {
        "total": _token_usage_mapping(total),
        "last": _token_usage_mapping(last),
        "model_context_window": _field(info, "model_context_window", None),
    }


def _token_usage_mapping(value: Any) -> dict[str, int]:
    return {
        "total_tokens": int(_field(value, "total_tokens", 0) or 0),
        "input_tokens": int(_field(value, "input_tokens", 0) or 0),
        "cached_input_tokens": int(_field(value, "cached_input_tokens", 0) or 0),
        "output_tokens": int(_field(value, "output_tokens", 0) or 0),
        "reasoning_output_tokens": int(_field(value, "reasoning_output_tokens", 0) or 0),
    }


def _chatwidget_item_from_turn_item(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    if isinstance(item, Mapping):
        raw_kind = item.get("kind") or item.get("type")
        if raw_kind is None:
            return None
        kind = _turn_item_kind(str(raw_kind))
        if kind == "CommandExecution":
            return _chatwidget_command_execution_item(item)
        result = dict(item)
        result.pop("type", None)
        result["kind"] = kind
        return result
    if isinstance(item, TurnItem):
        if item.type == "CommandExecution":
            return _chatwidget_command_execution_item(item.item)
        result = item.to_mapping()
        result.pop("type", None)
        result["kind"] = item.type
        return result
    raw_type = getattr(item, "type", None)
    raw_inner = getattr(item, "item", None)
    if isinstance(raw_type, str):
        if raw_type == "CommandExecution":
            return _chatwidget_command_execution_item(raw_inner)
        to_mapping = getattr(item, "to_mapping", None)
        result = to_mapping() if callable(to_mapping) else dict(getattr(item, "__dict__", {}))
        result.pop("type", None)
        result.pop("item", None)
        result["kind"] = raw_type
        return result
    return None


def _turn_item_from_response_item(item: Any) -> TurnItem | None:
    if item is None:
        return None
    response_item: ResponseItem | None
    if isinstance(item, ResponseItem):
        response_item = item
    elif isinstance(item, Mapping):
        try:
            response_item = ResponseItem.from_mapping(item)
        except (KeyError, TypeError, ValueError):
            return None
    else:
        to_mapping = getattr(item, "to_mapping", None)
        if callable(to_mapping):
            try:
                response_item = ResponseItem.from_mapping(to_mapping())
            except (KeyError, TypeError, ValueError):
                return None
        else:
            response_item = None
    return parse_turn_item(response_item) if response_item is not None else None


def _chatwidget_command_execution_item(value: Any) -> dict[str, Any]:
    status = _command_execution_status_name(_field(value, "status", "inProgress"))
    return {
        "kind": "CommandExecution",
        "id": str(_field(value, "id", "")),
        "command": str(_field(value, "command", "")),
        "cwd": _field(value, "cwd"),
        "process_id": _field(value, "process_id", _field(value, "processId")),
        "source": _command_execution_source_name(_field(value, "source", "agent")),
        "status": status,
        "command_actions": _field(value, "command_actions", _field(value, "commandActions", ())) or (),
        "aggregated_output": _field(value, "aggregated_output", _field(value, "aggregatedOutput")),
        "exit_code": _field(value, "exit_code", _field(value, "exitCode")),
        "duration_ms": _field(value, "duration_ms", _field(value, "durationMs")),
    }


def _turn_item_kind(value: str) -> str:
    return {
        "agentMessage": "AgentMessage",
        "commandExecution": "CommandExecution",
        "contextCompaction": "ContextCompaction",
        "dynamicToolCall": "DynamicToolCall",
        "enteredReviewMode": "EnteredReviewMode",
        "exitedReviewMode": "ExitedReviewMode",
        "fileChange": "FileChange",
        "hookPrompt": "HookPrompt",
        "imageGeneration": "ImageGeneration",
        "imageView": "ImageView",
        "mcpToolCall": "McpToolCall",
        "plan": "Plan",
        "reasoning": "Reasoning",
        "userMessage": "UserMessage",
        "webSearch": "WebSearch",
    }.get(value, value)


def _command_execution_status_name(value: Any) -> str:
    raw = getattr(value, "value", value)
    return {
        "inProgress": "InProgress",
        "completed": "Completed",
        "failed": "Failed",
        "declined": "Declined",
    }.get(str(raw), str(raw))


def _command_execution_source_name(value: Any) -> str:
    raw = getattr(value, "value", value)
    return {
        "agent": "agent",
        "userShell": "user_shell",
        "unifiedExecStartup": "unified_exec_startup",
        "unifiedExecInteraction": "unified_exec_interaction",
    }.get(str(raw), str(raw))


def _thread_id_value(value: Any) -> str:
    raw = getattr(value, "id", value)
    return str(raw)


def _command_completion_notifications_from_result(
    result: Any,
    *,
    thread_id: str,
    turn_id: str,
    pending_commands: dict[str, dict[str, Any]],
    completed_commands: set[str],
) -> tuple[ServerNotification, ...]:
    notifications: list[ServerNotification] = []
    for item in tuple(getattr(result, "tool_response_items", ()) or ()):
        call_id = _field(item, "call_id")
        if not isinstance(call_id, str) or call_id in completed_commands:
            continue
        started = pending_commands.get(call_id)
        if started is None:
            continue
        completed = dict(started)
        completed["status"] = "Completed" if _tool_output_success(item) is not False else "Failed"
        completed["aggregated_output"] = _tool_output_text(item)
        completed["exit_code"] = 0 if completed["status"] == "Completed" else 1
        completed["duration_ms"] = None
        completed_commands.add(call_id)
        notifications.append(
            ServerNotification(
                "ItemCompleted",
                {
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "completed_at_ms": int(time.time() * 1000),
                    "item": completed,
                },
            )
        )
    return tuple(notifications)


def _command_execution_item_from_response_item(item: Any, *, status: str) -> dict[str, Any] | None:
    item_type = _field(item, "type")
    name = _field(item, "name")
    if item_type not in {"function_call", "local_shell_call"}:
        return None
    if item_type == "function_call" and name not in {"exec_command", "local_shell", "shell"}:
        return None
    call_id = _field(item, "call_id") or _field(item, "id")
    if not isinstance(call_id, str) or not call_id:
        return None
    command, cwd = _command_and_cwd_from_tool_item(item)
    if not command:
        return None
    return {
        "kind": "CommandExecution",
        "id": call_id,
        "command": command,
        "cwd": cwd,
        "process_id": None,
        "source": "Agent",
        "status": status,
        "command_actions": [{"type": "unknown", "cmd": command}],
        "aggregated_output": None,
        "exit_code": None,
        "duration_ms": None,
    }


def _command_and_cwd_from_tool_item(item: Any) -> tuple[str, str | None]:
    if _field(item, "type") == "local_shell_call":
        action = _field(item, "action")
        command = _field(action, "command")
        return (str(command), _field(action, "workdir")) if command is not None else ("", None)
    arguments = _field(item, "arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return arguments, None
    if isinstance(arguments, Mapping):
        command = arguments.get("cmd", arguments.get("command"))
        cwd = arguments.get("workdir", arguments.get("cwd"))
        return (str(command), str(cwd) if cwd is not None else None) if command is not None else ("", None)
    return "", None


def _tool_output_text(item: Any) -> str | None:
    output = _field(item, "output")
    if output is None:
        return None
    to_text = getattr(output, "to_text", None)
    if callable(to_text):
        value = to_text()
        return None if value is None else str(value)
    if isinstance(output, Mapping):
        text = output.get("text")
        if isinstance(text, str):
            return text
    return str(output)


def _tool_output_success(item: Any) -> bool | None:
    output = _field(item, "output")
    success = _field(output, "success") if output is not None else None
    return success if isinstance(success, bool) else None


def _session_event_error_message(event: Any) -> str | None:
    event_type = _field(event, "type", None)
    if event_type not in {"stream_error", "error"}:
        return None
    payload = _field(event, "payload", None)
    message = _field(payload, "message", None)
    if isinstance(message, str) and message:
        details = _field(payload, "additional_details", None)
        if isinstance(details, str) and details and details != message:
            return f"{message}: {details}"
        return message
    return None


def _turn_started_notification(thread_id: str, turn_id: str) -> ServerNotification:
    return ServerNotification("TurnStarted", {"turn": {"id": turn_id, "thread_id": thread_id}})


def _turn_completed_notification(thread_id: str, turn_id: str, result: Any) -> ServerNotification:
    status = str(getattr(result, "turn_status", "completed") or "completed")
    if status == "completed":
        return ServerNotification("TurnCompleted", {"turn": {"id": turn_id, "thread_id": thread_id, "status": "Completed", "duration_ms": None}})
    if status.lower() == "interrupted":
        return _turn_interrupted_notification(thread_id, turn_id)
    return _turn_failed_notification(thread_id, turn_id, status, exit_code=1)


def _turn_interrupted_notification(thread_id: str, turn_id: str) -> ServerNotification:
    return ServerNotification(
        "TurnCompleted",
        {"turn": {"id": turn_id, "thread_id": thread_id, "status": "Interrupted", "duration_ms": None}},
    )


def _turn_failed_notification(thread_id: str, turn_id: str, message: str, *, exit_code: int) -> ServerNotification:
    return ServerNotification(
        "TurnCompleted",
        {"turn": {"id": turn_id, "thread_id": thread_id, "status": "Failed", "error": {"message": message, "codex_error_info": None, "exit_code": exit_code}}},
    )


def _coerce_server_notification(notification: Any) -> ServerNotification:
    if isinstance(notification, ServerNotification):
        return notification
    kind = _field(notification, "kind", _field(notification, "type", None))
    if kind is None:
        raise ValueError("app-server notification is missing kind/type")
    payload = _field(notification, "payload", None)
    return ServerNotification(str(kind), notification if payload is None else payload)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _request_thread_id(request: Any) -> str | None:
    params = _field(request, "params", None)
    value = _field(params, "thread_id", _field(params, "threadId", None))
    return None if value is None or not str(value) else str(value)


def _notification_thread_id(notification: Any) -> str | None:
    payload = _field(notification, "payload", notification)
    value = _field(payload, "thread_id", _field(payload, "threadId", None))
    if value is None:
        turn = _field(payload, "turn", None)
        value = _field(turn, "thread_id", _field(turn, "threadId", None))
    return None if value is None or not str(value) else str(value)


def _item_payload_field(value: Any, name: str, default: Any = None) -> Any:
    direct = _field(value, name, None)
    if direct is not None:
        return direct
    payload = _field(value, "payload", None)
    if isinstance(payload, Mapping):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _item_text(value: Any) -> Any:
    return _item_payload_field(value, "text")


@dataclass
class _TerminalMode:
    model_name: str = "terminal"
    effort: Any = None

    def model(self) -> str:
        return self.model_name

    def reasoning_effort(self) -> Any:
        return self.effort


@dataclass
class _TerminalPermissions:
    approval_policy: Any = None
    active_permission_profile_value: Any = None

    def active_permission_profile(self) -> Any:
        return self.active_permission_profile_value


@dataclass
class _TerminalFeatures:
    def enabled(self, _name: str) -> bool:
        return False


@dataclass
class _TerminalBottomPane:
    def take_recent_submission_images_with_placeholders(self) -> tuple[Any, ...]:
        return ()

    def take_recent_submission_mention_bindings(self) -> tuple[Any, ...]:
        return ()

    def skills(self) -> None:
        return None


@dataclass
class _TerminalInputQueue:
    queued_user_messages: Any = field(default_factory=list)
    queued_user_message_history_records: Any = field(default_factory=list)
    user_turn_pending_start: bool = False
    pending_steers: Any = field(default_factory=list)


@dataclass
class _TerminalInputSubmissionWidget:
    cwd: Path
    approval_policy: Any = None
    active_permission_profile: Any = None
    model: str = "terminal"
    reasoning_effort: Any = None
    service_tier: Any = None
    ops: list[AppCommand] = field(default_factory=list)
    bottom_pane: _TerminalBottomPane = field(default_factory=_TerminalBottomPane)
    input_queue: _TerminalInputQueue = field(default_factory=_TerminalInputQueue)

    def __post_init__(self) -> None:
        from types import SimpleNamespace

        self.turn_lifecycle = SimpleNamespace(agent_turn_running=False)
        self.transcript = SimpleNamespace(needs_final_message_separator=True, saw_plan_item_this_turn=False)
        self.config = SimpleNamespace(
            cwd=self.cwd,
            permissions=_TerminalPermissions(self.approval_policy, self.active_permission_profile),
            features=_TerminalFeatures(),
            personality=None,
        )

    def take_remote_image_urls(self) -> tuple[str, ...]:
        return ()

    def is_session_configured(self) -> bool:
        return True

    def current_model_supports_images(self) -> bool:
        return True

    def effective_collaboration_mode(self) -> _TerminalMode:
        return _TerminalMode(self.model, self.reasoning_effort)

    def collaboration_modes_enabled(self) -> bool:
        return False

    def current_model_supports_personality(self) -> bool:
        return False

    def service_tier_update_for_core(self) -> Any:
        return self.service_tier

    def maybe_apply_ide_context(self, _items: Any) -> None:
        return None

    def plugins_for_mentions(self) -> None:
        return None

    def connectors_for_mentions(self) -> None:
        return None

    def submit_op(self, op: AppCommand) -> bool:
        self.ops.append(op)
        return True

    def append_message_history_entry(self, _text: str) -> None:
        return None

    def on_user_message_display(self, _display: Any) -> None:
        return None


__all__ = [
    "ActiveThreadEventStream",
    "ActiveThreadRuntime",
    "CoreExecActiveThreadRuntime",
    "ExecFunctionActiveThreadRuntime",
    "QueueActiveThreadEventStream",
    "RUST_MODULE",
    "RUST_MODULE_CRATE",
    "RUST_SOURCE",
    "TuiAppRuntime",
    "app_command_for_prompt",
    "exec_run_plan_for_app_command",
    "user_inputs_for_app_command",
    "user_turn_prompt",
]
