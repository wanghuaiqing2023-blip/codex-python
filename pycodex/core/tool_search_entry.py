"""Tool-search entries ported from Codex core.

This mirrors the pure conversion logic in
``core/src/tools/tool_search_entry.rs`` and the adjacent loadable-spec helpers
from ``codex-rs/tools/src/responses_api.rs``.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

JsonValue = Any


def _ensure_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _ensure_optional_str(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field)


def _ensure_mapping(value: object, field: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return value


def _ensure_tool_list(value: object, field: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError(f"{field} must be a list")
    return value


@dataclass(frozen=True)
class ToolSearchEntry:
    search_text: str
    output: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "search_text", _ensure_str(self.search_text, "search_text"))


@dataclass(frozen=True)
class ToolSearchSourceInfo:
    name: str
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "description", _ensure_optional_str(self.description, "description"))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"name": self.name}
        if self.description is not None:
            data["description"] = self.description
        return data


@dataclass(frozen=True)
class ToolSearchInfo:
    entry: ToolSearchEntry
    source_info: ToolSearchSourceInfo | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.entry, ToolSearchEntry):
            raise TypeError("entry must be a ToolSearchEntry")
        if self.source_info is not None and not isinstance(self.source_info, ToolSearchSourceInfo):
            raise TypeError("source_info must be ToolSearchSourceInfo")

    @classmethod
    def from_spec(
        cls,
        search_text: str,
        spec: JsonValue,
        source_info: ToolSearchSourceInfo | Mapping[str, JsonValue] | None = None,
    ) -> "ToolSearchInfo | None":
        search_text = _ensure_str(search_text, "search_text")
        output = loadable_tool_spec_from_spec(spec)
        if output is None:
            return None
        return cls(
            entry=ToolSearchEntry(search_text=search_text, output=output),
            source_info=_coerce_source_info(source_info),
        )


def default_namespace_description(namespace_name: str) -> str:
    namespace_name = _ensure_str(namespace_name, "namespace_name")
    return f"Tools in the {namespace_name} namespace."


def loadable_tool_spec_from_spec(spec: JsonValue) -> JsonValue | None:
    data = _spec_to_mapping(spec)
    tool_type = data.get("type")
    if tool_type == "function":
        tool = copy.deepcopy(data)
        tool["defer_loading"] = True
        tool.pop("output_schema", None)
        return tool

    if tool_type == "namespace":
        namespace = copy.deepcopy(data)
        name = _ensure_str(namespace.get("name"), "namespace.name")
        description = _ensure_str(namespace.get("description", ""), "namespace.description")
        if description.strip() == "":
            namespace["description"] = default_namespace_description(name)
        namespace["tools"] = [
            _deferred_namespace_tool(tool)
            for tool in _ensure_tool_list(namespace.get("tools", []), "namespace.tools")
        ]
        return namespace

    return None


def coalesce_loadable_tool_specs(specs: Iterable[JsonValue]) -> tuple[JsonValue, ...]:
    coalesced: list[JsonValue] = []
    for spec in specs:
        data = _spec_to_mapping(spec)
        if data.get("type") != "namespace":
            coalesced.append(copy.deepcopy(data))
            continue

        namespace = copy.deepcopy(data)
        _ensure_str(namespace.get("name"), "namespace.name")
        _ensure_tool_list(namespace.get("tools", []), "namespace.tools")
        existing = next(
            (
                item
                for item in coalesced
                if isinstance(item, dict)
                and item.get("type") == "namespace"
                and item.get("name") == namespace.get("name")
            ),
            None,
        )
        if existing is None:
            coalesced.append(namespace)
        else:
            existing.setdefault("tools", []).extend(namespace.get("tools", []))
    return tuple(coalesced)


def _deferred_namespace_tool(tool: JsonValue) -> JsonValue:
    data = _spec_to_mapping(tool)
    if data.get("type") != "function":
        raise TypeError("namespace tool must be a function")
    _ensure_str(data.get("name"), "tool.name")
    deferred = copy.deepcopy(data)
    deferred["defer_loading"] = True
    deferred.pop("output_schema", None)
    return deferred


def _spec_to_mapping(spec: JsonValue) -> dict[str, JsonValue]:
    if hasattr(spec, "to_mapping"):
        spec = spec.to_mapping()
    if not isinstance(spec, Mapping):
        raise TypeError("tool spec must be a mapping or expose to_mapping()")
    return dict(_ensure_mapping(spec, "tool spec"))


def _coerce_source_info(
    source_info: ToolSearchSourceInfo | Mapping[str, JsonValue] | None,
) -> ToolSearchSourceInfo | None:
    if source_info is None or isinstance(source_info, ToolSearchSourceInfo):
        return source_info
    data = _ensure_mapping(source_info, "source_info")
    return ToolSearchSourceInfo(
        name=_ensure_str(data.get("name"), "source_info.name"),
        description=_ensure_optional_str(data.get("description"), "source_info.description"),
    )


__all__ = [
    "ToolSearchEntry",
    "ToolSearchInfo",
    "ToolSearchSourceInfo",
    "coalesce_loadable_tool_specs",
    "default_namespace_description",
    "loadable_tool_spec_from_spec",
]
