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
from pycodex.core.dynamic_tool_handler import DynamicToolHandler, DynamicToolRequestCallback
from pycodex.core.mcp_tool_handler import McpHandler, McpToolRequestCallback
from pycodex.core.request_plugin_install import (
    ListAvailablePluginsToInstallHandler,
    RequestPluginInstallCallback,
    RequestPluginInstallHandler,
)
from pycodex.core.tool_discovery import (
    DiscoverableTool,
    collect_request_plugin_install_entries,
)
from pycodex.core.tool_registry import ToolExposure, ToolRegistry, override_tool_exposure
from pycodex.core.tool_router import ToolRouter
from pycodex.core.tool_search_entry import default_namespace_description
from pycodex.core.tool_search_handler import ToolSearchHandler
from pycodex.protocol import ToolName

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
    append_tool_search_executor(planned_tools, options)

    specs: list[JsonValue] = []
    seen_tool_names: set[ToolName] = set()
    for runtime in planned_tools.runtimes:
        tool_name = _runtime_tool_name(runtime)
        if tool_name in seen_tool_names:
            continue
        seen_tool_names.add(tool_name)

        exposure = _runtime_exposure(runtime)
        if exposure.is_direct():
            specs.append(spec_for_model_request(exposure, _runtime_spec(runtime)))

    specs.extend(_spec_to_mapping(spec) for spec in planned_tools.hosted_specs)
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


def spec_for_model_request(_exposure: ToolExposure, spec: JsonValue) -> JsonValue:
    return _spec_to_mapping(spec)


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
            existing.setdefault("tools", []).extend(namespace.get("tools", ()))
            continue

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


def _copy_plan(planned_tools: PlannedTools) -> PlannedTools:
    return PlannedTools(
        runtimes=list(planned_tools.runtimes),
        hosted_specs=list(planned_tools.hosted_specs),
    )


def _runtime_tool_name(handler: Any) -> ToolName:
    value = _call_or_get(handler, "tool_name", None)
    if isinstance(value, ToolName):
        return value
    if isinstance(value, str):
        return ToolName.plain(value)
    raise TypeError("planned tool must expose a ToolName via tool_name()")


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
    "add_dynamic_tools",
    "add_mcp_tools",
    "append_tool_search_executor",
    "build_model_visible_specs_and_registry",
    "build_tool_router_from_plan",
    "merge_into_namespaces",
    "spec_for_model_request",
]
