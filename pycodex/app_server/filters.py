"""Thread source filters ported from ``codex-app-server/src/filters.rs``."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pycodex.app_server_protocol import ThreadSourceKind
from pycodex.core.rollout import INTERACTIVE_SESSION_SOURCES
from pycodex.protocol import SessionSource, SubAgentSource

_POST_FILTER_REQUIRED_KINDS = frozenset(
    {
        ThreadSourceKind.EXEC,
        ThreadSourceKind.APP_SERVER,
        ThreadSourceKind.SUB_AGENT,
        ThreadSourceKind.SUB_AGENT_REVIEW,
        ThreadSourceKind.SUB_AGENT_COMPACT,
        ThreadSourceKind.SUB_AGENT_THREAD_SPAWN,
        ThreadSourceKind.SUB_AGENT_OTHER,
        ThreadSourceKind.UNKNOWN,
    }
)


@dataclass(frozen=True)
class SourceFiltersProjection:
    allowed_sources: tuple[SessionSource, ...]
    post_filter: tuple[ThreadSourceKind, ...] | None


def compute_source_filters(source_kinds: Iterable[ThreadSourceKind | str] | None) -> SourceFiltersProjection:
    """Mirror Rust's source-filter split between rollout query and post-filter."""

    if source_kinds is None:
        return SourceFiltersProjection(tuple(INTERACTIVE_SESSION_SOURCES), None)

    kinds = tuple(_thread_source_kind(kind) for kind in source_kinds)
    if not kinds:
        return SourceFiltersProjection(tuple(INTERACTIVE_SESSION_SOURCES), None)

    if any(kind in _POST_FILTER_REQUIRED_KINDS for kind in kinds):
        return SourceFiltersProjection((), kinds)

    allowed_sources = tuple(
        source
        for source in (_interactive_source_for_kind(kind) for kind in kinds)
        if source is not None
    )
    return SourceFiltersProjection(allowed_sources, kinds)


def source_kind_matches(source: SessionSource | Any, source_filter: Iterable[ThreadSourceKind | str]) -> bool:
    source = _session_source(source)
    return any(_source_kind_matches_one(source, _thread_source_kind(kind)) for kind in source_filter)


def _thread_source_kind(value: ThreadSourceKind | str) -> ThreadSourceKind:
    if isinstance(value, ThreadSourceKind):
        return value
    return ThreadSourceKind.parse(value)


def _session_source(value: SessionSource | Any) -> SessionSource:
    if isinstance(value, SessionSource):
        return value
    if isinstance(value, str):
        return SessionSource.from_startup_arg(value)
    raise TypeError("source must be a SessionSource or startup source string")


def _interactive_source_for_kind(kind: ThreadSourceKind) -> SessionSource | None:
    if kind == ThreadSourceKind.CLI:
        return SessionSource.cli()
    if kind == ThreadSourceKind.VSCODE:
        return SessionSource.vscode()
    return None


def _source_kind_matches_one(source: SessionSource, kind: ThreadSourceKind) -> bool:
    if kind == ThreadSourceKind.CLI:
        return source.type == "cli"
    if kind == ThreadSourceKind.VSCODE:
        return source.type == "vscode"
    if kind == ThreadSourceKind.EXEC:
        return source.type == "exec"
    if kind == ThreadSourceKind.APP_SERVER:
        return source.type == "mcp"
    if kind == ThreadSourceKind.SUB_AGENT:
        return source.type == "subagent"
    if kind == ThreadSourceKind.UNKNOWN:
        return source.type == "unknown"

    subagent_source = source.subagent_source if source.type == "subagent" else None
    if not isinstance(subagent_source, SubAgentSource):
        return False
    if kind == ThreadSourceKind.SUB_AGENT_REVIEW:
        return subagent_source.type == "review"
    if kind == ThreadSourceKind.SUB_AGENT_COMPACT:
        return subagent_source.type == "compact"
    if kind == ThreadSourceKind.SUB_AGENT_THREAD_SPAWN:
        return subagent_source.type == "thread_spawn"
    if kind == ThreadSourceKind.SUB_AGENT_OTHER:
        return subagent_source.type == "other"
    return False


__all__ = [
    "SourceFiltersProjection",
    "compute_source_filters",
    "source_kind_matches",
]
