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
    DEFAULT_WAIT_YIELD_TIME_MS,
    _ensure_bool,
    _ensure_str,
    _non_negative_int,
    _optional_non_negative_int,
)

@dataclass(frozen=True)
class ExecWaitArgs:
    cell_id: str
    yield_time_ms: int = DEFAULT_WAIT_YIELD_TIME_MS
    max_tokens: int | None = None
    terminate: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", _ensure_str(self.cell_id, "cell_id"))
        object.__setattr__(self, "yield_time_ms", _non_negative_int(self.yield_time_ms))
        object.__setattr__(self, "max_tokens", _optional_non_negative_int(self.max_tokens))
        object.__setattr__(self, "terminate", _ensure_bool(self.terminate, "terminate"))

