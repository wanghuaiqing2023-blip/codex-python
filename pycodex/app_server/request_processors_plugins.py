"""Plugin request processor projection.

Ported from ``codex-app-server/src/request_processors/plugins.rs``.
The Rust module owns both local plugin summary conversion and a large set of
remote marketplace/share/install RPCs. This Python module mirrors the local
module-scoped data conversion, share-target validation, facade methods, and
cache-refresh boundaries while keeping concrete remote/plugin runtime work
behind injectable callables.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server_protocol import (
    JSONRPCErrorError,
    PluginAuthPolicy,
    PluginAvailability,
    PluginInstallPolicy,
    PluginInterface,
    PluginShareContext,
    PluginShareDiscoverability,
    PluginSharePrincipal,
    PluginSharePrincipalRole,
    PluginSharePrincipalType,
    PluginShareTarget,
    PluginShareTargetRole,
    PluginShareUpdateDiscoverability,
    PluginSource,
    PluginSummary,
    SkillInterface,
    SkillSummary,
)

JsonValue = Any


class PluginRequestProcessorError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class RemotePluginShareTarget:
    principal_type: PluginSharePrincipalType
    principal_id: str
    role: PluginShareTargetRole


class PluginRequestProcessor:
    def __init__(
        self,
        auth_manager: Any,
        thread_manager: Any,
        outgoing: Any,
        analytics_events_client: Any,
        config_manager: Any,
        workspace_settings_cache: Any,
        *,
        response_handlers: Mapping[str, Any] | None = None,
    ) -> None:
        self.auth_manager = auth_manager
        self.thread_manager = thread_manager
        self.outgoing = outgoing
        self.analytics_events_client = analytics_events_client
        self.config_manager = config_manager
        self.workspace_settings_cache = workspace_settings_cache
        self.response_handlers = dict(response_handlers or {})

    @classmethod
    def new(
        cls,
        auth_manager: Any,
        thread_manager: Any,
        outgoing: Any,
        analytics_events_client: Any,
        config_manager: Any,
        workspace_settings_cache: Any,
        **kwargs: Any,
    ) -> "PluginRequestProcessor":
        return cls(
            auth_manager,
            thread_manager,
            outgoing,
            analytics_events_client,
            config_manager,
            workspace_settings_cache,
            **kwargs,
        )

    async def plugin_list(self, params: Any) -> Any:
        return await self.plugin_list_response(params)

    async def plugin_installed(self, params: Any) -> Any:
        return await self.plugin_installed_response(params)

    async def plugin_read(self, params: Any) -> Any:
        return await self.plugin_read_response(params)

    async def plugin_skill_read(self, params: Any) -> Any:
        return await self.plugin_skill_read_response(params)

    async def plugin_share_save(self, params: Any) -> Any:
        return await self.plugin_share_save_response(params)

    async def plugin_share_update_targets(self, params: Any) -> Any:
        return await self.plugin_share_update_targets_response(params)

    async def plugin_share_list(self, params: Any) -> Any:
        return await self.plugin_share_list_response(params)

    async def plugin_share_checkout(self, params: Any) -> Any:
        return await self.plugin_share_checkout_response(params)

    async def plugin_share_delete(self, params: Any) -> Any:
        return await self.plugin_share_delete_response(params)

    async def plugin_install(self, params: Any) -> Any:
        return await self.plugin_install_response(params)

    async def plugin_uninstall(self, params: Any) -> Any:
        return await self.plugin_uninstall_response(params)

    def effective_plugins_changed_callback(self) -> Any:
        def callback() -> None:
            self.on_effective_plugins_changed()

        return callback

    def on_effective_plugins_changed(self) -> None:
        self.spawn_effective_plugins_changed_task(self.thread_manager, self.config_manager)

    @staticmethod
    def spawn_effective_plugins_changed_task(thread_manager: Any, config_manager: Any) -> None:
        plugins_manager = _call(thread_manager, "plugins_manager")
        skills_manager = _call(thread_manager, "skills_manager")
        _call(plugins_manager, "clear_cache")
        _call(skills_manager, "clear_cache")
        refresh = _field(config_manager, "queue_best_effort_refresh", None)
        if callable(refresh):
            refresh(thread_manager, config_manager)

    def clear_plugin_related_caches(self) -> None:
        _call(_call(self.thread_manager, "plugins_manager"), "clear_cache")
        _call(_call(self.thread_manager, "skills_manager"), "clear_cache")

    async def load_latest_config(self, fallback_cwd: str | Path | None = None) -> Any:
        try:
            if fallback_cwd is None:
                return await _maybe_await(_call(self.config_manager, "load_latest_config"))
            return await _maybe_await(_call(self.config_manager, "load_latest_config", fallback_cwd))
        except Exception as exc:
            raise PluginRequestProcessorError(internal_error(f"failed to reload config: {exc}")) from exc

    async def workspace_codex_plugins_enabled(self, config: Any, auth: Any | None = None) -> bool:
        checker = _field(self.workspace_settings_cache, "codex_plugins_enabled_for_workspace", None)
        if callable(checker):
            try:
                return bool(await _maybe_await(checker(config, auth, self.workspace_settings_cache)))
            except Exception:
                return True
        return True

    async def plugin_list_response(self, params: Any) -> Any:
        return await self._response("plugin_list_response", params)

    async def plugin_installed_response(self, params: Any) -> Any:
        return await self._response("plugin_installed_response", params)

    async def plugin_read_response(self, params: Any) -> Any:
        return await self._response("plugin_read_response", params)

    async def plugin_skill_read_response(self, params: Any) -> Any:
        return await self._response("plugin_skill_read_response", params)

    async def plugin_share_save_response(self, params: Any) -> Any:
        validate_client_plugin_share_targets(_field(params, "share_targets", None) or ())
        return await self._response("plugin_share_save_response", params)

    async def plugin_share_update_targets_response(self, params: Any) -> Any:
        validate_client_plugin_share_targets(_field(params, "share_targets", None) or ())
        return await self._response("plugin_share_update_targets_response", params)

    async def plugin_share_list_response(self, params: Any) -> Any:
        return await self._response("plugin_share_list_response", params)

    async def plugin_share_checkout_response(self, params: Any) -> Any:
        return await self._response("plugin_share_checkout_response", params)

    async def plugin_share_delete_response(self, params: Any) -> Any:
        return await self._response("plugin_share_delete_response", params)

    async def plugin_install_response(self, params: Any) -> Any:
        return await self._response("plugin_install_response", params)

    async def plugin_uninstall_response(self, params: Any) -> Any:
        return await self._response("plugin_uninstall_response", params)

    async def _response(self, name: str, params: Any) -> Any:
        handler = self.response_handlers.get(name)
        if handler is None:
            raise PluginRequestProcessorError(internal_error(f"{name} runtime is not configured"))
        return await _maybe_await(handler(params))


def plugin_skills_to_info(
    skills: Sequence[Any],
    disabled_skill_paths: set[str | Path],
) -> tuple[SkillSummary, ...]:
    disabled = {str(path) for path in disabled_skill_paths}
    summaries: list[SkillSummary] = []
    for skill in skills:
        path = _field(skill, "path_to_skills_md", _field(skill, "path", None))
        summaries.append(
            SkillSummary(
                name=_field(skill, "name"),
                description=_field(skill, "description"),
                short_description=_field(skill, "short_description", None),
                interface=_skill_interface_to_info(_field(skill, "interface", None)),
                path=path,
                enabled=str(path) not in disabled,
            )
        )
    return tuple(summaries)


def local_plugin_interface_to_info(interface: Any) -> PluginInterface:
    return PluginInterface(
        display_name=_field(interface, "display_name", None),
        short_description=_field(interface, "short_description", None),
        long_description=_field(interface, "long_description", None),
        developer_name=_field(interface, "developer_name", None),
        category=_field(interface, "category", None),
        capabilities=tuple(_field(interface, "capabilities", ()) or ()),
        website_url=_field(interface, "website_url", None),
        privacy_policy_url=_field(interface, "privacy_policy_url", None),
        terms_of_service_url=_field(interface, "terms_of_service_url", None),
        default_prompt=_field(interface, "default_prompt", None),
        brand_color=_field(interface, "brand_color", None),
        composer_icon=_field(interface, "composer_icon", None),
        composer_icon_url=None,
        logo=_field(interface, "logo", None),
        logo_url=None,
        screenshots=tuple(_field(interface, "screenshots", ()) or ()),
        screenshot_urls=(),
    )


def marketplace_plugin_source_to_info(source: Any) -> PluginSource:
    type_value = _source_type(source)
    if type_value == "local":
        return PluginSource.local(_field(source, "path"))
    if type_value == "git":
        return PluginSource.git(
            url=_field(source, "url"),
            path=_field(source, "path", None),
            ref_name=_field(source, "ref_name", None),
            sha=_field(source, "sha", None),
        )
    raise ValueError(f"unsupported marketplace plugin source: {type_value!r}")


def share_context_for_source(
    source: Any,
    shared_plugin_ids_by_local_path: Mapping[str | Path, str],
) -> PluginShareContext | None:
    if _source_type(source) != "local":
        return None
    lookup = {str(path): remote_id for path, remote_id in shared_plugin_ids_by_local_path.items()}
    remote_plugin_id = lookup.get(str(_field(source, "path")))
    if remote_plugin_id is None:
        return None
    return PluginShareContext(
        remote_plugin_id=remote_plugin_id,
        remote_version=None,
        discoverability=None,
        share_url=None,
        creator_account_user_id=None,
        creator_name=None,
        share_principals=None,
    )


def convert_configured_marketplace_plugin_to_plugin_summary(
    plugin: Any,
    shared_plugin_ids_by_local_path: Mapping[str | Path, str],
) -> PluginSummary:
    policy = _field(plugin, "policy", {})
    source = _field(plugin, "source")
    return PluginSummary(
        id=_field(plugin, "id"),
        remote_plugin_id=None,
        local_version=_field(plugin, "local_version", None),
        installed=bool(_field(plugin, "installed")),
        enabled=bool(_field(plugin, "enabled")),
        name=_field(plugin, "name"),
        share_context=share_context_for_source(source, shared_plugin_ids_by_local_path),
        source=marketplace_plugin_source_to_info(source),
        install_policy=_enum_value(_field(policy, "installation", PluginInstallPolicy.AVAILABLE)),
        auth_policy=_enum_value(_field(policy, "authentication", PluginAuthPolicy.ON_USE)),
        availability=PluginAvailability.AVAILABLE,
        interface=(
            local_plugin_interface_to_info(_field(plugin, "interface"))
            if _field(plugin, "interface", None) is not None
            else None
        ),
        keywords=tuple(_field(plugin, "keywords", ()) or ()),
    )


def remote_installed_plugin_visible_scopes(config: Any) -> tuple[str, ...]:
    scopes: list[str] = []
    if _feature_enabled(config, "RemotePlugin"):
        scopes.append("global")
    if _feature_enabled(config, "PluginSharing"):
        scopes.append("workspace")
    return tuple(scopes)


def remote_plugin_share_discoverability(discoverability: PluginShareDiscoverability | str) -> str:
    return PluginShareDiscoverability.parse(discoverability).value


def remote_plugin_share_update_discoverability(
    discoverability: PluginShareUpdateDiscoverability | str,
) -> str:
    return PluginShareUpdateDiscoverability.parse(discoverability).value


def validate_client_plugin_share_targets(targets: Sequence[PluginShareTarget | Mapping[str, JsonValue]]) -> None:
    for target in targets:
        principal_type = PluginSharePrincipalType.parse(_field(target, "principal_type"))
        if principal_type == PluginSharePrincipalType.WORKSPACE:
            raise PluginRequestProcessorError(
                invalid_request(
                    "shareTargets cannot include workspace principals; use discoverability UNLISTED for workspace link access"
                )
            )


def remote_plugin_share_target_role(role: PluginShareTargetRole | str) -> PluginShareTargetRole:
    return PluginShareTargetRole.parse(role)


def plugin_share_principal_role_from_remote(role: PluginSharePrincipalRole | str) -> PluginSharePrincipalRole:
    return PluginSharePrincipalRole.parse(role)


def remote_plugin_share_targets(
    targets: Sequence[PluginShareTarget | Mapping[str, JsonValue]],
) -> tuple[RemotePluginShareTarget, ...]:
    return tuple(
        RemotePluginShareTarget(
            principal_type=PluginSharePrincipalType.parse(_field(target, "principal_type")),
            principal_id=str(_field(target, "principal_id")),
            role=remote_plugin_share_target_role(_field(target, "role")),
        )
        for target in targets
    )


def plugin_share_principal_from_remote(principal: Any) -> PluginSharePrincipal:
    return PluginSharePrincipal(
        principal_type=PluginSharePrincipalType.parse(_field(principal, "principal_type")),
        principal_id=_field(principal, "principal_id"),
        role=plugin_share_principal_role_from_remote(_field(principal, "role")),
        name=_field(principal, "name", None),
    )


def _skill_interface_to_info(interface: Any | None) -> SkillInterface | None:
    if interface is None:
        return None
    return SkillInterface(
        display_name=_field(interface, "display_name", None),
        short_description=_field(interface, "short_description", None),
        icon_small=_field(interface, "icon_small", None),
        icon_large=_field(interface, "icon_large", None),
        brand_color=_field(interface, "brand_color", None),
        default_prompt=_field(interface, "default_prompt", None),
    )


def _feature_enabled(config: Any, name: str) -> bool:
    features = _field(config, "features", {})
    enabled = _field(features, "enabled", None)
    if callable(enabled):
        return bool(enabled(name))
    if isinstance(features, Mapping):
        return bool(features.get(name, features.get(name.lower(), False)))
    return False


def _source_type(source: Any) -> str:
    return str(_field(source, "type", _field(source, "kind", ""))).lower()


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        camel = _snake_to_camel(name)
        if camel in value:
            return value[camel]
        return default
    return getattr(value, name, default)


def _call(value: Any, name: str, *args: Any) -> Any:
    member = _field(value, name, None)
    if not callable(member):
        return member
    return member(*args)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


__all__ = [
    "PluginRequestProcessor",
    "PluginRequestProcessorError",
    "RemotePluginShareTarget",
    "convert_configured_marketplace_plugin_to_plugin_summary",
    "local_plugin_interface_to_info",
    "marketplace_plugin_source_to_info",
    "plugin_share_principal_from_remote",
    "plugin_share_principal_role_from_remote",
    "plugin_skills_to_info",
    "remote_installed_plugin_visible_scopes",
    "remote_plugin_share_discoverability",
    "remote_plugin_share_target_role",
    "remote_plugin_share_targets",
    "remote_plugin_share_update_discoverability",
    "share_context_for_source",
    "validate_client_plugin_share_targets",
]
