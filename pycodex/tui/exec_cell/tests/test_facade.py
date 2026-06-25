"""Parity tests for Rust ``codex-tui::exec_cell`` facade.

Rust source: ``codex/codex-rs/tui/src/exec_cell/mod.rs``.
"""

from pycodex.tui import exec_cell
from pycodex.tui.exec_cell import model, render


def test_exec_cell_parent_facade_reexports_rust_items() -> None:
    """Rust ``mod.rs`` declares ``model``/``render`` and re-exports selected items."""

    assert exec_cell.RUST_MODULE.module == "exec_cell"
    assert exec_cell.RUST_MODULE.source == "codex/codex-rs/tui/src/exec_cell/mod.rs"
    assert exec_cell.EXEC_CELL_SUBMODULES == ("model", "render")

    assert exec_cell.CommandOutput is model.CommandOutput
    assert exec_cell.ExecCall is model.ExecCall
    assert exec_cell.ExecCell is model.ExecCell
    assert exec_cell.OutputLinesParams is render.OutputLinesParams
    assert exec_cell.TOOL_CALL_MAX_LINES == render.TOOL_CALL_MAX_LINES
    assert exec_cell.new_active_exec_command is render.new_active_exec_command
    assert exec_cell.output_lines is render.output_lines
