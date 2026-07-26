"""Normalize terminal streams and reconstruct their current VT screen."""

from ._native_tui import normalize_tui_text
from ._native_tui import vt_screen_text

__all__ = ["normalize_tui_text", "vt_screen_text"]
