"""Original image-detail helpers ported from Codex tools.

This mirrors ``codex-rs/tools/src/image_detail.rs`` and the core re-export in
``codex-rs/core/src/original_image_detail.rs``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pycodex.protocol import (
    DEFAULT_IMAGE_DETAIL,
    FunctionCallOutputContentItem,
    ImageDetail,
    ModelInfo,
)

JsonValue = Any


def can_request_original_image_detail(model_info: ModelInfo) -> bool:
    return bool(model_info.supports_image_detail_original)


def normalize_output_image_detail(
    model_info: ModelInfo,
    detail: ImageDetail | str | None,
) -> ImageDetail | None:
    if isinstance(detail, str):
        detail = ImageDetail(detail)

    if detail is ImageDetail.ORIGINAL and can_request_original_image_detail(model_info):
        return ImageDetail.ORIGINAL
    if detail is ImageDetail.ORIGINAL or detail is None:
        return None
    if detail is ImageDetail.HIGH:
        return ImageDetail.HIGH
    raise ValueError(f"unknown image detail: {detail!r}")


def sanitize_original_image_detail(
    can_request_original_detail: bool,
    items: Iterable[FunctionCallOutputContentItem | JsonValue],
) -> tuple[FunctionCallOutputContentItem, ...]:
    content_items = tuple(FunctionCallOutputContentItem.from_mapping(item) for item in items)
    if can_request_original_detail:
        return content_items

    return tuple(_sanitize_item(item) for item in content_items)


def _sanitize_item(item: FunctionCallOutputContentItem) -> FunctionCallOutputContentItem:
    if item.type == "input_image" and item.detail is ImageDetail.ORIGINAL:
        return FunctionCallOutputContentItem.input_image(
            item.image_url or "",
            DEFAULT_IMAGE_DETAIL,
        )
    return item


__all__ = [
    "can_request_original_image_detail",
    "normalize_output_image_detail",
    "sanitize_original_image_detail",
]
