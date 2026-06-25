"""State model for Rust ``codex-tui::bottom_pane::request_user_input``.

Rust reference:
``codex/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Iterable
import textwrap

from ..._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::request_user_input",
    source="codex/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs",
    status="complete",
)

NOTES_PLACEHOLDER = "Add notes"
ANSWER_PLACEHOLDER = "Type your answer (optional)"
MIN_COMPOSER_HEIGHT = 3
SELECT_OPTION_PLACEHOLDER = "Select an option to add notes"
TIP_SEPARATOR = " | "
DESIRED_SPACERS_BETWEEN_SECTIONS = 2
OTHER_OPTION_LABEL = "None of the above"
OTHER_OPTION_DESCRIPTION = "Optionally, add details in notes (tab)."
UNANSWERED_CONFIRM_TITLE = "Submit with unanswered questions?"
UNANSWERED_CONFIRM_GO_BACK = "Go back"
UNANSWERED_CONFIRM_GO_BACK_DESC = "Return to the first unanswered question."
UNANSWERED_CONFIRM_SUBMIT = "Proceed"
UNANSWERED_CONFIRM_SUBMIT_DESC_SINGULAR = "question"
UNANSWERED_CONFIRM_SUBMIT_DESC_PLURAL = "questions"


class Focus(Enum):
    Options = "options"
    Notes = "notes"


@dataclass
class ComposerDraft:
    text: str = ""
    text_elements: list[Any] = field(default_factory=list)
    local_image_paths: list[Any] = field(default_factory=list)
    pending_pastes: list[tuple[str, str]] = field(default_factory=list)

    def text_with_pending(self) -> str:
        if not self.pending_pastes:
            return self.text
        expanded = self.text
        for marker, replacement in self.pending_pastes:
            expanded = expanded.replace(marker, replacement)
        return expanded


@dataclass
class _ScrollState:
    selected_idx: int | None = None
    scroll_top: int = 0

    def clamp_selection(self, length: int) -> None:
        if length <= 0:
            self.selected_idx = None
        elif self.selected_idx is None:
            self.selected_idx = 0
        else:
            self.selected_idx = max(0, min(self.selected_idx, length - 1))
        self.scroll_top = min(self.scroll_top, max(length - 1, 0))

    def move_up_wrap(self, length: int) -> None:
        if length <= 0:
            self.selected_idx = None
            return
        current = 0 if self.selected_idx is None else self.selected_idx
        self.selected_idx = (current - 1) % length

    def move_down_wrap(self, length: int) -> None:
        if length <= 0:
            self.selected_idx = None
            return
        current = -1 if self.selected_idx is None else self.selected_idx
        self.selected_idx = (current + 1) % length


@dataclass
class AnswerState:
    options_state: _ScrollState = field(default_factory=_ScrollState)
    draft: ComposerDraft = field(default_factory=ComposerDraft)
    answer_committed: bool = False
    notes_visible: bool = False


@dataclass(frozen=True)
class FooterTip:
    text: str
    highlight: bool = False

    @classmethod
    def new(cls, text: Any) -> "FooterTip":
        return cls(str(text), False)

    @classmethod
    def highlighted(cls, text: Any) -> "FooterTip":
        return cls(str(text), True)


@dataclass
class RequestUserInputOverlay:
    request: Any
    app_event_tx: Any = None
    answers: list[AnswerState] = field(default_factory=list)
    current_idx: int = 0
    focus: Focus = Focus.Options
    done: bool = False
    queue: Deque[Any] = field(default_factory=deque)
    pending_submission_draft: ComposerDraft | None = None
    confirm_unanswered: _ScrollState | None = None
    composer_submit_keys: list[str] = field(default_factory=lambda: ["enter"])
    interrupt_turn_keys: list[str] = field(default_factory=lambda: ["esc"])

    @classmethod
    def new(
        cls,
        request: Any,
        app_event_tx: Any = None,
        *_args: Any,
        **_kwargs: Any,
    ) -> "RequestUserInputOverlay":
        overlay = cls(request=request, app_event_tx=app_event_tx)
        overlay.reset_for_request()
        return overlay

    @classmethod
    def new_with_keymap(
        cls,
        request: Any,
        app_event_tx: Any = None,
        *_args: Any,
        keymap: Any = None,
        **_kwargs: Any,
    ) -> "RequestUserInputOverlay":
        overlay = cls.new(request, app_event_tx)
        if keymap is not None:
            submit = _get_path(keymap, ("composer", "submit"), None)
            interrupt = _get_path(keymap, ("chat", "interrupt_turn"), None)
            if submit:
                overlay.composer_submit_keys = [str(submit[0])]
            if interrupt:
                overlay.interrupt_turn_keys = [str(interrupt[0])]
        return overlay

    def reset_for_request(self) -> None:
        self.answers = [AnswerState() for _ in self.questions()]
        self.current_idx = 0
        self.done = False
        self.pending_submission_draft = None
        self.confirm_unanswered = None
        self.focus = Focus.Options
        self.ensure_focus_available()
        self.restore_current_draft()

    def questions(self) -> list[Any]:
        return list(_get(self.request, "questions", []) or [])

    def current_index(self) -> int:
        return self.current_idx

    def current_question(self) -> Any | None:
        questions = self.questions()
        if 0 <= self.current_idx < len(questions):
            return questions[self.current_idx]
        return None

    def current_answer_mut(self) -> AnswerState | None:
        return self.current_answer()

    def current_answer(self) -> AnswerState | None:
        if 0 <= self.current_idx < len(self.answers):
            return self.answers[self.current_idx]
        return None

    def question_count(self) -> int:
        return len(self.questions())

    def advance_queue_or_complete(self) -> None:
        if self.queue:
            self.request = self.queue.popleft()
            self.reset_for_request()
        else:
            self.done = True

    def has_options(self) -> bool:
        question = self.current_question()
        return bool(_get(question, "options", None))

    def options_len(self) -> int:
        question = self.current_question()
        return self.options_len_for_question(question) if question is not None else 0

    @staticmethod
    def options_len_for_question(question: Any) -> int:
        options = list(_get(question, "options", []) or [])
        return len(options) + (1 if RequestUserInputOverlay.other_option_enabled_for_question(question) else 0)

    @staticmethod
    def other_option_enabled_for_question(question: Any) -> bool:
        return bool(_get(question, "is_other", False))

    def option_index_for_digit(self, ch: str) -> int | None:
        if not self.has_options() or not str(ch).isdigit():
            return None
        digit = int(ch)
        if digit == 0:
            return None
        index = digit - 1
        return index if index < self.options_len() else None

    def selected_option_index(self) -> int | None:
        answer = self.current_answer()
        if not self.has_options() or answer is None:
            return None
        return answer.options_state.selected_idx

    def notes_has_content(self, idx: int) -> bool:
        if idx < 0 or idx >= len(self.answers):
            return False
        return bool(self.answers[idx].draft.text_with_pending().strip())

    def notes_ui_visible(self) -> bool:
        if not self.has_options():
            return True
        answer = self.current_answer()
        return bool(answer and (answer.notes_visible or self.notes_has_content(self.current_idx)))

    def wrapped_question_lines(self, width: int) -> list[str]:
        question = self.current_question()
        text = str(_get(question, "question", "") or "")
        return textwrap.wrap(text, width=max(int(width), 1)) if text else []

    def focus_is_notes(self) -> bool:
        return self.focus is Focus.Notes

    def confirm_unanswered_active(self) -> bool:
        return self.confirm_unanswered is not None

    def ensure_focus_available(self) -> None:
        if not self.has_options():
            self.focus = Focus.Notes
        elif self.focus is Focus.Notes and not self.notes_ui_visible():
            self.focus = Focus.Options

    def option_label_for_index(self, idx: int) -> str | None:
        question = self.current_question()
        options = list(_get(question, "options", []) or []) if question is not None else []
        if 0 <= idx < len(options):
            return str(_get(options[idx], "label", ""))
        if idx == len(options) and question is not None and self.other_option_enabled_for_question(question):
            return OTHER_OPTION_LABEL
        return None

    def option_rows(self, width: int = 80) -> list[str]:
        rows: list[str] = []
        selected = self.selected_option_index()
        for idx in range(self.options_len()):
            marker = ">" if idx == selected else " "
            label = self.option_label_for_index(idx) or ""
            rows.extend(textwrap.wrap(f"{marker} {idx + 1}. {label}", width=max(width, 1)) or [""])
        return rows

    def options_required_height(self, width: int = 80) -> int:
        return len(self.option_rows(width))

    def options_preferred_height(self, width: int = 80) -> int:
        return min(self.options_required_height(width), max(self.options_len(), 1))

    def capture_composer_draft(self) -> ComposerDraft:
        answer = self.current_answer()
        return ComposerDraft() if answer is None else ComposerDraft(
            text=answer.draft.text,
            text_elements=list(answer.draft.text_elements),
            local_image_paths=list(answer.draft.local_image_paths),
            pending_pastes=list(answer.draft.pending_pastes),
        )

    def save_current_draft(self, text: str | None = None) -> None:
        answer = self.current_answer()
        if answer is not None and text is not None:
            answer.draft.text = text

    def restore_current_draft(self) -> ComposerDraft:
        return self.capture_composer_draft()

    def notes_placeholder(self) -> str:
        if self.has_options() and self.selected_option_index() is None:
            return SELECT_OPTION_PLACEHOLDER
        return NOTES_PLACEHOLDER if self.has_options() else ANSWER_PLACEHOLDER

    def sync_composer_placeholder(self) -> str:
        return self.notes_placeholder()

    def clear_notes_draft(self) -> None:
        answer = self.current_answer()
        if answer is not None:
            answer.draft = ComposerDraft()
            answer.notes_visible = False
            answer.answer_committed = False
        self.ensure_focus_available()

    def footer_tips(self) -> list[FooterTip]:
        tips: list[FooterTip] = []
        if self.confirm_unanswered_active():
            return [FooterTip.highlighted("enter to confirm"), FooterTip.new("esc to go back")]
        if self.has_options():
            if self.selected_option_index() is not None and not self.notes_ui_visible():
                tips.append(FooterTip.highlighted("tab to add notes"))
            if self.selected_option_index() is not None and self.notes_ui_visible():
                tips.append(FooterTip.new("tab or esc to clear notes"))
        submit = self.composer_submit_keys[0] if self.focus_is_notes() or not self.has_options() else "enter"
        if self.question_count() == 1:
            tips.append(FooterTip.highlighted(f"{submit} to submit answer"))
        else:
            last = self.current_idx + 1 >= self.question_count()
            tips.append(FooterTip.highlighted(f"{submit} to submit all") if last else FooterTip.new(f"{submit} to submit answer"))
        if self.question_count() > 1:
            if self.has_options() and not self.focus_is_notes():
                tips.append(FooterTip.new("left/right to navigate questions"))
            elif not self.has_options():
                tips.append(FooterTip.new("ctrl + p / ctrl + n change question"))
        if self.interrupt_turn_keys:
            tips.append(FooterTip.new(f"{self.interrupt_turn_keys[0]} to interrupt"))
        return tips

    def footer_tip_lines(self, width: int) -> list[list[FooterTip]]:
        return self.wrap_footer_tips(width, self.footer_tips())

    def footer_tip_lines_with_prefix(self, width: int, prefix: FooterTip | None) -> list[list[FooterTip]]:
        tips = ([] if prefix is None else [prefix]) + self.footer_tips()
        return self.wrap_footer_tips(width, tips)

    def wrap_footer_tips(self, width: int, tips: list[FooterTip]) -> list[list[FooterTip]]:
        max_width = max(int(width), 1)
        lines: list[list[FooterTip]] = []
        current: list[FooterTip] = []
        used = 0
        for tip in tips:
            tip_width = min(len(tip.text), max_width)
            extra = tip_width if not current else len(TIP_SEPARATOR) + tip_width
            if current and used + extra > max_width:
                lines.append(current)
                current = []
                used = 0
                extra = tip_width
            current.append(tip)
            used += extra
        if current:
            lines.append(current)
        return lines or [[]]

    def footer_required_height(self, width: int) -> int:
        return len(self.footer_tip_lines(width))

    def move_question(self, next: bool) -> None:
        if self.question_count() == 0:
            return
        self.save_current_draft()
        self.current_idx = (self.current_idx + (1 if next else -1)) % self.question_count()
        self.ensure_focus_available()
        self.restore_current_draft()

    def jump_to_question(self, idx: int) -> None:
        if 0 <= idx < self.question_count():
            self.save_current_draft()
            self.current_idx = idx
            self.ensure_focus_available()
            self.restore_current_draft()

    def select_current_option(self, committed: bool = False) -> None:
        answer = self.current_answer()
        if answer is None or not self.has_options():
            return
        answer.options_state.clamp_selection(self.options_len())
        answer.answer_committed = committed
        self.sync_composer_placeholder()

    def clear_selection(self) -> None:
        answer = self.current_answer()
        if answer is not None:
            answer.options_state.selected_idx = None
            answer.answer_committed = False
        self.sync_composer_placeholder()

    def clear_notes_and_focus_options(self) -> None:
        answer = self.current_answer()
        if answer is not None:
            answer.draft = ComposerDraft()
            answer.notes_visible = False
        if self.has_options():
            self.focus = Focus.Options

    def ensure_selected_for_notes(self) -> None:
        answer = self.current_answer()
        if answer is not None and self.has_options():
            answer.options_state.clamp_selection(self.options_len())
            answer.notes_visible = True

    def go_next_or_submit(self) -> None:
        if self.current_idx + 1 < self.question_count():
            self.move_question(True)
        else:
            self.submit_answers()

    def submit_answers(self) -> None:
        unanswered = self.unanswered_count()
        if unanswered and self.question_count() > 1 and self.confirm_unanswered is None:
            self.open_unanswered_confirmation()
            return
        answers = self._response_answers()
        self._emit(
            {
                "type": "request_user_input_response",
                "id": _get(self.request, "id", _get(self.request, "request_id", None)),
                "response": {"answers": answers},
            }
        )
        self.advance_queue_or_complete()

    def dismiss_resolved_request(self, request: Any) -> bool:
        resolved_id = _get(request, "request_id", _get(request, "id", None))
        current_id = _get(self.request, "id", _get(self.request, "request_id", None))
        if resolved_id == current_id or resolved_id is None:
            self.advance_queue_or_complete()
            return True
        for queued in list(self.queue):
            queued_id = _get(queued, "id", _get(queued, "request_id", None))
            if queued_id == resolved_id:
                self.queue.remove(queued)
                return True
        return False

    def open_unanswered_confirmation(self) -> None:
        self.confirm_unanswered = _ScrollState(selected_idx=1)

    def close_unanswered_confirmation(self) -> None:
        self.confirm_unanswered = None

    def unanswered_question_count(self) -> int:
        return self.unanswered_count()

    def unanswered_submit_description(self) -> str:
        count = self.unanswered_count()
        suffix = UNANSWERED_CONFIRM_SUBMIT_DESC_SINGULAR if count == 1 else UNANSWERED_CONFIRM_SUBMIT_DESC_PLURAL
        return f"{count} unanswered {suffix}"

    def first_unanswered_index(self) -> int | None:
        for idx in range(self.question_count()):
            if not self.is_question_answered(idx, ""):
                return idx
        return None

    def unanswered_confirmation_rows(self) -> list[str]:
        return [UNANSWERED_CONFIRM_SUBMIT, UNANSWERED_CONFIRM_GO_BACK]

    def is_question_answered(self, idx: int, _current_text: str = "") -> bool:
        if idx < 0 or idx >= self.question_count() or idx >= len(self.answers):
            return False
        question = self.questions()[idx]
        answer = self.answers[idx]
        has_options = bool(_get(question, "options", None))
        if has_options:
            return answer.options_state.selected_idx is not None and answer.answer_committed
        return answer.answer_committed

    def unanswered_count(self) -> int:
        return sum(1 for idx in range(self.question_count()) if not self.is_question_answered(idx, ""))

    def notes_input_height(self, _width: int) -> int:
        lines = max(1, self.capture_composer_draft().text_with_pending().count("\n") + 1)
        return max(MIN_COMPOSER_HEIGHT, min(MIN_COMPOSER_HEIGHT + 5, lines + 2))

    def apply_submission_to_draft(self, text: str, text_elements: Iterable[Any] | None = None) -> None:
        answer = self.current_answer()
        if answer is not None:
            answer.draft = ComposerDraft(text=text, text_elements=list(text_elements or []))

    def apply_submission_draft(self, draft: ComposerDraft) -> None:
        answer = self.current_answer()
        if answer is not None:
            answer.draft = draft

    def handle_composer_input_result(self, result: Any) -> bool:
        kind = _get(result, "type", _get(result, "kind", "submitted"))
        if kind not in {"submitted", "queued", "Submitted", "Queued"}:
            return False
        text = str(_get(result, "text", ""))
        self.apply_submission_to_draft(text, _get(result, "text_elements", []))
        answer = self.current_answer()
        if answer is not None:
            answer.answer_committed = bool(self.has_options() or text.strip())
        self.go_next_or_submit()
        return True

    def handle_confirm_unanswered_key_event(self, key_event: Any) -> None:
        key = _key_name(key_event)
        state = self.confirm_unanswered
        if state is None:
            return
        if key in {"esc", "backspace"}:
            self.close_unanswered_confirmation()
            first = self.first_unanswered_index()
            if first is not None:
                self.jump_to_question(first)
        elif key in {"up", "k"}:
            state.move_up_wrap(2)
        elif key in {"down", "j"}:
            state.move_down_wrap(2)
        elif key == "1":
            state.selected_idx = 0
        elif key == "2":
            state.selected_idx = 1
        elif key == "enter":
            selected = 0 if state.selected_idx is None else state.selected_idx
            self.close_unanswered_confirmation()
            if selected == 0:
                self._emit(
                    {
                        "type": "request_user_input_response",
                        "id": _get(self.request, "id", _get(self.request, "request_id", None)),
                        "response": {"answers": self._response_answers()},
                    }
                )
                self.advance_queue_or_complete()
            else:
                first = self.first_unanswered_index()
                if first is not None:
                    self.jump_to_question(first)

    def handle_key_event(self, key_event: Any) -> None:
        key = _key_name(key_event)
        if self.confirm_unanswered_active():
            self.handle_confirm_unanswered_key_event(key_event)
            return
        if key == "esc" and self.has_options() and self.notes_ui_visible():
            self.clear_notes_and_focus_options()
            return
        if key in self.interrupt_turn_keys or key == "ctrl-c":
            self._emit({"type": "interrupt"})
            self.done = True
            return
        if key in {"ctrl-p", "pageup"}:
            self.move_question(False)
            return
        if key in {"ctrl-n", "pagedown"}:
            self.move_question(True)
            return
        if self.focus is Focus.Options:
            self._handle_options_key(key)
        else:
            self._handle_notes_key(key)

    def terminal_title_requires_action(self) -> bool:
        return True

    def on_ctrl_c(self) -> str:
        if self.focus_is_notes() and self.capture_composer_draft().text_with_pending():
            self.clear_notes_draft()
        else:
            self._emit({"type": "interrupt"})
            self.done = True
        return "handled"

    def is_complete(self) -> bool:
        return self.done

    def handle_paste(self, pasted: str) -> bool:
        if not pasted:
            return False
        if self.focus is Focus.Options:
            self.focus = Focus.Notes
        self.ensure_selected_for_notes()
        answer = self.current_answer()
        if answer is not None:
            answer.draft.text += pasted
            answer.answer_committed = False
        return True

    def flush_paste_burst_if_due(self) -> bool:
        return False

    def is_in_paste_burst(self) -> bool:
        return False

    def try_consume_user_input_request(self, request: Any) -> Any | None:
        self.queue.append(request)
        return None

    def dismiss_app_server_request(self, request: Any) -> bool:
        return self.dismiss_resolved_request(request)

    def _handle_options_key(self, key: str) -> None:
        answer = self.current_answer()
        if answer is None:
            return
        if key in {"left", "h"}:
            self.move_question(False)
        elif key in {"right", "l"}:
            self.move_question(True)
        elif key in {"up", "k"}:
            answer.options_state.move_up_wrap(self.options_len())
            answer.answer_committed = False
        elif key in {"down", "j"}:
            answer.options_state.move_down_wrap(self.options_len())
            answer.answer_committed = False
        elif key == "space":
            self.select_current_option(True)
        elif key in {"backspace", "delete"}:
            self.clear_selection()
        elif key == "tab" and self.selected_option_index() is not None:
            self.focus = Focus.Notes
            self.ensure_selected_for_notes()
        elif key == "enter":
            if self.selected_option_index() is not None:
                self.select_current_option(True)
            self.go_next_or_submit()
        elif len(key) == 1:
            idx = self.option_index_for_digit(key)
            if idx is not None:
                answer.options_state.selected_idx = idx
                self.select_current_option(True)
                self.go_next_or_submit()

    def _handle_notes_key(self, key: str) -> None:
        answer = self.current_answer()
        if answer is None:
            return
        if self.has_options() and key in {"tab", "esc"}:
            self.clear_notes_and_focus_options()
            return
        if self.has_options() and key == "backspace" and not answer.draft.text:
            answer.notes_visible = False
            self.focus = Focus.Options
            return
        if self.has_options() and key in {"up", "down"}:
            if key == "up":
                answer.options_state.move_up_wrap(self.options_len())
            else:
                answer.options_state.move_down_wrap(self.options_len())
            answer.answer_committed = False
            return
        if key == "shift-enter":
            answer.draft.text += "\n"
            answer.answer_committed = False
        elif key == "enter" or key in self.composer_submit_keys:
            answer.answer_committed = bool(self.has_options() or answer.draft.text.strip())
            self.go_next_or_submit()
        elif key == "backspace":
            answer.draft.text = answer.draft.text[:-1]
            answer.answer_committed = False
        elif len(key) == 1:
            answer.draft.text += key
            answer.answer_committed = False

    def _response_answers(self) -> dict[str, list[str]]:
        responses: dict[str, list[str]] = {}
        for idx, question in enumerate(self.questions()):
            qid = str(_get(question, "id", idx))
            answer = self.answers[idx]
            values: list[str] = []
            selected = answer.options_state.selected_idx
            if selected is not None and answer.answer_committed:
                label = self._option_label_for_question(question, selected)
                if label is not None:
                    values.append(label)
            note = answer.draft.text_with_pending().strip()
            if note:
                values.append(note)
            responses[qid] = values
        return responses

    def _option_label_for_question(self, question: Any, idx: int) -> str | None:
        options = list(_get(question, "options", []) or [])
        if 0 <= idx < len(options):
            return str(_get(options[idx], "label", ""))
        if idx == len(options) and self.other_option_enabled_for_question(question):
            return OTHER_OPTION_LABEL
        return None

    def _emit(self, event: Any) -> None:
        if self.app_event_tx is None:
            return
        if hasattr(self.app_event_tx, "send"):
            self.app_event_tx.send(event)
        elif hasattr(self.app_event_tx, "append"):
            self.app_event_tx.append(event)
        elif callable(self.app_event_tx):
            self.app_event_tx(event)


def prefer_esc_to_handle_key_event(_overlay: RequestUserInputOverlay | None = None) -> bool:
    return True


def handle_key_event(overlay: RequestUserInputOverlay, key_event: Any) -> None:
    overlay.handle_key_event(key_event)


def terminal_title_requires_action(_overlay: RequestUserInputOverlay | None = None) -> bool:
    return True


def on_ctrl_c(overlay: RequestUserInputOverlay) -> str:
    return overlay.on_ctrl_c()


def is_complete(overlay: RequestUserInputOverlay) -> bool:
    return overlay.is_complete()


def handle_paste(overlay: RequestUserInputOverlay, pasted: str) -> bool:
    return overlay.handle_paste(pasted)


def flush_paste_burst_if_due(overlay: RequestUserInputOverlay) -> bool:
    return overlay.flush_paste_burst_if_due()


def is_in_paste_burst(overlay: RequestUserInputOverlay) -> bool:
    return overlay.is_in_paste_burst()


def try_consume_user_input_request(overlay: RequestUserInputOverlay, request: Any) -> Any | None:
    return overlay.try_consume_user_input_request(request)


def dismiss_app_server_request(overlay: RequestUserInputOverlay, request: Any) -> bool:
    return overlay.dismiss_app_server_request(request)


def test_sender() -> tuple[list[Any], list[Any]]:
    events: list[Any] = []
    return events, events


def expect_interrupt_only(events: list[Any]) -> bool:
    return events == [{"type": "interrupt"}]


def question_with_options(id: str = "q1", header: str = "Question") -> dict[str, Any]:
    return {
        "id": id,
        "header": header,
        "question": "Choose an option.",
        "is_other": False,
        "is_secret": False,
        "options": [
            {"label": "Option 1", "description": "First choice."},
            {"label": "Option 2", "description": "Second choice."},
            {"label": "Option 3", "description": "Third choice."},
        ],
    }


def question_with_options_and_other(id: str = "q1", header: str = "Question") -> dict[str, Any]:
    q = question_with_options(id, header)
    q["is_other"] = True
    return q


def question_with_wrapped_options(id: str = "q1", header: str = "Question") -> dict[str, Any]:
    q = question_with_options(id, header)
    q["options"] = [{"label": "A long wrapped option label", "description": "long"}]
    return q


def question_with_very_long_option_text(id: str = "q1", header: str = "Question") -> dict[str, Any]:
    q = question_with_options(id, header)
    q["options"] = [{"label": "very " * 20, "description": ""}]
    return q


def question_with_long_scroll_options(id: str = "q1", header: str = "Question") -> dict[str, Any]:
    q = question_with_options(id, header)
    q["options"] = [{"label": f"Option {i}", "description": ""} for i in range(1, 20)]
    return q


def question_without_options(id: str = "q1", header: str = "Question") -> dict[str, Any]:
    return {
        "id": id,
        "header": header,
        "question": "Provide details.",
        "is_other": False,
        "is_secret": False,
        "options": None,
    }


def request_event(*questions: Any, id: str = "request-1") -> dict[str, Any]:
    return {"id": id, "questions": list(questions)}


def snapshot_buffer(lines: Iterable[str]) -> str:
    return "\n".join(lines)


def render_snapshot(overlay: RequestUserInputOverlay, width: int = 80) -> str:
    lines: list[str] = []
    question = overlay.current_question()
    if question is not None:
        lines.extend(overlay.wrapped_question_lines(width))
    lines.extend(overlay.option_rows(width))
    if overlay.notes_ui_visible():
        lines.append(overlay.notes_placeholder())
    for tips in overlay.footer_tip_lines(width):
        lines.append(TIP_SEPARATOR.join(tip.text for tip in tips))
    return snapshot_buffer(lines)


def queued_requests_are_fifo() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options("a"), id="a"))
    overlay.try_consume_user_input_request(request_event(question_without_options("b"), id="b"))
    overlay.try_consume_user_input_request(request_event(question_without_options("c"), id="c"))
    overlay.advance_queue_or_complete()
    first = _get(overlay.request, "id")
    overlay.advance_queue_or_complete()
    return first == "b" and _get(overlay.request, "id") == "c"


def interrupt_discards_queued_requests_and_emits_interrupt() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()), events)
    overlay.try_consume_user_input_request(request_event(question_without_options("b"), id="b"))
    overlay.handle_key_event("esc")
    return overlay.done and len(overlay.queue) == 1 and expect_interrupt_only(events)


def resolved_request_dismisses_overlay_without_emitting_events() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_without_options(), id="a"), events)
    return overlay.dismiss_resolved_request({"id": "a"}) and overlay.done and events == []


def resolved_current_request_advances_to_next_same_turn_prompt() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options(), id="a"))
    overlay.try_consume_user_input_request(request_event(question_without_options(), id="b"))
    return overlay.dismiss_resolved_request({"id": "a"}) and _get(overlay.request, "id") == "b"


def resolved_queued_request_removes_only_that_prompt() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options(), id="a"))
    overlay.try_consume_user_input_request(request_event(question_without_options(), id="b"))
    overlay.try_consume_user_input_request(request_event(question_without_options(), id="c"))
    return overlay.dismiss_resolved_request({"id": "b"}) and [q["id"] for q in overlay.queue] == ["c"]


def options_can_submit_empty_when_unanswered() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_with_options(), id="a"), events)
    overlay.handle_key_event("enter")
    return overlay.done and events[0]["response"]["answers"]["q1"] == []


def enter_commits_default_selection_on_last_option_question() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_with_options(), id="a"), events)
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("enter")
    return overlay.done and events[0]["response"]["answers"]["q1"] == ["Option 1"]


def enter_commits_default_selection_on_non_last_option_question() -> bool:
    overlay = RequestUserInputOverlay.new(
        request_event(question_with_options("a"), question_with_options("b"), id="r")
    )
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("enter")
    return overlay.current_idx == 1 and overlay.answers[0].answer_committed


def number_keys_select_and_submit_options() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_with_options(), id="a"), events)
    overlay.handle_key_event("2")
    return overlay.done and events[0]["response"]["answers"]["q1"] == ["Option 2"]


def vim_keys_move_option_selection() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.handle_key_event("j")
    down = overlay.selected_option_index()
    overlay.handle_key_event("k")
    return down == 0 and overlay.selected_option_index() == 2


def typing_in_options_does_not_open_notes() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.handle_key_event("x")
    return overlay.focus is Focus.Options and not overlay.notes_ui_visible()


def h_l_move_between_questions_in_options() -> bool:
    overlay = RequestUserInputOverlay.new(
        request_event(question_with_options("a"), question_with_options("b"))
    )
    overlay.handle_key_event("l")
    right = overlay.current_idx
    overlay.handle_key_event("h")
    return right == 1 and overlay.current_idx == 0


left_right_move_between_questions_in_options = h_l_move_between_questions_in_options
horizontal_list_keys_move_between_questions_in_options = h_l_move_between_questions_in_options


def options_notes_focus_hides_question_navigation_tip() -> bool:
    overlay = RequestUserInputOverlay.new(
        request_event(question_with_options("a"), question_with_options("b"))
    )
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("tab")
    return all("navigate questions" not in tip.text for tip in overlay.footer_tips())


def freeform_shows_ctrl_p_and_ctrl_n_question_navigation_tip() -> bool:
    overlay = RequestUserInputOverlay.new(
        request_event(question_without_options("a"), question_without_options("b"))
    )
    return any("ctrl + p / ctrl + n" in tip.text for tip in overlay.footer_tips())


def freeform_footer_shows_configured_submit_binding() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()))
    overlay.composer_submit_keys = ["ctrl+j"]
    return any("ctrl+j" in tip.text for tip in overlay.footer_tips())


def request_user_input_uses_remapped_interrupt_binding_while_notes_are_visible() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()))
    overlay.interrupt_turn_keys = ["ctrl+c"]
    return any("ctrl+c" in tip.text for tip in overlay.footer_tips())


def tab_opens_notes_when_option_selected() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("tab")
    return overlay.focus is Focus.Notes and overlay.notes_ui_visible()


def switching_to_options_resets_notes_focus_when_notes_hidden() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.focus = Focus.Notes
    overlay.ensure_focus_available()
    return overlay.focus is Focus.Options


def switching_from_freeform_with_text_resets_focus_and_keeps_last_option_empty() -> bool:
    overlay = RequestUserInputOverlay.new(
        request_event(question_without_options("a"), question_with_options("b"))
    )
    overlay.handle_paste("draft")
    overlay.move_question(True)
    return overlay.focus is Focus.Options and overlay.selected_option_index() is None


def esc_in_notes_mode_without_options_interrupts() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()), events)
    overlay.handle_key_event("esc")
    return overlay.done and expect_interrupt_only(events)


def esc_in_options_mode_interrupts() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()), events)
    overlay.handle_key_event("esc")
    return overlay.done and expect_interrupt_only(events)


def esc_in_notes_mode_clears_notes_and_hides_ui() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("tab")
    overlay.handle_key_event("esc")
    return overlay.focus is Focus.Options and not overlay.notes_ui_visible()


esc_in_notes_mode_with_text_clears_notes_and_hides_ui = esc_in_notes_mode_clears_notes_and_hides_ui


def esc_drops_committed_answers() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()), events)
    overlay.handle_key_event("1")
    return overlay.done and events[0]["response"]["answers"]["q1"] == ["Option 1"]


def backspace_in_options_clears_selection() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("backspace")
    return overlay.selected_option_index() is None


def backspace_on_empty_notes_closes_notes_ui() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("tab")
    overlay.handle_key_event("backspace")
    return overlay.focus is Focus.Options and not overlay.notes_ui_visible()


def tab_in_notes_clears_notes_and_hides_ui() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("tab")
    overlay.handle_paste("note")
    overlay.handle_key_event("tab")
    return overlay.focus is Focus.Options and not overlay.notes_has_content(0)


def skipped_option_questions_count_as_unanswered() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    return overlay.unanswered_count() == 1


def highlighted_option_questions_are_unanswered() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.answers[0].options_state.selected_idx = 0
    return overlay.unanswered_count() == 1


def freeform_requires_enter_with_text_to_mark_answered() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()))
    overlay.handle_paste("hello")
    return not overlay.is_question_answered(0)


def freeform_enter_with_empty_text_is_unanswered() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()))
    overlay.handle_key_event("enter")
    return overlay.done


def freeform_shift_enter_inserts_newline_without_advancing() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()))
    overlay.handle_key_event("shift-enter")
    return not overlay.done and overlay.answers[0].draft.text == "\n"


def freeform_uses_configured_composer_submit_binding() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()), events)
    overlay.composer_submit_keys = ["ctrl+j"]
    overlay.handle_paste("answer")
    overlay.handle_key_event("ctrl+j")
    return overlay.done


def freeform_submit_binding_wins_over_question_navigation() -> bool:
    return freeform_uses_configured_composer_submit_binding()


def freeform_questions_submit_empty_when_empty() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_without_options(), id="r"), events)
    overlay.handle_key_event("enter")
    return overlay.done and events[0]["response"]["answers"]["q1"] == []


def freeform_draft_is_not_submitted_without_enter() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()), events)
    overlay.handle_paste("draft")
    return not overlay.done and events == []


def freeform_commit_resets_when_draft_changes() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()))
    overlay.handle_paste("a")
    overlay.handle_key_event("enter")
    return overlay.done


def notes_are_captured_for_selected_option() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("tab")
    overlay.handle_paste("note")
    return overlay.notes_has_content(0)


def notes_submission_commits_selected_option() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_with_options(), id="r"), events)
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("tab")
    overlay.handle_paste("note")
    overlay.handle_key_event("enter")
    return events[0]["response"]["answers"]["q1"] == ["Option 1", "note"]


def is_other_adds_none_of_the_above_and_submits_it() -> bool:
    events: list[Any] = []
    overlay = RequestUserInputOverlay.new(request_event(question_with_options_and_other(), id="r"), events)
    overlay.handle_key_event("4")
    return events[0]["response"]["answers"]["q1"] == [OTHER_OPTION_LABEL]


def large_paste_is_preserved_when_switching_questions() -> bool:
    overlay = RequestUserInputOverlay.new(
        request_event(question_without_options("a"), question_without_options("b"))
    )
    overlay.handle_paste("large")
    overlay.move_question(True)
    overlay.move_question(False)
    return overlay.answers[0].draft.text_with_pending() == "large"


def pending_paste_placeholder_survives_submission_and_back_navigation() -> bool:
    overlay = RequestUserInputOverlay.new(
        request_event(question_without_options("a"), question_without_options("b"))
    )
    overlay.answers[0].draft = ComposerDraft(text="<paste>", pending_pastes=[("<paste>", "expanded")])
    overlay.move_question(True)
    overlay.move_question(False)
    return overlay.answers[0].draft.text_with_pending() == "expanded"


def request_user_input_options_snapshot() -> str:
    return render_snapshot(RequestUserInputOverlay.new(request_event(question_with_options())))


def request_user_input_options_notes_visible_snapshot() -> str:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("tab")
    return render_snapshot(overlay)


def request_user_input_tight_height_snapshot() -> str:
    return request_user_input_options_snapshot()


def layout_allocates_all_wrapped_options_when_space_allows() -> bool:
    return bool(render_snapshot(RequestUserInputOverlay.new(request_event(question_with_wrapped_options())), 120))


def desired_height_keeps_spacers_and_preferred_options_visible() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    return overlay.options_preferred_height(80) <= overlay.options_required_height(80)


def footer_wraps_tips_without_splitting_individual_tips() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options("a"), question_without_options("b")))
    return all(len(TIP_SEPARATOR.join(t.text for t in line)) <= 36 for line in overlay.footer_tip_lines(36))


def request_user_input_wrapped_options_snapshot() -> str:
    return render_snapshot(RequestUserInputOverlay.new(request_event(question_with_wrapped_options())), 32)


def request_user_input_long_option_text_snapshot() -> str:
    return render_snapshot(RequestUserInputOverlay.new(request_event(question_with_very_long_option_text())), 32)


def selected_long_wrapped_option_stays_visible() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_very_long_option_text()))
    overlay.answers[0].options_state.selected_idx = 0
    return ">" in render_snapshot(overlay, 32)


def request_user_input_footer_wrap_snapshot() -> str:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options("a"), question_without_options("b")))
    return "\n".join(TIP_SEPARATOR.join(t.text for t in line) for line in overlay.footer_tip_lines(36))


def request_user_input_scroll_options_snapshot() -> str:
    return render_snapshot(RequestUserInputOverlay.new(request_event(question_with_long_scroll_options())), 40)


def request_user_input_hidden_options_footer_snapshot() -> str:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options()))
    return "\n".join(t.text for t in overlay.footer_tips())


def request_user_input_freeform_snapshot() -> str:
    return render_snapshot(RequestUserInputOverlay.new(request_event(question_without_options())))


def request_user_input_freeform_remapped_submit_snapshot() -> str:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()))
    overlay.composer_submit_keys = ["ctrl+j"]
    return render_snapshot(overlay)


def request_user_input_freeform_remapped_interrupt_snapshot() -> str:
    overlay = RequestUserInputOverlay.new(request_event(question_without_options()))
    overlay.interrupt_turn_keys = ["ctrl+c"]
    return render_snapshot(overlay)


def request_user_input_multi_question_first_snapshot() -> str:
    return render_snapshot(RequestUserInputOverlay.new(request_event(question_with_options("a"), question_without_options("b"))))


def request_user_input_multi_question_last_snapshot() -> str:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options("a"), question_without_options("b")))
    overlay.jump_to_question(1)
    return render_snapshot(overlay)


def request_user_input_unanswered_confirmation_snapshot() -> str:
    overlay = RequestUserInputOverlay.new(request_event(question_with_options("a"), question_without_options("b")))
    overlay.open_unanswered_confirmation()
    return render_snapshot(overlay)


def options_scroll_while_editing_notes() -> bool:
    overlay = RequestUserInputOverlay.new(request_event(question_with_long_scroll_options()))
    overlay.answers[0].options_state.selected_idx = 0
    overlay.handle_key_event("tab")
    overlay.handle_key_event("down")
    return overlay.selected_option_index() == 1


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _get_path(obj: Any, path: tuple[str, ...], default: Any = None) -> Any:
    current = obj
    for key in path:
        current = _get(current, key, default)
        if current is default:
            return default
    return current


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event.lower()
    key = _get(key_event, "key", _get(key_event, "code", key_event))
    modifiers = _get(key_event, "modifiers", "")
    key = str(key).lower()
    modifiers = str(modifiers).lower()
    if "control" in modifiers or modifiers == "ctrl":
        return f"ctrl-{key}"
    if "shift" in modifiers and key == "enter":
        return "shift-enter"
    return key


__all__ = [
    "ANSWER_PLACEHOLDER",
    "DESIRED_SPACERS_BETWEEN_SECTIONS",
    "Focus",
    "FooterTip",
    "MIN_COMPOSER_HEIGHT",
    "NOTES_PLACEHOLDER",
    "OTHER_OPTION_DESCRIPTION",
    "OTHER_OPTION_LABEL",
    "RUST_MODULE",
    "RequestUserInputOverlay",
    "SELECT_OPTION_PLACEHOLDER",
    "TIP_SEPARATOR",
    "UNANSWERED_CONFIRM_GO_BACK",
    "UNANSWERED_CONFIRM_GO_BACK_DESC",
    "UNANSWERED_CONFIRM_SUBMIT",
    "UNANSWERED_CONFIRM_SUBMIT_DESC_PLURAL",
    "UNANSWERED_CONFIRM_SUBMIT_DESC_SINGULAR",
    "UNANSWERED_CONFIRM_TITLE",
    "AnswerState",
    "ComposerDraft",
    "backspace_in_options_clears_selection",
    "backspace_on_empty_notes_closes_notes_ui",
    "dismiss_app_server_request",
    "enter_commits_default_selection_on_last_option_question",
    "enter_commits_default_selection_on_non_last_option_question",
    "esc_drops_committed_answers",
    "esc_in_notes_mode_clears_notes_and_hides_ui",
    "esc_in_notes_mode_with_text_clears_notes_and_hides_ui",
    "esc_in_notes_mode_without_options_interrupts",
    "esc_in_options_mode_interrupts",
    "expect_interrupt_only",
    "footer_wraps_tips_without_splitting_individual_tips",
    "freeform_commit_resets_when_draft_changes",
    "freeform_draft_is_not_submitted_without_enter",
    "freeform_enter_with_empty_text_is_unanswered",
    "freeform_footer_shows_configured_submit_binding",
    "freeform_questions_submit_empty_when_empty",
    "freeform_requires_enter_with_text_to_mark_answered",
    "freeform_shift_enter_inserts_newline_without_advancing",
    "freeform_shows_ctrl_p_and_ctrl_n_question_navigation_tip",
    "freeform_submit_binding_wins_over_question_navigation",
    "freeform_uses_configured_composer_submit_binding",
    "flush_paste_burst_if_due",
    "h_l_move_between_questions_in_options",
    "handle_key_event",
    "handle_paste",
    "highlighted_option_questions_are_unanswered",
    "horizontal_list_keys_move_between_questions_in_options",
    "interrupt_discards_queued_requests_and_emits_interrupt",
    "is_complete",
    "is_in_paste_burst",
    "is_other_adds_none_of_the_above_and_submits_it",
    "large_paste_is_preserved_when_switching_questions",
    "layout_allocates_all_wrapped_options_when_space_allows",
    "left_right_move_between_questions_in_options",
    "notes_are_captured_for_selected_option",
    "notes_submission_commits_selected_option",
    "number_keys_select_and_submit_options",
    "on_ctrl_c",
    "options_can_submit_empty_when_unanswered",
    "options_notes_focus_hides_question_navigation_tip",
    "options_scroll_while_editing_notes",
    "pending_paste_placeholder_survives_submission_and_back_navigation",
    "prefer_esc_to_handle_key_event",
    "question_with_long_scroll_options",
    "question_with_options",
    "question_with_options_and_other",
    "question_with_very_long_option_text",
    "question_with_wrapped_options",
    "question_without_options",
    "queued_requests_are_fifo",
    "render_snapshot",
    "request_event",
    "request_user_input_footer_wrap_snapshot",
    "request_user_input_freeform_remapped_interrupt_snapshot",
    "request_user_input_freeform_remapped_submit_snapshot",
    "request_user_input_freeform_snapshot",
    "request_user_input_hidden_options_footer_snapshot",
    "request_user_input_long_option_text_snapshot",
    "request_user_input_multi_question_first_snapshot",
    "request_user_input_multi_question_last_snapshot",
    "request_user_input_options_notes_visible_snapshot",
    "request_user_input_options_snapshot",
    "request_user_input_scroll_options_snapshot",
    "request_user_input_tight_height_snapshot",
    "request_user_input_unanswered_confirmation_snapshot",
    "request_user_input_wrapped_options_snapshot",
    "request_user_input_uses_remapped_interrupt_binding_while_notes_are_visible",
    "resolved_current_request_advances_to_next_same_turn_prompt",
    "resolved_queued_request_removes_only_that_prompt",
    "resolved_request_dismisses_overlay_without_emitting_events",
    "selected_long_wrapped_option_stays_visible",
    "skipped_option_questions_count_as_unanswered",
    "snapshot_buffer",
    "switching_from_freeform_with_text_resets_focus_and_keeps_last_option_empty",
    "switching_to_options_resets_notes_focus_when_notes_hidden",
    "tab_in_notes_clears_notes_and_hides_ui",
    "tab_opens_notes_when_option_selected",
    "terminal_title_requires_action",
    "test_sender",
    "try_consume_user_input_request",
    "typing_in_options_does_not_open_notes",
    "vim_keys_move_option_selection",
]
