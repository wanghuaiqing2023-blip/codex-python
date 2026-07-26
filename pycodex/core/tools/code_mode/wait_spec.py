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
    JsonValue,
    PUBLIC_TOOL_NAME,
    WAIT_TOOL_NAME,
    build_wait_tool_description,
)

def create_wait_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": WAIT_TOOL_NAME,
        "description": (
            f"Waits on a yielded `{PUBLIC_TOOL_NAME}` cell and returns new output or completion.\n"
            f"{build_wait_tool_description().strip()}"
        ),
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "cell_id": {
                    "type": "string",
                    "description": "Identifier of the running exec cell.",
                },
                "yield_time_ms": {
                    "type": "number",
                    "description": (
                        "How long to wait (in milliseconds) for more output before yielding again."
                    ),
                },
                "max_tokens": {
                    "type": "number",
                    "description": "Maximum number of output tokens to return for this wait call.",
                },
                "terminate": {
                    "type": "boolean",
                    "description": "Whether to terminate the running exec cell.",
                },
            },
            "required": ["cell_id"],
            "additionalProperties": False,
        },
    }

