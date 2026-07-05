"""Machine-readable alignment map for the terminal TUI framework.

The entries in this file are intentionally small and high-signal. They cover
the runtime/input/bottom-pane modules where ad-hoc Python-only patches are most
likely to drift from the upstream Rust `codex-tui` crate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AdapterResponsibility:
    """One Rust-owned responsibility implemented by a Python adapter."""

    name: str
    rust_module: str
    rust_source: str
    python_tests: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class TuiAlignmentEntry:
    """A Python TUI module and the Rust behavior boundary it must track."""

    python_module: str
    python_tests: tuple[str, ...]
    rust_modules: tuple[str, ...] = ()
    rust_sources: tuple[str, ...] = ()
    role: str = "direct"
    notes: str = ""
    responsibilities: tuple[AdapterResponsibility, ...] = ()


TUI_ALIGNMENT_ENTRIES: tuple[TuiAlignmentEntry, ...] = (
    TuiAlignmentEntry(
        python_module="pycodex/tui/tui/event_stream.py",
        rust_modules=("codex-tui::tui::event_stream",),
        rust_sources=("codex/codex-rs/tui/src/tui/event_stream.rs",),
        python_tests=("pycodex/tui/tui/tests/test_event_stream.py",),
        notes="Only produces Rust-like terminal events; command semantics belong downstream.",
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/ratatui_bridge/buffer.py",
        python_tests=("pycodex/tui/ratatui_bridge/tests/test_ratatui_bridge.py",),
        role="ratatui-core-adapter",
        notes=(
            "No Rust file named ratatui_bridge/buffer.rs exists in codex-tui. "
            "This module models the ratatui Buffer/Cell semantics used by custom_terminal."
        ),
        responsibilities=(
            AdapterResponsibility(
                name="cell-addressable frame buffer",
                rust_module="codex-tui::custom_terminal",
                rust_source="codex/codex-rs/tui/src/custom_terminal.rs",
                python_tests=("pycodex/tui/ratatui_bridge/tests/test_ratatui_bridge.py",),
                description="Provides the Buffer/Cell render target needed by the Python custom terminal core.",
            ),
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/ratatui_bridge/backend.py",
        python_tests=("pycodex/tui/ratatui_bridge/tests/test_ratatui_bridge.py",),
        role="ratatui-core-adapter",
        notes=(
            "No Rust file named ratatui_bridge/backend.rs exists in codex-tui. "
            "This module models the backend/frame/terminal lifecycle used by custom_terminal."
        ),
        responsibilities=(
            AdapterResponsibility(
                name="frame buffer diff and terminal draw lifecycle",
                rust_module="codex-tui::custom_terminal",
                rust_source="codex/codex-rs/tui/src/custom_terminal.rs",
                python_tests=("pycodex/tui/ratatui_bridge/tests/test_ratatui_bridge.py",),
                description=(
                    "Provides current/previous buffer diffing, full-redraw command "
                    "generation, shared previous-frame buffer state, Terminal.draw "
                    "semantics, TestBackend, and draw-buffer-to-ANSI helpers for "
                    "Python adapters."
                ),
            ),
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/tui/terminal_runtime.py",
        python_tests=("pycodex/tui/tui/tests/test_terminal_runtime.py",),
        role="terminal-product-adapter",
        notes=(
            "No Rust file named terminal_runtime.rs exists. This adapter may only glue "
            "the Rust-owned event loop, app, bottom-pane, and terminal side-effect "
            "boundaries together."
        ),
        responsibilities=(
            AdapterResponsibility(
                name="terminal event loop",
                rust_module="codex-tui::tui",
                rust_source="codex/codex-rs/tui/src/tui.rs",
                python_tests=("pycodex/tui/tui/tests/test_terminal_runtime.py",),
                description="Runs the terminal product loop without owning app or widget semantics.",
            ),
            AdapterResponsibility(
                name="terminal input stream",
                rust_module="codex-tui::tui::event_stream",
                rust_source="codex/codex-rs/tui/src/tui/event_stream.rs",
                python_tests=("pycodex/tui/tui/tests/test_event_stream.py",),
                description="Consumes Rust-like key/paste/resize/eof events from the event source.",
            ),
            AdapterResponsibility(
                name="app dispatch boundary",
                rust_module="codex-tui::app",
                rust_source="codex/codex-rs/tui/src/app.rs",
                python_tests=("pycodex/tui/tui/tests/test_terminal_runtime.py",),
                description="Delegates app-owned commands, history, and status mutations to app/chatwidget modules.",
            ),
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/chat_composer.py",
        rust_modules=("codex-tui::bottom_pane::chat_composer",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/chat_composer.rs",),
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_chat_composer.py",
            "pycodex/tui/bottom_pane/tests/test_chat_composer_slash_input.py",
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/command_popup.py",
        rust_modules=("codex-tui::bottom_pane::command_popup",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/command_popup.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_command_popup.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/slash_commands.py",
        rust_modules=("codex-tui::bottom_pane::slash_commands",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/slash_commands.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_slash_commands.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/slash_dispatch.py",
        rust_modules=("codex-tui::chatwidget::slash_dispatch",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/slash_dispatch.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_slash_dispatch.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/model_popups.py",
        rust_modules=("codex-tui::chatwidget::model_popups",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/model_popups.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_model_popups.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/list_selection_view.py",
        rust_modules=("codex-tui::bottom_pane::list_selection_view",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/list_selection_view.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_list_selection_view.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/bottom_pane_view.py",
        rust_modules=("codex-tui::bottom_pane::bottom_pane_view",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/bottom_pane_view.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_bottom_pane_view.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/selection_popup_common.py",
        rust_modules=("codex-tui::bottom_pane::selection_popup_common",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/selection_popup_common.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_selection_popup_common.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/status_surfaces.py",
        rust_modules=("codex-tui::chatwidget::status_surfaces",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/status_surfaces.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_status_surfaces.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/terminal_frame.py",
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_terminal_frame.py",
            "pycodex/tui/bottom_pane/tests/test_terminal_surface.py",
        ),
        role="terminal-frame-adapter",
        notes=(
            "No Rust file named terminal_frame.rs exists. This adapter models the "
            "bottom-pane ratatui frame/footprint for Python's hybrid terminal backend."
        ),
        responsibilities=(
            AdapterResponsibility(
                name="bottom-pane frame layout projection",
                rust_module="codex-tui::chatwidget::rendering",
                rust_source="codex/codex-rs/tui/src/chatwidget/rendering.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_frame.py",
                    "pycodex/tui/bottom_pane/tests/test_terminal_surface.py",
                ),
                description=(
                    "Builds the Rust-like bottom-pane frame rows/writes and projects them "
                    "into a ratatui-like buffer consumed by the terminal repaint adapter; "
                    "does not perform terminal side effects."
                ),
            ),
            AdapterResponsibility(
                name="bottom-pane footprint model",
                rust_module="codex-tui::app::resize_reflow",
                rust_source="codex/codex-rs/tui/src/app/resize_reflow.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_frame.py",
                    "pycodex/tui/app/tests/test_resize_reflow.py",
                ),
                description=(
                    "Computes live-pane row reservations and history bottom rows so "
                    "resize reflow can replay transcript history without disappearing."
                ),
            ),
            AdapterResponsibility(
                name="footer projection placement",
                rust_module="codex-tui::bottom_pane::footer",
                rust_source="codex/codex-rs/tui/src/bottom_pane/footer.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_frame.py",
                    "pycodex/tui/bottom_pane/tests/test_footer.py",
                ),
                description="Places footer-owned terminal projection in the bottom-pane frame.",
            ),
            AdapterResponsibility(
                name="live status placement",
                rust_module="codex-tui::chatwidget::status_surfaces",
                rust_source="codex/codex-rs/tui/src/chatwidget/status_surfaces.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_frame.py",
                    "pycodex/tui/chatwidget/tests/test_status_surfaces.py",
                ),
                description="Places status_surfaces-owned live-status projection in the frame.",
            ),
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/terminal_controller.py",
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_terminal_controller.py",
            "pycodex/tui/bottom_pane/tests/test_terminal_surface.py",
            "pycodex/tui/tui/tests/test_terminal_runtime.py",
        ),
        role="terminal-bottom-pane-controller-adapter",
        notes=(
            "No Rust file named terminal_controller.rs exists. This adapter wires "
            "Rust-owned bottom-pane command/view state to Python's hybrid terminal backend."
        ),
        responsibilities=(
            AdapterResponsibility(
                name="composer popup key routing",
                rust_module="codex-tui::bottom_pane::chat_composer",
                rust_source="codex/codex-rs/tui/src/bottom_pane/chat_composer.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_controller.py",
                    "pycodex/tui/bottom_pane/tests/test_chat_composer.py",
                ),
                description=(
                    "Tracks terminal-path draft text and routes popup keys according "
                    "to chat_composer semantics; does not render terminal output."
                ),
            ),
            AdapterResponsibility(
                name="slash command popup navigation",
                rust_module="codex-tui::bottom_pane::command_popup",
                rust_source="codex/codex-rs/tui/src/bottom_pane/command_popup.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_controller.py",
                    "pycodex/tui/bottom_pane/tests/test_command_popup.py",
                ),
                description="Delegates slash filtering, selected item state, and terminal rows to CommandPopup.",
            ),
            AdapterResponsibility(
                name="active bottom-pane view stack",
                rust_module="codex-tui::bottom_pane::bottom_pane_view",
                rust_source="codex/codex-rs/tui/src/bottom_pane/bottom_pane_view.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_controller.py",
                    "pycodex/tui/bottom_pane/tests/test_bottom_pane_view.py",
                ),
                description="Owns terminal-path active view stack orchestration while ListSelectionView owns row state.",
            ),
            AdapterResponsibility(
                name="footprint reflow trigger",
                rust_module="codex-tui::app::resize_reflow",
                rust_source="codex/codex-rs/tui/src/app/resize_reflow.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_surface.py",
                    "pycodex/tui/app/tests/test_resize_reflow.py",
                ),
                description="Reports controller-detected live-pane footprint changes so resize reflow can repaint history.",
            ),
            AdapterResponsibility(
                name="live buffer lifecycle invalidation",
                rust_module="codex-tui::custom_terminal",
                rust_source="codex/codex-rs/tui/src/custom_terminal.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_controller.py",
                    "pycodex/tui/tui/tests/test_terminal_runtime.py",
                ),
                description=(
                    "Invalidates the previous live-pane buffer when resize, history replay, "
                    "or footprint repaint side effects change the visible terminal outside "
                    "the normal bottom-pane diff render."
                ),
            ),
            AdapterResponsibility(
                name="terminal bottom-pane action orchestration",
                rust_module="codex-tui::bottom_pane",
                rust_source="codex/codex-rs/tui/src/bottom_pane/mod.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_controller.py",
                    "pycodex/tui/bottom_pane/tests/test_terminal_surface.py",
                ),
                description=(
                    "Executes bottom-pane clear/render plans using terminal product "
                    "callbacks such as resize, terminal size, and live buffer invalidation; "
                    "actual live viewport side effects stay in terminal_surface."
                ),
            ),
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/terminal_surface.py",
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_terminal_surface.py",
            "pycodex/tui/bottom_pane/tests/test_terminal_frame.py",
        ),
        role="terminal-render-adapter",
        notes=(
            "No Rust file named terminal_surface.rs exists. This adapter exists because "
            "Python preserves ordinary terminal scrollback while Rust redraws a ratatui "
            "frame. UI behavior must still be owned by the listed Rust modules."
        ),
        responsibilities=(
            AdapterResponsibility(
                name="live viewport buffer draw and terminal side effects",
                rust_module="codex-tui::custom_terminal",
                rust_source="codex/codex-rs/tui/src/custom_terminal.rs",
                python_tests=("pycodex/tui/bottom_pane/tests/test_terminal_surface.py",),
                description=(
                    "Consumes current/previous bottom-pane buffers, delegates full repaint "
                    "and same-area diff drawing to ratatui_bridge's backend helper, delegates "
                    "row clearing and writer flushing to custom_terminal, and keeps only "
                    "live-pane clear/render frame and cursor-placement side effects."
                ),
            ),
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/resize_reflow.py",
        rust_modules=("codex-tui::app::resize_reflow",),
        rust_sources=("codex/codex-rs/tui/src/app/resize_reflow.rs",),
        python_tests=("pycodex/tui/app/tests/test_resize_reflow.py",),
        notes="Runtime use from tui.rs is a validation path, not a second owner.",
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/custom_terminal.py",
        rust_modules=("codex-tui::custom_terminal",),
        rust_sources=("codex/codex-rs/tui/src/custom_terminal.rs",),
        python_tests=("tests/test_tui_custom_terminal.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/insert_history.py",
        rust_modules=("codex-tui::insert_history",),
        rust_sources=("codex/codex-rs/tui/src/insert_history.rs",),
        python_tests=("tests/test_tui_insert_history.py",),
    ),
)


CRITICAL_TERMINAL_TUI_MODULES: frozenset[str] = frozenset(
    {
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
)


def repository_relative_path(path: str) -> Path:
    """Return a repository-relative path object without touching the filesystem."""

    return Path(path.replace("\\", "/"))


__all__ = [
    "AdapterResponsibility",
    "CRITICAL_TERMINAL_TUI_MODULES",
    "TUI_ALIGNMENT_ENTRIES",
    "TuiAlignmentEntry",
    "repository_relative_path",
]
