"""Rust-aligned owner for ``codex-rollout-trace::payload``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

RawPayloadId = str

class RawPayloadKind(str, Enum):
    INFERENCE_REQUEST = "inference_request"
    INFERENCE_RESPONSE = "inference_response"
    COMPACTION_REQUEST = "compaction_request"
    COMPACTION_CHECKPOINT = "compaction_checkpoint"
    COMPACTION_RESPONSE = "compaction_response"
    TOOL_INVOCATION = "tool_invocation"
    TOOL_RESULT = "tool_result"
    TOOL_RUNTIME_EVENT = "tool_runtime_event"
    TERMINAL_RUNTIME_EVENT = "terminal_runtime_event"
    PROTOCOL_EVENT = "protocol_event"
    SESSION_METADATA = "session_metadata"
    AGENT_RESULT = "agent_result"

@dataclass(frozen=True)
class RawPayloadRef:
    raw_payload_id: RawPayloadId
    kind: RawPayloadKind
    path: str
