from __future__ import annotations

from collections import deque
from types import SimpleNamespace

from pycodex.tui.app_command import AppCommand as CrateAppCommand
from pycodex.tui.chatwidget.input_submission import (
    AppCommand,
    LocalImageAttachment,
    MentionBinding,
    QueueDrain,
    ShellEscapePolicy,
    UserMessage,
    UserMessageHistoryRecord,
    submit_queued_shell_prompt,
    submit_shell_command,
    submit_user_message_with_history_record,
    submit_user_message_with_shell_escape_policy,
    user_message_from_submission,
)
from pycodex.tui.chatwidget.skills import AppInfo, SkillMetadata


class Tx:
    def __init__(self) -> None:
        self.events = []

    def send(self, event) -> None:
        self.events.append(event)


class Pane:
    def __init__(self) -> None:
        self.images = [LocalImageAttachment("/tmp/a.png")]
        self.bindings = [MentionBinding("docs", "skill:///skills/docs/SKILL.md")]
        self.restored = None
        self._skills = None

    def take_recent_submission_images_with_placeholders(self):
        images, self.images = self.images, []
        return images

    def take_recent_submission_mention_bindings(self):
        bindings, self.bindings = self.bindings, []
        return bindings

    def set_composer_text_with_mention_bindings(self, *args):
        self.restored = args

    def skills(self):
        return self._skills


class Mode:
    def __init__(self, model="gpt", effort="medium") -> None:
        self._model = model
        self._effort = effort

    def model(self):
        return self._model

    def reasoning_effort(self):
        return self._effort


class Features:
    def __init__(self, enabled=()) -> None:
        self.enabled_set = set(enabled)

    def enabled(self, feature):
        return feature in self.enabled_set


class Widget:
    def __init__(self) -> None:
        self.bottom_pane = Pane()
        self.remote_urls = ["https://img"]
        self.app_event_tx = Tx()
        self.input_queue = SimpleNamespace(
            queued_user_messages=deque(),
            queued_user_message_history_records=deque(),
            user_turn_pending_start=False,
            pending_steers=deque(),
        )
        self.turn_lifecycle = SimpleNamespace(agent_turn_running=False)
        self.transcript = SimpleNamespace(
            needs_final_message_separator=True,
            saw_plan_item_this_turn=True,
        )
        self.config = SimpleNamespace(
            cwd="/repo",
            permissions=SimpleNamespace(
                approval_policy="on-request",
                active_permission_profile=lambda: "auto",
            ),
            features=Features(),
            personality=None,
        )
        self.ops = []
        self.history = []
        self.displays = []
        self.errors = []
        self.restored = None
        self.redraws = 0
        self.session_configured = True
        self.supports_images = True
        self.mode = Mode()
        self.active_collaboration_mask = None
        self.plugins = None
        self.apps = None

    def take_remote_image_urls(self):
        urls, self.remote_urls = self.remote_urls, []
        return urls

    def is_session_configured(self):
        return self.session_configured

    def refresh_pending_input_preview(self):
        self.preview_refreshed = True

    def current_model_supports_images(self):
        return self.supports_images

    def image_inputs_not_supported_message(self):
        return "no images"

    def set_remote_image_urls(self, urls):
        self.remote_urls = list(urls)

    def add_to_history(self, item):
        self.history.append(item)

    def request_redraw(self):
        self.redraws += 1

    def submit_op(self, op):
        self.ops.append(op)
        return True

    def append_message_history_entry(self, text):
        self.history.append(text)

    def effective_collaboration_mode(self):
        return self.mode

    def maybe_apply_ide_context(self, items):
        self.ide_context_items = items

    def collaboration_modes_enabled(self):
        return True

    def service_tier_update_for_core(self):
        return "auto"

    def current_model_supports_personality(self):
        return True

    def restore_user_message_to_composer(self, message):
        self.restored = message

    def add_error_message(self, message):
        self.errors.append(message)

    def on_user_message_display(self, display):
        self.displays.append(display)

    def plugins_for_mentions(self):
        return self.plugins

    def connectors_for_mentions(self):
        return self.apps


def test_user_message_from_submission_drains_images_urls_and_bindings() -> None:
    widget = Widget()

    message = user_message_from_submission(widget, "hi", ["text"])

    assert message.text == "hi"
    assert message.local_images == (LocalImageAttachment("/tmp/a.png"),)
    assert message.remote_image_urls == ("https://img",)
    assert message.mention_bindings == (MentionBinding("docs", "skill:///skills/docs/SKILL.md"),)
    assert widget.bottom_pane.images == []
    assert widget.remote_urls == []


def test_shell_command_empty_shows_help_and_nonempty_submits_with_history() -> None:
    widget = Widget()

    assert AppCommand is CrateAppCommand
    assert submit_shell_command(widget, "   ") is QueueDrain.CONTINUE
    assert widget.app_event_tx.events[0][0] == "InsertHistoryCell"

    assert submit_queued_shell_prompt(widget, UserMessage("!pwd")) is QueueDrain.STOP
    assert widget.ops[-1] == AppCommand.run_user_shell_command("pwd")
    assert widget.history[-1] == "!pwd"


def test_user_message_queues_when_session_not_configured_and_rejects_empty() -> None:
    widget = Widget()
    widget.session_configured = False
    message = UserMessage("hello")

    assert submit_user_message_with_history_record(widget, message, UserMessageHistoryRecord.user_message_text())
    assert widget.input_queue.queued_user_messages[0] == message

    widget = Widget()
    assert not submit_user_message_with_history_record(widget, UserMessage(""), UserMessageHistoryRecord.user_message_text())


def test_blocked_image_submission_restores_payload_and_warns() -> None:
    widget = Widget()
    widget.supports_images = False
    message = UserMessage("look", local_images=(LocalImageAttachment("/tmp/a.png"),), remote_image_urls=("https://img",))

    accepted = submit_user_message_with_history_record(widget, message, UserMessageHistoryRecord.user_message_text())

    assert not accepted
    assert widget.bottom_pane.restored[0] == "look"
    assert widget.remote_urls == ["https://img"]
    assert widget.history == [{"kind": "warning", "message": "no images"}]
    assert widget.redraws == 1


def test_shell_escape_policy_can_return_app_command_without_model_turn() -> None:
    widget = Widget()

    command = submit_user_message_with_shell_escape_policy(widget, UserMessage("!echo hi"), ShellEscapePolicy.ALLOW)

    assert command == AppCommand.run_user_shell_command("echo hi")
    assert widget.ops[-1] == command

    widget = Widget()
    command = submit_user_message_with_shell_escape_policy(widget, UserMessage("!echo hi"), ShellEscapePolicy.DISALLOW)
    assert command.kind == "UserTurn"
    assert command.payload["items"][0].kind == "Text"


def test_user_turn_items_history_display_and_mentions_are_submitted() -> None:
    """Rust codex-tui chatwidget/tests/composer_submission.rs UserTurn payload contract."""

    widget = Widget()
    widget.bottom_pane._skills = [SkillMetadata(name="docs", path_to_skills_md="/skills/docs/SKILL.md")]
    message = UserMessage(
        "$docs use this",
        local_images=(LocalImageAttachment("/tmp/a.png"),),
        remote_image_urls=("https://img",),
        text_elements=({"range": (0, 5), "placeholder": "$docs"},),
        mention_bindings=(MentionBinding("docs", "skill:///skills/docs/SKILL.md"),),
    )

    accepted = submit_user_message_with_history_record(widget, message, UserMessageHistoryRecord.user_message_text())

    assert accepted
    op = widget.ops[-1]
    assert isinstance(op, CrateAppCommand)
    assert op.kind == "UserTurn"
    assert [item.kind for item in op.payload["items"]] == ["Image", "LocalImage", "Text", "Skill"]
    assert op.payload["items"][0].payload == {"url": "https://img", "detail": None}
    assert op.payload["items"][1].payload == {"path": "/tmp/a.png", "detail": None}
    assert op.payload["items"][2].payload["text_elements"] == ({"range": (0, 5), "placeholder": "$docs"},)
    assert op.payload["active_permission_profile"] == "auto"
    assert widget.input_queue.user_turn_pending_start is True
    assert widget.history[-1] == "[$docs](skill:///skills/docs/SKILL.md) use this"
    assert widget.displays[0]["text"] == "$docs use this"
    assert widget.transcript.needs_final_message_separator is False


def test_running_turn_records_pending_steer_instead_of_displaying_history() -> None:
    widget = Widget()
    widget.turn_lifecycle.agent_turn_running = True

    accepted = submit_user_message_with_history_record(widget, UserMessage("steer"), UserMessageHistoryRecord.user_message_text())

    assert accepted
    assert len(widget.input_queue.pending_steers) == 1
    assert widget.displays == []
    assert widget.transcript.saw_plan_item_this_turn is False


def test_unavailable_model_restores_message_and_does_not_submit() -> None:
    widget = Widget()
    widget.mode = Mode(model="")

    accepted = submit_user_message_with_history_record(widget, UserMessage("hello"), UserMessageHistoryRecord.override("override"))

    assert not accepted
    assert widget.ops == []
    assert widget.errors[0].startswith("Thread model is unavailable")
    assert widget.restored.text == "override"


def test_plugin_and_app_mentions_are_added_from_bound_paths_and_plain_text_mentions() -> None:
    widget = Widget()
    widget.plugins = [
        SimpleNamespace(config_name="lint", display_name="Lint Plugin"),
    ]
    widget.apps = [
        AppInfo(id="github", name="GitHub", is_accessible=True, is_enabled=True),
        AppInfo(id="slack", name="Slack", is_accessible=False, is_enabled=True),
    ]
    message = UserMessage(
        "$github $slack",
        mention_bindings=(
            MentionBinding("lint", "plugin://lint"),
            MentionBinding("github", "app://github"),
        ),
    )

    accepted = submit_user_message_with_history_record(
        widget,
        message,
        UserMessageHistoryRecord.user_message_text(),
    )

    assert accepted
    op = widget.ops[-1]
    mentions = [item.payload for item in op.payload["items"] if item.kind == "Mention"]
    assert {"name": "Lint Plugin", "path": "plugin://lint"} in mentions
    assert {"name": "GitHub", "path": "app://github"} in mentions
    assert {"name": "Slack", "path": "app://slack"} not in mentions


def test_collaboration_mode_and_personality_payloads_follow_rust_feature_gates() -> None:
    widget = Widget()
    widget.active_collaboration_mask = object()
    widget.config.features = Features({"Personality"})
    widget.config.personality = "pirate"

    accepted = submit_user_message_with_history_record(
        widget,
        UserMessage("hello"),
        UserMessageHistoryRecord.user_message_text(),
    )

    assert accepted
    payload = widget.ops[-1].payload
    assert payload["collaboration_mode"].model() == widget.mode.model()
    assert payload["collaboration_mode"].reasoning_effort() == widget.mode.reasoning_effort()
    assert payload["personality"] == "pirate"
