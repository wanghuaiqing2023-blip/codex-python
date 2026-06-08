"""Core tool handler modules aligned with ``codex-rs/core/src/tools/handlers``.

Concrete handlers still live in their submodules.  The shared pure helper layer
from Rust's ``core/src/tools/handlers/mod.rs`` is re-exported here so all
handlers use one common argument parsing, hook rewrite, and permission boundary.
The exports are intentionally lazy to avoid importing concrete handlers through
``pycodex.core`` during package initialization.
"""

__all__ = [
    "ApplyPatchHandler",
    "CodeModeExecuteHandler",
    "CodeModeWaitHandler",
    "CreateGoalHandler",
    "DynamicToolHandler",
    "EffectiveAdditionalPermissions",
    "ExecCommandHandler",
    "ExecCommandHandlerOptions",
    "GetGoalHandler",
    "ListAvailablePluginsToInstallHandler",
    "ListMcpResourceTemplatesHandler",
    "ListMcpResourcesHandler",
    "McpHandler",
    "PlanHandler",
    "ReadMcpResourceHandler",
    "RequestPermissionsHandler",
    "RequestPluginInstallHandler",
    "RequestUserInputHandler",
    "ShellCommandHandler",
    "ShellCommandHandlerOptions",
    "TestSyncHandler",
    "ToolSearchHandler",
    "UpdateGoalHandler",
    "ViewImageHandler",
    "WriteStdinHandler",
    "apply_granted_turn_permissions",
    "implicit_granted_permissions",
    "intersect_permission_profiles",
    "merge_permission_profiles",
    "normalize_additional_permissions",
    "normalize_and_validate_additional_permissions",
    "normalize_request_permissions_response",
    "parse_arguments",
    "parse_arguments_with_base_path",
    "permissions_are_preapproved",
    "record_granted_request_permissions",
    "resolve_tool_environment",
    "resolve_workdir_base_path",
    "rewrite_function_arguments",
    "rewrite_function_string_argument",
    "session_strict_auto_review",
    "updated_hook_command",
]

_HANDLER_EXPORTS = {
    "ApplyPatchHandler": ("pycodex.apply_patch", "ApplyPatchHandler"),
    "CodeModeExecuteHandler": ("pycodex.core.tools.code_mode", "CodeModeExecuteHandler"),
    "CodeModeWaitHandler": ("pycodex.core.tools.code_mode", "CodeModeWaitHandler"),
    "CreateGoalHandler": ("pycodex.core.tools.handlers.goal", "CreateGoalHandler"),
    "DynamicToolHandler": ("pycodex.core.tools.handlers.dynamic", "DynamicToolHandler"),
    "ExecCommandHandler": ("pycodex.core.tools.handlers.unified_exec", "ExecCommandHandler"),
    "ExecCommandHandlerOptions": ("pycodex.core.tools.handlers.unified_exec", "ExecCommandHandlerOptions"),
    "GetGoalHandler": ("pycodex.core.tools.handlers.goal", "GetGoalHandler"),
    "ListAvailablePluginsToInstallHandler": (
        "pycodex.core.tools.handlers.list_available_plugins_to_install",
        "ListAvailablePluginsToInstallHandler",
    ),
    "ListMcpResourceTemplatesHandler": (
        "pycodex.core.tools.handlers.mcp_resource",
        "ListMcpResourceTemplatesHandler",
    ),
    "ListMcpResourcesHandler": ("pycodex.core.tools.handlers.mcp_resource", "ListMcpResourcesHandler"),
    "McpHandler": ("pycodex.core.tools.handlers.mcp", "McpHandler"),
    "PlanHandler": ("pycodex.core.tools.handlers.plan", "PlanHandler"),
    "ReadMcpResourceHandler": ("pycodex.core.tools.handlers.mcp_resource", "ReadMcpResourceHandler"),
    "RequestPermissionsHandler": ("pycodex.core.tools.handlers.request_permissions", "RequestPermissionsHandler"),
    "RequestPluginInstallHandler": (
        "pycodex.core.tools.handlers.request_plugin_install",
        "RequestPluginInstallHandler",
    ),
    "RequestUserInputHandler": ("pycodex.core.tools.handlers.request_user_input", "RequestUserInputHandler"),
    "ShellCommandHandler": ("pycodex.core.tools.handlers.shell", "ShellCommandHandler"),
    "ShellCommandHandlerOptions": ("pycodex.core.tools.handlers.shell", "ShellCommandHandlerOptions"),
    "TestSyncHandler": ("pycodex.core.tools.handlers.test_sync", "TestSyncHandler"),
    "ToolSearchHandler": ("pycodex.core.tools.handlers.tool_search", "ToolSearchHandler"),
    "UpdateGoalHandler": ("pycodex.core.tools.handlers.goal", "UpdateGoalHandler"),
    "ViewImageHandler": ("pycodex.core.tools.handlers.view_image", "ViewImageHandler"),
    "WriteStdinHandler": ("pycodex.core.tools.handlers.unified_exec", "WriteStdinHandler"),
}


def __getattr__(name: str):
    if name in _HANDLER_EXPORTS:
        from importlib import import_module

        module_name, attr_name = _HANDLER_EXPORTS[name]
        return getattr(import_module(module_name), attr_name)
    if name in __all__:
        from . import utils

        return getattr(utils, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
