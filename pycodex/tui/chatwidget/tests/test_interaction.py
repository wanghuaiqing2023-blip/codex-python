from __future__ import annotations

from types import SimpleNamespace

from pycodex.tui.chatwidget.interaction import (
    AppCommand,
    CancellationEvent,
    ExternalEditorState,
    FrameRequester,
    KeyBinding,
    KeyEvent,
    apply_external_edit,
    arm_quit_shortcut,
    attach_image,
    handle_key_event,
    can_run_ctrl_l_clear_now,
    copy_last_agent_markdown_with,
    handle_paste,
    handle_paste_burst_tick,
    on_ctrl_c,
    on_ctrl_d,
    set_external_editor_state,
    show_selection_view,
)


class Tx:
    def __init__(self) -> None:
        self.events = []

    def send(self, event) -> None:
        self.events.append(event)


class Pane:
    def __init__(self) -> None:
        self.events = []
        self.task_running = False
        self.modal_clear = True
        self.ctrl_c_result = CancellationEvent.IGNORED
        self.empty = True
        self.flush_due = False
        self.in_burst = False
        self.active_view = False

    def __getattr__(self, name):
        def recorder(*args):
            self.events.append((name, *args))

        return recorder

    def no_modal_or_popup_active(self):
        return self.modal_clear

    def is_task_running(self):
        return self.task_running

    def on_ctrl_c(self):
        return self.ctrl_c_result

    def composer_is_empty(self):
        return self.empty

    def flush_paste_burst_if_due(self):
        return self.flush_due

    def is_in_paste_burst(self):
        return self.in_burst

    def recommended_paste_flush_delay(self):
        return "delay"

    def has_active_view(self):
        return self.active_view


class Realtime:
    def __init__(self, live=False) -> None:
        self.live = live

    def is_live(self):
        return self.live


class Transcript:
    def __init__(self) -> None:
        self.last_agent_markdown = None
        self.copy_history_evicted_by_rollback = False
        self.truncated_to = None

    def truncate_copy_history_to_user_turn_count(self, count):
        self.truncated_to = count


class Goal:
    def __init__(self, active=True) -> None:
        self.active = active

    def is_active(self):
        return self.active


class Widget:
    def __init__(self) -> None:
        self.bottom_pane = Pane()
        self.transcript = Transcript()
        self.realtime_conversation = Realtime()
        self.review = SimpleNamespace(is_review_mode=False)
        self.turn_lifecycle = SimpleNamespace(agent_turn_running=False)
        self.current_goal_status = None
        self.thread_id = "thread"
        self.app_event_tx = Tx()
        self.events = []
        self.history = []
        self.ops = []
        self.quit_shortcut_key = None
        self.quit_shortcut_expires_at = None
        self.clipboard_lease = None
        self.thread_rename_block_message = None
        self.copy_last_response_binding = KeyBinding("ctrl-y")
        self.chat_keymap = SimpleNamespace(
            edit_queued_message=KeyBinding("ctrl-e"),
            interrupt_turn=KeyBinding("esc"),
        )
        self.input_queue = SimpleNamespace(
            pending_steers=[],
            submit_pending_steers_after_interrupt=False,
        )
        self.queued = []
        self.reasoning_shortcut_handled = False
        self.plugins_popup_handled = False
        self.plan_nudge = False
        self.collaboration_enabled = False

    def __getattr__(self, name):
        def recorder(*args):
            self.events.append((name, *args))

        return recorder

    def add_to_history(self, item):
        self.history.append(item)

    def request_redraw(self):
        self.events.append(("request_redraw",))

    def current_model_supports_images(self):
        return self.supports_images

    def image_inputs_not_supported_message(self):
        return "no image support"

    def submit_op(self, op):
        self.ops.append(op)
        return True

    def handle_reasoning_shortcut(self, key_event):
        return self.reasoning_shortcut_handled

    def has_queued_follow_up_messages(self):
        return bool(self.queued)

    def pop_latest_queued_user_message(self):
        return self.queued.pop() if self.queued else None

    def should_handle_vim_insert_escape(self, key_event):
        return False

    def should_show_plan_mode_nudge(self):
        return self.plan_nudge

    def handle_plugins_popup_key_event(self, key_event):
        return self.plugins_popup_handled

    def collaboration_modes_enabled(self):
        return self.collaboration_enabled


def test_attach_image_warns_when_model_lacks_support_otherwise_attaches() -> None:
    widget = Widget()
    widget.supports_images = False

    attach_image(widget, "/tmp/a.png")

    assert widget.history == [{"kind": "warning", "message": "no image support"}]
    assert ("request_redraw",) in widget.events

    widget = Widget()
    widget.supports_images = True
    attach_image(widget, "/tmp/a.png")
    assert ("attach_image", "/tmp/a.png") in widget.bottom_pane.events
    assert ("request_redraw",) in widget.events


def test_copy_last_agent_markdown_success_error_empty_and_evicted_paths() -> None:
    widget = Widget()
    widget.transcript.last_agent_markdown = "hello"

    copy_last_agent_markdown_with(widget, lambda text: f"lease:{text}")

    assert widget.clipboard_lease == "lease:hello"
    assert widget.history[-1]["message"] == "Copied last message to clipboard"

    widget = Widget()
    widget.transcript.last_agent_markdown = "hello"
    copy_last_agent_markdown_with(widget, lambda text: (_ for _ in ()).throw(RuntimeError("nope")))
    assert widget.history[-1]["message"] == "Copy failed: nope"

    widget = Widget()
    copy_last_agent_markdown_with(widget, lambda text: None)
    assert widget.history[-1]["message"] == "No agent response to copy"

    widget = Widget()
    widget.transcript.copy_history_evicted_by_rollback = True
    copy_last_agent_markdown_with(widget, lambda text: None)
    assert "Cannot copy that response after rewinding" in widget.history[-1]["message"]


def test_ctrl_l_clear_blocks_while_task_running() -> None:
    widget = Widget()
    assert can_run_ctrl_l_clear_now(widget) is True

    widget.bottom_pane.task_running = True
    assert can_run_ctrl_l_clear_now(widget) is False
    assert widget.history[-1]["message"] == "Ctrl+L is disabled while a task is in progress."


def test_paste_and_selection_helpers_refresh_nudge_and_redraw() -> None:
    widget = Widget()

    apply_external_edit(widget, "new")
    handle_paste(widget, "paste")
    show_selection_view(widget, {"items": []})
    set_external_editor_state(widget, ExternalEditorState.OPEN)

    assert ("apply_external_edit", "new") in widget.bottom_pane.events
    assert ("handle_paste", "paste") in widget.bottom_pane.events
    assert ("show_selection_view", {"items": []}) in widget.bottom_pane.events
    assert widget.external_editor_state == ExternalEditorState.OPEN
    assert ("refresh_plan_mode_nudge",) in widget.events


def test_paste_burst_tick_flushes_or_schedules_or_allows_render() -> None:
    widget = Widget()
    requester = FrameRequester([])

    widget.bottom_pane.flush_due = True
    assert handle_paste_burst_tick(widget, requester) is True
    assert ("request_redraw",) in widget.events

    widget = Widget()
    requester = FrameRequester([])
    widget.bottom_pane.in_burst = True
    assert handle_paste_burst_tick(widget, requester) is True
    assert requester.scheduled_delays == ["delay"]

    widget = Widget()
    assert handle_paste_burst_tick(widget, FrameRequester([])) is False


def test_ctrl_c_stops_realtime_interrupts_or_quits_without_double_press() -> None:
    # Rust source contract:
    # - codex-tui::bottom_pane::DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED is false.
    # - chatwidget::interaction::on_ctrl_c stops realtime first, interrupts
    #   cancellable work immediately, and quits immediately when idle.
    widget = Widget()
    widget.realtime_conversation = Realtime(live=True)
    on_ctrl_c(widget)
    assert ("stop_realtime_conversation_from_ui",) in widget.events

    widget = Widget()
    widget.bottom_pane.task_running = True
    widget.turn_lifecycle.agent_turn_running = True
    widget.current_goal_status = Goal(active=True)
    on_ctrl_c(widget)
    assert widget.quit_shortcut_key is None
    assert widget.ops == [AppCommand.interrupt()]
    assert widget.app_event_tx.events == [{"kind": "SetThreadGoalStatus", "thread_id": "thread", "status": "Paused"}]

    widget = Widget()
    on_ctrl_c(widget)
    assert ("request_quit_without_confirmation",) in widget.events


def test_ctrl_c_bottom_pane_handled_does_not_arm_hint_when_double_press_disabled() -> None:
    # Rust source contract:
    # - BottomPane may clear a draft or dismiss a modal and report Handled.
    # - With DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED=false, ChatWidget does not arm
    #   the quit shortcut after a handled bottom-pane Ctrl+C.
    widget = Widget()
    widget.bottom_pane.ctrl_c_result = CancellationEvent.HANDLED
    widget.bottom_pane.modal_clear = False
    widget.quit_shortcut_key = KeyBinding("ctrl-c")
    widget.quit_shortcut_expires_at = 1

    on_ctrl_c(widget)

    assert widget.quit_shortcut_key == KeyBinding("ctrl-c")
    assert ("clear_quit_shortcut_hint",) not in widget.bottom_pane.events

    widget = Widget()
    widget.bottom_pane.ctrl_c_result = CancellationEvent.HANDLED
    on_ctrl_c(widget)
    assert widget.quit_shortcut_key is None
    assert ("request_quit_without_confirmation",) not in widget.events


def test_ctrl_d_quits_immediately_only_when_composer_empty_and_modal_clear() -> None:
    # Rust source contract:
    # - With DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED=false, Ctrl-D quits immediately
    #   only when the composer is empty and no modal/popup is active.
    widget = Widget()
    widget.bottom_pane.empty = False

    assert on_ctrl_d(widget) is False

    widget = Widget()
    assert on_ctrl_d(widget) is True
    assert ("request_quit_without_confirmation",) in widget.events


def test_handle_key_event_routes_active_view_then_maybe_drains_queue() -> None:
    widget = Widget()
    widget.bottom_pane.active_view = True

    handle_key_event(widget, KeyEvent("char", "x"))

    assert ("handle_key_event", KeyEvent("char", "x")) in widget.bottom_pane.events
    assert ("maybe_send_next_queued_input",) in widget.events


def test_handle_key_event_copy_paste_queued_edit_interrupt_and_nudge_paths() -> None:
    widget = Widget()
    handle_key_event(widget, KeyEvent("char", "y", ("control",)))
    assert ("copy_last_agent_markdown",) in widget.events

    widget = Widget()
    handle_key_event(widget, KeyEvent("char", "v", ("control",)), paste_image_fn=lambda: ("/tmp/p.png", object()))
    assert ("attach_image", "/tmp/p.png") in widget.bottom_pane.events

    widget = Widget()
    widget.queued = ["queued message"]
    handle_key_event(widget, KeyEvent("char", "e", ("control",)))
    assert ("restore_user_message_to_composer", "queued message") in widget.events
    assert ("request_redraw",) in widget.events

    widget = Widget()
    widget.bottom_pane.task_running = True
    widget.input_queue.pending_steers = ["steer"]
    handle_key_event(widget, KeyEvent("esc"))
    assert widget.input_queue.submit_pending_steers_after_interrupt is True
    assert widget.ops == [AppCommand.interrupt()]

    widget = Widget()
    widget.plan_nudge = True
    handle_key_event(widget, KeyEvent("esc"))
    assert ("dismiss_plan_mode_nudge",) in widget.events


def test_handle_key_event_backtab_cycles_collaboration_otherwise_composer_handles() -> None:
    widget = Widget()
    widget.collaboration_enabled = True

    handle_key_event(widget, KeyEvent("backtab"))

    assert ("cycle_collaboration_mode",) in widget.events
    assert ("refresh_plan_mode_nudge",) in widget.events

    widget = Widget()
    handle_key_event(widget, KeyEvent("enter"))
    assert ("handle_key_event", KeyEvent("enter")) in widget.bottom_pane.events
    assert ("handle_composer_input_result", None, False) in widget.events
"""Rust source: codex/codex-rs/tui/src/chatwidget/interaction.rs."""
