"""Public interface for the ``codex-extension-api`` Python coordinate."""

from importlib import import_module

from .capabilities import (
    AgentSpawnFuture,
    AgentSpawner,
    ExtensionEventSink,
    NoopExtensionEventSink,
    NoopResponseItemInjector,
    ResponseItemInjectionFuture,
    ResponseItemInjector,
)
from .contributors import (
    ApprovalReviewContributor,
    ConfigContributor,
    ContextContributor,
    PromptFragment,
    PromptSlot,
    ThreadIdleInput,
    ThreadLifecycleContributor,
    ThreadResumeInput,
    ThreadStartInput,
    ThreadStopInput,
    TokenUsageContributor,
    ToolCallOutcome,
    ToolCallSource,
    ToolContributor,
    ToolFinishInput,
    ToolLifecycleContributor,
    ToolLifecycleFuture,
    ToolStartInput,
    TurnAbortInput,
    TurnErrorInput,
    TurnItemContributor,
    TurnLifecycleContributor,
    TurnStartInput,
    TurnStopInput,
)
from .registry import ExtensionRegistry, ExtensionRegistryBuilder, empty_extension_registry
from .state import ExtensionData


_TOOLS_REEXPORTS = {
    "ConversationHistory": ("pycodex.tools.tool_call", "ConversationHistory"),
    "FunctionCallError": ("pycodex.tools", "FunctionCallError"),
    "JsonToolOutput": ("pycodex.tools", "JsonToolOutput"),
    "ResponsesApiTool": ("pycodex.tools", "ResponsesApiTool"),
    "ToolCall": ("pycodex.tools", "ToolCall"),
    "ToolExecutor": ("pycodex.tools", "ToolExecutor"),
    "ToolName": ("pycodex.tools", "ToolName"),
    "ToolOutput": ("pycodex.tools", "ToolOutput"),
    "ToolPayload": ("pycodex.tools", "ToolPayload"),
    "ToolSpec": ("pycodex.tools", "ResponsesToolSpec"),
    "parse_tool_input_schema": ("pycodex.tools", "parse_tool_input_schema"),
    "parse_tool_input_schema_without_compaction": (
        "pycodex.tools",
        "parse_tool_input_schema_without_compaction",
    ),
}


def __getattr__(name: str):
    target = _TOOLS_REEXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


__all__ = [name for name in globals() if not name.startswith("_")] + list(_TOOLS_REEXPORTS)
