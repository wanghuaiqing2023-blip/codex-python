"""Parity tests for codex-rs/tui/src/exec_cell/mod.rs."""

from pycodex.tui import exec_cell
from pycodex.tui.exec_cell import model, render


def test_exec_cell_module_boundary_metadata_matches_rust_mod():
    assert exec_cell.RUST_MODULE.crate == "codex-tui"
    assert exec_cell.RUST_MODULE.module == "exec_cell"
    assert exec_cell.RUST_MODULE.source == "codex/codex-rs/tui/src/exec_cell/mod.rs"


def test_exec_cell_reexports_model_items():
    assert exec_cell.CommandOutput is model.CommandOutput
    assert exec_cell.ExecCall is model.ExecCall
    assert exec_cell.ExecCell is model.ExecCell


def test_exec_cell_reexports_render_items():
    assert exec_cell.OutputLinesParams is render.OutputLinesParams
    assert exec_cell.TOOL_CALL_MAX_LINES is render.TOOL_CALL_MAX_LINES
    assert exec_cell.new_active_exec_command is render.new_active_exec_command
    assert exec_cell.output_lines is render.output_lines


def test_exec_cell_package_boundary_declares_submodules_only():
    assert exec_cell.EXEC_CELL_SUBMODULES == ("model", "render")
    assert set(exec_cell.__all__) == {
        "CommandOutput",
        "EXEC_CELL_SUBMODULES",
        "ExecCall",
        "ExecCell",
        "OutputLinesParams",
        "RUST_MODULE",
        "TOOL_CALL_MAX_LINES",
        "new_active_exec_command",
        "output_lines",
    }
