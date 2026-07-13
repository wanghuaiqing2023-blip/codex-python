"""Tool specification planning helpers ported from Codex core.

This is the dependency-free planning slice of
``core/src/tools/spec_plan.rs``: collect planned runtimes, inject
``tool_search`` for deferred tools, build model-visible specs, and build the
dispatch registry used by ``ToolRouter``.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from pycodex.core.tools.code_mode import (
    CodeModeExecuteHandler,
    CodeModeWaitHandler,
    PUBLIC_TOOL_NAME,
    WAIT_TOOL_NAME,
    ToolNamespaceDescription,
    augment_tool_spec_for_code_mode,
    code_mode_name_for_tool_name,
    code_mode_namespace_name,
    collect_code_mode_exec_prompt_tool_definitions,
    is_code_mode_nested_tool,
    sort_code_mode_tool_definitions,
)
from pycodex.core.tools.handlers.dynamic import DynamicToolHandler, DynamicToolRequestCallback
from pycodex.core.tools.hosted_spec import (
    WebSearchToolOptions,
    create_image_generation_tool,
    create_web_search_tool,
)
from pycodex.core.tools.handlers.agent_jobs import ReportAgentJobResultHandler, SpawnAgentsOnCsvHandler
from pycodex.core.tools.handlers.goal import CreateGoalHandler, GetGoalHandler, UpdateGoalHandler
from pycodex.core.tools.handlers.mcp import McpHandler, McpToolRequestCallback
from pycodex.core.tools.handlers.extension_tools import ExtensionToolAdapter
from pycodex.core.tools.handlers.multi_agents import (
    CloseAgentHandler,
    ResumeAgentHandler,
    SendInputHandler,
    SpawnAgentHandler,
    WaitAgentHandler,
)
from pycodex.core.tools.handlers.multi_agents_common import (
    DEFAULT_WAIT_TIMEOUT_MS,
    MAX_WAIT_TIMEOUT_MS,
    MIN_WAIT_TIMEOUT_MS,
)
from pycodex.core.tools.handlers.multi_agents_spec import SpawnAgentToolOptions, WaitAgentTimeoutOptions
from pycodex.core.tools.handlers.multi_agents_v2 import (
    CloseAgentHandler as CloseAgentHandlerV2,
    FollowupTaskHandler as FollowupTaskHandlerV2,
    ListAgentsHandler as ListAgentsHandlerV2,
    SendMessageHandler as SendMessageHandlerV2,
    SpawnAgentHandler as SpawnAgentHandlerV2,
    WaitAgentHandler as WaitAgentHandlerV2,
)
from pycodex.core.tools.handlers.request_plugin_install import (
    ListAvailablePluginsToInstallHandler,
    RequestPluginInstallCallback,
    RequestPluginInstallHandler,
)
from pycodex.core.tools.handlers.request_permissions import RequestPermissionsCallback, RequestPermissionsHandler
from pycodex.core.tools.handlers.plan import PlanHandler
from pycodex.core.tools.handlers.request_user_input import (
    RequestUserInputHandler,
    request_user_input_available_modes,
)
from pycodex.core.tools.handlers.shell import ShellCommandHandler, ShellCommandHandlerOptions
from pycodex.core.tools.handlers.test_sync import TestSyncHandler
from pycodex.tools.tool_discovery import (
    DiscoverableTool,
    collect_request_plugin_install_entries,
)
from pycodex.tools.tool_config import shell_type_for_model_and_features
from pycodex.core.tools.registry import ToolExposure, ToolRegistry, override_tool_exposure
from pycodex.core.tools.router import ToolRouter
from pycodex.core.tools.tool_search_entry import default_namespace_description
from pycodex.core.tools.handlers.tool_search import TOOL_SEARCH_TOOL_NAME, ToolSearchHandler
from pycodex.core.tools.handlers.unified_exec import ExecCommandHandler, ExecCommandHandlerOptions, WriteStdinHandler
from pycodex.core.tools.handlers.view_image import ViewImageHandler, ViewImageToolOptions
from pycodex.protocol import (
    ConfigShellToolType,
    ModeKind,
    SessionSource,
    SubAgentSource,
    ToolName,
    WebSearchConfig,
    WebSearchMode,
    WebSearchToolType,
)

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
    request_permissions_tool_enabled: bool = False
    goal_tools_enabled: bool = False
    tool_suggest_enabled: bool = False
    apps_enabled: bool = False
    plugins_enabled: bool = False
    request_user_input_default_mode_enabled: bool = False
    test_sync_tool_enabled: bool = False
    multi_agent_v2_enabled: bool = False
    collab_tools_enabled: bool = False
    multi_agent_v2_non_code_mode_only: bool = False
    agent_jobs_tools_enabled: bool = False
    agent_jobs_worker_tools_enabled: bool = False
    shell_tool_type: ConfigShellToolType | None = None
    use_unified_exec: bool = True
    allow_login_shell: bool = False
    exec_permission_approvals_enabled: bool = False


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


def build_tool_router(
    turn_context: Any,
    params: Any,
    options: ToolPlanOptions | None = None,
) -> ToolRouter:
    options = options or tool_plan_options_from_turn_context(turn_context)
    planned_tools = PlannedTools()
    add_shell_tools_for_turn_context(planned_tools, turn_context, options)
    add_core_utility_tools_for_turn_context(
        planned_tools,
        turn_context,
        options,
        discoverable_tools=getattr(params, "discoverable_tools", None),
    )
    add_collaboration_tools_for_turn_context(planned_tools, turn_context, options)
    add_mcp_tools(
        planned_tools,
        getattr(params, "mcp_tools", None) or (),
        getattr(params, "deferred_mcp_tools", None) or (),
    )
    add_dynamic_tools(planned_tools, getattr(params, "dynamic_tools", ()) or ())
    add_extension_tools(
        planned_tools,
        getattr(params, "extension_tool_executors", ()) or (),
        options,
    )
    return build_tool_router_from_plan(planned_tools, options)


def tool_plan_options_from_turn_context(turn_context: Any) -> ToolPlanOptions:
    provider = getattr(turn_context, "provider", None)
    capabilities = _call_or_get(provider, "capabilities", None)
    config = getattr(turn_context, "config", None)
    model_info = getattr(turn_context, "model_info", None)
    features = getattr(turn_context, "features", None)
    web_search_mode = _field_value(getattr(config, "web_search_mode", None), "value")
    web_search_tool_type = getattr(model_info, "web_search_tool_type", WebSearchToolType.TEXT)
    if web_search_tool_type is None:
        web_search_tool_type = WebSearchToolType.TEXT
    return ToolPlanOptions(
        search_tool_enabled=bool(getattr(model_info, "supports_search_tool", False)),
        namespace_tools_enabled=bool(getattr(capabilities, "namespace_tools", True)),
        code_mode_enabled=_feature_enabled(features, "CodeMode", "code_mode"),
        code_mode_only=_feature_enabled(features, "CodeModeOnly", "code_mode_only"),
        provider_web_search=bool(getattr(capabilities, "web_search", False)),
        standalone_web_run_available=False,
        web_search_mode=web_search_mode if isinstance(web_search_mode, WebSearchMode) else None,
        web_search_config=getattr(config, "web_search_config", None),
        web_search_tool_type=web_search_tool_type,
        provider_image_generation=bool(getattr(capabilities, "image_generation", False)),
        image_generation_enabled=_feature_enabled(features, "ImageGeneration", "image_generation"),
        auth_uses_codex_backend=_auth_uses_codex_backend(getattr(turn_context, "auth_manager", None)),
        model_supports_image_input=_model_supports_image_input(model_info),
        request_permissions_tool_enabled=_feature_enabled(features, "RequestPermissionsTool", "request_permissions_tool"),
        goal_tools_enabled=_goal_tools_enabled(turn_context),
        tool_suggest_enabled=_feature_enabled(features, "ToolSuggest", "tool_suggest"),
        apps_enabled=_feature_enabled(features, "Apps", "apps"),
        plugins_enabled=_feature_enabled(features, "Plugins", "plugins"),
        request_user_input_default_mode_enabled=_feature_enabled(features, "RequestUserInputDefaultMode", "request_user_input_default_mode"),
        test_sync_tool_enabled=_model_supports_experimental_tool(model_info, "test_sync_tool"),
        multi_agent_v2_enabled=_feature_enabled(features, "MultiAgentV2", "multi_agent_v2"),
        collab_tools_enabled=(
            _feature_enabled(features, "MultiAgentV2", "multi_agent_v2")
            or _feature_enabled(features, "Collab", "collab")
        ),
        multi_agent_v2_non_code_mode_only=bool(
            getattr(getattr(config, "multi_agent_v2", None), "non_code_mode_only", False)
        ),
        agent_jobs_tools_enabled=_feature_enabled(features, "SpawnCsv", "spawn_csv"),
        agent_jobs_worker_tools_enabled=_agent_jobs_worker_tools_enabled(turn_context, features),
        shell_tool_type=shell_type_for_model_and_features(model_info, features),
        use_unified_exec=_feature_enabled(features, "UnifiedExec", "unified_exec"),
        allow_login_shell=bool(getattr(getattr(config, "permissions", None), "allow_login_shell", False)),
        exec_permission_approvals_enabled=_feature_enabled(features, "ExecPermissionApprovals", "exec_permission_approvals"),
    )


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


def add_extension_tools(
    planned_tools: PlannedTools,
    executors: Iterable[Any],
    options: ToolPlanOptions | None = None,
) -> None:
    options = options or ToolPlanOptions()
    reserved_tool_names = {_runtime_tool_name(runtime) for runtime in planned_tools.runtimes}
    if options.code_mode_enabled:
        reserved_tool_names.add(ToolName.plain(PUBLIC_TOOL_NAME))
        reserved_tool_names.add(ToolName.plain(WAIT_TOOL_NAME))
    if (
        options.search_tool_enabled
        and options.namespace_tools_enabled
        and any(_runtime_exposure(runtime) is ToolExposure.DEFERRED for runtime in planned_tools.runtimes)
    ):
        reserved_tool_names.add(ToolName.plain(TOOL_SEARCH_TOOL_NAME))

    for executor in executors:
        adapter = ExtensionToolAdapter.new(executor)
        tool_name = adapter.tool_name()
        if tool_name in reserved_tool_names:
            continue
        reserved_tool_names.add(tool_name)
        planned_tools.add(adapter)


def add_apply_patch_tool(
    planned_tools: PlannedTools,
    *,
    has_environment: bool,
    apply_patch_tool_type: JsonValue | None,
    multi_environment: bool = False,
) -> None:
    if has_environment and apply_patch_tool_type is not None:
        from pycodex.apply_patch import ApplyPatchHandler

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
    options: ToolPlanOptions | None = None,
    apply_patch_tool_type: JsonValue | None = None,
    allow_login_shell: bool = False,
    exec_permission_approvals_enabled: bool = False,
    request_permissions_tool_enabled: bool = False,
    can_request_original_image_detail: bool = False,
) -> None:
    shell_options = options or tool_plan_options_from_turn_context(turn_context)
    shell_options = replace(
        shell_options,
        allow_login_shell=allow_login_shell,
        exec_permission_approvals_enabled=exec_permission_approvals_enabled,
    )
    add_shell_tools_for_turn_context(
        planned_tools,
        turn_context,
        shell_options,
    )
    add_apply_patch_tool_for_turn_context(
        planned_tools,
        turn_context,
        apply_patch_tool_type=apply_patch_tool_type,
    )
    add_request_permissions_tool(
        planned_tools,
        request_permissions_tool_enabled=request_permissions_tool_enabled,
    )
    add_view_image_tool_for_turn_context(
        planned_tools,
        turn_context,
        can_request_original_image_detail=can_request_original_image_detail,
    )


def add_shell_tools_for_turn_context(
    planned_tools: PlannedTools,
    turn_context: Any,
    options: ToolPlanOptions | None = None,
) -> None:
    options = options or tool_plan_options_from_turn_context(turn_context)
    if not tool_environment_has_environment(turn_context):
        return
    include_environment_id = tool_environment_includes_environment_id(turn_context)
    shell_tool_type = options.shell_tool_type
    if shell_tool_type is None:
        shell_tool_type = (
            ConfigShellToolType.UNIFIED_EXEC
            if options.use_unified_exec
            else ConfigShellToolType.SHELL_COMMAND
        )
    if shell_tool_type is ConfigShellToolType.DISABLED:
        return
    if shell_tool_type is ConfigShellToolType.UNIFIED_EXEC:
        planned_tools.add(
            ExecCommandHandler(
                ExecCommandHandlerOptions(
                    allow_login_shell=options.allow_login_shell,
                    exec_permission_approvals_enabled=options.exec_permission_approvals_enabled,
                    include_environment_id=include_environment_id,
                )
            )
        )
        planned_tools.add(WriteStdinHandler())
        planned_tools.add_dispatch_only(
            ShellCommandHandler(
                ShellCommandHandlerOptions(
                    allow_login_shell=options.allow_login_shell,
                    exec_permission_approvals_enabled=options.exec_permission_approvals_enabled,
                )
            )
        )
        return
    planned_tools.add(
        ShellCommandHandler(
            ShellCommandHandlerOptions(
                allow_login_shell=options.allow_login_shell,
                exec_permission_approvals_enabled=options.exec_permission_approvals_enabled,
            )
        )
    )


def add_core_utility_tools_for_turn_context(
    planned_tools: PlannedTools,
    turn_context: Any,
    options: ToolPlanOptions | None = None,
    *,
    discoverable_tools: Iterable[DiscoverableTool | Mapping[str, JsonValue]] | None = None,
) -> None:
    options = options or tool_plan_options_from_turn_context(turn_context)
    planned_tools.add(PlanHandler())
    if options.goal_tools_enabled:
        planned_tools.add(GetGoalHandler())
        planned_tools.add(CreateGoalHandler())
        planned_tools.add(UpdateGoalHandler())
    planned_tools.add(
        RequestUserInputHandler(
            request_user_input_available_modes(
                default_mode_enabled=options.request_user_input_default_mode_enabled,
            )
        )
    )
    add_request_permissions_tool(
        planned_tools,
        request_permissions_tool_enabled=options.request_permissions_tool_enabled,
    )
    add_discoverable_install_tools(
        planned_tools,
        discoverable_tools,
        tool_suggest_enabled=options.tool_suggest_enabled,
        apps_enabled=options.apps_enabled,
        plugins_enabled=options.plugins_enabled,
    )
    add_apply_patch_tool_for_turn_context(
        planned_tools,
        turn_context,
        apply_patch_tool_type=getattr(getattr(turn_context, "model_info", None), "apply_patch_tool_type", None),
    )
    if options.test_sync_tool_enabled:
        planned_tools.add(TestSyncHandler())
    add_view_image_tool_for_turn_context(
        planned_tools,
        turn_context,
        can_request_original_image_detail=_can_request_original_image_detail(getattr(turn_context, "model_info", None)),
    )


def add_collaboration_tools_for_turn_context(
    planned_tools: PlannedTools,
    turn_context: Any,
    options: ToolPlanOptions | None = None,
) -> None:
    options = options or tool_plan_options_from_turn_context(turn_context)
    if options.collab_tools_enabled:
        wait_options = wait_agent_timeout_options_from_turn_context(turn_context, options)
        spawn_options = spawn_agent_tool_options_from_turn_context(turn_context)
        if options.multi_agent_v2_enabled:
            exposure = (
                ToolExposure.DIRECT_MODEL_ONLY
                if options.multi_agent_v2_non_code_mode_only
                else ToolExposure.DIRECT
            )
            namespace = _multi_agent_v2_tool_namespace(turn_context, options)
            planned_tools.add_with_exposure(_multi_agent_v2_handler(SpawnAgentHandlerV2(spawn_options), namespace), exposure)
            planned_tools.add_with_exposure(_multi_agent_v2_handler(SendMessageHandlerV2(), namespace), exposure)
            planned_tools.add_with_exposure(_multi_agent_v2_handler(FollowupTaskHandlerV2(), namespace), exposure)
            planned_tools.add_with_exposure(_multi_agent_v2_handler(WaitAgentHandlerV2(wait_options), namespace), exposure)
            planned_tools.add_with_exposure(_multi_agent_v2_handler(CloseAgentHandlerV2(), namespace), exposure)
            planned_tools.add_with_exposure(_multi_agent_v2_handler(ListAgentsHandlerV2(), namespace), exposure)
        else:
            exposure = (
                ToolExposure.DEFERRED
                if options.search_tool_enabled and options.namespace_tools_enabled
                else ToolExposure.DIRECT
            )
            planned_tools.add_with_exposure(SpawnAgentHandler(spawn_options), exposure)
            planned_tools.add_with_exposure(SendInputHandler(), exposure)
            planned_tools.add_with_exposure(ResumeAgentHandler(), exposure)
            planned_tools.add_with_exposure(WaitAgentHandler(wait_options), exposure)
            planned_tools.add_with_exposure(CloseAgentHandler(), exposure)

    if options.agent_jobs_tools_enabled:
        planned_tools.add(SpawnAgentsOnCsvHandler())
        if options.agent_jobs_worker_tools_enabled:
            planned_tools.add(ReportAgentJobResultHandler())


def wait_agent_timeout_options_from_turn_context(
    turn_context: Any,
    options: ToolPlanOptions | None = None,
) -> WaitAgentTimeoutOptions:
    options = options or tool_plan_options_from_turn_context(turn_context)
    if not options.multi_agent_v2_enabled:
        return WaitAgentTimeoutOptions(DEFAULT_WAIT_TIMEOUT_MS, MIN_WAIT_TIMEOUT_MS, MAX_WAIT_TIMEOUT_MS)
    multi_agent_config = getattr(getattr(turn_context, "config", None), "multi_agent_v2", None)
    return WaitAgentTimeoutOptions(
        getattr(multi_agent_config, "default_wait_timeout_ms", DEFAULT_WAIT_TIMEOUT_MS),
        getattr(multi_agent_config, "min_wait_timeout_ms", MIN_WAIT_TIMEOUT_MS),
        getattr(multi_agent_config, "max_wait_timeout_ms", MAX_WAIT_TIMEOUT_MS),
    )


def spawn_agent_tool_options_from_turn_context(turn_context: Any) -> SpawnAgentToolOptions:
    config = getattr(turn_context, "config", None)
    multi_agent_config = getattr(config, "multi_agent_v2", None)
    return SpawnAgentToolOptions(
        available_models=getattr(turn_context, "available_models", ()),
        agent_type_description=_agent_type_description(turn_context),
        hide_agent_type_model_reasoning=bool(getattr(multi_agent_config, "hide_spawn_agent_metadata", False)),
        include_usage_hint=bool(getattr(multi_agent_config, "usage_hint_enabled", False)),
        usage_hint_text=getattr(multi_agent_config, "usage_hint_text", None),
        max_concurrent_threads_per_session=getattr(multi_agent_config, "max_concurrent_threads_per_session", None),
    )


def build_environment_tool_router_from_turn_context(
    turn_context: Any,
    options: ToolPlanOptions | None = None,
    *,
    apply_patch_tool_type: JsonValue | None = None,
    allow_login_shell: bool = False,
    exec_permission_approvals_enabled: bool = False,
    request_permissions_tool_enabled: bool = False,
    can_request_original_image_detail: bool = False,
) -> ToolRouter:
    options = options or tool_plan_options_from_turn_context(turn_context)
    planned_tools = PlannedTools()
    add_environment_tools_for_turn_context(
        planned_tools,
        turn_context,
        options=options,
        apply_patch_tool_type=apply_patch_tool_type,
        allow_login_shell=allow_login_shell,
        exec_permission_approvals_enabled=exec_permission_approvals_enabled,
        request_permissions_tool_enabled=request_permissions_tool_enabled,
        can_request_original_image_detail=can_request_original_image_detail,
    )
    if _goal_tools_enabled(turn_context):
        planned_tools.add(GetGoalHandler())
        planned_tools.add(CreateGoalHandler())
        planned_tools.add(UpdateGoalHandler())
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


class MultiAgentV2NamespaceOverride:
    def __init__(self, handler: Any, namespace: str) -> None:
        if not isinstance(namespace, str) or namespace == "":
            raise TypeError("namespace must be a non-empty string")
        self.handler = handler
        self.namespace = namespace

    def tool_name(self) -> ToolName:
        name = _runtime_tool_name(self.handler)
        return ToolName.namespaced(self.namespace, name.name)

    def spec(self) -> JsonValue:
        spec = _runtime_spec(self.handler)
        data = _spec_to_mapping(spec)
        if data.get("type") != "function":
            return data
        return {
            "type": "namespace",
            "name": self.namespace,
            "description": "Tools for spawning and managing sub-agents.",
            "tools": (data,),
        }

    def exposure(self) -> ToolExposure:
        return _runtime_exposure(self.handler)

    def supports_parallel_tool_calls(self) -> bool:
        value = _call_or_get(self.handler, "supports_parallel_tool_calls", False)
        return bool(value)

    def waits_for_runtime_cancellation(self) -> bool:
        value = _call_or_get(self.handler, "waits_for_runtime_cancellation", False)
        return bool(value)

    def matches_kind(self, payload: Any) -> bool:
        method = getattr(self.handler, "matches_kind", None)
        if callable(method):
            return bool(method(payload))
        return True

    def search_info(self) -> Any:
        method = getattr(self.handler, "search_info", None)
        if callable(method):
            return method()
        return None

    def handle(self, invocation: Any) -> Any:
        method = getattr(self.handler, "handle", None)
        if not callable(method):
            raise TypeError("wrapped multi-agent handler must expose handle(invocation)")
        return method(invocation)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.handler, name)


def _multi_agent_v2_handler(handler: Any, namespace: str | None) -> Any:
    if namespace is None:
        return handler
    return MultiAgentV2NamespaceOverride(handler, namespace)


def _multi_agent_v2_tool_namespace(turn_context: Any, options: ToolPlanOptions) -> str | None:
    if not options.namespace_tools_enabled:
        return None
    multi_agent_config = getattr(getattr(turn_context, "config", None), "multi_agent_v2", None)
    namespace = getattr(multi_agent_config, "tool_namespace", None)
    if namespace is None or namespace == "":
        return None
    return str(namespace)


def _feature_enabled(features: Any, *names: str) -> bool:
    if features is None:
        return False
    getter = getattr(features, "get", None)
    if callable(getter):
        features = getter()
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        for name in names:
            for candidate in (name, _snake_to_pascal(name), _pascal_to_snake(name)):
                try:
                    if bool(enabled(candidate)):
                        return True
                except Exception:
                    continue
    for name in names:
        for candidate in (name, _snake_to_pascal(name), _pascal_to_snake(name)):
            value = getattr(features, candidate, None)
            if isinstance(value, bool) and value:
                return True
            if isinstance(features, Mapping) and bool(features.get(candidate, False)):
                return True
    return False


def _field_value(value: Any, attr: str, default: Any = None) -> Any:
    if value is None:
        return default
    field = getattr(value, attr, default)
    return field() if callable(field) else field


def _auth_uses_codex_backend(auth_manager: Any) -> bool:
    if auth_manager is None:
        return False
    if isinstance(auth_manager, (tuple, list)):
        return any(_auth_uses_codex_backend(item) for item in auth_manager)
    current = getattr(auth_manager, "current_auth_uses_codex_backend", None)
    if callable(current):
        try:
            return bool(current())
        except Exception:
            return False
    return bool(getattr(auth_manager, "uses_codex_backend", False))


def _model_supports_image_input(model_info: Any) -> bool:
    modalities = getattr(model_info, "input_modalities", ())
    for modality in modalities or ():
        value = getattr(modality, "value", modality)
        if str(value).lower() == "image":
            return True
    return False


def _model_supports_experimental_tool(model_info: Any, tool_name: str) -> bool:
    tools = getattr(model_info, "experimental_supported_tools", ())
    return tool_name in tuple(tools or ())


def _can_request_original_image_detail(model_info: Any) -> bool:
    checker = getattr(model_info, "can_request_original_image_detail", None)
    if callable(checker):
        return bool(checker())
    return bool(getattr(model_info, "original_image_detail_supported", False))


def _goal_tools_enabled(turn_context: Any) -> bool:
    getter = getattr(turn_context, "goal_tools_enabled", None)
    enabled = bool(getter()) if callable(getter) else bool(getattr(turn_context, "goal_tools_enabled", False))
    if not enabled:
        return False
    session_source = getattr(turn_context, "session_source", None)
    source_text = str(getattr(session_source, "value", session_source)).lower()
    return "review" not in source_text


def _agent_jobs_worker_tools_enabled(turn_context: Any, features: Any) -> bool:
    if not _feature_enabled(features, "SpawnCsv", "spawn_csv"):
        return False
    session_source = getattr(turn_context, "session_source", None)
    if isinstance(session_source, Mapping):
        label = session_source.get("label") or session_source.get("source") or ""
    else:
        label = getattr(session_source, "label", None)
        if label is None:
            sub_agent = getattr(session_source, "sub_agent", None)
            label = getattr(sub_agent, "label", "")
    return str(label).startswith("agent_job:")


def _agent_type_description(turn_context: Any) -> str:
    config = getattr(turn_context, "config", None)
    roles = getattr(config, "agent_roles", None)
    if isinstance(roles, Mapping) and roles:
        return "\n".join(str(key) for key in sorted(roles))
    return ""


def _snake_to_pascal(value: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in value.split("_") if part)


def _pascal_to_snake(value: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


__all__ = [
    "PlannedTools",
    "ToolPlanOptions",
    "MultiAgentV2NamespaceOverride",
    "add_collaboration_tools_for_turn_context",
    "add_core_utility_tools_for_turn_context",
    "add_discoverable_install_tools",
    "add_apply_patch_tool",
    "add_apply_patch_tool_for_turn_context",
    "add_dynamic_tools",
    "add_environment_tools_for_turn_context",
    "add_extension_tools",
    "add_hosted_model_tools",
    "add_mcp_tools",
    "add_request_permissions_tool",
    "add_shell_tools_for_turn_context",
    "add_unified_exec_tools_for_turn_context",
    "add_view_image_tool_for_turn_context",
    "append_tool_search_executor",
    "build_model_visible_specs_and_registry",
    "build_tool_router",
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
    "tool_plan_options_from_turn_context",
    "wait_agent_timeout_options_from_turn_context",
    "spawn_agent_tool_options_from_turn_context",
]

