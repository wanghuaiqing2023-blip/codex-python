"""Public facade for Rust ``codex-code-mode``.

Rust source:
- ``codex/codex-rs/code-mode/src/lib.rs``
- ``codex/codex-rs/code-mode/src/description.rs``
- ``codex/codex-rs/code-mode/src/response.rs``

The V8-backed runtime remains owned by ``pycodex.core.tools.code_mode``'s
dependency-light service shim; this crate package re-exports the Rust public
surface that is useful to Python callers without adding a V8 dependency.
"""

from __future__ import annotations

from pycodex.core.tools.code_mode import CODE_MODE_PRAGMA_PREFIX
from pycodex.core.tools.code_mode import DEFAULT_EXEC_YIELD_TIME_MS
from pycodex.core.tools.code_mode import DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL
from pycodex.core.tools.code_mode import DEFAULT_WAIT_YIELD_TIME_MS
from pycodex.core.tools.code_mode import CodeModeNestedToolCall
from pycodex.core.tools.code_mode import CodeModeService
from pycodex.core.tools.code_mode import CodeModeToolDefinition
from pycodex.core.tools.code_mode import CodeModeToolKind
from pycodex.core.tools.code_mode import ExecuteRequest
from pycodex.core.tools.code_mode import ExecuteToPendingOutcome
from pycodex.core.tools.code_mode import RuntimeResponse
from pycodex.core.tools.code_mode import ToolNamespaceDescription
from pycodex.core.tools.code_mode import WaitOutcome
from pycodex.core.tools.code_mode import WaitRequest
from pycodex.core.tools.code_mode import WaitToPendingOutcome
from pycodex.core.tools.code_mode import WaitToPendingRequest
from pycodex.core.tools.code_mode import augment_tool_definition
from pycodex.core.tools.code_mode import build_exec_tool_description
from pycodex.core.tools.code_mode import build_wait_tool_description
from pycodex.core.tools.code_mode import enabled_tool_metadata
from pycodex.core.tools.code_mode import is_code_mode_nested_tool
from pycodex.core.tools.code_mode import normalize_code_mode_identifier
from pycodex.core.tools.code_mode import parse_exec_source
from pycodex.core.tools.code_mode import render_code_mode_sample
from pycodex.core.tools.code_mode import render_json_schema_to_typescript
from pycodex.protocol import DEFAULT_IMAGE_DETAIL
from pycodex.protocol import FunctionCallOutputContentItem
from pycodex.protocol import ImageDetail


PUBLIC_TOOL_NAME = "exec"
WAIT_TOOL_NAME = "wait"

# Rust names the description struct ``ToolDefinition``.  The core package uses
# a more explicit Python name because it lives beside other tool definitions.
ToolDefinition = CodeModeToolDefinition


class CodeModeTurnHost:
    """Python marker for Rust ``CodeModeTurnHost``.

    The concrete V8 worker bridge is intentionally not ported here.  Core tests
    exercise the dependency-light service callback boundary instead.
    """


class CodeModeTurnWorker:
    """Python marker for Rust ``CodeModeTurnWorker`` runtime ownership."""


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
