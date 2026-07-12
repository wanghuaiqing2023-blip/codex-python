from __future__ import annotations

"""Parity tests for Rust ``codex-tui::bottom_pane`` view-stack ownership.

Rust source: codex/codex-rs/tui/src/bottom_pane/mod.rs
Behavior contract: ``BottomPane::pop_active_view_with_completion`` pops an
accepted child and parent views marked ``dismiss_after_child_accept``; a
cancelled child only clears that marker on its parent.
"""

from dataclasses import dataclass
import os
from pathlib import Path

from pycodex.tui.bottom_pane.bottom_pane_view import ViewCompletion
from pycodex.tui.bottom_pane.approval_overlay import ApprovalOverlay, ApprovalRequest
from pycodex.tui.bottom_pane.chat_composer import TerminalCommandPopupState
from pycodex.tui.bottom_pane.list_selection_view import ListSelectionView, SelectionItem, SelectionViewParams
from pycodex.tui.bottom_pane.selection_popup_common import TerminalPopupLine
from pycodex.app_server_protocol.item import ToolRequestUserInputParams, ToolRequestUserInputQuestion
from pycodex.tui.app.app_server_requests import ResolvedAppServerRequest
from pycodex.tui.app_event_sender import AppEventSender
from pycodex.tui.bottom_pane.mcp_server_elicitation import McpServerElicitationFormRequest
from pycodex.tui.bottom_pane.view_stack import (
    BottomPaneViewStack,
    TerminalBottomPanePopupProjection,
    TerminalBottomPaneViewState,
    terminal_bottom_pane_active_view_input,
    terminal_bottom_pane_cursor_visible,
    terminal_bottom_pane_handle_composer_key,
    terminal_bottom_pane_popup_lines,
    terminal_bottom_pane_popup_projection,
    terminal_bottom_pane_popup_projection_for_size,
    terminal_bottom_pane_show_selection_view,
    terminal_bottom_pane_sync_command_popup,
)


@dataclass
class FakeView:
    complete: bool = False
    completion_value: ViewCompletion | None = None
    dismiss_after_child_accept_value: bool = False
    clear_calls: int = 0
    handled_keys: list[str] | None = None

    def is_complete(self) -> bool:
        return self.complete

    def completion(self):
        return self.completion_value

    def dismiss_after_child_accept(self) -> bool:
        return self.dismiss_after_child_accept_value

    def clear_dismiss_after_child_accept(self) -> None:
        self.dismiss_after_child_accept_value = False
        self.clear_calls += 1

    def terminal_lines(self, *, width: int):
        return [TerminalPopupLine(f"line:{width}")]

    def handle_key_event(self, key_event) -> None:
        if self.handled_keys is not None:
            self.handled_keys.append(str(key_event))


@dataclass
class FakeCommandPopupState:
    visible: bool = False
    calls: list[tuple[str, bool]] | None = None
    hide_calls: int = 0

    def terminal_lines(self, *, width: int):
        return [TerminalPopupLine(f"popup:{width}")]

    def sync_draft(self, draft: str, *, active_view_present: bool = False) -> bool:
        if self.calls is not None:
            self.calls.append((draft, active_view_present))
        self.visible = not active_view_present and draft.startswith("/")
        return self.visible

    def hide(self) -> None:
        self.hide_calls += 1
        self.visible = False


def test_view_stack_replaces_and_tracks_active_view() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns view_stack and active_view.
    stack = BottomPaneViewStack()
    first = FakeView()
    second = FakeView()

    stack.replace_with(first)
    stack.push(second)

    assert stack.views == [first, second]
    assert stack.active_view() is second


def test_bottom_pane_user_input_requests_queue_fifo_and_external_resolution_advances() -> None:
    # Fixed Rust commit 1c7832f:
    # bottom_pane::BottomPane::push_user_input_request offers a second request
    # to RequestUserInputOverlay, which owns FIFO queueing and item-id dismissal.
    state = TerminalBottomPaneViewState.new()
    sender = AppEventSender([])
    first = ToolRequestUserInputParams(
        "thread",
        "turn",
        "item-1",
        (ToolRequestUserInputQuestion("q1", "One", "First?"),),
    )
    second = ToolRequestUserInputParams(
        "thread",
        "turn",
        "item-2",
        (ToolRequestUserInputQuestion("q2", "Two", "Second?"),),
    )

    from pycodex.tui.bottom_pane.request_user_input import RequestUserInputOverlay

    view = state.show_view(RequestUserInputOverlay.new(first, sender))
    queued_view = state.show_view(RequestUserInputOverlay.new(second, sender))

    assert queued_view is view
    assert len(state.views) == 1
    assert [request.item_id for request in view.queue] == ["item-2"]
    assert state.dismiss_app_server_request(ResolvedAppServerRequest.UserInput("item-1"))
    assert view.request.item_id == "item-2"
    assert len(state.views) == 1


def test_bottom_pane_mcp_form_requests_queue_fifo_and_external_resolution_advances() -> None:
    # Fixed Rust commit 1c7832f:
    # BottomPaneView::try_consume_mcp_server_elicitation_request returns None
    # when the active MCP overlay consumes the request.
    state = TerminalBottomPaneViewState.new()
    sender = AppEventSender([])
    first = McpServerElicitationFormRequest.from_parts(
        thread_id="thread",
        server_name="server",
        request_id="mcp-1",
        message="First",
        schema={"type": "object", "properties": {}},
    )
    second = McpServerElicitationFormRequest.from_parts(
        thread_id="thread",
        server_name="server",
        request_id="mcp-2",
        message="Second",
        schema={"type": "object", "properties": {}},
    )
    assert first is not None and second is not None

    from pycodex.tui.bottom_pane.mcp_server_elicitation import McpServerElicitationOverlay

    view = state.show_view(McpServerElicitationOverlay.new(first, sender))
    queued_view = state.show_view(McpServerElicitationOverlay.new(second, sender))

    assert queued_view is view
    assert len(state.views) == 1
    assert [request.request_id for request in view.pending_requests] == ["mcp-2"]
    assert state.dismiss_app_server_request(
        ResolvedAppServerRequest.McpElicitation("server", "mcp-1")
    )
    assert view.request.request_id == "mcp-2"
    assert len(state.views) == 1


def test_view_stack_projects_active_view_terminal_lines() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns active view routing;
    # concrete views own their terminal row projection.
    stack = BottomPaneViewStack()

    assert stack.terminal_lines(width=80) == []

    stack.replace_with(FakeView())

    assert stack.terminal_lines(width=80) == [TerminalPopupLine("line:80")]


def test_bottom_pane_popup_lines_prioritize_active_view_over_command_popup() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns active view priority
    # over composer popups. command_popup and concrete views own row rendering.
    stack = BottomPaneViewStack()
    hidden_popup = FakeCommandPopupState(visible=False)
    visible_popup = FakeCommandPopupState(visible=True)

    assert terminal_bottom_pane_popup_lines(stack, hidden_popup, width=80) == []
    assert terminal_bottom_pane_popup_lines(stack, visible_popup, width=80) == [TerminalPopupLine("popup:80")]

    stack.replace_with(FakeView())

    assert terminal_bottom_pane_popup_lines(stack, visible_popup, width=80) == [TerminalPopupLine("line:80")]


def test_bottom_pane_popup_projection_reports_active_view_source() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns the precedence
    # between active views and composer popups. The terminal footprint logic
    # consumes this projection instead of duplicating active-view checks.
    stack = BottomPaneViewStack()
    visible_popup = FakeCommandPopupState(visible=True)

    command_projection = terminal_bottom_pane_popup_projection(stack, visible_popup, width=80)
    assert command_projection == TerminalBottomPanePopupProjection(
        (TerminalPopupLine("popup:80"),),
        is_active_view=False,
    )
    assert command_projection.height == 1

    stack.replace_with(FakeView())

    view_projection = terminal_bottom_pane_popup_projection(stack, visible_popup, width=80)
    assert view_projection == TerminalBottomPanePopupProjection(
        (TerminalPopupLine("line:80"),),
        is_active_view=True,
    )
    assert view_projection.height == 1


def test_bottom_pane_popup_projection_for_size_owns_terminal_width_mapping() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns bottom-pane popup
    # layout. Terminal adapters provide observed terminal geometry instead of
    # duplicating the width expression for command popup / active view rows.
    stack = BottomPaneViewStack()
    visible_popup = FakeCommandPopupState(visible=True)

    assert terminal_bottom_pane_popup_projection_for_size(
        stack,
        visible_popup,
        os.terminal_size((12, 5)),
    ) == TerminalBottomPanePopupProjection((TerminalPopupLine("popup:11"),), is_active_view=False)

    assert terminal_bottom_pane_popup_projection_for_size(
        stack,
        visible_popup,
        os.terminal_size((0, 5)),
    ) == TerminalBottomPanePopupProjection((TerminalPopupLine("popup:1"),), is_active_view=False)

    stack.replace_with(FakeView())

    assert terminal_bottom_pane_popup_projection_for_size(
        stack,
        visible_popup,
        os.terminal_size((12, 5)),
    ) == TerminalBottomPanePopupProjection((TerminalPopupLine("line:11"),), is_active_view=True)


def test_bottom_pane_sync_command_popup_suppresses_popup_for_active_view() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns active view priority
    # over composer popups; chat_composer::sync_popups owns draft visibility.
    stack = BottomPaneViewStack()
    popup = FakeCommandPopupState(calls=[])

    assert terminal_bottom_pane_sync_command_popup(stack, popup, "/m") is True
    assert popup.visible is True
    assert popup.calls == [("/m", False)]

    stack.replace_with(FakeView())

    assert terminal_bottom_pane_sync_command_popup(stack, popup, "/m") is False
    assert popup.visible is False
    assert popup.calls == [("/m", False), ("/m", True)]


def test_bottom_pane_cursor_visible_hides_primary_cursor_for_active_view() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane gives active
    # BottomPaneView instances priority over the primary chat composer cursor;
    # custom_terminal applies the resulting frame cursor visibility.
    stack = BottomPaneViewStack()
    calls = 0

    def composer_cursor_visible() -> bool:
        nonlocal calls
        calls += 1
        return True

    assert terminal_bottom_pane_cursor_visible(stack, composer_cursor_visible) is True
    assert calls == 1

    stack.replace_with(FakeView())

    assert terminal_bottom_pane_cursor_visible(stack, composer_cursor_visible) is False
    assert calls == 1


def test_bottom_pane_show_selection_view_replaces_stack_and_hides_command_popup() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns active-view stack
    # replacement. Opening an active view suppresses composer command popups
    # before the terminal adapter renders the next frame.
    events = ["stale"]
    stack = BottomPaneViewStack()
    popup = FakeCommandPopupState(visible=True)

    terminal_bottom_pane_show_selection_view(
        stack,
        popup,
        SelectionViewParams(items=[SelectionItem(name="model")]),
        events,
    )

    assert events == []
    assert popup.visible is False
    assert popup.hide_calls == 1
    assert stack.active_view() is not None
    assert stack.active_view().selected_index() == 0


def test_view_stack_handles_active_selection_key_and_completion_pop() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane routes active view keys
    # and applies completion popping after the view handles the key.
    events = []
    stack = BottomPaneViewStack()
    stack.replace_with_selection_view(
        SelectionViewParams(
            items=[
                SelectionItem(name="first"),
                SelectionItem(name="second", dismiss_on_select=True),
            ],
        ),
        events,
    )

    assert stack.active_view().selected_index() == 0
    assert stack.handle_active_key("down", selection_events=events) is True
    assert stack.active_view().selected_index() == 1

    assert stack.handle_active_key("enter", selection_events=events) is True

    assert stack.active_view() is None


def test_view_stack_routes_active_key_through_bottom_pane_view_trait() -> None:
    # Rust owner: bottom_pane::BottomPane routes active-view input through the
    # BottomPaneView trait, not through list-selection-specific helpers.
    events = []
    view = FakeView(handled_keys=[])
    stack = BottomPaneViewStack()
    stack.replace_with(view)

    assert stack.handle_active_key("down", selection_events=events) is True

    assert view.handled_keys == ["down"]


def test_bottom_pane_active_view_input_has_priority_over_composer() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane gives active views first
    # chance at terminal input before composer/slash handling.
    events = []
    stack = BottomPaneViewStack()

    inactive = terminal_bottom_pane_active_view_input(
        stack,
        "down",
        "down",
        "draft",
        selection_events=events,
    )
    assert inactive.active is False
    assert inactive.draft is None

    stack.replace_with_selection_view(
        SelectionViewParams(
            items=[
                SelectionItem(name="first"),
                SelectionItem(name="second"),
            ],
        ),
        events,
    )

    moved = terminal_bottom_pane_active_view_input(
        stack,
        "down",
        "down",
        "draft",
        selection_events=events,
    )
    assert moved.active is True
    assert moved.draft == "draft"
    assert stack.active_view().selected_index() == 1

    text = terminal_bottom_pane_active_view_input(
        stack,
        "",
        "text",
        "draft",
        selection_events=events,
    )
    assert text.active is True
    assert text.draft == "draft"

    eof = terminal_bottom_pane_active_view_input(
        stack,
        "",
        "eof",
        "draft",
        selection_events=events,
    )
    assert eof.active is True
    assert eof.draft is None


def test_bottom_pane_handle_composer_key_routes_active_view_before_command_popup() -> None:
    # Rust owners: codex-tui::bottom_pane::BottomPane routes active views
    # before composer input, while chat_composer owns slash-popup key handling.
    # Terminal adapters consume this single shared precedence boundary.
    events = []
    stack = BottomPaneViewStack()
    popup = TerminalCommandPopupState.new()
    popup.sync_draft("/m")

    moved = terminal_bottom_pane_handle_composer_key(
        stack,
        popup,
        "/m",
        "down",
        selection_events=events,
    )

    assert moved.draft == "/m"
    assert popup.selected_item().command() == "memories"

    params = SelectionViewParams(
        title="Select Model",
        items=(
            SelectionItem(name="gpt-5.5"),
            SelectionItem(name="gpt-5.4"),
        ),
    )
    popup.sync_draft("/model")

    opened = terminal_bottom_pane_handle_composer_key(
        stack,
        popup,
        "/model",
        "enter",
        selection_events=events,
        open_command_view=lambda command: params if command == "model" else None,
    )

    assert opened.draft == ""
    assert popup.visible is False
    assert stack.active_view() is not None
    assert stack.active_view().selected_index() == 0

    active_moved = terminal_bottom_pane_handle_composer_key(
        stack,
        popup,
        "",
        "down",
        selection_events=events,
    )

    assert active_moved.draft == ""
    assert stack.active_view().selected_index() == 1


def test_terminal_bottom_pane_view_state_owns_draft_popup_and_view_stack_semantics() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns the combined
    # view-stack, command-popup suppression, and selection-event state. Terminal
    # adapters hold this state object instead of splitting those semantics.
    state = TerminalBottomPaneViewState.new()

    state.apply_draft("/m")

    assert state.draft == "/m"
    assert state.command_popup_visible is True
    assert state.command_popup.selected_item().command() == "model"

    assert state.handle_composer_key("/m", "down") == "/m"
    assert state.command_popup.selected_item().command() == "memories"

    params = SelectionViewParams(
        title="Select Model",
        items=(
            SelectionItem(name="gpt-5.5"),
            SelectionItem(name="gpt-5.4"),
        ),
    )

    state.show_selection_view(params)

    assert state.command_popup_visible is False
    assert state.active_view is not None
    assert state.views == [state.active_view]
    assert state.cursor_visible(lambda: True) is False
    projection = state.popup_projection_for_size(os.terminal_size((20, 10)))
    context = state.render_context_for_size(os.terminal_size((20, 10)), lambda: True)

    assert projection.is_active_view is True
    assert context.draft == "/m"
    assert context.popup_lines == projection.lines
    assert context.popup_height == projection.height
    assert context.popup_is_active_view is True
    assert context.cursor_visible is False

    assert state.handle_composer_key("", "down") == ""
    assert state.active_view.selected_index() == 1


def test_terminal_bottom_pane_view_state_recalls_local_history_with_up_down() -> None:
    # Fixed Rust owners: chat_composer records submissions and delegates
    # boundary navigation to chat_composer_history.
    state = TerminalBottomPaneViewState.new()
    state.record_submission("first")
    state.record_submission("second")
    state.record_submission("second")

    assert state.handle_composer_key("", "up") == "second"
    assert state.command_popup_visible is False
    assert state.handle_composer_key("second", "up") == "first"
    assert state.handle_composer_key("first", "up") == "first"
    assert state.handle_composer_key("first", "down") == "second"
    assert state.handle_composer_key("second", "down") == ""

    # A user-edited, non-recalled draft keeps Up available to normal textarea
    # movement instead of replacing the text with history.
    assert state.handle_composer_key("editing", "up") is None


def test_terminal_bottom_pane_history_does_not_steal_slash_popup_navigation() -> None:
    # Fixed Rust chat_composer precedence: an active command popup owns Up/Down
    # before shell-style history traversal.
    state = TerminalBottomPaneViewState.new()
    state.record_submission("older prompt")
    state.apply_draft("/m")

    assert state.command_popup_visible is True
    assert state.command_popup.selected_item().command() == "model"
    assert state.handle_composer_key("/m", "down") == "/m"
    assert state.command_popup.selected_item().command() == "memories"


def test_terminal_bottom_pane_history_combines_persistent_and_local_entries() -> None:
    # Fixed Rust chat_composer_history uses one offset space: persistent
    # entries first and current-session entries after them.
    state = TerminalBottomPaneViewState.new()
    lookups: list[tuple[int, int]] = []

    def lookup(log_id: int, offset: int) -> str:
        lookups.append((log_id, offset))
        return ("persistent older", "persistent newer")[offset]

    state.configure_history("thread", 7, 2, lookup)
    state.record_submission("local newest")

    assert state.handle_composer_key("", "up") == "local newest"
    assert state.handle_composer_key("local newest", "up") == "persistent newer"
    assert state.handle_composer_key("persistent newer", "up") == "persistent older"
    assert lookups == [(7, 1), (7, 0)]


def test_terminal_bottom_pane_view_state_projects_pending_thread_approvals() -> None:
    # Fixed Rust commit 1c7832f:
    # bottom_pane::pending_thread_approvals renders inactive-thread approval
    # labels and yields to active views and command popups.
    state = TerminalBottomPaneViewState.new()
    state.apply_pending_thread_approvals(["Robie [explorer]"])

    pending = state.popup_projection_for_size(os.terminal_size((40, 12)))

    assert [line.text for line in pending.lines] == [
        "  ! Approval needed in Robie [explorer]",
        "    /agent to switch threads",
    ]
    assert pending.is_active_view is False

    state.apply_draft("/m")
    command = state.popup_projection_for_size(os.terminal_size((40, 12)))

    assert command.lines
    assert command.lines[0].text.startswith("/")
    assert all("Approval needed" not in line.text for line in command.lines)


def test_terminal_bottom_pane_view_state_queues_approval_on_active_overlay() -> None:
    # Fixed Rust commit 1c7832f:
    # bottom_pane::BottomPane offers a new request to
    # BottomPaneView::try_consume_approval_request before pushing another view.
    state = TerminalBottomPaneViewState.new()
    first = ApprovalOverlay.new(
        ApprovalRequest.Exec("thread", "exec-1", ["echo", "one"], available_decisions=["Accept", "Cancel"])
    )
    second = ApprovalOverlay.new(
        ApprovalRequest.ApplyPatch("thread", "patch-1", Path("C:/repo"), {})
    )

    state.show_view(first)
    state.show_view(second)

    assert state.views == [first]
    assert first.current_request is not None
    assert first.current_request.id == "exec-1"
    assert [request.id for request in first.queue] == ["patch-1"]

    first.apply_selection(0)

    assert first.current_request is not None
    assert first.current_request.id == "patch-1"
    assert first.done is False


def test_terminal_bottom_pane_interrupt_calls_active_view_ctrl_c_contract() -> None:
    # Fixed Rust bottom_pane::BottomPane::on_ctrl_c gives the active view first
    # refusal and pops it only after the view reports handled + complete.
    state = TerminalBottomPaneViewState.new()
    overlay = ApprovalOverlay.new(
        ApprovalRequest.Exec(
            "thread",
            "exec-1",
            ["echo", "one"],
            available_decisions=["Accept", "Cancel"],
        )
    )
    state.show_view(overlay)

    result = state.handle_composer_key("", "interrupt")

    assert result == ""
    assert overlay.is_complete()
    assert state.active_view is None
    assert overlay.emitted_events[-1]["type"] == "ExecApproval"
    assert overlay.emitted_events[-1]["decision"] == "Cancel"

def test_terminal_bottom_pane_view_state_dismisses_current_and_queued_resolutions() -> None:
    # Fixed Rust commit 1c7832f:
    # ServerRequestResolved is correlated by app::app_server_requests and then
    # offered to BottomPaneView::dismiss_app_server_request.
    state = TerminalBottomPaneViewState.new()
    overlay = ApprovalOverlay.new(
        ApprovalRequest.Exec("thread", "exec-1", ["echo", "one"], available_decisions=["Accept", "Cancel"])
    )
    overlay.enqueue_request(
        ApprovalRequest.ApplyPatch("thread", "patch-drop", Path("C:/repo"), {})
    )
    overlay.enqueue_request(
        ApprovalRequest.Permissions("thread", "perm-next", {})
    )
    state.show_view(overlay)

    assert state.dismiss_app_server_request({"kind": "FileChangeApproval", "id": "patch-drop"}) is True
    assert [request.call_id for request in overlay.queue] == ["perm-next"]
    assert overlay.current_request is not None
    assert overlay.current_request.id == "exec-1"

    assert state.dismiss_app_server_request({"kind": "ExecApproval", "id": "exec-1"}) is True
    assert overlay.current_request is not None
    assert overlay.current_request.call_id == "perm-next"
    assert state.active_view is overlay

    assert state.dismiss_app_server_request({"kind": "ExecApproval", "id": "missing"}) is False
    assert state.active_view is overlay


def test_terminal_bottom_pane_view_state_pushes_child_selection_view_from_events() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns parent/child active
    # view stack transitions. Terminal controllers provide callbacks, but the
    # selection-event drain and child completion rules live at this owner
    # boundary.
    state = TerminalBottomPaneViewState.new()
    emitted: list[object] = []

    def handle_events(events: tuple[object, ...]) -> SelectionViewParams | None:
        emitted.extend(events)
        if "open_child" in events:
            return SelectionViewParams(
                header="Select Reasoning Level",
                items=[
                    SelectionItem(name="Medium", actions=["medium"], dismiss_on_select=True),
                    SelectionItem(name="High", actions=["high"], dismiss_on_select=True),
                ],
            )
        return None

    assert (
        state.handle_composer_key(
            "/model",
            "enter",
            open_command_view=lambda command: SelectionViewParams(
                header="Select Model and Effort",
                items=[
                    SelectionItem(
                        name="gpt-5.4",
                        actions=["open_child"],
                        dismiss_on_select=False,
                        dismiss_parent_on_child_accept=True,
                    )
                ],
            ),
        )
        == ""
    )
    assert state.handle_composer_key("", "enter", on_selection_events=handle_events) == ""
    assert state.active_view is not None
    child_lines = state.popup_projection_for_size(os.terminal_size((96, 18))).lines
    assert any("Medium" in line.text for line in child_lines)

    assert state.handle_composer_key("", "down", on_selection_events=handle_events) == ""
    assert state.handle_composer_key("", "enter", on_selection_events=handle_events) == ""

    assert state.active_view is None
    assert emitted == ["open_child", "high"]


def test_terminal_bottom_pane_view_state_normalizes_text_enter_for_active_selection_view() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane consumes Rust-like key
    # events after tui::event_stream normalization. CR/LF-shaped Enter must use
    # the same active BottomPaneView path as a symbolic Enter key.
    state = TerminalBottomPaneViewState.new()
    emitted: list[object] = []

    assert (
        state.handle_composer_key(
            "/model",
            "enter",
            open_command_view=lambda command: SelectionViewParams(
                header="Select Reasoning Level",
                items=[
                    SelectionItem(name="Low", actions=["low"], dismiss_on_select=True),
                    SelectionItem(name="Medium", actions=["medium"], dismiss_on_select=True),
                ],
            ),
        )
        == ""
    )
    assert state.handle_composer_key("", "down") == ""
    assert (
        state.handle_composer_key(
            "",
            "text",
            "\r",
            on_selection_events=lambda events: emitted.extend(events) or None,
        )
        == ""
    )

    assert state.active_view is None
    assert emitted == ["medium"]


def test_view_stack_drains_selection_events_and_pushes_child_view() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns active-view stack
    # child transitions; list_selection_view owns the event emission itself.
    events = []
    stack = BottomPaneViewStack()
    stack.replace_with_selection_view(
        SelectionViewParams(
            items=[
                SelectionItem(
                    name="parent",
                    actions=[lambda tx: tx.append("open-child")],
                )
            ],
        ),
        events,
    )

    def open_child(received):
        assert received == ("open-child",)
        return SelectionViewParams(items=[SelectionItem(name="child")])

    assert stack.handle_active_key(
        "enter",
        selection_events=events,
        on_selection_events=open_child,
    ) is True

    assert len(stack.views) == 2
    assert stack.active_view().selected_index() == 0
    assert "child" in stack.terminal_lines(width=80)[0].text


def test_accepted_child_dismisses_parent_marked_for_child_accept() -> None:
    # Rust owner: BottomPane::pop_active_view_with_completion handles
    # ViewCompletion::Accepted by popping parents that dismiss after child
    # acceptance.
    parent = FakeView(dismiss_after_child_accept_value=True)
    child = FakeView(complete=True, completion_value=ViewCompletion.ACCEPTED)
    stack = BottomPaneViewStack([parent, child])

    stack.pop_completed_views()

    assert stack.views == []


def test_list_selection_child_completion_uses_rust_view_completion_enum() -> None:
    # Rust owner: list_selection_view::accept sets ViewCompletion::Accepted,
    # and BottomPane::pop_active_view_with_completion handles the enum directly.
    parent = FakeView(dismiss_after_child_accept_value=True)
    events: list[object] = []
    child = ListSelectionView.new(
        SelectionViewParams(
            items=[
                SelectionItem(
                    name="child",
                    dismiss_on_select=True,
                )
            ],
        ),
        events,
    )
    stack = BottomPaneViewStack([parent, child])

    stack.handle_active_key("enter", selection_events=events)

    assert stack.views == []


def test_accepted_child_dismisses_parent_for_list_selection_view() -> None:
    # Rust owner: list-selection acceptance maps into the same accepted-child
    # bottom-pane stack rule through ViewCompletion::Accepted.
    parent = FakeView(dismiss_after_child_accept_value=True)
    child = FakeView(complete=True, completion_value=ViewCompletion.ACCEPTED)
    stack = BottomPaneViewStack([parent, child])

    stack.pop_completed_views()

    assert stack.views == []


def test_cancelled_child_keeps_parent_and_clears_child_accept_marker() -> None:
    # Rust owner: BottomPane::pop_active_view_with_completion handles
    # ViewCompletion::Cancelled by clearing the parent marker instead of
    # popping the parent view.
    parent = FakeView(dismiss_after_child_accept_value=True)
    child = FakeView(complete=True, completion_value=ViewCompletion.CANCELLED)
    stack = BottomPaneViewStack([parent, child])

    stack.pop_completed_views()

    assert stack.views == [parent]
    assert parent.dismiss_after_child_accept_value is False
    assert parent.clear_calls == 1
