"""Python port of ``codex-hooks::output_spill``."""


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

HOOK_OUTPUTS_DIR = "hook_outputs"
HOOK_OUTPUT_TOKEN_LIMIT = 2_500

def _hook_output_path(output_dir: Path, thread_id: ThreadId | str) -> Path:
    return output_dir / str(thread_id) / f"{uuid.uuid4()}.txt"


def _spilled_hook_output_preview(text: str, path: Path) -> str:
    footer = f"\n\nFull hook output saved to: {path}"
    preview_limit = max(HOOK_OUTPUT_TOKEN_LIMIT - approx_token_count(footer), 0)
    preview = formatted_truncate_text(
        text,
        TruncationPolicyConfig.tokens(preview_limit),
    )
    return f"{preview}{footer}"


@dataclass
class HookOutputSpiller:
    output_dir: Path = field(
        default_factory=lambda: Path(tempfile.gettempdir()) / HOOK_OUTPUTS_DIR
    )

    @classmethod
    def new(cls) -> "HookOutputSpiller":
        return cls()

    async def maybe_spill_text(self, thread_id: ThreadId | str, text: str) -> str:
        if approx_token_count(text) <= HOOK_OUTPUT_TOKEN_LIMIT:
            return text

        path = _hook_output_path(self.output_dir, thread_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError:
            return formatted_truncate_text(
                text,
                TruncationPolicyConfig.tokens(HOOK_OUTPUT_TOKEN_LIMIT),
            )
        return _spilled_hook_output_preview(text, path)

    async def maybe_spill_texts(
        self,
        thread_id: ThreadId | str,
        texts: Sequence[str],
    ) -> list[str]:
        spilled: list[str] = []
        for text in texts:
            spilled.append(await self.maybe_spill_text(thread_id, text))
        return spilled

    async def maybe_spill_prompt_fragments(
        self,
        thread_id: ThreadId | str,
        fragments: Sequence[HookPromptFragment],
    ) -> list[HookPromptFragment]:
        spilled: list[HookPromptFragment] = []
        for fragment in fragments:
            spilled.append(
                HookPromptFragment(
                    text=await self.maybe_spill_text(thread_id, fragment.text),
                    hook_run_id=fragment.hook_run_id,
                )
            )
        return spilled
