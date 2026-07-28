from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.ext.memories.backend import MemoriesBackendError
from pycodex.ext.memories.local.ad_hoc_note import validate_filename
from pycodex.ext.memories.local.path import display_relative_path
from pycodex.ext.memories.local.path import is_hidden_path
from pycodex.ext.memories.local.read import line_end_byte_offset
from pycodex.ext.memories.local.read import line_start_byte_offset


def test_ad_hoc_note_filename_contract_matches_rust() -> None:
    validate_filename("2026-07-27T12-34-56-project-note.md")

    with pytest.raises(MemoriesBackendError, match="must end with .md"):
        validate_filename("note.txt")
    with pytest.raises(MemoriesBackendError, match="must use YYYY-MM-DD"):
        validate_filename("note.md")
    with pytest.raises(MemoriesBackendError, match="lowercase ASCII"):
        validate_filename("2026-07-27T12-34-56-Upper.md")


def test_path_display_and_hidden_contract_matches_rust(tmp_path: Path) -> None:
    nested = tmp_path / "folder" / "note.md"
    assert display_relative_path(tmp_path, nested) == "folder/note.md"
    assert is_hidden_path(tmp_path / ".private")
    assert not is_hidden_path(nested)


def test_line_offsets_use_utf8_byte_positions_like_rust() -> None:
    content = "一\nsecond\nthird"
    second = len("一\n".encode())
    assert line_start_byte_offset(content, 1) == 0
    assert line_start_byte_offset(content, 2) == second
    assert line_end_byte_offset(content, second, 1) == len("一\nsecond\n".encode())
    assert line_end_byte_offset(content, second, None) == len(content.encode())

    with pytest.raises(MemoriesBackendError, match="line_offset exceeds"):
        line_start_byte_offset(content, 5)
