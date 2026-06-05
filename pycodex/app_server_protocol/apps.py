"""App metadata protocol types ported from `codex-rs/app-server-protocol`."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class AppInfo:
    id: str
    name: str
    description: str | None = None
    logo_url: str | None = None
    logo_url_dark: str | None = None
    distribution_channel: str | None = None
    branding: JsonValue | None = None
    app_metadata: JsonValue | None = None
    labels: tuple[str, ...] | None = None
    install_url: str | None = None
    is_accessible: bool = False
    is_enabled: bool = False
    plugin_display_names: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "description", _optional_str(self.description))
        object.__setattr__(self, "logo_url", _optional_str(self.logo_url))
        object.__setattr__(self, "logo_url_dark", _optional_str(self.logo_url_dark))
        object.__setattr__(
            self,
            "distribution_channel",
            _optional_str(self.distribution_channel),
        )
        object.__setattr__(self, "labels", _optional_tuple(self.labels))
        object.__setattr__(self, "install_url", _optional_str(self.install_url))
        object.__setattr__(self, "is_accessible", _ensure_bool(self.is_accessible, "is_accessible"))
        object.__setattr__(self, "is_enabled", _ensure_bool(self.is_enabled, "is_enabled"))
        object.__setattr__(
            self,
            "plugin_display_names",
            _string_tuple(self.plugin_display_names),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppInfo":
        if not isinstance(value, Mapping):
            raise TypeError("AppInfo mapping must be a mapping")
        return cls(
            id=_ensure_str(value["id"], "id"),
            name=_ensure_str(value["name"], "name"),
            description=_optional_str(value.get("description")),
            logo_url=_optional_str(value.get("logo_url")),
            logo_url_dark=_optional_str(value.get("logo_url_dark")),
            distribution_channel=_optional_str(value.get("distribution_channel")),
            branding=copy.deepcopy(value.get("branding")),
            app_metadata=copy.deepcopy(value.get("app_metadata")),
            labels=_optional_tuple(value.get("labels")),
            install_url=_optional_str(value.get("install_url")),
            is_accessible=_ensure_bool(value.get("is_accessible", False), "is_accessible"),
            is_enabled=_ensure_bool(value.get("is_enabled", False), "is_enabled"),
            plugin_display_names=_string_tuple(value.get("plugin_display_names", ())),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "logo_url": self.logo_url,
            "logo_url_dark": self.logo_url_dark,
            "distribution_channel": self.distribution_channel,
            "branding": copy.deepcopy(self.branding),
            "app_metadata": copy.deepcopy(self.app_metadata),
            "labels": None if self.labels is None else list(self.labels),
            "install_url": self.install_url,
            "is_accessible": self.is_accessible,
            "is_enabled": self.is_enabled,
            "plugin_display_names": list(self.plugin_display_names),
        }


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_str(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, "optional string")


def _string_tuple(value: JsonValue) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError("string list must be an iterable of strings, not a string")
    if not isinstance(value, Iterable):
        raise TypeError("string list must be iterable")
    result: list[str] = []
    for item in value:
        result.append(_ensure_str(item, "string list item"))
    return tuple(result)


def _optional_tuple(value: JsonValue) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _string_tuple(value)


__all__ = ["AppInfo"]
