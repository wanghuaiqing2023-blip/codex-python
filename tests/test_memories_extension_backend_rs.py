from __future__ import annotations

from pycodex.ext.memories.backend import MemoriesBackendError
from pycodex.ext.memories.backend import MemoryEntryType
from pycodex.ext.memories.backend import SearchMatchMode
from pycodex.ext.memories.backend import SearchMatchModeKind


def test_search_match_modes_match_rust_tagged_variants() -> None:
    assert SearchMatchMode.any() == SearchMatchMode(SearchMatchModeKind.ANY)
    assert SearchMatchMode.all_on_same_line() == SearchMatchMode(
        SearchMatchModeKind.ALL_ON_SAME_LINE
    )
    assert SearchMatchMode.all_within_lines(3) == SearchMatchMode(
        SearchMatchModeKind.ALL_WITHIN_LINES,
        3,
    )
    assert MemoryEntryType.FILE.value == "file"
    assert MemoryEntryType.DIRECTORY.value == "directory"


def test_backend_error_helpers_match_rust_display_contract() -> None:
    assert (
        str(MemoriesBackendError.invalid_filename("note.md", "is invalid"))
        == "filename 'note.md' is invalid"
    )
    assert (
        str(MemoriesBackendError.invalid_path("nested", "escapes the memory root"))
        == "path 'nested' escapes the memory root"
    )
    assert (
        str(MemoriesBackendError.invalid_cursor("abc", "is malformed"))
        == "cursor 'abc' is malformed"
    )
