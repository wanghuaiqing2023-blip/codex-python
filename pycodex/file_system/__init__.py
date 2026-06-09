"""Port of Rust ``codex-file-system``.

Rust source:
- ``codex/codex-rs/file-system/src/lib.rs``
"""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CreateDirectoryOptions:
    recursive: bool


@dataclass(frozen=True)
class RemoveOptions:
    recursive: bool
    force: bool


@dataclass(frozen=True)
class CopyOptions:
    recursive: bool


@dataclass(frozen=True)
class FileMetadata:
    is_directory: bool
    is_file: bool
    is_symlink: bool
    created_at_ms: int
    modified_at_ms: int


@dataclass(frozen=True)
class ReadDirectoryEntry:
    file_name: str
    is_directory: bool
    is_file: bool


@dataclass(frozen=True)
class FileSystemSandboxContext:
    permissions: Any
    cwd: Path | None = None
    windows_sandbox_level: Any = "disabled"
    windows_sandbox_private_desktop: bool = False
    use_legacy_landlock: bool = False

    @classmethod
    def from_legacy_sandbox_policy(cls, sandbox_policy: Any, cwd: str | os.PathLike[str]) -> "FileSystemSandboxContext":
        raise NotImplementedError(
            "from_legacy_sandbox_policy requires the protocol permission-profile conversion layer"
        )

    @classmethod
    def from_permission_profile(cls, permissions: Any) -> "FileSystemSandboxContext":
        return cls.from_permissions_and_cwd(permissions, None)

    @classmethod
    def from_permission_profile_with_cwd(
        cls, permissions: Any, cwd: str | os.PathLike[str]
    ) -> "FileSystemSandboxContext":
        return cls.from_permissions_and_cwd(permissions, Path(cwd))

    @classmethod
    def from_permissions_and_cwd(
        cls, permissions: Any, cwd: Path | None
    ) -> "FileSystemSandboxContext":
        return cls(
            permissions=permissions,
            cwd=cwd,
            windows_sandbox_level="disabled",
            windows_sandbox_private_desktop=False,
            use_legacy_landlock=False,
        )

    def should_run_in_sandbox(self) -> bool:
        policy = _file_system_sandbox_policy(self.permissions)
        kind = _get(policy, "kind")
        return _kind_is_restricted(kind) and not _has_full_disk_write_access(policy)

    def has_cwd_dependent_permissions(self) -> bool:
        return file_system_policy_has_cwd_dependent_entries(_file_system_sandbox_policy(self.permissions))

    def drop_cwd_if_unused(self) -> "FileSystemSandboxContext":
        if self.has_cwd_dependent_permissions():
            return self
        return FileSystemSandboxContext(
            permissions=self.permissions,
            cwd=None,
            windows_sandbox_level=self.windows_sandbox_level,
            windows_sandbox_private_desktop=self.windows_sandbox_private_desktop,
            use_legacy_landlock=self.use_legacy_landlock,
        )


def file_system_policy_has_cwd_dependent_entries(file_system_policy: Any) -> bool:
    for entry in _get(file_system_policy, "entries", default=()) or ():
        path = _get(entry, "path", default=entry)
        if _is_relative_glob_pattern(path):
            return True
        if _is_project_roots_special_path(path):
            return True
    return False


class ExecutorFileSystem(ABC):
    @abstractmethod
    async def read_file(self, path: str | os.PathLike[str], sandbox: FileSystemSandboxContext | None = None) -> bytes:
        raise NotImplementedError

    async def read_file_text(self, path: str | os.PathLike[str], sandbox: FileSystemSandboxContext | None = None) -> str:
        return (await self.read_file(path, sandbox)).decode("utf-8")

    @abstractmethod
    async def write_file(
        self, path: str | os.PathLike[str], contents: bytes, sandbox: FileSystemSandboxContext | None = None
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def create_directory(
        self,
        path: str | os.PathLike[str],
        create_directory_options: CreateDirectoryOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_metadata(
        self, path: str | os.PathLike[str], sandbox: FileSystemSandboxContext | None = None
    ) -> FileMetadata:
        raise NotImplementedError

    @abstractmethod
    async def read_directory(
        self, path: str | os.PathLike[str], sandbox: FileSystemSandboxContext | None = None
    ) -> list[ReadDirectoryEntry]:
        raise NotImplementedError

    @abstractmethod
    async def remove(
        self,
        path: str | os.PathLike[str],
        remove_options: RemoveOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def copy(
        self,
        source_path: str | os.PathLike[str],
        destination_path: str | os.PathLike[str],
        copy_options: CopyOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        raise NotImplementedError


class LocalExecutorFileSystem(ExecutorFileSystem):
    async def read_file(self, path: str | os.PathLike[str], sandbox: FileSystemSandboxContext | None = None) -> bytes:
        return Path(path).read_bytes()

    async def write_file(
        self, path: str | os.PathLike[str], contents: bytes, sandbox: FileSystemSandboxContext | None = None
    ) -> None:
        Path(path).write_bytes(contents)

    async def create_directory(
        self,
        path: str | os.PathLike[str],
        create_directory_options: CreateDirectoryOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        Path(path).mkdir(parents=create_directory_options.recursive, exist_ok=create_directory_options.recursive)

    async def get_metadata(
        self, path: str | os.PathLike[str], sandbox: FileSystemSandboxContext | None = None
    ) -> FileMetadata:
        p = Path(path)
        stat = p.stat()
        return FileMetadata(
            is_directory=p.is_dir(),
            is_file=p.is_file(),
            is_symlink=p.is_symlink(),
            created_at_ms=int(stat.st_ctime * 1000),
            modified_at_ms=int(stat.st_mtime * 1000),
        )

    async def read_directory(
        self, path: str | os.PathLike[str], sandbox: FileSystemSandboxContext | None = None
    ) -> list[ReadDirectoryEntry]:
        return [
            ReadDirectoryEntry(file_name=entry.name, is_directory=entry.is_dir(), is_file=entry.is_file())
            for entry in Path(path).iterdir()
        ]

    async def remove(
        self,
        path: str | os.PathLike[str],
        remove_options: RemoveOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        p = Path(path)
        if not p.exists() and remove_options.force:
            return
        if p.is_dir() and not p.is_symlink():
            if remove_options.recursive:
                shutil.rmtree(p)
            else:
                p.rmdir()
            return
        p.unlink(missing_ok=remove_options.force)

    async def copy(
        self,
        source_path: str | os.PathLike[str],
        destination_path: str | os.PathLike[str],
        copy_options: CopyOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        source = Path(source_path)
        destination = Path(destination_path)
        if source.is_dir():
            if not copy_options.recursive:
                raise IsADirectoryError(str(source))
            shutil.copytree(source, destination, dirs_exist_ok=True)
            return
        shutil.copy2(source, destination)


def _file_system_sandbox_policy(permissions: Any) -> Any:
    method = getattr(permissions, "file_system_sandbox_policy", None)
    if callable(method):
        return method()
    if isinstance(permissions, dict):
        return permissions.get("file_system_sandbox_policy") or permissions.get("fileSystemSandboxPolicy") or permissions
    return getattr(permissions, "file_system_sandbox_policy", permissions)


def _kind_is_restricted(kind: Any) -> bool:
    value = getattr(kind, "value", kind)
    return str(value).lower() == "restricted"


def _has_full_disk_write_access(policy: Any) -> bool:
    method = getattr(policy, "has_full_disk_write_access", None)
    if callable(method):
        return bool(method())
    return bool(_get(policy, "has_full_disk_write_access", default=False))


def _is_relative_glob_pattern(path: Any) -> bool:
    pattern = _get(path, "pattern", default=None)
    kind = str(_get(path, "type", default=_get(path, "kind", default=""))).lower()
    if pattern is None or (kind and "glob" not in kind):
        return False
    return not Path(str(pattern)).is_absolute()


def _is_project_roots_special_path(path: Any) -> bool:
    value = _get(path, "value", default=path)
    text = str(getattr(value, "value", value)).lower()
    return "projectroots" in text or "project_roots" in text or "project roots" in text


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "CopyOptions",
    "CreateDirectoryOptions",
    "ExecutorFileSystem",
    "FileMetadata",
    "FileSystemSandboxContext",
    "LocalExecutorFileSystem",
    "ReadDirectoryEntry",
    "RemoveOptions",
    "file_system_policy_has_cwd_dependent_entries",
]
