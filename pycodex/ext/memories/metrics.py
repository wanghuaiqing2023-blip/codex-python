"""Metrics helpers from Rust ``memories/src/metrics.rs``."""

from __future__ import annotations

from typing import Any

MEMORIES_TOOL_CALL_METRIC = "codex.memories.tool.call"
MEMORY_TOOLS_NAMESPACE = "memories"


def record_tool_call(
    metrics_client: Any | None,
    operation: str,
    scope: str,
    success: bool,
    truncated: str,
) -> None:
    if metrics_client is None:
        return
    attributes = (
        ("tool", f"{MEMORY_TOOLS_NAMESPACE}/{operation}"),
        ("operation", operation),
        ("scope", scope),
        ("status", status_tag(success)),
        ("truncated", truncated),
    )
    metrics_client.counter(MEMORIES_TOOL_CALL_METRIC, 1, attributes)


def scope_from_path(path: str) -> str:
    normalized = path.strip("/").removeprefix("./")
    if not normalized:
        return "root"
    if normalized == "MEMORY.md":
        return "memory_md"
    if normalized == "memory_summary.md":
        return "memory_summary"
    if normalized == "raw_memories.md":
        return "raw_memories"
    if normalized == "rollout_summaries" or normalized.startswith(
        "rollout_summaries/"
    ):
        return "rollout_summaries"
    if normalized == "skills" or normalized.startswith("skills/"):
        return "skills"
    if normalized == "extensions/ad_hoc/notes" or normalized.startswith(
        "extensions/ad_hoc/notes/"
    ):
        return "ad_hoc_notes"
    return "other"


def scope_from_optional_path(path: str | None, default: str) -> str:
    return default if path is None else scope_from_path(path)


def truncated_tag(truncated: bool | None) -> str:
    if truncated is None:
        return "unknown"
    return "true" if truncated else "false"


def status_tag(success: bool) -> str:
    return "succeeded" if success else "failed"


__all__ = [
    "MEMORIES_TOOL_CALL_METRIC",
    "record_tool_call",
    "scope_from_optional_path",
    "scope_from_path",
    "status_tag",
    "truncated_tag",
]
