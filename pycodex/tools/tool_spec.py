"""Responses API tool spec helpers ported from ``codex-rs/tools``.

This module owns the ``tool_spec.rs`` boundary: top-level tool-spec variants,
variant names, web-search config adapters, and Responses API JSON
serialization. The function/namespace payloads are dependency inputs from
``responses_api.rs`` and are accepted as mapping-like objects here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.core.client import create_tools_json_for_responses_api as _create_tools_json
from pycodex.core.tools.hosted_spec import FreeformToolFormat
from pycodex.protocol import (
    WebSearchContextSize,
    WebSearchFilters,
    WebSearchUserLocation,
    WebSearchUserLocationType,
)

JsonValue = Any


@dataclass(frozen=True)
class ResponsesApiWebSearchFilters:
    allowed_domains: tuple[str, ...] | None = None

    @classmethod
    def from_config(cls, filters: WebSearchFilters | Mapping[str, JsonValue]) -> "ResponsesApiWebSearchFilters":
        if isinstance(filters, WebSearchFilters):
            domains = filters.allowed_domains
        elif isinstance(filters, Mapping):
            domains = filters.get("allowed_domains")
        else:
            raise TypeError("filters must be WebSearchFilters or mapping")
        return cls(None if domains is None else _string_tuple(domains, "allowed_domains"))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.allowed_domains is not None:
            data["allowed_domains"] = list(self.allowed_domains)
        return data


@dataclass(frozen=True)
class ResponsesApiWebSearchUserLocation:
    type: WebSearchUserLocationType
    country: str | None = None
    region: str | None = None
    city: str | None = None
    timezone: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _coerce_location_type(self.type))
        for field_name in ("country", "region", "city", "timezone"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or None")

    @classmethod
    def from_config(
        cls,
        user_location: WebSearchUserLocation | Mapping[str, JsonValue],
    ) -> "ResponsesApiWebSearchUserLocation":
        if isinstance(user_location, WebSearchUserLocation):
            return cls(
                type=user_location.type,
                country=user_location.country,
                region=user_location.region,
                city=user_location.city,
                timezone=user_location.timezone,
            )
        if not isinstance(user_location, Mapping):
            raise TypeError("user_location must be WebSearchUserLocation or mapping")
        return cls(
            type=_coerce_location_type(user_location.get("type", WebSearchUserLocationType.APPROXIMATE)),
            country=_optional_str(user_location.get("country"), "country"),
            region=_optional_str(user_location.get("region"), "region"),
            city=_optional_str(user_location.get("city"), "city"),
            timezone=_optional_str(user_location.get("timezone"), "timezone"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type.value}
        if self.country is not None:
            data["country"] = self.country
        if self.region is not None:
            data["region"] = self.region
        if self.city is not None:
            data["city"] = self.city
        if self.timezone is not None:
            data["timezone"] = self.timezone
        return data


@dataclass(frozen=True)
class ToolSpec:
    type: str
    payload: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        _ensure_str(self.type, "type")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        object.__setattr__(self, "payload", dict(self.payload))

    @classmethod
    def function(cls, tool: Mapping[str, JsonValue] | Any) -> "ToolSpec":
        return cls("function", _payload_mapping(tool))

    @classmethod
    def namespace(cls, namespace: Mapping[str, JsonValue] | Any) -> "ToolSpec":
        return cls("namespace", _payload_mapping(namespace))

    @classmethod
    def tool_search(
        cls,
        *,
        execution: str,
        description: str,
        parameters: Mapping[str, JsonValue] | Any,
    ) -> "ToolSpec":
        _ensure_str(execution, "execution")
        _ensure_str(description, "description")
        return cls(
            "tool_search",
            {
                "execution": execution,
                "description": description,
                "parameters": _payload_mapping(parameters),
            },
        )

    @classmethod
    def image_generation(cls, output_format: str) -> "ToolSpec":
        _ensure_str(output_format, "output_format")
        return cls("image_generation", {"output_format": output_format})

    @classmethod
    def web_search(
        cls,
        *,
        external_web_access: bool | None = None,
        filters: ResponsesApiWebSearchFilters | WebSearchFilters | Mapping[str, JsonValue] | None = None,
        user_location: ResponsesApiWebSearchUserLocation | WebSearchUserLocation | Mapping[str, JsonValue] | None = None,
        search_context_size: WebSearchContextSize | str | None = None,
        search_content_types: Sequence[str] | None = None,
    ) -> "ToolSpec":
        payload: dict[str, JsonValue] = {}
        if external_web_access is not None:
            if not isinstance(external_web_access, bool):
                raise TypeError("external_web_access must be a bool")
            payload["external_web_access"] = external_web_access
        if filters is not None:
            if not isinstance(filters, ResponsesApiWebSearchFilters):
                filters = ResponsesApiWebSearchFilters.from_config(filters)
            payload["filters"] = filters.to_mapping()
        if user_location is not None:
            if not isinstance(user_location, ResponsesApiWebSearchUserLocation):
                user_location = ResponsesApiWebSearchUserLocation.from_config(user_location)
            payload["user_location"] = user_location.to_mapping()
        if search_context_size is not None:
            payload["search_context_size"] = _enum_or_string(search_context_size, "search_context_size")
        if search_content_types is not None:
            payload["search_content_types"] = list(_string_tuple(search_content_types, "search_content_types"))
        return cls("web_search", payload)

    @classmethod
    def freeform(
        cls,
        *,
        name: str,
        description: str,
        format: FreeformToolFormat,
    ) -> "ToolSpec":
        _ensure_str(name, "name")
        _ensure_str(description, "description")
        if not isinstance(format, FreeformToolFormat):
            raise TypeError("format must be a FreeformToolFormat")
        return cls(
            "custom",
            {
                "name": name,
                "description": description,
                "format": format.to_mapping(),
            },
        )

    def name(self) -> str:
        if self.type in {"function", "namespace", "custom"}:
            name = self.payload.get("name")
            if not isinstance(name, str):
                raise TypeError(f"{self.type} tool spec name must be a string")
            return name
        if self.type == "tool_search":
            return "tool_search"
        if self.type == "image_generation":
            return "image_generation"
        if self.type == "web_search":
            return "web_search"
        raise ValueError(f"unsupported tool spec type: {self.type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type not in {
            "function",
            "namespace",
            "tool_search",
            "image_generation",
            "web_search",
            "custom",
        }:
            raise ValueError(f"unsupported tool spec type: {self.type}")
        return {"type": self.type, **dict(self.payload)}


def create_tools_json_for_responses_api(tools: Sequence[ToolSpec | Mapping[str, JsonValue]]) -> list[dict[str, JsonValue]]:
    return _create_tools_json(tools)


def _payload_mapping(value: Mapping[str, JsonValue] | Any) -> dict[str, JsonValue]:
    if hasattr(value, "to_mapping"):
        value = value.to_mapping()
    if not isinstance(value, Mapping):
        raise TypeError("tool spec payload must be a mapping or expose to_mapping()")
    return dict(value)


def _coerce_location_type(value: WebSearchUserLocationType | str | JsonValue) -> WebSearchUserLocationType:
    if isinstance(value, WebSearchUserLocationType):
        return value
    if isinstance(value, str):
        return WebSearchUserLocationType(value)
    raise TypeError("type must be WebSearchUserLocationType or string")


def _enum_or_string(value: Enum | str, name: str) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return _ensure_str(value, name)


def _ensure_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_str(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, name)


def _string_tuple(value: JsonValue, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be an iterable of strings")
    if not isinstance(value, Sequence):
        raise TypeError(f"{name} must be an iterable of strings")
    result = tuple(value)
    if not all(isinstance(item, str) for item in result):
        raise TypeError(f"{name} must contain only strings")
    return result


__all__ = [
    "ResponsesApiWebSearchFilters",
    "ResponsesApiWebSearchUserLocation",
    "ToolSpec",
    "create_tools_json_for_responses_api",
]
