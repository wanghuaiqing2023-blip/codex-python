"""Python port of ``codex-hooks::config_rules``."""


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

from .declarations import _field

def hook_states_from_stack(config_layer_stack: Any | None) -> dict[str, HookStateToml]:
    if config_layer_stack is None:
        return {}
    if hasattr(config_layer_stack, "get_layers"):
        layers = config_layer_stack.get_layers(
            ConfigLayerStackOrdering.LOWEST_PRECEDENCE_FIRST,
            True,
        )
    elif isinstance(config_layer_stack, Sequence):
        layers = config_layer_stack
    else:
        return {}

    states: dict[str, HookStateToml] = {}
    for layer in layers:
        name = _field(layer, "name")
        name_type = _field(name, "type", name)
        if name_type not in ("user", "sessionFlags"):
            continue
        config = _field(layer, "config", {})
        hooks = _field(config, "hooks", {}) if not isinstance(config, Mapping) else config.get("hooks", {})
        state_by_key = _field(hooks, "state", {}) if not isinstance(hooks, Mapping) else hooks.get("state", {})
        if not isinstance(state_by_key, Mapping):
            continue
        for key, state in state_by_key.items():
            key = str(key).strip()
            if not key:
                continue
            try:
                parsed = state if isinstance(state, HookStateToml) else HookStateToml.from_mapping(state)
            except (TypeError, ValueError):
                continue
            effective = states.get(key, HookStateToml())
            states[key] = HookStateToml(
                enabled=parsed.enabled if parsed.enabled is not None else effective.enabled,
                trusted_hash=(
                    parsed.trusted_hash
                    if parsed.trusted_hash is not None
                    else effective.trusted_hash
                ),
            )
    return states
