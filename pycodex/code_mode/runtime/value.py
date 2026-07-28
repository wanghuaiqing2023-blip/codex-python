"""V8/JSON value conversion ported from ``runtime/value.rs``."""
from __future__ import annotations
import json
from collections.abc import Mapping
from typing import Any
from ..response import DEFAULT_IMAGE_DETAIL, FunctionCallOutputContentItem, ImageDetail
JsonValue = Any

CODEX_IMAGE_DETAIL_META_KEY = "codex/imageDetail"


IMAGE_HELPER_EXPECTS_MESSAGE = (
    "image expects a non-empty image URL string, an object with image_url and optional detail, "
    "or a raw MCP image block"
)


def serialize_output_text(value: JsonValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float | str):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def normalize_output_image(
    value: JsonValue,
    detail_override: str | ImageDetail | None = None,
) -> FunctionCallOutputContentItem:
    image_url, detail = _parse_output_image(value)
    if image_url == "":
        raise ValueError(IMAGE_HELPER_EXPECTS_MESSAGE)
    lower = image_url.lower()
    if not (lower.startswith("http://") or lower.startswith("https://") or lower.startswith("data:")):
        raise ValueError("image expects an http(s) or data URL")

    normalized_detail = _normalize_image_detail(detail_override if detail_override is not None else detail)
    return FunctionCallOutputContentItem.input_image(
        image_url,
        normalized_detail or DEFAULT_IMAGE_DETAIL,
    )


def value_to_error_text(value: JsonValue) -> str:
    if isinstance(value, Mapping):
        stack = value.get("stack")
        if isinstance(stack, str):
            return stack
    return serialize_output_text(value)


def _parse_output_image(value: JsonValue) -> tuple[str, str | ImageDetail | None]:
    if isinstance(value, str):
        return value, None
    if isinstance(value, Mapping):
        parsed = _parse_non_mcp_output_image(value)
        if parsed is not None:
            return parsed
        return _parse_mcp_output_image(value)
    raise ValueError(IMAGE_HELPER_EXPECTS_MESSAGE)


def _parse_non_mcp_output_image(
    value: Mapping[str, JsonValue],
) -> tuple[str, str | ImageDetail | None] | None:
    if "image_url" not in value:
        return None
    image_url = value["image_url"]
    if not isinstance(image_url, str):
        raise ValueError(IMAGE_HELPER_EXPECTS_MESSAGE)
    detail = _parse_image_detail_value(value.get("detail"))
    return image_url, detail


def _parse_mcp_output_image(value: Mapping[str, JsonValue]) -> tuple[str, str | None]:
    item_type = value.get("type")
    if not isinstance(item_type, str):
        raise ValueError(IMAGE_HELPER_EXPECTS_MESSAGE)
    if item_type != "image":
        raise ValueError(f'image only accepts MCP image blocks, got "{item_type}"')

    data = value.get("data")
    if not isinstance(data, str) or data == "":
        raise ValueError("image expected MCP image data")

    if data.lower().startswith("data:"):
        image_url = data
    else:
        mime_type = value.get("mimeType", value.get("mime_type"))
        if not isinstance(mime_type, str) or mime_type == "":
            mime_type = "application/octet-stream"
        image_url = f"data:{mime_type};base64,{data}"

    meta = value.get("_meta")
    detail = None
    if isinstance(meta, Mapping):
        raw_detail = meta.get(CODEX_IMAGE_DETAIL_META_KEY)
        if isinstance(raw_detail, str) and raw_detail in {"auto", "low", "high", "original"}:
            detail = raw_detail
    return image_url, detail


def _parse_image_detail_value(value: JsonValue) -> str | ImageDetail | None:
    if value is None:
        return None
    if isinstance(value, ImageDetail):
        return value
    if isinstance(value, str):
        return value
    raise ValueError("image detail must be a string when provided")


def _normalize_image_detail(value: str | ImageDetail | None) -> ImageDetail | None:
    if value is None:
        return None
    if isinstance(value, ImageDetail):
        return value
    normalized = value.lower()
    try:
        return ImageDetail(normalized)
    except ValueError as exc:
        raise ValueError(
            "image detail must be one of: auto, low, high, original"
        ) from exc


def _json_round_trip(value: JsonValue) -> JsonValue:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
