"""Search-mode state for Rust bottom_pane/mentions_v2/search_mode.rs."""

from __future__ import annotations

from enum import Enum
from typing import Any

from ..._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::mentions_v2::search_mode",
    source="codex/codex-rs/tui/src/bottom_pane/mentions_v2/search_mode.rs",
)


class SearchMode(Enum):
    RESULTS = "Results"
    FILESYSTEM_ONLY = "FilesystemOnly"
    TOOLS = "Tools"

    def previous(self) -> "SearchMode":
        if self is SearchMode.RESULTS:
            return SearchMode.TOOLS
        if self is SearchMode.FILESYSTEM_ONLY:
            return SearchMode.RESULTS
        return SearchMode.FILESYSTEM_ONLY

    def next(self) -> "SearchMode":
        if self is SearchMode.RESULTS:
            return SearchMode.FILESYSTEM_ONLY
        if self is SearchMode.FILESYSTEM_ONLY:
            return SearchMode.TOOLS
        return SearchMode.RESULTS

    def accepts(self, mention_type: Any) -> bool:
        name = _mention_type_name(mention_type)
        if self is SearchMode.RESULTS:
            return True
        if self is SearchMode.FILESYSTEM_ONLY:
            return name in {"File", "Directory"}
        return name in {"Plugin", "Skill"}

    def label(self) -> str:
        if self is SearchMode.RESULTS:
            return "All Results"
        if self is SearchMode.FILESYSTEM_ONLY:
            return "Filesystem Only"
        return "Plugins"


def previous(mode: SearchMode) -> SearchMode:
    return SearchMode(mode).previous()


def next(mode: SearchMode) -> SearchMode:
    return SearchMode(mode).next()


def accepts(mode: SearchMode, mention_type: Any) -> bool:
    return SearchMode(mode).accepts(mention_type)


def label(mode: SearchMode) -> str:
    return SearchMode(mode).label()


def _mention_type_name(value: Any) -> str:
    raw = getattr(value, "value", value)
    if isinstance(raw, str):
        text = raw
    else:
        text = getattr(value, "name", str(value))
    text = text.split(".")[-1]
    normalized = text.replace("_", "").replace("-", "").lower()
    mapping = {
        "plugin": "Plugin",
        "skill": "Skill",
        "file": "File",
        "directory": "Directory",
        "dir": "Directory",
    }
    return mapping.get(normalized, text)


__all__ = ["RUST_MODULE", "SearchMode", "previous", "next", "accepts", "label"]
