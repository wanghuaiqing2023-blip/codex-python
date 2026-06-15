"""Parity tests for ``codex-tui/src/app_event_sender.rs``."""

from pathlib import Path

from pycodex.tui.app_command import AppCommand
from pycodex.tui.app_event_sender import AppEvent, AppEventSender


def test_send_logs_only_non_codex_op_events_and_sends_to_target() -> None:
    # Rust: send logs inbound events except AppEvent::CodexOp and swallows send errors.
    sent: list[AppEvent] = []
    logged: list[AppEvent] = []
    sender = AppEventSender(sent, inbound_logger=logged.append)

    codex = AppEvent.codex_op(AppCommand.interrupt())
    submit = AppEvent.submit_thread_op("thread-1", AppCommand.compact())
    sender.send(codex)
    sender.send(submit)

    assert sent == [codex, submit]
    assert logged == [submit]


def test_send_swallows_send_errors_after_error_logging() -> None:
    # Rust: failed channel send is logged but not raised to caller.
    errors: list[Exception] = []

    def fail(_event: AppEvent) -> None:
        raise RuntimeError("closed")

    sender = AppEventSender(fail, error_logger=errors.append)
    sender.send(AppEvent.codex_op(AppCommand.interrupt()))

    assert len(errors) == 1
    assert str(errors[0]) == "closed"


def test_codex_op_helpers_send_expected_commands() -> None:
    # Rust: interrupt/compact/set_thread_name/review/list_skills/audio/user_input_answer wrap CodexOp.
    sent: list[AppEvent] = []
    sender = AppEventSender.new(sent)

    sender.interrupt()
    sender.compact()
    sender.set_thread_name("new name")
    sender.review("target")
    sender.list_skills(["/repo", Path("/other")], force_reload=True)
    sender.realtime_conversation_audio(b"frame")
    sender.user_input_answer("input-1", "answer")

    assert sent == [
        AppEvent.codex_op(AppCommand.interrupt()),
        AppEvent.codex_op(AppCommand.compact()),
        AppEvent.codex_op(AppCommand.set_thread_name("new name")),
        AppEvent.codex_op(AppCommand.review("target")),
        AppEvent.codex_op(AppCommand.list_skills(["/repo", Path("/other")], True)),
        AppEvent.codex_op(AppCommand.realtime_conversation_audio(b"frame")),
        AppEvent.codex_op(AppCommand.user_input_answer("input-1", "answer")),
    ]


def test_thread_op_helpers_submit_expected_commands() -> None:
    # Rust: approval/elicitation helpers send SubmitThreadOp with AppCommand payloads.
    sent: list[AppEvent] = []
    sender = AppEventSender.new(sent)

    sender.exec_approval("thread-1", "exec-1", "accept")
    sender.request_permissions_response("thread-1", "perm-1", "response")
    sender.patch_approval("thread-2", "patch-1", "cancel")
    sender.resolve_elicitation("thread-3", "server", "req", "accept", {"x": 1}, None)

    assert sent == [
        AppEvent.submit_thread_op("thread-1", AppCommand.exec_approval("exec-1", None, "accept")),
        AppEvent.submit_thread_op("thread-1", AppCommand.request_permissions_response("perm-1", "response")),
        AppEvent.submit_thread_op("thread-2", AppCommand.patch_approval("patch-1", "cancel")),
        AppEvent.submit_thread_op(
            "thread-3",
            AppCommand.resolve_elicitation("server", "req", "accept", {"x": 1}, None),
        ),
    ]


def test_sender_accepts_send_method_targets() -> None:
    # Rust sends through UnboundedSender::send; Python supports send-like targets.
    class Target:
        def __init__(self) -> None:
            self.events: list[AppEvent] = []

        def send(self, event: AppEvent) -> None:
            self.events.append(event)

    target = Target()
    sender = AppEventSender.new(target)
    sender.compact()
    assert target.events == [AppEvent.codex_op(AppCommand.compact())]


def test_sender_accepts_put_nowait_targets() -> None:
    # Rust source: AppEventSender wraps a channel sender; put_nowait is Python's queue analogue.
    class Target:
        def __init__(self) -> None:
            self.events: list[AppEvent] = []

        def put_nowait(self, event: AppEvent) -> None:
            self.events.append(event)

    target = Target()
    sender = AppEventSender.new(target)
    sender.set_thread_name("queued")
    assert target.events == [AppEvent.codex_op(AppCommand.set_thread_name("queued"))]
