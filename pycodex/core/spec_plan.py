"""Tool specification planning helpers ported from Codex core.

This is the dependency-free planning slice of
``core/src/tools/spec_plan.rs``: collect planned runtimes, inject
``tool_search`` for deferred tools, build model-visible specs, and build the
dispatch registry used by ``ToolRouter``.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pycodex.core.apply_patch import ApplyPatchHandler
from pycodex.core.code_mode import (
    CodeModeExecuteHandler,
    CodeModeWaitHandler,
    ToolNamespaceDescription,
    augment_tool_spec_for_code_mode,
    code_mode_name_for_tool_name,
    code_mode_namespace_name,
    collect_code_mode_exec_prompt_tool_definitions,
    is_code_mode_nested_tool,
    sort_code_mode_tool_definitions,
)
from pycodex.core.dynamic_tool_handler import DynamicToolHandler, DynamicToolRequestCallback
from pycodex.core.hosted_spec import (
    WebSearchToolOptions,
    create_image_generation_tool,
    create_web_search_tool,
)
from pycodex.core.mcp_tool_handler import McpHandler, McpToolRequestCallback
from pycodex.core.request_plugin_install import (
    ListAvailablePluginsToInstallHandler,
    RequestPluginInstallCallback,
    RequestPluginInstallHandler,
)
from pycodex.core.request_permissions_handler import RequestPermissionsCallback, RequestPermissionsHandler
from pycodex.core.tool_discovery import (
    DiscoverableTool,
    collect_request_plugin_install_entries,
)
from pycodex.core.tool_registry import ToolExposure, ToolRegistry, override_tool_exposure
from pycodex.core.tool_router import ToolRouter
from pycodex.core.tool_search_entry import default_namespace_description
from pycodex.core.tool_search_handler import ToolSearchHandler
from pycodex.core.unified_exec_handler import ExecCommandHandler, ExecCommandHandlerOptions, WriteStdinHandler
from pycodex.core.view_image_handler import ViewImageHandler, ViewImageToolOptions
from pycodex.protocol import ToolName, WebSearchConfig, WebSearchMode, WebSearchToolType

JsonValue = Any


@dataclass
class PlannedTools:
    runtimes: list[Any] = field(default_factory=list)
    hosted_specs: list[JsonValue] = field(default_factory=list)

    def add(self, handler: Any) -> None:
        self.runtimes.append(handler)

    def add_with_exposure(self, handler: Any, exposure: ToolExposure | str) -> None:
        self.runtimes.append(override_tool_exposure(handler, exposure))

    def add_dispatch_only(self, handler: Any) -> None:
        self.add_with_exposure(handler, ToolExposure.HIDDEN)

    def add_hosted_spec(self, spec: JsonValue) -> None:
        self.hosted_specs.append(spec)


@dataclass(frozen=True)
class ToolPlanOptions:
    search_tool_enabled: bool = True
    namespace_tools_enabled: bool = True
    code_mode_enabled: bool = False
    code_mode_only: bool = False
    provider_web_search: bool = False
    standalone_web_run_available: bool = False
    web_search_mode: WebSearchMode | None = None
    web_search_config: WebSearchConfig | None = None
    web_search_tool_type: WebSearchToolType = WebSearchToolType.TEXT
    provider_image_generation: bool = False
    image_generation_enabled: bool = False
    auth_uses_codex_backend: bool = False
    model_supports_image_input: bool = False


def tool_environment_mode_from_turn_context(turn_context: Any) -> str:
    environments = getattr(turn_context, "environments", None)
    if environments is None:
        return "none"
    candidates = getattr(environments, "turn_environments", environments)
    if candidates is None:
        return "none"
    count = len(tuple(candidates))
    if count == 0:
        return "none"
    if count == 1:
        return "single"
    return "multiple"


def tool_environment_has_environment(turn_context: Any) -> bool:
    return tool_environment_mode_from_turn_context(turn_context) != "none"


def tool_environment_includes_environment_id(turn_context: Any) -> bool:
    return tool_environment_mode_from_turn_context(turn_context) == "multiple"


def build_tool_router_from_plan(
    planned_tools: PlannedTools,
    options: ToolPlanOptions | None = None,
) -> ToolRouter:
    model_visible_specs, registry = build_model_visible_specs_and_registry(planned_tools, options)
    return ToolRouter.from_parts(registry, model_visible_specs)


def build_model_visible_specs_and_registry(
    planned_tools: PlannedTools,
    options: ToolPlanOptions | None = None,
) -> tuple[tuple[JsonValue, ...], ToolRegistry]:
    options = options or ToolPlanOptions()
    planned_tools = _copy_plan(planned_tools)
    add_hosted_model_tools(planned_tools, options)
    append_tool_search_executor(planned_tools, options)
    prepend_code_mode_executors(planned_tools, options)

    specs: list[JsonValue] = []
    seen_tool_names: set[ToolName] = set()
    for runtime in planned_tools.runtimes:
        tool_name = _runtime_tool_name(runtime)
        if tool_name in seen_tool_names:
            continue
        seen_tool_names.add(tool_name)

        exposure = _runtime_exposure(runtime)
        if exposure.is_direct() and not is_hidden_by_code_mode_only(tool_name, exposure, options):
            specs.append(spec_for_model_request(exposure, _runtime_spec(runtime), options))

    specs.extend(
        _spec_to_mapping(spec)
        for spec in planned_tools.hosted_specs
        if not is_hidden_by_code_mode_only(ToolName.plain(_spec_name(spec)), ToolExposure.DIRECT, options)
    )
    model_visible_specs = tuple(
        spec
        for spec in merge_into_namespaces(specs)
        if options.namespace_tools_enabled or _spec_type(spec) != "namespace"
    )
    return model_visible_specs, ToolRegistry.from_tools(planned_tools.runtimes)


def append_tool_search_executor(planned_tools: PlannedTools, options: ToolPlanOptions | None = None) -> None:
    options = options or ToolPlanOptions()
    if not (options.search_tool_enabled and options.namespace_tools_enabled):
        return

    search_infos = [
        _runtime_search_info(runtime)
        for runtime in planned_tools.runtimes
        if _runtime_exposure(runtime) is ToolExposure.DEFERRED
    ]
    search_infos = [info for info in search_infos if info is not None]
    if search_infos:
        planned_tools.add(ToolSearchHandler(search_infos))


def hosted_model_tool_specs(options: ToolPlanOptions | None = None) -> tuple[JsonValue, ...]:
    options = options or ToolPlanOptions()
    specs: list[JsonValue] = []
    web_search_mode = (
        options.web_search_mode
        if options.provider_web_search and not options.standalone_web_run_available
        else None
    )
    web_search_config = options.web_search_config if options.provider_web_search else None
    web_search_tool = create_web_search_tool(
        WebSearchToolOptions(
            web_search_mode=web_search_mode,
            web_search_config=web_search_config,
            web_search_tool_type=options.web_search_tool_type,
        )
    )
    if web_search_tool is not None:
        specs.append(web_search_tool)
    if image_generation_tool_enabled(options):
        specs.append(create_image_generation_tool("png"))
    return tuple(specs)


def add_hosted_model_tools(planned_tools: PlannedTools, options: ToolPlanOptions | None = None) -> None:
    for spec in hosted_model_tool_specs(options):
        planned_tools.add_hosted_spec(spec)


def image_generation_tool_enabled(options: ToolPlanOptions | None = None) -> bool:
    options = options or ToolPlanOptions()
    return (
        options.auth_uses_codex_backend
        and options.provider_image_generation
        and options.image_generation_enabled
        and options.model_supports_image_input
    )


def prepend_code_mode_executors(planned_tools: PlannedTools, options: ToolPlanOptions | None = None) -> None:
    options = options or ToolPlanOptions()
    if not options.code_mode_enabled:
        return

    deferred_tools_available = options.search_tool_enabled and any(
        _runtime_exposure(runtime) is ToolExposure.DEFERRED for runtime in planned_tools.runtimes
    )
    namespace_descriptions = code_mode_namespace_descriptions(planned_tools.runtimes)
    planned_tools.runtimes[0:0] = [
        CodeModeExecuteHandler(
            nested_tool_specs=tuple(
                _runtime_spec(runtime)
                for runtime in planned_tools.runtimes
                if _runtime_exposure(runtime)
                not in {ToolExposure.DIRECT_MODEL_ONLY, ToolExposure.HIDDEN}
            ),
            namespace_descriptions=namespace_descriptions,
            code_mode_only=options.code_mode_only,
            deferred_tools_available=deferred_tools_available,
        ),
        CodeModeWaitHandler(),
    ]


def add_dynamic_tools(
    planned_tools: PlannedTools,
    dynamic_tools: Iterable[Any],
    request_callback: DynamicToolRequestCallback | None = None,
) -> None:
    for tool in dynamic_tools:
        handler = DynamicToolHandler.new(tool, request_callback=request_callback)
        if handler is not None:
            planned_tools.add(handler)


def add_mcp_tools(
    planned_tools: PlannedTools,
    mcp_tools: Iterable[Any] = (),
    deferred_mcp_tools: Iterable[Any] = (),
    request_callback: McpToolRequestCallback | None = None,
) -> None:
    for tool_info in mcp_tools:
        planned_tools.add(McpHandler.new(tool_info, request_callback=request_callback))
    for tool_info in deferred_mcp_tools:
        planned_tools.add_with_exposure(
            McpHandler.new(tool_info, request_callback=request_callback),
            ToolExposure.DEFERRED,
        )


def add_apply_patch_tool(
    planned_tools: PlannedTools,
    *,
    has_environment: bool,
    apply_patch_tool_type: JsonValue | None,
    multi_environment: bool = False,
) -> None:
    if has_environment and apply_patch_tool_type is not None:
        planned_tools.add(ApplyPatchHandler.new(multi_environment))


def add_apply_patch_tool_for_turn_context(
    planned_tools: PlannedTools,
    turn_context: Any,
    *,
    apply_patch_tool_type: JsonValue | None,
) -> None:
    add_apply_patch_tool(
        planned_tools,
        has_environment=tool_environment_has_environment(turn_context),
        apply_patch_tool_type=apply_patch_tool_type,
        multi_environment=tool_environment_includes_environment_id(turn_context),
    )


def add_unified_exec_tools_for_turn_context(
    planned_tools: PlannedTools,
    turn_context: Any,
    *,
    allow_login_shell: bool = False,
    exec_permission_approvals_enabled: bool = False,
) -> None:
    if not tool_environment_has_environment(turn_context):
        return
    planned_tools.add(
        ExecCommandHandler(
            ExecCommandHandlerOptions(
                allow_login_shell=allow_login_shell,
                exec_permission_approvals_enabled=exec_permission_approvals_enabled,
                include_environment_id=tool_environment_includes_environment_id(turn_context),
            )
        )
    )
    planned_tools.add(WriteStdinHandler())


def add_view_image_tool_for_turn_context(
    planned_tools: PlannedTools,
    turn_context: Any,
    *,
    can_request_original_image_detail: bool = False,
) -> None:
    if not tool_environment_has_environment(turn_context):
        return
    planned_tools.add(
        ViewImageHandler(
            ViewImageToolOptions(
                can_request_original_image_detail=can_request_original_image_detail,
                include_environment_id=tool_environment_includes_environment_id(turn_context),
            )
        )
    )


def add_environment_tools_for_turn_context(
    planned_tools: PlannedTools,
    turn_context: Any,
    *,
    apply_patch_tool_type: JsonValue | None = None,
    allow_login_shell: bool = False,
    exec_permission_approvals_enabled: bool = False,
    can_request_original_image_detail: bool = False,
) -> None:
    add_unified_exec_tools_for_turn_context(
        planned_tools,
        turn_context,
        allow_login_shell=allow_login_shell,
        exec_permission_approvals_enabled=exec_permission_approvals_enabled,
    )
    add_apply_patch_tool_for_turn_context(
        planned_tools,
        turn_context,
        apply_patch_tool_type=apply_patch_tool_type,
    )
    add_view_image_tool_for_turn_context(
        planned_tools,
        turn_context,
        can_request_original_image_detail=can_request_original_image_detail,
    )


def build_environment_tool_router_from_turn_context(
    turn_context: Any,
    options: ToolPlanOptions | None = None,
    *,
    apply_patch_tool_type: JsonValue | None = None,
    allow_login_shell: bool = False,
    exec_permission_approvals_enabled: bool = False,
    can_request_original_image_detail: bool = False,
) -> ToolRouter:
    planned_tools = PlannedTools()
    add_environment_tools_for_turn_context(
        planned_tools,
        turn_context,
        apply_patch_tool_type=apply_patch_tool_type,
        allow_login_shell=allow_login_shell,
        exec_permission_approvals_enabled=exec_permission_approvals_enabled,
        can_request_original_image_detail=can_request_original_image_detail,
    )
    return build_tool_router_from_plan(planned_tools, options)


def add_request_permissions_tool(
    planned_tools: PlannedTools,
    *,
    request_permissions_tool_enabled: bool,
    request_callback: RequestPermissionsCallback | None = None,
) -> None:
    if not isinstance(request_permissions_tool_enabled, bool):
        raise TypeError("request_permissions_tool_enabled must be a bool")
    if not request_permissions_tool_enabled:
        return
    planned_tools.add(RequestPermissionsHandler(request_callback))


def add_discoverable_install_tools(
    planned_tools: PlannedTools,
    discoverable_tools: Iterable[DiscoverableTool | Mapping[str, JsonValue]] | None,
    *,
    tool_suggest_enabled: bool = True,
    apps_enabled: bool = True,
    plugins_enabled: bool = True,
    request_callback: RequestPluginInstallCallback | None = None,
    app_server_client_name: str | None = None,
    server_name: str = "codex-apps",
    thread_id: str = "",
    turn_id: str = "",
) -> None:
    if not (tool_suggest_enabled and apps_enabled and plugins_enabled):
        return
    if discoverable_tools is None:
        return
    tools = tuple(
        tool
        if isinstance(tool, DiscoverableTool)
        else DiscoverableTool.from_mapping(tool)
        for tool in discoverable_tools
    )
    if not tools:
        return
    planned_tools.add(
        ListAvailablePluginsToInstallHandler.new(
            collect_request_plugin_install_entries(tools)
        )
    )
    planned_tools.add(
        RequestPluginInstallHandler(
            discoverable_tools=tools,
            request_callback=request_callback,
            app_server_client_name=app_server_client_name,
            server_name=server_name,
            thread_id=thread_id,
            turn_id=turn_id,
        )
    )


def spec_for_model_request(
    exposure: ToolExposure,
    spec: JsonValue,
    options: ToolPlanOptions | None = None,
) -> JsonValue:
    options = options or ToolPlanOptions()
    data = _spec_to_mapping(spec)
    if options.code_mode_enabled and exposure is not ToolExposure.DIRECT_MODEL_ONLY:
        spec_name = _spec_name(data)
        if is_code_mode_nested_tool(spec_name):
            return augment_tool_spec_for_code_mode(data)
    return data


def merge_into_namespaces(specs: Iterable[JsonValue]) -> tuple[JsonValue, ...]:
    merged_specs: list[dict[str, JsonValue]] = []
    namespace_indices: dict[str, int] = {}
    for spec in specs:
        data = _spec_to_mapping(spec)
        if data.get("type") != "namespace":
            merged_specs.append(data)
            continue

        namespace = copy.deepcopy(data)
        name = str(namespace.get("name", ""))
        if name in namespace_indices:
            existing = merged_specs[namespace_indices[name]]
            existing_description = str(existing.get("description", ""))
            new_description = str(namespace.get("description", ""))
            if existing_description.strip() == "" and new_description.strip() != "":
                existing["description"] = namespace.get("description")
            existing_tools = list(existing.get("tools", ()))
            existing_tools.extend(namespace.get("tools", ()))
            existing["tools"] = existing_tools
            continue

        namespace["tools"] = list(namespace.get("tools", ()))
        namespace_indices[name] = len(merged_specs)
        merged_specs.append(namespace)

    for spec in merged_specs:
        if spec.get("type") != "namespace":
            continue
        spec["tools"] = tuple(
            sorted(
                (copy.deepcopy(tool) for tool in spec.get("tools", ())),
                key=lambda tool: str(tool.get("name", "")) if isinstance(tool, Mapping) else "",
            )
        )
        description = spec.get("description", "")
        if isinstance(description, str) and description.strip() == "":
            spec["description"] = default_namespace_description(str(spec.get("name", "")))

    return tuple(merged_specs)


def is_hidden_by_code_mode_only(
    tool_name: ToolName,
    exposure: ToolExposure | str,
    options: ToolPlanOptions | None = None,
) -> bool:
    options = options or ToolPlanOptions()
    return (
        options.code_mode_enabled
        and options.code_mode_only
        and ToolExposure.from_value(exposure) is not ToolExposure.DIRECT_MODEL_ONLY
        and is_code_mode_nested_tool(code_mode_name_for_tool_name(tool_name))
    )


def code_mode_namespace_descriptions(
    runtimes: Iterable[Any],
) -> dict[str, ToolNamespaceDescription]:
    descriptions: dict[str, ToolNamespaceDescription] = {}
    for runtime in runtimes:
        exposure = _runtime_exposure(runtime)
        if exposure in {ToolExposure.DEFERRED, ToolExposure.DIRECT_MODEL_ONLY, ToolExposure.HIDDEN}:
            continue
        for definition in collect_code_mode_exec_prompt_tool_definitions((_runtime_spec(runtime),)):
            namespace = definition.tool_name.namespace
            if namespace is None:
                continue
            description = _namespace_description_from_spec(_runtime_spec(runtime), namespace)
            existing = descriptions.get(namespace)
            if existing is None:
                descriptions[namespace] = ToolNamespaceDescription(namespace, description)
            elif existing.description.strip() == "" and description.strip() != "":
                descriptions[namespace] = ToolNamespaceDescription(existing.name, description)
    return descriptions


def code_mode_tool_sort_key(
    definition: Any,
    namespace_descriptions: Mapping[str, ToolNamespaceDescription | Mapping[str, str]] | None = None,
) -> tuple[int, str, str, str]:
    namespace = code_mode_namespace_name(definition, namespace_descriptions)
    return (0 if namespace is None else 1, namespace or "", definition.tool_name.name, definition.name)


def _copy_plan(planned_tools: PlannedTools) -> PlannedTools:
    return PlannedTools(
        runtimes=list(planned_tools.runtimes),
        hosted_specs=list(planned_tools.hosted_specs),
    )


def _runtime_tool_name(handler: Any) -> ToolName:
    value = _call_or_get(handler, "tool_name", None)
    try:
        return ToolName.from_value(value)
    except TypeError as err:
        raise TypeError("planned tool must expose a ToolName via tool_name()") from err


def _runtime_spec(handler: Any) -> JsonValue:
    return _call_or_get(handler, "spec", None)


def _runtime_exposure(handler: Any) -> ToolExposure:
    return ToolExposure.from_value(_call_or_get(handler, "exposure", ToolExposure.DIRECT))


def _runtime_search_info(handler: Any) -> Any:
    method = getattr(handler, "search_info", None)
    if method is None:
        return None
    return method()


def _spec_to_mapping(spec: JsonValue) -> dict[str, JsonValue]:
    if hasattr(spec, "to_mapping"):
        spec = spec.to_mapping()
    if not isinstance(spec, Mapping):
        raise TypeError("tool spec must be a mapping or expose to_mapping()")
    return copy.deepcopy(dict(spec))


def _spec_type(spec: JsonValue) -> str | None:
    return _spec_to_mapping(spec).get("type")


def _spec_name(spec: JsonValue) -> str:
    return str(_spec_to_mapping(spec).get("name", ""))


def _namespace_description_from_spec(spec: JsonValue, namespace: str) -> str:
    data = _spec_to_mapping(spec)
    if data.get("type") == "namespace" and str(data.get("name", "")) == namespace:
        description = data.get("description", "")
        return description if isinstance(description, str) else ""
    return ""


def _call_or_get(handler: Any, name: str, default: Any) -> Any:
    value = getattr(handler, name, default)
    if callable(value):
        return value()
    return value


__all__ = [
    "PlannedTools",
    "ToolPlanOptions",
    "add_discoverable_install_tools",
    "add_apply_patch_tool",
    "add_apply_patch_tool_for_turn_context",
    "add_dynamic_tools",
    "add_environment_tools_for_turn_context",
    "add_hosted_model_tools",
    "add_mcp_tools",
    "add_request_permissions_tool",
    "add_unified_exec_tools_for_turn_context",
    "add_view_image_tool_for_turn_context",
    "append_tool_search_executor",
    "build_model_visible_specs_and_registry",
    "build_environment_tool_router_from_turn_context",
    "build_tool_router_from_plan",
    "code_mode_namespace_descriptions",
    "code_mode_tool_sort_key",
    "hosted_model_tool_specs",
    "image_generation_tool_enabled",
    "is_hidden_by_code_mode_only",
    "merge_into_namespaces",
    "prepend_code_mode_executors",
    "spec_for_model_request",
    "tool_environment_has_environment",
    "tool_environment_includes_environment_id",
    "tool_environment_mode_from_turn_context",
]
