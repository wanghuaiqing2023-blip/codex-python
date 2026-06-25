"""User-message and shell-prompt submission behavior for chat widgets.

This ports the local behavior of Rust
``codex-tui::chatwidget::input_submission`` into semantic Python DTOs and
widget callback hooks.  Like Rust, submitted user turns are constructed through
the crate-level ``app_command::AppCommand`` boundary.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple

from .._porting import RustTuiModule
from ..app_command import AppCommand
from .skills import (
    collect_tool_mentions,
    find_app_mentions,
    find_skill_mentions_with_tool_mentions,
    is_app_mentionable,
)

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::input_submission",
    source="codex/codex-rs/tui/src/chatwidget/input_submission.rs",
    status="complete",
)

__all__ = [
    "AppCommand",
    "LocalImageAttachment",
    "MentionBinding",
    "PendingSteer",
    "QueueDrain",
    "RUST_MODULE",
    "ShellEscapePolicy",
    "UserInput",
    "UserMessage",
    "UserMessageHistoryRecord",
    "restore_blocked_image_submission",
    "submit_queued_shell_prompt",
    "submit_user_message",
    "submit_user_message_with_history_record",
    "submit_user_message_with_shell_escape_policy",
    "user_message_from_submission",
]


USER_SHELL_COMMAND_HELP_TITLE = "Shell command"
USER_SHELL_COMMAND_HELP_HINT = "Type ! followed by a command to run it locally."


class QueueDrain(str, Enum):
    CONTINUE = "Continue"
    STOP = "Stop"


class ShellEscapePolicy(str, Enum):
    ALLOW = "Allow"
    DISALLOW = "Disallow"


class UserMessageHistoryRecordKind(str, Enum):
    USER_MESSAGE_TEXT = "UserMessageText"
    OVERRIDE = "Override"


@dataclass(frozen=True)
class LocalImageAttachment:
    path: str


@dataclass(frozen=True)
class MentionBinding:
    mention: str
    path: str


@dataclass(frozen=True)
class UserMessage:
    text: str
    local_images: tuple[LocalImageAttachment, ...] = ()
    remote_image_urls: tuple[str, ...] = ()
    text_elements: tuple[Any, ...] = ()
    mention_bindings: tuple[MentionBinding, ...] = ()


@dataclass(frozen=True)
class UserMessageHistoryRecord:
    kind: UserMessageHistoryRecordKind = UserMessageHistoryRecordKind.USER_MESSAGE_TEXT
    text: str = ""

    @classmethod
    def user_message_text(cls) -> "UserMessageHistoryRecord":
        return cls(UserMessageHistoryRecordKind.USER_MESSAGE_TEXT)

    @classmethod
    def override(cls, text: str) -> "UserMessageHistoryRecord":
        return cls(UserMessageHistoryRecordKind.OVERRIDE, text)


@dataclass(frozen=True)
class UserInput:
    kind: str
    payload: Dict[str, Any]


@dataclass(frozen=True)
class PendingSteer:
    user_message: UserMessage
    history_record: UserMessageHistoryRecord
    compare_key: tuple[Any, ...]


class InputSubmissionWidget(Protocol):
    bottom_pane: Any
    config: Any
    input_queue: Any
    transcript: Any


def user_message_from_submission(
    widget: Any,
    text: str,
    text_elements: Any,
) -> UserMessage:
    return UserMessage(
        text=text,
        local_images=tuple(widget.bottom_pane.take_recent_submission_images_with_placeholders()),
        remote_image_urls=tuple(widget.take_remote_image_urls()),
        text_elements=tuple(text_elements),
        mention_bindings=tuple(widget.bottom_pane.take_recent_submission_mention_bindings()),
    )


def submit_queued_shell_prompt(widget: Any, user_message: UserMessage) -> QueueDrain:
    if user_message.text.startswith("!"):
        return submit_shell_command_with_history(widget, user_message.text[1:], user_message.text)
    submit_user_message(widget, user_message)
    return QueueDrain.STOP


def submit_user_message(widget: Any, user_message: UserMessage) -> None:
    submit_user_message_with_history_record(
        widget, user_message, UserMessageHistoryRecord.user_message_text()
    )


def submit_user_message_with_history_record(
    widget: Any,
    user_message: UserMessage,
    history_record: UserMessageHistoryRecord,
) -> bool:
    accepted, _ = submit_user_message_with_history_and_shell_escape_policy(
        widget, user_message, history_record, ShellEscapePolicy.ALLOW
    )
    return accepted


def submit_user_message_with_shell_escape_policy(
    widget: Any,
    user_message: UserMessage,
    shell_escape_policy: ShellEscapePolicy,
) -> Optional[AppCommand]:
    _, command = submit_user_message_with_history_and_shell_escape_policy(
        widget,
        user_message,
        UserMessageHistoryRecord.user_message_text(),
        shell_escape_policy,
    )
    return command


def submit_user_message_with_history_and_shell_escape_policy(
    widget: Any,
    user_message: UserMessage,
    history_record: UserMessageHistoryRecord,
    shell_escape_policy: ShellEscapePolicy,
) -> Tuple[bool, Optional[AppCommand]]:
    if not widget.is_session_configured():
        widget.input_queue.queued_user_messages.appendleft(user_message)
        widget.input_queue.queued_user_message_history_records.appendleft(history_record)
        widget.refresh_pending_input_preview()
        return True, None

    if not user_message.text and not user_message.local_images and not user_message.remote_image_urls:
        return False, None

    if (user_message.local_images or user_message.remote_image_urls) and not widget.current_model_supports_images():
        restored = user_message_for_restore(user_message, history_record)
        restore_blocked_image_submission(
            widget,
            restored.text,
            restored.text_elements,
            restored.local_images,
            restored.mention_bindings,
            restored.remote_image_urls,
        )
        return False, None

    if shell_escape_policy is ShellEscapePolicy.ALLOW and user_message.text.startswith("!"):
        stripped = user_message.text[1:]
        drain = submit_shell_command_with_history(widget, stripped, user_message.text)
        if drain is QueueDrain.CONTINUE:
            return False, None
        return True, AppCommand.run_user_shell_command(stripped.strip())

    render_in_history = not bool(getattr(widget.turn_lifecycle, "agent_turn_running", False))
    items = _user_inputs_from_message(widget, user_message)
    effective_mode = widget.effective_collaboration_mode()
    model = effective_mode.model().strip()
    if not model:
        widget.add_error_message(
            "Thread model is unavailable. Wait for the thread to finish syncing or choose a model before sending input."
        )
        widget.restore_user_message_to_composer(user_message_for_restore(user_message, history_record))
        return False, None

    widget.maybe_apply_ide_context(items)
    collaboration_mode = effective_mode if widget.collaboration_modes_enabled() and getattr(widget, "active_collaboration_mask", None) is not None else None
    personality = (
        getattr(widget.config, "personality", None)
        if widget.config.features.enabled("Personality") and widget.current_model_supports_personality()
        else None
    )
    op = AppCommand.user_turn(
        items,
        cwd=widget.config.cwd,
        approval_policy=getattr(widget.config.permissions, "approval_policy", None),
        active_permission_profile=widget.config.permissions.active_permission_profile(),
        model=model,
        effort=effective_mode.reasoning_effort(),
        summary=None,
        service_tier=widget.service_tier_update_for_core(),
        final_output_json_schema=None,
        collaboration_mode=collaboration_mode,
        personality=personality,
    )
    if not widget.submit_op(op):
        return False, None

    if render_in_history:
        widget.input_queue.user_turn_pending_start = True

    history_text = _history_text(user_message.text, history_record, user_message.mention_bindings)
    if history_text:
        widget.append_message_history_entry(history_text)

    if not render_in_history:
        pending_steer = PendingSteer(
            user_message=user_message,
            history_record=history_record,
            compare_key=pending_steer_compare_key_from_items(items),
        )
        widget.input_queue.pending_steers.append(pending_steer)
        widget.transcript.saw_plan_item_this_turn = False
        widget.refresh_pending_input_preview()
    else:
        widget.on_user_message_display(user_message_display_for_history(user_message, history_record))

    widget.transcript.needs_final_message_separator = False
    return True, op


def submit_shell_command(widget: Any, command: str) -> QueueDrain:
    cmd = command.strip()
    if not cmd:
        widget.app_event_tx.send(
            ("InsertHistoryCell", {"title": USER_SHELL_COMMAND_HELP_TITLE, "hint": USER_SHELL_COMMAND_HELP_HINT})
        )
        return QueueDrain.CONTINUE
    widget.submit_op(AppCommand.run_user_shell_command(cmd))
    return QueueDrain.STOP


def submit_shell_command_with_history(widget: Any, command: str, history_text: str) -> QueueDrain:
    drain = submit_shell_command(widget, command)
    if drain is QueueDrain.STOP:
        widget.append_message_history_entry(history_text)
    return drain


def restore_blocked_image_submission(
    widget: Any,
    text: str,
    text_elements: tuple[Any, ...],
    local_images: tuple[LocalImageAttachment, ...],
    mention_bindings: tuple[MentionBinding, ...],
    remote_image_urls: tuple[str, ...],
) -> None:
    widget.set_remote_image_urls(tuple(remote_image_urls))
    widget.bottom_pane.set_composer_text_with_mention_bindings(
        text,
        tuple(text_elements),
        [image.path for image in local_images],
        tuple(mention_bindings),
    )
    widget.add_to_history({"kind": "warning", "message": widget.image_inputs_not_supported_message()})
    widget.request_redraw()


def _user_inputs_from_message(widget: Any, user_message: UserMessage) -> List[UserInput]:
    items: List[UserInput] = []
    for image_url in user_message.remote_image_urls:
        items.append(UserInput("Image", {"url": image_url, "detail": None}))
    for image in user_message.local_images:
        items.append(UserInput("LocalImage", {"path": image.path, "detail": None}))
    if user_message.text:
        items.append(
            UserInput(
                "Text",
                {"text": user_message.text, "text_elements": tuple(user_message.text_elements)},
            )
        )

    mentions = collect_tool_mentions(user_message.text, {})
    bound_names = {binding.mention for binding in user_message.mention_bindings}
    skill_names_lower: Set[str] = set()
    selected_skill_paths: Set[str] = set()

    skills = widget.bottom_pane.skills()
    if skills is not None:
        skill_names_lower = {skill.name.lower() for skill in skills}
        for binding in user_message.mention_bindings:
            path = _strip_prefix(binding.path, "skill://")
            for skill in skills:
                if skill.path_to_skills_md == path and skill.path_to_skills_md not in selected_skill_paths:
                    selected_skill_paths.add(skill.path_to_skills_md)
                    items.append(UserInput("Skill", {"name": skill.name, "path": skill.path_to_skills_md}))
                    break
        for skill in find_skill_mentions_with_tool_mentions(mentions, skills):
            if skill.name in bound_names or skill.path_to_skills_md in selected_skill_paths:
                continue
            selected_skill_paths.add(skill.path_to_skills_md)
            items.append(UserInput("Skill", {"name": skill.name, "path": skill.path_to_skills_md}))

    selected_plugin_ids: Set[str] = set()
    plugins = widget.plugins_for_mentions()
    if plugins is not None:
        for binding in user_message.mention_bindings:
            plugin_id = _strip_prefix(binding.path, "plugin://")
            if plugin_id == binding.path or not plugin_id or plugin_id in selected_plugin_ids:
                continue
            for plugin in plugins:
                if plugin.config_name == plugin_id:
                    selected_plugin_ids.add(plugin_id)
                    items.append(UserInput("Mention", {"name": plugin.display_name, "path": binding.path}))
                    break

    selected_app_ids: Set[str] = set()
    apps = widget.connectors_for_mentions()
    if apps is not None:
        for binding in user_message.mention_bindings:
            app_id = _strip_prefix(binding.path, "app://")
            if app_id == binding.path or not app_id or app_id in selected_app_ids:
                continue
            for app in apps:
                if app.id == app_id and is_app_mentionable(app):
                    selected_app_ids.add(app_id)
                    items.append(UserInput("Mention", {"name": app.name, "path": binding.path}))
                    break
        for app in find_app_mentions(mentions, apps, skill_names_lower):
            slug = _connector_mention_slug(app)
            if slug in bound_names or app.id in selected_app_ids:
                continue
            selected_app_ids.add(app.id)
            items.append(UserInput("Mention", {"name": app.name, "path": f"app://{app.id}"}))
    return items


def user_message_for_restore(user_message: UserMessage, history_record: UserMessageHistoryRecord) -> UserMessage:
    if history_record.kind is UserMessageHistoryRecordKind.OVERRIDE:
        return UserMessage(
            text=history_record.text,
            local_images=user_message.local_images,
            remote_image_urls=user_message.remote_image_urls,
            text_elements=user_message.text_elements,
            mention_bindings=user_message.mention_bindings,
        )
    return user_message


def user_message_display_for_history(
    user_message: UserMessage,
    history_record: UserMessageHistoryRecord,
) -> Dict[str, Any]:
    restored = user_message_for_restore(user_message, history_record)
    return {
        "text": restored.text,
        "local_images": restored.local_images,
        "remote_image_urls": restored.remote_image_urls,
        "text_elements": restored.text_elements,
        "mention_bindings": restored.mention_bindings,
    }


def pending_steer_compare_key_from_items(items: List[UserInput]) -> Tuple[Any, ...]:
    return tuple((item.kind, tuple(sorted(item.payload.items()))) for item in items)


def encode_history_mentions(text: str, mention_bindings: tuple[MentionBinding, ...]) -> str:
    result = text
    for binding in mention_bindings:
        result = result.replace(f"${binding.mention}", f"[${binding.mention}]({binding.path})")
    return result


def _history_text(
    text: str,
    history_record: UserMessageHistoryRecord,
    mention_bindings: Tuple[MentionBinding, ...],
) -> Optional[str]:
    if history_record.kind is UserMessageHistoryRecordKind.USER_MESSAGE_TEXT and text:
        return encode_history_mentions(text, mention_bindings)
    if history_record.kind is UserMessageHistoryRecordKind.OVERRIDE and history_record.text:
        return encode_history_mentions(history_record.text, mention_bindings)
    return None


def _connector_mention_slug(app: Any) -> str:
    name = getattr(app, "name", "")
    chars: List[str] = []
    prev_dash = False
    for char in name.lower():
        if char.isascii() and char.isalnum():
            chars.append(char)
            prev_dash = False
        elif not prev_dash:
            chars.append("-")
            prev_dash = True
    return "".join(chars).strip("-")


def _strip_prefix(value: str, prefix: str) -> str:
    if value.startswith(prefix):
        return value[len(prefix) :]
    return value
