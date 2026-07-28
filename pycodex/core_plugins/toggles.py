"""Plugin toggle extraction for ``codex-core-plugins``."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def collect_plugin_enabled_candidates(
    edits: Iterable[tuple[str, Any]],
) -> dict[str, bool]:
    pending_changes: dict[str, bool] = {}
    for key_path, value in edits:
        segments = key_path.split(".")
        if (
            len(segments) == 3
            and segments[0] == "plugins"
            and segments[2] == "enabled"
            and isinstance(value, bool)
        ):
            pending_changes[segments[1]] = value
        elif len(segments) == 2 and segments[0] == "plugins":
            if isinstance(value, dict) and isinstance(value.get("enabled"), bool):
                pending_changes[segments[1]] = value["enabled"]
        elif segments == ["plugins"] and isinstance(value, dict):
            for plugin_id, plugin_value in value.items():
                if (
                    isinstance(plugin_value, dict)
                    and isinstance(plugin_value.get("enabled"), bool)
                ):
                    pending_changes[str(plugin_id)] = plugin_value["enabled"]
    return dict(sorted(pending_changes.items()))


__all__ = ["collect_plugin_enabled_candidates"]
