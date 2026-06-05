"""Pure apply_patch helpers ported from Codex core.

This module covers the dependency-free parser/spec/conversion layers from
``codex-rs/apply-patch`` and ``core/src/apply_patch.rs``. It does not apply
patches to disk.
"""

from __future__ import annotations

import difflib
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pycodex.features import Feature
from pycodex.core.tools.hosted_spec import FreeformToolFormat, ToolSpec
from pycodex.core.tools.hook_names import HookToolName
from pycodex.core.tools.context import ApplyPatchToolOutput, ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.core.tools.registry import CoreToolRuntime, PostToolUsePayload, PreToolUsePayload
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    EventMsg,
    FileChange,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    GranularApprovalConfig,
    PatchApplyUpdatedEvent,
    approval_policy_display_value,
)
from pycodex.protocol import ToolName

JsonValue = Any

APPLY_PATCH_TOOL_NAME = "apply_patch"
APPLY_PATCH_FREEFORM_DESCRIPTION = (
    "Use the `apply_patch` tool to edit files. This is a FREEFORM tool, so do "
    "not wrap the patch in JSON."
)
APPLY_PATCH_LARK_GRAMMAR = """start: begin_patch hunk+ end_patch
begin_patch: "*** Begin Patch" LF
end_patch: "*** End Patch" LF?

hunk: add_hunk | delete_hunk | update_hunk
add_hunk: "*** Add File: " filename LF add_line+
delete_hunk: "*** Delete File: " filename LF
update_hunk: "*** Update File: " filename LF change_move? change?

filename: /(.+)/
add_line: "+" /(.*)/ LF -> line

change_move: "*** Move to: " filename LF
change: (change_context | change_line)+ eof_line?
change_context: ("@@" | "@@ " /(.+)/) LF
change_line: ("+" | "-" | " ") /(.*)/ LF
eof_line: "*** End of File" LF

%import common.LF
"""

BEGIN_PATCH_MARKER = "*** Begin Patch"
ENVIRONMENT_ID_MARKER = "*** Environment ID: "
END_PATCH_MARKER = "*** End Patch"
ADD_FILE_MARKER = "*** Add File: "
DELETE_FILE_MARKER = "*** Delete File: "
UPDATE_FILE_MARKER = "*** Update File: "
MOVE_TO_MARKER = "*** Move to: "
EOF_MARKER = "*** End of File"
CHANGE_CONTEXT_MARKER = "@@ "
EMPTY_CHANGE_CONTEXT_MARKER = "@@"
PARSE_IN_STRICT_MODE = False
APPLY_PATCH_COMMANDS = ("apply_patch", "applypatch")


@dataclass(frozen=True)
class ApplyPatchParseError(Exception):
    kind: str
    message: str
    line_number: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"invalid_patch", "invalid_hunk"}:
            raise ValueError("unknown apply_patch parse error kind")
        _ensure_str(self.message, "message")
        if self.kind == "invalid_patch" and self.line_number is not None:
            raise ValueError("invalid_patch errors must not have a line_number")
        if self.kind == "invalid_hunk":
            _ensure_positive_int(self.line_number, "line_number")

    @classmethod
    def invalid_patch(cls, message: str) -> "ApplyPatchParseError":
        return cls(kind="invalid_patch", message=message)

    @classmethod
    def invalid_hunk(cls, message: str, line_number: int) -> "ApplyPatchParseError":
        return cls(kind="invalid_hunk", message=message, line_number=line_number)

    def __str__(self) -> str:
        if self.kind == "invalid_hunk":
            return f"invalid hunk at line {self.line_number}, {self.message}"
        return f"invalid patch: {self.message}"


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
class UpdateFileChunk:
    change_context: str | None
    old_lines: tuple[str, ...] = ()
    new_lines: tuple[str, ...] = ()
    is_end_of_file: bool = False

    def __post_init__(self) -> None:
        if self.change_context is not None:
            _ensure_str(self.change_context, "change_context")
        object.__setattr__(self, "old_lines", _ensure_str_tuple(self.old_lines, "old_lines"))
        object.__setattr__(self, "new_lines", _ensure_str_tuple(self.new_lines, "new_lines"))
        if not isinstance(self.is_end_of_file, bool):
            raise TypeError("is_end_of_file must be a bool")


@dataclass(frozen=True)
class Hunk:
    type: str
    path: Path
    contents: str | None = None
    move_path: Path | None = None
    chunks: tuple[UpdateFileChunk, ...] = ()

    def __post_init__(self) -> None:
        if self.type not in {"add", "delete", "update"}:
            raise ValueError("unknown hunk type")
        if not isinstance(self.path, Path):
            raise TypeError("path must be a Path")
        object.__setattr__(self, "chunks", tuple(self.chunks))
        if not all(isinstance(chunk, UpdateFileChunk) for chunk in self.chunks):
            raise TypeError("chunks must contain only UpdateFileChunk values")
        if self.type == "add":
            _ensure_str(self.contents, "contents")
            _ensure_absent(self.move_path, "move_path")
            if self.chunks:
                raise ValueError("add hunks must not have chunks")
            return
        if self.type == "delete":
            _ensure_absent(self.contents, "contents")
            _ensure_absent(self.move_path, "move_path")
            if self.chunks:
                raise ValueError("delete hunks must not have chunks")
            return
        _ensure_absent(self.contents, "contents")
        if self.move_path is not None and not isinstance(self.move_path, Path):
            raise TypeError("move_path must be a Path")

    @classmethod
    def add_file(cls, path: str | Path, contents: str) -> "Hunk":
        _ensure_pathlike(path, "path")
        _ensure_str(contents, "contents")
        return cls(type="add", path=Path(path), contents=contents)

    @classmethod
    def delete_file(cls, path: str | Path) -> "Hunk":
        _ensure_pathlike(path, "path")
        return cls(type="delete", path=Path(path))

    @classmethod
    def update_file(
        cls,
        path: str | Path,
        *,
        move_path: str | Path | None = None,
        chunks: tuple[UpdateFileChunk, ...] | list[UpdateFileChunk] = (),
    ) -> "Hunk":
        _ensure_pathlike(path, "path")
        if move_path is not None:
            _ensure_pathlike(move_path, "move_path")
        return cls(
            type="update",
            path=Path(path),
            move_path=Path(move_path) if move_path is not None else None,
            chunks=tuple(chunks),
        )

    def affected_path(self) -> Path:
        return self.move_path if self.type == "update" and self.move_path is not None else self.path

    def resolve_path(self, cwd: str | Path) -> Path:
        _ensure_pathlike(cwd, "cwd")
        path = self.path
        if path.is_absolute():
            return path
        return Path(cwd) / path


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
class MaybeApplyPatch:
    type: str
    body: ApplyPatchArgs | None = None
    error: ApplyPatchParseError | str | None = None

    def __post_init__(self) -> None:
        if self.type not in {"body", "patch_parse_error", "shell_parse_error", "not_apply_patch"}:
            raise ValueError("unknown maybe apply_patch type")
        if self.type == "body":
            if not isinstance(self.body, ApplyPatchArgs):
                raise TypeError("body must be an ApplyPatchArgs")
            _ensure_absent(self.error, "error")
            return
        _ensure_absent(self.body, "body")
        if self.type == "patch_parse_error" and not isinstance(self.error, ApplyPatchParseError):
            raise TypeError("error must be an ApplyPatchParseError")
        if self.type == "shell_parse_error":
            _ensure_str(self.error, "error")
        if self.type == "not_apply_patch":
            _ensure_absent(self.error, "error")

    @classmethod
    def body_result(cls, body: ApplyPatchArgs) -> "MaybeApplyPatch":
        return cls(type="body", body=body)

    @classmethod
    def patch_parse_error(cls, error: ApplyPatchParseError) -> "MaybeApplyPatch":
        return cls(type="patch_parse_error", error=error)

    @classmethod
    def shell_parse_error(cls, error: str) -> "MaybeApplyPatch":
        return cls(type="shell_parse_error", error=error)

    @classmethod
    def not_apply_patch(cls) -> "MaybeApplyPatch":
        return cls(type="not_apply_patch")


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


@dataclass
class StreamingPatchParser:
    line_buffer: str = ""
    mode: str = "not_started"
    line_number: int = 0
    hunks: list[Hunk] = field(default_factory=list)
    hunk_line_number: int | None = None

    def push_delta(self, delta: str) -> tuple[Hunk, ...]:
        for ch in delta:
            if ch == "\n":
                line = self.line_buffer
                self.line_buffer = ""
                if line.endswith("\r"):
                    line = line[:-1]
                self.line_number += 1
                self._process_line(line)
            else:
                self.line_buffer += ch
        return tuple(self.hunks)

    def finish(self) -> tuple[Hunk, ...]:
        if self.line_buffer:
            line = self.line_buffer
            self.line_buffer = ""
            self.line_number += 1
            if line.strip() == END_PATCH_MARKER:
                self._ensure_update_hunk_is_not_empty(line.strip())
                self.mode = "ended_patch"
            else:
                self._process_line(line)

        if self.mode != "ended_patch":
            raise ApplyPatchParseError.invalid_patch(
                "The last line of the patch must be '*** End Patch'"
            )
        return tuple(self.hunks)

    def _process_line(self, line: str) -> None:
        trimmed = line.strip()
        if self.mode == "not_started":
            if trimmed == BEGIN_PATCH_MARKER:
                self.mode = "started_patch"
                return
            raise ApplyPatchParseError.invalid_patch(
                "The first line of the patch must be '*** Begin Patch'"
            )

        if self.mode == "started_patch":
            if line.startswith(ENVIRONMENT_ID_MARKER):
                return
            if self._handle_hunk_headers_and_end_patch(trimmed):
                return
            raise ApplyPatchParseError.invalid_hunk(
                _invalid_hunk_header_message(trimmed),
                self.line_number,
            )

        if self.mode == "add_file":
            if self._handle_hunk_headers_and_end_patch(trimmed):
                return
            if line.startswith("+") and self.hunks and self.hunks[-1].type == "add":
                hunk = self.hunks[-1]
                self.hunks[-1] = Hunk.add_file(
                    hunk.path,
                    (hunk.contents or "") + line[1:] + "\n",
                )
                return
            raise ApplyPatchParseError.invalid_hunk(
                _invalid_hunk_header_message(trimmed),
                self.line_number,
            )

        if self.mode == "delete_file":
            if self._handle_hunk_headers_and_end_patch(trimmed):
                return
            raise ApplyPatchParseError.invalid_hunk(
                _invalid_hunk_header_message(trimmed),
                self.line_number,
            )

        if self.mode == "update_file":
            self._process_update_line(line)

    def _process_update_line(self, line: str) -> None:
        update_line = line.rstrip()
        if self._handle_hunk_headers_and_end_patch(update_line):
            return
        if not self.hunks or self.hunks[-1].type != "update":
            raise ApplyPatchParseError.invalid_hunk(
                _unexpected_update_line_message(line),
                self.line_number,
            )

        hunk = self.hunks[-1]
        chunks = list(hunk.chunks)

        if not chunks and hunk.move_path is None and update_line.startswith(MOVE_TO_MARKER):
            self.hunks[-1] = Hunk.update_file(
                hunk.path,
                move_path=update_line.removeprefix(MOVE_TO_MARKER),
                chunks=chunks,
            )
            return

        if (
            update_line == EMPTY_CHANGE_CONTEXT_MARKER
            or update_line.startswith(CHANGE_CONTEXT_MARKER)
        ) and chunks and _chunk_is_empty(chunks[-1]):
            raise ApplyPatchParseError.invalid_hunk(
                _unexpected_update_line_message(line),
                self.line_number,
            )

        if update_line == EMPTY_CHANGE_CONTEXT_MARKER:
            chunks.append(UpdateFileChunk(change_context=None))
            self._replace_last_update_hunk(chunks)
            return

        if update_line.startswith(CHANGE_CONTEXT_MARKER):
            chunks.append(
                UpdateFileChunk(
                    change_context=update_line.removeprefix(CHANGE_CONTEXT_MARKER)
                )
            )
            self._replace_last_update_hunk(chunks)
            return

        if update_line == EOF_MARKER:
            if chunks and _chunk_is_empty(chunks[-1]):
                raise ApplyPatchParseError.invalid_hunk(
                    "Update hunk does not contain any lines",
                    self.line_number,
                )
            if chunks:
                chunks[-1] = _replace_chunk(chunks[-1], is_end_of_file=True)
                self._replace_last_update_hunk(chunks)
                return

        if line == "":
            chunks = self._ensure_streaming_chunk(chunks)
            chunks[-1] = _append_streaming_context_line(chunks[-1], "")
            self._replace_last_update_hunk(chunks)
            return

        if line.startswith(" "):
            chunks = self._ensure_streaming_chunk(chunks)
            chunks[-1] = _append_streaming_context_line(chunks[-1], line[1:])
            self._replace_last_update_hunk(chunks)
            return

        if line.startswith("+"):
            chunks = self._ensure_streaming_chunk(chunks)
            chunks[-1] = _append_streaming_new_line(chunks[-1], line[1:])
            self._replace_last_update_hunk(chunks)
            return

        if line.startswith("-"):
            chunks = self._ensure_streaming_chunk(chunks)
            chunks[-1] = _append_streaming_old_line(chunks[-1], line[1:])
            self._replace_last_update_hunk(chunks)
            return

        if chunks and not _chunk_is_empty(chunks[-1]):
            raise ApplyPatchParseError.invalid_hunk(
                f"Expected update hunk to start with a @@ context marker, got: '{line}'",
                self.line_number,
            )
        raise ApplyPatchParseError.invalid_hunk(
            _unexpected_update_line_message(line),
            self.line_number,
        )

    def _handle_hunk_headers_and_end_patch(self, marker_line: str) -> bool:
        if marker_line == END_PATCH_MARKER:
            self._ensure_update_hunk_is_not_empty(marker_line)
            self.mode = "ended_patch"
            return True
        if marker_line.startswith(ADD_FILE_MARKER):
            self._ensure_update_hunk_is_not_empty(marker_line)
            self.hunks.append(Hunk.add_file(marker_line.removeprefix(ADD_FILE_MARKER), ""))
            self.mode = "add_file"
            self.hunk_line_number = None
            return True
        if marker_line.startswith(DELETE_FILE_MARKER):
            self._ensure_update_hunk_is_not_empty(marker_line)
            self.hunks.append(Hunk.delete_file(marker_line.removeprefix(DELETE_FILE_MARKER)))
            self.mode = "delete_file"
            self.hunk_line_number = None
            return True
        if marker_line.startswith(UPDATE_FILE_MARKER):
            self._ensure_update_hunk_is_not_empty(marker_line)
            self.hunks.append(
                Hunk.update_file(marker_line.removeprefix(UPDATE_FILE_MARKER))
            )
            self.mode = "update_file"
            self.hunk_line_number = self.line_number
            return True
        return False

    def _ensure_update_hunk_is_not_empty(self, line: str) -> None:
        if not self.hunks or self.hunks[-1].type != "update":
            return
        hunk = self.hunks[-1]
        if not hunk.chunks and self.mode == "update_file" and self.hunk_line_number is not None:
            raise ApplyPatchParseError.invalid_hunk(
                f"Update file hunk for path '{hunk.path}' is empty",
                self.hunk_line_number,
            )
        if hunk.chunks and _chunk_is_empty(hunk.chunks[-1]):
            if line == END_PATCH_MARKER:
                raise ApplyPatchParseError.invalid_hunk(
                    "Update hunk does not contain any lines",
                    self.line_number,
                )
            raise ApplyPatchParseError.invalid_hunk(
                _unexpected_update_line_message(line),
                self.line_number,
            )

    def _ensure_streaming_chunk(self, chunks: list[UpdateFileChunk]) -> list[UpdateFileChunk]:
        if not chunks:
            chunks.append(UpdateFileChunk(change_context=None))
        return chunks

    def _replace_last_update_hunk(self, chunks: list[UpdateFileChunk]) -> None:
        hunk = self.hunks[-1]
        self.hunks[-1] = Hunk.update_file(
            hunk.path,
            move_path=hunk.move_path,
            chunks=tuple(chunks),
        )


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


@dataclass(frozen=True)
class ApplyPatchHandler(CoreToolRuntime):
    multi_environment: bool = False

    @classmethod
    def new(cls, include_environment_id: bool) -> "ApplyPatchHandler":
        return cls(multi_environment=include_environment_id)

    def tool_name(self) -> ToolName:
        return ToolName.plain(APPLY_PATCH_TOOL_NAME)

    def spec(self) -> ToolSpec:
        return create_apply_patch_freeform_tool(self.multi_environment)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return payload.type == "custom"

    def create_diff_consumer(self) -> "ApplyPatchArgumentDiffConsumer":
        return ApplyPatchArgumentDiffConsumer()

    def pre_tool_use_payload(self, invocation: Any) -> PreToolUsePayload | None:
        command = apply_patch_payload_command(getattr(invocation, "payload", None))
        if command is None:
            return None
        return PreToolUsePayload(HookToolName.apply_patch(), {"command": command})

    def with_updated_hook_input(self, invocation: Any, updated_input: JsonValue) -> Any:
        from pycodex.core.tools.handlers.utils import updated_hook_command

        patch = updated_hook_command(updated_input)
        payload = getattr(invocation, "payload", None)
        if isinstance(payload, ToolPayload) and payload.type == "custom":
            return replace(invocation, payload=ToolPayload.custom(patch))
        return invocation

    def post_tool_use_payload(self, invocation: Any, result: Any) -> PostToolUsePayload | None:
        command = apply_patch_payload_command(getattr(invocation, "payload", None))
        if command is None:
            return None
        response_method = getattr(result, "post_tool_use_response", None)
        tool_response = response_method(invocation.call_id, invocation.payload) if callable(response_method) else None
        if tool_response is None:
            return None
        return PostToolUsePayload(
            HookToolName.apply_patch(),
            invocation.call_id,
            {"command": command},
            tool_response,
        )

    def handle(self, invocation: Any) -> ApplyPatchToolOutput:
        resolved = resolve_apply_patch_invocation(
            invocation,
            multi_environment=self.multi_environment,
        )
        verified = verify_apply_patch_args(resolved.args, resolved.cwd)
        if verified.type == "body":
            assert verified.body is not None
            rejection = _apply_patch_policy_rejection(invocation, verified.body)
            if rejection is not None:
                raise FunctionCallError.respond_to_model(rejection)
            return ApplyPatchToolOutput.from_text(apply_patch_action_to_disk(verified.body))
        if verified.type == "correctness_error":
            raise FunctionCallError.respond_to_model(
                f"apply_patch verification failed: {verified.error}"
            )
        raise FunctionCallError.respond_to_model(
            "apply_patch handler received invalid patch input"
        )


@dataclass
class ApplyPatchArgumentDiffConsumer:
    parser: StreamingPatchParser = field(default_factory=StreamingPatchParser)

    def consume_diff(self, turn: Any, call_id: str, delta: str) -> EventMsg | None:
        if not _apply_patch_streaming_events_enabled(turn):
            return None
        try:
            hunks = self.parser.push_delta(delta)
        except ApplyPatchParseError:
            return None
        if not hunks:
            return None
        return EventMsg.with_payload(
            "patch_apply_updated",
            PatchApplyUpdatedEvent(call_id, convert_apply_patch_hunks_to_protocol(hunks)),
        )

    def finish(self) -> EventMsg | None:
        try:
            self.parser.finish()
        except ApplyPatchParseError as error:
            raise FunctionCallError.respond_to_model(f"failed to parse apply_patch: {error}") from error
        return None


def apply_patch_payload_command(payload: Any) -> str | None:
    if isinstance(payload, ToolPayload) and payload.type == "custom":
        return payload.input
    return None


def convert_apply_patch_hunks_to_protocol(hunks: tuple[Hunk, ...] | list[Hunk]) -> dict[Path, FileChange]:
    changes: dict[Path, FileChange] = {}
    for hunk in hunks:
        path = hunk.path
        if hunk.type == "add":
            changes[path] = FileChange.add(hunk.contents or "")
        elif hunk.type == "delete":
            changes[path] = FileChange.delete("")
        elif hunk.type == "update":
            changes[path] = FileChange.update(
                _format_update_chunks_for_progress(hunk.chunks),
                move_path=hunk.move_path,
            )
        else:
            raise ValueError(f"unknown apply_patch hunk type: {hunk.type}")
    return changes


def _format_update_chunks_for_progress(chunks: tuple[UpdateFileChunk, ...]) -> str:
    lines: list[str] = []
    for chunk in chunks:
        lines.append(f"@@ {chunk.change_context}" if chunk.change_context is not None else "@@")
        lines.extend(f"-{line}" for line in chunk.old_lines)
        lines.extend(f"+{line}" for line in chunk.new_lines)
        if chunk.is_end_of_file:
            lines.append(EOF_MARKER)
    return "\n".join(lines) + ("\n" if lines else "")


def _apply_patch_streaming_events_enabled(turn: Any) -> bool:
    features = getattr(turn, "features", None)
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        return bool(enabled(Feature.APPLY_PATCH_STREAMING_EVENTS))
    if isinstance(features, Mapping):
        return bool(
            features.get(Feature.APPLY_PATCH_STREAMING_EVENTS)
            or features.get(Feature.APPLY_PATCH_STREAMING_EVENTS.value)
            or features.get(Feature.APPLY_PATCH_STREAMING_EVENTS.key())
        )
    return False


def _apply_patch_policy_rejection(invocation: Any, action: ApplyPatchAction) -> str | None:
    file_system_sandbox_policy = _invocation_file_system_sandbox_policy(invocation)
    if file_system_sandbox_policy is None:
        return None
    cwd = action.cwd
    write_check_paths = _apply_patch_write_check_paths(action)
    unwritable = tuple(
        path for path in write_check_paths if not file_system_sandbox_policy.can_write_path_with_cwd(path, cwd)
    )
    if not unwritable:
        return None
    granted_permissions = _invocation_granted_permissions(invocation)
    from pycodex.core.tools.handlers.utils import permissions_are_preapproved

    if granted_permissions is not None and permissions_are_preapproved(
        _apply_patch_required_permissions(write_check_paths, cwd),
        granted_permissions,
        cwd,
    ):
        return None
    approval_policy = _invocation_approval_policy(invocation)
    approval = approval_policy_display_value(approval_policy)
    paths = "\n".join(str(path) for path in unwritable)
    if approval_policy is AskForApproval.NEVER or (
        isinstance(approval_policy, GranularApprovalConfig)
        and not approval_policy.allows_sandbox_approval()
    ):
        return (
            "exit_code: forbidden\n"
            f"approval_policy: {approval}\n"
            "stderr:\n"
            "patch rejected: writing outside of the project; rejected by user approval settings\n"
            f"paths:\n{paths}"
        )
    return (
        "exit_code: approval_required\n"
        f"approval_policy: {approval}\n"
        "stderr:\n"
        "patch requires approval before writing outside the current sandbox\n"
        f"paths:\n{paths}"
    )


def _apply_patch_write_check_paths(action: ApplyPatchAction) -> tuple[Path, ...]:
    paths: list[Path] = []
    for path, change in action.changes.items():
        paths.append(_write_check_path(path))
        move_path = getattr(change, "move_path", None)
        if move_path is not None:
            paths.append(_write_check_path(move_path))
    return tuple(dict.fromkeys(paths))


def _write_check_path(path: Path) -> Path:
    parent = path.parent
    return parent if str(parent) not in {"", "."} else path


def _apply_patch_required_permissions(paths: tuple[Path, ...], cwd: Path) -> AdditionalPermissionProfile:
    entries = tuple(
        FileSystemSandboxEntry(
            FileSystemPath.explicit_path(path if path.is_absolute() else cwd / path),
            FileSystemAccessMode.WRITE,
        )
        for path in paths
    )
    return AdditionalPermissionProfile(file_system=FileSystemPermissions(entries=entries))


def _invocation_granted_permissions(invocation: Any) -> AdditionalPermissionProfile | None:
    session = getattr(invocation, "session", None)
    granted_session = _sync_granted_permissions(session, "granted_session_permissions", "_granted_session_permissions")
    granted_turn = _sync_granted_permissions(session, "granted_turn_permissions", "_granted_turn_permissions")
    turn = getattr(invocation, "turn", None)
    from pycodex.core.tools.handlers.utils import merge_permission_profiles

    granted_turn = merge_permission_profiles(
        granted_turn,
        _sync_granted_permissions(turn, "granted_turn_permissions", "_granted_turn_permissions"),
    )
    return merge_permission_profiles(granted_session, granted_turn)


def _sync_granted_permissions(target: Any, method_name: str, attr_name: str) -> AdditionalPermissionProfile | None:
    if target is None:
        return None
    if hasattr(target, attr_name):
        value = getattr(target, attr_name)
        return value if isinstance(value, AdditionalPermissionProfile) else None
    method = getattr(target, method_name, None)
    if callable(method):
        try:
            value = method()
        except TypeError:
            return None
        close = getattr(value, "close", None)
        if callable(close):
            close()
            return None
        if isinstance(value, AdditionalPermissionProfile):
            return value
    return None


def _invocation_file_system_sandbox_policy(invocation: Any) -> Any | None:
    turn = getattr(invocation, "turn", None)
    policy = getattr(turn, "file_system_sandbox_policy", None)
    if policy is not None:
        return policy
    permission_profile = getattr(turn, "permission_profile", None)
    if permission_profile is None:
        session = getattr(invocation, "session", None)
        permission_profile = getattr(session, "permission_profile", None)
    method = getattr(permission_profile, "file_system_sandbox_policy", None)
    return method() if callable(method) else None


def _invocation_approval_policy(invocation: Any) -> AskForApproval | GranularApprovalConfig:
    turn = getattr(invocation, "turn", None)
    value = getattr(turn, "approval_policy", AskForApproval.ON_REQUEST)
    method = getattr(value, "value", None)
    if callable(method):
        value = method()
    if isinstance(value, GranularApprovalConfig):
        return value
    if not isinstance(value, AskForApproval):
        value = AskForApproval.parse(str(value))
    return value


@dataclass(frozen=True)
class ResolvedApplyPatchInvocation:
    args: ApplyPatchArgs
    selected_environment_id: str | None
    turn_environment: Any
    cwd: Path

    def __post_init__(self) -> None:
        if not isinstance(self.args, ApplyPatchArgs):
            raise TypeError("args must be ApplyPatchArgs")
        if self.selected_environment_id is not None:
            _ensure_str(self.selected_environment_id, "selected_environment_id")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))


def resolve_apply_patch_invocation(
    invocation: Any,
    *,
    multi_environment: bool = False,
) -> ResolvedApplyPatchInvocation:
    payload = getattr(invocation, "payload", None)
    if payload is None or getattr(payload, "type", None) != "custom":
        raise FunctionCallError.respond_to_model("apply_patch handler received unsupported payload")
    patch_input = getattr(payload, "input", None)
    if not isinstance(patch_input, str):
        raise FunctionCallError.respond_to_model("apply_patch handler received unsupported payload")
    try:
        args = parse_patch(patch_input)
    except ApplyPatchParseError as parse_error:
        raise FunctionCallError.respond_to_model(
            f"apply_patch verification failed: {parse_error}"
        ) from parse_error
    selected_environment_id = require_apply_patch_environment_id(
        args.environment_id,
        multi_environment,
    )
    from pycodex.core.tools.handlers.utils import resolve_tool_environment

    turn_environment = resolve_tool_environment(
        getattr(invocation, "turn", None),
        selected_environment_id,
    )
    if turn_environment is None:
        raise FunctionCallError.respond_to_model("apply_patch is unavailable in this session")
    return ResolvedApplyPatchInvocation(
        args=args,
        selected_environment_id=selected_environment_id,
        turn_environment=turn_environment,
        cwd=Path(getattr(turn_environment, "cwd")),
    )


def require_apply_patch_environment_id(
    parsed_environment_id: str | None,
    allow_environment_id: bool,
) -> str | None:
    if parsed_environment_id is not None and not allow_environment_id:
        raise FunctionCallError.respond_to_model(
            "apply_patch environment selection is unavailable for this turn"
        )
    return parsed_environment_id


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
            path.write_text(change.content, encoding="utf-8")
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
            output_path.write_text(change.new_content, encoding="utf-8")
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


def convert_apply_patch_to_protocol(
    action: ApplyPatchAction | Mapping[str, JsonValue],
) -> dict[Path, FileChange]:
    action = action if isinstance(action, ApplyPatchAction) else ApplyPatchAction.from_mapping(action)
    result: dict[Path, FileChange] = {}
    for path, change in action.changes.items():
        if change.type == "add":
            result[path] = FileChange.add(change.content or "")
        elif change.type == "delete":
            result[path] = FileChange.delete(change.content or "")
        elif change.type == "update":
            result[path] = FileChange.update(
                change.unified_diff or "",
                move_path=change.move_path,
            )
        else:
            raise ValueError(f"unknown apply_patch file change type: {change.type}")
    return result


def parse_patch(patch: str) -> ApplyPatchArgs:
    return _parse_patch_text(
        patch,
        strict=PARSE_IN_STRICT_MODE,
    )


def maybe_parse_apply_patch(argv: list[str] | tuple[str, ...]) -> MaybeApplyPatch:
    if len(argv) == 2 and argv[0] in APPLY_PATCH_COMMANDS:
        try:
            return MaybeApplyPatch.body_result(parse_patch(argv[1]))
        except ApplyPatchParseError as error:
            return MaybeApplyPatch.patch_parse_error(error)

    shell_script = _parse_shell_script(argv)
    if shell_script is None:
        return MaybeApplyPatch.not_apply_patch()
    _shell_kind, script = shell_script
    extracted = _extract_apply_patch_from_shell(script)
    if extracted is None:
        return MaybeApplyPatch.not_apply_patch()
    body, workdir = extracted
    try:
        source = parse_patch(body)
    except ApplyPatchParseError as error:
        return MaybeApplyPatch.patch_parse_error(error)
    return MaybeApplyPatch.body_result(
        ApplyPatchArgs(
            patch=source.patch,
            hunks=source.hunks,
            workdir=workdir,
            environment_id=source.environment_id,
        )
    )


def maybe_parse_apply_patch_verified(
    argv: list[str] | tuple[str, ...],
    cwd: str | Path,
) -> MaybeApplyPatchVerified:
    if len(argv) == 1:
        try:
            parse_patch(argv[0])
        except ApplyPatchParseError:
            pass
        else:
            return MaybeApplyPatchVerified.correctness_error(
                ApplyPatchError.implicit_invocation()
            )

    shell_script = _parse_shell_script(argv)
    if shell_script is not None:
        _shell_kind, script = shell_script
        try:
            parse_patch(script)
        except ApplyPatchParseError:
            pass
        else:
            return MaybeApplyPatchVerified.correctness_error(
                ApplyPatchError.implicit_invocation()
            )

    parsed = maybe_parse_apply_patch(argv)
    if parsed.type == "body":
        assert parsed.body is not None
        return verify_apply_patch_args(parsed.body, cwd)
    if parsed.type == "shell_parse_error":
        return MaybeApplyPatchVerified.shell_parse_error(str(parsed.error))
    if parsed.type == "patch_parse_error":
        assert isinstance(parsed.error, ApplyPatchParseError)
        return MaybeApplyPatchVerified.correctness_error(
            ApplyPatchError.parse_error(parsed.error)
        )
    return MaybeApplyPatchVerified.not_apply_patch()


def verify_apply_patch_args(
    args: ApplyPatchArgs,
    cwd: str | Path,
) -> MaybeApplyPatchVerified:
    cwd_path = Path(cwd)
    if not cwd_path.is_absolute():
        raise ValueError("cwd must be an absolute path")

    effective_cwd = cwd_path / args.workdir if args.workdir is not None else cwd_path
    changes: dict[Path, ApplyPatchFileChange] = {}
    for hunk in args.hunks:
        path = hunk.resolve_path(effective_cwd)
        if hunk.type == "add":
            overwritten_content = _read_optional_text(path)
            changes[path] = ApplyPatchFileChange.add(
                hunk.contents or "",
                overwritten_content=overwritten_content,
            )
            continue

        if hunk.type == "delete":
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as error:
                return MaybeApplyPatchVerified.correctness_error(
                    ApplyPatchError.io_error(f"Failed to read {path}", error)
                )
            changes[path] = ApplyPatchFileChange.delete(content)
            continue

        if hunk.type == "update":
            try:
                original_content = path.read_text(encoding="utf-8")
            except OSError as error:
                return MaybeApplyPatchVerified.correctness_error(
                    ApplyPatchError.io_error(
                        f"Failed to read file to update {path}",
                        error,
                    )
                )
            try:
                update = unified_diff_from_chunks(
                    path,
                    hunk.chunks,
                    original_content,
                )
            except ApplyPatchError as error:
                return MaybeApplyPatchVerified.correctness_error(error)
            move_path = effective_cwd / hunk.move_path if hunk.move_path is not None else None
            changes[path] = ApplyPatchFileChange.update(
                update.unified_diff,
                move_path=move_path,
                new_content=update.content,
                old_content=original_content,
                overwritten_move_content=_read_optional_text(move_path) if move_path is not None else None,
            )
            continue

        return MaybeApplyPatchVerified.correctness_error(
            ApplyPatchError.compute_replacements(
                f"unknown apply_patch hunk type: {hunk.type}"
            )
        )

    return MaybeApplyPatchVerified.body_result(
        ApplyPatchAction(changes=changes, cwd=effective_cwd, patch=args.patch)
    )


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


def create_apply_patch_freeform_tool(include_environment_id: bool) -> ToolSpec:
    if not isinstance(include_environment_id, bool):
        raise TypeError("include_environment_id must be a bool")
    definition = APPLY_PATCH_LARK_GRAMMAR
    if include_environment_id:
        definition = definition.replace(
            "start: begin_patch hunk+ end_patch",
            (
                "start: begin_patch environment_id? hunk+ end_patch\n"
                'environment_id: "*** Environment ID: " filename LF'
            ),
        )
    return ToolSpec.freeform(
        name=APPLY_PATCH_TOOL_NAME,
        description=APPLY_PATCH_FREEFORM_DESCRIPTION,
        format=FreeformToolFormat.grammar(
            syntax="lark",
            definition=definition,
        ),
    )


def _parse_patch_text(patch: str, *, strict: bool) -> ApplyPatchArgs:
    lines = patch.strip().splitlines()
    patch_lines, hunk_lines = _check_patch_boundaries_strict(lines) if strict else _check_patch_boundaries_lenient(lines)
    environment_id, remaining_lines, line_number = _parse_environment_id_preamble(hunk_lines)
    hunks: list[Hunk] = []
    while remaining_lines:
        hunk, hunk_line_count = _parse_one_hunk(remaining_lines, line_number)
        hunks.append(hunk)
        line_number += hunk_line_count
        remaining_lines = remaining_lines[hunk_line_count:]
    return ApplyPatchArgs(
        patch="\n".join(patch_lines),
        hunks=tuple(hunks),
        workdir=None,
        environment_id=environment_id,
    )


def _parse_environment_id_preamble(lines: list[str]) -> tuple[str | None, list[str], int]:
    if not lines:
        return None, lines, 2
    first_line = lines[0].lstrip()
    if not first_line.startswith(ENVIRONMENT_ID_MARKER):
        return None, lines, 2
    environment_id = first_line.removeprefix(ENVIRONMENT_ID_MARKER).strip()
    if environment_id == "":
        raise ApplyPatchParseError.invalid_patch("apply_patch environment_id cannot be empty")
    return environment_id, lines[1:], 3


def _check_patch_boundaries_strict(lines: list[str]) -> tuple[list[str], list[str]]:
    first_line = lines[0].strip() if lines else None
    last_line = lines[-1].strip() if lines else None
    if first_line == BEGIN_PATCH_MARKER and last_line == END_PATCH_MARKER:
        return lines, lines[1:-1]
    if first_line is not None and first_line != BEGIN_PATCH_MARKER:
        raise ApplyPatchParseError.invalid_patch(
            "The first line of the patch must be '*** Begin Patch'"
        )
    raise ApplyPatchParseError.invalid_patch(
        "The last line of the patch must be '*** End Patch'"
    )


def _check_patch_boundaries_lenient(lines: list[str]) -> tuple[list[str], list[str]]:
    try:
        return _check_patch_boundaries_strict(lines)
    except ApplyPatchParseError as original_parse_error:
        if (
            len(lines) >= 4
            and lines[0] in {"<<EOF", "<<'EOF'", '<<"EOF"'}
            and lines[-1].endswith("EOF")
        ):
            return _check_patch_boundaries_strict(lines[1:-1])
        raise original_parse_error


def _parse_one_hunk(lines: list[str], line_number: int) -> tuple[Hunk, int]:
    first_line = lines[0].strip()
    if first_line.startswith(ADD_FILE_MARKER):
        path = first_line.removeprefix(ADD_FILE_MARKER)
        contents = ""
        parsed_lines = 1
        for add_line in lines[1:]:
            if add_line.startswith("+"):
                contents += add_line[1:] + "\n"
                parsed_lines += 1
            else:
                break
        return Hunk.add_file(path, contents), parsed_lines

    if first_line.startswith(DELETE_FILE_MARKER):
        return Hunk.delete_file(first_line.removeprefix(DELETE_FILE_MARKER)), 1

    if first_line.startswith(UPDATE_FILE_MARKER):
        path = first_line.removeprefix(UPDATE_FILE_MARKER)
        remaining_lines = lines[1:]
        parsed_lines = 1
        move_path = None
        if remaining_lines and remaining_lines[0].startswith(MOVE_TO_MARKER):
            move_path = remaining_lines[0].removeprefix(MOVE_TO_MARKER)
            remaining_lines = remaining_lines[1:]
            parsed_lines += 1

        chunks: list[UpdateFileChunk] = []
        while remaining_lines:
            if remaining_lines[0].strip() == "":
                parsed_lines += 1
                remaining_lines = remaining_lines[1:]
                continue
            if remaining_lines[0].startswith("*"):
                break
            chunk, chunk_line_count = _parse_update_file_chunk(
                remaining_lines,
                line_number + parsed_lines,
                allow_missing_context=not chunks,
            )
            chunks.append(chunk)
            parsed_lines += chunk_line_count
            remaining_lines = remaining_lines[chunk_line_count:]

        if not chunks:
            raise ApplyPatchParseError.invalid_hunk(
                f"Update file hunk for path '{Path(path)}' is empty",
                line_number,
            )
        return Hunk.update_file(path, move_path=move_path, chunks=tuple(chunks)), parsed_lines

    raise ApplyPatchParseError.invalid_hunk(
        (
            f"'{first_line}' is not a valid hunk header. Valid hunk headers: "
            "'*** Add File: {path}', '*** Delete File: {path}', "
            "'*** Update File: {path}'"
        ),
        line_number,
    )


def _parse_update_file_chunk(
    lines: list[str],
    line_number: int,
    *,
    allow_missing_context: bool,
) -> tuple[UpdateFileChunk, int]:
    if not lines:
        raise ApplyPatchParseError.invalid_hunk("Update hunk does not contain any lines", line_number)

    if lines[0] == EMPTY_CHANGE_CONTEXT_MARKER:
        change_context = None
        start_index = 1
    elif lines[0].startswith(CHANGE_CONTEXT_MARKER):
        change_context = lines[0].removeprefix(CHANGE_CONTEXT_MARKER)
        start_index = 1
    elif allow_missing_context:
        change_context = None
        start_index = 0
    else:
        raise ApplyPatchParseError.invalid_hunk(
            f"Expected update hunk to start with a @@ context marker, got: '{lines[0]}'",
            line_number,
        )

    if start_index >= len(lines):
        raise ApplyPatchParseError.invalid_hunk(
            "Update hunk does not contain any lines",
            line_number + 1,
        )

    old_lines: list[str] = []
    new_lines: list[str] = []
    is_end_of_file = False
    parsed_lines = 0
    for line in lines[start_index:]:
        if line == EOF_MARKER:
            if parsed_lines == 0:
                raise ApplyPatchParseError.invalid_hunk(
                    "Update hunk does not contain any lines",
                    line_number + 1,
                )
            is_end_of_file = True
            parsed_lines += 1
            break

        if line == "":
            old_lines.append("")
            new_lines.append("")
        elif line.startswith(" "):
            old_lines.append(line[1:])
            new_lines.append(line[1:])
        elif line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("-"):
            old_lines.append(line[1:])
        else:
            if parsed_lines == 0:
                raise ApplyPatchParseError.invalid_hunk(
                    (
                        f"Unexpected line found in update hunk: '{line}'. Every line should start "
                        "with ' ' (context line), '+' (added line), or '-' (removed line)"
                    ),
                    line_number + 1,
                )
            break
        parsed_lines += 1

    return (
        UpdateFileChunk(
            change_context=change_context,
            old_lines=tuple(old_lines),
            new_lines=tuple(new_lines),
            is_end_of_file=is_end_of_file,
        ),
        parsed_lines + start_index,
    )


def _parse_shell_script(argv: list[str] | tuple[str, ...]) -> tuple[str, str] | None:
    if len(argv) == 3:
        shell, flag, script = argv
        shell_kind = _classify_shell(shell, flag)
        return (shell_kind, script) if shell_kind is not None else None
    if len(argv) == 4 and _can_skip_shell_flag(argv[0], argv[1]):
        shell_kind = _classify_shell(argv[0], argv[2])
        return (shell_kind, argv[3]) if shell_kind is not None else None
    return None


def _classify_shell(shell: str, flag: str) -> str | None:
    name = _classify_shell_name(shell)
    flag_lc = flag.lower()
    if name in {"bash", "zsh", "sh"} and flag in {"-lc", "-c"}:
        return "unix"
    if name in {"pwsh", "powershell"} and flag_lc == "-command":
        return "powershell"
    if name == "cmd" and flag_lc == "/c":
        return "cmd"
    return None


def _classify_shell_name(shell: str) -> str:
    return Path(shell.replace("\\", "/")).stem.lower()


def _can_skip_shell_flag(shell: str, flag: str) -> bool:
    return _classify_shell_name(shell) in {"pwsh", "powershell"} and flag.lower() == "-noprofile"


def _extract_apply_patch_from_shell(script: str) -> tuple[str, str | None] | None:
    first_line, separator, rest = script.partition("\n")
    if separator == "":
        return None
    redirect_index = first_line.find("<<")
    if redirect_index < 0 or first_line.find("<<<") >= 0:
        return None
    if first_line.find("<<", redirect_index + 2) >= 0:
        return None

    command_text = first_line[:redirect_index].strip()
    heredoc_start = first_line[redirect_index + 2 :].strip()
    delimiter = _parse_single_shell_word(heredoc_start)
    if delimiter is None:
        return None

    command_parts = _parse_apply_patch_heredoc_command(command_text)
    if command_parts is None:
        return None
    workdir = None if command_parts == _NO_WORKDIR else command_parts

    lines = rest.splitlines()
    terminator_index = next((index for index, line in enumerate(lines) if line == delimiter), None)
    if terminator_index is None:
        return None
    if any(line.strip() for line in lines[terminator_index + 1 :]):
        return None
    return "\n".join(lines[:terminator_index]), workdir


def _parse_single_shell_word(value: str) -> str | None:
    try:
        words = shlex.split(value, posix=True)
    except ValueError:
        return None
    if len(words) != 1 or words[0] == "":
        return None
    return words[0]


def _parse_apply_patch_heredoc_command(command_text: str) -> str | None:
    try:
        words = shlex.split(command_text, posix=True)
    except ValueError:
        return None
    if words in (["apply_patch"], ["applypatch"]):
        return _NO_WORKDIR
    if len(words) == 4 and words[0] == "cd" and words[2] == "&&" and words[3] in APPLY_PATCH_COMMANDS:
        return words[1]
    return None


_NO_WORKDIR = "__pycodex_no_workdir__"


def _invalid_hunk_header_message(line: str) -> str:
    return (
        f"'{line}' is not a valid hunk header. Valid hunk headers: "
        "'*** Add File: {path}', '*** Delete File: {path}', "
        "'*** Update File: {path}'"
    )


def _unexpected_update_line_message(line: str) -> str:
    return (
        f"Unexpected line found in update hunk: '{line}'. Every line should start "
        "with ' ' (context line), '+' (added line), or '-' (removed line)"
    )


def _chunk_is_empty(chunk: UpdateFileChunk) -> bool:
    return not chunk.old_lines and not chunk.new_lines


def _replace_chunk(
    chunk: UpdateFileChunk,
    *,
    old_lines: tuple[str, ...] | None = None,
    new_lines: tuple[str, ...] | None = None,
    is_end_of_file: bool | None = None,
) -> UpdateFileChunk:
    return UpdateFileChunk(
        change_context=chunk.change_context,
        old_lines=chunk.old_lines if old_lines is None else old_lines,
        new_lines=chunk.new_lines if new_lines is None else new_lines,
        is_end_of_file=chunk.is_end_of_file if is_end_of_file is None else is_end_of_file,
    )


def _append_streaming_context_line(chunk: UpdateFileChunk, line: str) -> UpdateFileChunk:
    return _replace_chunk(
        chunk,
        old_lines=chunk.old_lines + (line,),
        new_lines=chunk.new_lines + (line,),
    )


def _append_streaming_old_line(chunk: UpdateFileChunk, line: str) -> UpdateFileChunk:
    return _replace_chunk(chunk, old_lines=chunk.old_lines + (line,))


def _append_streaming_new_line(chunk: UpdateFileChunk, line: str) -> UpdateFileChunk:
    return _replace_chunk(chunk, new_lines=chunk.new_lines + (line,))


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


def _seek_sequence(
    lines: list[str],
    pattern: tuple[str, ...],
    start: int,
    *,
    eof: bool,
) -> int | None:
    if not pattern:
        return start
    if len(pattern) > len(lines):
        return None

    max_start = len(lines) - len(pattern)
    search_start = max_start if eof and len(lines) >= len(pattern) else start
    if search_start > max_start:
        return None

    for line_index in range(search_start, max_start + 1):
        if tuple(lines[line_index : line_index + len(pattern)]) == pattern:
            return line_index

    for line_index in range(search_start, max_start + 1):
        if all(
            lines[line_index + pattern_index].rstrip() == expected.rstrip()
            for pattern_index, expected in enumerate(pattern)
        ):
            return line_index

    for line_index in range(search_start, max_start + 1):
        if all(
            lines[line_index + pattern_index].strip() == expected.strip()
            for pattern_index, expected in enumerate(pattern)
        ):
            return line_index

    for line_index in range(search_start, max_start + 1):
        if all(
            _normalise_patch_seek_line(lines[line_index + pattern_index])
            == _normalise_patch_seek_line(expected)
            for pattern_index, expected in enumerate(pattern)
        ):
            return line_index

    return None


_PATCH_SEEK_NORMALISE_MAP = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u00a0": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
        "\u205f": " ",
        "\u3000": " ",
    }
)


def _normalise_patch_seek_line(value: str) -> str:
    return value.strip().translate(_PATCH_SEEK_NORMALISE_MAP)


def _split_for_unified_diff(value: str) -> list[str]:
    return [
        line if line.endswith("\n") else line + "\n"
        for line in value.splitlines(keepends=True)
    ]


def _read_optional_text(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


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


__all__ = [
    "ADD_FILE_MARKER",
    "APPLY_PATCH_FREEFORM_DESCRIPTION",
    "APPLY_PATCH_LARK_GRAMMAR",
    "APPLY_PATCH_TOOL_NAME",
    "APPLY_PATCH_COMMANDS",
    "BEGIN_PATCH_MARKER",
    "CHANGE_CONTEXT_MARKER",
    "DELETE_FILE_MARKER",
    "EMPTY_CHANGE_CONTEXT_MARKER",
    "END_PATCH_MARKER",
    "ENVIRONMENT_ID_MARKER",
    "EOF_MARKER",
    "MOVE_TO_MARKER",
    "PARSE_IN_STRICT_MODE",
    "UPDATE_FILE_MARKER",
    "ApplyPatchAction",
    "ApplyPatchArgs",
    "ApplyPatchArgumentDiffConsumer",
    "ApplyPatchError",
    "ApplyPatchFileChange",
    "ApplyPatchFileUpdate",
    "ApplyPatchHandler",
    "ApplyPatchParseError",
    "Hunk",
    "MaybeApplyPatch",
    "MaybeApplyPatchVerified",
    "ResolvedApplyPatchInvocation",
    "StreamingPatchParser",
    "UpdateFileChunk",
    "apply_patch_action_to_disk",
    "apply_patch_payload_command",
    "apply_patch_summary",
    "convert_apply_patch_hunks_to_protocol",
    "convert_apply_patch_to_protocol",
    "create_apply_patch_freeform_tool",
    "derive_new_contents_from_chunks",
    "maybe_parse_apply_patch",
    "maybe_parse_apply_patch_verified",
    "parse_patch",
    "require_apply_patch_environment_id",
    "resolve_apply_patch_invocation",
    "unified_diff_from_chunks",
    "unified_diff_from_chunks_with_context",
    "verify_apply_patch_args",
]

