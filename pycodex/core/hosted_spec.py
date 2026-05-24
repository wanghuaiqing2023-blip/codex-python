"""Hosted tool specifications ported from Codex core.

This mirrors the pure helpers in ``core/src/tools/hosted_spec.rs`` for building
OpenAI-hosted image generation and web-search tool specs.
"""

from __future__ import annotations

from dataclasses import dataclass

from pycodex.protocol import (
    WebSearchConfig,
    WebSearchContextSize,
    WebSearchFilters,
    WebSearchMode,
    WebSearchToolType,
    WebSearchUserLocation,
)

WEB_SEARCH_TEXT_AND_IMAGE_CONTENT_TYPES = ("text", "image")


@dataclass(frozen=True)
class FreeformToolFormat:
    type: str
    syntax: str
    definition: str

    @classmethod
    def grammar(cls, *, syntax: str, definition: str) -> "FreeformToolFormat":
        return cls(type="grammar", syntax=syntax, definition=definition)

    def to_mapping(self) -> dict[str, object]:
        return {
            "type": self.type,
            "syntax": self.syntax,
            "definition": self.definition,
        }


@dataclass(frozen=True)
class ToolSpec:
    type: str
    name: str | None = None
    description: str | None = None
    format: FreeformToolFormat | None = None
    output_format: str | None = None
    external_web_access: bool | None = None
    filters: WebSearchFilters | None = None
    user_location: WebSearchUserLocation | None = None
    search_context_size: WebSearchContextSize | None = None
    search_content_types: tuple[str, ...] | None = None

    @classmethod
    def image_generation(cls, output_format: str) -> "ToolSpec":
        return cls(type="image_generation", output_format=output_format)

    @classmethod
    def freeform(
        cls,
        *,
        name: str,
        description: str,
        format: FreeformToolFormat,
    ) -> "ToolSpec":
        return cls(
            type="custom",
            name=name,
            description=description,
            format=format,
        )

    @classmethod
    def web_search(
        cls,
        *,
        external_web_access: bool | None = None,
        filters: WebSearchFilters | None = None,
        user_location: WebSearchUserLocation | None = None,
        search_context_size: WebSearchContextSize | None = None,
        search_content_types: tuple[str, ...] | list[str] | None = None,
    ) -> "ToolSpec":
        return cls(
            type="web_search",
            external_web_access=external_web_access,
            filters=filters,
            user_location=user_location,
            search_context_size=search_context_size,
            search_content_types=tuple(search_content_types) if search_content_types is not None else None,
        )

    def to_mapping(self) -> dict[str, object]:
        data: dict[str, object] = {"type": self.type}
        if self.name is not None:
            data["name"] = self.name
        if self.description is not None:
            data["description"] = self.description
        if self.format is not None:
            data["format"] = self.format.to_mapping()
        if self.output_format is not None:
            data["output_format"] = self.output_format
        if self.external_web_access is not None:
            data["external_web_access"] = self.external_web_access
        if self.filters is not None:
            data["filters"] = {
                "allowed_domains": (
                    list(self.filters.allowed_domains)
                    if self.filters.allowed_domains is not None
                    else None
                )
            }
        if self.user_location is not None:
            data["user_location"] = {
                "type": self.user_location.type.value,
                "country": self.user_location.country,
                "region": self.user_location.region,
                "city": self.user_location.city,
                "timezone": self.user_location.timezone,
            }
        if self.search_context_size is not None:
            data["search_context_size"] = self.search_context_size.value
        if self.search_content_types is not None:
            data["search_content_types"] = list(self.search_content_types)
        return data


@dataclass(frozen=True)
class WebSearchToolOptions:
    web_search_mode: WebSearchMode | None
    web_search_config: WebSearchConfig | None
    web_search_tool_type: WebSearchToolType


def create_image_generation_tool(output_format: str) -> ToolSpec:
    return ToolSpec.image_generation(output_format)


def create_web_search_tool(options: WebSearchToolOptions) -> ToolSpec | None:
    if options.web_search_mode is WebSearchMode.CACHED:
        external_web_access = False
    elif options.web_search_mode is WebSearchMode.LIVE:
        external_web_access = True
    else:
        return None

    if options.web_search_tool_type is WebSearchToolType.TEXT_AND_IMAGE:
        search_content_types = WEB_SEARCH_TEXT_AND_IMAGE_CONTENT_TYPES
    else:
        search_content_types = None

    config = options.web_search_config
    return ToolSpec.web_search(
        external_web_access=external_web_access,
        filters=config.filters if config is not None else None,
        user_location=config.user_location if config is not None else None,
        search_context_size=config.search_context_size if config is not None else None,
        search_content_types=search_content_types,
    )


__all__ = [
    "FreeformToolFormat",
    "ToolSpec",
    "WEB_SEARCH_TEXT_AND_IMAGE_CONTENT_TYPES",
    "WebSearchToolOptions",
    "create_image_generation_tool",
    "create_web_search_tool",
]
