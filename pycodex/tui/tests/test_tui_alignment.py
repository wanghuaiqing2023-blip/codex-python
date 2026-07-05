from __future__ import annotations

from pathlib import Path
import ast

from pycodex.tui.tui_alignment import CRITICAL_TERMINAL_TUI_MODULES, TUI_ALIGNMENT_ENTRIES


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_terminal_tui_alignment_manifest_paths_exist() -> None:
    for entry in TUI_ALIGNMENT_ENTRIES:
        assert (REPO_ROOT / entry.python_module).exists(), entry.python_module
        assert entry.python_tests, entry.python_module

        for rust_source in entry.rust_sources:
            assert (REPO_ROOT / rust_source).exists(), rust_source
        for python_test in entry.python_tests:
            assert (REPO_ROOT / python_test).exists(), python_test

        for responsibility in entry.responsibilities:
            assert (REPO_ROOT / responsibility.rust_source).exists(), responsibility.rust_source
            for python_test in responsibility.python_tests:
                assert (REPO_ROOT / python_test).exists(), python_test


def test_terminal_tui_alignment_manifest_has_unique_python_modules() -> None:
    python_modules = [entry.python_module for entry in TUI_ALIGNMENT_ENTRIES]
    assert len(python_modules) == len(set(python_modules))


def test_terminal_tui_python_only_adapters_are_explicitly_mapped() -> None:
    adapter_entries = {entry.python_module: entry for entry in TUI_ALIGNMENT_ENTRIES if entry.role != "direct"}

    assert "pycodex/tui/tui/terminal_runtime.py" in adapter_entries
    assert "pycodex/tui/bottom_pane/terminal_surface.py" in adapter_entries

    for entry in adapter_entries.values():
        assert not entry.rust_modules
        assert not entry.rust_sources
        assert "No Rust file named" in entry.notes
        assert entry.responsibilities, entry.python_module


def test_terminal_tui_adapter_responsibilities_are_one_rust_owner_each() -> None:
    for entry in TUI_ALIGNMENT_ENTRIES:
        if entry.role == "direct":
            assert not entry.responsibilities
            continue

        covered_rust_modules = set()
        for responsibility in entry.responsibilities:
            covered_rust_modules.add(responsibility.rust_module)
            assert responsibility.python_tests
            assert responsibility.description
            assert (REPO_ROOT / responsibility.rust_source).exists(), responsibility.rust_source
            for python_test in responsibility.python_tests:
                assert python_test in entry.python_tests or (REPO_ROOT / python_test).exists(), python_test

        assert len(covered_rust_modules) == len(entry.responsibilities)


def test_terminal_tui_direct_entries_are_one_to_one_with_rust_modules() -> None:
    for entry in TUI_ALIGNMENT_ENTRIES:
        if entry.role != "direct":
            continue

        assert len(entry.rust_modules) == 1, entry.python_module
        assert len(entry.rust_sources) == 1, entry.python_module


def test_terminal_tui_critical_modules_are_manifested() -> None:
    expected = {
        "pycodex/tui/tui/event_stream.py",
        "pycodex/tui/ratatui_bridge/buffer.py",
        "pycodex/tui/ratatui_bridge/backend.py",
        "pycodex/tui/tui/terminal_runtime.py",
        "pycodex/tui/bottom_pane/chat_composer.py",
        "pycodex/tui/bottom_pane/command_popup.py",
        "pycodex/tui/bottom_pane/slash_commands.py",
        "pycodex/tui/chatwidget/slash_dispatch.py",
        "pycodex/tui/chatwidget/model_popups.py",
        "pycodex/tui/bottom_pane/list_selection_view.py",
        "pycodex/tui/bottom_pane/bottom_pane_view.py",
        "pycodex/tui/bottom_pane/selection_popup_common.py",
        "pycodex/tui/chatwidget/status_surfaces.py",
        "pycodex/tui/bottom_pane/terminal_frame.py",
        "pycodex/tui/bottom_pane/terminal_controller.py",
        "pycodex/tui/bottom_pane/terminal_surface.py",
        "pycodex/tui/app/resize_reflow.py",
        "pycodex/tui/custom_terminal.py",
        "pycodex/tui/insert_history.py",
    }

    assert expected <= CRITICAL_TERMINAL_TUI_MODULES


def test_terminal_tui_critical_modules_have_manifest_entries() -> None:
    manifest_modules = {entry.python_module for entry in TUI_ALIGNMENT_ENTRIES}

    assert CRITICAL_TERMINAL_TUI_MODULES <= manifest_modules


def test_terminal_tui_manifest_tests_include_rust_evidence_comments() -> None:
    # Rust owner: this project-level guard enforces the TUI porting discipline
    # from AGENTS.md and pycodex/tui/tui_alignment.py. Manifested product-path
    # tests must name the Rust owner/source/behavior evidence they protect.
    evidence_markers = (
        "Rust owner:",
        "Rust owners:",
        "Rust crate",
        "Rust module",
        "Rust source:",
        "Rust sources:",
        "behavior contract",
        "Behavior contract",
    )
    manifested_tests = {
        python_test
        for entry in TUI_ALIGNMENT_ENTRIES
        for python_test in entry.python_tests
    } | {
        python_test
        for entry in TUI_ALIGNMENT_ENTRIES
        for responsibility in entry.responsibilities
        for python_test in responsibility.python_tests
    }

    for python_test in sorted(manifested_tests):
        source = (REPO_ROOT / python_test).read_text(encoding="utf-8-sig")
        assert any(marker in source for marker in evidence_markers), python_test


def test_terminal_product_path_contract_matrix_is_guarded() -> None:
    # Rust owners: tui::event_stream, bottom_pane::chat_composer,
    # command_popup, list_selection_view, chatwidget::model_popups,
    # chatwidget::status_surfaces, custom_terminal, insert_history, and
    # app::resize_reflow collectively define the real-terminal product path.
    # This guard makes the goal-level regression matrix explicit so future
    # refactors cannot silently drop one behavior category while preserving
    # unrelated green tests.
    runtime_tests = _test_function_names(REPO_ROOT / "pycodex/tui/tui/tests/test_terminal_runtime.py")
    controller_tests = _test_function_names(REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_terminal_controller.py")
    surface_tests = _test_function_names(REPO_ROOT / "pycodex/tui/bottom_pane/tests/test_terminal_surface.py")

    required_runtime_tests = {
        "ascii_text_submit": "test_terminal_runtime_key_stream_submits_ascii_prompt",
        "ime_text_submit": "test_terminal_runtime_terminal_event_loop_submits_chinese_text_once",
        "slash_popup_filter_and_navigation": "test_terminal_runtime_slash_popup_renders_and_moves_selection",
        "model_picker": "test_terminal_runtime_model_command_opens_bottom_pane_selection_view",
        "model_reasoning_picker": "test_terminal_runtime_model_command_pushes_reasoning_selection_view",
        "reasoning_footer_update": "test_terminal_runtime_model_reasoning_text_enter_updates_footer_from_low_to_medium",
        "history_visible_during_stream": "test_terminal_runtime_keeps_user_prompt_visible_during_assistant_stream",
        "resize_history_single_copy": "test_terminal_runtime_grow_shrink_replay_has_single_transcript_copy",
        "footer_live_pane": "test_terminal_runtime_terminal_footer_is_live_not_history",
    }
    required_controller_tests = {
        "popup_key_mapping": "test_terminal_controller_maps_rust_like_key_payloads",
        "tab_completes_selected_slash": "test_terminal_controller_moves_slash_highlight_and_tabs_selection",
        "active_view_navigation": "test_terminal_controller_model_command_opens_active_selection_view",
    }
    required_surface_tests = {
        "bottom_pane_frame_diff": "test_terminal_bottom_pane_frame_diff_updates_only_changed_buffer_cells",
        "bottom_pane_history_reflow_on_popup": "test_terminal_bottom_pane_surface_writer_reflows_history_when_popup_footprint_grows",
    }

    assert set(required_runtime_tests.values()) <= runtime_tests
    assert set(required_controller_tests.values()) <= controller_tests
    assert set(required_surface_tests.values()) <= surface_tests


def test_terminal_surface_does_not_own_frame_buffer_projection() -> None:
    # Rust owner: chatwidget::rendering / terminal_frame owns frame->Buffer
    # projection.  terminal_surface is only the custom_terminal live viewport
    # draw adapter and must not grow projection imports or re-export helpers.
    surface_path = REPO_ROOT / "pycodex/tui/bottom_pane/terminal_surface.py"
    source = surface_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    exported = _literal_all(tree)

    forbidden_projection_imports = {
        "Color",
        "Line",
        "Rect",
        "Span",
        "Style",
        "RatatuiColor",
        "DrawCommand",
        "RatatuiLine",
        "RatatuiRect",
        "RatatuiSpan",
        "RatatuiStyle",
        "RatatuiDrawCommand",
        "AnsiBackend",
        "RatatuiAnsiBackend",
        "diff_buffers",
        "ratatui_diff_buffers",
        "full_redraw_commands",
        "ratatui_full_redraw_commands",
        "clear_line_at",
        "clear_lines_at",
        "reset_scroll_region",
        "terminal_move_cursor",
        "RatatuiPosition",
        "TerminalBottomPaneState",
        "terminal_bottom_pane_frame",
        "terminal_bottom_pane_frame_buffer",
        "RatatuiFrameBufferState",
    }
    assert imported_names.isdisjoint(forbidden_projection_imports)
    assert exported == {
        "clear_bottom_pane",
        "clear_bottom_pane_and_flush",
        "render_terminal_bottom_pane_frame",
    }
    assert "def render_bottom_pane" not in source
    assert "def render_bottom_pane_and_flush" not in source
    assert "terminal_bottom_pane_frame_buffer" not in exported
    assert "TerminalBottomPaneBufferState" not in exported
    assert "class TerminalBottomPaneBufferState" not in source
    assert "_full_repaint_commands" not in source
    assert "_render_terminal_bottom_pane_buffer_diff" not in source
    assert "_draw_terminal_bottom_pane_buffer" not in source
    assert "previous_buffer.area" not in source
    assert "frame.cursor_column - 1" not in source
    assert "frame.cursor_row - 1" not in source
    assert "for row in frame.clear_rows" not in source
    assert "for row in bottom_pane_rows_for_size" not in source
    assert "def run_terminal_bottom_pane_" not in source
    assert not any(name.startswith("run_terminal_bottom_pane_") for name in exported)
    assert "def _flush_writer" not in source
    assert "prepare_live_viewport_redraw" in source

    frame_path = REPO_ROOT / "pycodex/tui/bottom_pane/terminal_frame.py"
    frame_source = frame_path.read_text(encoding="utf-8-sig")
    assert "def terminal_bottom_pane_frame_buffer" in frame_source
    assert "def terminal_bottom_pane_frame_cursor_position" in frame_source
    assert "SELECTED_ROW_STYLE" in frame_source


def test_terminal_controller_does_not_own_popup_row_projection() -> None:
    # Rust owners: bottom_pane::command_popup and
    # bottom_pane::list_selection_view own popup/list row projection.
    # terminal_controller may orchestrate key routing and view stack state, but
    # it must not import low-level row rendering helpers or layout geometry.
    controller_path = REPO_ROOT / "pycodex/tui/bottom_pane/terminal_controller.py"
    source = controller_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    exported = _literal_all(tree)

    forbidden_projection_imports = {
        "COMMAND_COLUMN_WIDTH",
        "MAX_POPUP_ROWS",
        "Rect",
        "render_rows_with_col_width_mode",
    }
    assert imported_names.isdisjoint(forbidden_projection_imports)
    assert "terminal_command_popup_lines" in exported
    assert "terminal_selection_view_lines" in exported
    assert "render_rows_with_col_width_mode" not in source
    assert "render_bottom_pane_and_flush" not in source
    assert "render_terminal_bottom_pane_frame" in source
    assert "terminal_bottom_pane_frame_buffer" in source
    assert ".terminal_lines(width=width)" in source


def test_terminal_runtime_does_not_own_bottom_pane_ui_projection() -> None:
    # Rust owners: bottom_pane::chat_composer, command_popup,
    # list_selection_view, chatwidget::model_popups, chatwidget::rendering, and
    # custom_terminal own input interpretation, popup/view rows, frame
    # projection, and buffer redraw.  terminal_runtime may wire those modules
    # together, but it must not import their low-level projection/render types.
    runtime_path = REPO_ROOT / "pycodex/tui/tui/terminal_runtime.py"
    source = runtime_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    forbidden_ui_projection_imports = {
        "Buffer",
        "Color",
        "CommandPopup",
        "Line",
        "ListSelectionView",
        "Rect",
        "SelectionViewParams",
        "Span",
        "Style",
        "TerminalBottomPaneState",
        "TerminalPopupLine",
        "terminal_bottom_pane_frame",
        "terminal_bottom_pane_frame_buffer",
        "terminal_bottom_pane_frame_minimum_row_widths",
        "terminal_command_popup_lines",
        "terminal_selection_view_lines",
        "render_rows_with_col_width_mode",
    }
    assert imported_names.isdisjoint(forbidden_ui_projection_imports)
    assert "terminal_bottom_pane_frame(" not in source
    assert "terminal_bottom_pane_frame_buffer(" not in source
    assert "render_rows_with_col_width_mode" not in source
    assert "TerminalBottomPaneSurfaceWriter" in imported_names
    assert "open_model_popup" in imported_names


def _literal_all(tree: ast.AST) -> set[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        return {str(item) for item in value}
    return set()


def _test_function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }
