"""Semantic Python port of Rust ``codex-tui::app_server_session``.

Upstream source: ``codex/codex-rs/tui/src/app_server_session.rs``.

This module intentionally models the app-server session contract with
standard-library Python values instead of the Rust protocol/ratatui types.
Large response decoding and concrete app-server transport remain runtime
boundaries; request construction and pure helper behavior are ported here.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app_server_session",
    source="codex/codex-rs/tui/src/app_server_session.rs",
    status="complete",
)

JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
THREAD_SETTINGS_UPDATE_METHOD = "thread/settings/update"


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _set_if_not_none(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        target[key] = value


def _as_path_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).replace("\\", "/")


def _params_from_args(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> dict[str, Any]:
    if len(args) == 1 and isinstance(args[0], Mapping) and not kwargs:
        return dict(args[0])
    params: dict[str, Any] = {}
    for index, value in enumerate(args):
        params[f"arg{index}"] = value
    params.update(kwargs)
    return params


def _thread_id_params(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> dict[str, Any]:
    if len(args) == 1 and not kwargs:
        return {"thread_id": args[0]}
    return _params_from_args(args, kwargs)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def bootstrap_request_error(context: str, err: Any) -> RuntimeError:
    """Match Rust's bootstrap error context wrapping."""

    return RuntimeError(f"{context}: {err}")


def is_thread_settings_update_unsupported(source: Any) -> bool:
    """Return whether a JSON-RPC error means thread/settings/update is absent.

    Rust treats method-not-found as unsupported and also accepts older
    invalid-request responses that mention the method name in their message.
    """

    error = _get(source, "error", source)
    code = _get(error, "code")
    message = str(_get(error, "message", ""))
    return code == JSONRPC_METHOD_NOT_FOUND or (
        code == JSONRPC_INVALID_REQUEST and THREAD_SETTINGS_UPDATE_METHOD in message
    )


@dataclass(frozen=True)
class AppServerBootstrap:
    account_email: str | None = None
    auth_mode: Any = None
    status_account_display: str | None = None
    plan_type: str | None = None
    requires_openai_auth: bool = False
    default_model: Any = None
    feedback_audience: Any = None
    has_chatgpt_account: bool = False
    available_models: list[Any] = field(default_factory=list)


class ThreadParamsMode(str, Enum):
    Embedded = "Embedded"
    Remote = "Remote"

    def model_provider_from_config(self, config: Any) -> Any:
        if self is ThreadParamsMode.Embedded:
            return _get(config, "model_provider_id")
        return None


@dataclass(frozen=True)
class TurnPermissionsOverride:
    kind: str
    value: Any = None

    @classmethod
    def Preserve(cls) -> "TurnPermissionsOverride":
        return cls("Preserve")

    @classmethod
    def ActiveProfile(cls, profile_id: Any) -> "TurnPermissionsOverride":
        return cls("ActiveProfile", profile_id)

    @classmethod
    def LegacySandbox(cls, sandbox: Any) -> "TurnPermissionsOverride":
        return cls("LegacySandbox", sandbox)


@dataclass(frozen=True)
class ThreadLifecycleParams:
    cwd: str | None = None
    model_provider: Any = None
    sandbox: Any = None
    permissions: Any = None
    config_overrides: dict[str, Any] = field(default_factory=dict)
    service_tier: Any = None
    thread_source: Any = None
    base_instructions: str | None = None
    developer_instructions: str | None = None
    thread_id: Any = None
    source_thread_id: Any = None

    def as_request_params(self) -> dict[str, Any]:
        data = {
            "cwd": self.cwd,
            "model_provider": self.model_provider,
            "sandbox": self.sandbox,
            "permissions": self.permissions,
            "config_overrides": dict(self.config_overrides),
            "service_tier": self.service_tier,
            "thread_source": self.thread_source,
            "base_instructions": self.base_instructions,
            "developer_instructions": self.developer_instructions,
            "thread_id": self.thread_id,
            "source_thread_id": self.source_thread_id,
        }
        return {key: value for key, value in data.items() if value is not None}


@dataclass(frozen=True)
class AppServerStartedThread:
    session: Any
    turns: list[Any] = field(default_factory=list)


@dataclass
class AppServerSession:
    client: Any
    thread_params_mode_value: ThreadParamsMode
    next_request_id_value: int = 1
    remote_cwd_override_value: str | None = None
    thread_settings_update_supported: bool = True
    default_model: Any = None
    available_models: list[Any] = field(default_factory=list)

    @classmethod
    def new(cls, client: Any, thread_params_mode: ThreadParamsMode | str) -> "AppServerSession":
        return cls(client=client, thread_params_mode_value=ThreadParamsMode(thread_params_mode))

    def with_remote_cwd_override(self, remote_cwd_override: str | Path | None) -> "AppServerSession":
        self.remote_cwd_override_value = _as_path_string(remote_cwd_override)
        return self

    def remote_cwd_override(self) -> str | None:
        return self.remote_cwd_override_value

    def uses_remote_workspace(self) -> bool:
        return self.thread_params_mode_value is ThreadParamsMode.Remote

    def server_version(self) -> Any:
        version = _get(self.client, "server_version")
        if callable(version):
            return version()
        return version

    def thread_params_mode(self) -> ThreadParamsMode:
        return self.thread_params_mode_value

    def request_handle(self) -> Any:
        handle = _get(self.client, "request_handle")
        if callable(handle):
            return handle()
        return handle

    def next_request_id(self) -> int:
        request_id = self.next_request_id_value
        self.next_request_id_value += 1
        return request_id

    async def _request_typed(self, request_type: str, params: Mapping[str, Any] | None, context: str) -> Any:
        request = {
            "type": request_type,
            "request_id": self.next_request_id(),
            "params": dict(params or {}),
        }
        try:
            sender = getattr(self.client, "request_typed")
            return await _maybe_await(sender(request))
        except Exception as exc:  # pragma: no cover - exercised by callers.
            raise bootstrap_request_error(context, exc) from exc

    async def read_account(self) -> Any:
        return await self._request_typed(
            "GetAccount",
            {"refresh_token": False},
            "account/read failed during TUI bootstrap",
        )

    async def external_agent_config_detect(self, params: Any) -> Any:
        return await self._request_typed(
            "ExternalAgentConfigDetect",
            {"params": params},
            "external agent config detection failed",
        )

    async def external_agent_config_import(self, migration_items: Any) -> Any:
        return await self._request_typed(
            "ExternalAgentConfigImport",
            {"migration_items": migration_items},
            "external agent config import failed",
        )

    async def next_event(self) -> Any:
        return await _maybe_await(self.client.next_event())

    async def start_thread(self, config: Any) -> Any:
        return await start_thread_with_request_handle(
            self.request_handle(),
            thread_start_params_from_config(
                config,
                self.thread_params_mode_value,
                self.remote_cwd_override_value,
                session_start_source=None,
            ),
        )

    async def start_thread_with_session_start_source(self, config: Any, session_start_source: Any) -> Any:
        return await start_thread_with_request_handle(
            self.request_handle(),
            thread_start_params_from_config(
                config,
                self.thread_params_mode_value,
                self.remote_cwd_override_value,
                session_start_source=session_start_source,
            ),
        )

    async def resume_thread(self, config: Any, thread_id: Any) -> Any:
        params = thread_resume_params_from_config(
            config,
            thread_id,
            self.thread_params_mode_value,
            self.remote_cwd_override_value,
        )
        return await self._request_typed("ThreadResume", params.as_request_params(), "thread/resume failed")

    async def fork_thread(self, config: Any, source_thread_id: Any, base_instructions: str | None = None, developer_instructions: str | None = None) -> Any:
        params = thread_fork_params_from_config(
            config,
            source_thread_id,
            self.thread_params_mode_value,
            self.remote_cwd_override_value,
            base_instructions=base_instructions,
            developer_instructions=developer_instructions,
        )
        return await self._request_typed("ThreadFork", params.as_request_params(), "thread/fork failed")

    def session_config_with_effective_service_tier(self, config: Any) -> dict[str, Any]:
        return {
            "config": config,
            "service_tier": service_tier_override_from_config(config),
            "default_model": self.default_model,
            "available_models": list(self.available_models),
        }

    async def bootstrap(self, *args: Any, **kwargs: Any) -> Any:
        config = args[0] if args else kwargs.get("config")
        account = await self.read_account()
        models = await self._request_typed(
            "ModelList",
            {"cursor": None, "limit": None, "include_hidden": True},
            "model/list failed during TUI bootstrap",
        )
        raw_models = _get(models, "data", models if isinstance(models, list) else [])
        available_models = [model_preset_from_api_model(model) for model in raw_models]
        default_model = _get(config, "model") or next((_get(model, "model") for model in available_models if _get(model, "is_default")), None)
        if default_model is None and available_models:
            default_model = _get(available_models[0], "model")
        if default_model is None:
            raise RuntimeError("model/list returned no models for TUI bootstrap")
        self.default_model = default_model
        self.available_models = available_models

        account_data = _get(account, "account", None)
        account_kind = _get(account_data, "kind", _get(account_data, "type", account_data))
        email = _get(account_data, "email")
        plan_type = _get(account_data, "plan_type")
        auth_mode = _get(account, "auth_mode", None)
        if account_kind == "ApiKey":
            auth_mode = "ApiKey"
        elif account_kind in {"Chatgpt", "ChatGPT"}:
            auth_mode = "ChatGPT"
        return AppServerBootstrap(
            account_email=email,
            auth_mode=auth_mode,
            status_account_display=status_account_display_from_auth_mode(auth_mode, plan_type),
            plan_type=plan_type,
            requires_openai_auth=bool(_get(account, "requires_openai_auth", False)),
            default_model=default_model,
            feedback_audience="OpenAiEmployee" if isinstance(email, str) and email.endswith("@openai.com") else "External",
            has_chatgpt_account=account_kind in {"Chatgpt", "ChatGPT"},
            available_models=available_models,
        )

    async def fork_parent_title_from_app_server(self, *args: Any, **kwargs: Any) -> Any:
        thread_id = args[0] if args else kwargs.get("thread_id")
        if thread_id is None:
            return None
        response = await self.thread_read(thread_id)
        return _get(_get(response, "thread", response), "name", _get(_get(response, "thread", response), "preview"))

    async def thread_list(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadList", _params_from_args(args, kwargs), "thread/list failed")

    async def thread_loaded_list(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadLoadedList", _params_from_args(args, kwargs), "thread/loaded/list failed")

    async def thread_read(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadRead", _thread_id_params(args, kwargs), "thread/read failed")

    async def thread_metadata_update_branch(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadMetadataUpdate", _params_from_args(args, kwargs), "thread/metadata/update failed")

    async def thread_settings_update(self, *args: Any, **kwargs: Any) -> Any:
        if not self.thread_settings_update_supported:
            return None
        try:
            return await self._request_typed("ThreadSettingsUpdate", _params_from_args(args, kwargs), "thread/settings/update failed")
        except RuntimeError as exc:
            cause = exc.__cause__
            if cause is not None and is_thread_settings_update_unsupported(cause):
                self.thread_settings_update_supported = False
                return None
            raise

    async def thread_inject_items(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadInjectItems", _params_from_args(args, kwargs), "thread/inject_items failed")

    async def turn_start(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("TurnStart", _params_from_args(args, kwargs), "turn/start failed")

    async def turn_interrupt(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("TurnInterrupt", _params_from_args(args, kwargs), "turn/interrupt failed")

    async def startup_interrupt(self, *args: Any, **kwargs: Any) -> Any:
        return await self.turn_interrupt(*args, **kwargs)

    async def turn_steer(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("TurnSteer", _params_from_args(args, kwargs), "turn/steer failed")

    async def thread_set_name(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadSetName", _params_from_args(args, kwargs), "thread/set_name failed")

    async def thread_memory_mode_set(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadMemoryModeSet", _params_from_args(args, kwargs), "thread/memory_mode/set failed")

    async def memory_reset(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("MemoryReset", _params_from_args(args, kwargs), "memory/reset failed")

    async def thread_goal_get(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadGoalGet", _params_from_args(args, kwargs), "thread/goal/get failed")

    async def thread_goal_set(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadGoalSet", _params_from_args(args, kwargs), "thread/goal/set failed")

    async def thread_goal_clear(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadGoalClear", _params_from_args(args, kwargs), "thread/goal/clear failed")

    async def logout_account(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("LogoutAccount", _params_from_args(args, kwargs), "account/logout failed")

    async def thread_unsubscribe(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadUnsubscribe", _thread_id_params(args, kwargs), "thread/unsubscribe failed")

    async def thread_compact_start(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadCompactStart", _params_from_args(args, kwargs), "thread/compact/start failed")

    async def thread_shell_command(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadShellCommand", _params_from_args(args, kwargs), "thread/shell_command failed")

    async def thread_approve_guardian_denied_action(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadApproveGuardianDeniedAction", _params_from_args(args, kwargs), "thread/approve_guardian_denied_action failed")

    async def thread_background_terminals_clean(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadBackgroundTerminalsClean", _params_from_args(args, kwargs), "thread/background_terminals/clean failed")

    async def thread_rollback(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadRollback", _params_from_args(args, kwargs), "thread/rollback failed")

    async def review_start(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ReviewStart", _params_from_args(args, kwargs), "review/start failed")

    async def skills_list(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("SkillsList", _params_from_args(args, kwargs), "skills/list failed")

    async def reload_user_config(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ConfigReload", _params_from_args(args, kwargs), "config/reload failed")

    async def thread_realtime_start(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadRealtimeStart", _params_from_args(args, kwargs), "thread/realtime/start failed")

    async def thread_realtime_audio(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadRealtimeAppendAudio", _params_from_args(args, kwargs), "thread/realtime/audio failed")

    async def thread_realtime_stop(self, *args: Any, **kwargs: Any) -> Any:
        return await self._request_typed("ThreadRealtimeStop", _params_from_args(args, kwargs), "thread/realtime/stop failed")

    async def reject_server_request(self, *args: Any, **kwargs: Any) -> Any:
        handle = self.request_handle()
        reject = getattr(handle, "reject_server_request", None)
        if callable(reject):
            return await _maybe_await(reject(*args, **kwargs))
        return await self._request_typed("RejectServerRequest", _params_from_args(args, kwargs), "server request reject failed")

    async def resolve_server_request(self, *args: Any, **kwargs: Any) -> Any:
        handle = self.request_handle()
        resolve = getattr(handle, "resolve_server_request", None)
        if callable(resolve):
            return await _maybe_await(resolve(*args, **kwargs))
        return await self._request_typed("ResolveServerRequest", _params_from_args(args, kwargs), "server request resolve failed")

    async def shutdown(self, *args: Any, **kwargs: Any) -> Any:
        shutdown = getattr(self.client, "shutdown", None)
        if callable(shutdown):
            return await _maybe_await(shutdown(*args, **kwargs))
        return None


async def start_thread_with_request_handle(request_handle: Any, params: ThreadLifecycleParams | Mapping[str, Any]) -> Any:
    payload = params.as_request_params() if isinstance(params, ThreadLifecycleParams) else dict(params)
    sender = getattr(request_handle, "start_thread", None)
    if sender is None:
        sender = getattr(request_handle, "request_typed")
        return await _maybe_await(sender({"type": "ThreadStart", "params": payload}))
    return await _maybe_await(sender(payload))


def thread_realtime_start_params(config: Any) -> dict[str, Any]:
    return {
        "model": _get(config, "model"),
        "cwd": _as_path_string(_get(config, "cwd")),
    }


def status_account_display_from_auth_mode(auth_mode: Any, plan_type: Any = None) -> str | None:
    mode = str(_get(auth_mode, "name", auth_mode))
    if mode in {"None", "NoneAuth", "null"}:
        return None
    if mode == "ApiKey":
        return "ApiKey"
    if mode == "ChatGPT":
        plan = _get(auth_mode, "plan_type", plan_type)
        remapped = {
            "EnterpriseCbpUsageBased": "Enterprise",
            "SelfServeBusinessUsageBased": "Business",
        }.get(str(plan), plan)
        return str(remapped) if remapped else "ChatGPT"
    return mode


def model_preset_from_api_model(model: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for source, target in (
        ("model", "model"),
        ("id", "model"),
        ("name", "name"),
        ("display_name", "name"),
        ("is_default", "is_default"),
        ("service_tier", "service_tier"),
        ("availability", "availability"),
        ("upgrade", "upgrade"),
    ):
        value = _get(model, source)
        if value is not None and target not in result:
            result[target] = value
    return result


def approvals_reviewer_override_from_config(config: Any) -> Any:
    return _get(config, "approvals_reviewer")


def config_request_overrides_from_config(config: Any) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for key in (
        "model_reasoning_effort",
        "model_reasoning_summary",
        "model_verbosity",
        "personality",
        "web_search",
    ):
        _set_if_not_none(overrides, key, _get(config, key))
    if _get(config, "bypass_hook_trust", False):
        overrides["bypass_hook_trust"] = True
    return overrides


def service_tier_override_from_config(config: Any) -> Any:
    return _get(config, "model_service_tier", _get(config, "service_tier"))


def sandbox_mode_from_permission_profile(permission_profile: Any, cwd: str | Path | None = None) -> str:
    profile = _get(permission_profile, "kind", permission_profile)
    if isinstance(profile, str):
        normalized = profile.lower().replace("-", "_")
        if normalized in {"danger_full_access", "dangerously_full_access", "unrestricted"}:
            return "DangerFullAccess"
        if normalized in {"workspace_write", "workspacewrite"}:
            return "WorkspaceWrite"
        if normalized in {"read_only", "readonly"}:
            return "ReadOnly"
    writable_roots = _get(permission_profile, "writable_roots", _get(permission_profile, "write_roots", [])) or []
    cwd_string = _as_path_string(cwd)
    if _get(permission_profile, "workspace_write", False):
        return "WorkspaceWrite"
    if cwd_string and any(_as_path_string(root) == cwd_string for root in writable_roots):
        return "WorkspaceWrite"
    return "ReadOnly"


def permission_profile_id_from_active_profile(config: Any) -> Any:
    active = _get(config, "active_profile", _get(config, "profile"))
    return _get(active, "id", active)


def turn_permissions_overrides(config: Any, mode: ThreadParamsMode | str) -> TurnPermissionsOverride:
    thread_mode = ThreadParamsMode(mode)
    explicit = _get(config, "turn_permissions_override")
    if explicit is not None:
        return explicit
    if thread_mode is ThreadParamsMode.Embedded:
        profile_id = permission_profile_id_from_active_profile(config)
        if profile_id is not None:
            return TurnPermissionsOverride.ActiveProfile(profile_id)
    return TurnPermissionsOverride.Preserve()


def permissions_selection_from_config(config: Any, mode: ThreadParamsMode | str) -> Any:
    override = turn_permissions_overrides(config, mode)
    if override.kind == "Preserve":
        return None
    if override.kind == "ActiveProfile":
        return {"active_profile_id": override.value}
    if override.kind == "LegacySandbox":
        return {"sandbox": override.value}
    return override.value


def thread_cwd_from_config(config: Any, mode: ThreadParamsMode | str, remote_cwd_override: str | Path | None = None) -> str | None:
    thread_mode = ThreadParamsMode(mode)
    if thread_mode is ThreadParamsMode.Remote:
        return _as_path_string(remote_cwd_override)
    return _as_path_string(_get(config, "cwd"))


def _thread_lifecycle_params(
    config: Any,
    mode: ThreadParamsMode | str,
    remote_cwd_override: str | Path | None,
    *,
    thread_source: Any = None,
    thread_id: Any = None,
    source_thread_id: Any = None,
    base_instructions: str | None = None,
    developer_instructions: str | None = None,
) -> ThreadLifecycleParams:
    thread_mode = ThreadParamsMode(mode)
    cwd = thread_cwd_from_config(config, thread_mode, remote_cwd_override)
    profile = _get(config, "permission_profile", _get(config, "sandbox_policy", "read_only"))
    return ThreadLifecycleParams(
        cwd=cwd,
        model_provider=thread_mode.model_provider_from_config(config),
        sandbox=sandbox_mode_from_permission_profile(profile, cwd),
        permissions=permissions_selection_from_config(config, thread_mode),
        config_overrides=config_request_overrides_from_config(config),
        service_tier=service_tier_override_from_config(config),
        thread_source=thread_source,
        base_instructions=base_instructions,
        developer_instructions=developer_instructions,
        thread_id=thread_id,
        source_thread_id=source_thread_id,
    )


def thread_start_params_from_config(
    config: Any,
    mode: ThreadParamsMode | str,
    remote_cwd_override: str | Path | None = None,
    session_start_source: Any = None,
) -> ThreadLifecycleParams:
    return _thread_lifecycle_params(
        config,
        mode,
        remote_cwd_override,
        thread_source=session_start_source,
    )


def thread_resume_params_from_config(
    config: Any,
    thread_id: Any,
    mode: ThreadParamsMode | str,
    remote_cwd_override: str | Path | None = None,
) -> ThreadLifecycleParams:
    return _thread_lifecycle_params(
        config,
        mode,
        remote_cwd_override,
        thread_id=thread_id,
    )


def thread_fork_params_from_config(
    config: Any,
    source_thread_id: Any,
    mode: ThreadParamsMode | str,
    remote_cwd_override: str | Path | None = None,
    *,
    base_instructions: str | None = None,
    developer_instructions: str | None = None,
) -> ThreadLifecycleParams:
    return _thread_lifecycle_params(
        config,
        mode,
        remote_cwd_override,
        source_thread_id=source_thread_id,
        base_instructions=base_instructions,
        developer_instructions=developer_instructions,
    )


async def started_thread_from_start_response(response: Any) -> AppServerStartedThread:
    return AppServerStartedThread(session=_get(response, "session"), turns=list(_get(response, "turns", [])))


async def started_thread_from_resume_response(response: Any) -> AppServerStartedThread:
    return await started_thread_from_start_response(response)


async def started_thread_from_fork_response(response: Any) -> AppServerStartedThread:
    return await started_thread_from_start_response(response)


async def thread_session_state_from_thread_start_response(*args: Any, **kwargs: Any) -> Any:
    response = args[0] if args else kwargs.get("response")
    config = args[1] if len(args) > 1 else kwargs.get("config")
    return await thread_session_state_from_thread_response(_get(response, "thread", response), config=config)


async def thread_session_state_from_thread_resume_response(*args: Any, **kwargs: Any) -> Any:
    response = args[0] if args else kwargs.get("response")
    config = args[1] if len(args) > 1 else kwargs.get("config")
    return await thread_session_state_from_thread_response(_get(response, "thread", response), config=config)


async def thread_session_state_from_thread_fork_response(*args: Any, **kwargs: Any) -> Any:
    response = args[0] if args else kwargs.get("response")
    config = args[1] if len(args) > 1 else kwargs.get("config")
    return await thread_session_state_from_thread_response(_get(response, "thread", response), config=config)


def display_permission_profile_from_thread_response(*args: Any, **kwargs: Any) -> Any:
    sandbox = args[0] if args else kwargs.get("sandbox")
    cwd = args[1] if len(args) > 1 else kwargs.get("cwd")
    config = args[2] if len(args) > 2 else kwargs.get("config")
    mode = args[3] if len(args) > 3 else kwargs.get("mode", ThreadParamsMode.Embedded)
    if ThreadParamsMode(mode) is ThreadParamsMode.Embedded:
        configured = _get(config, "permission_profile", None)
        if configured is not None:
            return configured
    return sandbox_mode_from_permission_profile(sandbox, cwd)


async def thread_session_state_from_thread_response(*args: Any, **kwargs: Any) -> Any:
    thread = args[0] if args else kwargs.get("thread")
    config = kwargs.get("config", args[1] if len(args) > 1 else None)
    thread_id = _get(thread, "id", _get(thread, "thread_id"))
    cwd = _get(thread, "cwd", _get(config, "cwd"))
    permission_profile = display_permission_profile_from_thread_response(
        _get(thread, "sandbox", _get(config, "permission_profile", "read_only")),
        cwd,
        config,
        kwargs.get("mode", ThreadParamsMode.Remote),
    )
    message_history = _get(thread, "message_history")
    if message_history is None and config is not None:
        message_history = await _message_history_metadata_from_config(config)
    return {
        "thread_id": thread_id,
        "session_id": _get(thread, "session_id"),
        "forked_from_id": _get(thread, "forked_from_id"),
        "thread_name": _get(thread, "name"),
        "model": _get(thread, "model"),
        "model_provider": _get(thread, "model_provider"),
        "cwd": _as_path_string(cwd),
        "runtime_workspace_roots": list(_get(thread, "runtime_workspace_roots", [])),
        "instruction_source_paths": list(_get(thread, "instruction_sources", [])),
        "permission_profile": permission_profile,
        "message_history": message_history,
    }


async def _message_history_metadata_from_config(config: Any) -> dict[str, int] | None:
    codex_home = _get(config, "codex_home")
    if codex_home is None:
        return None
    try:
        from pycodex.config.types import History
        from pycodex.message_history import HistoryConfig, history_metadata

        history = _get(config, "history", None) or History()
        log_id, entry_count = await history_metadata(HistoryConfig.new(Path(codex_home), history))
    except Exception:
        return None
    return {"log_id": int(log_id), "entry_count": int(entry_count)}


def app_server_rate_limit_snapshots(*args: Any, **kwargs: Any) -> Any:
    response = args[0] if args else kwargs
    primary = _get(response, "primary", _get(response, "primary_snapshot"))
    secondary = _get(response, "secondary", _get(response, "secondary_snapshot"))
    return {"primary": primary, "secondary": secondary}


async def build_config(*args: Any, **kwargs: Any) -> Any:
    if args and isinstance(args[0], Mapping) and not kwargs:
        return dict(args[0])
    return dict(kwargs)


def rate_limit_snapshot(*args: Any, **kwargs: Any) -> Any:
    if args and isinstance(args[0], Mapping) and not kwargs:
        return dict(args[0])
    return dict(kwargs)


__all__ = [
    "AppServerBootstrap",
    "AppServerSession",
    "AppServerStartedThread",
    "JSONRPC_INVALID_REQUEST",
    "JSONRPC_METHOD_NOT_FOUND",
    "RUST_MODULE",
    "THREAD_SETTINGS_UPDATE_METHOD",
    "ThreadLifecycleParams",
    "ThreadParamsMode",
    "TurnPermissionsOverride",
    "app_server_rate_limit_snapshots",
    "approvals_reviewer_override_from_config",
    "bootstrap_request_error",
    "build_config",
    "config_request_overrides_from_config",
    "display_permission_profile_from_thread_response",
    "is_thread_settings_update_unsupported",
    "model_preset_from_api_model",
    "permission_profile_id_from_active_profile",
    "permissions_selection_from_config",
    "rate_limit_snapshot",
    "sandbox_mode_from_permission_profile",
    "service_tier_override_from_config",
    "start_thread_with_request_handle",
    "started_thread_from_fork_response",
    "started_thread_from_resume_response",
    "started_thread_from_start_response",
    "status_account_display_from_auth_mode",
    "thread_cwd_from_config",
    "thread_fork_params_from_config",
    "thread_realtime_start_params",
    "thread_resume_params_from_config",
    "thread_session_state_from_thread_fork_response",
    "thread_session_state_from_thread_response",
    "thread_session_state_from_thread_resume_response",
    "thread_session_state_from_thread_start_response",
    "thread_start_params_from_config",
    "turn_permissions_overrides",
]
