"""Tool specification for the Rust ``view_image_spec`` module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

JsonValue = Any
VIEW_IMAGE_TOOL_NAME = "view_image"


@dataclass(frozen=True)
class ViewImageToolOptions:
    can_request_original_image_detail: bool = False
    include_environment_id: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.can_request_original_image_detail, bool):
            raise TypeError("can_request_original_image_detail must be a bool")
        if not isinstance(self.include_environment_id, bool):
            raise TypeError("include_environment_id must be a bool")


def create_view_image_tool(
    options: ViewImageToolOptions = ViewImageToolOptions(),
) -> dict[str, JsonValue]:
    if not isinstance(options, ViewImageToolOptions):
        raise TypeError("options must be ViewImageToolOptions")
    properties: dict[str, JsonValue] = {
        "path": {"type": "string", "description": "Local filesystem path to an image file"}
    }
    if options.can_request_original_image_detail:
        properties["detail"] = {
            "type": "string",
            "enum": ["high", "original"],
            "description": "Optional detail override. Supported values are `high` and `original`; omit this field for default high resized behavior. Use `original` to preserve the file's original resolution instead of resizing to fit. This is important when high-fidelity image perception or precise localization is needed, especially for CUA agents.",
        }
    if options.include_environment_id:
        properties["environment_id"] = {
            "type": "string",
            "description": "Optional selected environment id to target. Omit this to use the primary environment.",
        }
    return {
        "type": "function",
        "name": VIEW_IMAGE_TOOL_NAME,
        "description": "View a local image file from the filesystem when visual inspection is needed. Use this for images already available on disk.",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": ["path"],
            "additionalProperties": False,
        },
        "output_schema": view_image_output_schema(),
    }


def view_image_output_schema() -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "image_url": {"type": "string", "description": "Data URL for the loaded image."},
            "detail": {
                "type": "string",
                "enum": ["high", "original"],
                "description": "Image detail hint returned by view_image. Returns `high` for default resized behavior or `original` when original resolution is preserved.",
            },
        },
        "required": ["image_url", "detail"],
        "additionalProperties": False,
    }


__all__ = [
    "VIEW_IMAGE_TOOL_NAME",
    "ViewImageToolOptions",
    "create_view_image_tool",
    "view_image_output_schema",
]
