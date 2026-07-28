"""Response values ported from ``code-mode/src/response.rs``.

The protocol representation is shared intentionally so Core conversion does not
create a second incompatible image-detail type.
"""
from pycodex.protocol import DEFAULT_IMAGE_DETAIL, FunctionCallOutputContentItem, ImageDetail
__all__ = ["DEFAULT_IMAGE_DETAIL", "FunctionCallOutputContentItem", "ImageDetail"]
