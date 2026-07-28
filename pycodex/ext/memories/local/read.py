"""Line slicing helpers from Rust ``local/read.rs``."""

from __future__ import annotations

from ..backend import MemoriesBackendError
from ..backend import ReadMemoryRequest
from ..backend import ReadMemoryResponse
from .path import display_relative_path


def line_start_byte_offset(content: str, line_offset: int) -> int:
    if line_offset == 1:
        return 0
    current_line = 1
    byte_offset = 0
    for character in content:
        byte_offset += len(character.encode("utf-8"))
        if character == "\n":
            current_line += 1
            if current_line == line_offset:
                return byte_offset
    raise MemoriesBackendError("line_offset exceeds file length")


def line_end_byte_offset(
    content: str, start_byte: int, max_lines: int | None
) -> int:
    encoded = content.encode("utf-8")
    if max_lines is None:
        return len(encoded)
    lines_seen = 1
    for relative_index, byte in enumerate(encoded[start_byte:]):
        if byte == 10:
            if lines_seen == max_lines:
                return start_byte + relative_index + 1
            lines_seen += 1
    return len(encoded)


async def read(backend: object, request: ReadMemoryRequest) -> ReadMemoryResponse:
    if request.line_offset == 0:
        raise MemoriesBackendError("line_offset must be a 1-indexed line number")
    if request.max_lines == 0:
        raise MemoriesBackendError("max_lines must be a positive integer")
    path = backend.resolve_scoped_path(request.path)
    if not path.exists():
        raise MemoriesBackendError(f"path '{request.path}' was not found")
    if path.is_symlink():
        raise MemoriesBackendError.invalid_path(request.path, "must not be a symlink")
    if not path.is_file():
        raise MemoriesBackendError(f"path '{request.path}' is not a file")
    original = path.read_text(encoding="utf-8")
    start = line_start_byte_offset(original, request.line_offset)
    end = line_end_byte_offset(original, start, request.max_lines)
    encoded = original.encode("utf-8")
    content = encoded[start:end].decode("utf-8")
    # Rust token truncation uses an approximate four-byte token budget.
    max_tokens = request.max_tokens or 20_000
    max_bytes = max_tokens * 4
    truncated_content = content.encode("utf-8")[:max_bytes]
    while True:
        try:
            content = truncated_content.decode("utf-8")
            break
        except UnicodeDecodeError:
            truncated_content = truncated_content[:-1]
    return ReadMemoryResponse(
        path=display_relative_path(backend.root, path),
        start_line_number=request.line_offset,
        content=content,
        truncated=end < len(encoded) or len(truncated_content) < end - start,
    )


__all__ = ["line_end_byte_offset", "line_start_byte_offset", "read"]
