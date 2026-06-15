from pathlib import Path

from pycodex.tui.chatwidget.notifications import (
    Notification,
    NotificationCoalescer,
    Notifications,
    ToolRequestUserInputQuestion,
)


def test_agent_turn_preview_normalizes_whitespace_and_empty_falls_back() -> None:
    # Rust parity: codex-tui chatwidget::notifications::Notification::agent_turn_preview
    assert Notification.agent_turn_preview("  hello\n\nthere\tfriend  ") == "hello there friend"
    assert Notification.agent_turn_complete(" \n\t ").display() == "Agent turn complete"
    assert Notification.agent_turn_preview("a" * 250) == ("a" * 197) + "..."


def test_notification_display_strings_match_rust_variants() -> None:
    # Rust parity: codex-tui chatwidget::notifications::Notification::display
    assert (
        Notification.exec_approval_requested("x" * 40).display()
        == "Approval requested: " + ("x" * 27) + "..."
    )
    assert (
        Notification.edit_approval_requested(Path("C:/work"), [Path("C:/work/src/main.rs")]).display()
        == f"Codex wants to edit {Path('src/main.rs')}"
    )
    assert (
        Notification.edit_approval_requested(Path("/work"), ["relative.txt"]).display()
        == "Codex wants to edit relative.txt"
    )
    assert (
        Notification.edit_approval_requested(Path("/work"), ["a", "b"]).display()
        == "Codex wants to edit 2 files"
    )
    assert Notification.elicitation_requested("server").display() == "Approval requested by server"
    assert Notification.plan_mode_prompt("Pick one").display() == "Plan mode prompt: Pick one"


def test_allowed_for_enabled_and_custom_settings() -> None:
    # Rust parity: codex-tui chatwidget::notifications::Notification::allowed_for
    agent = Notification.agent_turn_complete("done")
    approval = Notification.exec_approval_requested("git status")
    plan = Notification.plan_mode_prompt("Review")

    assert agent.allowed_for(Notifications.enabled_setting(True))
    assert not agent.allowed_for(Notifications.enabled_setting(False))
    assert agent.allowed_for(Notifications.custom(["agent-turn-complete"]))
    assert approval.allowed_for(Notifications.custom(["approval-requested"]))
    assert plan.allowed_for(Notifications.custom(["plan-mode-prompt"]))
    assert not approval.allowed_for(Notifications.custom(["agent-turn-complete"]))


def test_coalescer_preserves_higher_priority_pending_notification() -> None:
    # Rust parity: codex-tui chatwidget::notifications::ChatWidget::notify
    coalescer = NotificationCoalescer()
    low = Notification.agent_turn_complete("done")
    high = Notification.exec_approval_requested("cargo test")

    assert coalescer.notify(high)
    assert not coalescer.notify(low)
    assert coalescer.maybe_post_pending_notification() == "Approval requested: cargo test"
    assert coalescer.maybe_post_pending_notification() is None


def test_coalescer_replaces_lower_priority_with_higher_priority() -> None:
    # Rust: existing priority is only preserved when it is greater than the incoming priority.
    coalescer = NotificationCoalescer()
    assert coalescer.notify(Notification.agent_turn_complete("done"))
    assert coalescer.notify(Notification.exec_approval_requested("cargo test"))
    assert coalescer.redraw_requests == 2
    assert coalescer.maybe_post_pending_notification() == "Approval requested: cargo test"


def test_coalescer_filters_disallowed_notifications_without_redraw() -> None:
    # Rust: ChatWidget::notify returns before mutating pending_notification or requesting redraw.
    coalescer = NotificationCoalescer(settings=Notifications.custom(["approval-requested"]))
    assert not coalescer.notify(Notification.agent_turn_complete("done"))
    assert coalescer.pending_notification is None
    assert coalescer.redraw_requests == 0


def test_coalescer_replaces_equal_or_lower_priority_and_requests_redraw() -> None:
    # Rust parity: codex-tui chatwidget::notifications::ChatWidget::notify
    coalescer = NotificationCoalescer()
    assert coalescer.notify(Notification.agent_turn_complete("first"))
    assert coalescer.notify(Notification.agent_turn_complete("second"))
    assert coalescer.redraw_requests == 2
    assert coalescer.maybe_post_pending_notification() == "second"


def test_user_input_request_summary_uses_header_then_question() -> None:
    # Rust parity: codex-tui chatwidget::notifications::Notification::user_input_request_summary
    assert (
        Notification.user_input_request_summary(
            [ToolRequestUserInputQuestion(header="  Header  ", question="Question")]
        )
        == "Header"
    )
    assert (
        Notification.user_input_request_summary(
            [{"header": " ", "question": "  What should Codex do next?  "}]
        )
        == "What should Codex do next?"
    )
    assert Notification.user_input_request_summary([{"header": " ", "question": " "}]) is None
    assert Notification.user_input_request_summary([]) is None
    assert (
        Notification.user_input_request_summary(
            [{"header": "x" * 40, "question": "ignored"}]
        )
        == ("x" * 27) + "..."
    )
