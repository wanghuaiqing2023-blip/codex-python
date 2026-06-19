"""Tool output boundary ported from ``codex-rs/tools``.

Rust defines the ``ToolOutput`` trait and ``JsonToolOutput`` in
``codex-tools``. The Python runtime keeps the implementation in
``pycodex.core.tools.context`` with the rest of the dispatch context; this
module exposes the canonical tools-crate import path while preserving shared
runtime types.
"""

from pycodex.core.tools.context import (
    JsonToolOutput,
    ToolOutput,
    boxed_tool_output,
    telemetry_preview,
)

__all__ = [
    "JsonToolOutput",
    "ToolOutput",
    "boxed_tool_output",
    "telemetry_preview",
]
