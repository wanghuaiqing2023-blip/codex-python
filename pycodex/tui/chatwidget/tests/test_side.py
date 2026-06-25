"""Parity tests for codex-rs/tui/src/chatwidget/side.rs."""

from pycodex.tui.chatwidget.side import (
    SHELL_ESCAPE_POLICY_DISALLOW,
    SideConversationMixin,
    set_side_conversation_active,
    set_side_conversation_context_label,
    side_conversation_active,
    submit_user_message_as_plain_user_turn,
)


class FakeBottomPane:
    def __init__(self):
        self.placeholder_text = None
        self.side_active = None
        self.context_label = "unset"

    def set_placeholder_text(self, text):
        self.placeholder_text = text

    def set_side_conversation_active(self, active):
        self.side_active = active

    def set_side_conversation_context_label(self, label):
        self.context_label = label


class FakeWidget:
    def __init__(self):
        self.active_side_conversation = False
        self.side_placeholder_text = "Ask a side question"
        self.normal_placeholder_text = "Ask Codex"
        self.bottom_pane = FakeBottomPane()
        self.submissions = []

    def submit_user_message_with_shell_escape_policy(self, user_message, policy):
        self.submissions.append((user_message, policy))
        return {"message": user_message, "policy": policy}


class MixedWidget(SideConversationMixin, FakeWidget):
    pass


def test_submit_user_message_as_plain_user_turn_disallows_shell_escape_policy():
    widget = FakeWidget()

    result = submit_user_message_as_plain_user_turn(widget, "hello")

    assert result == {"message": "hello", "policy": SHELL_ESCAPE_POLICY_DISALLOW}
    assert widget.submissions == [("hello", SHELL_ESCAPE_POLICY_DISALLOW)]


def test_set_side_conversation_active_sets_side_placeholder_and_bottom_pane_flag():
    widget = FakeWidget()

    set_side_conversation_active(widget, True)

    assert widget.active_side_conversation is True
    assert widget.bottom_pane.placeholder_text == "Ask a side question"
    assert widget.bottom_pane.side_active is True


def test_set_side_conversation_inactive_restores_normal_placeholder():
    widget = FakeWidget()
    set_side_conversation_active(widget, True)

    set_side_conversation_active(widget, False)

    assert widget.active_side_conversation is False
    assert widget.bottom_pane.placeholder_text == "Ask Codex"
    assert widget.bottom_pane.side_active is False


def test_side_conversation_active_reads_widget_flag_with_false_default():
    widget = FakeWidget()

    assert side_conversation_active(widget) is False
    widget.active_side_conversation = True
    assert side_conversation_active(widget) is True
    assert side_conversation_active(object()) is False


def test_set_side_conversation_context_label_forwards_to_bottom_pane():
    widget = FakeWidget()

    set_side_conversation_context_label(widget, "editing docs")
    assert widget.bottom_pane.context_label == "editing docs"

    set_side_conversation_context_label(widget, None)
    assert widget.bottom_pane.context_label is None


def test_mixin_exposes_rust_impl_method_shape():
    widget = MixedWidget()

    widget.set_side_conversation_active(True)
    result = widget.submit_user_message_as_plain_user_turn("hi")
    widget.set_side_conversation_context_label("ctx")

    assert widget.side_conversation_active() is True
    assert result["policy"] == SHELL_ESCAPE_POLICY_DISALLOW
    assert widget.bottom_pane.context_label == "ctx"
