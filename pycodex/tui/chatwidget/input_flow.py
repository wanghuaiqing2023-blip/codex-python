"""Semantic Python port of Rust ``codex-tui::chatwidget::input_flow``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/input_flow.rs``.

The Rust module owns user input submission, queue draining, and draft restore
flow around ``ChatWidget``. Python models the app-level state transitions and
side effects without requiring the concrete bottom pane, slash dispatcher, or
command runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::input_flow",
    source="codex/codex-rs/tui/src/chatwidget/input_flow.rs",
)


class QueuedInputAction(Enum):
    PLAIN = "Plain"
    PARSE_SLASH = "ParseSlash"
    RUN_SHELL = "RunShell"


class QueueDrain(Enum):
    CONTINUE = "Continue"
    STOP = "Stop"


class InputResultKind(Enum):
    SUBMITTED = "Submitted"
    QUEUED = "Queued"
    COMMAND = "Command"
    SERVICE_TIER_COMMAND = "ServiceTierCommand"
    COMMAND_WITH_ARGS = "CommandWithArgs"
    NONE = "None"


class ModeKind(Enum):
    PLAN = "Plan"
    OTHER = "Other"


class ExecCommandSource(Enum):
    USER_SHELL = "UserShell"
    OTHER = "Other"


@dataclass
class TextElement:
    value: Any


@dataclass
class UserMessage:
    text: str = ""
    local_images: list[Any] = field(default_factory=list)
    remote_image_urls: list[str] = field(default_factory=list)
    text_elements: list[TextElement] = field(default_factory=list)
    mention_bindings: list[Any] = field(default_factory=list)

    def is_empty_for_submission(self) -> bool:
        return not self.text and not self.local_images and not self.remote_image_urls


@dataclass
class QueuedUserMessage:
    user_message: UserMessage
    action: QueuedInputAction = QueuedInputAction.PLAIN

    def into_user_message(self) -> UserMessage:
        return self.user_message


@dataclass
class CollaborationModeMask:
    mode: ModeKind | None = None
    reasoning_effort: Any | None = None


@dataclass
class InputResult:
    kind: InputResultKind
    text: str = ""
    text_elements: list[TextElement] = field(default_factory=list)
    action: QueuedInputAction = QueuedInputAction.PLAIN
    command: Any | None = None
    args: str | None = None

    @classmethod
    def submitted(cls, text: str, text_elements: list[TextElement] | None = None) -> "InputResult":
        return cls(InputResultKind.SUBMITTED, text=text, text_elements=text_elements or [])

    @classmethod
    def queued(
        cls,
        text: str,
        action: QueuedInputAction,
        text_elements: list[TextElement] | None = None,
    ) -> "InputResult":
        return cls(
            InputResultKind.QUEUED,
            text=text,
            text_elements=text_elements or [],
            action=action,
        )

    @classmethod
    def command(cls, command: Any) -> "InputResult":
        return cls(InputResultKind.COMMAND, command=command)

    @classmethod
    def service_tier_command(cls, command: Any) -> "InputResult":
        return cls(InputResultKind.SERVICE_TIER_COMMAND, command=command)

    @classmethod
    def command_with_args(
        cls,
        command: Any,
        args: str,
        text_elements: list[TextElement] | None = None,
    ) -> "InputResult":
        return cls(
            InputResultKind.COMMAND_WITH_ARGS,
            command=command,
            args=args,
            text_elements=text_elements or [],
        )

    @classmethod
    def none(cls) -> "InputResult":
        return cls(InputResultKind.NONE)


@dataclass
class RunningCommand:
    source: ExecCommandSource


@dataclass
class InputQueue:
    queued_user_messages: list[QueuedUserMessage] = field(default_factory=list)
    queued_user_message_history_records: list[str] = field(default_factory=list)
    rejected_steers_queue: list[UserMessage] = field(default_factory=list)
    user_turn_pending_start: bool = False
    suppress_queue_autosend: bool = False

    def preview(self) -> dict[str, int]:
        return {
            "queued_messages": len(self.queued_user_messages),
            "pending_steers": 0,
            "rejected_steers": len(self.rejected_steers_queue),
        }


@dataclass
class InputFlowModel:
    session_configured: bool = True
    plan_streaming_in_tui: bool = False
    task_running: bool = False
    agent_turn_running: bool = False
    running_commands: dict[str, RunningCommand] = field(default_factory=dict)
    input_queue: InputQueue = field(default_factory=InputQueue)
    active_collaboration_mask: CollaborationModeMask | None = None
    plan_mode_reasoning_effort: Any | None = None
    bottom_pane_modal_active: bool = False

    submitted_messages: list[UserMessage] = field(default_factory=list)
    submitted_messages_with_history: list[tuple[UserMessage, str]] = field(default_factory=list)
    slash_dispatches: list[Any] = field(default_factory=list)
    service_tier_dispatches: list[Any] = field(default_factory=list)
    slash_with_args_dispatches: list[tuple[Any, str | None, list[TextElement]]] = field(
        default_factory=list
    )
    pending_input_previews: list[dict[str, int]] = field(default_factory=list)
    status_headers: list[str] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)
    collaboration_masks_set: list[CollaborationModeMask] = field(default_factory=list)
    reasoning_buffer: list[str] = field(default_factory=list)
    full_reasoning_buffer: list[str] = field(default_factory=list)
    plan_mode_nudge_refreshes: int = 0
    maybe_send_calls: int = 0

    queued_slash_handler: Callable[[UserMessage], QueueDrain] | None = None
    queued_shell_handler: Callable[[UserMessage], QueueDrain] | None = None

    def handle_composer_input_result(
        self,
        input_result: InputResult,
        had_modal_or_popup: bool,
    ) -> None:
        if input_result.kind is InputResultKind.SUBMITTED:
            user_message = self.user_message_from_submission(
                input_result.text,
                input_result.text_elements,
            )
            if user_message.is_empty_for_submission():
                return
            should_submit_now = self.is_session_configured() and not self.is_plan_streaming_in_tui()
            if should_submit_now:
                if self.only_user_shell_commands_running() and not user_message.text.startswith("!"):
                    self.queue_user_message(user_message)
                    return
                self.reasoning_buffer.clear()
                self.full_reasoning_buffer.clear()
                self.set_status_header("Working")
                self.submit_user_message(user_message)
            else:
                self.queue_user_message(user_message)
        elif input_result.kind is InputResultKind.QUEUED:
            user_message = self.user_message_from_submission(
                input_result.text,
                input_result.text_elements,
            )
            self.queue_user_message_with_options(user_message, input_result.action)
        elif input_result.kind is InputResultKind.COMMAND:
            self.handle_slash_command_dispatch(input_result.command)
        elif input_result.kind is InputResultKind.SERVICE_TIER_COMMAND:
            self.handle_service_tier_command_dispatch(input_result.command)
        elif input_result.kind is InputResultKind.COMMAND_WITH_ARGS:
            self.handle_slash_command_with_args_dispatch(
                input_result.command,
                input_result.args,
                input_result.text_elements,
            )

        if had_modal_or_popup and self.bottom_pane_no_modal_or_popup_active():
            self.maybe_send_next_queued_input()
        self.refresh_plan_mode_nudge()

    def queue_user_message(self, user_message: UserMessage) -> None:
        self.queue_user_message_with_options(user_message, QueuedInputAction.PLAIN)

    def set_queue_submissions_until_session_configured(self, queue: bool) -> bool:
        return bool(queue and not self.is_session_configured())

    def queue_user_message_with_options(
        self,
        user_message: UserMessage,
        action: QueuedInputAction,
    ) -> None:
        if not self.is_session_configured() or self.is_user_turn_pending_or_running():
            self.input_queue.queued_user_messages.append(QueuedUserMessage(user_message, action))
            self.input_queue.queued_user_message_history_records.append("UserMessageText")
            self.refresh_pending_input_preview()
        else:
            self.submit_user_message(user_message)

    def maybe_send_next_queued_input(self) -> bool:
        self.maybe_send_calls += 1
        if self.input_queue.suppress_queue_autosend:
            return False
        if self.is_user_turn_pending_or_running():
            return False

        submitted_follow_up = False
        while not self.is_user_turn_pending_or_running():
            popped = self.pop_next_queued_user_message()
            if popped is None:
                break
            queued_message, history_record = popped
            if queued_message.action is QueuedInputAction.PLAIN:
                submitted_follow_up = self.submit_user_message_with_history_record(
                    queued_message.into_user_message(),
                    history_record,
                )
                break
            if queued_message.action is QueuedInputAction.PARSE_SLASH:
                drain = self.submit_queued_slash_prompt(queued_message.into_user_message())
                if drain is QueueDrain.STOP:
                    submitted_follow_up = self.is_user_turn_pending_or_running()
                    break
            if queued_message.action is QueuedInputAction.RUN_SHELL:
                drain = self.submit_queued_shell_prompt(queued_message.into_user_message())
                if drain is QueueDrain.STOP:
                    submitted_follow_up = self.is_user_turn_pending_or_running()
                    break

        self.refresh_pending_input_preview()
        return submitted_follow_up

    def is_user_turn_pending_or_running(self) -> bool:
        return self.input_queue.user_turn_pending_start or self.task_running

    def only_user_shell_commands_running(self) -> bool:
        return (
            self.agent_turn_running
            and bool(self.running_commands)
            and all(command.source is ExecCommandSource.USER_SHELL for command in self.running_commands.values())
        )

    def refresh_pending_input_preview(self) -> None:
        self.pending_input_previews.append(self.input_queue.preview())

    def submit_user_message_with_mode(self, text: str, collaboration_mode: CollaborationModeMask) -> None:
        if (
            collaboration_mode.mode is ModeKind.PLAN
            and self.plan_mode_reasoning_effort is not None
        ):
            collaboration_mode.reasoning_effort = self.plan_mode_reasoning_effort
        if self.agent_turn_running and self.active_collaboration_mask != collaboration_mode:
            self.add_error_message("Cannot switch collaboration mode while a turn is running.")
            return
        self.set_collaboration_mask_from_user_action(collaboration_mode)
        user_message = UserMessage(text=text)
        if self.is_plan_streaming_in_tui():
            self.queue_user_message(user_message)
        else:
            self.submit_user_message(user_message)

    def queued_user_message_texts(self) -> list[str]:
        return [message.text for message in self.input_queue.rejected_steers_queue] + [
            queued.user_message.text for queued in self.input_queue.queued_user_messages
        ]

    def pop_next_queued_user_message(self) -> tuple[QueuedUserMessage, str] | None:
        if self.input_queue.rejected_steers_queue:
            message = self.input_queue.rejected_steers_queue.pop(0)
            return QueuedUserMessage(message), "UserMessageText"
        if not self.input_queue.queued_user_messages:
            return None
        queued = self.input_queue.queued_user_messages.pop(0)
        history = (
            self.input_queue.queued_user_message_history_records.pop(0)
            if self.input_queue.queued_user_message_history_records
            else "UserMessageText"
        )
        return queued, history

    def user_message_from_submission(
        self,
        text: str,
        text_elements: list[TextElement],
    ) -> UserMessage:
        return UserMessage(text=text, text_elements=list(text_elements))

    def is_session_configured(self) -> bool:
        return self.session_configured

    def is_plan_streaming_in_tui(self) -> bool:
        return self.plan_streaming_in_tui

    def bottom_pane_no_modal_or_popup_active(self) -> bool:
        return not self.bottom_pane_modal_active

    def submit_user_message(self, user_message: UserMessage) -> bool:
        self.submitted_messages.append(user_message)
        self.input_queue.user_turn_pending_start = True
        return True

    def submit_user_message_with_history_record(self, user_message: UserMessage, history: str) -> bool:
        self.submitted_messages_with_history.append((user_message, history))
        self.input_queue.user_turn_pending_start = True
        return True

    def submit_queued_slash_prompt(self, user_message: UserMessage) -> QueueDrain:
        if self.queued_slash_handler is not None:
            return self.queued_slash_handler(user_message)
        self.slash_dispatches.append(user_message.text)
        return QueueDrain.CONTINUE

    def submit_queued_shell_prompt(self, user_message: UserMessage) -> QueueDrain:
        if self.queued_shell_handler is not None:
            return self.queued_shell_handler(user_message)
        self.slash_dispatches.append(f"shell:{user_message.text}")
        return QueueDrain.CONTINUE

    def handle_slash_command_dispatch(self, command: Any) -> None:
        self.slash_dispatches.append(command)

    def handle_service_tier_command_dispatch(self, command: Any) -> None:
        self.service_tier_dispatches.append(command)

    def handle_slash_command_with_args_dispatch(
        self,
        command: Any,
        args: str | None,
        text_elements: list[TextElement],
    ) -> None:
        self.slash_with_args_dispatches.append((command, args, text_elements))

    def set_status_header(self, header: str) -> None:
        self.status_headers.append(header)

    def refresh_plan_mode_nudge(self) -> None:
        self.plan_mode_nudge_refreshes += 1

    def set_collaboration_mask_from_user_action(self, mask: CollaborationModeMask) -> None:
        self.active_collaboration_mask = mask
        self.collaboration_masks_set.append(mask)

    def add_error_message(self, message: str) -> None:
        self.error_messages.append(message)


__all__ = [
    "CollaborationModeMask",
    "ExecCommandSource",
    "InputFlowModel",
    "InputQueue",
    "InputResult",
    "InputResultKind",
    "ModeKind",
    "QueueDrain",
    "QueuedInputAction",
    "QueuedUserMessage",
    "RUST_MODULE",
    "RunningCommand",
    "TextElement",
    "UserMessage",
]
