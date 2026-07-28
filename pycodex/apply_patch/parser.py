"""Patch grammar parser owned by ``parser.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import ApplyPatchArgs, _ensure_absent, _ensure_pathlike, _ensure_positive_int, _ensure_str, _ensure_str_tuple

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

def parse_patch(patch: str) -> ApplyPatchArgs:
    return _parse_patch_text(
        patch,
        strict=PARSE_IN_STRICT_MODE,
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

__all__ = ["ApplyPatchParseError", "Hunk", "UpdateFileChunk", "parse_patch"]
