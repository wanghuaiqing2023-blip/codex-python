"""Python port of ``codex-hooks::types``."""


from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import replace
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import (
    HookCompletedEvent,
    HookEventName,
    HookExecutionMode,
    HookHandlerType,
    HookOutputEntry,
    HookOutputEntryKind,
    HookPromptFragment,
    HookRunStatus,
    HookRunSummary,
    HookScope,
    HookSource,
    HookTrustStatus,
    ThreadId,
    TruncationPolicyConfig,
)
from pycodex.config.hook_config import HookStateToml
from pycodex.config.hook_config import HookEventsToml
from pycodex.config.hook_config import HookHandlerConfig
from pycodex.config.hook_config import HooksFile
from pycodex.config.hook_config import MatcherGroup
from pycodex.config.fingerprint import version_for_toml
from pycodex.config.state import ConfigLayerStackOrdering
from pycodex.utils.output_truncation import approx_token_count
from pycodex.utils.output_truncation import formatted_truncate_text

class HookResultKind(str, Enum):
    SUCCESS = "success"
    FAILED_CONTINUE = "failed_continue"
    FAILED_ABORT = "failed_abort"


@dataclass(frozen=True)
class HookResult:
    kind: HookResultKind
    error: Exception | str | None = None

    @classmethod
    def Success(cls) -> "HookResult":
        return cls(HookResultKind.SUCCESS)

    @classmethod
    def FailedContinue(cls, error: Exception | str) -> "HookResult":
        return cls(HookResultKind.FAILED_CONTINUE, error)

    @classmethod
    def FailedAbort(cls, error: Exception | str) -> "HookResult":
        return cls(HookResultKind.FAILED_ABORT, error)

    def should_abort_operation(self) -> bool:
        return self.kind == HookResultKind.FAILED_ABORT


@dataclass
class HookResponse:
    hook_name: str
    result: HookResult


HookFunc = Callable[["HookPayload"], Awaitable[HookResult] | HookResult]


async def _default_hook_func(_payload: "HookPayload") -> HookResult:
    return HookResult.Success()


@dataclass
class Hook:
    name: str = "default"
    func: HookFunc = _default_hook_func

    async def execute(self, payload: "HookPayload") -> HookResponse:
        result = self.func(payload)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[assignment]
        if not isinstance(result, HookResult):
            raise TypeError("hook func must return HookResult")
        return HookResponse(self.name, result)


@dataclass
class HookEventAfterAgent:
    thread_id: ThreadId | str
    turn_id: str
    input_messages: list[str]
    last_assistant_message: str | None


@dataclass
class HookEvent:
    after_agent: HookEventAfterAgent

    @classmethod
    def AfterAgent(cls, event: HookEventAfterAgent) -> "HookEvent":
        return cls(event)

    def to_mapping(self) -> dict[str, Any]:
        event = self.after_agent
        return {
            "event_type": "after_agent",
            "thread_id": str(event.thread_id),
            "turn_id": event.turn_id,
            "input_messages": list(event.input_messages),
            "last_assistant_message": event.last_assistant_message,
        }


@dataclass
class HookPayload:
    session_id: ThreadId | str
    cwd: Path
    client: str | None
    triggered_at: datetime
    hook_event: HookEvent

    def to_mapping(self) -> dict[str, Any]:
        data = {
            "session_id": str(self.session_id),
            "cwd": str(self.cwd),
            "triggered_at": self.triggered_at.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "hook_event": self.hook_event.to_mapping(),
        }
        if self.client is not None:
            data["client"] = self.client
        return data
