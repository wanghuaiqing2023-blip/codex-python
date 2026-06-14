"""Width guards for transcript rendering with fixed prefix columns.

Upstream source: ``codex/codex-rs/tui/src/width.rs``.
"""

from __future__ import annotations

from typing import Any

from ._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="width", source="codex/codex-rs/tui/src/width.rs")


def _require_rust_unsigned(value: int, name: str, *, bits: int | None = None) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    if bits is not None and value > (1 << bits) - 1:
        raise ValueError(f"{name} must fit in u{bits}")
    return value


def usable_content_width(total_width: int, reserved_cols: int) -> int | None:
    """Return usable content width after reserving fixed columns.

    Mirrors Rust ``usable_content_width(total_width: usize, reserved_cols:
    usize) -> Option<usize>``. The result is strictly positive, or ``None``
    when the reserved columns consume the whole width.
    """

    total_width = _require_rust_unsigned(total_width, "total_width")
    reserved_cols = _require_rust_unsigned(reserved_cols, "reserved_cols")
    remaining = total_width - reserved_cols
    return remaining if remaining > 0 else None


def usable_content_width_u16(total_width: int, reserved_cols: int) -> int | None:
    """``u16`` convenience wrapper around :func:`usable_content_width`."""

    total_width = _require_rust_unsigned(total_width, "total_width", bits=16)
    reserved_cols = _require_rust_unsigned(reserved_cols, "reserved_cols", bits=16)
    return usable_content_width(total_width, reserved_cols)

__all__ = [
    "RUST_MODULE",
    "usable_content_width",
    "usable_content_width_u16",
]
