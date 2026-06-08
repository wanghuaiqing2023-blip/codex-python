"""Core mention helper facade.

Rust source:
- ``codex/codex-rs/core/src/lib.rs`` inline ``mentions`` module
- ``codex/codex-rs/core/src/plugins/mentions.rs``
"""

from __future__ import annotations

from .plugins.mentions import (
    build_connector_slug_counts,
    collect_explicit_app_ids,
    collect_explicit_plugin_mentions,
    collect_tool_mentions_from_messages,
)
from .skills import build_skill_name_counts


__all__ = [
    "build_connector_slug_counts",
    "build_skill_name_counts",
    "collect_explicit_app_ids",
    "collect_explicit_plugin_mentions",
    "collect_tool_mentions_from_messages",
]
