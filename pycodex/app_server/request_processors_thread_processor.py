"""Thread request processor helpers ported from ``app-server/src/request_processors/thread_processor.rs``."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import invalid_params, invalid_request, method_not_found
from pycodex.app_server.request_processors_thread_lifecycle import merge_turn_history_with_active_turn
from pycodex.app_server.thread_status import resolve_thread_status
from pycodex.app_server_protocol import (
    DynamicToolSpec,
    JSONRPCErrorError,
    SortDirection,
    ThreadListCwdFilter,
    ThreadResumeParams,
    ThreadStatus,
    Turn,
    TurnStatus,
)

JsonValue = Any

THREAD_LIST_DEFAULT_LIMIT = 25
THREAD_LIST_MAX_LIMIT = 100
PERSIST_EXTENDED_HISTORY_DEPRECATION_SUMMARY = "persistExtendedHistory is deprecated and ignored"
PERSIST_EXTENDED_HISTORY_DEPRECATION_DETAILS = "Remove this parameter. App-server always uses limited history persistence."
THREAD_TURNS_DEFAULT_LIMIT = 25
THREAD_TURNS_MAX_LIMIT = 100

RESERVED_RESPONSES_NAMESPACES: tuple[str, ...] = (
    "api_tool",
    "browser",
    "computer",
    "container",
    "file_search",
    "functions",
    "image_gen",
    "multi_tool_use",
    "python",
    "python_user_visible",
    "submodel_delegator",
    "terminal",
    "tool_search",
    "web",
)


class ThreadProcessorJSONRPCError(Exception):
    """Exception wrapper for Rust-style JSON-RPC helper errors."""

    def __init__(self, error: JSONRPCErrorError) -> None:
        self.error = error
        self.code = error.code
        self.message = error.message
        self.data = error.data
        super().__init__(error.message)


@dataclass
class ThreadRequestProcessor:
    auth_manager: Any
    thread_manager: Any
    outgoing: Any
    arg0_paths: Any
    config: Any
    config_manager: Any
    thread_store: Any
    pending_thread_unloads: Any
    thread_state_manager: Any
    thread_watch_manager: Any
    thread_list_state_permit: Any
    thread_goal_processor: Any
    state_db: Any | None
    background_tasks: Any
    skills_watcher: Any

    @classmethod
    def new(
        cls,
        auth_manager: Any,
        thread_manager: Any,
        outgoing: Any,
        arg0_paths: Any,
        config: Any,
        config_manager: Any,
        thread_store: Any,
        pending_thread_unloads: Any,
        thread_state_manager: Any,
        thread_watch_manager: Any,
        thread_list_state_permit: Any,
        thread_goal_processor: Any,
        state_db: Any | None,
        background_tasks: Any,
        skills_watcher: Any,
    ) -> "ThreadRequestProcessor":
        return cls(
            auth_manager,
            thread_manager,
            outgoing,
            arg0_paths,
            config,
            config_manager,
            thread_store,
            pending_thread_unloads,
            thread_state_manager,
            thread_watch_manager,
            thread_list_state_permit,
            thread_goal_processor,
            state_db,
            background_tasks,
            skills_watcher,
        )


@dataclass(frozen=True)
class ThreadTurnsCursor:
    turn_id: str
    include_anchor: bool


@dataclass(frozen=True)
class ThreadTurnsPage:
    turns: tuple[Turn, ...]
    next_cursor: str | None
    backwards_cursor: str | None


def collect_resume_override_mismatches(request: ThreadResumeParams | Mapping[str, JsonValue], config_snapshot: Any) -> list[str]:
    request = request if isinstance(request, ThreadResumeParams) else ThreadResumeParams.from_mapping(request)
    details: list[str] = []
    _append_mismatch(details, request, "model", _get(config_snapshot, "model"), "model")
    _append_mismatch(details, request, "model_provider", _get(config_snapshot, "model_provider_id"), "model_provider")
    _append_mismatch(details, request, "service_tier", _get(config_snapshot, "service_tier"), "service_tier")
    if _has(request, "cwd") and _get(request, "cwd") is not None:
        requested = str(Path(str(_get(request, "cwd"))))
        active = str(_get(config_snapshot, "cwd"))
        if requested != active:
            details.append(f"cwd requested={requested} active={active}")
    if _has(request, "runtime_workspace_roots") and _get(request, "runtime_workspace_roots") is not None:
        requested_roots = tuple(str(Path(str(item))) for item in _get(request, "runtime_workspace_roots"))
        active_roots = tuple(str(item) for item in (_get(config_snapshot, "workspace_roots") or ()))
        if requested_roots != active_roots:
            details.append(f"runtime_workspace_roots requested={requested_roots!r} active={active_roots!r}")
    _append_mismatch(details, request, "approval_policy", _get(config_snapshot, "approval_policy"), "approval_policy")
    _append_mismatch(details, request, "approvals_reviewer", _get(config_snapshot, "approvals_reviewer"), "approvals_reviewer")
    _append_mismatch(details, request, "sandbox", _get(config_snapshot, "sandbox"), "sandbox")
    if _has(request, "permissions") and _get(request, "permissions") is not None:
        details.append(f"permissions override was provided and ignored while running; active={_get(config_snapshot, 'active_permission_profile')!r}")
    _append_mismatch(details, request, "personality", _get(config_snapshot, "personality"), "personality")
    for field_name, label in (
        ("config", "config overrides were provided and ignored while running"),
        ("base_instructions", "baseInstructions override was provided and ignored while running"),
        ("developer_instructions", "developerInstructions override was provided and ignored while running"),
    ):
        if _has(request, field_name) and _get(request, field_name) is not None:
            details.append(label)
    return details


def merge_persisted_resume_metadata(
    request_overrides: dict[str, JsonValue] | None,
    typesafe_overrides: Any,
    persisted_metadata: Any,
) -> dict[str, JsonValue] | None:
    if has_model_resume_override(request_overrides, typesafe_overrides):
        return request_overrides
    _set(typesafe_overrides, "model", _get(persisted_metadata, "model"))
    _set(typesafe_overrides, "model_provider", _get(persisted_metadata, "model_provider"))
    reasoning_effort = _get(persisted_metadata, "reasoning_effort")
    if reasoning_effort is not None:
        if request_overrides is None:
            request_overrides = {}
        request_overrides["model_reasoning_effort"] = str(reasoning_effort)
    return request_overrides


def normalize_thread_list_cwd_filters(cwd: ThreadListCwdFilter | str | Iterable[str] | None) -> tuple[str, ...] | None:
    if cwd is None:
        return None
    parsed = cwd if isinstance(cwd, ThreadListCwdFilter) else ThreadListCwdFilter(cwd)
    values = parsed.value if isinstance(parsed.value, tuple) else (parsed.value,)
    normalized: list[str] = []
    for raw_cwd in values:
        try:
            normalized.append(str(Path(raw_cwd).resolve()))
        except Exception as exc:
            raise ThreadProcessorJSONRPCError(invalid_params(f"invalid thread/list cwd filter `{raw_cwd}`: {exc}")) from exc
    return tuple(normalized)


def has_model_resume_override(request_overrides: Mapping[str, JsonValue] | None, typesafe_overrides: Any) -> bool:
    return bool(
        _get(typesafe_overrides, "model") is not None
        or _get(typesafe_overrides, "model_provider") is not None
        or (request_overrides is not None and "model" in request_overrides)
        or (request_overrides is not None and "model_reasoning_effort" in request_overrides)
    )


def validate_dynamic_tools(
    tools: Iterable[DynamicToolSpec | Mapping[str, JsonValue]],
    *,
    schema_validator: Callable[[JsonValue], None] | None = None,
) -> None:
    seen: set[tuple[str | None, str]] = set()
    for raw_tool in tools:
        tool = raw_tool if isinstance(raw_tool, DynamicToolSpec) else DynamicToolSpec.from_mapping(raw_tool)
        name = tool.name.strip()
        if not name:
            raise ValueError("dynamic tool name must not be empty")
        if name != tool.name:
            raise ValueError(f"dynamic tool name has leading/trailing whitespace: {_escape_identifier_for_error(tool.name)}")
        _validate_dynamic_tool_identifier(name, "dynamic tool name", 128)
        if name == "mcp" or name.startswith("mcp__"):
            raise ValueError(f"dynamic tool name is reserved: {name}")

        namespace = tool.namespace.strip() if tool.namespace is not None else None
        if namespace is not None:
            if not namespace:
                raise ValueError(f"dynamic tool namespace must not be empty for {name}")
            if namespace != tool.namespace:
                raise ValueError(
                    "dynamic tool namespace has leading/trailing whitespace for "
                    f"{_escape_identifier_for_error(name)}: {_escape_identifier_for_error(namespace)}"
                )
            _validate_dynamic_tool_identifier(namespace, "dynamic tool namespace", 64)
            if namespace == "mcp" or namespace.startswith("mcp__"):
                raise ValueError(f"dynamic tool namespace is reserved for {name}: {namespace}")
            if namespace in RESERVED_RESPONSES_NAMESPACES:
                raise ValueError(
                    "dynamic tool namespace collides with a reserved Responses API namespace "
                    f"for {name}: {namespace}"
                )

        key = (namespace, name)
        if key in seen:
            if namespace is not None:
                raise ValueError(f"duplicate dynamic tool name in namespace {namespace}: {name}")
            raise ValueError(f"duplicate dynamic tool name: {name}")
        seen.add(key)
        if tool.defer_loading and namespace is None:
            raise ValueError(f"deferred dynamic tool must include a namespace: {name}")
        if schema_validator is not None:
            try:
                schema_validator(tool.input_schema)
            except Exception as exc:
                raise ValueError(f"dynamic tool input schema is not supported for {name}: {exc}") from exc


def serialize_thread_turns_cursor(turn_id: str, include_anchor: bool) -> str:
    return json.dumps({"turnId": turn_id, "includeAnchor": include_anchor}, separators=(",", ":"))


def parse_thread_turns_cursor(cursor: str) -> ThreadTurnsCursor:
    try:
        data = json.loads(cursor)
        return ThreadTurnsCursor(turn_id=str(data["turnId"]), include_anchor=bool(data["includeAnchor"]))
    except Exception as exc:
        raise ThreadProcessorJSONRPCError(invalid_request(f"invalid cursor: {cursor}")) from exc


def paginate_thread_turns(
    turns: Iterable[Turn],
    cursor: str | None = None,
    limit: int | None = None,
    sort_direction: SortDirection | str = SortDirection.ASC,
) -> ThreadTurnsPage:
    turns = tuple(turns)
    if not turns:
        return ThreadTurnsPage(turns=(), next_cursor=None, backwards_cursor=None)

    direction = SortDirection.parse(sort_direction)
    anchor = parse_thread_turns_cursor(cursor) if cursor is not None else None
    page_size = max(1, min(int(limit) if limit is not None else THREAD_TURNS_DEFAULT_LIMIT, THREAD_TURNS_MAX_LIMIT))
    anchor_index = None
    if anchor is not None:
        for index, turn in enumerate(turns):
            if turn.id == anchor.turn_id:
                anchor_index = index
                break
        if anchor_index is None:
            raise ThreadProcessorJSONRPCError(invalid_request("invalid cursor: anchor turn is no longer present"))

    keyed = list(enumerate(turns))
    if direction is SortDirection.ASC:
        if anchor is not None and anchor_index is not None:
            keyed = [
                (idx, turn)
                for idx, turn in keyed
                if (idx >= anchor_index if anchor.include_anchor else idx > anchor_index)
            ]
    else:
        keyed.reverse()
        if anchor is not None and anchor_index is not None:
            keyed = [
                (idx, turn)
                for idx, turn in keyed
                if (idx <= anchor_index if anchor.include_anchor else idx < anchor_index)
            ]

    more = len(keyed) > page_size
    keyed = keyed[:page_size]
    backwards_cursor = serialize_thread_turns_cursor(keyed[0][1].id, True) if keyed else None
    next_cursor = serialize_thread_turns_cursor(keyed[-1][1].id, False) if more and keyed else None
    return ThreadTurnsPage(turns=tuple(turn for _, turn in keyed), next_cursor=next_cursor, backwards_cursor=backwards_cursor)


def reconstruct_thread_turns_for_turns_list(
    turns: Iterable[Turn],
    loaded_status: ThreadStatus,
    has_live_running_thread: bool,
    active_turn: Turn | None = None,
) -> list[Turn]:
    has_live_in_progress_turn = has_live_running_thread or (
        active_turn is not None and active_turn.status == TurnStatus.IN_PROGRESS
    )
    reconstructed = list(turns)
    normalize_thread_turns_status(reconstructed, loaded_status, has_live_in_progress_turn)
    if active_turn is not None:
        reconstructed = merge_turn_history_with_active_turn(reconstructed, active_turn)
    return reconstructed


def normalize_thread_turns_status(
    turns: list[Turn],
    loaded_status: ThreadStatus,
    has_live_in_progress_turn: bool,
) -> None:
    status = resolve_thread_status(loaded_status, has_live_in_progress_turn)
    if getattr(status, "type", None) == "active":
        return
    for index, turn in enumerate(turns):
        if turn.status == TurnStatus.IN_PROGRESS:
            turns[index] = _replace_or_set(turn, status=TurnStatus.INTERRUPTED)


def unsupported_thread_store_operation(operation: str) -> JSONRPCErrorError:
    return method_not_found(f"{operation} is not supported yet")


def set_thread_name_from_title(thread: Any, title: str) -> Any:
    if not title.strip() or str(_get(thread, "preview", "")).strip() == title.strip():
        return thread
    return _replace_or_set(thread, name=title)


def requested_permissions_trust_project(overrides: Any, cwd: str | Path) -> bool:
    sandbox_mode = _get(overrides, "sandbox_mode")
    if sandbox_mode in {"workspace-write", "workspaceWrite", "danger-full-access", "dangerFullAccess"}:
        return True
    default_permissions = _get(overrides, "default_permissions")
    if default_permissions in {"workspace-write", "danger-full-access"}:
        return True
    profile = _get(overrides, "permission_profile")
    return permission_profile_trusts_project(profile, cwd) if profile is not None else False


def permission_profile_trusts_project(profile: Any, cwd: str | Path) -> bool:
    profile_type = _get(profile, "type", _get(profile, "kind", profile))
    if profile_type in {"disabled", "external", "Disabled", "External"}:
        return True
    checker = getattr(profile, "can_write_path_with_cwd", None)
    if callable(checker):
        return bool(checker(Path(cwd), Path(cwd)))
    return False


def _append_mismatch(details: list[str], request: Any, field_name: str, active_value: Any, label: str) -> None:
    if _has(request, field_name) and _get(request, field_name) is not None and _get(request, field_name) != active_value:
        details.append(f"{label} requested={_get(request, field_name)!r} active={active_value!r}")


def _validate_dynamic_tool_identifier(value: str, label: str, max_len: int) -> None:
    if not all(char.isascii() and (char.isalnum() or char in "_-") for char in value):
        raise ValueError(
            f"{label} must match ^[a-zA-Z0-9_-]+$ to match Responses API: {_escape_identifier_for_error(value)}"
        )
    if len(value) > max_len:
        raise ValueError(f"{label} must be at most {max_len} characters to match Responses API: {_escape_identifier_for_error(value)}")


def _escape_identifier_for_error(value: str) -> str:
    return value.encode("unicode_escape").decode("ascii")


def _has(obj: Any, name: str) -> bool:
    if isinstance(obj, Mapping):
        return name in obj
    return hasattr(obj, name)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _set(obj: Any, name: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[name] = value
    else:
        setattr(obj, name, value)


def _replace_or_set(obj: Any, **changes: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses

        return dataclasses.replace(obj, **changes)
    if hasattr(obj, "_fields"):
        fields = dict(obj._fields)
        fields.update(changes)
        return obj.__class__(**fields)
    for key, value in changes.items():
        setattr(obj, key, value)
    return obj


__all__ = [
    "PERSIST_EXTENDED_HISTORY_DEPRECATION_DETAILS",
    "PERSIST_EXTENDED_HISTORY_DEPRECATION_SUMMARY",
    "THREAD_LIST_DEFAULT_LIMIT",
    "THREAD_LIST_MAX_LIMIT",
    "THREAD_TURNS_DEFAULT_LIMIT",
    "THREAD_TURNS_MAX_LIMIT",
    "ThreadRequestProcessor",
    "ThreadTurnsCursor",
    "ThreadTurnsPage",
    "collect_resume_override_mismatches",
    "has_model_resume_override",
    "merge_persisted_resume_metadata",
    "normalize_thread_list_cwd_filters",
    "normalize_thread_turns_status",
    "paginate_thread_turns",
    "parse_thread_turns_cursor",
    "permission_profile_trusts_project",
    "reconstruct_thread_turns_for_turns_list",
    "requested_permissions_trust_project",
    "serialize_thread_turns_cursor",
    "set_thread_name_from_title",
    "unsupported_thread_store_operation",
    "validate_dynamic_tools",
]
