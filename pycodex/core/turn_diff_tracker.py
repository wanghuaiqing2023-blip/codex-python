"""Turn diff tracker ported from ``core/src/turn_diff_tracker.rs``."""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .apply_patch import ApplyPatchAction

JsonValue = Any

ZERO_OID = "0000000000000000000000000000000000000000"
DEV_NULL = "/dev/null"
REGULAR_FILE_MODE = "100644"


@dataclass(frozen=True)
class AppliedPatchFileChange:
    type: str
    content: str | None = None
    overwritten_content: str | None = None
    move_path: Path | None = None
    old_content: str | None = None
    overwritten_move_content: str | None = None
    new_content: str | None = None

    @classmethod
    def add(
        cls,
        content: str,
        overwritten_content: str | None = None,
    ) -> "AppliedPatchFileChange":
        return cls(
            type="add",
            content=content,
            overwritten_content=overwritten_content,
        )

    @classmethod
    def delete(cls, content: str) -> "AppliedPatchFileChange":
        return cls(type="delete", content=content)

    @classmethod
    def update(
        cls,
        old_content: str,
        new_content: str,
        *,
        move_path: str | Path | None = None,
        overwritten_move_content: str | None = None,
    ) -> "AppliedPatchFileChange":
        return cls(
            type="update",
            move_path=Path(move_path) if move_path is not None else None,
            old_content=old_content,
            overwritten_move_content=overwritten_move_content,
            new_content=new_content,
        )


@dataclass(frozen=True)
class AppliedPatchChange:
    path: Path
    change: AppliedPatchFileChange

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            object.__setattr__(self, "path", Path(self.path))


@dataclass
class AppliedPatchDelta:
    changes: tuple[AppliedPatchChange, ...] = ()
    exact: bool = True

    @classmethod
    def new(
        cls,
        changes: tuple[AppliedPatchChange, ...] | list[AppliedPatchChange],
        exact: bool,
    ) -> "AppliedPatchDelta":
        return cls(tuple(changes), exact)

    @classmethod
    def empty(cls) -> "AppliedPatchDelta":
        return cls((), True)

    @classmethod
    def from_apply_patch_action(
        cls,
        action: ApplyPatchAction,
    ) -> "AppliedPatchDelta":
        changes: list[AppliedPatchChange] = []
        exact = True
        for path, change in action.changes.items():
            if change.type == "add":
                applied = AppliedPatchFileChange.add(
                    change.content or "",
                    overwritten_content=change.overwritten_content,
                )
            elif change.type == "delete":
                applied = AppliedPatchFileChange.delete(change.content or "")
            elif change.type == "update":
                if change.old_content is None or change.new_content is None:
                    exact = False
                    old_content = change.old_content or ""
                    new_content = change.new_content or ""
                else:
                    old_content = change.old_content
                    new_content = change.new_content
                applied = AppliedPatchFileChange.update(
                    old_content,
                    new_content,
                    move_path=change.move_path,
                    overwritten_move_content=change.overwritten_move_content,
                )
            else:
                exact = False
                continue
            changes.append(AppliedPatchChange(path=path, change=applied))
        return cls(tuple(changes), exact)

    def is_empty(self) -> bool:
        return not self.changes

    def is_exact(self) -> bool:
        return self.exact

    def append(self, other: "AppliedPatchDelta") -> None:
        self.changes = self.changes + other.changes
        self.exact = self.exact and other.exact


@dataclass
class TurnDiffTracker:
    valid: bool = True
    display_root: Path | None = None
    baseline_by_path: dict[Path, str] | None = None
    current_by_path: dict[Path, str] | None = None
    origin_by_current_path: dict[Path, Path] | None = None

    def __post_init__(self) -> None:
        if self.display_root is not None and not isinstance(self.display_root, Path):
            self.display_root = Path(self.display_root)
        if self.baseline_by_path is None:
            self.baseline_by_path = {}
        if self.current_by_path is None:
            self.current_by_path = {}
        if self.origin_by_current_path is None:
            self.origin_by_current_path = {}

    @classmethod
    def new(cls) -> "TurnDiffTracker":
        return cls()

    @classmethod
    def with_display_root(cls, display_root: str | Path) -> "TurnDiffTracker":
        return cls(display_root=Path(display_root))

    def track_action(self, action: ApplyPatchAction) -> None:
        self.track_delta(AppliedPatchDelta.from_apply_patch_action(action))

    def track_delta(self, delta: AppliedPatchDelta) -> None:
        if not delta.is_exact():
            self.invalidate()
            return
        for change in delta.changes:
            self.apply_change(change)

    def invalidate(self) -> None:
        self.valid = False

    def get_unified_diff(self) -> str | None:
        if not self.valid:
            return None

        rename_pairs = self.rename_pairs()
        paired_destinations = set(rename_pairs.values())
        handled: set[Path] = set()
        paths = sorted(
            set(self.baseline_by_path or {}).union(self.current_by_path or {}),
            key=self.display_path,
        )

        aggregated = ""
        for path in paths:
            if path in handled:
                continue
            handled.add(path)

            if path in paired_destinations:
                continue

            dest = rename_pairs.get(path)
            if dest is not None:
                handled.add(dest)
                diff = self.render_rename_diff(path, dest)
            else:
                diff = self.render_path_diff(path)

            if diff is not None:
                aggregated += diff
                if not aggregated.endswith("\n"):
                    aggregated += "\n"

        return aggregated or None

    def apply_change(self, change: AppliedPatchChange) -> None:
        source_path = change.path
        file_change = change.change
        if file_change.type == "add":
            self.apply_add(
                source_path,
                file_change.content or "",
                file_change.overwritten_content,
            )
        elif file_change.type == "delete":
            self.apply_delete(source_path, file_change.content or "")
        elif file_change.type == "update":
            self.apply_update(
                source_path,
                file_change.move_path,
                file_change.old_content or "",
                file_change.overwritten_move_content,
                file_change.new_content or "",
            )
        else:
            self.invalidate()

    def apply_add(
        self,
        path: Path,
        content: str,
        overwritten_content: str | None = None,
    ) -> None:
        self.origin_by_current_path.pop(path, None)
        if (
            path not in self.current_by_path
            and path not in self.baseline_by_path
            and overwritten_content is not None
        ):
            self.baseline_by_path[path] = overwritten_content
        self.current_by_path[path] = content

    def apply_delete(self, path: Path, content: str) -> None:
        if self.current_by_path.pop(path, None) is None and path not in self.baseline_by_path:
            self.baseline_by_path[path] = content
        self.origin_by_current_path.pop(path, None)

    def apply_update(
        self,
        source_path: Path,
        move_path: Path | None,
        old_content: str,
        overwritten_move_content: str | None,
        new_content: str,
    ) -> None:
        if source_path not in self.current_by_path and source_path not in self.baseline_by_path:
            self.baseline_by_path[source_path] = old_content

        if move_path is not None:
            dest_path = move_path
            if (
                dest_path not in self.current_by_path
                and dest_path not in self.baseline_by_path
                and overwritten_move_content is not None
            ):
                self.baseline_by_path[dest_path] = overwritten_move_content
            origin = self.origin_by_current_path.pop(source_path, source_path)
            self.current_by_path.pop(source_path, None)
            self.current_by_path[dest_path] = new_content
            self.origin_by_current_path.pop(dest_path, None)
            if dest_path != origin:
                self.origin_by_current_path[dest_path] = origin
            return

        self.current_by_path[source_path] = new_content

    def rename_pairs(self) -> dict[Path, Path]:
        pairs: dict[Path, Path] = {}
        for dest_path, origin_path in self.origin_by_current_path.items():
            if (
                dest_path == origin_path
                or origin_path in self.current_by_path
                or dest_path not in self.current_by_path
                or origin_path not in self.baseline_by_path
                or dest_path in self.baseline_by_path
            ):
                continue
            pairs[origin_path] = dest_path
        return pairs

    def render_path_diff(self, path: Path) -> str | None:
        return self.render_diff(
            path,
            self.baseline_by_path.get(path),
            path,
            self.current_by_path.get(path),
        )

    def render_rename_diff(self, source_path: Path, dest_path: Path) -> str | None:
        return self.render_diff(
            source_path,
            self.baseline_by_path.get(source_path),
            dest_path,
            self.current_by_path.get(dest_path),
        )

    def render_diff(
        self,
        left_path: Path,
        left_content: str | None,
        right_path: Path,
        right_content: str | None,
    ) -> str | None:
        if left_content == right_content:
            return None

        left_display = self.display_path(left_path)
        right_display = self.display_path(right_path)
        left_oid = ZERO_OID if left_content is None else git_blob_oid(left_content.encode())
        right_oid = ZERO_OID if right_content is None else git_blob_oid(right_content.encode())

        diff = f"diff --git a/{left_display} b/{right_display}\n"
        if left_content is None and right_content is not None:
            diff += f"new file mode {REGULAR_FILE_MODE}\n"
        elif left_content is not None and right_content is None:
            diff += f"deleted file mode {REGULAR_FILE_MODE}\n"
        elif left_content is None and right_content is None:
            return None

        diff += f"index {left_oid}..{right_oid}\n"
        old_header = f"a/{left_display}" if left_content is not None else DEV_NULL
        new_header = f"b/{right_display}" if right_content is not None else DEV_NULL
        unified = difflib.unified_diff(
            _split_for_unified_diff(left_content or ""),
            _split_for_unified_diff(right_content or ""),
            fromfile=old_header,
            tofile=new_header,
            n=3,
            lineterm="\n",
        )
        diff += "".join(unified)
        return diff

    def display_path(self, path: Path) -> str:
        display = path
        if self.display_root is not None:
            try:
                display = path.relative_to(self.display_root)
            except ValueError:
                display = path
        return str(display).replace("\\", "/")


def git_blob_oid(data: bytes) -> str:
    return git_blob_sha1_hex_bytes(data).hex()


def git_blob_sha1_hex_bytes(data: bytes) -> bytes:
    header = f"blob {len(data)}\0".encode()
    hasher = hashlib.sha1()
    hasher.update(header)
    hasher.update(data)
    return hasher.digest()


def _split_for_unified_diff(value: str) -> list[str]:
    return [
        line if line.endswith("\n") else line + "\n"
        for line in value.splitlines(keepends=True)
    ]


__all__ = [
    "DEV_NULL",
    "REGULAR_FILE_MODE",
    "ZERO_OID",
    "AppliedPatchChange",
    "AppliedPatchDelta",
    "AppliedPatchFileChange",
    "TurnDiffTracker",
    "git_blob_oid",
    "git_blob_sha1_hex_bytes",
]
