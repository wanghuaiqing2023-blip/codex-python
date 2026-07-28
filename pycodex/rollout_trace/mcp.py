"""Rust-aligned owner for ``codex-rollout-trace::mcp``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.rollout_trace.model import *
from pycodex.rollout_trace.payload import *
from pycodex.rollout_trace.raw_event import *
from pycodex.rollout_trace.bundle import *
from pycodex.rollout_trace.writer import TraceWriter, _NoOpTraceContext, _jsonable, _unix_time_ms

MCP_CALL_ID_META_KEY = "codex_bridge_mcp_call_id"

@dataclass
class McpCallTraceContext:
    mcp_call_id: McpCallId | None = None

    @classmethod
    def disabled(cls) -> "McpCallTraceContext":
        return cls(None)

    @classmethod
    def enabled(cls, mcp_call_id: McpCallId) -> "McpCallTraceContext":
        return cls(mcp_call_id)

    def add_request_meta(self, meta: dict[str, Any] | None) -> dict[str, Any] | None:
        if self.mcp_call_id is None:
            return meta
        if meta is None:
            meta = {}
        if not isinstance(meta, dict):
            return meta
        return {**meta, MCP_CALL_ID_META_KEY: self.mcp_call_id}

from pycodex.rollout_trace.model import McpCallId
