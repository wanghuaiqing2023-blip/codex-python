"""Code-mode tool definition helpers ported from Codex core."""

from __future__ import annotations

import copy
import json
import math
import time
import uuid
from collections.abc import Iterable, Mapping
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pycodex.protocol import FunctionCallOutputContentItem, ImageDetail, ToolName
from pycodex.protocol import DEFAULT_IMAGE_DETAIL

JsonValue = Any
CellIdAllocator = Callable[[], str]



from . import (
    CodeModeToolDefinition,
    JsonValue,
    PUBLIC_TOOL_NAME,
    ToolNamespaceDescription,
    _coerce_code_mode_tool_definition,
    build_exec_tool_description,
)

CODE_MODE_FREEFORM_GRAMMAR = """
start: pragma_source | plain_source
pragma_source: PRAGMA_LINE NEWLINE SOURCE
plain_source: SOURCE

PRAGMA_LINE: /[ \\t]*\\/\\/ @exec:[^\\r\\n]*/
NEWLINE: /\\r?\\n/
SOURCE: /[\\s\\S]+/
"""

def create_code_mode_tool(
    enabled_tools: Iterable[CodeModeToolDefinition | Mapping[str, JsonValue]] = (),
    namespace_descriptions: Mapping[str, ToolNamespaceDescription | Mapping[str, str]] | None = None,
    *,
    code_mode_only: bool,
    deferred_tools_available: bool,
) -> Any:
    from pycodex.core.tools.hosted_spec import FreeformToolFormat, ToolSpec

    definitions = tuple(_coerce_code_mode_tool_definition(tool) for tool in enabled_tools)
    return ToolSpec.freeform(
        name=PUBLIC_TOOL_NAME,
        description=build_exec_tool_description(
            definitions,
            namespace_descriptions,
            code_mode_only=code_mode_only,
            deferred_tools_available=deferred_tools_available,
        ),
        format=FreeformToolFormat.grammar(
            syntax="lark",
            definition=CODE_MODE_FREEFORM_GRAMMAR,
        ),
    )

