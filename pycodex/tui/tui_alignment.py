"""Machine-readable alignment map for the terminal TUI framework.

The entries in this file are intentionally small and high-signal. They cover
the runtime/input/bottom-pane modules where ad-hoc Python-only patches are most
likely to drift from the upstream Rust `codex-tui` crate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


RUST_CODEX_BASELINE_COMMIT = "1c7832ffa37a3ab56f601497c00bfce120370bf9"


@dataclass(frozen=True)
class AdapterResponsibility:
    """One Rust-owned responsibility implemented by a Python adapter."""

    name: str
    rust_module: str
    rust_source: str
    python_tests: tuple[str, ...]
    description: str
    rust_commit: str = RUST_CODEX_BASELINE_COMMIT


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
    rust_commit: str = RUST_CODEX_BASELINE_COMMIT


@dataclass(frozen=True)
class TuiModuleOwner:
    """Module-level owner map for Rust behavior contracts.

    File-level entries above remain useful audit anchors, but the porting
    acceptance unit is a Rust module behavior contract.  A Python owner may be
    a package or a single file, and the files underneath it are implementation
    details that must not drift into unrelated Rust-owned behavior.
    """

    python_owner: str
    rust_module: str
    rust_source: str
    implementation_files: tuple[str, ...]
    python_tests: tuple[str, ...]
    role: str = "direct"
    notes: str = ""
    rust_commit: str = RUST_CODEX_BASELINE_COMMIT


TUI_ALIGNMENT_ENTRIES: tuple[TuiAlignmentEntry, ...] = (
    TuiAlignmentEntry(
        python_module="pycodex/tui/app_event.py",
        rust_modules=("codex-tui::app_event",),
        rust_sources=("codex/codex-rs/tui/src/app_event.rs",),
        python_tests=("tests/test_tui_app_event.py",),
        notes="Owns the single canonical AppEvent payload and variant model.",
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app_event_sender.py",
        rust_modules=("codex-tui::app_event_sender",),
        rust_sources=("codex/codex-rs/tui/src/app_event_sender.rs",),
        python_tests=("tests/test_tui_app_event_sender.py",),
        notes=(
            "Wraps the app event send endpoint only; receiving and dispatch "
            "belong to codex-tui::app."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/runtime.py",
        rust_modules=("codex-tui::app",),
        rust_sources=("codex/codex-rs/tui/src/app.rs",),
        python_tests=("pycodex/tui/app/tests/test_runtime.py",),
        notes=(
            "Owns the app event channel receiver, FIFO dispatch, and app-loop "
            "step ordering. Bottom-pane and terminal adapters may invoke this "
            "boundary but must not receive or drain AppEvent themselves."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/tui/event_stream.py",
        rust_modules=("codex-tui::tui::event_stream",),
        rust_sources=("codex/codex-rs/tui/src/tui/event_stream.rs",),
        python_tests=("pycodex/tui/tui/tests/test_event_stream.py",),
        notes=(
            "Owns terminal input-source creation, stdin terminal detection, and "
            "Rust-like terminal events, including submitted-turn stream "
            "event/idle/closed polling and idle-maintenance callback binding; "
            "command semantics belong downstream."
        ),
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
                description=(
                    "Consumes Rust-like key/paste/resize/eof events and stdin "
                    "terminal-state decisions plus submitted-turn idle callback "
                    "binding from the event source owner."
                ),
            ),
            AdapterResponsibility(
                name="app dispatch boundary",
                rust_module="codex-tui::app",
                rust_source="codex/codex-rs/tui/src/app.rs",
                python_tests=("pycodex/tui/tui/tests/test_terminal_runtime.py",),
                description=(
                    "Delegates each bottom-pane input cycle to app-owned "
                    "run_app_event_loop_step, plus app-owned commands, history, "
                    "and status mutations; chatwidget retains prompt slash/local "
                    "classification."
                ),
            ),
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/chat_composer/__init__.py",
        rust_modules=("codex-tui::bottom_pane::chat_composer",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/chat_composer.rs",),
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_chat_composer.py",
            "pycodex/tui/bottom_pane/tests/test_chat_composer_slash_input.py",
        ),
        notes=(
            "Owns composer input lifecycle and coordinates DraftState, command "
            "popup, and history. DraftState is the sole editable-state field; "
            "all ordinary editing is delegated to its TextArea and rendering "
            "uses its TextAreaState. Also owns prompt presentation, "
            "submit/EOF/interrupt outcomes, runtime-bound prompt/submit/EOF "
            "effect callbacks, "
            "and slash popup synchronization; terminal_runtime supplies IO "
            "handles and callbacks only."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/chat_composer/attachment_state.py",
        rust_modules=("codex-tui::bottom_pane::chat_composer::attachment_state",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/chat_composer/attachment_state.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_chat_composer_attachment_state.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/chat_composer/draft_state.py",
        rust_modules=("codex-tui::bottom_pane::chat_composer::draft_state",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/chat_composer/draft_state.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_chat_composer_draft_state.py",),
        notes="Owns DraftState composition of TextArea and TextAreaState plus draft-local paste and mention metadata.",
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/textarea/__init__.py",
        rust_modules=("codex-tui::bottom_pane::textarea",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/textarea.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_textarea_mod.py",),
        notes="Sole owner of editable text, cursor, atomic element boundaries, visual-line movement, wrapping, and cursor_pos_with_state.",
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/chat_composer_history.py",
        rust_modules=("codex-tui::bottom_pane::chat_composer_history",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/chat_composer_history.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_chat_composer_history.py",),
        notes="Owns local and persistent composer history navigation; ChatComposer supplies real text and cursor byte offsets.",
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/chat_composer/footer_state.py",
        rust_modules=("codex-tui::bottom_pane::chat_composer::footer_state",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/chat_composer/footer_state.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_chat_composer_footer_state.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/chat_composer/history_search.py",
        rust_modules=("codex-tui::bottom_pane::chat_composer::history_search",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/chat_composer/history_search.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_chat_composer_history_search.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/chat_composer/popup_state.py",
        rust_modules=("codex-tui::bottom_pane::chat_composer::popup_state",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/chat_composer/popup_state.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_chat_composer_popup_state.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/chat_composer/slash_input.py",
        rust_modules=("codex-tui::bottom_pane::chat_composer::slash_input",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/chat_composer/slash_input.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_chat_composer_slash_input.py",),
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
        notes=(
            "Owns terminal completed-prompt classification before terminal_runtime "
            "submits a user turn: blank input, local slash command handling, exit, "
            "or normal user text."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/model_popups.py",
        rust_modules=("codex-tui::chatwidget::model_popups",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/model_popups.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_model_popups.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/rendering.py",
        rust_modules=("codex-tui::chatwidget::rendering",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/rendering.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_rendering.py",),
        notes=(
            "Owns the chatwidget render composition contract that bottom-pane "
            "terminal frame adapters reference when projecting composer, active "
            "cell, hook cell, and cursor behavior. It also owns the side-effect-free "
            "terminal bottom-pane frame DTOs, frame construction, and frame-to-buffer "
            "projection used by Python's hybrid terminal backend."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/turn_runtime.py",
        rust_modules=("codex-tui::chatwidget::turn_runtime",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/turn_runtime.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_turn_runtime.py",),
        notes=(
            "Owns terminal turn-start/submission lifecycle and runtime-bound "
            "turn submission runner callbacks. terminal_runtime binds this "
            "owner runner instead of assembling started-at and submission "
            "callbacks at the call site."
        ),
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
        python_module="pycodex/tui/bottom_pane/view_stack.py",
        rust_modules=("codex-tui::bottom_pane",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/mod.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_view_stack.py",),
        notes=(
            "Ports BottomPane view-state ownership, active-view-first composer "
            "event routing, command-popup suppression, and child-view "
            "completion rules, plus terminal render context projection, so "
            "terminal adapters do not own active-view stack or popup/cursor "
            "semantics. It holds one ChatComposer and never stores a parallel "
            "draft, history, popup, or cursor editor."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/selection_popup_common.py",
        rust_modules=("codex-tui::bottom_pane::selection_popup_common",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/selection_popup_common.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_selection_popup_common.py",),
        notes=(
            "Owns shared selection-popup row measurement, wrapping, selected-row "
            "style, and terminal popup line width clipping before chatwidget.rendering "
            "places those rows into the live-pane frame."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/status_surfaces.py",
        rust_modules=("codex-tui::chatwidget::status_surfaces",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/status_surfaces.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_status_surfaces.py",),
        notes=(
            "Owns status text, live-status hide/clear transitions, turn-status "
            "refresh/force-render state, active-turn composer cursor visibility, "
            "protocol-facing callback methods, and delayed bottom-pane render "
            "callback binding consumed by terminal_runtime."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/status/card.py",
        rust_modules=("codex-tui::status::card",),
        rust_sources=("codex/codex-rs/tui/src/status/card.rs",),
        python_tests=("pycodex/tui/status/tests/test_card.py",),
        notes=(
            "Owns the history-facing /status card surface and runtime-bound "
            "callback used by terminal local-command dispatch."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/history_ui.py",
        rust_modules=("codex-tui::app::history_ui",),
        rust_sources=("codex/codex-rs/tui/src/app/history_ui.rs",),
        python_tests=("pycodex/tui/app/tests/test_history_ui.py",),
        notes=(
            "Owns /clear terminal reset sequencing, session-header repaint, "
            "and the runtime-bound clear-UI executor used by local commands."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/terminal_footprint.py",
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_terminal_footprint.py",
            "pycodex/tui/app/tests/test_resize_reflow.py",
        ),
        role="terminal-footprint-adapter",
        notes=(
            "No Rust file named terminal_footprint.rs exists. This adapter models "
            "the bottom-pane desired-height/row footprint used by Python's hybrid "
            "terminal backend before custom_terminal draws the live viewport."
        ),
        responsibilities=(
            AdapterResponsibility(
                name="bottom-pane desired height footprint",
                rust_module="codex-tui::bottom_pane::chat_composer",
                rust_source="codex/codex-rs/tui/src/bottom_pane/chat_composer.rs",
                python_tests=("pycodex/tui/bottom_pane/tests/test_terminal_footprint.py",),
                description=(
                    "Models the compact terminal-path footprint derived from "
                    "composer/footer/live-status/popup desired heights and "
                    "assigns the concrete status/composer/popup/footer rows "
                    "consumed by the frame renderer."
                ),
            ),
            AdapterResponsibility(
                name="history viewport footprint value",
                rust_module="codex-tui::app::resize_reflow",
                rust_source="codex/codex-rs/tui/src/app/resize_reflow.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_footprint.py",
                    "pycodex/tui/app/tests/test_resize_reflow.py",
                ),
                description=(
                    "Provides compact row reservations consumed by resize_reflow "
                    "for footprint transition comparison and history repaint."
                ),
            ),
            AdapterResponsibility(
                name="live viewport clear rows",
                rust_module="codex-tui::custom_terminal",
                rust_source="codex/codex-rs/tui/src/custom_terminal.rs",
                python_tests=("pycodex/tui/bottom_pane/tests/test_terminal_footprint.py",),
                description="Projects the footprint into custom_terminal's generic clear request.",
            ),
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/terminal_action.py",
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_terminal_action.py",
        ),
        role="terminal-action-adapter",
        notes=(
            "No Rust file named terminal_action.rs exists. This adapter prepares "
            "bottom-pane clear/render requests, actions, and frame input state "
            "for Python's hybrid terminal backend before chatwidget.rendering "
            "assembles rows and projects them into a buffer."
        ),
        responsibilities=(
            AdapterResponsibility(
                name="bottom-pane render action gating",
                rust_module="codex-tui::bottom_pane::chat_composer",
                rust_source="codex/codex-rs/tui/src/bottom_pane/chat_composer.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_action.py",
                ),
                description=(
                    "Prepares clear/render requests, actions, and frame input "
                    "state from composer/footer/status/popup context so "
                    "terminal_controller and terminal adapters do not own "
                    "TTY/layout gating, render-context field unpacking, or "
                    "resize-owned render-pass field unpacking."
                ),
            ),
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/terminal_projection.py",
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_terminal_projection.py",
        ),
        role="terminal-projection-adapter",
        notes=(
            "No Rust file named terminal_projection.rs exists. This adapter "
            "bridges bottom-pane frame output to custom_terminal's generic live "
            "viewport update contract for Python's hybrid terminal backend."
        ),
        responsibilities=(
            AdapterResponsibility(
                name="live viewport request and backend metadata projection",
                rust_module="codex-tui::custom_terminal",
                rust_source="codex/codex-rs/tui/src/custom_terminal.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_projection.py",
                    "tests/test_tui_custom_terminal.py",
                ),
                description=(
                    "Projects bottom-pane clear/render frame geometry into "
                    "custom_terminal's generic live viewport projection/request "
                    "types, including the one-based compatibility cursor callback "
                    "target, minimum visible row widths, intentional blank rows, "
                    "the zero-based ratatui cursor position, and cleanup fields "
                    "from bottom-pane-owned clear/render requests. It also owns "
                    "the bottom-pane request-runner adapter that supplies the "
                    "projection callback to custom_terminal's generic request "
                    "runner, so no separate terminal_surface adapter needs to "
                    "call action_plan, build clear/render-pass requests, read "
                    "request cursor policy, or unpack row/cursor/backend "
                    "metadata or request cleanup fields. "
                    "This keeps chatwidget.rendering from owning backend "
                    "compatibility projections."
                ),
            ),
            AdapterResponsibility(
                name="terminal bottom-pane action runner",
                rust_module="codex-tui::bottom_pane",
                rust_source="codex/codex-rs/tui/src/bottom_pane/mod.rs",
                python_tests=("pycodex/tui/bottom_pane/tests/test_terminal_projection.py",),
                description=(
                    "Consumes bottom-pane-owned clear/render requests and "
                    "supplies the projection-owner callback to the "
                    "custom_terminal request lifecycle. It also exposes "
                    "request-runner methods that build clear/render-pass "
                    "requests plus the resize-reflow clear/render-pass "
                    "callbacks and factories through terminal_action owner "
                    "helpers so "
                    "terminal_controller does not import request builders, "
                    "render-pass protocols, define pass/context unpacking "
                    "closures, or define local clear-request closures; it "
                    "does not own command, popup, model, "
                    "reasoning, footer, resize, cursor, request gating, or "
                    "backend flush semantics."
                ),
            ),
            AdapterResponsibility(
                name="bottom-pane frame handoff",
                rust_module="codex-tui::chatwidget::rendering",
                rust_source="codex/codex-rs/tui/src/chatwidget/rendering.rs",
                python_tests=("pycodex/tui/bottom_pane/tests/test_terminal_projection.py",),
                description=(
                    "Consumes chatwidget.rendering's side-effect-free frame row "
                    "projection and buffer projection without owning "
                    "composer, popup, footer, or status layout behavior."
                ),
            ),
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/terminal_controller.py",
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_terminal_controller.py",
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
                    "Synchronizes terminal-path composer draft text into "
                    "bottom_pane.view_stack's combined owner state and delegates "
                    "active-view-first popup key routing to the bottom-pane "
                    "owner; it does not expose draft state, create active views "
                    "directly, or render terminal output."
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
                    "pycodex/tui/bottom_pane/tests/test_view_stack.py",
                ),
                description=(
                    "Terminal adapter holds the bottom-pane view-state object but "
                    "receives command-view factory and selection-event callbacks "
                    "through bottom_pane.view_stack's owner boundary and delegates "
                    "stack replacement, command-popup suppression, active-view "
                    "input precedence, completion semantics, approval request "
                    "consumption, and resolved-request dismissal to "
                    "bottom_pane.view_stack while concrete command view creation "
                    "stays with chatwidget owners and ListSelectionView owns row "
                    "state."
                ),
            ),
            AdapterResponsibility(
                name="footprint reflow trigger",
                rust_module="codex-tui::app::resize_reflow",
                rust_source="codex/codex-rs/tui/src/app/resize_reflow.rs",
                python_tests=(
                    "pycodex/tui/bottom_pane/tests/test_terminal_controller.py",
                    "pycodex/tui/app/tests/test_resize_reflow.py",
                ),
                description=(
                    "Provides bottom-pane owner state and cursor callbacks, a "
                    "render callback backed by the terminal_projection request "
                    "runner boundary, and the external repaint runner to "
                    "resize_reflow. The controller "
                    "requests the footprint cycle runner from the resize_reflow "
                    "owner so clear callback binding, footprint-change "
                    "detection, render-context acquisition, history viewport "
                    "bounds, footprint timing, no-op detection, remembered "
                    "footprint state, and external repaint dispatch stay "
                    "inside app::resize_reflow. It also "
                    "exposes no-resize clear/render callback methods for "
                    "runtime collaborators whose owner already handles resize "
                    "timing, instead of making terminal_runtime spell those "
                    "callback policies out with local lambdas or tracker "
                    "construction in the controller."
                ),
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
                    "the normal bottom-pane diff render, by requesting "
                    "custom_terminal's owner-managed projection-cycle runner instead "
                    "of constructing LiveViewportRenderer or resetting raw buffer state."
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
        python_module="pycodex/tui/app/agent_message_consolidation.py",
        rust_modules=("codex-tui::app::agent_message_consolidation",),
        rust_sources=("codex/codex-rs/tui/src/app/agent_message_consolidation.rs",),
        python_tests=("pycodex/tui/app/tests/test_agent_message_consolidation.py",),
        notes=(
            "Owns replacement of trailing streamed AgentMessageCell values with "
            "one source-backed AgentMarkdownCell and selects the Rust consolidation "
            "reflow boundary."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/streaming.py",
        rust_modules=("codex-tui::chatwidget::streaming",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/streaming.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_streaming.py",),
        notes=(
            "Owns the product StreamController lifecycle: AgentMessageDelta, "
            "commit ticks, stable history cells, mutable frame tail, and completion "
            "dispatch to app::agent_message_consolidation."
        ),
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
        notes=(
            "Owns finalized and resize-replayed scrollback insertion helpers; "
            "resize_reflow decides when replay happens, but terminal_runtime "
            "must not rebuild insert-history clear/render flag combinations."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/history_cell/messages.py",
        rust_modules=("codex-tui::history_cell::messages",),
        rust_sources=("codex/codex-rs/tui/src/history_cell/messages.rs",),
        python_tests=("pycodex/tui/history_cell/tests/test_messages.py",),
        notes=(
            "Owns source-backed user, stable assistant, streaming-tail, and "
            "consolidated Markdown history cells. Product streaming state belongs "
            "to chatwidget::streaming; this module contains no terminal-only "
            "string delta or finalized projection model."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/history_cell/session.py",
        rust_modules=("codex-tui::history_cell::session",),
        rust_sources=("codex/codex-rs/tui/src/history_cell/session.rs",),
        python_tests=("pycodex/tui/history_cell/tests/test_session.py",),
        notes=(
            "Owns session header/tooltip/startup notice history-cell text plus "
            "runtime-bound startup notice writer callbacks for the terminal "
            "product path."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/protocol_requests.py",
        rust_modules=("codex-tui::chatwidget::protocol_requests",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/protocol_requests.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_protocol_requests.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/tool_requests.py",
        rust_modules=("codex-tui::chatwidget::tool_requests",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/tool_requests.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_tool_requests.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/approval_overlay.py",
        rust_modules=("codex-tui::bottom_pane::approval_overlay",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/approval_overlay.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_approval_overlay.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/request_user_input/__init__.py",
        rust_modules=("codex-tui::bottom_pane::request_user_input",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_request_user_input_mod.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/mcp_server_elicitation.py",
        rust_modules=("codex-tui::bottom_pane::mcp_server_elicitation",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/mcp_server_elicitation.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_mcp_server_elicitation.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/app_server_requests.py",
        rust_modules=("codex-tui::app::app_server_requests",),
        rust_sources=("codex/codex-rs/tui/src/app/app_server_requests.rs",),
        python_tests=("pycodex/tui/app/tests/test_app_server_requests.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/pending_interactive_replay.py",
        rust_modules=("codex-tui::app::pending_interactive_replay",),
        rust_sources=("codex/codex-rs/tui/src/app/pending_interactive_replay.rs",),
        python_tests=("pycodex/tui/app/tests/test_pending_interactive_replay.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/history_cell/request_user_input.py",
        rust_modules=("codex-tui::history_cell::request_user_input",),
        rust_sources=("codex/codex-rs/tui/src/history_cell/request_user_input.rs",),
        python_tests=("pycodex/tui/history_cell/tests/test_request_user_input.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/app_link_view.py",
        rust_modules=("codex-tui::bottom_pane::app_link_view",),
        rust_sources=("codex/codex-rs/tui/src/bottom_pane/app_link_view.rs",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_app_link_view.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/app_server_events.py",
        rust_modules=("codex-tui::app::app_server_events",),
        rust_sources=("codex/codex-rs/tui/src/app/app_server_events.rs",),
        python_tests=("pycodex/tui/app/tests/test_app_server_events.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/thread_routing.py",
        rust_modules=("codex-tui::app::thread_routing",),
        rust_sources=("codex/codex-rs/tui/src/app/thread_routing.rs",),
        python_tests=("pycodex/tui/app/tests/test_thread_routing.py",),
        notes=(
            "Owns inactive-thread request conversion, thread labels, pending "
            "request routing, and the SelectAgentThread behavior contract."
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/thread_events.py",
        rust_modules=("codex-tui::app::thread_events",),
        rust_sources=("codex/codex-rs/tui/src/app/thread_events.rs",),
        python_tests=("pycodex/tui/app/tests/test_thread_events.py",),
        notes="Preserves request identity and pending replay state per thread.",
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/event_dispatch.py",
        rust_modules=("codex-tui::app::event_dispatch",),
        rust_sources=("codex/codex-rs/tui/src/app/event_dispatch.rs",),
        python_tests=("pycodex/tui/app/tests/test_event_dispatch.py",),
        notes="Owns typed SelectAgentThread and full-screen approval execution.",
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/bottom_pane/pending_thread_approvals.py",
        rust_modules=("codex-tui::bottom_pane::pending_thread_approvals",),
        rust_sources=(
            "codex/codex-rs/tui/src/bottom_pane/pending_thread_approvals.rs",
        ),
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_pending_thread_approvals.py",
        ),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/side.py",
        rust_modules=("codex-tui::app::side",),
        rust_sources=("codex/codex-rs/tui/src/app/side.rs",),
        python_tests=("pycodex/tui/app/tests/test_side.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/app/platform_actions.py",
        rust_modules=("codex-tui::app::platform_actions",),
        rust_sources=("codex/codex-rs/tui/src/app/platform_actions.rs",),
        python_tests=("pycodex/tui/app/tests/test_platform_actions.py",),
    ),
    TuiAlignmentEntry(
        python_module="pycodex/tui/chatwidget/interaction.py",
        rust_modules=("codex-tui::chatwidget::interaction",),
        rust_sources=("codex/codex-rs/tui/src/chatwidget/interaction.rs",),
        python_tests=("pycodex/tui/chatwidget/tests/test_interaction.py",),
    ),
)


TUI_MODULE_OWNERS: tuple[TuiModuleOwner, ...] = (
    TuiModuleOwner(
        python_owner="pycodex/tui/bottom_pane/chat_composer/__init__.py",
        rust_module="codex-tui::bottom_pane::chat_composer",
        rust_source="codex/codex-rs/tui/src/bottom_pane/chat_composer.rs",
        implementation_files=("pycodex/tui/bottom_pane/chat_composer/__init__.py",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_chat_composer.py",),
        notes="Coordinates DraftState, popup, history, submission, and terminal projection without owning a second text buffer.",
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/bottom_pane/chat_composer/draft_state.py",
        rust_module="codex-tui::bottom_pane::chat_composer::draft_state",
        rust_source="codex/codex-rs/tui/src/bottom_pane/chat_composer/draft_state.rs",
        implementation_files=("pycodex/tui/bottom_pane/chat_composer/draft_state.py",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_chat_composer_draft_state.py",),
        notes="Composes TextArea and TextAreaState as the Rust draft owner.",
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/bottom_pane/textarea",
        rust_module="codex-tui::bottom_pane::textarea",
        rust_source="codex/codex-rs/tui/src/bottom_pane/textarea.rs",
        implementation_files=(
            "pycodex/tui/bottom_pane/textarea/__init__.py",
            "pycodex/tui/bottom_pane/textarea/vim.py",
        ),
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_textarea_mod.py",
            "pycodex/tui/bottom_pane/tests/test_textarea_vim.py",
        ),
        notes="Sole editable-text, cursor, atomic-element, wrapping, and viewport-coordinate owner.",
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/bottom_pane/chat_composer_history.py",
        rust_module="codex-tui::bottom_pane::chat_composer_history",
        rust_source="codex/codex-rs/tui/src/bottom_pane/chat_composer_history.rs",
        implementation_files=("pycodex/tui/bottom_pane/chat_composer_history.py",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_chat_composer_history.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app_event.py",
        rust_module="codex-tui::app_event",
        rust_source="codex/codex-rs/tui/src/app_event.rs",
        implementation_files=("pycodex/tui/app_event.py",),
        python_tests=("tests/test_tui_app_event.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app_event_sender.py",
        rust_module="codex-tui::app_event_sender",
        rust_source="codex/codex-rs/tui/src/app_event_sender.rs",
        implementation_files=("pycodex/tui/app_event_sender.py",),
        python_tests=("tests/test_tui_app_event_sender.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/runtime.py",
        rust_module="codex-tui::app",
        rust_source="codex/codex-rs/tui/src/app.rs",
        implementation_files=("pycodex/tui/app/runtime.py",),
        python_tests=("pycodex/tui/app/tests/test_runtime.py",),
        notes=(
            "Owns app event receive/dispatch ordering. Product adapters call "
            "the app-loop step instead of draining the channel themselves."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/app_server_events.py",
        rust_module="codex-tui::app::app_server_events",
        rust_source="codex/codex-rs/tui/src/app/app_server_events.rs",
        implementation_files=("pycodex/tui/app/app_server_events.py",),
        python_tests=("pycodex/tui/app/tests/test_app_server_events.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/thread_routing.py",
        rust_module="codex-tui::app::thread_routing",
        rust_source="codex/codex-rs/tui/src/app/thread_routing.rs",
        implementation_files=("pycodex/tui/app/thread_routing.py",),
        python_tests=("pycodex/tui/app/tests/test_thread_routing.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/thread_events.py",
        rust_module="codex-tui::app::thread_events",
        rust_source="codex/codex-rs/tui/src/app/thread_events.rs",
        implementation_files=("pycodex/tui/app/thread_events.py",),
        python_tests=("pycodex/tui/app/tests/test_thread_events.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/event_dispatch.py",
        rust_module="codex-tui::app::event_dispatch",
        rust_source="codex/codex-rs/tui/src/app/event_dispatch.rs",
        implementation_files=("pycodex/tui/app/event_dispatch.py",),
        python_tests=("pycodex/tui/app/tests/test_event_dispatch.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/bottom_pane/pending_thread_approvals.py",
        rust_module="codex-tui::bottom_pane::pending_thread_approvals",
        rust_source="codex/codex-rs/tui/src/bottom_pane/pending_thread_approvals.rs",
        implementation_files=(
            "pycodex/tui/bottom_pane/pending_thread_approvals.py",
        ),
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_pending_thread_approvals.py",
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/side.py",
        rust_module="codex-tui::app::side",
        rust_source="codex/codex-rs/tui/src/app/side.rs",
        implementation_files=("pycodex/tui/app/side.py",),
        python_tests=("pycodex/tui/app/tests/test_side.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/platform_actions.py",
        rust_module="codex-tui::app::platform_actions",
        rust_source="codex/codex-rs/tui/src/app/platform_actions.rs",
        implementation_files=("pycodex/tui/app/platform_actions.py",),
        python_tests=("pycodex/tui/app/tests/test_platform_actions.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/chatwidget/interaction.py",
        rust_module="codex-tui::chatwidget::interaction",
        rust_source="codex/codex-rs/tui/src/chatwidget/interaction.rs",
        implementation_files=("pycodex/tui/chatwidget/interaction.py",),
        python_tests=("pycodex/tui/chatwidget/tests/test_interaction.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/tui/event_stream.py",
        rust_module="codex-tui::tui::event_stream",
        rust_source="codex/codex-rs/tui/src/tui/event_stream.rs",
        implementation_files=("pycodex/tui/tui/event_stream.py",),
        python_tests=("pycodex/tui/tui/tests/test_event_stream.py",),
        notes=(
            "Owns terminal input-source mapping plus submitted-turn "
            "event/idle/closed stream polling and runtime-bound idle ticker "
            "callbacks for the terminal product path."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/tui/terminal_runtime.py",
        rust_module="codex-tui::tui",
        rust_source="codex/codex-rs/tui/src/tui.rs",
        implementation_files=("pycodex/tui/tui/terminal_runtime.py",),
        python_tests=("pycodex/tui/tui/tests/test_terminal_runtime.py",),
        role="terminal-product-adapter",
        notes=(
            "Python keeps a product-path adapter, but the module contract is "
            "Rust tui.rs event-loop/draw orchestration. UI behavior belongs to "
            "bottom_pane/chatwidget/custom_terminal owners."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/ratatui_bridge",
        rust_module="codex-tui::custom_terminal",
        rust_source="codex/codex-rs/tui/src/custom_terminal.rs",
        implementation_files=(
            "pycodex/tui/ratatui_bridge/backend.py",
            "pycodex/tui/ratatui_bridge/buffer.py",
            "pycodex/tui/ratatui_bridge/crossterm.py",
            "pycodex/tui/ratatui_bridge/layout.py",
            "pycodex/tui/ratatui_bridge/renderable.py",
            "pycodex/tui/ratatui_bridge/rich_adapter.py",
            "pycodex/tui/ratatui_bridge/style.py",
            "pycodex/tui/ratatui_bridge/text.py",
            "pycodex/tui/ratatui_bridge/widgets.py",
        ),
        python_tests=("pycodex/tui/ratatui_bridge/tests/test_ratatui_bridge.py",),
        role="ratatui-core-adapter",
        notes=(
            "Minimal ratatui-like primitives used by Python custom_terminal and "
            "bottom-pane frame rendering. This owner supplies backend/frame "
            "mechanics only, not slash/model/history behavior."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/custom_terminal.py",
        rust_module="codex-tui::custom_terminal",
        rust_source="codex/codex-rs/tui/src/custom_terminal.rs",
        implementation_files=("pycodex/tui/custom_terminal.py",),
        python_tests=("tests/test_tui_custom_terminal.py",),
        notes=(
            "Owns generic live viewport requests, updates, projection envelopes, "
            "prepared projection-cycle unpacking, cursor policy, diff/flush "
            "lifecycle, and external repaint invalidation for Python's hybrid "
            "terminal backend."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/chatwidget/streaming.py",
        rust_module="codex-tui::chatwidget::streaming",
        rust_source="codex/codex-rs/tui/src/chatwidget/streaming.rs",
        implementation_files=("pycodex/tui/chatwidget/streaming.py",),
        python_tests=("pycodex/tui/chatwidget/tests/test_streaming.py",),
        notes=(
            "Owns the real terminal product StreamController, adaptive commit tick, "
            "stable-cell insertion callback, and mutable live-tail frame projection."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/chatwidget/protocol.py",
        rust_module="codex-tui::chatwidget::protocol",
        rust_source="codex/codex-rs/tui/src/chatwidget/protocol.rs",
        implementation_files=("pycodex/tui/chatwidget/protocol.py",),
        python_tests=(
            "pycodex/tui/chatwidget/tests/test_protocol.py",
            "pycodex/tui/chatwidget/tests/test_protocol_composition.py",
        ),
        notes="Owns notification routing into typed active/final history cells.",
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/chatwidget/command_lifecycle.py",
        rust_module="codex-tui::chatwidget::command_lifecycle",
        rust_source="codex/codex-rs/tui/src/chatwidget/command_lifecycle.rs",
        implementation_files=("pycodex/tui/chatwidget/command_lifecycle.py",),
        python_tests=("pycodex/tui/chatwidget/tests/test_command_lifecycle.py",),
        notes="Owns active ExecCell grouping, output updates, and final insertion.",
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/exec_cell",
        rust_module="codex-tui::exec_cell",
        rust_source="codex/codex-rs/tui/src/exec_cell/mod.rs",
        implementation_files=(
            "pycodex/tui/exec_cell/__init__.py",
            "pycodex/tui/exec_cell/model.py",
            "pycodex/tui/exec_cell/render.py",
        ),
        python_tests=(
            "pycodex/tui/exec_cell/tests/test_model.py",
            "pycodex/tui/exec_cell/tests/test_render.py",
        ),
        notes="Owns canonical command history-cell model and rendering.",
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/diff_render.py",
        rust_module="codex-tui::diff_render",
        rust_source="codex/codex-rs/tui/src/diff_render.rs",
        implementation_files=("pycodex/tui/diff_render.py",),
        python_tests=("pycodex/tui/tests/test_diff_render.py",),
        notes="Owns line-numbered, styled add/delete/update diff rendering.",
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/history_cell/patches.py",
        rust_module="codex-tui::history_cell::patches",
        rust_source="codex/codex-rs/tui/src/history_cell/patches.rs",
        implementation_files=("pycodex/tui/history_cell/patches.py",),
        python_tests=("pycodex/tui/history_cell/tests/test_patches.py",),
        notes="Owns patch and patch-failure HistoryCell boundaries.",
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/history_cell/separators.py",
        rust_module="codex-tui::history_cell::separators",
        rust_source="codex/codex-rs/tui/src/history_cell/separators.rs",
        implementation_files=("pycodex/tui/history_cell/separators.py",),
        python_tests=("pycodex/tui/history_cell/tests/test_separators.py",),
        notes="Owns final-message separator HistoryCell rendering.",
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/agent_message_consolidation.py",
        rust_module="codex-tui::app::agent_message_consolidation",
        rust_source="codex/codex-rs/tui/src/app/agent_message_consolidation.rs",
        implementation_files=("pycodex/tui/app/agent_message_consolidation.py",),
        python_tests=("pycodex/tui/app/tests/test_agent_message_consolidation.py",),
        notes=(
            "Owns typed terminal transcript consolidation and Required versus "
            "IfResizeReflowRan completion behavior."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/insert_history.py",
        rust_module="codex-tui::insert_history",
        rust_source="codex/codex-rs/tui/src/insert_history.rs",
        implementation_files=("pycodex/tui/insert_history.py",),
        python_tests=("tests/test_tui_insert_history.py",),
        notes=(
            "Owns terminal scrollback insertion state and helpers for normal, "
            "streaming, and resize-replayed history rows. app::resize_reflow "
            "owns replay timing; terminal_runtime only wires the callback."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/history_cell/messages.py",
        rust_module="codex-tui::history_cell::messages",
        rust_source="codex/codex-rs/tui/src/history_cell/messages.rs",
        implementation_files=("pycodex/tui/history_cell/messages.py",),
        python_tests=("pycodex/tui/history_cell/tests/test_messages.py",),
        notes=(
            "Owns terminal user-prompt history-cell output, assistant streaming "
            "projection, and runtime-bound prompt-output writer callbacks for "
            "the terminal product path."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/history_cell/session.py",
        rust_module="codex-tui::history_cell::session",
        rust_source="codex/codex-rs/tui/src/history_cell/session.rs",
        implementation_files=("pycodex/tui/history_cell/session.py",),
        python_tests=("pycodex/tui/history_cell/tests/test_session.py",),
        notes=(
            "Owns session header, tooltip, and startup notice history-cell "
            "projection plus terminal runtime startup-notice callback binding."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/resize_reflow.py",
        rust_module="codex-tui::app::resize_reflow",
        rust_source="codex/codex-rs/tui/src/app/resize_reflow.rs",
        implementation_files=("pycodex/tui/app/resize_reflow.py",),
        python_tests=("pycodex/tui/app/tests/test_resize_reflow.py",),
        notes=(
            "Owns resize/layout lifecycle state, replay timing, bottom-pane "
            "footprint reflow, bottom-pane render-cycle callback binding, "
            "clear-cycle callback binding, and "
            "dynamic terminal-layout-active provider callbacks consumed by "
            "terminal runtime bindings."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/chatwidget/protocol_requests.py",
        rust_module="codex-tui::chatwidget::protocol_requests",
        rust_source="codex/codex-rs/tui/src/chatwidget/protocol_requests.rs",
        implementation_files=("pycodex/tui/chatwidget/protocol_requests.py",),
        python_tests=("pycodex/tui/chatwidget/tests/test_protocol_requests.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/chatwidget/tool_requests.py",
        rust_module="codex-tui::chatwidget::tool_requests",
        rust_source="codex/codex-rs/tui/src/chatwidget/tool_requests.rs",
        implementation_files=("pycodex/tui/chatwidget/tool_requests.py",),
        python_tests=("pycodex/tui/chatwidget/tests/test_tool_requests.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/bottom_pane/approval_overlay.py",
        rust_module="codex-tui::bottom_pane::approval_overlay",
        rust_source="codex/codex-rs/tui/src/bottom_pane/approval_overlay.rs",
        implementation_files=("pycodex/tui/bottom_pane/approval_overlay.py",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_approval_overlay.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/bottom_pane/request_user_input",
        rust_module="codex-tui::bottom_pane::request_user_input",
        rust_source="codex/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs",
        implementation_files=("pycodex/tui/bottom_pane/request_user_input/__init__.py",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_request_user_input_mod.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/bottom_pane/mcp_server_elicitation.py",
        rust_module="codex-tui::bottom_pane::mcp_server_elicitation",
        rust_source="codex/codex-rs/tui/src/bottom_pane/mcp_server_elicitation.rs",
        implementation_files=("pycodex/tui/bottom_pane/mcp_server_elicitation.py",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_mcp_server_elicitation.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/app_server_requests.py",
        rust_module="codex-tui::app::app_server_requests",
        rust_source="codex/codex-rs/tui/src/app/app_server_requests.rs",
        implementation_files=("pycodex/tui/app/app_server_requests.py",),
        python_tests=("pycodex/tui/app/tests/test_app_server_requests.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/pending_interactive_replay.py",
        rust_module="codex-tui::app::pending_interactive_replay",
        rust_source="codex/codex-rs/tui/src/app/pending_interactive_replay.rs",
        implementation_files=("pycodex/tui/app/pending_interactive_replay.py",),
        python_tests=("pycodex/tui/app/tests/test_pending_interactive_replay.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/history_cell/request_user_input.py",
        rust_module="codex-tui::history_cell::request_user_input",
        rust_source="codex/codex-rs/tui/src/history_cell/request_user_input.rs",
        implementation_files=("pycodex/tui/history_cell/request_user_input.py",),
        python_tests=("pycodex/tui/history_cell/tests/test_request_user_input.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/bottom_pane/app_link_view.py",
        rust_module="codex-tui::bottom_pane::app_link_view",
        rust_source="codex/codex-rs/tui/src/bottom_pane/app_link_view.rs",
        implementation_files=("pycodex/tui/bottom_pane/app_link_view.py",),
        python_tests=("pycodex/tui/bottom_pane/tests/test_app_link_view.py",),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/bottom_pane",
        rust_module="codex-tui::bottom_pane",
        rust_source="codex/codex-rs/tui/src/bottom_pane/mod.rs",
        implementation_files=(
            "pycodex/tui/bottom_pane/bottom_pane_view.py",
            "pycodex/tui/bottom_pane/chat_composer/__init__.py",
            "pycodex/tui/bottom_pane/chat_composer/attachment_state.py",
            "pycodex/tui/bottom_pane/chat_composer/draft_state.py",
            "pycodex/tui/bottom_pane/chat_composer/footer_state.py",
            "pycodex/tui/bottom_pane/chat_composer/history_search.py",
            "pycodex/tui/bottom_pane/chat_composer/popup_state.py",
            "pycodex/tui/bottom_pane/chat_composer/slash_input.py",
            "pycodex/tui/bottom_pane/command_popup.py",
            "pycodex/tui/bottom_pane/footer.py",
            "pycodex/tui/bottom_pane/list_selection_view.py",
            "pycodex/tui/bottom_pane/selection_popup_common.py",
            "pycodex/tui/bottom_pane/terminal_action.py",
            "pycodex/tui/bottom_pane/terminal_footprint.py",
            "pycodex/tui/bottom_pane/slash_commands.py",
            "pycodex/tui/bottom_pane/terminal_controller.py",
            "pycodex/tui/bottom_pane/terminal_projection.py",
            "pycodex/tui/bottom_pane/view_stack.py",
        ),
        python_tests=(
            "pycodex/tui/bottom_pane/tests/test_bottom_pane_view.py",
            "pycodex/tui/bottom_pane/tests/test_chat_composer.py",
            "pycodex/tui/bottom_pane/tests/test_command_popup.py",
            "pycodex/tui/bottom_pane/tests/test_list_selection_view.py",
            "pycodex/tui/bottom_pane/tests/test_terminal_controller.py",
            "pycodex/tui/bottom_pane/tests/test_terminal_projection.py",
            "pycodex/tui/bottom_pane/tests/test_view_stack.py",
        ),
        notes=(
            "Package-level owner for the bottom_pane Rust module. Individual "
            "Python files may still have narrower file-level entries, but all "
            "bottom-pane UI behavior must stay inside this module owner, "
            "including footer formatting and runtime-bound passive-footer text "
            "callbacks."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/chatwidget",
        rust_module="codex-tui::chatwidget",
        rust_source="codex/codex-rs/tui/src/chatwidget.rs",
        implementation_files=(
            "pycodex/tui/chatwidget/model_popups.py",
            "pycodex/tui/chatwidget/rendering.py",
            "pycodex/tui/chatwidget/slash_dispatch.py",
            "pycodex/tui/chatwidget/status_surfaces.py",
        ),
        python_tests=(
            "pycodex/tui/chatwidget/tests/test_model_popups.py",
            "pycodex/tui/chatwidget/tests/test_slash_dispatch.py",
            "pycodex/tui/chatwidget/tests/test_status_surfaces.py",
        ),
        notes=(
            "Package-level owner for chatwidget behavior used by the terminal "
            "product path, including model/reasoning view creation and status "
            "surfaces. Protocol-facing status callbacks should live here so "
            "terminal_runtime can bind methods instead of local policy lambdas."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/status/card.py",
        rust_module="codex-tui::status::card",
        rust_source="codex/codex-rs/tui/src/status/card.rs",
        implementation_files=("pycodex/tui/status/card.py",),
        python_tests=("pycodex/tui/status/tests/test_card.py",),
        notes=(
            "Owns terminal /status card data shaping, history-cell rendering, "
            "and runtime-bound callback construction for local command dispatch."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/chatwidget/turn_runtime.py",
        rust_module="codex-tui::chatwidget::turn_runtime",
        rust_source="codex/codex-rs/tui/src/chatwidget/turn_runtime.rs",
        implementation_files=("pycodex/tui/chatwidget/turn_runtime.py",),
        python_tests=("pycodex/tui/chatwidget/tests/test_turn_runtime.py",),
        notes=(
            "Owns terminal turn-start/submission lifecycle, typed callback "
            "contracts, and the runtime-bound turn submission runner consumed "
            "by terminal_runtime."
        ),
    ),
    TuiModuleOwner(
        python_owner="pycodex/tui/app/history_ui.py",
        rust_module="codex-tui::app::history_ui",
        rust_source="codex/codex-rs/tui/src/app/history_ui.rs",
        implementation_files=("pycodex/tui/app/history_ui.py",),
        python_tests=("pycodex/tui/app/tests/test_history_ui.py",),
        notes=(
            "Owns /clear state reset ordering, terminal clear/header repaint "
            "callbacks, session-header history text, and runtime-bound "
            "session-header writer callback packaging for the terminal path."
        ),
    ),
)


CRITICAL_TERMINAL_TUI_MODULES: frozenset[str] = frozenset(
    {
        "pycodex/tui/app_event.py",
        "pycodex/tui/app_event_sender.py",
        "pycodex/tui/app/runtime.py",
        "pycodex/tui/tui/event_stream.py",
        "pycodex/tui/ratatui_bridge/buffer.py",
        "pycodex/tui/ratatui_bridge/backend.py",
        "pycodex/tui/tui/terminal_runtime.py",
        "pycodex/tui/bottom_pane/chat_composer/__init__.py",
        "pycodex/tui/bottom_pane/chat_composer/attachment_state.py",
        "pycodex/tui/bottom_pane/chat_composer/draft_state.py",
        "pycodex/tui/bottom_pane/textarea/__init__.py",
        "pycodex/tui/bottom_pane/chat_composer_history.py",
        "pycodex/tui/bottom_pane/chat_composer/footer_state.py",
        "pycodex/tui/bottom_pane/chat_composer/history_search.py",
        "pycodex/tui/bottom_pane/chat_composer/popup_state.py",
        "pycodex/tui/bottom_pane/chat_composer/slash_input.py",
        "pycodex/tui/bottom_pane/command_popup.py",
        "pycodex/tui/bottom_pane/slash_commands.py",
        "pycodex/tui/chatwidget/slash_dispatch.py",
        "pycodex/tui/chatwidget/model_popups.py",
        "pycodex/tui/chatwidget/rendering.py",
        "pycodex/tui/chatwidget/turn_runtime.py",
        "pycodex/tui/bottom_pane/list_selection_view.py",
        "pycodex/tui/bottom_pane/bottom_pane_view.py",
        "pycodex/tui/bottom_pane/view_stack.py",
        "pycodex/tui/bottom_pane/selection_popup_common.py",
        "pycodex/tui/bottom_pane/terminal_action.py",
        "pycodex/tui/bottom_pane/terminal_footprint.py",
        "pycodex/tui/chatwidget/status_surfaces.py",
        "pycodex/tui/status/card.py",
        "pycodex/tui/app/history_ui.py",
        "pycodex/tui/bottom_pane/terminal_projection.py",
        "pycodex/tui/bottom_pane/terminal_controller.py",
        "pycodex/tui/app/resize_reflow.py",
        "pycodex/tui/custom_terminal.py",
        "pycodex/tui/insert_history.py",
        "pycodex/tui/history_cell/messages.py",
        "pycodex/tui/history_cell/session.py",
        "pycodex/tui/chatwidget/protocol_requests.py",
        "pycodex/tui/chatwidget/tool_requests.py",
        "pycodex/tui/bottom_pane/approval_overlay.py",
        "pycodex/tui/bottom_pane/request_user_input/__init__.py",
        "pycodex/tui/bottom_pane/mcp_server_elicitation.py",
        "pycodex/tui/app/app_server_requests.py",
        "pycodex/tui/app/pending_interactive_replay.py",
        "pycodex/tui/history_cell/request_user_input.py",
        "pycodex/tui/bottom_pane/app_link_view.py",
        "pycodex/tui/app/app_server_events.py",
        "pycodex/tui/app/thread_routing.py",
        "pycodex/tui/app/thread_events.py",
        "pycodex/tui/app/event_dispatch.py",
        "pycodex/tui/bottom_pane/pending_thread_approvals.py",
        "pycodex/tui/app/side.py",
        "pycodex/tui/app/platform_actions.py",
        "pycodex/tui/chatwidget/interaction.py",
    }
)


def repository_relative_path(path: str) -> Path:
    """Return a repository-relative path object without touching the filesystem."""

    return Path(path.replace("\\", "/"))


__all__ = [
    "AdapterResponsibility",
    "CRITICAL_TERMINAL_TUI_MODULES",
    "RUST_CODEX_BASELINE_COMMIT",
    "TUI_ALIGNMENT_ENTRIES",
    "TUI_MODULE_OWNERS",
    "TuiAlignmentEntry",
    "TuiModuleOwner",
    "repository_relative_path",
]
