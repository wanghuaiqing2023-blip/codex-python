"""Python port of ``codex-hooks::legacy_notify``."""


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

from .types import Hook, HookPayload, HookResult

def legacy_notify_json(payload: HookPayload) -> str:
    event = payload.hook_event.after_agent
    return json.dumps(
        {
            "type": "agent-turn-complete",
            "thread-id": str(event.thread_id),
            "turn-id": event.turn_id,
            "cwd": str(payload.cwd),
            **({"client": payload.client} if payload.client is not None else {}),
            "input-messages": list(event.input_messages),
            "last-assistant-message": event.last_assistant_message,
        },
        separators=(",", ":"),
    )


def notify_hook(argv: Sequence[str]) -> Hook:
    async def run(payload: HookPayload) -> HookResult:
        from .registry import command_from_argv

        command = command_from_argv(argv)
        if command is None:
            return HookResult.Success()
        try:
            subprocess.Popen(
                [*command, legacy_notify_json(payload)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            return HookResult.FailedContinue(exc)
        return HookResult.Success()

    return Hook("legacy_notify", run)
