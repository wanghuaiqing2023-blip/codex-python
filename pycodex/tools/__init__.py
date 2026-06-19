"""Canonical package for helpers ported from `codex-rs/tools`.

The Rust crate root re-exports many child modules.  Python keeps the same
public surface lazily so importing one child module, such as
``pycodex.tools.tool_discovery``, does not eagerly pull in ``pycodex.core`` and
create initialization cycles.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from pycodex.protocol import ToolName


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "AdditionalProperties": ("pycodex.tools.json_schema", "AdditionalProperties"),
    "DiscoverablePluginInfo": ("pycodex.tools.tool_discovery", "DiscoverablePluginInfo"),
    "DiscoverableTool": ("pycodex.tools.tool_discovery", "DiscoverableTool"),
    "DiscoverableToolAction": ("pycodex.tools.tool_discovery", "DiscoverableToolAction"),
    "DiscoverableToolType": ("pycodex.tools.tool_discovery", "DiscoverableToolType"),
    "FreeformTool": ("pycodex.tools.responses_api", "FreeformTool"),
    "FreeformToolFormat": ("pycodex.tools.responses_api", "FreeformToolFormat"),
    "FunctionCallError": ("pycodex.tools.function_call_error", "FunctionCallError"),
    "FunctionCallErrorKind": ("pycodex.tools.function_call_error", "FunctionCallErrorKind"),
    "JsonSchema": ("pycodex.tools.json_schema", "JsonSchema"),
    "JsonSchemaPrimitiveType": ("pycodex.tools.json_schema", "JsonSchemaPrimitiveType"),
    "JsonSchemaType": ("pycodex.tools.json_schema", "JsonSchemaType"),
    "JsonToolOutput": ("pycodex.tools.tool_output", "JsonToolOutput"),
    "LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME": (
        "pycodex.tools.tool_discovery",
        "LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME",
    ),
    "ListAvailablePluginsToInstallResult": (
        "pycodex.tools.tool_discovery",
        "ListAvailablePluginsToInstallResult",
    ),
    "LoadableToolSpec": ("pycodex.tools.responses_api", "LoadableToolSpec"),
    "REQUEST_PLUGIN_INSTALL_APPROVAL_KIND_VALUE": (
        "pycodex.tools.request_plugin_install",
        "REQUEST_PLUGIN_INSTALL_APPROVAL_KIND_VALUE",
    ),
    "REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE": (
        "pycodex.tools.request_plugin_install",
        "REQUEST_PLUGIN_INSTALL_PERSIST_ALWAYS_VALUE",
    ),
    "REQUEST_PLUGIN_INSTALL_PERSIST_KEY": (
        "pycodex.tools.request_plugin_install",
        "REQUEST_PLUGIN_INSTALL_PERSIST_KEY",
    ),
    "REQUEST_PLUGIN_INSTALL_SUGGEST_TYPE_KEY": (
        "pycodex.tools.request_plugin_install",
        "REQUEST_PLUGIN_INSTALL_SUGGEST_TYPE_KEY",
    ),
    "REQUEST_PLUGIN_INSTALL_TOOL_ID_KEY": (
        "pycodex.tools.request_plugin_install",
        "REQUEST_PLUGIN_INSTALL_TOOL_ID_KEY",
    ),
    "REQUEST_PLUGIN_INSTALL_TOOL_NAME": ("pycodex.tools.tool_discovery", "REQUEST_PLUGIN_INSTALL_TOOL_NAME"),
    "REQUEST_PLUGIN_INSTALL_TOOL_TYPE_KEY": (
        "pycodex.tools.request_plugin_install",
        "REQUEST_PLUGIN_INSTALL_TOOL_TYPE_KEY",
    ),
    "RequestPluginInstallArgs": ("pycodex.tools.request_plugin_install", "RequestPluginInstallArgs"),
    "RequestPluginInstallEntry": ("pycodex.tools.tool_discovery", "RequestPluginInstallEntry"),
    "RequestPluginInstallMeta": ("pycodex.tools.request_plugin_install", "RequestPluginInstallMeta"),
    "RequestPluginInstallResult": ("pycodex.tools.request_plugin_install", "RequestPluginInstallResult"),
    "ResponsesApiNamespace": ("pycodex.tools.responses_api", "ResponsesApiNamespace"),
    "ResponsesApiNamespaceTool": ("pycodex.tools.responses_api", "ResponsesApiNamespaceTool"),
    "ResponsesApiTool": ("pycodex.tools.responses_api", "ResponsesApiTool"),
    "ResponsesApiWebSearchFilters": ("pycodex.tools.tool_spec", "ResponsesApiWebSearchFilters"),
    "ResponsesApiWebSearchUserLocation": ("pycodex.tools.tool_spec", "ResponsesApiWebSearchUserLocation"),
    "ResponsesToolSpec": ("pycodex.tools.tool_spec", "ToolSpec"),
    "ShellCommandBackendConfig": ("pycodex.tools.tool_config", "ShellCommandBackendConfig"),
    "TOOL_SEARCH_DEFAULT_LIMIT": ("pycodex.tools.tool_discovery", "TOOL_SEARCH_DEFAULT_LIMIT"),
    "TOOL_SEARCH_TOOL_NAME": ("pycodex.tools.tool_discovery", "TOOL_SEARCH_TOOL_NAME"),
    "TUI_CLIENT_NAME": ("pycodex.tools.tool_discovery", "TUI_CLIENT_NAME"),
    "ToolCall": ("pycodex.tools.tool_call", "ToolCall"),
    "ToolDefinition": ("pycodex.tools.tool_definition", "ToolDefinition"),
    "ToolEnvironmentMode": ("pycodex.tools.tool_config", "ToolEnvironmentMode"),
    "ToolExecutor": ("pycodex.tools.tool_executor", "ToolExecutor"),
    "ToolExposure": ("pycodex.tools.tool_executor", "ToolExposure"),
    "ToolOutput": ("pycodex.tools.tool_output", "ToolOutput"),
    "ToolPayload": ("pycodex.tools.tool_payload", "ToolPayload"),
    "ToolSearchSourceInfo": ("pycodex.tools.tool_discovery", "ToolSearchSourceInfo"),
    "ToolUserShellType": ("pycodex.tools.tool_config", "ToolUserShellType"),
    "UnifiedExecShellMode": ("pycodex.tools.tool_config", "UnifiedExecShellMode"),
    "ZshForkConfig": ("pycodex.tools.tool_config", "ZshForkConfig"),
    "all_requested_connectors_picked_up": (
        "pycodex.tools.request_plugin_install",
        "all_requested_connectors_picked_up",
    ),
    "augment_tool_spec_for_code_mode": ("pycodex.tools.code_mode", "augment_tool_spec_for_code_mode"),
    "boxed_tool_output": ("pycodex.tools.tool_output", "boxed_tool_output"),
    "build_request_plugin_install_elicitation_request": (
        "pycodex.tools.request_plugin_install",
        "build_request_plugin_install_elicitation_request",
    ),
    "build_request_plugin_install_meta": (
        "pycodex.tools.request_plugin_install",
        "build_request_plugin_install_meta",
    ),
    "can_request_original_image_detail": ("pycodex.tools.original_image_detail", "can_request_original_image_detail"),
    "code_mode_name_for_tool_name": ("pycodex.tools.code_mode", "code_mode_name_for_tool_name"),
    "code_mode_tool_definitions_for_spec": ("pycodex.tools.code_mode", "code_mode_tool_definitions_for_spec"),
    "coalesce_loadable_tool_specs": ("pycodex.tools.responses_api", "coalesce_loadable_tool_specs"),
    "collect_code_mode_exec_prompt_tool_definitions": (
        "pycodex.tools.code_mode",
        "collect_code_mode_exec_prompt_tool_definitions",
    ),
    "collect_code_mode_tool_definitions": ("pycodex.tools.code_mode", "collect_code_mode_tool_definitions"),
    "collect_request_plugin_install_entries": (
        "pycodex.tools.tool_discovery",
        "collect_request_plugin_install_entries",
    ),
    "create_tools_json_for_responses_api": ("pycodex.tools.tool_spec", "create_tools_json_for_responses_api"),
    "default_namespace_description": ("pycodex.tools.responses_api", "default_namespace_description"),
    "dynamic_tool_to_responses_api_tool": ("pycodex.tools.responses_api", "dynamic_tool_to_responses_api_tool"),
    "filter_request_plugin_install_discoverable_tools_for_client": (
        "pycodex.tools.tool_discovery",
        "filter_request_plugin_install_discoverable_tools_for_client",
    ),
    "mcp_call_tool_result_output_schema": ("pycodex.tools.mcp_tool", "mcp_call_tool_result_output_schema"),
    "mcp_tool_to_deferred_responses_api_tool": (
        "pycodex.tools.responses_api",
        "mcp_tool_to_deferred_responses_api_tool",
    ),
    "mcp_tool_to_responses_api_tool": ("pycodex.tools.responses_api", "mcp_tool_to_responses_api_tool"),
    "normalize_output_image_detail": ("pycodex.tools.original_image_detail", "normalize_output_image_detail"),
    "parse_dynamic_tool": ("pycodex.tools.dynamic_tool", "parse_dynamic_tool"),
    "parse_mcp_tool": ("pycodex.tools.mcp_tool", "parse_mcp_tool"),
    "parse_tool_input_schema": ("pycodex.tools.json_schema", "parse_tool_input_schema"),
    "parse_tool_input_schema_without_compaction": (
        "pycodex.tools.json_schema",
        "parse_tool_input_schema_without_compaction",
    ),
    "request_user_input_available_modes": ("pycodex.tools.tool_config", "request_user_input_available_modes"),
    "retain_tail_from_last_n_user_messages": (
        "pycodex.tools.response_history",
        "retain_tail_from_last_n_user_messages",
    ),
    "sanitize_original_image_detail": ("pycodex.tools.original_image_detail", "sanitize_original_image_detail"),
    "shell_command_backend_for_features": ("pycodex.tools.tool_config", "shell_command_backend_for_features"),
    "shell_type_for_model_and_features": ("pycodex.tools.tool_config", "shell_type_for_model_and_features"),
    "telemetry_preview": ("pycodex.tools.tool_output", "telemetry_preview"),
    "tool_definition_to_responses_api_tool": (
        "pycodex.tools.responses_api",
        "tool_definition_to_responses_api_tool",
    ),
    "tool_spec_to_code_mode_tool_definition": ("pycodex.tools.code_mode", "tool_spec_to_code_mode_tool_definition"),
    "truncate_assistant_output_text_to_token_budget": (
        "pycodex.tools.response_history",
        "truncate_assistant_output_text_to_token_budget",
    ),
    "unified_exec_shell_mode_for_session": ("pycodex.tools.tool_config", "unified_exec_shell_mode_for_session"),
    "verified_connector_install_completed": (
        "pycodex.tools.request_plugin_install",
        "verified_connector_install_completed",
    ),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_name, attr_name = _LAZY_EXPORTS[name]
        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ToolName", *_LAZY_EXPORTS]
