"""Warnings for ignored ``--add-dir`` entries.

Rust source: ``codex/codex-rs/tui/src/additional_dirs.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="additional_dirs",
    source="codex/codex-rs/tui/src/additional_dirs.rs",
)


class PermissionProfileKind(Enum):
    Disabled = "disabled"
    External = "external"
    WorkspaceWrite = "workspace_write"
    ReadOnly = "read_only"
    Managed = "managed"


@dataclass(eq=True)
class FileSystemPolicy:
    full_disk_write: bool = False
    writable_paths: set[str] = field(default_factory=set)

    def has_full_disk_write_access(self) -> bool:
        return self.full_disk_write

    def can_write_path_with_cwd(self, path: str | Path, cwd: str | Path) -> bool:
        if self.full_disk_write:
            return True
        target = _path_key(path)
        cwd_text = _path_key(cwd)
        return any(
            _path_contains(_path_key(writable_path), target)
            or _path_contains(_path_key(writable_path), cwd_text)
            for writable_path in self.writable_paths
        )


@dataclass(eq=True)
class PermissionProfile:
    kind: PermissionProfileKind
    file_system: FileSystemPolicy = field(default_factory=FileSystemPolicy)

    @classmethod
    def disabled(cls) -> "PermissionProfile":
        return cls(PermissionProfileKind.Disabled, FileSystemPolicy(full_disk_write=True))

    @classmethod
    def external(cls) -> "PermissionProfile":
        return cls(PermissionProfileKind.External)

    @classmethod
    def workspace_write(cls) -> "PermissionProfile":
        return cls(PermissionProfileKind.WorkspaceWrite, FileSystemPolicy(writable_paths={"__cwd__"}))

    @classmethod
    def read_only(cls) -> "PermissionProfile":
        return cls(PermissionProfileKind.ReadOnly, FileSystemPolicy())

    @classmethod
    def managed(cls, writable_paths: Iterable[str] = (), full_disk_write: bool = False) -> "PermissionProfile":
        return cls(
            PermissionProfileKind.Managed,
            FileSystemPolicy(full_disk_write=full_disk_write, writable_paths={_path_key(path) for path in writable_paths}),
        )

    def file_system_sandbox_policy(self, cwd: str | Path | None = None) -> FileSystemPolicy:
        if self.kind is PermissionProfileKind.WorkspaceWrite and cwd is not None:
            return FileSystemPolicy(writable_paths={_path_key(cwd)})
        return self.file_system


def add_dir_warning_message(
    additional_dirs: Iterable[str | Path],
    permission_profile: PermissionProfile | Any,
    cwd: str | Path,
) -> str | None:
    dirs = [_display_path(path) for path in additional_dirs]
    if not dirs:
        return None

    kind = getattr(permission_profile, "kind", None)
    if kind in {PermissionProfileKind.Disabled, PermissionProfileKind.External, "disabled", "external"}:
        return None

    file_system_policy = _file_system_policy(permission_profile, cwd)
    if file_system_policy.has_full_disk_write_access():
        return None

    if file_system_policy.can_write_path_with_cwd(cwd, cwd):
        return None

    return format_warning(dirs)


def format_warning(additional_dirs: Iterable[str | Path]) -> str:
    joined_paths = ", ".join(_display_path(path) for path in additional_dirs)
    return (
        f"Ignoring --add-dir ({joined_paths}) because the effective permissions do not allow "
        "additional writable roots. Switch to workspace-write or danger-full-access to allow them."
    )


def _file_system_policy(permission_profile: Any, cwd: str | Path) -> FileSystemPolicy:
    method = getattr(permission_profile, "file_system_sandbox_policy", None)
    if method is not None:
        try:
            return method(cwd)
        except TypeError:
            return method()
    policy = getattr(permission_profile, "file_system", None)
    if isinstance(policy, FileSystemPolicy):
        return policy
    return FileSystemPolicy()


def _display_path(path: str | Path) -> str:
    return str(path)


def _path_key(path: str | Path) -> str:
    text = str(path).replace("\\", "/")
    while len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    return text


def _path_contains(root: str, candidate: str) -> bool:
    if root == "__cwd__":
        return False
    if root in {"", "."}:
        return candidate in {"", "."}
    if root == "/":
        return candidate.startswith("/")
    return candidate == root or candidate.startswith(root.rstrip("/") + "/")


__all__ = [
    "FileSystemPolicy",
    "PermissionProfile",
    "PermissionProfileKind",
    "RUST_MODULE",
    "add_dir_warning_message",
    "format_warning",
]
