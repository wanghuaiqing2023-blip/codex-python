"""Python port of ``codex-hooks::declarations``."""


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

from . import hook_key

@dataclass(frozen=True)
class PluginHookDeclaration:
    key: str
    event_name: HookEventName


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _plugin_key(plugin_id: Any) -> str:
    if hasattr(plugin_id, "as_key"):
        return str(plugin_id.as_key())
    return str(plugin_id)


def plugin_hook_declarations(hook_sources: Sequence[Any]) -> list[PluginHookDeclaration]:
    declarations: list[PluginHookDeclaration] = []
    for source in hook_sources:
        key_source = f"{_plugin_key(_field(source, 'plugin_id'))}:{_field(source, 'source_relative_path', '')}"
        hooks = _field(source, "hooks", {})
        if hasattr(hooks, "into_matcher_groups"):
            groups_by_event = hooks.into_matcher_groups()
        elif isinstance(hooks, Mapping):
            groups_by_event = hooks.items()
        else:
            groups_by_event = ()
        for event_name, groups in groups_by_event:
            event = HookEventName(event_name)
            for group_index, group in enumerate(groups):
                handlers = _field(group, "hooks", ())
                for handler_index, _handler in enumerate(handlers):
                    declarations.append(
                        PluginHookDeclaration(
                            hook_key(key_source, event, group_index, handler_index),
                            event,
                        )
                    )
    return declarations
