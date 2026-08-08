"""Rust-aligned root module for ``codex-apply-patch``."""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

JsonValue = Any

CODEX_CORE_APPLY_PATCH_ARG1 = "--codex-run-as-apply-patch"

APPLY_PATCH_TOOL_INSTRUCTIONS = '## `apply_patch`\n\nUse the `apply_patch` shell command to edit files.\nYour patch language is a stripped‑down, file‑oriented diff format designed to be easy to parse and safe to apply. You can think of it as a high‑level envelope:\n\n*** Begin Patch\n[ one or more file sections ]\n*** End Patch\n\nWithin that envelope, you get a sequence of file operations.\nYou MUST include a header to specify the action you are taking.\nEach operation starts with one of three headers:\n\n*** Add File: <path> - create a new file. Every following line is a + line (the initial contents).\n*** Delete File: <path> - remove an existing file. Nothing follows.\n*** Update File: <path> - patch an existing file in place (optionally with a rename).\n\nMay be immediately followed by *** Move to: <new path> if you want to rename the file.\nThen one or more “hunks”, each introduced by @@ (optionally followed by a hunk header).\nWithin a hunk each line starts with:\n\nFor instructions on [context_before] and [context_after]:\n- By default, show 3 lines of code immediately above and 3 lines immediately below each change. If a change is within 3 lines of a previous change, do NOT duplicate the first change’s [context_after] lines in the second change’s [context_before] lines.\n- If 3 lines of context is insufficient to uniquely identify the snippet of code within the file, use the @@ operator to indicate the class or function to which the snippet belongs. For instance, we might have:\n@@ class BaseClass\n[3 lines of pre-context]\n- [old_code]\n+ [new_code]\n[3 lines of post-context]\n\n- If a code block is repeated so many times in a class or function such that even a single `@@` statement and 3 lines of context cannot uniquely identify the snippet of code, you can use multiple `@@` statements to jump to the right context. For instance:\n\n@@ class BaseClass\n@@ \t def method():\n[3 lines of pre-context]\n- [old_code]\n+ [new_code]\n[3 lines of post-context]\n\nThe full grammar definition is below:\nPatch := Begin { FileOp } End\nBegin := "*** Begin Patch" NEWLINE\nEnd := "*** End Patch" NEWLINE\nFileOp := AddFile | DeleteFile | UpdateFile\nAddFile := "*** Add File: " path NEWLINE { "+" line NEWLINE }\nDeleteFile := "*** Delete File: " path NEWLINE\nUpdateFile := "*** Update File: " path NEWLINE [ MoveTo ] { Hunk }\nMoveTo := "*** Move to: " newPath NEWLINE\nHunk := "@@" [ header ] NEWLINE { HunkLine } [ "*** End of File" NEWLINE ]\nHunkLine := (" " | "-" | "+") text NEWLINE\n\nA full patch can combine several operations:\n\n*** Begin Patch\n*** Add File: hello.txt\n+Hello world\n*** Update File: src/app.py\n*** Move to: src/main.py\n@@ def greet():\n-print("Hi")\n+print("Hello, world!")\n*** Delete File: obsolete.txt\n*** End Patch\n\nIt is important to remember:\n\n- You must include a header with your intended action (Add/Delete/Update)\n- You must prefix new lines with `+` even when creating a new file\n- File references can only be relative, NEVER ABSOLUTE.\n\nYou can invoke apply_patch like:\n\n```\nshell {"command":["apply_patch","*** Begin Patch\\n*** Add File: hello.txt\\n+Hello, world!\\n*** End Patch\\n"]}\n```\n'

@dataclass(frozen=True)
class ApplyPatchError(Exception):
    kind: str
    message: str
    source: BaseException | None = field(default=None, compare=False)

    @classmethod
    def parse_error(cls, error: ApplyPatchParseError) -> "ApplyPatchError":
        return cls(kind="parse_error", message=str(error), source=error)

    @classmethod
    def io_error(cls, context: str, source: OSError) -> "ApplyPatchError":
        return cls(kind="io_error", message=f"{context}: {source}", source=source)

    @classmethod
    def compute_replacements(cls, message: str) -> "ApplyPatchError":
        return cls(kind="compute_replacements", message=message)

    @classmethod
    def implicit_invocation(cls) -> "ApplyPatchError":
        return cls(
            kind="implicit_invocation",
            message=(
                "patch detected without explicit call to apply_patch. Rerun as "
                '[\"apply_patch\", \"<patch>\"]'
            ),
        )

    def __str__(self) -> str:
        return self.message

@dataclass(frozen=True)
class ApplyPatchArgs:
    patch: str
    hunks: tuple[Hunk, ...]
    workdir: str | None = None
    environment_id: str | None = None

    def __post_init__(self) -> None:
        _ensure_str(self.patch, "patch")
        object.__setattr__(self, "hunks", tuple(self.hunks))
        if not all(isinstance(hunk, Hunk) for hunk in self.hunks):
            raise TypeError("hunks must contain only Hunk values")
        if self.workdir is not None:
            _ensure_str(self.workdir, "workdir")
        if self.environment_id is not None:
            _ensure_str(self.environment_id, "environment_id")

@dataclass(frozen=True)
class MaybeApplyPatchVerified:
    type: str
    body: "ApplyPatchAction" | None = None
    error: ApplyPatchError | str | None = None

    @classmethod
    def body_result(cls, body: "ApplyPatchAction") -> "MaybeApplyPatchVerified":
        return cls(type="body", body=body)

    @classmethod
    def shell_parse_error(cls, error: str) -> "MaybeApplyPatchVerified":
        return cls(type="shell_parse_error", error=error)

    @classmethod
    def correctness_error(cls, error: ApplyPatchError) -> "MaybeApplyPatchVerified":
        return cls(type="correctness_error", error=error)

    @classmethod
    def not_apply_patch(cls) -> "MaybeApplyPatchVerified":
        return cls(type="not_apply_patch")

@dataclass(frozen=True)
class ApplyPatchFileChange:
    type: str
    content: str | None = None
    unified_diff: str | None = None
    move_path: Path | None = None
    new_content: str | None = None
    overwritten_content: str | None = None
    old_content: str | None = None
    overwritten_move_content: str | None = None

    def __post_init__(self) -> None:
        if self.type not in {"add", "delete", "update"}:
            raise ValueError("unknown apply_patch file change type")
        if self.type == "add":
            _ensure_str(self.content, "content")
            _ensure_absent(self.unified_diff, "unified_diff")
            _ensure_absent(self.move_path, "move_path")
            _ensure_absent(self.old_content, "old_content")
            _ensure_absent(self.overwritten_move_content, "overwritten_move_content")
            if self.new_content is not None:
                _ensure_str(self.new_content, "new_content")
            if self.overwritten_content is not None:
                _ensure_str(self.overwritten_content, "overwritten_content")
            return
        if self.type == "delete":
            _ensure_str(self.content, "content")
            _ensure_absent(self.unified_diff, "unified_diff")
            _ensure_absent(self.move_path, "move_path")
            _ensure_absent(self.new_content, "new_content")
            _ensure_absent(self.overwritten_content, "overwritten_content")
            _ensure_absent(self.old_content, "old_content")
            _ensure_absent(self.overwritten_move_content, "overwritten_move_content")
            return
        _ensure_absent(self.content, "content")
        _ensure_str(self.unified_diff, "unified_diff")
        if self.move_path is not None and not isinstance(self.move_path, Path):
            raise TypeError("move_path must be a Path")
        if self.new_content is not None:
            _ensure_str(self.new_content, "new_content")
        if self.old_content is not None:
            _ensure_str(self.old_content, "old_content")
        if self.overwritten_move_content is not None:
            _ensure_str(self.overwritten_move_content, "overwritten_move_content")
        _ensure_absent(self.overwritten_content, "overwritten_content")

    @classmethod
    def add(
        cls,
        content: str,
        *,
        new_content: str | None = None,
        overwritten_content: str | None = None,
    ) -> "ApplyPatchFileChange":
        _ensure_str(content, "content")
        return cls(
            type="add",
            content=content,
            new_content=new_content,
            overwritten_content=overwritten_content,
        )

    @classmethod
    def delete(cls, content: str) -> "ApplyPatchFileChange":
        _ensure_str(content, "content")
        return cls(type="delete", content=content)

    @classmethod
    def update(
        cls,
        unified_diff: str,
        *,
        move_path: str | Path | None = None,
        new_content: str | None = None,
        old_content: str | None = None,
        overwritten_move_content: str | None = None,
    ) -> "ApplyPatchFileChange":
        _ensure_str(unified_diff, "unified_diff")
        if move_path is not None:
            _ensure_pathlike(move_path, "move_path")
        return cls(
            type="update",
            unified_diff=unified_diff,
            move_path=Path(move_path) if move_path is not None else None,
            new_content=new_content,
            old_content=old_content,
            overwritten_move_content=overwritten_move_content,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ApplyPatchFileChange":
        if not isinstance(value, Mapping):
            raise TypeError("value must be a mapping")
        change_type = _required_str(value, "type")
        if change_type == "add":
            return cls.add(
                _required_str(value, "content"),
                new_content=_optional_str(value, "new_content"),
                overwritten_content=_optional_str(value, "overwritten_content"),
            )
        if change_type == "delete":
            return cls.delete(_required_str(value, "content"))
        if change_type == "update":
            move_path = _optional_str(value, "move_path")
            return cls.update(
                _required_str(value, "unified_diff"),
                move_path=move_path,
                new_content=_optional_str(value, "new_content"),
                old_content=_optional_str(value, "old_content"),
                overwritten_move_content=_optional_str(value, "overwritten_move_content"),
            )
        raise ValueError(f"unknown apply_patch file change type: {change_type}")

@dataclass(frozen=True)
class ApplyPatchAction:
    changes: dict[Path, ApplyPatchFileChange]
    cwd: Path | None = None
    patch: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.changes, dict):
            raise TypeError("changes must be a dict")
        normalized: dict[Path, ApplyPatchFileChange] = {}
        for path, change in self.changes.items():
            if not isinstance(path, Path):
                raise TypeError("changes keys must be Paths")
            if not isinstance(change, ApplyPatchFileChange):
                raise TypeError("changes values must be ApplyPatchFileChange values")
            normalized[path] = change
        object.__setattr__(self, "changes", normalized)
        if self.cwd is not None and not isinstance(self.cwd, Path):
            raise TypeError("cwd must be a Path")
        _ensure_str(self.patch, "patch")

    @classmethod
    def new_add_for_test(cls, path: str | Path, content: str) -> "ApplyPatchAction":
        _ensure_pathlike(path, "path")
        _ensure_str(content, "content")
        return cls({Path(path): ApplyPatchFileChange.add(content)})

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ApplyPatchAction":
        if not isinstance(value, Mapping):
            raise TypeError("value must be a mapping")
        raw_changes = value.get("changes")
        if not isinstance(raw_changes, Mapping):
            raise TypeError("changes must be a mapping")
        cwd = value.get("cwd")
        patch = value.get("patch")
        return cls(
            changes={
                _path_from_mapping_key(path): _coerce_apply_patch_file_change(change)
                for path, change in raw_changes.items()
            },
            cwd=Path(cwd) if isinstance(cwd, str) else None,
            patch=patch if isinstance(patch, str) else "",
        )

@dataclass(frozen=True)
class ApplyPatchFileUpdate:
    unified_diff: str
    original_content: str
    content: str

    def __post_init__(self) -> None:
        _ensure_str(self.unified_diff, "unified_diff")
        _ensure_str(self.original_content, "original_content")
        _ensure_str(self.content, "content")

def apply_patch_action_to_disk(action: ApplyPatchAction) -> str:
    if not isinstance(action, ApplyPatchAction):
        raise TypeError("action must be ApplyPatchAction")
    added: list[Path] = []
    modified: list[Path] = []
    deleted: list[Path] = []
    for path, change in action.changes.items():
        if change.type == "add":
            assert change.content is not None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(change.content.encode("utf-8"))
            added.append(path)
            continue
        if change.type == "delete":
            path.unlink()
            deleted.append(path)
            continue
        if change.type == "update":
            if change.new_content is None:
                raise ApplyPatchError.compute_replacements(
                    f"missing computed content for update {path}"
                )
            output_path = change.move_path or path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(change.new_content.encode("utf-8"))
            if change.move_path is not None and change.move_path != path:
                path.unlink()
            modified.append(path)
            continue
        raise ValueError(f"unknown apply_patch file change type: {change.type}")
    return apply_patch_summary(added, modified, deleted)

def apply_patch_summary(
    added: list[Path] | tuple[Path, ...],
    modified: list[Path] | tuple[Path, ...],
    deleted: list[Path] | tuple[Path, ...],
) -> str:
    lines = ["Success. Updated the following files:"]
    lines.extend(f"A {path}" for path in added)
    lines.extend(f"M {path}" for path in modified)
    lines.extend(f"D {path}" for path in deleted)
    return "\n".join(lines) + "\n"

def derive_new_contents_from_chunks(
    path: str | Path,
    chunks: tuple[UpdateFileChunk, ...] | list[UpdateFileChunk],
    original_content: str,
) -> str:
    original_lines = original_content.split("\n")
    if original_lines and original_lines[-1] == "":
        original_lines.pop()
    replacements = _compute_replacements(original_lines, Path(path), tuple(chunks))
    new_lines = _apply_replacements(original_lines, replacements)
    if not new_lines or new_lines[-1] != "":
        new_lines.append("")
    return "\n".join(new_lines)

def unified_diff_from_chunks(
    path: str | Path,
    chunks: tuple[UpdateFileChunk, ...] | list[UpdateFileChunk],
    original_content: str,
) -> ApplyPatchFileUpdate:
    return unified_diff_from_chunks_with_context(
        path,
        chunks,
        original_content,
        context=1,
    )

def unified_diff_from_chunks_with_context(
    path: str | Path,
    chunks: tuple[UpdateFileChunk, ...] | list[UpdateFileChunk],
    original_content: str,
    *,
    context: int,
) -> ApplyPatchFileUpdate:
    new_content = derive_new_contents_from_chunks(path, chunks, original_content)
    diff_lines = list(
        difflib.unified_diff(
            _split_for_unified_diff(original_content),
            _split_for_unified_diff(new_content),
            n=context,
            lineterm="\n",
        )
    )
    return ApplyPatchFileUpdate(
        unified_diff="".join(diff_lines[2:]),
        original_content=original_content,
        content=new_content,
    )

def _compute_replacements(
    original_lines: list[str],
    path: Path,
    chunks: tuple[UpdateFileChunk, ...],
) -> list[tuple[int, int, tuple[str, ...]]]:
    replacements: list[tuple[int, int, tuple[str, ...]]] = []
    line_index = 0

    for chunk in chunks:
        if chunk.change_context is not None:
            context_index = _seek_sequence(
                original_lines,
                (chunk.change_context,),
                line_index,
                eof=False,
            )
            if context_index is None:
                raise ApplyPatchError.compute_replacements(
                    f"Failed to find context '{chunk.change_context}' in {path}"
                )
            line_index = context_index + 1

        if not chunk.old_lines:
            insertion_index = (
                len(original_lines) - 1
                if original_lines and original_lines[-1] == ""
                else len(original_lines)
            )
            replacements.append((insertion_index, 0, chunk.new_lines))
            continue

        pattern = chunk.old_lines
        found = _seek_sequence(
            original_lines,
            pattern,
            line_index,
            eof=chunk.is_end_of_file,
        )
        new_slice = chunk.new_lines

        if found is None and pattern and pattern[-1] == "":
            pattern = pattern[:-1]
            if new_slice and new_slice[-1] == "":
                new_slice = new_slice[:-1]
            found = _seek_sequence(
                original_lines,
                pattern,
                line_index,
                eof=chunk.is_end_of_file,
            )

        if found is None:
            raise ApplyPatchError.compute_replacements(
                f"Failed to find expected lines in {path}:\n"
                + "\n".join(chunk.old_lines)
            )

        replacements.append((found, len(pattern), new_slice))
        line_index = found + len(pattern)

    return sorted(replacements, key=lambda replacement: replacement[0])

def _apply_replacements(
    lines: list[str],
    replacements: list[tuple[int, int, tuple[str, ...]]],
) -> list[str]:
    result = list(lines)
    for start_index, old_length, new_segment in reversed(replacements):
        del result[start_index : start_index + old_length]
        for offset, new_line in enumerate(new_segment):
            result.insert(start_index + offset, new_line)
    return result

def _split_for_unified_diff(value: str) -> list[str]:
    return [
        line if line.endswith("\n") else line + "\n"
        for line in value.splitlines(keepends=True)
    ]

def _coerce_apply_patch_file_change(value: ApplyPatchFileChange | Mapping[str, JsonValue]) -> ApplyPatchFileChange:
    if isinstance(value, ApplyPatchFileChange):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("apply_patch file change must be a mapping")
    return ApplyPatchFileChange.from_mapping(value)

def _path_from_mapping_key(value: object) -> Path:
    if not isinstance(value, str):
        raise TypeError("changes keys must be strings")
    return Path(value)

def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw

def _optional_str(value: Mapping[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw

def _ensure_str(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")

def _ensure_pathlike(value: object, name: str) -> None:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be path-like")

def _ensure_absent(value: object, name: str) -> None:
    if value is not None:
        raise ValueError(f"{name} is not valid for this variant")

def _ensure_positive_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")

def _ensure_str_tuple(value: object, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(f"{name} must be an iterable of strings") from exc
    if not all(isinstance(item, str) for item in items):
        raise TypeError(f"{name} must contain only strings")
    return items

from .invocation import maybe_parse_apply_patch_verified, verify_apply_patch_args
from .parser import ApplyPatchParseError, Hunk, UpdateFileChunk, parse_patch
from .seek_sequence import seek_sequence as _seek_sequence
from .streaming_parser import StreamingPatchParser

__all__ = [
    "APPLY_PATCH_TOOL_INSTRUCTIONS", "CODEX_CORE_APPLY_PATCH_ARG1",
    "ApplyPatchAction", "ApplyPatchArgs", "ApplyPatchError",
    "ApplyPatchFileChange", "ApplyPatchFileUpdate", "ApplyPatchParseError",
    "Hunk", "MaybeApplyPatchVerified", "StreamingPatchParser",
    "UpdateFileChunk", "apply_patch_action_to_disk", "apply_patch_summary",
    "derive_new_contents_from_chunks", "maybe_parse_apply_patch_verified",
    "parse_patch", "unified_diff_from_chunks",
    "unified_diff_from_chunks_with_context", "verify_apply_patch_args",
]
