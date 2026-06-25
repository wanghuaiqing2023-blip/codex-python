"""Data model for Rust ``codex-tui::ide_context``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="ide_context", source="codex/codex-rs/tui/src/ide_context.rs")


@dataclass(frozen=True)
class Position:
    line: int
    character: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Position":
        return cls(line=int(value["line"]), character=int(value["character"]))


@dataclass(frozen=True)
class Range:
    start: Position
    end: Position

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Range":
        return cls(
            start=Position.from_mapping(_mapping(value["start"])),
            end=Position.from_mapping(_mapping(value["end"])),
        )


@dataclass(frozen=True)
class FileDescriptor:
    label: str
    path: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FileDescriptor":
        return cls(label=str(value["label"]), path=str(value["path"]))


@dataclass(frozen=True)
class ActiveFile:
    descriptor: FileDescriptor
    selection: Range
    active_selection_content: str = ""
    selections: tuple[Range, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ActiveFile":
        selections = tuple(Range.from_mapping(_mapping(item)) for item in value.get("selections", []))
        return cls(
            descriptor=FileDescriptor.from_mapping(value),
            selection=Range.from_mapping(_mapping(value["selection"])),
            active_selection_content=str(value.get("activeSelectionContent", "")),
            selections=selections,
        )


@dataclass(frozen=True)
class IdeContext:
    active_file: ActiveFile | None = None
    open_tabs: tuple[FileDescriptor, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IdeContext":
        active = value.get("activeFile")
        tabs = tuple(FileDescriptor.from_mapping(_mapping(item)) for item in value.get("openTabs", []))
        return cls(
            active_file=ActiveFile.from_mapping(_mapping(active)) if active is not None else None,
            open_tabs=tabs,
        )


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected mapping, got {type(value).__name__}")
    return value


def deserializes_existing_ide_context_shape(value: Mapping[str, Any]) -> IdeContext:
    return IdeContext.from_mapping(value)

__all__ = [
    "ActiveFile",
    "FileDescriptor",
    "IdeContext",
    "Position",
    "RUST_MODULE",
    "Range",
    "deserializes_existing_ide_context_shape",
]
