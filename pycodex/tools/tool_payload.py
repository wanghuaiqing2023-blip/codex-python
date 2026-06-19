"""Tool payload boundary ported from ``codex-rs/tools``.

Rust defines ``ToolPayload`` in ``codex-tools`` and core consumes it throughout
tool dispatch. The Python implementation lives in ``pycodex.core.tools.context``
with the rest of the runtime context models; this module exposes the canonical
tools-crate import path while preserving a single shared payload type.
"""

from pycodex.core.tools.context import ToolPayload

__all__ = ["ToolPayload"]
