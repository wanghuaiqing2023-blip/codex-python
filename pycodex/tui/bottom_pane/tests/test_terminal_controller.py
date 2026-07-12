import io
import os
from types import SimpleNamespace

from pycodex.tui.bottom_pane.chat_composer import terminal_composer_line_text
from pycodex.tui.bottom_pane.list_selection_view import SelectionItem, SelectionViewParams
from pycodex.tui.bottom_pane.terminal_footprint import TerminalBottomPaneFootprint
from pycodex.tui.bottom_pane.terminal_controller import (
    TerminalBottomPaneController,
)
from pycodex.tui.chatwidget.status_surfaces import TerminalLiveStatusSurface
from pycodex.tui.bottom_pane.bottom_pane_view import BottomPaneViewDefaults


class FlushTrackingStringIO(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


def test_terminal_controller_external_repaint_uses_live_viewport_lifecycle() -> None:
    # Rust owner: codex-tui::custom_terminal owns buffer invalidation around
    # external terminal writes; terminal controllers expose only the lifecycle
    # entrypoint used by tui/resize glue.
    writer = io.StringIO()
    controller = TerminalBottomPaneController(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((40, 12)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
    )
    controller.sync_draft("hello")

    assert controller.render(check_resize=False) is True
    writer.seek(0)
    writer.truncate(0)
    assert controller.render(check_resize=False) is True
    assert "\x1b[10;1H\u203a hello" not in writer.getvalue()

    calls: list[str] = []
    result = controller.run_external_repaint(lambda: calls.append("repaint") or "done")

    writer.seek(0)
    writer.truncate(0)
    assert controller.render(check_resize=False) is True
    assert result == "done"
    assert calls == ["repaint"]
    assert "\x1b[10;1H\u203a hello" in writer.getvalue()


def test_terminal_controller_projects_active_view_action_required_title_state() -> None:
    # Fixed Rust commit 1c7832f, bottom_pane::BottomPane owns the active-view
    # terminal_title_requires_action signal; the terminal controller forwards
    # it without interpreting approval semantics.
    class ActionView(BottomPaneViewDefaults):
        done = False

        def terminal_title_requires_action(self) -> bool:
            return not self.done

        def handle_key_event(self, _key_event: object) -> None:
            self.done = True

        def is_complete(self) -> bool:
            return self.done

    required: list[bool] = []
    controller = TerminalBottomPaneController(
        io.StringIO(),
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((40, 12)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
        set_terminal_title_requires_action=required.append,
    )

    controller.show_view(ActionView())
    controller.handle_active_view_input(SimpleNamespace(kind="key", text="enter"))

    assert required == [True, False]


def test_terminal_bottom_pane_controller_syncs_draft_and_terminal_callbacks() -> None:
    # Rust owner: codex-tui::bottom_pane owns composer/status/footer surface
    # rendering.  The terminal runner should supply environment callbacks while
    # this boundary syncs draft text and computes the live-pane footprint.
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    live = [TerminalLiveStatusSurface.inactive()]

    controller = TerminalBottomPaneController(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=lambda: live[0],
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
        footer_text=lambda: calls.append("footer") or "gpt-test high",
    )

    assert controller.history_bottom_row() == 8
    live[0] = TerminalLiveStatusSurface.active_status("\u2022 Working")
    assert controller.history_bottom_row() == 6
    assert controller.history_bottom_row(True) == 6

    controller.sync_draft("hello")
    assert controller.render(check_resize=True) is True
    assert calls[-3:] == ["footer", "resize", "size"]
    output = writer.getvalue()
    assert "\x1b[7;1H\u2022 Working" in output
    assert "\x1b[10;1H\u203a hello" in output
    assert "\x1b[12;1Hgpt-test high" in output

    assert controller.clear(check_resize=False) is True
    assert calls[-1] == "size"


def test_terminal_bottom_pane_controller_exposes_no_resize_callbacks_for_runtime_glue() -> None:
    # Rust owner: codex-tui::bottom_pane coordinates live-pane clear/render
    # callbacks while app::resize_reflow owns resize timing. terminal_runtime
    # should consume these callback boundaries instead of spelling out
    # check_resize=False lambdas for history/composer/resize collaborators.
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    controller = TerminalBottomPaneController(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
        footer_text=lambda: "gpt-test high",
    )
    controller.sync_draft("hello")

    assert controller.clear_without_resize_check() is True
    assert "resize" not in calls
    assert calls[-1] == "size"

    calls.clear()
    assert controller.render_without_resize_check() is True
    assert "resize" not in calls
    assert calls[0] == "size"


def test_terminal_bottom_pane_controller_applies_cursor_visibility_policy() -> None:
    # Rust owner: codex-tui::custom_terminal owns cursor hide/show lifecycle.
    # The Python terminal controller maps active turn/view state into that
    # frame-level cursor policy instead of moving the prompt cursor every tick.
    writer = FlushTrackingStringIO()
    visible = [True]
    controller = TerminalBottomPaneController(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((40, 12)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
        cursor_visible=lambda: visible[0],
    )
    controller.sync_draft("hi")

    visible[0] = False
    assert controller.render(check_resize=False) is True
    first_output = writer.getvalue()
    assert "\x1b[?25l" in first_output
    assert not first_output.endswith(f"\x1b[10;{len(terminal_composer_line_text('hi')) + 1}H")

    writer.seek(0)
    writer.truncate(0)
    assert controller.render(check_resize=False) is True
    second_output = writer.getvalue()
    assert "\x1b[?25l" not in second_output
    assert f"\x1b[10;{len(terminal_composer_line_text('hi')) + 1}H" not in second_output

    visible[0] = True
    writer.seek(0)
    writer.truncate(0)
    assert controller.render(check_resize=False) is True
    restored_output = writer.getvalue()
    assert "\x1b[?25h" in restored_output
    assert f"\x1b[10;{len(terminal_composer_line_text('hi')) + 1}H" in restored_output


def test_terminal_bottom_pane_controller_hides_cursor_for_active_selection_view() -> None:
    # Rust owner: codex-tui::bottom_pane::ListSelectionView implements
    # BottomPaneView without a text cursor.  Active selection views must use the
    # same frame cursor policy even if the idle composer policy would show one.
    writer = FlushTrackingStringIO()
    controller = TerminalBottomPaneController(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((96, 18)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
        open_command_view=lambda command: SelectionViewParams(
            header="Select Model and Effort",
            items=[SelectionItem(name="gpt-5.4", description="Strong model")],
        ),
        cursor_visible=lambda: True,
    )
    assert controller.handle_composer_key("/model", "enter") == ""

    assert controller.render(check_resize=False) is True
    output = writer.getvalue()
    assert "\x1b[?25l" in output
    assert "Select Model and Effort" in output


def test_terminal_bottom_pane_controller_reflows_history_when_popup_footprint_grows() -> None:
    # Rust owner: bottom_pane computes active view height, while
    # app::resize_reflow repairs the transcript viewport when that bottom-pane
    # footprint changes. Opening any selection popup must use that shared
    # footprint path rather than a /model-specific clear.
    writer = FlushTrackingStringIO()
    transitions: list[tuple[TerminalBottomPaneFootprint, TerminalBottomPaneFootprint]] = []
    controller = TerminalBottomPaneController(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((96, 18)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
        open_command_view=lambda command: SelectionViewParams(
            header="Select Model and Effort",
            items=[
                SelectionItem(name="gpt-5.5", description="Frontier model", is_current=True),
                SelectionItem(name="gpt-5.4", description="Strong model"),
            ],
        ),
        repaint_footprint=lambda previous, current: transitions.append((previous, current)),
    )

    controller.render(check_resize=False)
    assert controller.handle_composer_key("/model", "enter") == ""
    controller.render(check_resize=False)

    assert transitions
    previous, current = transitions[-1]
    assert previous.popup_height == 0
    assert current.popup_height > 0
