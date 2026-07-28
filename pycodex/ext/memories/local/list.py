"""Sorted memory listing from Rust ``local/list.rs``."""

from __future__ import annotations

from ..backend import ListMemoriesRequest
from ..backend import ListMemoriesResponse
from ..backend import MemoriesBackendError
from ..backend import MemoryEntry
from ..backend import MemoryEntryType
from .path import display_relative_path, is_hidden_path, read_sorted_dir_paths

MAX_LIST_RESULTS = 2_000


async def list(backend: object, request: ListMemoriesRequest) -> ListMemoriesResponse:
    maximum = min(request.max_results, MAX_LIST_RESULTS)
    start = backend.resolve_scoped_path(request.path)
    try:
        start_index = int(request.cursor) if request.cursor is not None else 0
        if start_index < 0:
            raise ValueError
    except ValueError as exc:
        raise MemoriesBackendError.invalid_cursor(
            request.cursor or "", "must be a non-negative integer"
        ) from exc
    if not start.exists():
        raise MemoriesBackendError(f"path '{request.path or ''}' was not found")
    if start.is_symlink():
        raise MemoriesBackendError.invalid_path(
            display_relative_path(backend.root, start), "must not be a symlink"
        )
    entries: list[MemoryEntry] = []
    if start.is_file():
        entries.append(
            MemoryEntry(
                display_relative_path(backend.root, start), MemoryEntryType.FILE
            )
        )
    elif start.is_dir():
        for path in read_sorted_dir_paths(start):
            if is_hidden_path(path) or path.is_symlink():
                continue
            if path.is_dir():
                entry_type = MemoryEntryType.DIRECTORY
            elif path.is_file():
                entry_type = MemoryEntryType.FILE
            else:
                continue
            entries.append(
                MemoryEntry(display_relative_path(backend.root, path), entry_type)
            )
    if start_index > len(entries):
        raise MemoriesBackendError.invalid_cursor(
            str(start_index), "exceeds result count"
        )
    end = min(start_index + maximum, len(entries))
    next_cursor = str(end) if end < len(entries) else None
    return ListMemoriesResponse(
        request.path,
        tuple(entries[start_index:end]),
        next_cursor,
        next_cursor is not None,
    )


__all__ = ["list"]
