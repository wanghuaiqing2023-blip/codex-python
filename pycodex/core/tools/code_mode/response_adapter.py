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
    _into_function_call_output_content_item,
)

def into_function_call_output_content_items(
    items: Iterable[FunctionCallOutputContentItem | Mapping[str, JsonValue]],
) -> tuple[FunctionCallOutputContentItem, ...]:
    return tuple(_into_function_call_output_content_item(item) for item in items)

