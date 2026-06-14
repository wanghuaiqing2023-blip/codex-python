"""Semantic package boundary for codex-rs/tui/src/exec_cell/mod.rs.

Rust declares ``model`` and ``render`` submodules and re-exports selected items
from them. Python mirrors that package-level export without marking submodule
behavior complete at this level.
"""

from __future__ import annotations

from .._porting import RustTuiModule
from .model import CommandOutput, ExecCall, ExecCell
from .render import OutputLinesParams, TOOL_CALL_MAX_LINES, new_active_exec_command, output_lines


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="exec_cell",
    source="codex/codex-rs/tui/src/exec_cell/mod.rs",
)

EXEC_CELL_SUBMODULES = ("model", "render")


__all__ = [
    "CommandOutput",
    "EXEC_CELL_SUBMODULES",
    "ExecCall",
    "ExecCell",
    "OutputLinesParams",
    "RUST_MODULE",
    "TOOL_CALL_MAX_LINES",
    "new_active_exec_command",
    "output_lines",
]
