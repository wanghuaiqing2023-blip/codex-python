"""Filesystem protocol types ported from ``protocol/v2/fs.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class FsReadFileParams:
    path: Path | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _absolute_path(self.path, "path"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsReadFileParams":
        _ensure_mapping(value, "FsReadFileParams")
        return cls(path=_absolute_path(value["path"], "path"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"path": str(self.path)}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class FsReadFileResponse:
    data_base64: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_base64", _ensure_str(self.data_base64, "data_base64"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsReadFileResponse":
        _ensure_mapping(value, "FsReadFileResponse")
        return cls(data_base64=_ensure_str(_pick(value, "data_base64", "dataBase64"), "data_base64"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"data_base64": self.data_base64}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"dataBase64": self.data_base64}


@dataclass(frozen=True)
class FsWriteFileParams:
    path: Path | str
    data_base64: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _absolute_path(self.path, "path"))
        object.__setattr__(self, "data_base64", _ensure_str(self.data_base64, "data_base64"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsWriteFileParams":
        _ensure_mapping(value, "FsWriteFileParams")
        return cls(
            path=_absolute_path(value["path"], "path"),
            data_base64=_ensure_str(_pick(value, "data_base64", "dataBase64"), "data_base64"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"path": str(self.path), "data_base64": self.data_base64}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"path": str(self.path), "dataBase64": self.data_base64}


@dataclass(frozen=True)
class FsWriteFileResponse:
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "FsWriteFileResponse":
        if value is not None:
            _ensure_mapping(value, "FsWriteFileResponse")
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class FsCreateDirectoryParams:
    path: Path | str
    recursive: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _absolute_path(self.path, "path"))
        object.__setattr__(self, "recursive", _optional_bool(self.recursive, "recursive"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsCreateDirectoryParams":
        _ensure_mapping(value, "FsCreateDirectoryParams")
        return cls(path=_absolute_path(value["path"], "path"), recursive=_optional_bool(_pick(value, "recursive"), "recursive"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"path": str(self.path), "recursive": self.recursive}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class FsCreateDirectoryResponse(FsWriteFileResponse):
    pass


@dataclass(frozen=True)
class FsGetMetadataParams(FsReadFileParams):
    pass


@dataclass(frozen=True)
class FsGetMetadataResponse:
    is_directory: bool
    is_file: bool
    is_symlink: bool
    created_at_ms: int
    modified_at_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "is_directory", _ensure_bool(self.is_directory, "is_directory"))
        object.__setattr__(self, "is_file", _ensure_bool(self.is_file, "is_file"))
        object.__setattr__(self, "is_symlink", _ensure_bool(self.is_symlink, "is_symlink"))
        object.__setattr__(self, "created_at_ms", _ensure_i64(self.created_at_ms, "created_at_ms"))
        object.__setattr__(self, "modified_at_ms", _ensure_i64(self.modified_at_ms, "modified_at_ms"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsGetMetadataResponse":
        _ensure_mapping(value, "FsGetMetadataResponse")
        return cls(
            is_directory=_ensure_bool(_pick(value, "is_directory", "isDirectory"), "is_directory"),
            is_file=_ensure_bool(_pick(value, "is_file", "isFile"), "is_file"),
            is_symlink=_ensure_bool(_pick(value, "is_symlink", "isSymlink"), "is_symlink"),
            created_at_ms=_ensure_i64(_pick(value, "created_at_ms", "createdAtMs"), "created_at_ms"),
            modified_at_ms=_ensure_i64(_pick(value, "modified_at_ms", "modifiedAtMs"), "modified_at_ms"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "is_directory": self.is_directory,
            "is_file": self.is_file,
            "is_symlink": self.is_symlink,
            "created_at_ms": self.created_at_ms,
            "modified_at_ms": self.modified_at_ms,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "isDirectory": self.is_directory,
            "isFile": self.is_file,
            "isSymlink": self.is_symlink,
            "createdAtMs": self.created_at_ms,
            "modifiedAtMs": self.modified_at_ms,
        }


@dataclass(frozen=True)
class FsReadDirectoryParams(FsReadFileParams):
    pass


@dataclass(frozen=True)
class FsReadDirectoryEntry:
    file_name: str
    is_directory: bool
    is_file: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_name", _ensure_str(self.file_name, "file_name"))
        object.__setattr__(self, "is_directory", _ensure_bool(self.is_directory, "is_directory"))
        object.__setattr__(self, "is_file", _ensure_bool(self.is_file, "is_file"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsReadDirectoryEntry":
        _ensure_mapping(value, "FsReadDirectoryEntry")
        return cls(
            file_name=_ensure_str(_pick(value, "file_name", "fileName"), "file_name"),
            is_directory=_ensure_bool(_pick(value, "is_directory", "isDirectory"), "is_directory"),
            is_file=_ensure_bool(_pick(value, "is_file", "isFile"), "is_file"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"file_name": self.file_name, "is_directory": self.is_directory, "is_file": self.is_file}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"fileName": self.file_name, "isDirectory": self.is_directory, "isFile": self.is_file}


@dataclass(frozen=True)
class FsReadDirectoryResponse:
    entries: tuple[FsReadDirectoryEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", _dataclass_tuple(self.entries, FsReadDirectoryEntry, "entries"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsReadDirectoryResponse":
        _ensure_mapping(value, "FsReadDirectoryResponse")
        return cls(entries=_dataclass_tuple(value["entries"], FsReadDirectoryEntry, "entries"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"entries": [item.to_mapping() for item in self.entries]}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"entries": [item.to_camel_mapping() for item in self.entries]}


@dataclass(frozen=True)
class FsRemoveParams:
    path: Path | str
    recursive: bool | None = None
    force: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _absolute_path(self.path, "path"))
        object.__setattr__(self, "recursive", _optional_bool(self.recursive, "recursive"))
        object.__setattr__(self, "force", _optional_bool(self.force, "force"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsRemoveParams":
        _ensure_mapping(value, "FsRemoveParams")
        return cls(
            path=_absolute_path(value["path"], "path"),
            recursive=_optional_bool(_pick(value, "recursive"), "recursive"),
            force=_optional_bool(_pick(value, "force"), "force"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"path": str(self.path), "recursive": self.recursive, "force": self.force}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class FsRemoveResponse(FsWriteFileResponse):
    pass


@dataclass(frozen=True)
class FsCopyParams:
    source_path: Path | str
    destination_path: Path | str
    recursive: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_path", _absolute_path(self.source_path, "source_path"))
        object.__setattr__(self, "destination_path", _absolute_path(self.destination_path, "destination_path"))
        object.__setattr__(self, "recursive", _ensure_bool(self.recursive, "recursive"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsCopyParams":
        _ensure_mapping(value, "FsCopyParams")
        return cls(
            source_path=_absolute_path(_pick(value, "source_path", "sourcePath"), "source_path"),
            destination_path=_absolute_path(_pick(value, "destination_path", "destinationPath"), "destination_path"),
            recursive=_ensure_bool(_pick(value, "recursive", default=False), "recursive"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"source_path": str(self.source_path), "destination_path": str(self.destination_path)}
        if self.recursive:
            result["recursive"] = self.recursive
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = {"sourcePath": str(self.source_path), "destinationPath": str(self.destination_path)}
        if self.recursive:
            result["recursive"] = self.recursive
        return result


@dataclass(frozen=True)
class FsCopyResponse(FsWriteFileResponse):
    pass


@dataclass(frozen=True)
class FsWatchParams:
    watch_id: str
    path: Path | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "watch_id", _ensure_str(self.watch_id, "watch_id"))
        object.__setattr__(self, "path", _absolute_path(self.path, "path"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsWatchParams":
        _ensure_mapping(value, "FsWatchParams")
        return cls(
            watch_id=_ensure_str(_pick(value, "watch_id", "watchId"), "watch_id"),
            path=_absolute_path(value["path"], "path"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"watch_id": self.watch_id, "path": str(self.path)}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"watchId": self.watch_id, "path": str(self.path)}


@dataclass(frozen=True)
class FsWatchResponse(FsReadFileParams):
    pass


@dataclass(frozen=True)
class FsUnwatchParams:
    watch_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "watch_id", _ensure_str(self.watch_id, "watch_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsUnwatchParams":
        _ensure_mapping(value, "FsUnwatchParams")
        return cls(watch_id=_ensure_str(_pick(value, "watch_id", "watchId"), "watch_id"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"watch_id": self.watch_id}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"watchId": self.watch_id}


@dataclass(frozen=True)
class FsUnwatchResponse(FsWriteFileResponse):
    pass


@dataclass(frozen=True)
class FsChangedNotification:
    watch_id: str
    changed_paths: tuple[Path, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "watch_id", _ensure_str(self.watch_id, "watch_id"))
        object.__setattr__(self, "changed_paths", _absolute_path_tuple(self.changed_paths, "changed_paths"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FsChangedNotification":
        _ensure_mapping(value, "FsChangedNotification")
        return cls(
            watch_id=_ensure_str(_pick(value, "watch_id", "watchId"), "watch_id"),
            changed_paths=_absolute_path_tuple(_pick(value, "changed_paths", "changedPaths"), "changed_paths"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"watch_id": self.watch_id, "changed_paths": [str(path) for path in self.changed_paths]}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"watchId": self.watch_id, "changedPaths": [str(path) for path in self.changed_paths]}


def _ensure_mapping(value: JsonValue, type_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} mapping must be a mapping")


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_bool(value: JsonValue, field_name: str) -> bool | None:
    if value is None:
        return None
    return _ensure_bool(value, field_name)


def _ensure_i64(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < -(2**63) or value > 2**63 - 1:
        raise TypeError(f"{field_name} must be a signed 64-bit integer")
    return value


def _absolute_path(value: JsonValue, field_name: str) -> Path:
    if isinstance(value, Path):
        path = value
    elif isinstance(value, str):
        path = Path(value)
    else:
        raise TypeError(f"{field_name} must be a path string or Path")
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")
    return path


def _absolute_path_tuple(value: JsonValue, field_name: str) -> tuple[Path, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable of absolute paths")
    return tuple(_absolute_path(item, f"{field_name} item") for item in value)


def _dataclass_tuple(value: JsonValue, cls: type, field_name: str) -> tuple:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable")
    result = []
    for item in value:
        if isinstance(item, cls):
            result.append(item)
        elif isinstance(item, Mapping) and hasattr(cls, "from_mapping"):
            result.append(cls.from_mapping(item))
        else:
            raise TypeError(f"{field_name} item must be {cls.__name__} or mapping")
    return tuple(result)


__all__ = [
    "FsChangedNotification",
    "FsCopyParams",
    "FsCopyResponse",
    "FsCreateDirectoryParams",
    "FsCreateDirectoryResponse",
    "FsGetMetadataParams",
    "FsGetMetadataResponse",
    "FsReadDirectoryEntry",
    "FsReadDirectoryParams",
    "FsReadDirectoryResponse",
    "FsReadFileParams",
    "FsReadFileResponse",
    "FsRemoveParams",
    "FsRemoveResponse",
    "FsUnwatchParams",
    "FsUnwatchResponse",
    "FsWatchParams",
    "FsWatchResponse",
    "FsWriteFileParams",
    "FsWriteFileResponse",
]
