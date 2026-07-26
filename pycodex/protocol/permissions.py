"""Filesystem and network sandbox protocol types.

Ported from ``codex/codex-rs/protocol/src/permissions.rs``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .protocol import SandboxPolicy, WritableRoot

JsonValue = Any


def _as_mapping(value: JsonValue, label: str = "value") -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _optional_path(value: JsonValue) -> Path | None:
    return None if value is None else Path(str(value))


def _sandbox_policy_type() -> type[SandboxPolicy]:
    from .protocol import SandboxPolicy

    return SandboxPolicy


def _writable_root_type() -> type[WritableRoot]:
    from .protocol import WritableRoot

    return WritableRoot


PROTECTED_METADATA_GIT_PATH_NAME = ".git"


PROTECTED_METADATA_AGENTS_PATH_NAME = ".agents"


PROTECTED_METADATA_CODEX_PATH_NAME = ".codex"


PROTECTED_METADATA_PATH_NAMES = (
    PROTECTED_METADATA_GIT_PATH_NAME,
    PROTECTED_METADATA_AGENTS_PATH_NAME,
    PROTECTED_METADATA_CODEX_PATH_NAME,
)


PROJECT_ROOTS_GLOB_PATTERN_PREFIX = "codex-project-roots://"


class NetworkSandboxPolicy(str, Enum):
    RESTRICTED = "restricted"
    ENABLED = "enabled"

    @classmethod
    def default(cls) -> "NetworkSandboxPolicy":
        return cls.RESTRICTED

    def is_enabled(self) -> bool:
        return self is NetworkSandboxPolicy.ENABLED

    @classmethod
    def parse(cls, value: JsonValue) -> "NetworkSandboxPolicy":
        if not isinstance(value, str):
            raise TypeError("network must be a string")
        return cls(value)


def is_protected_metadata_name(name: str | os.PathLike[str]) -> bool:
    return os.fspath(name) in PROTECTED_METADATA_PATH_NAMES


def is_protected_metadata_directory_name(name: str | os.PathLike[str]) -> bool:
    return os.fspath(name) in {PROTECTED_METADATA_AGENTS_PATH_NAME, PROTECTED_METADATA_CODEX_PATH_NAME}


def project_roots_glob_pattern(subpath: Path | str) -> str:
    return f"{PROJECT_ROOTS_GLOB_PATTERN_PREFIX}{_path_for_glob(Path(subpath))}"


class FileSystemAccessMode(str, Enum):
    READ = "read"
    WRITE = "write"
    DENY = "deny"

    @classmethod
    def parse(cls, value: str) -> "FileSystemAccessMode":
        if not isinstance(value, str):
            raise TypeError("access must be a string")
        if value == "none":
            return cls.DENY
        return cls(value)

    def can_read(self) -> bool:
        return self is not FileSystemAccessMode.DENY

    def can_write(self) -> bool:
        return self is FileSystemAccessMode.WRITE

    def conflict_precedence(self) -> int:
        return {
            FileSystemAccessMode.READ: 0,
            FileSystemAccessMode.WRITE: 1,
            FileSystemAccessMode.DENY: 2,
        }[self]


class FileSystemSandboxKind(str, Enum):
    RESTRICTED = "restricted"
    UNRESTRICTED = "unrestricted"
    EXTERNAL_SANDBOX = "external-sandbox"

    @classmethod
    def default(cls) -> "FileSystemSandboxKind":
        return cls.RESTRICTED


@dataclass(frozen=True)
class FileSystemSpecialPath:
    kind: str
    subpath: Path | None = None
    path: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"root", "minimal", "project_roots", "tmpdir", "slash_tmp", "unknown"}:
            raise ValueError(f"unknown filesystem special path kind: {self.kind}")
        if self.subpath is not None and not isinstance(self.subpath, Path):
            object.__setattr__(self, "subpath", Path(self.subpath))
        if self.kind == "project_roots":
            if self.path is not None:
                raise ValueError("project_roots special path cannot include path")
        elif self.kind == "unknown":
            if not isinstance(self.path, str):
                raise TypeError("unknown special path requires path")
        else:
            if self.subpath is not None:
                raise ValueError(f"{self.kind} special path cannot include subpath")
            if self.path is not None:
                raise ValueError(f"{self.kind} special path cannot include path")

    @classmethod
    def root(cls) -> "FileSystemSpecialPath":
        return cls("root")

    @classmethod
    def minimal(cls) -> "FileSystemSpecialPath":
        return cls("minimal")

    @classmethod
    def project_roots(cls, subpath: Path | str | None = None) -> "FileSystemSpecialPath":
        return cls("project_roots", Path(subpath) if subpath is not None else None)

    @classmethod
    def tmpdir(cls) -> "FileSystemSpecialPath":
        return cls("tmpdir")

    @classmethod
    def slash_tmp(cls) -> "FileSystemSpecialPath":
        return cls("slash_tmp")

    @classmethod
    def unknown(cls, path: str, subpath: Path | str | None = None) -> "FileSystemSpecialPath":
        return cls("unknown", Path(subpath) if subpath is not None else None, path)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FileSystemSpecialPath":
        data = _as_mapping(value, "special path")
        if not isinstance(data.get("kind"), str):
            raise TypeError("kind must be a string")
        kind = data["kind"]
        raw_subpath = data.get("subpath")
        if raw_subpath is not None and not isinstance(raw_subpath, str):
            raise TypeError("subpath must be a string")
        if kind == "root":
            return cls.root()
        if kind == "minimal":
            return cls.minimal()
        if kind in {"project_roots", "current_working_directory"}:
            return cls.project_roots(_optional_path(raw_subpath))
        if kind == "tmpdir":
            return cls.tmpdir()
        if kind == "slash_tmp":
            return cls.slash_tmp()
        if kind == "unknown":
            raw_path = data.get("path")
            if not isinstance(raw_path, str):
                raise TypeError("path must be a string")
            return cls.unknown(raw_path, _optional_path(raw_subpath))
        return cls.unknown(kind, _optional_path(raw_subpath))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"kind": self.kind}
        if self.subpath is not None:
            data["subpath"] = str(self.subpath)
        if self.path is not None:
            data["path"] = self.path
        return data


@dataclass(frozen=True)
class FileSystemPath:
    type: str
    path: Path | None = None
    pattern: str | None = None
    value: FileSystemSpecialPath | None = None

    def __post_init__(self) -> None:
        if self.type not in {"path", "glob_pattern", "special"}:
            raise ValueError(f"unknown filesystem path type: {self.type}")
        if self.type == "path":
            if self.path is None:
                raise TypeError("path filesystem path requires path")
            if not isinstance(self.path, Path):
                object.__setattr__(self, "path", Path(self.path))
            if self.pattern is not None:
                raise ValueError("path filesystem path cannot include pattern")
            if self.value is not None:
                raise ValueError("path filesystem path cannot include value")
        elif self.type == "glob_pattern":
            if not isinstance(self.pattern, str):
                raise TypeError("glob_pattern filesystem path requires pattern")
            if self.path is not None:
                raise ValueError("glob_pattern filesystem path cannot include path")
            if self.value is not None:
                raise ValueError("glob_pattern filesystem path cannot include value")
        elif self.type == "special":
            if not isinstance(self.value, FileSystemSpecialPath):
                raise TypeError("special filesystem path requires FileSystemSpecialPath")
            if self.path is not None:
                raise ValueError("special filesystem path cannot include path")
            if self.pattern is not None:
                raise ValueError("special filesystem path cannot include pattern")

    @classmethod
    def explicit_path(cls, path: Path | str) -> "FileSystemPath":
        return cls(type="path", path=Path(path))

    @classmethod
    def glob_pattern(cls, pattern: str) -> "FileSystemPath":
        return cls(type="glob_pattern", pattern=pattern)

    @classmethod
    def special(cls, value: FileSystemSpecialPath) -> "FileSystemPath":
        return cls(type="special", value=value)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FileSystemPath":
        data = _as_mapping(value, "filesystem path")
        if not isinstance(data.get("type"), str):
            raise TypeError("type must be a string")
        path_type = data["type"]
        if path_type == "path":
            raw_path = data.get("path")
            if not isinstance(raw_path, str):
                raise TypeError("path must be a string")
            return cls.explicit_path(raw_path)
        if path_type == "glob_pattern":
            raw_pattern = data.get("pattern")
            if not isinstance(raw_pattern, str):
                raise TypeError("pattern must be a string")
            return cls.glob_pattern(raw_pattern)
        if path_type == "special":
            return cls.special(FileSystemSpecialPath.from_mapping(data["value"]))
        raise ValueError(f"unknown filesystem path type: {path_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "path":
            return {"type": "path", "path": str(self.path)}
        if self.type == "glob_pattern":
            return {"type": "glob_pattern", "pattern": self.pattern}
        if self.type == "special":
            return {"type": "special", "value": self.value.to_mapping() if self.value is not None else None}
        return {"type": self.type}


@dataclass(frozen=True)
class FileSystemSandboxEntry:
    path: FileSystemPath
    access: FileSystemAccessMode

    def __post_init__(self) -> None:
        if not isinstance(self.path, FileSystemPath):
            raise TypeError("path must be FileSystemPath")
        if not isinstance(self.access, FileSystemAccessMode):
            raise TypeError("access must be FileSystemAccessMode")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FileSystemSandboxEntry":
        data = _as_mapping(value, "filesystem sandbox entry")
        return cls(
            path=FileSystemPath.from_mapping(data["path"]),
            access=FileSystemAccessMode.parse(data["access"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"path": self.path.to_mapping(), "access": self.access.value}


@dataclass(frozen=True)
class FileSystemSemanticSignature:
    has_full_disk_read_access: bool
    has_full_disk_write_access: bool
    include_platform_defaults: bool
    readable_roots: tuple[Path, ...]
    writable_roots: tuple[WritableRoot, ...]
    unreadable_roots: tuple[Path, ...]
    unreadable_globs: tuple[str, ...]


@dataclass(frozen=True)
class FileSystemSandboxPolicy:
    kind: FileSystemSandboxKind = FileSystemSandboxKind.RESTRICTED
    entries: tuple[FileSystemSandboxEntry, ...] = (
        FileSystemSandboxEntry(
            FileSystemPath.special(FileSystemSpecialPath.root()),
            FileSystemAccessMode.READ,
        ),
    )
    glob_scan_max_depth: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FileSystemSandboxKind):
            raise TypeError("kind must be FileSystemSandboxKind")
        if not isinstance(self.entries, tuple):
            object.__setattr__(self, "entries", tuple(self.entries))
        if not all(isinstance(entry, FileSystemSandboxEntry) for entry in self.entries):
            raise TypeError("entries must contain FileSystemSandboxEntry")
        if self.glob_scan_max_depth is not None:
            if isinstance(self.glob_scan_max_depth, bool) or not isinstance(self.glob_scan_max_depth, int):
                raise TypeError("glob_scan_max_depth must be an integer")
            if self.glob_scan_max_depth < 0:
                raise ValueError("glob_scan_max_depth must be non-negative")

    @classmethod
    def default(cls) -> "FileSystemSandboxPolicy":
        return cls()

    @classmethod
    def unrestricted(cls) -> "FileSystemSandboxPolicy":
        return cls(kind=FileSystemSandboxKind.UNRESTRICTED, entries=())

    @classmethod
    def external_sandbox(cls) -> "FileSystemSandboxPolicy":
        return cls(kind=FileSystemSandboxKind.EXTERNAL_SANDBOX, entries=())

    @classmethod
    def restricted(cls, entries: tuple[FileSystemSandboxEntry, ...] | list[FileSystemSandboxEntry]) -> "FileSystemSandboxPolicy":
        return cls(kind=FileSystemSandboxKind.RESTRICTED, entries=tuple(entries))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FileSystemSandboxPolicy":
        data = _as_mapping(value, "filesystem sandbox policy")
        raw_kind = data.get("kind", FileSystemSandboxKind.RESTRICTED.value)
        if not isinstance(raw_kind, str):
            raise TypeError("kind must be a string")
        raw_depth = data.get("glob_scan_max_depth")
        if raw_depth is not None and (isinstance(raw_depth, bool) or not isinstance(raw_depth, int)):
            raise TypeError("glob_scan_max_depth must be an integer")
        entries = data.get("entries", None)
        if entries is None:
            entries_tuple = cls().entries if raw_kind == FileSystemSandboxKind.RESTRICTED.value else ()
        else:
            if not isinstance(entries, list | tuple):
                raise TypeError("entries must be a list")
            entries_tuple = tuple(FileSystemSandboxEntry.from_mapping(item) for item in entries)
        return cls(
            kind=FileSystemSandboxKind(raw_kind),
            entries=entries_tuple,
            glob_scan_max_depth=raw_depth,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"kind": self.kind.value}
        if self.glob_scan_max_depth is not None:
            data["glob_scan_max_depth"] = self.glob_scan_max_depth
        if self.entries:
            data["entries"] = [entry.to_mapping() for entry in self.entries]
        return data

    @classmethod
    def workspace_write(
        cls,
        writable_roots: tuple[Path | str, ...] | list[Path | str] = (),
        exclude_tmpdir_env_var: bool = False,
        exclude_slash_tmp: bool = False,
    ) -> "FileSystemSandboxPolicy":
        if not isinstance(writable_roots, (list, tuple)):
            raise TypeError("writable_roots must be a list or tuple")
        if not all(isinstance(path, (str, Path)) for path in writable_roots):
            raise TypeError("writable_roots entries must be strings or Path")
        if not isinstance(exclude_tmpdir_env_var, bool):
            raise TypeError("exclude_tmpdir_env_var must be a bool")
        if not isinstance(exclude_slash_tmp, bool):
            raise TypeError("exclude_slash_tmp must be a bool")
        entries = [
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
        ]
        if not exclude_slash_tmp:
            entries.append(FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.slash_tmp()), FileSystemAccessMode.WRITE))
        if not exclude_tmpdir_env_var:
            entries.append(FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.tmpdir()), FileSystemAccessMode.WRITE))
        for path in writable_roots:
            entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.WRITE))
        for name in (".git", ".agents", ".codex"):
            entries.append(
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.project_roots(Path(name))),
                    FileSystemAccessMode.READ,
                )
            )
        for path in writable_roots:
            for protected_path in _default_read_only_subpaths_for_writable_root(Path(path), False):
                _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
        return cls.restricted(tuple(entries))

    @classmethod
    def from_legacy_sandbox_policy(cls, sandbox_policy: SandboxPolicy) -> "FileSystemSandboxPolicy":
        if sandbox_policy.type == "danger-full-access":
            return cls.unrestricted()
        if sandbox_policy.type == "external-sandbox":
            return cls.external_sandbox()
        if sandbox_policy.type == "read-only":
            return cls.restricted(
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.root()),
                        FileSystemAccessMode.READ,
                    ),
                )
            )
        if sandbox_policy.type == "workspace-write":
            return cls.workspace_write(
                sandbox_policy.writable_roots,
                sandbox_policy.exclude_tmpdir_env_var,
                sandbox_policy.exclude_slash_tmp,
            )
        raise ValueError(f"unknown sandbox policy type: {sandbox_policy.type}")

    @classmethod
    def from_legacy_sandbox_policy_for_cwd(
        cls,
        sandbox_policy: SandboxPolicy,
        cwd: Path | str,
    ) -> "FileSystemSandboxPolicy":
        policy = cls.from_legacy_sandbox_policy(sandbox_policy)
        if sandbox_policy.type != "workspace-write":
            return policy
        entries = list(policy.entries)
        cwd = Path(cwd)
        if cwd.is_absolute():
            for protected_path in _default_read_only_subpaths_for_writable_root(cwd, True):
                _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
        for writable_root in sandbox_policy.writable_roots:
            for protected_path in _default_read_only_subpaths_for_writable_root(writable_root, False):
                _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
        return policy._replace(entries=tuple(entries))

    @classmethod
    def from_legacy_sandbox_policy_preserving_deny_entries(
        cls,
        sandbox_policy: SandboxPolicy,
        cwd: Path | str,
        existing: "FileSystemSandboxPolicy",
    ) -> "FileSystemSandboxPolicy":
        rebuilt = cls.from_legacy_sandbox_policy_for_cwd(sandbox_policy, cwd)
        if rebuilt.kind is not FileSystemSandboxKind.RESTRICTED:
            return rebuilt
        entries = list(rebuilt.entries)
        for deny_entry in existing.entries:
            if deny_entry.access is FileSystemAccessMode.DENY and deny_entry not in entries:
                entries.append(deny_entry)
        return rebuilt._replace(entries=tuple(entries), glob_scan_max_depth=existing.glob_scan_max_depth)

    def has_denied_read_restrictions(self) -> bool:
        return self.kind is FileSystemSandboxKind.RESTRICTED and any(
            entry.access is FileSystemAccessMode.DENY for entry in self.entries
        )

    def has_root_access(self, predicate) -> bool:
        return self.kind is FileSystemSandboxKind.RESTRICTED and any(
            entry.path.type == "special"
            and entry.path.value == FileSystemSpecialPath.root()
            and predicate(entry.access)
            for entry in self.entries
        )

    def has_full_disk_read_access(self) -> bool:
        if self.kind in {FileSystemSandboxKind.UNRESTRICTED, FileSystemSandboxKind.EXTERNAL_SANDBOX}:
            return True
        return self.has_root_access(lambda access: access.can_read()) and not self.has_denied_read_restrictions()

    def has_full_disk_write_access(self) -> bool:
        if self.kind in {FileSystemSandboxKind.UNRESTRICTED, FileSystemSandboxKind.EXTERNAL_SANDBOX}:
            return True
        return self.has_root_access(lambda access: access.can_write()) and not self._has_write_narrowing_entries()

    def include_platform_defaults(self) -> bool:
        return (
            not self.has_full_disk_read_access()
            and self.kind is FileSystemSandboxKind.RESTRICTED
            and any(
                entry.path.type == "special"
                and entry.path.value == FileSystemSpecialPath.minimal()
                and entry.access.can_read()
                for entry in self.entries
            )
        )

    def preserve_deny_read_restrictions_from(
        self,
        existing: "FileSystemSandboxPolicy",
    ) -> "FileSystemSandboxPolicy":
        has_deny_read_entries = any(entry.access is FileSystemAccessMode.DENY for entry in existing.entries)
        policy = self
        if self.kind is FileSystemSandboxKind.UNRESTRICTED and has_deny_read_entries:
            policy = FileSystemSandboxPolicy.restricted(
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.root()),
                        FileSystemAccessMode.WRITE,
                    ),
                )
            )

        if policy.kind is not FileSystemSandboxKind.RESTRICTED:
            return policy

        entries = list(policy.entries)
        for deny_entry in existing.entries:
            if deny_entry.access is FileSystemAccessMode.DENY and deny_entry not in entries:
                entries.append(deny_entry)
        glob_scan_max_depth = policy.glob_scan_max_depth
        if glob_scan_max_depth is None:
            glob_scan_max_depth = existing.glob_scan_max_depth
        return policy._replace(entries=tuple(entries), glob_scan_max_depth=glob_scan_max_depth)

    def resolve_access_with_cwd(self, path: Path | str, cwd: Path | str) -> FileSystemAccessMode:
        if self.kind in {FileSystemSandboxKind.UNRESTRICTED, FileSystemSandboxKind.EXTERNAL_SANDBOX}:
            return FileSystemAccessMode.WRITE
        target = _resolve_candidate_path(Path(path), Path(cwd))
        if target is None:
            return FileSystemAccessMode.DENY
        matching = [
            entry
            for entry in self._resolved_entries_with_cwd(Path(cwd))
            if _path_starts_with(target, entry.path)
        ]
        if not matching:
            return FileSystemAccessMode.DENY
        return max(matching, key=lambda entry: (len(entry.path.parts), entry.access.conflict_precedence())).access

    def can_read_path_with_cwd(self, path: Path | str, cwd: Path | str) -> bool:
        return self.resolve_access_with_cwd(path, cwd).can_read()

    def can_write_path_with_cwd(self, path: Path | str, cwd: Path | str) -> bool:
        if not self.resolve_access_with_cwd(path, cwd).can_write():
            return False
        if self.has_full_disk_write_access():
            return True
        return not self._is_metadata_write_denied(Path(path), Path(cwd))

    def materialize_project_roots_with_cwd(self, cwd: Path | str) -> "FileSystemSandboxPolicy":
        cwd = Path(cwd)
        cwd_root = cwd if cwd.is_absolute() else None
        entries: list[FileSystemSandboxEntry] = []
        for entry in self.entries:
            path = entry.path
            if path.type == "special" and path.value is not None and path.value.kind == "project_roots":
                resolved_path = _resolve_file_system_path(path, cwd_root)
                if resolved_path is not None:
                    entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(resolved_path), entry.access))
                    continue
            if path.type == "glob_pattern" and path.pattern is not None and cwd_root is not None:
                subpath = _parse_project_roots_glob_pattern(path.pattern)
                if subpath is not None:
                    entries.append(
                        FileSystemSandboxEntry(
                            FileSystemPath.glob_pattern(_resolve_project_roots_glob_pattern(subpath, cwd_root)),
                            entry.access,
                        )
                    )
                    continue
            entries.append(entry)
        return self._replace(entries=tuple(entries))

    def materialize_project_roots_with_workspace_roots(
        self,
        workspace_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "FileSystemSandboxPolicy":
        roots = tuple(Path(root) for root in workspace_roots)
        entries: list[FileSystemSandboxEntry] = []
        for entry in self.entries:
            path = entry.path
            if path.type == "special" and path.value is not None and path.value.kind == "project_roots":
                subpath = path.value.subpath
                for root in roots:
                    resolved_path = _resolve_against_base(subpath or Path("."), root)
                    entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(resolved_path), entry.access))
                continue
            if path.type == "glob_pattern" and path.pattern is not None:
                subpath = _parse_project_roots_glob_pattern(path.pattern)
                if subpath is not None:
                    for root in roots:
                        entries.append(
                            FileSystemSandboxEntry(
                                FileSystemPath.glob_pattern(_resolve_project_roots_glob_pattern(subpath, root)),
                                entry.access,
                            )
                        )
                    continue
            entries.append(entry)
        return self._replace(entries=tuple(entries))

    def with_materialized_project_roots_for_workspace_roots(
        self,
        workspace_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "FileSystemSandboxPolicy":
        entries = list(self.entries)
        materialized = self.materialize_project_roots_with_workspace_roots(workspace_roots)
        for entry in materialized.entries:
            if entry not in entries:
                entries.append(entry)
        return self._replace(entries=tuple(entries))

    def with_additional_readable_roots(
        self,
        cwd: Path | str,
        additional_readable_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "FileSystemSandboxPolicy":
        if self.has_full_disk_read_access():
            return self
        cwd = Path(cwd)
        entries = list(self.entries)
        for path in additional_readable_roots:
            path = Path(path)
            if self.can_read_path_with_cwd(path, cwd):
                continue
            entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.READ))
        return self._replace(entries=tuple(entries))

    def with_additional_writable_roots(
        self,
        cwd: Path | str,
        additional_writable_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "FileSystemSandboxPolicy":
        cwd = Path(cwd)
        entries = list(self.entries)
        for path in additional_writable_roots:
            path = Path(path)
            if self.can_write_path_with_cwd(path, cwd):
                continue
            entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.WRITE))
        return self._replace(entries=tuple(entries))

    def with_additional_legacy_workspace_writable_roots(
        self,
        additional_writable_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "FileSystemSandboxPolicy":
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return self
        entries = list(self.entries)
        for path in additional_writable_roots:
            path = Path(path)
            entry_path = FileSystemPath.explicit_path(path)
            if not any(entry.access.can_write() and entry.path == entry_path for entry in entries):
                entries.append(FileSystemSandboxEntry(entry_path, FileSystemAccessMode.WRITE))
            for protected_path in _default_read_only_subpaths_for_writable_root(path, False):
                _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
        return self._replace(entries=tuple(entries))

    def get_readable_roots_with_cwd(self, cwd: Path | str) -> tuple[Path, ...]:
        if self.has_full_disk_read_access():
            return ()
        cwd = Path(cwd)
        roots = [
            entry.path
            for entry in self._resolved_entries_with_cwd(cwd)
            if entry.access.can_read() and self.can_read_path_with_cwd(entry.path, cwd)
        ]
        return tuple(_dedup_paths(roots, normalize=True))

    def get_writable_roots_with_cwd(self, cwd: Path | str) -> tuple[WritableRoot, ...]:
        if self.has_full_disk_write_access():
            return ()
        cwd = Path(cwd)
        resolved_entries = self._resolved_entries_with_cwd(cwd)
        writable_entries = [
            entry.path
            for entry in resolved_entries
            if entry.access.can_write() and self.can_write_path_with_cwd(entry.path, cwd)
        ]
        writable_roots: list[WritableRoot] = []
        for root in _dedup_paths(writable_entries.copy(), normalize=True):
            raw_writable_roots = [
                path for path in writable_entries if _normalize_effective_absolute_path(path) == root
            ]
            protected_metadata_names = _protected_metadata_names_for_writable_root(
                self,
                root,
                raw_writable_roots,
                cwd,
            )
            protect_missing_dot_codex = _normalize_effective_absolute_path(_resolve_base_cwd(cwd)) == root
            read_only_subpaths = [
                path
                for path in _default_read_only_subpaths_for_writable_root(root, protect_missing_dot_codex)
                if not _has_explicit_resolved_path_entry(resolved_entries, path)
            ]
            for entry in resolved_entries:
                if entry.access.can_write() or self.can_write_path_with_cwd(entry.path, cwd):
                    continue
                effective_path = _normalize_effective_absolute_path(entry.path)
                if effective_path != root and _path_starts_with(effective_path, root):
                    read_only_subpaths.append(effective_path)
            writable_roots.append(
                _writable_root_type()(
                    root=root,
                    read_only_subpaths=tuple(_dedup_paths(read_only_subpaths, normalize=False)),
                    protected_metadata_names=tuple(protected_metadata_names),
                )
            )
        return tuple(writable_roots)

    def get_unreadable_roots_with_cwd(self, cwd: Path | str) -> tuple[Path, ...]:
        cwd = Path(cwd)
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return ()
        root = _absolute_root_path_for_cwd(cwd)
        roots = [
            entry.path
            for entry in self._resolved_entries_with_cwd(cwd)
            if entry.access is FileSystemAccessMode.DENY
            and not self.can_read_path_with_cwd(entry.path, cwd)
            and entry.path != root
        ]
        return tuple(_dedup_paths(roots, normalize=True))

    def get_unreadable_globs_with_cwd(self, cwd: Path | str) -> tuple[str, ...]:
        cwd = Path(cwd)
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return ()
        patterns = []
        for entry in self.entries:
            if entry.access is FileSystemAccessMode.DENY and entry.path.type == "glob_pattern" and entry.path.pattern is not None:
                if (subpath := _parse_project_roots_glob_pattern(entry.path.pattern)) is not None:
                    patterns.append(_resolve_project_roots_glob_pattern(subpath, cwd))
                else:
                    patterns.append(str(_resolve_against_base(entry.path.pattern, cwd)))
        return tuple(sorted(set(patterns)))

    def semantic_signature(self, cwd: Path | str) -> FileSystemSemanticSignature:
        cwd = Path(cwd)
        return FileSystemSemanticSignature(
            has_full_disk_read_access=self.has_full_disk_read_access(),
            has_full_disk_write_access=self.has_full_disk_write_access(),
            include_platform_defaults=self.include_platform_defaults(),
            readable_roots=_sorted_paths(self.get_readable_roots_with_cwd(cwd)),
            writable_roots=_sorted_writable_roots(self.get_writable_roots_with_cwd(cwd)),
            unreadable_roots=_sorted_paths(self.get_unreadable_roots_with_cwd(cwd)),
            unreadable_globs=self.get_unreadable_globs_with_cwd(cwd),
        )

    def is_semantically_equivalent_to(
        self,
        other: "FileSystemSandboxPolicy",
        cwd: Path | str,
    ) -> bool:
        return self.semantic_signature(cwd) == other.semantic_signature(cwd)

    def to_legacy_sandbox_policy(
        self,
        network_policy: NetworkSandboxPolicy,
        cwd: Path | str,
    ) -> SandboxPolicy:
        if self.kind is FileSystemSandboxKind.EXTERNAL_SANDBOX:
            return _sandbox_policy_type().external_sandbox(network_policy)
        if self.kind is FileSystemSandboxKind.UNRESTRICTED:
            if network_policy.is_enabled():
                return _sandbox_policy_type().danger_full_access()
            return _sandbox_policy_type().external_sandbox(NetworkSandboxPolicy.RESTRICTED)

        cwd = Path(cwd)
        cwd_absolute = cwd if cwd.is_absolute() else None
        has_full_disk_write_access = self.has_full_disk_write_access()
        workspace_root_writable = False
        writable_roots: list[Path] = []
        tmpdir_writable = False
        slash_tmp_writable = False
        unbridgeable_root_write = False

        for entry in self.entries:
            if entry.path.type == "glob_pattern":
                continue
            if entry.path.type == "path" and entry.path.path is not None:
                if entry.access.can_write():
                    if cwd_absolute is not None and entry.path.path == cwd_absolute:
                        workspace_root_writable = True
                    else:
                        writable_roots.append(entry.path.path)
                continue
            if entry.path.type == "special" and entry.path.value is not None:
                value = entry.path.value
                if value.kind == "root":
                    if entry.access is FileSystemAccessMode.WRITE:
                        unbridgeable_root_write = True
                elif value.kind == "project_roots":
                    if value.subpath is None and entry.access.can_write():
                        workspace_root_writable = True
                    elif entry.access.can_write():
                        resolved_path = _resolve_file_system_special_path(value, cwd_absolute)
                        if resolved_path is not None:
                            writable_roots.append(resolved_path)
                elif value.kind == "tmpdir" and entry.access.can_write():
                    tmpdir_writable = True
                elif value.kind == "slash_tmp" and entry.access.can_write():
                    slash_tmp_writable = True

        if has_full_disk_write_access:
            if network_policy.is_enabled():
                return _sandbox_policy_type().danger_full_access()
            return _sandbox_policy_type().external_sandbox(NetworkSandboxPolicy.RESTRICTED)

        if workspace_root_writable:
            return _sandbox_policy_type().workspace_write(
                _dedup_paths(writable_roots, normalize=False),
                network_access=network_policy.is_enabled(),
                exclude_tmpdir_env_var=not tmpdir_writable,
                exclude_slash_tmp=not slash_tmp_writable,
            )
        if unbridgeable_root_write or writable_roots or tmpdir_writable or slash_tmp_writable:
            raise ValueError(
                "permissions profile requests filesystem writes outside the workspace root, "
                "which is not supported until the runtime enforces FileSystemSandboxPolicy directly"
            )
        return _sandbox_policy_type().read_only(network_access=network_policy.is_enabled())

    def needs_direct_runtime_enforcement(
        self,
        network_policy: NetworkSandboxPolicy,
        cwd: Path | str,
    ) -> bool:
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return False
        try:
            legacy_policy = self.to_legacy_sandbox_policy(network_policy, cwd)
        except ValueError:
            return True
        if _protected_metadata_names_need_direct_runtime_enforcement(self, legacy_policy, Path(cwd)):
            return True
        return self.semantic_signature(cwd) != _legacy_runtime_file_system_policy_for_cwd(legacy_policy, cwd).semantic_signature(cwd)

    def _has_write_narrowing_entries(self) -> bool:
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return False
        for entry in self.entries:
            if entry.access.can_write():
                continue
            if entry.path.type == "glob_pattern":
                return True
            if entry.path.type == "special" and entry.path.value is not None:
                if entry.path.value == FileSystemSpecialPath.root():
                    if entry.access is FileSystemAccessMode.DENY:
                        return True
                    continue
                if entry.path.value.kind in {"minimal", "unknown"}:
                    continue
            if not self._has_same_target_write_override(entry):
                return True
        return False

    def _has_same_target_write_override(self, entry: FileSystemSandboxEntry) -> bool:
        return any(
            candidate.access.can_write()
            and candidate.access.conflict_precedence() > entry.access.conflict_precedence()
            and _file_system_paths_share_target(candidate.path, entry.path)
            for candidate in self.entries
        )

    def _resolved_entries_with_cwd(self, cwd: Path) -> tuple["_ResolvedFileSystemEntry", ...]:
        resolved = []
        for entry in self.entries:
            path = _resolve_entry_path(entry.path, cwd)
            if path is not None:
                resolved.append(_ResolvedFileSystemEntry(path, entry.access))
        return tuple(resolved)

    def _is_metadata_write_denied(self, path: Path, cwd: Path) -> bool:
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return False
        target = _resolve_candidate_path(path, cwd)
        if target is None:
            return True
        metadata = _metadata_child_of_writable_root(self, target, cwd)
        if metadata is None:
            return False
        protected_metadata_path, _ = metadata
        return not _has_explicit_write_entry_for_metadata_path(self, protected_metadata_path, target, cwd)

    def _replace(
        self,
        *,
        entries: tuple[FileSystemSandboxEntry, ...] | None = None,
        glob_scan_max_depth: int | None = None,
    ) -> "FileSystemSandboxPolicy":
        return FileSystemSandboxPolicy(
            kind=self.kind,
            entries=self.entries if entries is None else entries,
            glob_scan_max_depth=self.glob_scan_max_depth if glob_scan_max_depth is None else glob_scan_max_depth,
        )


@dataclass(frozen=True)
class _ResolvedFileSystemEntry:
    path: Path
    access: FileSystemAccessMode


class ReadDenyMatcher:
    def __init__(
        self,
        denied_candidates: tuple[tuple[Path, ...], ...],
        deny_read_matchers: tuple[re.Pattern[str], ...],
        invalid_pattern: bool = False,
    ) -> None:
        self.denied_candidates = denied_candidates
        self.deny_read_matchers = deny_read_matchers
        self.invalid_pattern = invalid_pattern

    @classmethod
    def new(cls, file_system_sandbox_policy: FileSystemSandboxPolicy, cwd: Path | str) -> "ReadDenyMatcher | None":
        return cls._build(file_system_sandbox_policy, Path(cwd), fail_closed=True)

    @classmethod
    def try_new(cls, file_system_sandbox_policy: FileSystemSandboxPolicy, cwd: Path | str) -> "ReadDenyMatcher | None":
        return cls._build(file_system_sandbox_policy, Path(cwd), fail_closed=False)

    @classmethod
    def _build(
        cls,
        file_system_sandbox_policy: FileSystemSandboxPolicy,
        cwd: Path,
        fail_closed: bool,
    ) -> "ReadDenyMatcher | None":
        if not file_system_sandbox_policy.has_denied_read_restrictions():
            return None
        denied_candidates = tuple(
            tuple(_normalized_and_canonical_candidates(path))
            for path in file_system_sandbox_policy.get_unreadable_roots_with_cwd(cwd)
        )
        matchers: list[re.Pattern[str]] = []
        invalid_pattern = False
        for pattern in file_system_sandbox_policy.get_unreadable_globs_with_cwd(cwd):
            try:
                matchers.append(_build_glob_matcher(pattern))
            except ValueError as exc:
                if fail_closed:
                    invalid_pattern = True
                else:
                    raise ValueError(
                        f"invalid deny-read glob pattern `{pattern}`: {exc}"
                    ) from exc
        return cls(denied_candidates, tuple(matchers), invalid_pattern)

    def is_read_denied(self, path: Path | str) -> bool:
        if self.invalid_pattern:
            return True
        path_candidates = _normalized_and_canonical_candidates(Path(path))
        if any(
            candidate == denied_candidate or _path_starts_with(candidate, denied_candidate)
            for denied_group in self.denied_candidates
            for candidate in path_candidates
            for denied_candidate in denied_group
        ):
            return True
        path_strings = [_path_for_glob(candidate) for candidate in path_candidates]
        return any(matcher.fullmatch(path_string) for matcher in self.deny_read_matchers for path_string in path_strings)


def forbidden_agent_metadata_write(
    path: Path | str,
    cwd: Path | str,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
) -> str | None:
    if file_system_sandbox_policy.kind is not FileSystemSandboxKind.RESTRICTED:
        return None
    cwd = Path(cwd)
    target = _resolve_candidate_path(Path(path), cwd)
    if target is None:
        return None
    metadata = _metadata_child_of_writable_root(file_system_sandbox_policy, target, cwd)
    if metadata is None:
        return None
    protected_metadata_path, metadata_name = metadata
    if _has_explicit_write_entry_for_metadata_path(file_system_sandbox_policy, protected_metadata_path, target, cwd):
        return None
    if not file_system_sandbox_policy.can_write_path_with_cwd(target, cwd):
        return metadata_name
    return None


def _resolve_file_system_path(path: FileSystemPath, cwd: Path | None) -> Path | None:
    if path.type == "path":
        return path.path
    if path.type == "glob_pattern":
        return None
    if path.type == "special" and path.value is not None:
        return _resolve_file_system_special_path(path.value, cwd)
    return None


def _resolve_entry_path(path: FileSystemPath, cwd: Path) -> Path | None:
    if path.type == "special" and path.value == FileSystemSpecialPath.root():
        return _absolute_root_path_for_cwd(cwd)
    return _resolve_file_system_path(path, cwd)


def _resolve_file_system_special_path(value: FileSystemSpecialPath, cwd: Path | None) -> Path | None:
    if value.kind in {"root", "minimal", "unknown"}:
        return None
    if value.kind == "project_roots":
        if cwd is None:
            return None
        return _resolve_against_base(value.subpath or Path("."), _resolve_base_cwd(cwd))
    if value.kind == "tmpdir":
        raw = os.environ.get("TMPDIR")
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_absolute() else None
    if value.kind == "slash_tmp":
        slash_tmp = Path("/tmp")
        return slash_tmp if slash_tmp.is_dir() else None
    return None


def _resolve_candidate_path(path: Path, cwd: Path) -> Path | None:
    if path.is_absolute():
        return path
    return _resolve_base_cwd(cwd) / path


def _resolve_against_base(path: Path | str, base: Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else _resolve_base_cwd(base) / path


def _resolve_base_cwd(cwd: Path) -> Path:
    return cwd if cwd.is_absolute() else Path.cwd() / cwd


def _absolute_root_path_for_cwd(cwd: Path) -> Path:
    if cwd.anchor:
        return Path(cwd.anchor)
    return Path("/")


def _file_system_paths_share_target(left: FileSystemPath, right: FileSystemPath) -> bool:
    if left.type == "path" and right.type == "path":
        return left.path == right.path
    if left.type == "special" and right.type == "special":
        return _special_paths_share_target(left.value, right.value)
    if left.type == "path" and right.type == "special" and left.path is not None and right.value is not None:
        return _special_path_matches_absolute_path(right.value, left.path)
    if left.type == "special" and right.type == "path" and left.value is not None and right.path is not None:
        return _special_path_matches_absolute_path(left.value, right.path)
    if left.type == "glob_pattern" and right.type == "glob_pattern":
        return left.pattern == right.pattern
    return False


def _special_paths_share_target(left: FileSystemSpecialPath | None, right: FileSystemSpecialPath | None) -> bool:
    if left is None or right is None:
        return False
    return left == right


def _special_path_matches_absolute_path(value: FileSystemSpecialPath, path: Path) -> bool:
    if value.kind == "root":
        return path == _absolute_root_path_for_cwd(path)
    if value.kind == "slash_tmp":
        return path == Path("/tmp")
    return False


def _metadata_path_name(name: str) -> str | None:
    return name if name in PROTECTED_METADATA_PATH_NAMES else None


def _metadata_child_of_writable_root(
    policy: FileSystemSandboxPolicy,
    target: Path,
    cwd: Path,
) -> tuple[Path, str] | None:
    for entry in policy._resolved_entries_with_cwd(cwd):
        if not entry.access.can_write():
            continue
        relative = _strip_prefix(target, entry.path)
        if relative is None or relative == Path(".") or not relative.parts:
            continue
        metadata_name = _metadata_path_name(relative.parts[0])
        if metadata_name is not None:
            return entry.path / metadata_name, metadata_name
    return None


def _has_explicit_write_entry_for_metadata_path(
    policy: FileSystemSandboxPolicy,
    protected_metadata_path: Path,
    target: Path,
    cwd: Path,
) -> bool:
    return any(
        entry.access.can_write()
        and _path_starts_with(target, entry.path)
        and _path_starts_with(entry.path, protected_metadata_path)
        for entry in policy._resolved_entries_with_cwd(cwd)
    )


def _legacy_runtime_file_system_policy_for_cwd(
    sandbox_policy: SandboxPolicy,
    cwd: Path | str,
) -> FileSystemSandboxPolicy:
    if sandbox_policy.type != "workspace-write":
        return FileSystemSandboxPolicy.from_legacy_sandbox_policy(sandbox_policy)

    entries = [
        FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.READ),
        FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
    ]
    if not sandbox_policy.exclude_slash_tmp:
        entries.append(FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.slash_tmp()), FileSystemAccessMode.WRITE))
    if not sandbox_policy.exclude_tmpdir_env_var:
        entries.append(FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.tmpdir()), FileSystemAccessMode.WRITE))
    for writable_root in sandbox_policy.writable_roots:
        entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(writable_root), FileSystemAccessMode.WRITE))

    cwd = Path(cwd)
    if cwd.is_absolute():
        for protected_path in _default_read_only_subpaths_for_writable_root(cwd, True):
            _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
    for writable_root in sandbox_policy.writable_roots:
        for protected_path in _default_read_only_subpaths_for_writable_root(writable_root, False):
            _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
    return FileSystemSandboxPolicy.restricted(tuple(entries))


def _protected_metadata_names_need_direct_runtime_enforcement(
    policy: FileSystemSandboxPolicy,
    legacy_policy: SandboxPolicy,
    cwd: Path,
) -> bool:
    legacy_roots = legacy_policy.get_writable_roots_with_cwd(cwd)
    for writable_root in policy.get_writable_roots_with_cwd(cwd):
        legacy_root = next((candidate for candidate in legacy_roots if candidate.root == writable_root.root), None)
        if legacy_root is None:
            if writable_root.protected_metadata_names:
                return True
            continue
        for metadata_name in writable_root.protected_metadata_names:
            metadata_path = writable_root.root / metadata_name
            if not any(subpath == metadata_path for subpath in legacy_root.read_only_subpaths):
                return True
    return False


def _protected_metadata_names_for_writable_root(
    policy: FileSystemSandboxPolicy,
    root: Path,
    raw_writable_roots: list[Path],
    cwd: Path,
) -> list[str]:
    protected_names = []
    for metadata_name in PROTECTED_METADATA_PATH_NAMES:
        metadata_paths = [root / metadata_name]
        metadata_paths.extend(raw_root / metadata_name for raw_root in raw_writable_roots)
        if all(not policy.can_write_path_with_cwd(metadata_path, cwd) for metadata_path in metadata_paths):
            protected_names.append(metadata_name)
    return protected_names


def _default_read_only_subpaths_for_writable_root(writable_root: Path, protect_missing_dot_codex: bool) -> list[Path]:
    subpaths: list[Path] = []
    top_level_git = writable_root / PROTECTED_METADATA_GIT_PATH_NAME
    if top_level_git.is_dir() or top_level_git.is_file():
        subpaths.append(top_level_git)

    top_level_agents = writable_root / PROTECTED_METADATA_AGENTS_PATH_NAME
    if top_level_agents.is_dir():
        subpaths.append(top_level_agents)

    top_level_codex = writable_root / PROTECTED_METADATA_CODEX_PATH_NAME
    if protect_missing_dot_codex or top_level_codex.is_dir():
        subpaths.append(top_level_codex)

    return _dedup_paths(subpaths, normalize=False)


def _append_default_read_only_path_if_no_explicit_rule(
    entries: list[FileSystemSandboxEntry],
    path: Path,
) -> None:
    file_system_path = FileSystemPath.explicit_path(path)
    if any(_file_system_paths_share_target(entry.path, file_system_path) for entry in entries):
        return
    entries.append(FileSystemSandboxEntry(file_system_path, FileSystemAccessMode.READ))


def _has_explicit_resolved_path_entry(resolved_entries: tuple[_ResolvedFileSystemEntry, ...], path: Path) -> bool:
    return any(entry.path == path for entry in resolved_entries)


def _parse_project_roots_glob_pattern(pattern: str) -> Path | None:
    if not pattern.startswith(PROJECT_ROOTS_GLOB_PATTERN_PREFIX):
        return None
    return Path(pattern[len(PROJECT_ROOTS_GLOB_PATTERN_PREFIX) :])


def _resolve_project_roots_glob_pattern(subpath: Path, root: Path) -> str:
    return str(_resolve_against_base(subpath, root))


def _normalized_and_canonical_candidates(path: Path) -> tuple[Path, ...]:
    candidates = [path]
    try:
        canonical = path.resolve(strict=True)
    except OSError:
        canonical = None
    if canonical is not None and canonical not in candidates:
        candidates.append(canonical)
    return tuple(candidates)


def _dedup_paths(paths: list[Path], normalize: bool) -> list[Path]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        candidate = _normalize_effective_absolute_path(path) if normalize else path
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def _sorted_paths(paths: tuple[Path, ...] | list[Path]) -> tuple[Path, ...]:
    return tuple(sorted(paths, key=lambda path: str(path)))


def _sorted_writable_roots(roots: tuple[WritableRoot, ...] | list[WritableRoot]) -> tuple[WritableRoot, ...]:
    normalized = [
        _writable_root_type()(
            root=root.root,
            read_only_subpaths=_sorted_paths(tuple(root.read_only_subpaths)),
            protected_metadata_names=tuple(sorted(set(root.protected_metadata_names))),
        )
        for root in roots
    ]
    return tuple(sorted(normalized, key=lambda root: str(root.root)))


def _normalize_effective_absolute_path(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError:
        return path


def _strip_prefix(path: Path, prefix: Path) -> Path | None:
    try:
        relative = path.relative_to(prefix)
    except ValueError:
        return None
    return relative if str(relative) != "" else Path(".")


def _path_starts_with(path: Path, prefix: Path) -> bool:
    return _strip_prefix(path, prefix) is not None


def _build_glob_matcher(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(_glob_to_regex(_path_for_glob(Path(pattern))))
    except re.error as exc:
        raise ValueError(str(exc)) from exc


def _path_for_glob(path: Path) -> str:
    return str(path).replace("\\", "/")


def _glob_to_regex(pattern: str) -> str:
    index = 0
    out = ["^"]
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    out.append("(?:.*/)?")
                    index += 1
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = pattern.find("]", index + 1)
            if end == -1:
                out.append(re.escape("["))
            else:
                content = pattern[index + 1 : end]
                if content.startswith("!"):
                    content = "^" + re.escape(content[1:])
                else:
                    content = re.escape(content).replace("\\-", "-")
                out.append(f"[{content}]")
                index = end
        else:
            out.append(re.escape(char))
        index += 1
    out.append("$")
    return "".join(out)
