"""Project root marker config helpers ported from ``codex-config``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_PROJECT_ROOT_MARKERS = (".git",)
PROJECT_ROOT_MARKERS_ERROR = "project_root_markers must be an array of strings"


def default_project_root_markers() -> list[str]:
    """Return Rust's default project-root marker list."""

    return list(DEFAULT_PROJECT_ROOT_MARKERS)


def project_root_markers_from_config(config: Any) -> list[str] | None:
    """Read ``project_root_markers`` from a merged config mapping.

    Rust accepts an absent key as ``None`` and an empty array as ``Some([])``.
    Any specified non-array or non-string entry is invalid.
    """

    if not isinstance(config, Mapping):
        return None
    if "project_root_markers" not in config:
        return None

    value = config["project_root_markers"]
    if not isinstance(value, list):
        raise ValueError(PROJECT_ROOT_MARKERS_ERROR)
    markers: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise ValueError(PROJECT_ROOT_MARKERS_ERROR)
        markers.append(entry)
    return markers


__all__ = [
    "DEFAULT_PROJECT_ROOT_MARKERS",
    "PROJECT_ROOT_MARKERS_ERROR",
    "default_project_root_markers",
    "project_root_markers_from_config",
]
