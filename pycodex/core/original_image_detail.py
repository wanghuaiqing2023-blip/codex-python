"""Re-exports matching codex-core's ``original_image_detail`` module."""

from pycodex.tools.original_image_detail import can_request_original_image_detail
from pycodex.tools.original_image_detail import sanitize_original_image_detail


__all__ = [
    "can_request_original_image_detail",
    "sanitize_original_image_detail",
]
