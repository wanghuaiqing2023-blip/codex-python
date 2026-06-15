"""Minimal file-change model used by TUI diff rendering and approval previews.

Upstream source: ``codex/codex-rs/tui/src/diff_model.rs``.
Rust represents this as a serde-tagged enum with ``type`` values
``add``, ``delete``, and ``update``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="diff_model",
    source="codex/codex-rs/tui/src/diff_model.rs",
    status="complete",
)


@dataclass(frozen=True)
class FileChange:
    """Semantic equivalent of Rust ``diff_model::FileChange``."""

    type: str
    content: Optional[str] = None
    unified_diff: Optional[str] = None
    move_path: Optional[Path] = None

    @classmethod
    def add(cls, content: str) -> "FileChange":
        return cls(type="add", content=content)

    @classmethod
    def delete(cls, content: str) -> "FileChange":
        return cls(type="delete", content=content)

    @classmethod
    def update(cls, unified_diff: str, move_path: Optional[Union[str, Path]] = None) -> "FileChange":
        path = None if move_path is None else Path(move_path)
        return cls(type="update", unified_diff=unified_diff, move_path=path)

    def is_add(self) -> bool:
        return self.type == "add"

    def is_delete(self) -> bool:
        return self.type == "delete"

    def is_update(self) -> bool:
        return self.type == "update"

    def to_dict(self) -> Dict[str, Any]:
        if self.type == "add":
            if self.content is None:
                raise ValueError("add FileChange requires content")
            return {"type": "add", "content": self.content}
        if self.type == "delete":
            if self.content is None:
                raise ValueError("delete FileChange requires content")
            return {"type": "delete", "content": self.content}
        if self.type == "update":
            if self.unified_diff is None:
                raise ValueError("update FileChange requires unified_diff")
            return {
                "type": "update",
                "unified_diff": self.unified_diff,
                "move_path": None if self.move_path is None else self.move_path.as_posix(),
            }
        raise ValueError(f"unknown FileChange type: {self.type!r}")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FileChange":
        kind = value.get("type")
        if kind == "add":
            return cls.add(_required_str(value, "content"))
        if kind == "delete":
            return cls.delete(_required_str(value, "content"))
        if kind == "update":
            move_path = value.get("move_path")
            if move_path is not None and not isinstance(move_path, str):
                raise TypeError("move_path must be a string or None")
            return cls.update(_required_str(value, "unified_diff"), move_path)
        raise ValueError(f"unknown FileChange type: {kind!r}")


def _required_str(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string")
    return item


__all__ = [
    "FileChange",
    "RUST_MODULE",
]
