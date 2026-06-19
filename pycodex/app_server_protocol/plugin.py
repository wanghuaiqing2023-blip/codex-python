"""Plugin, marketplace, skill, and hook protocol types from ``v2/plugin.rs``.

The Rust module is an app-server protocol surface. This Python port mirrors the
wire data contracts and deliberately does not implement plugin discovery,
marketplace sync, sharing, install, or hook execution runtime behavior.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from enum import Enum
from pathlib import Path
from typing import Any

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


class PluginListMarketplaceKind(_StringEnum):
    LOCAL = "local"
    VERTICAL = "vertical"
    WORKSPACE_DIRECTORY = "workspace-directory"
    SHARED_WITH_ME = "shared-with-me"


class PluginShareDiscoverability(_StringEnum):
    LISTED = "LISTED"
    UNLISTED = "UNLISTED"
    PRIVATE = "PRIVATE"


class PluginShareUpdateDiscoverability(_StringEnum):
    UNLISTED = "UNLISTED"
    PRIVATE = "PRIVATE"


class PluginSharePrincipalType(_StringEnum):
    USER = "user"
    GROUP = "group"
    WORKSPACE = "workspace"


class PluginShareTargetRole(_StringEnum):
    READER = "reader"
    EDITOR = "editor"


class PluginSharePrincipalRole(_StringEnum):
    READER = "reader"
    EDITOR = "editor"
    OWNER = "owner"


class SkillScope(_StringEnum):
    USER = "user"
    REPO = "repo"
    SYSTEM = "system"
    ADMIN = "admin"


class PluginInstallPolicy(_StringEnum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    AVAILABLE = "AVAILABLE"
    INSTALLED_BY_DEFAULT = "INSTALLED_BY_DEFAULT"


class PluginAuthPolicy(_StringEnum):
    ON_INSTALL = "ON_INSTALL"
    ON_USE = "ON_USE"


class PluginAvailability(_StringEnum):
    AVAILABLE = "AVAILABLE"
    DISABLED_BY_ADMIN = "DISABLED_BY_ADMIN"

    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if raw == "ENABLED":
            raw = "AVAILABLE"
        return super().parse(raw)


class PluginSource:
    def __init__(self, type: str, **fields: JsonValue):
        self.type = _ensure_str(type, "type")
        if self.type not in {"local", "git", "remote"}:
            raise ValueError(f"unknown PluginSource type: {self.type}")
        self._fields = {_camel_to_snake(key): value for key, value in fields.items()}

    @classmethod
    def local(cls, path: str | Path) -> "PluginSource":
        return cls("local", path=path)

    @classmethod
    def git(
        cls,
        url: str,
        path: str | None = None,
        ref_name: str | None = None,
        sha: str | None = None,
    ) -> "PluginSource":
        return cls("git", url=url, path=path, ref_name=ref_name, sha=sha)

    @classmethod
    def remote(cls) -> "PluginSource":
        return cls("remote")

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "PluginSource":
        data = _mapping(value, "PluginSource")
        type_value = _ensure_str(data["type"], "type")
        fields = {
            _camel_to_snake(key): copy.deepcopy(item)
            for key, item in data.items()
            if key != "type"
        }
        return cls(type_value, **fields)

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"type": self.type}
        result.update({key: _serialize(value) for key, value in self._fields.items()})
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = {"type": self.type}
        result.update({_snake_to_camel(key): _serialize_camel(value) for key, value in self._fields.items()})
        return result

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PluginSource) and self.type == other.type and self._fields == other._fields

    def __repr__(self) -> str:
        return f"PluginSource(type={self.type!r}, fields={self._fields!r})"


class _Record:
    _omit_false: frozenset[str] = frozenset()
    _omit_empty: frozenset[str] = frozenset()
    _omit_none: frozenset[str] = frozenset()
    _defaults: dict[str, JsonValue] = {}
    _coercers: dict[str, Any] = {}

    def __init__(self, **fields: JsonValue):
        normalized: dict[str, JsonValue] = copy.deepcopy(self._defaults)
        for key, value in fields.items():
            snake = _camel_to_snake(key)
            if snake in self._coercers:
                value = self._coercers[snake](value)
            normalized[snake] = value
        self._fields = normalized

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]):
        data = _mapping(value, cls.__name__)
        return cls(**{_camel_to_snake(key): copy.deepcopy(item) for key, item in data.items()})

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            key: _serialize(value)
            for key, value in self._fields.items()
            if not _should_skip(key, value, self)
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            _snake_to_camel(key): _serialize_camel(value)
            for key, value in self._fields.items()
            if not _should_skip(key, value, self)
        }

    def __getattr__(self, name: str) -> JsonValue:
        try:
            return self._fields[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and self._fields == other._fields

    def __repr__(self) -> str:
        args = ", ".join(f"{key}={value!r}" for key, value in self._fields.items())
        return f"{self.__class__.__name__}({args})"


def _record_class(
    name: str,
    *,
    omit_false: Iterable[str] = (),
    omit_empty: Iterable[str] = (),
    omit_none: Iterable[str] = (),
    defaults: Mapping[str, JsonValue] | None = None,
    coercers: Mapping[str, Any] | None = None,
):
    return type(
        name,
        (_Record,),
        {
            "_omit_false": frozenset(omit_false),
            "_omit_empty": frozenset(omit_empty),
            "_omit_none": frozenset(omit_none),
            "_defaults": dict(defaults or {}),
            "_coercers": dict(coercers or {}),
            "__module__": __name__,
        },
    )


def _empty_record_class(name: str):
    class Empty(_Record):
        @classmethod
        def from_mapping(cls, value: Mapping[str, JsonValue] | None = None):
            if value is not None:
                _mapping(value, name)
            return cls()

    Empty.__name__ = name
    Empty.__qualname__ = name
    Empty.__module__ = __name__
    return Empty


def _enum_list(enum_type):
    return lambda value: tuple(enum_type.parse(item) for item in value) if value is not None else None


def _record_list(record_type):
    return lambda value: tuple(record_type.from_mapping(item) if isinstance(item, Mapping) else item for item in value)


def _source(value: JsonValue) -> PluginSource:
    if isinstance(value, PluginSource):
        return value
    return PluginSource.from_mapping(value)


SkillsListParams = _record_class(
    "SkillsListParams",
    omit_false=("force_reload",),
    omit_empty=("cwds",),
    defaults={"cwds": (), "force_reload": False},
)
SkillsListResponse = _record_class("SkillsListResponse", coercers={"data": lambda v: tuple(_skill_list_entry(item) for item in v)})
HooksListParams = _record_class("HooksListParams", omit_empty=("cwds",), defaults={"cwds": ()})
HooksListResponse = _record_class("HooksListResponse", coercers={"data": lambda v: tuple(_hooks_list_entry(item) for item in v)})

MarketplaceAddParams = _record_class("MarketplaceAddParams")
MarketplaceAddResponse = _record_class("MarketplaceAddResponse")
MarketplaceRemoveParams = _record_class("MarketplaceRemoveParams")
MarketplaceRemoveResponse = _record_class("MarketplaceRemoveResponse")
MarketplaceUpgradeParams = _record_class("MarketplaceUpgradeParams")
MarketplaceUpgradeErrorInfo = _record_class("MarketplaceUpgradeErrorInfo")
MarketplaceUpgradeResponse = _record_class("MarketplaceUpgradeResponse", defaults={"selected_marketplaces": (), "upgraded_roots": (), "errors": ()})


class PluginListParams(_Record):
    _coercers = {"marketplace_kinds": _enum_list(PluginListMarketplaceKind)}

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "PluginListParams":
        data = _mapping(value, cls.__name__)
        return cls(
            cwds=copy.deepcopy(_pick(data, "cwds", default=None)),
            marketplace_kinds=copy.deepcopy(_pick(data, "marketplaceKinds", "marketplace_kinds", default=None)),
        )


PluginInstalledParams = _record_class("PluginInstalledParams")
PluginListResponse = _record_class(
    "PluginListResponse",
    defaults={"marketplace_load_errors": (), "featured_plugin_ids": ()},
    coercers={
        "marketplaces": lambda v: tuple(_plugin_marketplace_entry(item) for item in v),
        "marketplace_load_errors": lambda v: tuple(MarketplaceLoadErrorInfo.from_mapping(item) if isinstance(item, Mapping) else item for item in v),
    },
)
PluginInstalledResponse = _record_class("PluginInstalledResponse", defaults={"marketplace_load_errors": ()})
MarketplaceLoadErrorInfo = _record_class("MarketplaceLoadErrorInfo")
PluginReadParams = _record_class("PluginReadParams")
PluginReadResponse = _record_class("PluginReadResponse", coercers={"plugin": lambda v: _plugin_detail(v)})
PluginSkillReadParams = _record_class("PluginSkillReadParams")
PluginSkillReadResponse = _record_class("PluginSkillReadResponse")

PluginShareSaveParams = _record_class(
    "PluginShareSaveParams",
    coercers={
        "discoverability": lambda v: PluginShareDiscoverability.parse(v) if v is not None else None,
        "share_targets": lambda v: tuple(_plugin_share_target(item) for item in v) if v is not None else None,
    },
)
PluginShareSaveResponse = _record_class("PluginShareSaveResponse")
PluginShareUpdateTargetsParams = _record_class(
    "PluginShareUpdateTargetsParams",
    coercers={
        "discoverability": PluginShareUpdateDiscoverability.parse,
        "share_targets": lambda v: tuple(_plugin_share_target(item) for item in v),
    },
)
PluginShareUpdateTargetsResponse = _record_class(
    "PluginShareUpdateTargetsResponse",
    coercers={
        "principals": lambda v: tuple(_plugin_share_principal(item) for item in v),
        "discoverability": PluginShareDiscoverability.parse,
    },
)
PluginShareListParams = _empty_record_class("PluginShareListParams")
PluginShareListResponse = _record_class("PluginShareListResponse", coercers={"data": lambda v: tuple(_plugin_share_list_item(item) for item in v)})
PluginShareCheckoutParams = _record_class("PluginShareCheckoutParams")
PluginShareCheckoutResponse = _record_class("PluginShareCheckoutResponse")
PluginShareDeleteParams = _record_class("PluginShareDeleteParams")
PluginShareDeleteResponse = _empty_record_class("PluginShareDeleteResponse")

PluginShareListItem = _record_class("PluginShareListItem", coercers={"plugin": lambda v: _plugin_summary(v)})
PluginShareTarget = _record_class(
    "PluginShareTarget",
    coercers={"principal_type": PluginSharePrincipalType.parse, "role": PluginShareTargetRole.parse},
)
PluginSharePrincipal = _record_class(
    "PluginSharePrincipal",
    coercers={"principal_type": PluginSharePrincipalType.parse, "role": PluginSharePrincipalRole.parse},
)

SkillInterface = _record_class("SkillInterface")
SkillToolDependency = _record_class("SkillToolDependency", omit_none=("description", "transport", "command", "url"))
SkillDependencies = _record_class("SkillDependencies", coercers={"tools": lambda v: tuple(_skill_tool_dependency(item) for item in v)})
SkillMetadata = _record_class(
    "SkillMetadata",
    omit_none=("short_description", "interface", "dependencies"),
    coercers={
        "interface": lambda v: _skill_interface(v) if v is not None else None,
        "dependencies": lambda v: _skill_dependencies(v) if v is not None else None,
        "scope": SkillScope.parse,
    },
)
SkillErrorInfo = _record_class("SkillErrorInfo")
SkillsListEntry = _record_class(
    "SkillsListEntry",
    coercers={
        "skills": lambda v: tuple(_skill_metadata(item) for item in v),
        "errors": lambda v: tuple(_skill_error_info(item) for item in v),
    },
)
HookMetadata = _record_class("HookMetadata")
HookErrorInfo = _record_class("HookErrorInfo")
HooksListEntry = _record_class(
    "HooksListEntry",
    coercers={
        "hooks": lambda v: tuple(_hook_metadata(item) for item in v),
        "warnings": lambda v: tuple(v),
        "errors": lambda v: tuple(_hook_error_info(item) for item in v),
    },
)

MarketplaceInterface = _record_class("MarketplaceInterface")
PluginMarketplaceEntry = _record_class(
    "PluginMarketplaceEntry",
    coercers={
        "interface": lambda v: MarketplaceInterface.from_mapping(v) if isinstance(v, Mapping) else v,
        "plugins": lambda v: tuple(_plugin_summary(item) for item in v),
    },
)
PluginShareContext = _record_class(
    "PluginShareContext",
    coercers={
        "discoverability": lambda v: PluginShareDiscoverability.parse(v) if v is not None else None,
        "share_principals": lambda v: tuple(_plugin_share_principal(item) for item in v) if v is not None else None,
    },
)
PluginSummary = _record_class(
    "PluginSummary",
    defaults={"local_version": None, "share_context": None, "availability": PluginAvailability.AVAILABLE, "keywords": ()},
    coercers={
        "source": _source,
        "install_policy": PluginInstallPolicy.parse,
        "auth_policy": PluginAuthPolicy.parse,
        "availability": PluginAvailability.parse,
        "share_context": lambda v: PluginShareContext.from_mapping(v) if isinstance(v, Mapping) else v,
        "interface": lambda v: PluginInterface.from_mapping(v) if isinstance(v, Mapping) else v,
    },
)
PluginHookSummary = _record_class("PluginHookSummary")
SkillSummary = _record_class("SkillSummary", coercers={"interface": lambda v: _skill_interface(v) if v is not None else None})
PluginInterface = _record_class("PluginInterface", defaults={"capabilities": (), "screenshots": (), "screenshot_urls": ()})
PluginDetail = _record_class(
    "PluginDetail",
    coercers={
        "summary": lambda v: _plugin_summary(v),
        "skills": lambda v: tuple(_skill_summary(item) for item in v),
        "hooks": lambda v: tuple(PluginHookSummary.from_mapping(item) if isinstance(item, Mapping) else item for item in v),
        "apps": tuple,
        "mcp_servers": tuple,
    },
)

SkillsConfigWriteParams = _record_class("SkillsConfigWriteParams")
SkillsConfigWriteResponse = _record_class("SkillsConfigWriteResponse")
PluginInstallParams = _record_class("PluginInstallParams")
PluginInstallResponse = _record_class("PluginInstallResponse", coercers={"auth_policy": PluginAuthPolicy.parse, "apps_needing_auth": tuple})


class PluginUninstallParams(_Record):
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "PluginUninstallParams":
        data = _mapping(value, cls.__name__)
        return cls(plugin_id=copy.deepcopy(_pick(data, "pluginId", "plugin_id")))


PluginUninstallResponse = _empty_record_class("PluginUninstallResponse")
SkillsChangedNotification = _empty_record_class("SkillsChangedNotification")


def _plugin_share_target(value: JsonValue) -> PluginShareTarget:
    return PluginShareTarget.from_mapping(value) if isinstance(value, Mapping) else value


def _plugin_share_principal(value: JsonValue) -> PluginSharePrincipal:
    return PluginSharePrincipal.from_mapping(value) if isinstance(value, Mapping) else value


def _plugin_share_list_item(value: JsonValue) -> PluginShareListItem:
    return PluginShareListItem.from_mapping(value) if isinstance(value, Mapping) else value


def _skill_interface(value: JsonValue) -> SkillInterface:
    return SkillInterface.from_mapping(value) if isinstance(value, Mapping) else value


def _skill_tool_dependency(value: JsonValue) -> SkillToolDependency:
    return SkillToolDependency.from_mapping(value) if isinstance(value, Mapping) else value


def _skill_dependencies(value: JsonValue) -> SkillDependencies:
    return SkillDependencies.from_mapping(value) if isinstance(value, Mapping) else value


def _skill_metadata(value: JsonValue) -> SkillMetadata:
    return SkillMetadata.from_mapping(value) if isinstance(value, Mapping) else value


def _skill_error_info(value: JsonValue) -> SkillErrorInfo:
    return SkillErrorInfo.from_mapping(value) if isinstance(value, Mapping) else value


def _skill_list_entry(value: JsonValue) -> SkillsListEntry:
    return SkillsListEntry.from_mapping(value) if isinstance(value, Mapping) else value


def _hook_metadata(value: JsonValue) -> HookMetadata:
    return HookMetadata.from_mapping(value) if isinstance(value, Mapping) else value


def _hook_error_info(value: JsonValue) -> HookErrorInfo:
    return HookErrorInfo.from_mapping(value) if isinstance(value, Mapping) else value


def _hooks_list_entry(value: JsonValue) -> HooksListEntry:
    return HooksListEntry.from_mapping(value) if isinstance(value, Mapping) else value


def _plugin_marketplace_entry(value: JsonValue) -> PluginMarketplaceEntry:
    return PluginMarketplaceEntry.from_mapping(value) if isinstance(value, Mapping) else value


def _plugin_summary(value: JsonValue) -> PluginSummary:
    return PluginSummary.from_mapping(value) if isinstance(value, Mapping) else value


def _skill_summary(value: JsonValue) -> SkillSummary:
    return SkillSummary.from_mapping(value) if isinstance(value, Mapping) else value


def _plugin_detail(value: JsonValue) -> PluginDetail:
    return PluginDetail.from_mapping(value) if isinstance(value, Mapping) else value


def _should_skip(key: str, value: JsonValue, record: _Record) -> bool:
    return (
        key in record._omit_none and value is None
        or key in record._omit_false and value is False
        or key in record._omit_empty and value in ((), [], {})
    )


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


def _serialize(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return copy.deepcopy(value)


def _serialize_camel(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_camel_mapping"):
        return value.to_camel_mapping()
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, tuple):
        return [_serialize_camel(item) for item in value]
    if isinstance(value, list):
        return [_serialize_camel(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_camel(item) for key, item in value.items()}
    return copy.deepcopy(value)


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _camel_to_snake(value: str) -> str:
    result: list[str] = []
    for char in value:
        if char.isupper():
            result.append("_")
            result.append(char.lower())
        else:
            result.append(char)
    return "".join(result).lstrip("_")


__all__ = [
    "HookErrorInfo",
    "HookMetadata",
    "HooksListEntry",
    "HooksListParams",
    "HooksListResponse",
    "MarketplaceAddParams",
    "MarketplaceAddResponse",
    "MarketplaceInterface",
    "MarketplaceLoadErrorInfo",
    "MarketplaceRemoveParams",
    "MarketplaceRemoveResponse",
    "MarketplaceUpgradeErrorInfo",
    "MarketplaceUpgradeParams",
    "MarketplaceUpgradeResponse",
    "PluginAuthPolicy",
    "PluginAvailability",
    "PluginDetail",
    "PluginHookSummary",
    "PluginInstallParams",
    "PluginInstallPolicy",
    "PluginInstallResponse",
    "PluginInstalledParams",
    "PluginInstalledResponse",
    "PluginInterface",
    "PluginListMarketplaceKind",
    "PluginListParams",
    "PluginListResponse",
    "PluginMarketplaceEntry",
    "PluginReadParams",
    "PluginReadResponse",
    "PluginShareCheckoutParams",
    "PluginShareCheckoutResponse",
    "PluginShareContext",
    "PluginShareDeleteParams",
    "PluginShareDeleteResponse",
    "PluginShareDiscoverability",
    "PluginShareListItem",
    "PluginShareListParams",
    "PluginShareListResponse",
    "PluginSharePrincipal",
    "PluginSharePrincipalRole",
    "PluginSharePrincipalType",
    "PluginShareSaveParams",
    "PluginShareSaveResponse",
    "PluginShareTarget",
    "PluginShareTargetRole",
    "PluginShareUpdateDiscoverability",
    "PluginShareUpdateTargetsParams",
    "PluginShareUpdateTargetsResponse",
    "PluginSkillReadParams",
    "PluginSkillReadResponse",
    "PluginSource",
    "PluginSummary",
    "PluginUninstallParams",
    "PluginUninstallResponse",
    "SkillDependencies",
    "SkillErrorInfo",
    "SkillInterface",
    "SkillMetadata",
    "SkillScope",
    "SkillSummary",
    "SkillToolDependency",
    "SkillsChangedNotification",
    "SkillsConfigWriteParams",
    "SkillsConfigWriteResponse",
    "SkillsListEntry",
    "SkillsListParams",
    "SkillsListResponse",
]
