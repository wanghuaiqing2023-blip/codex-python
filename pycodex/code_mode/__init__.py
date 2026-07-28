"""Public surface ported from ``codex-rs/code-mode/src/lib.rs``."""

from __future__ import annotations

PUBLIC_TOOL_NAME = "exec"
WAIT_TOOL_NAME = "wait"

from .description import CODE_MODE_PRAGMA_PREFIX
from .description import CodeModeToolDefinition
from .description import CodeModeToolKind
from .description import ToolNamespaceDescription
from .description import augment_tool_definition
from .description import build_exec_tool_description
from .description import build_wait_tool_description
from .description import enabled_tool_metadata
from .description import is_code_mode_nested_tool
from .description import normalize_code_mode_identifier
from .description import parse_exec_source
from .description import render_code_mode_sample
from .description import render_json_schema_to_typescript
from .response import DEFAULT_IMAGE_DETAIL
from .response import FunctionCallOutputContentItem
from .response import ImageDetail
from .runtime import DEFAULT_EXEC_YIELD_TIME_MS
from .runtime import DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL
from .runtime import DEFAULT_WAIT_YIELD_TIME_MS
from .runtime import CodeModeNestedToolCall
from .runtime import ExecuteRequest
from .runtime import ExecuteToPendingOutcome
from .runtime import RuntimeResponse
from .runtime import WaitOutcome
from .runtime import WaitRequest
from .runtime import WaitToPendingOutcome
from .runtime import WaitToPendingRequest
from .service import CodeModeService
from .service import CodeModeTurnHost
from .service import CodeModeTurnWorker

# Rust calls this type ``ToolDefinition``; Core keeps the explicit Python name
# when several tool-definition families are in scope.
ToolDefinition = CodeModeToolDefinition

__all__ = [
    "CODE_MODE_PRAGMA_PREFIX",
    "DEFAULT_EXEC_YIELD_TIME_MS",
    "DEFAULT_IMAGE_DETAIL",
    "DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL",
    "DEFAULT_WAIT_YIELD_TIME_MS",
    "CodeModeNestedToolCall",
    "CodeModeService",
    "CodeModeToolKind",
    "CodeModeTurnHost",
    "CodeModeTurnWorker",
    "ExecuteRequest",
    "ExecuteToPendingOutcome",
    "FunctionCallOutputContentItem",
    "ImageDetail",
    "PUBLIC_TOOL_NAME",
    "RuntimeResponse",
    "ToolDefinition",
    "ToolNamespaceDescription",
    "WAIT_TOOL_NAME",
    "WaitOutcome",
    "WaitRequest",
    "WaitToPendingOutcome",
    "WaitToPendingRequest",
    "augment_tool_definition",
    "build_exec_tool_description",
    "build_wait_tool_description",
    "enabled_tool_metadata",
    "is_code_mode_nested_tool",
    "normalize_code_mode_identifier",
    "parse_exec_source",
    "render_code_mode_sample",
    "render_json_schema_to_typescript",
]
