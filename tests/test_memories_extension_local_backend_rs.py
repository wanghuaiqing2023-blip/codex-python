from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pycodex.ext.memories.backend import AddAdHocMemoryNoteRequest
from pycodex.ext.memories.backend import ListMemoriesRequest
from pycodex.ext.memories.backend import MemoriesBackendError
from pycodex.ext.memories.backend import MemoryEntryType
from pycodex.ext.memories.backend import ReadMemoryRequest
from pycodex.ext.memories.backend import SearchMatchMode
from pycodex.ext.memories.backend import SearchMemoriesRequest
from pycodex.ext.memories.local import LocalMemoriesBackend


def run(awaitable):
    return asyncio.run(awaitable)


def test_local_list_read_and_search_follow_rust_contract(tmp_path: Path) -> None:
    root = tmp_path / "memories"
    root.mkdir()
    (root / "MEMORY.md").write_text("Alpha\nBeta project\nGamma", encoding="utf-8")
    (root / "nested").mkdir()
    (root / "nested" / "note.md").write_text(
        "alpha on one line\nbeta on another", encoding="utf-8"
    )
    (root / ".hidden.md").write_text("alpha", encoding="utf-8")
    backend = LocalMemoriesBackend.from_memory_root(root)

    listing = run(backend.list(ListMemoriesRequest(None, None, 10)))
    assert [(entry.path, entry.entry_type) for entry in listing.entries] == [
        ("MEMORY.md", MemoryEntryType.FILE),
        ("nested", MemoryEntryType.DIRECTORY),
    ]

    reading = run(backend.read(ReadMemoryRequest("MEMORY.md", 2, 1, 100)))
    assert reading.content == "Beta project\n"
    assert reading.start_line_number == 2
    assert reading.truncated

    searching = run(
        backend.search(
            SearchMemoriesRequest(
                ("alpha", "beta"),
                SearchMatchMode.all_within_lines(2),
                None,
                None,
                0,
                False,
                False,
                10,
            )
        )
    )
    assert [(match.path, match.match_line_number) for match in searching.matches] == [
        ("MEMORY.md", 1),
        ("nested/note.md", 1),
    ]


def test_local_ad_hoc_notes_and_path_guards_match_rust(tmp_path: Path) -> None:
    backend = LocalMemoriesBackend.from_memory_root(tmp_path / "memories")
    request = AddAdHocMemoryNoteRequest(
        "2026-07-27T12-34-56-project-note.md", "Remember this."
    )
    run(backend.add_ad_hoc_note(request))
    note = (
        tmp_path
        / "memories"
        / "extensions"
        / "ad_hoc"
        / "notes"
        / request.filename
    )
    assert note.read_text(encoding="utf-8") == "Remember this."
    with pytest.raises(MemoriesBackendError, match="already exists"):
        run(backend.add_ad_hoc_note(request))
    with pytest.raises(MemoriesBackendError, match="stay within"):
        backend.resolve_scoped_path("../outside")
