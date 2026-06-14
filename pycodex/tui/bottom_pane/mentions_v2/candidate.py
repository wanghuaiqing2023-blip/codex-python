"""Candidate DTOs for Rust bottom_pane/mentions_v2/candidate.rs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from ..._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::mentions_v2::candidate",
    source="codex/codex-rs/tui/src/bottom_pane/mentions_v2/candidate.rs",
)

TAG_WIDTH = len("Plugin")


@dataclass(frozen=True)
class SemanticSpan:
    content: str
    style: tuple[str, ...] = ()


@dataclass(frozen=True)
class Selection:
    kind: str
    file: Path | None = None
    insert_text: str | None = None
    path: str | None = None

    @classmethod
    def File(cls, path: str | Path) -> "Selection":
        return cls(kind="File", file=Path(path))

    @classmethod
    def Tool(cls, insert_text: str, path: str | None = None) -> "Selection":
        return cls(kind="Tool", insert_text=insert_text, path=path)


class MentionType(Enum):
    PLUGIN = "Plugin"
    SKILL = "Skill"
    FILE = "File"
    DIRECTORY = "Directory"

    def is_filesystem(self) -> bool:
        return self in {MentionType.FILE, MentionType.DIRECTORY}

    def label(self) -> str:
        if self is MentionType.DIRECTORY:
            return "Dir"
        return self.value

    def span(self, base_style: Any = None) -> SemanticSpan:
        style = _style_tuple(base_style)
        if self is MentionType.PLUGIN:
            style = (*style, "magenta")
        elif self is MentionType.SKILL:
            style = (*style, "dim")
        elif self is MentionType.FILE:
            style = (*style, "cyan")
        return SemanticSpan(content=f"{self.label():<{TAG_WIDTH}}", style=style)


@dataclass
class Candidate:
    display_name: str
    description: str | None
    search_terms: list[str]
    mention_type: MentionType
    selection: Selection

    def to_result(self, match_indices: list[int] | None, score: int) -> "SearchResult":
        return SearchResult(
            display_name=str(self.display_name),
            description=None if self.description is None else str(self.description),
            mention_type=self.mention_type,
            selection=replace(self.selection),
            match_indices=None if match_indices is None else list(match_indices),
            score=int(score),
        )


@dataclass
class SearchResult:
    display_name: str
    description: str | None
    mention_type: MentionType
    selection: Selection
    match_indices: list[int] | None
    score: int


def is_filesystem(mention_type: MentionType) -> bool:
    return MentionType(mention_type).is_filesystem()


def span(mention_type: MentionType, base_style: Any = None) -> SemanticSpan:
    return MentionType(mention_type).span(base_style)


def label(mention_type: MentionType) -> str:
    return MentionType(mention_type).label()


def to_result(candidate: Candidate, match_indices: list[int] | None, score: int) -> SearchResult:
    return candidate.to_result(match_indices, score)


def _style_tuple(base_style: Any) -> tuple[str, ...]:
    if base_style is None:
        return ()
    if isinstance(base_style, str):
        return (base_style,)
    if isinstance(base_style, tuple):
        return tuple(str(part) for part in base_style)
    if isinstance(base_style, list):
        return tuple(str(part) for part in base_style)
    modifiers = getattr(base_style, "modifiers", None)
    if modifiers is not None:
        return tuple(str(part) for part in modifiers)
    return (str(base_style),)


__all__ = [
    "Candidate",
    "MentionType",
    "RUST_MODULE",
    "SearchResult",
    "Selection",
    "SemanticSpan",
    "TAG_WIDTH",
    "is_filesystem",
    "label",
    "span",
    "to_result",
]
