"""Config request processor ported from ``app-server/src/request_processors/config_processor.rs``."""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from pycodex.app_server.config_manager_service import ConfigManagerError
from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server_protocol import (
    ApprovalsReviewer,
    AskForApproval,
    ComputerUseRequirements,
    ConfigBatchWriteParams,
    ConfigReadParams,
    ConfigReadResponse,
    ConfigRequirements,
    ConfigRequirementsReadResponse,
    ConfigValueWriteParams,
    ConfigWriteErrorCode,
    ConfigWriteResponse,
    ConfiguredHookHandler,
    ConfiguredHookMatcherGroup,
    ExperimentalFeatureEnablementSetParams,
    ExperimentalFeatureEnablementSetResponse,
    JSONRPCErrorError,
    ManagedHooksRequirements,
    ModelProviderCapabilitiesReadResponse,
    NetworkDomainPermission,
    NetworkRequirements,
    NetworkUnixSocketPermission,
    ResidencyRequirement,
    SandboxMode,
)
from pycodex.protocol import WebSearchMode

JsonValue = Any

SUPPORTED_EXPERIMENTAL_FEATURE_ENABLEMENT = (
    "apps",
    "memories",
    "mentions_v2",
    "plugins",
    "remote_control",
    "remote_plugin",
    "tool_suggest",
    "tool_call_mcp_elicitation",
)

_SUPPORTED_SET = set(SUPPORTED_EXPERIMENTAL_FEATURE_ENABLEMENT)

_FEATURE_ALIASES = {
    "connectors": "apps",
    "collab": "multi_agent",
    "codex_hooks": "hooks",
    "memory_tool": "memories",
    "request_permissions": "exec_permission_approvals",
    "telepathy": "chronicle",
    "web_search": "web_search_request",
}

_KNOWN_CANONICAL_FEATURES = _SUPPORTED_SET | set(_FEATURE_ALIASES.values()) | {
    "apply_patch_freeform",
    "browser_use",
    "browser_use_external",
    "chronicle",
    "computer_use",
    "exec_permission_approvals",
    "hooks",
    "image_detail_original",
    "in_app_browser",
    "js_repl",
    "js_repl_tools_only",
    "multi_agent",
    "network_proxy",
    "remote_compaction_v2",
    "responses_websocket_response_processed",
    "standalone_web_search",
    "terminal_resize_reflow",
    "tool_search",
    "use_legacy_landlock",
    "use_linux_sandbox_bwrap",
}


class ConfigRequestProcessorError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


class ConfigRequestProcessor:
    """Python projection of Rust's config request processor.

    Runtime-heavy neighbors such as connector refresh, plugin telemetry metadata
    loading, and concrete thread managers stay injectable boundaries here.
    """

    def __init__(
        self,
        outgoing: Any,
        config_manager: Any,
        auth_manager: Any,
        thread_manager: Any,
        analytics_events_client: Any,
        *,
        model_provider_factory: Any | None = None,
        app_list_refresher: Any | None = None,
    ) -> None:
        self.outgoing = outgoing
        self.config_manager = config_manager
        self.auth_manager = auth_manager
        self.thread_manager = thread_manager
        self.analytics_events_client = analytics_events_client
        self.model_provider_factory = model_provider_factory
        self.app_list_refresher = app_list_refresher

    @classmethod
    def new(
        cls,
        outgoing: Any,
        config_manager: Any,
        auth_manager: Any,
        thread_manager: Any,
        analytics_events_client: Any,
    ) -> "ConfigRequestProcessor":
        return cls(outgoing, config_manager, auth_manager, thread_manager, analytics_events_client)

    async def read(self, params: ConfigReadParams | Mapping[str, JsonValue] | None = None) -> ConfigReadResponse:
        parsed = params if isinstance(params, ConfigReadParams) else ConfigReadParams.from_mapping(params)
        try:
            response = await _maybe_await(self.config_manager.read(parsed))
        except ConfigManagerError as exc:
            raise ConfigRequestProcessorError(map_error(exc)) from exc

        config = await self.load_latest_config(parsed.cwd)
        features = _ensure_response_features(response)
        for feature_key in SUPPORTED_EXPERIMENTAL_FEATURE_ENABLEMENT:
            features[feature_key] = _feature_enabled(config, feature_key)
        return response

    async def config_requirements_read(self) -> ConfigRequirementsReadResponse:
        try:
            requirements = await _maybe_await(self.config_manager.read_requirements())
        except ConfigManagerError as exc:
            raise ConfigRequestProcessorError(map_error(exc)) from exc
        return ConfigRequirementsReadResponse(
            requirements=None if requirements is None else map_requirements_toml_to_api(requirements)
        )

    async def value_write(
        self,
        params: ConfigValueWriteParams | Mapping[str, JsonValue],
    ) -> ConfigWriteResponse:
        parsed = params if isinstance(params, ConfigValueWriteParams) else ConfigValueWriteParams.from_mapping(params)
        response = await self.write_value(parsed)
        await self.handle_config_mutation()
        return response

    async def batch_write(
        self,
        params: ConfigBatchWriteParams | Mapping[str, JsonValue],
    ) -> ConfigWriteResponse:
        parsed = params if isinstance(params, ConfigBatchWriteParams) else ConfigBatchWriteParams.from_mapping(params)
        response = await self.batch_write_inner(parsed)
        await self.handle_config_mutation()
        return response

    async def experimental_feature_enablement_set(
        self,
        request_id: Any,
        params: ExperimentalFeatureEnablementSetParams | Mapping[str, JsonValue],
    ) -> None:
        parsed = (
            params
            if isinstance(params, ExperimentalFeatureEnablementSetParams)
            else ExperimentalFeatureEnablementSetParams.from_mapping(params)
        )
        should_refresh_apps_list = parsed.enablement.get("apps") is True
        response = await self.set_experimental_feature_enablement(parsed)
        await self.handle_config_mutation()
        await _call_optional(self.outgoing, "send_response_as", request_id, response)
        if should_refresh_apps_list:
            await self.refresh_apps_list_after_experimental_feature_enablement_set()
        return None

    async def model_provider_capabilities_read(self) -> ModelProviderCapabilitiesReadResponse:
        config = await self.load_latest_config(None)
        provider = None
        if self.model_provider_factory is not None:
            provider = await _maybe_await(self.model_provider_factory(_get(config, "model_provider")))
        else:
            provider = _get(config, "model_provider")
        capabilities = _call_or_get(provider, "capabilities") if provider is not None else {}
        return ModelProviderCapabilitiesReadResponse(
            namespace_tools=bool(_get(capabilities, "namespace_tools", False)),
            image_generation=bool(_get(capabilities, "image_generation", False)),
            web_search=bool(_get(capabilities, "web_search", False)),
        )

    async def handle_config_mutation(self) -> None:
        await _clear_manager_cache(_call_or_get(self.thread_manager, "plugins_manager"))
        await _clear_manager_cache(_call_or_get(self.thread_manager, "skills_manager"))

    async def refresh_apps_list_after_experimental_feature_enablement_set(self) -> None:
        try:
            config = await self.load_latest_config(None)
        except ConfigRequestProcessorError:
            return
        auth = await _maybe_await(_call_or_get(self.auth_manager, "auth"))
        if not _apps_enabled_for_auth(config, auth):
            return
        if self.app_list_refresher is not None:
            await _maybe_await(self.app_list_refresher(config, auth, self.thread_manager, self.outgoing))
        else:
            await _call_optional(self.outgoing, "send_server_notification", {"method": "appListUpdated"})

    async def load_latest_config(self, fallback_cwd: str | Path | None) -> Any:
        try:
            return await _maybe_await(self.config_manager.load_latest_config(fallback_cwd))
        except Exception as exc:  # Rust maps all config-load failures to this fixed message.
            raise ConfigRequestProcessorError(
                internal_error(f"failed to resolve feature override precedence: {exc}")
            ) from exc

    async def write_value(self, params: ConfigValueWriteParams) -> ConfigWriteResponse:
        pending_changes = collect_plugin_enabled_candidates(((params.key_path, params.value),))
        try:
            response = await _maybe_await(self.config_manager.write_value(params))
        except ConfigManagerError as exc:
            raise ConfigRequestProcessorError(map_error(exc)) from exc
        await self.emit_plugin_toggle_events(pending_changes)
        return response

    async def batch_write_inner(self, params: ConfigBatchWriteParams) -> ConfigWriteResponse:
        pending_changes = collect_plugin_enabled_candidates((edit.key_path, edit.value) for edit in params.edits)
        try:
            response = await _maybe_await(self.config_manager.batch_write(params))
        except ConfigManagerError as exc:
            raise ConfigRequestProcessorError(map_error(exc)) from exc
        await self.emit_plugin_toggle_events(pending_changes)
        if params.reload_user_config:
            await self.reload_user_config()
        return response

    async def set_experimental_feature_enablement(
        self,
        params: ExperimentalFeatureEnablementSetParams | Mapping[str, JsonValue],
    ) -> ExperimentalFeatureEnablementSetResponse:
        parsed = (
            params
            if isinstance(params, ExperimentalFeatureEnablementSetParams)
            else ExperimentalFeatureEnablementSetParams.from_mapping(params)
        )
        enablement = dict(parsed.enablement)
        for key in enablement:
            if canonical_feature_for_key(key):
                if key in _SUPPORTED_SET:
                    continue
                raise ConfigRequestProcessorError(
                    invalid_request(
                        f"unsupported feature enablement `{key}`: currently supported features are "
                        f"{', '.join(SUPPORTED_EXPERIMENTAL_FEATURE_ENABLEMENT)}"
                    )
                )
            canonical = feature_for_key(key)
            if canonical is not None:
                raise ConfigRequestProcessorError(
                    invalid_request(f"invalid feature enablement `{key}`: use canonical feature key `{canonical}`")
                )
            raise ConfigRequestProcessorError(invalid_request(f"invalid feature enablement `{key}`"))

        if not enablement:
            return ExperimentalFeatureEnablementSetResponse(enablement={})

        try:
            await _maybe_await(self.config_manager.extend_runtime_feature_enablement(enablement.items()))
        except Exception as exc:
            raise ConfigRequestProcessorError(internal_error("failed to update feature enablement")) from exc
        await self.load_latest_config(None)
        await self.reload_user_config()
        return ExperimentalFeatureEnablementSetResponse(enablement=enablement)

    async def reload_user_config(self) -> None:
        try:
            next_config = await self.load_latest_config(None)
        except ConfigRequestProcessorError:
            return
        thread_ids = await _maybe_await(_call_or_get(self.thread_manager, "list_thread_ids")) or ()
        for thread_id in thread_ids:
            try:
                thread = await _maybe_await(self.thread_manager.get_thread(thread_id))
            except Exception:
                continue
            await _call_optional(thread, "refresh_runtime_config", next_config)

    async def emit_plugin_toggle_events(self, pending_changes: Mapping[str, bool]) -> None:
        for plugin_id, enabled in pending_changes.items():
            if not _valid_plugin_id(plugin_id):
                continue
            method = "track_plugin_enabled" if enabled else "track_plugin_disabled"
            await _call_optional(self.analytics_events_client, method, {"plugin_id": plugin_id})


def map_requirements_toml_to_api(requirements: Any) -> ConfigRequirements:
    web_search_modes = _map_optional_sequence(_get(requirements, "allowed_web_search_modes"), WebSearchMode.parse)
    if web_search_modes is not None and WebSearchMode.DISABLED not in web_search_modes:
        web_search_modes = (*web_search_modes, WebSearchMode.DISABLED)

    return ConfigRequirements(
        allowed_approval_policies=_map_optional_sequence(
            _get(requirements, "allowed_approval_policies"),
            AskForApproval.from_mapping,
        ),
        allowed_approvals_reviewers=_map_optional_sequence(
            _get(requirements, "allowed_approvals_reviewers"),
            ApprovalsReviewer.parse,
        ),
        allowed_sandbox_modes=tuple(
            item
            for item in (
                map_sandbox_mode_requirement_to_api(mode)
                for mode in _optional_iter(_get(requirements, "allowed_sandbox_modes"))
            )
            if item is not None
        )
        or None,
        allowed_permissions=_tuple_or_none(_get(requirements, "allowed_permissions")),
        allowed_web_search_modes=web_search_modes,
        allow_managed_hooks_only=_get(requirements, "allow_managed_hooks_only"),
        allow_appshots=_get(requirements, "allow_appshots"),
        computer_use=(
            map_computer_use_requirements_to_api(_get(requirements, "computer_use"))
            if _get(requirements, "computer_use") is not None
            else None
        ),
        feature_requirements=_feature_requirements_entries(_get(requirements, "feature_requirements")),
        hooks=map_hooks_requirements_to_api(_get(requirements, "hooks")) if _get(requirements, "hooks") is not None else None,
        enforce_residency=(
            map_residency_requirement_to_api(_get(requirements, "enforce_residency"))
            if _get(requirements, "enforce_residency") is not None
            else None
        ),
        network=(
            map_network_requirements_to_api(_get(requirements, "network"))
            if _get(requirements, "network") is not None
            else None
        ),
    )


def map_computer_use_requirements_to_api(computer_use: Any) -> ComputerUseRequirements:
    return ComputerUseRequirements(allow_locked_computer_use=_get(computer_use, "allow_locked_computer_use"))


def map_hooks_requirements_to_api(hooks: Any) -> ManagedHooksRequirements:
    hook_events = _get(hooks, "hooks", hooks)
    return ManagedHooksRequirements(
        managed_dir=_get(hooks, "managed_dir"),
        windows_managed_dir=_get(hooks, "windows_managed_dir"),
        pre_tool_use=map_hook_matcher_groups_to_api(_get(hook_events, "pre_tool_use", ())),
        permission_request=map_hook_matcher_groups_to_api(_get(hook_events, "permission_request", ())),
        post_tool_use=map_hook_matcher_groups_to_api(_get(hook_events, "post_tool_use", ())),
        pre_compact=map_hook_matcher_groups_to_api(_get(hook_events, "pre_compact", ())),
        post_compact=map_hook_matcher_groups_to_api(_get(hook_events, "post_compact", ())),
        session_start=map_hook_matcher_groups_to_api(_get(hook_events, "session_start", ())),
        user_prompt_submit=map_hook_matcher_groups_to_api(_get(hook_events, "user_prompt_submit", ())),
        subagent_start=map_hook_matcher_groups_to_api(_get(hook_events, "subagent_start", ())),
        subagent_stop=map_hook_matcher_groups_to_api(_get(hook_events, "subagent_stop", ())),
        stop=map_hook_matcher_groups_to_api(_get(hook_events, "stop", ())),
    )


def map_hook_matcher_groups_to_api(groups: Iterable[Any]) -> tuple[ConfiguredHookMatcherGroup, ...]:
    return tuple(map_hook_matcher_group_to_api(group) for group in groups)


def map_hook_matcher_group_to_api(group: Any) -> ConfiguredHookMatcherGroup:
    return ConfiguredHookMatcherGroup(
        matcher=_get(group, "matcher"),
        hooks=tuple(map_hook_handler_to_api(handler) for handler in _get(group, "hooks", ())),
    )


def map_hook_handler_to_api(handler: Any) -> ConfiguredHookHandler:
    kind = str(_get(handler, "type", _get(handler, "variant", _get(handler, "kind", "command")))).lower()
    if kind in {"prompt", "corehookhandlerconfig::prompt"}:
        return ConfiguredHookHandler(type="prompt")
    if kind in {"agent", "corehookhandlerconfig::agent"}:
        return ConfiguredHookHandler(type="agent")
    return ConfiguredHookHandler(
        type="command",
        command=_get(handler, "command"),
        command_windows=_get(handler, "command_windows"),
        timeout_sec=_get(handler, "timeout_sec"),
        async_=bool(_get(handler, "async", _get(handler, "async_", False))),
        status_message=_get(handler, "status_message"),
    )


def map_sandbox_mode_requirement_to_api(mode: Any) -> SandboxMode | None:
    raw = _enum_value(mode)
    normalized = raw.replace("_", "-").lower()
    if normalized in {"read-only", "readonly"}:
        return SandboxMode.READ_ONLY
    if normalized in {"workspace-write", "workspacewrite"}:
        return SandboxMode.WORKSPACE_WRITE
    if normalized in {"danger-full-access", "dangerfullaccess"}:
        return SandboxMode.DANGER_FULL_ACCESS
    if normalized in {"external-sandbox", "externalsandbox"}:
        return None
    return SandboxMode.parse(raw)


def map_residency_requirement_to_api(residency: Any) -> ResidencyRequirement:
    raw = _enum_value(residency).lower()
    if raw == "us":
        return ResidencyRequirement.US
    return ResidencyRequirement.parse(raw)


def map_network_requirements_to_api(network: Any) -> NetworkRequirements:
    domains = _get(network, "domains")
    unix_sockets = _get(network, "unix_sockets")
    domain_entries = _entries(domains)
    socket_entries = _entries(unix_sockets)
    return NetworkRequirements(
        enabled=_get(network, "enabled"),
        http_port=_get(network, "http_port"),
        socks_port=_get(network, "socks_port"),
        allow_upstream_proxy=_get(network, "allow_upstream_proxy"),
        dangerously_allow_non_loopback_proxy=_get(network, "dangerously_allow_non_loopback_proxy"),
        dangerously_allow_all_unix_sockets=_get(network, "dangerously_allow_all_unix_sockets"),
        domains={key: map_network_domain_permission_to_api(value) for key, value in domain_entries.items()} or None,
        managed_allowed_domains_only=_get(network, "managed_allowed_domains_only"),
        allowed_domains=_tuple_or_none(_get(network, "allowed_domains")) or _domains_with_permission(domain_entries, "allow"),
        denied_domains=_tuple_or_none(_get(network, "denied_domains")) or _domains_with_permission(domain_entries, "deny"),
        unix_sockets={
            key: map_network_unix_socket_permission_to_api(value) for key, value in socket_entries.items()
        }
        or None,
        allow_unix_sockets=_tuple_or_none(_get(network, "allow_unix_sockets"))
        or _sockets_with_permission(socket_entries, "allow"),
        allow_local_binding=_get(network, "allow_local_binding"),
    )


def map_network_domain_permission_to_api(permission: Any) -> NetworkDomainPermission:
    return NetworkDomainPermission.parse(_enum_value(permission).lower())


def map_network_unix_socket_permission_to_api(permission: Any) -> NetworkUnixSocketPermission:
    return NetworkUnixSocketPermission.parse(_enum_value(permission).lower())


def map_error(err: ConfigManagerError) -> JSONRPCErrorError:
    code = err.write_error_code() if hasattr(err, "write_error_code") else getattr(err, "code", None)
    if code is not None:
        return config_write_error(code, str(err))
    return internal_error(str(err))


def config_write_error(code: ConfigWriteErrorCode | str, message: str) -> JSONRPCErrorError:
    parsed = ConfigWriteErrorCode.parse(code)
    return replace(invalid_request(message), data={"config_write_error_code": parsed.value})


def collect_plugin_enabled_candidates(edits: Iterable[tuple[str, JsonValue]]) -> dict[str, bool]:
    changes: dict[str, bool] = {}
    for key_path, value in edits:
        if not isinstance(value, bool):
            continue
        parts = str(key_path).split(".")
        if len(parts) == 3 and parts[0] == "plugins" and parts[2] == "enabled":
            changes[parts[1]] = value
    return dict(sorted(changes.items()))


def canonical_feature_for_key(key: str) -> str | None:
    return key if key in _KNOWN_CANONICAL_FEATURES else None


def feature_for_key(key: str) -> str | None:
    return canonical_feature_for_key(key) or _FEATURE_ALIASES.get(key)


def _ensure_response_features(response: ConfigReadResponse) -> dict[str, JsonValue]:
    features = response.config.additional.get("features")
    if not isinstance(features, dict):
        features = {}
        response.config.additional["features"] = features
    return features


def _feature_enabled(config: Any, feature_key: str) -> bool:
    features = _get(config, "features")
    if features is None:
        return False
    enabled = _call_or_get(features, "enabled", feature_key)
    if enabled is not None:
        return bool(enabled)
    if isinstance(features, Mapping):
        return bool(features.get(feature_key, False))
    return bool(_get(features, feature_key, False))


def _apps_enabled_for_auth(config: Any, auth: Any) -> bool:
    features = _get(config, "features")
    if features is None:
        return False
    uses_backend = bool(_call_or_get(auth, "uses_codex_backend")) if auth is not None else False
    result = _call_or_get(features, "apps_enabled_for_auth", uses_backend)
    if result is not None:
        return bool(result)
    return _feature_enabled(config, "apps")


async def _clear_manager_cache(manager: Any) -> None:
    if manager is not None:
        await _call_optional(manager, "clear_cache")


async def _call_optional(target: Any, method: str, *args: Any) -> Any:
    if target is None:
        return None
    func = getattr(target, method, None)
    if func is None:
        return None
    return await _maybe_await(func(*args))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _call_or_get(target: Any, name: str, *args: Any) -> Any:
    if target is None:
        return None
    value = target.get(name) if isinstance(target, Mapping) else getattr(target, name, None)
    if callable(value):
        return value(*args)
    return value


def _get(target: Any, name: str, default: Any = None) -> Any:
    if target is None:
        return default
    if isinstance(target, Mapping):
        if name in target:
            return target[name]
        camel = _snake_to_camel(name)
        return target.get(camel, default)
    return getattr(target, name, default)


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    if isinstance(raw, str):
        return raw
    return str(raw)


def _optional_iter(value: Any) -> Iterable[Any]:
    return () if value is None else value


def _map_optional_sequence(value: Any, mapper: Any) -> tuple[Any, ...] | None:
    if value is None:
        return None
    return tuple(mapper(item) for item in value)


def _tuple_or_none(value: Any) -> tuple[Any, ...] | None:
    if value is None:
        return None
    result = tuple(value)
    return result or None


def _feature_requirements_entries(value: Any) -> dict[str, bool] | None:
    if value is None:
        return None
    entries = _entries(value)
    return {str(key): bool(item) for key, item in entries.items()} or None


def _entries(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    entries = _get(value, "entries")
    if isinstance(entries, Mapping):
        return dict(entries)
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _domains_with_permission(entries: Mapping[str, Any], permission: str) -> tuple[str, ...] | None:
    result = tuple(key for key, value in entries.items() if _enum_value(value).lower() == permission)
    return result or None


def _sockets_with_permission(entries: Mapping[str, Any], permission: str) -> tuple[str, ...] | None:
    result = tuple(key for key, value in entries.items() if _enum_value(value).lower() == permission)
    return result or None


def _valid_plugin_id(value: str) -> bool:
    return bool(value) and all(part for part in value.replace("@", "/").split("/"))


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


__all__ = [
    "SUPPORTED_EXPERIMENTAL_FEATURE_ENABLEMENT",
    "ConfigRequestProcessor",
    "ConfigRequestProcessorError",
    "canonical_feature_for_key",
    "collect_plugin_enabled_candidates",
    "config_write_error",
    "feature_for_key",
    "map_computer_use_requirements_to_api",
    "map_error",
    "map_hook_handler_to_api",
    "map_hook_matcher_group_to_api",
    "map_hook_matcher_groups_to_api",
    "map_hooks_requirements_to_api",
    "map_network_domain_permission_to_api",
    "map_network_requirements_to_api",
    "map_network_unix_socket_permission_to_api",
    "map_requirements_toml_to_api",
    "map_residency_requirement_to_api",
    "map_sandbox_mode_requirement_to_api",
]
