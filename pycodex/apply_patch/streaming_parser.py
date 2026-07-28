"""Streaming patch parser owned by ``streaming_parser.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field

from .parser import (
    ADD_FILE_MARKER, BEGIN_PATCH_MARKER, CHANGE_CONTEXT_MARKER,
    DELETE_FILE_MARKER, EMPTY_CHANGE_CONTEXT_MARKER, END_PATCH_MARKER,
    EOF_MARKER, MOVE_TO_MARKER, UPDATE_FILE_MARKER,
    ApplyPatchParseError, Hunk, UpdateFileChunk, _chunk_is_empty,
    _invalid_hunk_header_message, _unexpected_update_line_message,
)

ENVIRONMENT_ID_MARKER = "*** Environment ID: "

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

__all__ = ["StreamingPatchParser"]
