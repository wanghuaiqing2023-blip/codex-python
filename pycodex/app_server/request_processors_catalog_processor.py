"""Catalog request processor projection.

Ported from ``codex-app-server/src/request_processors/catalog_processor.rs``.
The Rust module owns catalog-style request processing: list pagination, model
and collaboration-mode listing, experimental feature and permission-profile
projection, plus lightweight skill/hook metadata mapping. Runtime plugin,
skill discovery, hook loading, and config writing stay injected at this module
boundary.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_params, invalid_request
from pycodex.app_server_protocol import (
    CollaborationModeListParams,
    CollaborationModeListResponse,
    ExperimentalFeature,
    ExperimentalFeatureListParams,
    ExperimentalFeatureListResponse,
    ExperimentalFeatureStage,
    HookErrorInfo,
    HookMetadata,
    HooksListParams,
    HooksListResponse,
    JSONRPCErrorError,
    ModelListParams,
    ModelListResponse,
    MockExperimentalMethodParams,
    MockExperimentalMethodResponse,
    PermissionProfileListParams,
    PermissionProfileListResponse,
    PermissionProfileSummary,
    SkillDependencies,
    SkillErrorInfo,
    SkillInterface,
    SkillMetadata,
    SkillToolDependency,
    SkillsConfigWriteParams,
    SkillsConfigWriteResponse,
    SkillsListParams,
    SkillsListResponse,
)

JsonValue = Any

SKILLS_LIST_CWD_CONCURRENCY = 5
BUILT_IN_PERMISSION_PROFILES = (
    PermissionProfileSummary(id="read-only"),
    PermissionProfileSummary(id="workspace"),
    PermissionProfileSummary(id="danger-full-access"),
)
PLUGIN_FEATURE_NAMES = frozenset({"apps", "plugins"})


class CatalogRequestProcessorError(Exception):
    def __init__(self, error: JSONRPCErrorError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class ConfigEdit:
    kind: str
    key: str
    enabled: bool


class CatalogRequestProcessor:
    def __init__(
        self,
        auth_manager: Any,
        thread_manager: Any,
        config: Any,
        config_manager: Any,
        workspace_settings_cache: Any,
    ) -> None:
        self.auth_manager = auth_manager
        self.thread_manager = thread_manager
        self.config = config
        self.config_manager = config_manager
        self.workspace_settings_cache = workspace_settings_cache

    @classmethod
    def new(
        cls,
        auth_manager: Any,
        thread_manager: Any,
        config: Any,
        config_manager: Any,
        workspace_settings_cache: Any,
    ) -> "CatalogRequestProcessor":
        return cls(auth_manager, thread_manager, config, config_manager, workspace_settings_cache)

    async def model_list(self, params: ModelListParams | Mapping[str, JsonValue] | None = None) -> ModelListResponse:
        return await list_models(self.thread_manager, _params(ModelListParams, params))

    async def collaboration_mode_list(
        self,
        params: CollaborationModeListParams | Mapping[str, JsonValue] | None = None,
    ) -> CollaborationModeListResponse:
        return await list_collaboration_modes(self.thread_manager, _params(CollaborationModeListParams, params))

    async def experimental_feature_list(
        self,
        params: ExperimentalFeatureListParams | Mapping[str, JsonValue] | None = None,
    ) -> ExperimentalFeatureListResponse:
        return await self.experimental_feature_list_response(_params(ExperimentalFeatureListParams, params))

    async def permission_profile_list(
        self,
        params: PermissionProfileListParams | Mapping[str, JsonValue] | None = None,
    ) -> PermissionProfileListResponse:
        return await self.permission_profile_list_response(_params(PermissionProfileListParams, params))

    async def mock_experimental_method(
        self,
        params: MockExperimentalMethodParams | Mapping[str, JsonValue] | None = None,
    ) -> MockExperimentalMethodResponse:
        return mock_experimental_method_inner(_params(MockExperimentalMethodParams, params))

    async def skills_list(
        self,
        params: SkillsListParams | Mapping[str, JsonValue] | None = None,
    ) -> SkillsListResponse:
        params = _params(SkillsListParams, params)
        loader = _callable(self.thread_manager, "list_skills") or _callable(self.thread_manager, "skills_list")
        if loader is None:
            return SkillsListResponse(data=())
        data = await _maybe_await(loader(getattr(params, "cwds", ()), getattr(params, "force_reload", False)))
        return SkillsListResponse(data=data)

    async def hooks_list(
        self,
        params: HooksListParams | Mapping[str, JsonValue] | None = None,
    ) -> HooksListResponse:
        params = _params(HooksListParams, params)
        loader = _callable(self.thread_manager, "list_hooks") or _callable(self.thread_manager, "hooks_list")
        if loader is None:
            return HooksListResponse(data=())
        data = await _maybe_await(loader(getattr(params, "cwds", ())))
        return HooksListResponse(data=data)

    async def skills_config_write(
        self,
        params: SkillsConfigWriteParams | Mapping[str, JsonValue],
    ) -> SkillsConfigWriteResponse:
        return await self.skills_config_write_response_inner(_params(SkillsConfigWriteParams, params))

    async def resolve_cwd_config(self, cwd: str | Path) -> tuple[Path, Any]:
        cwd_abs = Path(cwd).expanduser().resolve()
        try:
            layers = await _maybe_await(_call(self.config_manager, "load_config_layers_for_cwd", cwd_abs))
        except Exception as exc:
            raise CatalogRequestProcessorError(internal_error(f"failed to reload config: {exc}")) from exc
        return cwd_abs, layers

    async def load_latest_config(self, fallback_cwd: str | Path | None = None) -> Any:
        try:
            if fallback_cwd is None:
                return await _maybe_await(_call(self.config_manager, "load_latest_config"))
            return await _maybe_await(_call(self.config_manager, "load_latest_config", fallback_cwd))
        except Exception as exc:
            raise CatalogRequestProcessorError(internal_error(f"failed to reload config: {exc}")) from exc

    async def workspace_codex_plugins_enabled(self, config: Any, auth: Any) -> bool:
        try:
            checker = _callable(self.workspace_settings_cache, "codex_plugins_enabled_for_workspace")
            if checker is None:
                checker = _callable(config, "codex_plugins_enabled_for_workspace")
            if checker is None:
                value = _get(config, "workspace_codex_plugins_enabled", default=True)
                return bool(value)
            return bool(await _maybe_await(checker(config, auth)))
        except Exception:
            return True

    async def experimental_feature_list_response(
        self,
        params: ExperimentalFeatureListParams,
    ) -> ExperimentalFeatureListResponse:
        config = await self._config_for_features(params.thread_id)
        auth = await _maybe_await(_call(self.auth_manager, "auth")) if self.auth_manager is not None else None
        workspace_plugins = await self.workspace_codex_plugins_enabled(config, auth)
        features = tuple(_feature_from_spec(spec, config, workspace_plugins) for spec in _feature_specs(config))
        data, next_cursor = paginate_items(features, params.limit, params.cursor, "feature flags")
        return ExperimentalFeatureListResponse(data=data, next_cursor=next_cursor)

    async def permission_profile_list_response(
        self,
        params: PermissionProfileListParams,
    ) -> PermissionProfileListResponse:
        try:
            if params.cwd is not None:
                _, layers = await self.resolve_cwd_config(params.cwd)
            else:
                layers = await _maybe_await(_call(self.config_manager, "load_config_layers", None))
        except CatalogRequestProcessorError:
            raise
        except Exception as exc:
            raise CatalogRequestProcessorError(internal_error(f"failed to reload config: {exc}")) from exc

        try:
            effective_config = _effective_config(layers)
        except Exception as exc:
            raise CatalogRequestProcessorError(internal_error(f"failed to read effective config: {exc}")) from exc

        profiles = list(BUILT_IN_PERMISSION_PROFILES)
        profiles.extend(_configured_permission_profiles(effective_config))
        data, next_cursor = paginate_items(profiles, params.limit, params.cursor, "permission profiles")
        return PermissionProfileListResponse(data=data, next_cursor=next_cursor)

    async def skills_config_write_response_inner(
        self,
        params: SkillsConfigWriteParams,
    ) -> SkillsConfigWriteResponse:
        path = getattr(params, "path", None)
        name = getattr(params, "name", None)
        enabled = bool(getattr(params, "enabled", False))
        has_path = path is not None
        has_name = isinstance(name, str) and bool(name.strip())
        if has_path == has_name:
            raise CatalogRequestProcessorError(
                invalid_params("skills/config/write requires exactly one of path or name")
            )

        edit = ConfigEdit("path" if has_path else "name", str(path if has_path else name), enabled)
        writer = _callable(self.config_manager, "apply_skill_config_edit") or _callable(self.config_manager, "apply_config_edit")
        if writer is not None:
            try:
                await _maybe_await(writer(edit))
            except Exception as exc:
                raise CatalogRequestProcessorError(internal_error(f"failed to update skill settings: {exc}")) from exc
        await _maybe_await(_optional_call(self.config_manager, "clear_plugin_cache"))
        await _maybe_await(_optional_call(self.thread_manager, "clear_skills_cache"))
        return SkillsConfigWriteResponse(effective_enabled=enabled)

    async def _config_for_features(self, thread_id: str | None) -> Any:
        if thread_id is None:
            return await self.load_latest_config(None)
        getter = _callable(self.thread_manager, "get_thread")
        if getter is None:
            raise CatalogRequestProcessorError(invalid_request(f"thread not found: {thread_id}"))
        thread = await _maybe_await(getter(thread_id))
        if thread is None:
            raise CatalogRequestProcessorError(invalid_request(f"thread not found: {thread_id}"))
        loader = _callable(self.config_manager, "load_latest_config_for_thread")
        if loader is None:
            return await self.load_latest_config(None)
        try:
            return await _maybe_await(loader(thread))
        except Exception as exc:
            raise CatalogRequestProcessorError(internal_error(f"failed to reload config: {exc}")) from exc


def skills_to_info(skills: Iterable[Any], disabled_paths: Iterable[str | Path]) -> tuple[SkillMetadata, ...]:
    disabled = {str(path) for path in disabled_paths}
    result: list[SkillMetadata] = []
    for skill in skills:
        path = str(_get(skill, "path"))
        result.append(
            SkillMetadata(
                name=_get(skill, "name"),
                description=_get(skill, "description"),
                short_description=_get(skill, "short_description", default=None),
                interface=_skill_interface(_get(skill, "interface", default=None)),
                dependencies=_skill_dependencies(_get(skill, "dependencies", default=None)),
                path=path,
                scope=_enum_value(_get(skill, "scope", default="user")),
                enabled=path not in disabled,
            )
        )
    return tuple(result)


def hooks_to_info(hooks: Iterable[Any]) -> tuple[HookMetadata, ...]:
    fields = (
        "key",
        "event_name",
        "handler_type",
        "matcher",
        "command",
        "timeout_sec",
        "status_message",
        "source_path",
        "source",
        "plugin_id",
        "display_order",
        "enabled",
        "is_managed",
        "current_hash",
        "trust_status",
    )
    return tuple(HookMetadata(**{field: _get(hook, field, default=None) for field in fields}) for hook in hooks)


def errors_to_info(errors: Iterable[Any]) -> tuple[SkillErrorInfo, ...]:
    return tuple(SkillErrorInfo(path=str(_get(error, "path")), message=_get(error, "message")) for error in errors)


def hook_errors_to_info(errors: Iterable[Any]) -> tuple[HookErrorInfo, ...]:
    return tuple(HookErrorInfo(path=str(_get(error, "path")), message=_get(error, "message")) for error in errors)


async def list_models(thread_manager: Any, params: ModelListParams) -> ModelListResponse:
    include_hidden = params.include_hidden if params.include_hidden is not None else False
    provider = (
        _callable(thread_manager, "supported_models")
        or _callable(thread_manager, "list_models")
        or _callable(thread_manager, "models")
    )
    if provider is None:
        models = ()
    else:
        models = await _maybe_await(provider(include_hidden))
    data, next_cursor = paginate_items(tuple(models), params.limit, params.cursor, "models")
    return ModelListResponse(data=data, next_cursor=next_cursor)


async def list_collaboration_modes(
    thread_manager: Any,
    params: CollaborationModeListParams,
) -> CollaborationModeListResponse:
    del params
    modes = await _maybe_await(_call(thread_manager, "list_collaboration_modes"))
    return CollaborationModeListResponse(data=tuple(modes))


def paginate_items(
    items: Sequence[Any],
    limit: int | None,
    cursor: str | None,
    total_label: str,
) -> tuple[tuple[Any, ...], str | None]:
    total = len(items)
    if total == 0:
        return (), None
    effective_limit = min(max(limit if limit is not None else total, 1), total)
    start = _parse_cursor(cursor)
    if start > total:
        raise CatalogRequestProcessorError(invalid_request(f"cursor {start} exceeds total {total_label} {total}"))
    end = min(start + effective_limit, total)
    next_cursor = str(end) if end < total else None
    return tuple(items[start:end]), next_cursor


def mock_experimental_method_inner(params: MockExperimentalMethodParams) -> MockExperimentalMethodResponse:
    return MockExperimentalMethodResponse(echoed=getattr(params, "value", None))


def _parse_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        value = int(cursor)
    except ValueError as exc:
        raise CatalogRequestProcessorError(invalid_request(f"invalid cursor: {cursor}")) from exc
    if value < 0:
        raise CatalogRequestProcessorError(invalid_request(f"invalid cursor: {cursor}"))
    return value


def _feature_from_spec(spec: Any, config: Any, workspace_plugins_enabled: bool) -> ExperimentalFeature:
    name = _get(spec, "id", default=_get(spec, "name"))
    stage = _feature_stage(_get(spec, "stage", default=ExperimentalFeatureStage.BETA.value))
    beta = stage == ExperimentalFeatureStage.BETA
    enabled = bool(_feature_enabled(config, name)) and (
        workspace_plugins_enabled or str(name) not in PLUGIN_FEATURE_NAMES
    )
    return ExperimentalFeature(
        name=str(name),
        stage=stage,
        display_name=_get(spec, "display_name", default=None) if beta else None,
        description=_get(spec, "menu_description", default=_get(spec, "description", default=None)) if beta else None,
        announcement=_get(spec, "announcement", default=None) if beta else None,
        enabled=enabled,
        default_enabled=bool(_get(spec, "default_enabled", default=False)),
    )


def _feature_stage(value: Any) -> ExperimentalFeatureStage:
    raw = _enum_value(value)
    mapping = {
        "experimental": ExperimentalFeatureStage.BETA,
        "beta": ExperimentalFeatureStage.BETA,
        "under_development": ExperimentalFeatureStage.UNDER_DEVELOPMENT,
        "underDevelopment": ExperimentalFeatureStage.UNDER_DEVELOPMENT,
        "stable": ExperimentalFeatureStage.STABLE,
        "deprecated": ExperimentalFeatureStage.DEPRECATED,
        "removed": ExperimentalFeatureStage.REMOVED,
    }
    return mapping.get(raw, ExperimentalFeatureStage.parse(raw))


def _feature_enabled(config: Any, name: str) -> bool:
    features = _get(config, "features", default={})
    enabled = _callable(features, "enabled")
    if enabled is not None:
        return bool(enabled(name))
    if isinstance(features, Mapping):
        if "enabled" in features and isinstance(features["enabled"], Mapping):
            return bool(features["enabled"].get(name, False))
        return bool(features.get(name, False))
    return bool(_get(features, name, default=False))


def _feature_specs(config: Any) -> tuple[Any, ...]:
    value = _get(config, "feature_specs", default=None)
    if value is None:
        value = _get(config, "features_catalog", default=None)
    if value is None:
        value = _get(_get(config, "features", default={}), "specs", default=())
    return tuple(value or ())


def _effective_config(layers: Any) -> Any:
    effective = _callable(layers, "effective_config")
    if effective is not None:
        return effective()
    if isinstance(layers, Mapping):
        return layers.get("effective_config", layers)
    return _get(layers, "effective_config", default=layers)


def _configured_permission_profiles(config: Any) -> tuple[PermissionProfileSummary, ...]:
    permissions = _get(config, "permissions", default={})
    entries = _get(permissions, "entries", default={})
    if entries is None:
        entries = {}
    result = []
    iterable = entries.items() if isinstance(entries, Mapping) else ((getattr(item, "id"), item) for item in entries)
    for profile_id, profile in iterable:
        result.append(
            PermissionProfileSummary(
                id=str(profile_id),
                description=_get(profile, "description", default=None),
            )
        )
    return tuple(sorted(result, key=lambda item: item.id))


def _skill_interface(value: Any) -> SkillInterface | None:
    if value is None:
        return None
    if isinstance(value, SkillInterface):
        return value
    return SkillInterface(**_object_fields(value, ("type", "value", "schema", "input_schema", "output_schema")))


def _skill_dependencies(value: Any) -> SkillDependencies | None:
    if value is None:
        return None
    if isinstance(value, SkillDependencies):
        return value
    tools = _get(value, "tools", default=())
    return SkillDependencies(tools=tuple(_skill_tool_dependency(tool) for tool in tools))


def _skill_tool_dependency(value: Any) -> SkillToolDependency:
    if isinstance(value, SkillToolDependency):
        return value
    return SkillToolDependency(
        name=_get(value, "name"),
        description=_get(value, "description", default=None),
        transport=_get(value, "transport", default=None),
        command=_get(value, "command", default=None),
        url=_get(value, "url", default=None),
    )


def _object_fields(value: Any, fields: Iterable[str]) -> dict[str, Any]:
    return {field: _get(value, field, default=None) for field in fields if _has(value, field)}


def _params(cls: type, value: Any) -> Any:
    if isinstance(value, cls):
        return value
    if value is None:
        try:
            return cls.from_mapping(None)
        except TypeError:
            return cls()
    if isinstance(value, Mapping):
        return cls.from_mapping(value)
    return value


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _optional_call(obj: Any, name: str, *args: Any) -> Any:
    method = _callable(obj, name)
    if method is None:
        return None
    return method(*args)


def _call(obj: Any, name: str, *args: Any) -> Any:
    method = _callable(obj, name)
    if method is None:
        raise AttributeError(name)
    return method(*args)


def _callable(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    value = getattr(obj, name, None)
    return value if callable(value) else None


def _get(obj: Any, name: str, *, default: Any = ...):
    if isinstance(obj, Mapping):
        if name in obj:
            return obj[name]
        camel = _snake_to_camel(name)
        if camel in obj:
            return obj[camel]
    elif hasattr(obj, name):
        return getattr(obj, name)
    if default is not ...:
        return default
    raise AttributeError(name)


def _has(obj: Any, name: str) -> bool:
    try:
        _get(obj, name)
    except AttributeError:
        return False
    return True


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


__all__ = [
    "BUILT_IN_PERMISSION_PROFILES",
    "CatalogRequestProcessor",
    "CatalogRequestProcessorError",
    "ConfigEdit",
    "SKILLS_LIST_CWD_CONCURRENCY",
    "errors_to_info",
    "hook_errors_to_info",
    "hooks_to_info",
    "list_collaboration_modes",
    "list_models",
    "mock_experimental_method_inner",
    "paginate_items",
    "skills_to_info",
]
