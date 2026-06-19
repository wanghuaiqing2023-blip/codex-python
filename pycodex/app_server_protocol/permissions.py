"""Permission protocol types ported from ``protocol/v2/permissions.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol.approvals import ExecPolicyAmendment as CoreExecPolicyAmendment
from pycodex.protocol.approvals import NetworkApprovalContext as CoreNetworkApprovalContext
from pycodex.protocol.approvals import NetworkApprovalProtocol as CoreNetworkApprovalProtocol
from pycodex.protocol.approvals import NetworkPolicyAmendment as CoreNetworkPolicyAmendment
from pycodex.protocol.approvals import NetworkPolicyRuleAction as CoreNetworkPolicyRuleAction
from pycodex.protocol.models import ActivePermissionProfile as CoreActivePermissionProfile
from pycodex.protocol.models import AdditionalPermissionProfile as CoreAdditionalPermissionProfile
from pycodex.protocol.models import FileSystemAccessMode as CoreFileSystemAccessMode
from pycodex.protocol.models import FileSystemPath as CoreFileSystemPath
from pycodex.protocol.models import FileSystemPermissions as CoreFileSystemPermissions
from pycodex.protocol.models import FileSystemSandboxEntry as CoreFileSystemSandboxEntry
from pycodex.protocol.models import FileSystemSpecialPath as CoreFileSystemSpecialPath
from pycodex.protocol.models import NetworkPermissions as CoreNetworkPermissions
from pycodex.protocol.models import NetworkSandboxPolicy as CoreNetworkSandboxPolicy
from pycodex.protocol.models import SandboxPolicy as CoreSandboxPolicy
from pycodex.protocol.request_permissions import PermissionGrantScope as CorePermissionGrantScope
from pycodex.protocol.request_permissions import RequestPermissionProfile as CoreRequestPermissionProfile

JsonValue = Any


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc

    def to_mapping(self) -> str:
        return self.value

    def to_core(self):
        return self.value


class NetworkApprovalProtocol(_StringEnum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5_TCP = "socks5_tcp"
    SOCKS5_UDP = "socks5_udp"

    @classmethod
    def from_core(cls, value: CoreNetworkApprovalProtocol | str) -> "NetworkApprovalProtocol":
        return cls.parse(getattr(value, "value", value))

    def to_core(self) -> CoreNetworkApprovalProtocol:
        return CoreNetworkApprovalProtocol.parse(self.value)


@dataclass(frozen=True)
class NetworkApprovalContext:
    host: str
    protocol: NetworkApprovalProtocol | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "host", _ensure_str(self.host, "host"))
        object.__setattr__(self, "protocol", NetworkApprovalProtocol.parse(self.protocol))

    @classmethod
    def from_core(cls, value: CoreNetworkApprovalContext) -> "NetworkApprovalContext":
        if not isinstance(value, CoreNetworkApprovalContext):
            raise TypeError("value must be CoreNetworkApprovalContext")
        return cls(host=value.host, protocol=NetworkApprovalProtocol.from_core(value.protocol))

    def to_core(self) -> CoreNetworkApprovalContext:
        return CoreNetworkApprovalContext(host=self.host, protocol=self.protocol.to_core())

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "NetworkApprovalContext":
        data = _mapping(value, "NetworkApprovalContext")
        return cls(host=_ensure_str(data["host"], "host"), protocol=NetworkApprovalProtocol.parse(data["protocol"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"host": self.host, "protocol": self.protocol.value}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class AdditionalFileSystemPermissions:
    read: tuple[Path, ...] | None = None
    write: tuple[Path, ...] | None = None
    glob_scan_max_depth: int | None = None
    entries: tuple["FileSystemSandboxEntry", ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "read", _optional_absolute_paths(self.read, "read"))
        object.__setattr__(self, "write", _optional_absolute_paths(self.write, "write"))
        object.__setattr__(
            self,
            "glob_scan_max_depth",
            _optional_nonzero_usize(self.glob_scan_max_depth, "glob_scan_max_depth"),
        )
        if self.entries is not None:
            if not isinstance(self.entries, tuple):
                object.__setattr__(self, "entries", tuple(_entry(item) for item in self.entries))
            else:
                object.__setattr__(self, "entries", tuple(_entry(item) for item in self.entries))

    @classmethod
    def from_core(cls, value: CoreFileSystemPermissions) -> "AdditionalFileSystemPermissions":
        if not isinstance(value, CoreFileSystemPermissions):
            raise TypeError("value must be CoreFileSystemPermissions")
        legacy = value.legacy_read_write_roots()
        if legacy is not None:
            read, write = legacy
            entries: list[FileSystemSandboxEntry] = []
            for path in read or ():
                entries.append(
                    FileSystemSandboxEntry(FileSystemPath.path(path), FileSystemAccessMode.READ)
                )
            for path in write or ():
                entries.append(
                    FileSystemSandboxEntry(FileSystemPath.path(path), FileSystemAccessMode.WRITE)
                )
            return cls(read=read, write=write, entries=tuple(entries))
        return cls(
            entries=tuple(FileSystemSandboxEntry.from_core(entry) for entry in value.entries),
            glob_scan_max_depth=value.glob_scan_max_depth,
        )

    def to_core(self) -> CoreFileSystemPermissions:
        if self.entries is not None:
            permissions = CoreFileSystemPermissions(
                entries=tuple(entry.to_core() for entry in self.entries),
                glob_scan_max_depth=None,
            )
        else:
            permissions = CoreFileSystemPermissions.from_read_write_roots(self.read, self.write)
        if self.glob_scan_max_depth is not None:
            permissions = CoreFileSystemPermissions(
                entries=permissions.entries,
                glob_scan_max_depth=self.glob_scan_max_depth,
            )
        return permissions

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AdditionalFileSystemPermissions":
        data = _mapping(value, "AdditionalFileSystemPermissions")
        return cls(
            read=_optional_path_list(data.get("read"), "read"),
            write=_optional_path_list(data.get("write"), "write"),
            glob_scan_max_depth=_optional_nonzero_usize(
                _pick(data, "glob_scan_max_depth", "globScanMaxDepth"),
                "glob_scan_max_depth",
            ),
            entries=(
                tuple(FileSystemSandboxEntry.from_mapping(item) for item in _list(_pick(data, "entries"), "entries"))
                if _pick(data, "entries") is not None
                else None
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        if self.read is not None:
            result["read"] = [str(path) for path in self.read]
        if self.write is not None:
            result["write"] = [str(path) for path in self.write]
        if self.glob_scan_max_depth is not None:
            result["glob_scan_max_depth"] = self.glob_scan_max_depth
        if self.entries is not None:
            result["entries"] = [entry.to_mapping() for entry in self.entries]
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        if self.read is not None:
            result["read"] = [str(path) for path in self.read]
        if self.write is not None:
            result["write"] = [str(path) for path in self.write]
        if self.glob_scan_max_depth is not None:
            result["globScanMaxDepth"] = self.glob_scan_max_depth
        if self.entries is not None:
            result["entries"] = [entry.to_camel_mapping() for entry in self.entries]
        return result


@dataclass(frozen=True)
class AdditionalNetworkPermissions:
    enabled: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _optional_bool(self.enabled, "enabled"))

    @classmethod
    def from_core(cls, value: CoreNetworkPermissions) -> "AdditionalNetworkPermissions":
        if not isinstance(value, CoreNetworkPermissions):
            raise TypeError("value must be CoreNetworkPermissions")
        return cls(enabled=value.enabled)

    def to_core(self) -> CoreNetworkPermissions:
        return CoreNetworkPermissions(enabled=self.enabled)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AdditionalNetworkPermissions":
        data = _mapping(value, "AdditionalNetworkPermissions")
        return cls(enabled=_optional_bool(data.get("enabled"), "enabled"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {} if self.enabled is None else {"enabled": self.enabled}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class RequestPermissionProfile:
    network: AdditionalNetworkPermissions | Mapping[str, JsonValue] | None = None
    file_system: AdditionalFileSystemPermissions | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "network", _optional_network(self.network, "network"))
        object.__setattr__(self, "file_system", _optional_file_system(self.file_system, "file_system"))

    @classmethod
    def from_core(cls, value: CoreRequestPermissionProfile) -> "RequestPermissionProfile":
        if not isinstance(value, CoreRequestPermissionProfile):
            raise TypeError("value must be CoreRequestPermissionProfile")
        return cls(
            network=AdditionalNetworkPermissions.from_core(value.network) if value.network is not None else None,
            file_system=AdditionalFileSystemPermissions.from_core(value.file_system)
            if value.file_system is not None
            else None,
        )

    def to_core(self) -> CoreRequestPermissionProfile:
        return CoreRequestPermissionProfile(
            network=self.network.to_core() if self.network is not None else None,
            file_system=self.file_system.to_core() if self.file_system is not None else None,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RequestPermissionProfile":
        data = _mapping(value, "RequestPermissionProfile")
        unknown = set(data) - {"network", "file_system", "fileSystem"}
        if unknown:
            raise ValueError(f"unknown field: {sorted(unknown)[0]}")
        return cls(
            network=AdditionalNetworkPermissions.from_mapping(data["network"])
            if data.get("network") is not None
            else None,
            file_system=AdditionalFileSystemPermissions.from_mapping(_pick(data, "file_system", "fileSystem"))
            if _pick(data, "file_system", "fileSystem") is not None
            else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        if self.network is not None:
            result["network"] = self.network.to_mapping()
        if self.file_system is not None:
            result["file_system"] = self.file_system.to_mapping()
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        if self.network is not None:
            result["network"] = self.network.to_camel_mapping()
        if self.file_system is not None:
            result["fileSystem"] = self.file_system.to_camel_mapping()
        return result


class FileSystemAccessMode(_StringEnum):
    READ = "read"
    WRITE = "write"
    DENY = "deny"

    @classmethod
    def parse(cls, value: JsonValue) -> "FileSystemAccessMode":
        raw = getattr(value, "value", value)
        if raw == "none":
            return cls.DENY
        return super().parse(raw)

    @classmethod
    def from_core(cls, value: CoreFileSystemAccessMode | str) -> "FileSystemAccessMode":
        return cls.parse(getattr(value, "value", value))

    def to_core(self) -> CoreFileSystemAccessMode:
        return CoreFileSystemAccessMode.parse(self.value)


@dataclass(frozen=True)
class FileSystemSpecialPath:
    kind: str
    subpath: Path | None = None
    path: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"root", "minimal", "project_roots", "tmpdir", "slash_tmp", "unknown"}:
            raise ValueError(f"unknown filesystem special path kind: {self.kind}")
        object.__setattr__(self, "subpath", _optional_relative_path(self.subpath, "subpath"))
        object.__setattr__(self, "path", _optional_str(self.path, "path"))
        if self.kind == "unknown":
            if self.path is None:
                raise TypeError("unknown special path requires path")
        elif self.path is not None:
            raise ValueError(f"{self.kind} special path cannot include path")
        if self.kind not in {"project_roots", "unknown"} and self.subpath is not None:
            raise ValueError(f"{self.kind} special path cannot include subpath")

    @classmethod
    def root(cls) -> "FileSystemSpecialPath":
        return cls("root")

    @classmethod
    def minimal(cls) -> "FileSystemSpecialPath":
        return cls("minimal")

    @classmethod
    def project_roots(cls, subpath: Path | str | None = None) -> "FileSystemSpecialPath":
        return cls("project_roots", subpath=Path(subpath) if subpath is not None else None)

    @classmethod
    def tmpdir(cls) -> "FileSystemSpecialPath":
        return cls("tmpdir")

    @classmethod
    def slash_tmp(cls) -> "FileSystemSpecialPath":
        return cls("slash_tmp")

    @classmethod
    def unknown(cls, path: str, subpath: Path | str | None = None) -> "FileSystemSpecialPath":
        return cls("unknown", subpath=Path(subpath) if subpath is not None else None, path=path)

    @classmethod
    def from_core(cls, value: CoreFileSystemSpecialPath) -> "FileSystemSpecialPath":
        if not isinstance(value, CoreFileSystemSpecialPath):
            raise TypeError("value must be CoreFileSystemSpecialPath")
        if value.kind == "root":
            return cls.root()
        if value.kind == "minimal":
            return cls.minimal()
        if value.kind == "project_roots":
            return cls.project_roots(value.subpath)
        if value.kind == "tmpdir":
            return cls.tmpdir()
        if value.kind == "slash_tmp":
            return cls.slash_tmp()
        if value.kind == "unknown":
            return cls.unknown(value.path or "", value.subpath)
        return cls.unknown(value.kind, value.subpath)

    def to_core(self) -> CoreFileSystemSpecialPath:
        if self.kind == "root":
            return CoreFileSystemSpecialPath.root()
        if self.kind == "minimal":
            return CoreFileSystemSpecialPath.minimal()
        if self.kind == "project_roots":
            return CoreFileSystemSpecialPath.project_roots(self.subpath)
        if self.kind == "tmpdir":
            return CoreFileSystemSpecialPath.tmpdir()
        if self.kind == "slash_tmp":
            return CoreFileSystemSpecialPath.slash_tmp()
        return CoreFileSystemSpecialPath.unknown(self.path or "", self.subpath)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FileSystemSpecialPath":
        data = _mapping(value, "FileSystemSpecialPath")
        kind = _ensure_str(data["kind"], "kind")
        if kind == "current_working_directory":
            kind = "project_roots"
        subpath = _optional_path(_pick(data, "subpath"), "subpath")
        if kind == "root":
            return cls.root()
        if kind == "minimal":
            return cls.minimal()
        if kind == "project_roots":
            return cls.project_roots(subpath)
        if kind == "tmpdir":
            return cls.tmpdir()
        if kind == "slash_tmp":
            return cls.slash_tmp()
        if kind == "unknown":
            return cls.unknown(_ensure_str(data["path"], "path"), subpath)
        raise ValueError(f"unknown filesystem special path kind: {kind}")

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"kind": self.kind}
        if self.subpath is not None:
            result["subpath"] = str(self.subpath)
        if self.kind == "unknown":
            result["path"] = self.path
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class FileSystemPath:
    type: str
    path: Path | None = None
    pattern: str | None = None
    value: FileSystemSpecialPath | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        if self.type not in {"path", "glob_pattern", "special"}:
            raise ValueError(f"unknown filesystem path type: {self.type}")
        if self.type == "path":
            object.__setattr__(self, "path", _absolute_path(self.path, "path"))
            if self.pattern is not None or self.value is not None:
                raise ValueError("path filesystem path cannot include pattern or value")
        elif self.type == "glob_pattern":
            object.__setattr__(self, "pattern", _ensure_str(self.pattern, "pattern"))
            if self.path is not None or self.value is not None:
                raise ValueError("glob_pattern filesystem path cannot include path or value")
        else:
            object.__setattr__(self, "value", _special_path(self.value, "value"))
            if self.path is not None or self.pattern is not None:
                raise ValueError("special filesystem path cannot include path or pattern")

    @classmethod
    def path(cls, path: Path | str) -> "FileSystemPath":
        return cls("path", path=Path(path))

    @classmethod
    def glob_pattern(cls, pattern: str) -> "FileSystemPath":
        return cls("glob_pattern", pattern=pattern)

    @classmethod
    def special(cls, value: FileSystemSpecialPath | Mapping[str, JsonValue]) -> "FileSystemPath":
        return cls("special", value=value)

    @classmethod
    def from_core(cls, value: CoreFileSystemPath) -> "FileSystemPath":
        if not isinstance(value, CoreFileSystemPath):
            raise TypeError("value must be CoreFileSystemPath")
        if value.type == "path":
            return cls.path(value.path)
        if value.type == "glob_pattern":
            return cls.glob_pattern(value.pattern or "")
        if value.type == "special":
            return cls.special(FileSystemSpecialPath.from_core(value.value))
        raise ValueError(f"unknown filesystem path type: {value.type}")

    def to_core(self) -> CoreFileSystemPath:
        if self.type == "path":
            return CoreFileSystemPath.explicit_path(self.path)
        if self.type == "glob_pattern":
            return CoreFileSystemPath.glob_pattern(self.pattern or "")
        return CoreFileSystemPath.special(self.value.to_core())

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FileSystemPath":
        data = _mapping(value, "FileSystemPath")
        path_type = _ensure_str(data["type"], "type")
        if path_type == "path":
            return cls.path(_ensure_str(data["path"], "path"))
        if path_type == "glob_pattern":
            return cls.glob_pattern(_ensure_str(data["pattern"], "pattern"))
        if path_type == "special":
            return cls.special(FileSystemSpecialPath.from_mapping(data["value"]))
        raise ValueError(f"unknown filesystem path type: {path_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "path":
            return {"type": "path", "path": str(self.path)}
        if self.type == "glob_pattern":
            return {"type": "glob_pattern", "pattern": self.pattern}
        return {"type": "special", "value": self.value.to_mapping()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class FileSystemSandboxEntry:
    path: FileSystemPath | Mapping[str, JsonValue]
    access: FileSystemAccessMode | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _file_system_path(self.path, "path"))
        object.__setattr__(self, "access", FileSystemAccessMode.parse(self.access))

    @classmethod
    def from_core(cls, value: CoreFileSystemSandboxEntry) -> "FileSystemSandboxEntry":
        if not isinstance(value, CoreFileSystemSandboxEntry):
            raise TypeError("value must be CoreFileSystemSandboxEntry")
        return cls(path=FileSystemPath.from_core(value.path), access=FileSystemAccessMode.from_core(value.access))

    def to_core(self) -> CoreFileSystemSandboxEntry:
        return CoreFileSystemSandboxEntry(path=self.path.to_core(), access=self.access.to_core())

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FileSystemSandboxEntry":
        data = _mapping(value, "FileSystemSandboxEntry")
        return cls(path=FileSystemPath.from_mapping(data["path"]), access=FileSystemAccessMode.parse(data["access"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"path": self.path.to_mapping(), "access": self.access.value}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class PermissionProfileListParams:
    cursor: str | None = None
    limit: int | None = None
    cwd: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cursor", _optional_str(self.cursor, "cursor"))
        object.__setattr__(self, "limit", _optional_u32(self.limit, "limit"))
        object.__setattr__(self, "cwd", _optional_str(self.cwd, "cwd"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "PermissionProfileListParams":
        data = {} if value is None else _mapping(value, "PermissionProfileListParams")
        return cls(
            cursor=_optional_str(data.get("cursor"), "cursor"),
            limit=_optional_u32(data.get("limit"), "limit"),
            cwd=_optional_str(data.get("cwd"), "cwd"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"cursor": self.cursor, "limit": self.limit, "cwd": self.cwd}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class PermissionProfileSummary:
    id: str
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "description", _optional_str(self.description, "description"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "PermissionProfileSummary":
        data = _mapping(value, "PermissionProfileSummary")
        return cls(id=_ensure_str(data["id"], "id"), description=_optional_str(data.get("description"), "description"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"id": self.id, "description": self.description}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class PermissionProfileListResponse:
    data: tuple[PermissionProfileSummary, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", tuple(_profile_summary(item) for item in self.data))
        object.__setattr__(self, "next_cursor", _optional_str(self.next_cursor, "next_cursor"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "PermissionProfileListResponse":
        data = _mapping(value, "PermissionProfileListResponse")
        return cls(
            data=tuple(PermissionProfileSummary.from_mapping(item) for item in _list(data["data"], "data")),
            next_cursor=_optional_str(_pick(data, "next_cursor", "nextCursor"), "next_cursor"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"data": [item.to_mapping() for item in self.data], "next_cursor": self.next_cursor}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"data": [item.to_camel_mapping() for item in self.data], "nextCursor": self.next_cursor}


@dataclass(frozen=True)
class ActivePermissionProfile:
    id: str
    extends: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "extends", _optional_str(self.extends, "extends"))

    @classmethod
    def new(cls, id: str) -> "ActivePermissionProfile":
        return cls(id=id)

    @classmethod
    def read_only(cls) -> "ActivePermissionProfile":
        return cls.from_core(CoreActivePermissionProfile.read_only())

    @classmethod
    def from_core(cls, value: CoreActivePermissionProfile) -> "ActivePermissionProfile":
        if not isinstance(value, CoreActivePermissionProfile):
            raise TypeError("value must be CoreActivePermissionProfile")
        return cls(id=value.id, extends=value.extends)

    def to_core(self) -> CoreActivePermissionProfile:
        return CoreActivePermissionProfile(id=self.id, extends=self.extends)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ActivePermissionProfile":
        data = _mapping(value, "ActivePermissionProfile")
        return cls(id=_ensure_str(data["id"], "id"), extends=_optional_str(data.get("extends"), "extends"))

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"id": self.id}
        if self.extends is not None:
            result["extends"] = self.extends
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class AdditionalPermissionProfile:
    network: AdditionalNetworkPermissions | Mapping[str, JsonValue] | None = None
    file_system: AdditionalFileSystemPermissions | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "network", _optional_network(self.network, "network"))
        object.__setattr__(self, "file_system", _optional_file_system(self.file_system, "file_system"))

    @classmethod
    def from_core(cls, value: CoreAdditionalPermissionProfile) -> "AdditionalPermissionProfile":
        if not isinstance(value, CoreAdditionalPermissionProfile):
            raise TypeError("value must be CoreAdditionalPermissionProfile")
        return cls(
            network=AdditionalNetworkPermissions.from_core(value.network) if value.network is not None else None,
            file_system=AdditionalFileSystemPermissions.from_core(value.file_system)
            if value.file_system is not None
            else None,
        )

    def to_core(self) -> CoreAdditionalPermissionProfile:
        return CoreAdditionalPermissionProfile(
            network=self.network.to_core() if self.network is not None else None,
            file_system=self.file_system.to_core() if self.file_system is not None else None,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AdditionalPermissionProfile":
        data = _mapping(value, "AdditionalPermissionProfile")
        return cls(
            network=AdditionalNetworkPermissions.from_mapping(data["network"])
            if data.get("network") is not None
            else None,
            file_system=AdditionalFileSystemPermissions.from_mapping(_pick(data, "file_system", "fileSystem"))
            if _pick(data, "file_system", "fileSystem") is not None
            else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return RequestPermissionProfile(self.network, self.file_system).to_mapping()

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return RequestPermissionProfile(self.network, self.file_system).to_camel_mapping()


@dataclass(frozen=True)
class GrantedPermissionProfile:
    network: AdditionalNetworkPermissions | Mapping[str, JsonValue] | None = None
    file_system: AdditionalFileSystemPermissions | Mapping[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "network", _optional_network(self.network, "network"))
        object.__setattr__(self, "file_system", _optional_file_system(self.file_system, "file_system"))

    def to_core(self) -> CoreAdditionalPermissionProfile:
        return CoreAdditionalPermissionProfile(
            network=self.network.to_core() if self.network is not None else None,
            file_system=self.file_system.to_core() if self.file_system is not None else None,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "GrantedPermissionProfile":
        data = {} if value is None else _mapping(value, "GrantedPermissionProfile")
        return cls(
            network=AdditionalNetworkPermissions.from_mapping(data["network"])
            if data.get("network") is not None
            else None,
            file_system=AdditionalFileSystemPermissions.from_mapping(_pick(data, "file_system", "fileSystem"))
            if _pick(data, "file_system", "fileSystem") is not None
            else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return RequestPermissionProfile(self.network, self.file_system).to_mapping()

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return RequestPermissionProfile(self.network, self.file_system).to_camel_mapping()


class NetworkAccess(_StringEnum):
    RESTRICTED = "restricted"
    ENABLED = "enabled"

    @classmethod
    def default(cls) -> "NetworkAccess":
        return cls.RESTRICTED

    @classmethod
    def from_core(cls, value: CoreNetworkSandboxPolicy | str | bool) -> "NetworkAccess":
        raw = getattr(value, "value", value)
        if raw is True:
            return cls.ENABLED
        if raw is False:
            return cls.RESTRICTED
        return cls.parse(raw)

    def to_core(self) -> CoreNetworkSandboxPolicy:
        return CoreNetworkSandboxPolicy.ENABLED if self is NetworkAccess.ENABLED else CoreNetworkSandboxPolicy.RESTRICTED


@dataclass(frozen=True)
class SandboxPolicy:
    type: str
    network_access: bool | NetworkAccess | str = False
    writable_roots: tuple[Path, ...] = ()
    exclude_tmpdir_env_var: bool = False
    exclude_slash_tmp: bool = False

    def __post_init__(self) -> None:
        if self.type not in {"dangerFullAccess", "readOnly", "externalSandbox", "workspaceWrite"}:
            raise ValueError(f"unknown sandbox policy type: {self.type}")
        if self.type == "externalSandbox":
            object.__setattr__(self, "network_access", NetworkAccess.parse(self.network_access))
        else:
            object.__setattr__(self, "network_access", _ensure_bool(self.network_access, "network_access"))
        object.__setattr__(self, "writable_roots", _absolute_paths(self.writable_roots, "writable_roots"))
        object.__setattr__(self, "exclude_tmpdir_env_var", _ensure_bool(self.exclude_tmpdir_env_var, "exclude_tmpdir_env_var"))
        object.__setattr__(self, "exclude_slash_tmp", _ensure_bool(self.exclude_slash_tmp, "exclude_slash_tmp"))
        if self.type == "dangerFullAccess":
            if self.network_access:
                raise ValueError("dangerFullAccess policy cannot include network_access")
            if self.writable_roots or self.exclude_tmpdir_env_var or self.exclude_slash_tmp:
                raise ValueError("dangerFullAccess policy cannot include workspace fields")
        if self.type in {"readOnly", "externalSandbox"}:
            if self.writable_roots or self.exclude_tmpdir_env_var or self.exclude_slash_tmp:
                raise ValueError(f"{self.type} policy cannot include workspace fields")

    @classmethod
    def danger_full_access(cls) -> "SandboxPolicy":
        return cls("dangerFullAccess")

    @classmethod
    def read_only(cls, network_access: bool = False) -> "SandboxPolicy":
        return cls("readOnly", network_access=network_access)

    @classmethod
    def external_sandbox(cls, network_access: NetworkAccess | str = NetworkAccess.RESTRICTED) -> "SandboxPolicy":
        return cls("externalSandbox", network_access=network_access)

    @classmethod
    def workspace_write(
        cls,
        writable_roots: Iterable[Path | str] = (),
        network_access: bool = False,
        exclude_tmpdir_env_var: bool = False,
        exclude_slash_tmp: bool = False,
    ) -> "SandboxPolicy":
        return cls(
            "workspaceWrite",
            writable_roots=tuple(Path(path) for path in writable_roots),
            network_access=network_access,
            exclude_tmpdir_env_var=exclude_tmpdir_env_var,
            exclude_slash_tmp=exclude_slash_tmp,
        )

    @classmethod
    def from_core(cls, value: CoreSandboxPolicy) -> "SandboxPolicy":
        if not isinstance(value, CoreSandboxPolicy):
            raise TypeError("value must be CoreSandboxPolicy")
        if value.type == "danger-full-access":
            return cls.danger_full_access()
        if value.type == "read-only":
            return cls.read_only(bool(value.network_access))
        if value.type == "external-sandbox":
            return cls.external_sandbox(NetworkAccess.from_core(value.network_access))
        if value.type == "workspace-write":
            return cls.workspace_write(
                value.writable_roots,
                network_access=bool(value.network_access),
                exclude_tmpdir_env_var=value.exclude_tmpdir_env_var,
                exclude_slash_tmp=value.exclude_slash_tmp,
            )
        raise ValueError(f"unknown core sandbox policy type: {value.type}")

    def to_core(self) -> CoreSandboxPolicy:
        if self.type == "dangerFullAccess":
            return CoreSandboxPolicy.danger_full_access()
        if self.type == "readOnly":
            return CoreSandboxPolicy.read_only(bool(self.network_access))
        if self.type == "externalSandbox":
            return CoreSandboxPolicy.external_sandbox(self.network_access.to_core())
        return CoreSandboxPolicy.workspace_write(
            self.writable_roots,
            network_access=bool(self.network_access),
            exclude_tmpdir_env_var=self.exclude_tmpdir_env_var,
            exclude_slash_tmp=self.exclude_slash_tmp,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "SandboxPolicy":
        data = _mapping(value, "SandboxPolicy")
        policy_type = _ensure_str(data["type"], "type")
        if policy_type == "dangerFullAccess":
            return cls.danger_full_access()
        if policy_type == "readOnly":
            legacy_access = _pick(data, "access")
            if legacy_access is not None and _ensure_legacy_access(legacy_access, "access") == "restricted":
                raise ValueError(
                    "readOnly.access is no longer supported; use permissionProfile for restricted reads"
                )
            return cls.read_only(_ensure_bool(_pick(data, "network_access", "networkAccess", default=False), "network_access"))
        if policy_type == "externalSandbox":
            return cls.external_sandbox(
                NetworkAccess.parse(_pick(data, "network_access", "networkAccess", default=NetworkAccess.RESTRICTED.value))
            )
        if policy_type == "workspaceWrite":
            legacy_access = _pick(data, "read_only_access", "readOnlyAccess")
            if legacy_access is not None and _ensure_legacy_access(legacy_access, "read_only_access") == "restricted":
                raise ValueError(
                    "workspaceWrite.readOnlyAccess is no longer supported; use permissionProfile for restricted reads"
                )
            return cls.workspace_write(
                _optional_path_list(_pick(data, "writable_roots", "writableRoots", default=()), "writable_roots") or (),
                network_access=_ensure_bool(_pick(data, "network_access", "networkAccess", default=False), "network_access"),
                exclude_tmpdir_env_var=_ensure_bool(
                    _pick(data, "exclude_tmpdir_env_var", "excludeTmpdirEnvVar", default=False),
                    "exclude_tmpdir_env_var",
                ),
                exclude_slash_tmp=_ensure_bool(
                    _pick(data, "exclude_slash_tmp", "excludeSlashTmp", default=False),
                    "exclude_slash_tmp",
                ),
            )
        raise ValueError(f"unknown sandbox policy type: {policy_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "dangerFullAccess":
            return {"type": self.type}
        if self.type == "readOnly":
            result: dict[str, JsonValue] = {"type": self.type}
            if self.network_access:
                result["network_access"] = True
            return result
        if self.type == "externalSandbox":
            return {"type": self.type, "network_access": self.network_access.value}
        result = {
            "type": self.type,
            "writable_roots": [str(path) for path in self.writable_roots],
            "network_access": bool(self.network_access),
            "exclude_tmpdir_env_var": self.exclude_tmpdir_env_var,
            "exclude_slash_tmp": self.exclude_slash_tmp,
        }
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        if self.type == "dangerFullAccess":
            return {"type": self.type}
        if self.type == "readOnly":
            result: dict[str, JsonValue] = {"type": self.type}
            if self.network_access:
                result["networkAccess"] = True
            return result
        if self.type == "externalSandbox":
            return {"type": self.type, "networkAccess": self.network_access.value}
        return {
            "type": self.type,
            "writableRoots": [str(path) for path in self.writable_roots],
            "networkAccess": bool(self.network_access),
            "excludeTmpdirEnvVar": self.exclude_tmpdir_env_var,
            "excludeSlashTmp": self.exclude_slash_tmp,
        }


@dataclass(frozen=True)
class ExecPolicyAmendment:
    command: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _string_tuple(self.command, "command"))

    @classmethod
    def from_core(cls, value: CoreExecPolicyAmendment) -> "ExecPolicyAmendment":
        if not isinstance(value, CoreExecPolicyAmendment):
            raise TypeError("value must be CoreExecPolicyAmendment")
        return cls(command=value.command_tokens())

    def to_core(self) -> CoreExecPolicyAmendment:
        return CoreExecPolicyAmendment.new(list(self.command))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ExecPolicyAmendment":
        return cls(command=_string_tuple(value, "command"))

    def to_mapping(self) -> list[str]:
        return list(self.command)

    def to_camel_mapping(self) -> list[str]:
        return self.to_mapping()


class NetworkPolicyRuleAction(_StringEnum):
    ALLOW = "allow"
    DENY = "deny"

    @classmethod
    def from_core(cls, value: CoreNetworkPolicyRuleAction | str) -> "NetworkPolicyRuleAction":
        return cls.parse(getattr(value, "value", value))

    def to_core(self) -> CoreNetworkPolicyRuleAction:
        return CoreNetworkPolicyRuleAction(self.value)


@dataclass(frozen=True)
class NetworkPolicyAmendment:
    host: str
    action: NetworkPolicyRuleAction | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "host", _ensure_str(self.host, "host"))
        object.__setattr__(self, "action", NetworkPolicyRuleAction.parse(self.action))

    @classmethod
    def from_core(cls, value: CoreNetworkPolicyAmendment) -> "NetworkPolicyAmendment":
        if not isinstance(value, CoreNetworkPolicyAmendment):
            raise TypeError("value must be CoreNetworkPolicyAmendment")
        return cls(host=value.host, action=NetworkPolicyRuleAction.from_core(value.action))

    def to_core(self) -> CoreNetworkPolicyAmendment:
        return CoreNetworkPolicyAmendment(host=self.host, action=self.action.to_core())

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "NetworkPolicyAmendment":
        data = _mapping(value, "NetworkPolicyAmendment")
        return cls(host=_ensure_str(data["host"], "host"), action=NetworkPolicyRuleAction.parse(data["action"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"host": self.host, "action": self.action.value}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class PermissionsRequestApprovalParams:
    thread_id: str
    turn_id: str
    item_id: str
    started_at_ms: int
    cwd: Path
    permissions: RequestPermissionProfile | Mapping[str, JsonValue]
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "item_id", _ensure_str(self.item_id, "item_id"))
        object.__setattr__(self, "started_at_ms", _ensure_i64(self.started_at_ms, "started_at_ms"))
        object.__setattr__(self, "cwd", _absolute_path(self.cwd, "cwd"))
        object.__setattr__(self, "reason", _optional_str(self.reason, "reason"))
        object.__setattr__(self, "permissions", _request_profile(self.permissions, "permissions"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "PermissionsRequestApprovalParams":
        data = _mapping(value, "PermissionsRequestApprovalParams")
        return cls(
            thread_id=_ensure_str(_pick(data, "thread_id", "threadId"), "thread_id"),
            turn_id=_ensure_str(_pick(data, "turn_id", "turnId"), "turn_id"),
            item_id=_ensure_str(_pick(data, "item_id", "itemId"), "item_id"),
            started_at_ms=_ensure_i64(_pick(data, "started_at_ms", "startedAtMs"), "started_at_ms"),
            cwd=_absolute_path(_ensure_str(data["cwd"], "cwd"), "cwd"),
            reason=_optional_str(data.get("reason"), "reason"),
            permissions=RequestPermissionProfile.from_mapping(data["permissions"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "item_id": self.item_id,
            "started_at_ms": self.started_at_ms,
            "cwd": str(self.cwd),
            "reason": self.reason,
            "permissions": self.permissions.to_mapping(),
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "threadId": self.thread_id,
            "turnId": self.turn_id,
            "itemId": self.item_id,
            "startedAtMs": self.started_at_ms,
            "cwd": str(self.cwd),
            "reason": self.reason,
            "permissions": self.permissions.to_camel_mapping(),
        }


class PermissionGrantScope(_StringEnum):
    TURN = "turn"
    SESSION = "session"

    @classmethod
    def default(cls) -> "PermissionGrantScope":
        return cls.TURN

    @classmethod
    def from_core(cls, value: CorePermissionGrantScope | str) -> "PermissionGrantScope":
        return cls.parse(getattr(value, "value", value))

    def to_core(self) -> CorePermissionGrantScope:
        return CorePermissionGrantScope(self.value)


@dataclass(frozen=True)
class PermissionsRequestApprovalResponse:
    permissions: GrantedPermissionProfile | Mapping[str, JsonValue]
    scope: PermissionGrantScope | str = PermissionGrantScope.TURN
    strict_auto_review: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", _granted_profile(self.permissions, "permissions"))
        object.__setattr__(self, "scope", PermissionGrantScope.parse(self.scope))
        object.__setattr__(self, "strict_auto_review", _optional_bool(self.strict_auto_review, "strict_auto_review"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "PermissionsRequestApprovalResponse":
        data = _mapping(value, "PermissionsRequestApprovalResponse")
        return cls(
            permissions=GrantedPermissionProfile.from_mapping(data["permissions"]),
            scope=PermissionGrantScope.parse(_pick(data, "scope", default=PermissionGrantScope.TURN.value)),
            strict_auto_review=_optional_bool(
                _pick(data, "strict_auto_review", "strictAutoReview"),
                "strict_auto_review",
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "permissions": self.permissions.to_mapping(),
            "scope": self.scope.value,
        }
        if self.strict_auto_review is not None:
            result["strict_auto_review"] = self.strict_auto_review
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "permissions": self.permissions.to_camel_mapping(),
            "scope": self.scope.value,
        }
        if self.strict_auto_review is not None:
            result["strictAutoReview"] = self.strict_auto_review
        return result


def _mapping(value: JsonValue, type_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    return value


def _pick(data: Mapping[str, JsonValue], *keys: str, default: JsonValue = None) -> JsonValue:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_bool(value: JsonValue, field_name: str) -> bool | None:
    if value is None:
        return None
    return _ensure_bool(value, field_name)


def _ensure_i64(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{field_name} must fit in i64")
    return value


def _optional_u32(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an unsigned 32-bit integer")
    if value < 0 or value > 2**32 - 1:
        raise ValueError(f"{field_name} must fit in u32")
    return value


def _optional_nonzero_usize(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be non-zero")
    return value


def _absolute_path(value: Path | str | None, field_name: str) -> Path:
    if value is None:
        raise TypeError(f"{field_name} must be a path")
    if not isinstance(value, (Path, str)):
        raise TypeError(f"{field_name} must be a path string")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be absolute")
    return path


def _optional_path(value: JsonValue, field_name: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, (Path, str)):
        raise TypeError(f"{field_name} must be a path string")
    return Path(value)


def _optional_relative_path(value: JsonValue, field_name: str) -> Path | None:
    path = _optional_path(value, field_name)
    if path is not None and path.is_absolute():
        raise ValueError(f"{field_name} must be relative")
    return path


def _optional_path_list(value: JsonValue, field_name: str) -> tuple[Path, ...] | None:
    if value is None:
        return None
    return _absolute_paths(value, field_name)


def _absolute_paths(value: Iterable[Path | str], field_name: str) -> tuple[Path, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be a list of path strings")
    return tuple(_absolute_path(path, field_name) for path in value)


def _optional_absolute_paths(value: Iterable[Path | str] | None, field_name: str) -> tuple[Path, ...] | None:
    if value is None:
        return None
    return _absolute_paths(value, field_name)


def _list(value: JsonValue, field_name: str) -> list[JsonValue]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    return value


def _string_tuple(value: JsonValue, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a list of strings")
    return tuple(value)


def _special_path(value: FileSystemSpecialPath | Mapping[str, JsonValue] | None, field_name: str) -> FileSystemSpecialPath:
    if isinstance(value, FileSystemSpecialPath):
        return value
    if isinstance(value, Mapping):
        return FileSystemSpecialPath.from_mapping(value)
    raise TypeError(f"{field_name} must be FileSystemSpecialPath")


def _file_system_path(value: FileSystemPath | Mapping[str, JsonValue], field_name: str) -> FileSystemPath:
    if isinstance(value, FileSystemPath):
        return value
    if isinstance(value, Mapping):
        return FileSystemPath.from_mapping(value)
    raise TypeError(f"{field_name} must be FileSystemPath")


def _entry(value: FileSystemSandboxEntry | Mapping[str, JsonValue]) -> FileSystemSandboxEntry:
    if isinstance(value, FileSystemSandboxEntry):
        return value
    if isinstance(value, Mapping):
        return FileSystemSandboxEntry.from_mapping(value)
    raise TypeError("entry must be FileSystemSandboxEntry")


def _optional_network(value: AdditionalNetworkPermissions | Mapping[str, JsonValue] | None, field_name: str) -> AdditionalNetworkPermissions | None:
    if value is None:
        return None
    if isinstance(value, AdditionalNetworkPermissions):
        return value
    if isinstance(value, Mapping):
        return AdditionalNetworkPermissions.from_mapping(value)
    raise TypeError(f"{field_name} must be AdditionalNetworkPermissions")


def _optional_file_system(
    value: AdditionalFileSystemPermissions | Mapping[str, JsonValue] | None,
    field_name: str,
) -> AdditionalFileSystemPermissions | None:
    if value is None:
        return None
    if isinstance(value, AdditionalFileSystemPermissions):
        return value
    if isinstance(value, Mapping):
        return AdditionalFileSystemPermissions.from_mapping(value)
    raise TypeError(f"{field_name} must be AdditionalFileSystemPermissions")


def _request_profile(value: RequestPermissionProfile | Mapping[str, JsonValue], field_name: str) -> RequestPermissionProfile:
    if isinstance(value, RequestPermissionProfile):
        return value
    if isinstance(value, Mapping):
        return RequestPermissionProfile.from_mapping(value)
    raise TypeError(f"{field_name} must be RequestPermissionProfile")


def _granted_profile(value: GrantedPermissionProfile | Mapping[str, JsonValue], field_name: str) -> GrantedPermissionProfile:
    if isinstance(value, GrantedPermissionProfile):
        return value
    if isinstance(value, Mapping):
        return GrantedPermissionProfile.from_mapping(value)
    raise TypeError(f"{field_name} must be GrantedPermissionProfile")


def _profile_summary(value: PermissionProfileSummary | Mapping[str, JsonValue]) -> PermissionProfileSummary:
    if isinstance(value, PermissionProfileSummary):
        return value
    if isinstance(value, Mapping):
        return PermissionProfileSummary.from_mapping(value)
    raise TypeError("data entries must be PermissionProfileSummary")


def _ensure_legacy_access(value: JsonValue, field_name: str) -> str:
    data = _mapping(value, field_name)
    access_type = _ensure_str(data["type"], "type")
    if access_type not in {"fullAccess", "restricted"}:
        raise ValueError(f"unknown legacy read-only access type: {access_type}")
    return access_type


__all__ = [
    "ActivePermissionProfile",
    "AdditionalFileSystemPermissions",
    "AdditionalNetworkPermissions",
    "AdditionalPermissionProfile",
    "ExecPolicyAmendment",
    "FileSystemAccessMode",
    "FileSystemPath",
    "FileSystemSandboxEntry",
    "FileSystemSpecialPath",
    "GrantedPermissionProfile",
    "NetworkAccess",
    "NetworkApprovalContext",
    "NetworkApprovalProtocol",
    "NetworkPolicyAmendment",
    "NetworkPolicyRuleAction",
    "PermissionGrantScope",
    "PermissionProfileListParams",
    "PermissionProfileListResponse",
    "PermissionProfileSummary",
    "PermissionsRequestApprovalParams",
    "PermissionsRequestApprovalResponse",
    "RequestPermissionProfile",
    "SandboxPolicy",
]
