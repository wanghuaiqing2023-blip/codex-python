"""Filesystem backend from Rust ``memories/src/local.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePath

from ..backend import AddAdHocMemoryNoteRequest
from ..backend import AddAdHocMemoryNoteResponse
from ..backend import ListMemoriesRequest
from ..backend import ListMemoriesResponse
from ..backend import MemoriesBackendError
from ..backend import ReadMemoryRequest
from ..backend import ReadMemoryResponse
from ..backend import SearchMemoriesRequest
from ..backend import SearchMemoriesResponse
from . import ad_hoc_note
from . import list as list_module
from . import read as read_module
from . import search as search_module


@dataclass(frozen=True)
class LocalMemoriesBackend:
    root: Path

    @classmethod
    def from_codex_home(cls, codex_home: str | Path) -> "LocalMemoriesBackend":
        return cls.from_memory_root(Path(codex_home) / "memories")

    @classmethod
    def from_memory_root(cls, root: str | Path) -> "LocalMemoriesBackend":
        return cls(Path(root))

    def resolve_scoped_path(self, relative_path: str | None) -> Path:
        if relative_path is None:
            return self.root
        relative = PurePath(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise MemoriesBackendError.invalid_path(
                relative_path, "must stay within the memories root"
            )
        if any(part.startswith(".") for part in relative.parts):
            raise MemoriesBackendError(f"path '{relative_path}' was not found")

        scoped = self.root
        for index, component in enumerate(relative.parts):
            scoped /= component
            if not scoped.exists() and not scoped.is_symlink():
                scoped = scoped.joinpath(*relative.parts[index + 1 :])
                break
            if scoped.is_symlink():
                raise MemoriesBackendError.invalid_path(
                    scoped.relative_to(self.root).as_posix(), "must not be a symlink"
                )
            if index + 1 < len(relative.parts) and not scoped.is_dir():
                raise MemoriesBackendError.invalid_path(
                    relative_path,
                    "traverses through a non-directory path component",
                )
        return scoped

    async def add_ad_hoc_note(
        self, request: AddAdHocMemoryNoteRequest
    ) -> AddAdHocMemoryNoteResponse:
        return await ad_hoc_note.add_ad_hoc_note(self, request)

    async def list(self, request: ListMemoriesRequest) -> ListMemoriesResponse:
        return await list_module.list(self, request)

    async def read(self, request: ReadMemoryRequest) -> ReadMemoryResponse:
        return await read_module.read(self, request)

    async def search(self, request: SearchMemoriesRequest) -> SearchMemoriesResponse:
        return await search_module.search(self, request)


__all__ = ["LocalMemoriesBackend"]
