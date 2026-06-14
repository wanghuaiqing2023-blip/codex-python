"""Feedback bottom-pane views and copy helpers.

Python port of Rust ``codex-tui::bottom_pane::feedback_view``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.feedback import DOCTOR_REPORT_ATTACHMENT_FILENAME
from pycodex.feedback import FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME
from pycodex.feedback import WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME
from pycodex.feedback import FeedbackDiagnostics

from .._porting import RustTuiModule
from ..app_event import FeedbackCategory
from .list_selection_view import SelectionItem
from .list_selection_view import SelectionViewParams
from .popup_consts import standard_popup_hint_line

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::feedback_view",
    source="codex/codex-rs/tui/src/bottom_pane/feedback_view.rs",
)

BASE_CLI_BUG_ISSUE_URL = "https://github.com/openai/codex/issues/new?template=3-cli.yml"
CODEX_FEEDBACK_INTERNAL_URL = "http://go/codex-feedback-internal"
GUTTER = "▌"


class FeedbackAudience(Enum):
    OPEN_AI_EMPLOYEE = "OpenAiEmployee"
    EXTERNAL = "External"


@dataclass(frozen=True)
class DisplayLine:
    text: str
    style: str = "plain"


@dataclass
class SimpleTextArea:
    text_value: str = ""
    cursor: int = 0

    @classmethod
    def new(cls) -> "SimpleTextArea":
        return cls()

    def text(self) -> str:
        return self.text_value

    def insert_str(self, text: str) -> None:
        text = str(text)
        self.text_value = self.text_value[: self.cursor] + text + self.text_value[self.cursor :]
        self.cursor += len(text)

    def input(self, key_event: Any) -> None:
        key = _key_name(key_event)
        if key == "enter":
            self.insert_str("\n")
        elif key == "backspace" and self.cursor > 0:
            self.text_value = self.text_value[: self.cursor - 1] + self.text_value[self.cursor :]
            self.cursor -= 1
        elif len(key) == 1:
            self.insert_str(key)

    def desired_height(self, width: int) -> int:
        width = max(1, int(width))
        if self.text_value == "":
            return 1
        return sum(max(1, (len(line) + width - 1) // width) for line in self.text_value.split("\n"))

    def cursor_pos(self, x: int, y: int, width: int, height: int) -> tuple[int, int] | None:
        if width <= 0 or height <= 0:
            return None
        row = 0
        col = 0
        for ch in self.text_value[: self.cursor]:
            if ch == "\n":
                row += 1
                col = 0
            else:
                col += 1
                if col >= width:
                    row += 1
                    col = 0
        return (x + col, y + min(row, height - 1))


@dataclass
class FeedbackNoteView:
    category: FeedbackCategory
    turn_id: str | None
    app_event_tx: Any
    include_logs: bool
    textarea: SimpleTextArea = field(default_factory=SimpleTextArea.new)
    complete: bool = False

    @classmethod
    def new(
        cls,
        category: FeedbackCategory,
        turn_id: str | None,
        app_event_tx: Any,
        include_logs: bool,
    ) -> "FeedbackNoteView":
        return cls(category, turn_id, app_event_tx, include_logs)

    def submit(self) -> None:
        note = self.textarea.text().strip()
        _send(
            self.app_event_tx,
            {
                "type": "SubmitFeedback",
                "category": self.category,
                "reason": note or None,
                "turn_id": self.turn_id,
                "include_logs": self.include_logs,
            },
        )
        self.complete = True

    def handle_key_event(self, key_event: Any) -> None:
        key = _key_name(key_event)
        if key == "esc":
            self.on_ctrl_c()
        elif key == "enter" and not _has_modifier(key_event):
            self.submit()
        else:
            self.textarea.input(key_event)

    def on_ctrl_c(self) -> str:
        self.complete = True
        return "Handled"

    def is_complete(self) -> bool:
        return self.complete

    def handle_paste(self, pasted: str) -> bool:
        if pasted == "":
            return False
        self.textarea.insert_str(pasted)
        return True

    def desired_height(self, width: int) -> int:
        return len(self.intro_lines(width)) + self.input_height(width) + 2

    def cursor_pos(self, area: Any) -> tuple[int, int] | None:
        width = _area_width(area)
        height = _area_height(area)
        if height < 2 or width <= 2:
            return None
        intro_height = len(self.intro_lines(width))
        text_area_height = self.input_height(width) - 1
        if text_area_height == 0:
            return None
        return self.textarea.cursor_pos(
            _area_x(area) + 2,
            _area_y(area) + intro_height + 1,
            width - 2,
            text_area_height,
        )

    def render(self, area: Any = None, buf: Any = None) -> list[DisplayLine]:
        width = _area_width(area)
        height = _area_height(area)
        if width == 0 or height == 0:
            return []
        _title, placeholder = feedback_title_and_placeholder(self.category)
        lines = self.intro_lines(width)
        lines.append(DisplayLine(gutter(), "gutter"))
        if self.textarea.text():
            lines.extend(DisplayLine(line) for line in self.textarea.text().split("\n"))
        else:
            lines.append(DisplayLine(placeholder, "placeholder"))
        lines.append(DisplayLine(""))
        lines.append(DisplayLine(standard_popup_hint_line(), "hint"))
        return lines[:height]

    def input_height(self, width: int) -> int:
        usable_width = max(0, int(width) - 2)
        text_height = min(8, max(1, self.textarea.desired_height(usable_width)))
        return min(9, text_height + 1)

    def intro_lines(self, width: int) -> list[DisplayLine]:
        title, _placeholder = feedback_title_and_placeholder(self.category)
        return [DisplayLine(f"{gutter()}{title}", "title")]


def handle_key_event(view: FeedbackNoteView, key_event: Any) -> None:
    view.handle_key_event(key_event)


def on_ctrl_c(view: FeedbackNoteView) -> str:
    return view.on_ctrl_c()


def is_complete(view: FeedbackNoteView) -> bool:
    return view.is_complete()


def handle_paste(view: FeedbackNoteView, pasted: str) -> bool:
    return view.handle_paste(pasted)


def desired_height(view: FeedbackNoteView, width: int) -> int:
    return view.desired_height(width)


def cursor_pos(view: FeedbackNoteView, area: Any) -> tuple[int, int] | None:
    return view.cursor_pos(area)


def render(view: FeedbackNoteView, area: Any = None, buf: Any = None) -> list[DisplayLine]:
    return view.render(area, buf)


def should_show_feedback_connectivity_details(
    category: FeedbackCategory,
    diagnostics: FeedbackDiagnostics,
) -> bool:
    return category is not FeedbackCategory.GOOD_RESULT and not _diagnostics_empty(diagnostics)


def gutter() -> str:
    return GUTTER


def feedback_title_and_placeholder(category: FeedbackCategory) -> tuple[str, str]:
    category = _category(category)
    common = "(optional) Write a short description to help us further"
    if category is FeedbackCategory.BAD_RESULT:
        return "Tell us more (bad result)", common
    if category is FeedbackCategory.GOOD_RESULT:
        return "Tell us more (good result)", common
    if category is FeedbackCategory.BUG:
        return "Tell us more (bug)", common
    if category is FeedbackCategory.SAFETY_CHECK:
        return "Tell us more (safety check)", "(optional) Share what was refused and why it should have been allowed"
    return "Tell us more (other)", common


def feedback_classification(category: FeedbackCategory) -> str:
    return {
        FeedbackCategory.BAD_RESULT: "bad_result",
        FeedbackCategory.GOOD_RESULT: "good_result",
        FeedbackCategory.BUG: "bug",
        FeedbackCategory.SAFETY_CHECK: "safety_check",
        FeedbackCategory.OTHER: "other",
    }[_category(category)]


@dataclass(frozen=True)
class WebHyperlinkHistoryCell:
    lines: list[DisplayLine]

    def display_lines(self, width: int) -> list[DisplayLine]:
        return list(self.lines)

    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def feedback_success_cell(
    category: FeedbackCategory,
    include_logs: bool,
    thread_id: str,
    feedback_audience: FeedbackAudience,
) -> WebHyperlinkHistoryCell:
    prefix = "• Feedback uploaded." if include_logs else "• Feedback recorded (no logs)."
    issue_url = issue_url_for_category(category, thread_id, feedback_audience)
    lines: list[DisplayLine] = []
    if issue_url and feedback_audience is FeedbackAudience.OPEN_AI_EMPLOYEE:
        lines.append(DisplayLine(f"{prefix} Please report this in #codex-feedback:"))
        lines.extend(
            [
                DisplayLine(""),
                DisplayLine(f"  {issue_url}", "link"),
                DisplayLine(""),
                DisplayLine("  Share this and add some info about your problem:"),
                DisplayLine(f"    https://go/codex-feedback/{thread_id}", "bold"),
            ]
        )
    elif issue_url:
        lines.append(DisplayLine(f"{prefix} Please open an issue using the following URL:"))
        lines.extend(
            [
                DisplayLine(""),
                DisplayLine(f"  {issue_url}", "link"),
                DisplayLine(""),
                DisplayLine(f"  Or mention your thread ID {thread_id} in an existing issue."),
            ]
        )
    else:
        lines.append(DisplayLine(f"{prefix} Thanks for the feedback!"))
        lines.extend([DisplayLine(""), DisplayLine(f"  Thread ID: {thread_id}")])
    return WebHyperlinkHistoryCell(lines)


def issue_url_for_category(
    category: FeedbackCategory,
    thread_id: str,
    feedback_audience: FeedbackAudience,
) -> str | None:
    category = _category(category)
    if category is FeedbackCategory.GOOD_RESULT:
        return None
    if feedback_audience is FeedbackAudience.OPEN_AI_EMPLOYEE:
        return slack_feedback_url(thread_id)
    return f"{BASE_CLI_BUG_ISSUE_URL}&steps=Uploaded%20thread:%20{thread_id}"


def slack_feedback_url(thread_id: str) -> str:
    return CODEX_FEEDBACK_INTERNAL_URL


def feedback_selection_params(app_event_tx: Any) -> SelectionViewParams:
    return SelectionViewParams(
        title="How was this?",
        items=[
            make_feedback_item(app_event_tx, "bug", "Crash, error message, hang, or broken UI/behavior.", FeedbackCategory.BUG),
            make_feedback_item(app_event_tx, "bad result", "Output was off-target, incorrect, incomplete, or unhelpful.", FeedbackCategory.BAD_RESULT),
            make_feedback_item(app_event_tx, "good result", "Helpful, correct, high-quality, or delightful result worth celebrating.", FeedbackCategory.GOOD_RESULT),
            make_feedback_item(app_event_tx, "safety check", "Benign usage blocked due to safety checks or refusals.", FeedbackCategory.SAFETY_CHECK),
            make_feedback_item(app_event_tx, "other", "Slowness, feature suggestion, UX feedback, or anything else.", FeedbackCategory.OTHER),
        ],
    )


def feedback_disabled_params() -> SelectionViewParams:
    return SelectionViewParams(
        title="Sending feedback is disabled",
        subtitle="This action is disabled by configuration.",
        footer_hint=standard_popup_hint_line(),
        items=[SelectionItem(name="Close", dismiss_on_select=True)],
    )


def make_feedback_item(
    app_event_tx: Any,
    name: str,
    description: str,
    category: FeedbackCategory,
) -> SelectionItem:
    def action(_sender: Any = None) -> None:
        _send(app_event_tx, {"type": "OpenFeedbackConsent", "category": category})

    return SelectionItem(
        name=name,
        description=description,
        actions=[action],
        dismiss_on_select=True,
    )


def feedback_upload_consent_params(
    app_event_tx: Any,
    category: FeedbackCategory,
    rollout_path: Any,
    auto_review_rollout_filename: str | None,
    include_windows_sandbox_log: bool,
    feedback_diagnostics: FeedbackDiagnostics,
) -> SelectionViewParams:
    def yes_action(_sender: Any = None) -> None:
        _send(app_event_tx, {"type": "OpenFeedbackNote", "category": category, "include_logs": True})

    def no_action(_sender: Any = None) -> None:
        _send(app_event_tx, {"type": "OpenFeedbackNote", "category": category, "include_logs": False})

    header = upload_consent_header_lines(
        category,
        rollout_path,
        auto_review_rollout_filename,
        include_windows_sandbox_log,
        feedback_diagnostics,
    )
    return SelectionViewParams(
        footer_hint=standard_popup_hint_line(),
        items=[
            SelectionItem(
                name="Yes",
                description="Share the current Codex session logs and diagnostics with the team for troubleshooting.",
                actions=[yes_action],
                dismiss_on_select=True,
            ),
            SelectionItem(name="No", actions=[no_action], dismiss_on_select=True),
        ],
        header=header,
    )


def upload_consent_header_lines(
    category: FeedbackCategory,
    rollout_path: Any,
    auto_review_rollout_filename: str | None,
    include_windows_sandbox_log: bool,
    feedback_diagnostics: FeedbackDiagnostics,
) -> list[DisplayLine]:
    lines = [
        DisplayLine("Upload logs?", "title"),
        DisplayLine(""),
        DisplayLine("The following files will be sent:", "dim"),
        DisplayLine("  • codex-logs.log"),
        DisplayLine(f"  • {DOCTOR_REPORT_ATTACHMENT_FILENAME}"),
    ]
    if include_windows_sandbox_log:
        lines.append(DisplayLine(f"  • {WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME}"))
    if rollout_path is not None:
        lines.append(DisplayLine(f"  • {Path(rollout_path).name}"))
    if auto_review_rollout_filename:
        lines.append(DisplayLine(f"  • {auto_review_rollout_filename}"))
    if not _diagnostics_empty(feedback_diagnostics):
        lines.append(DisplayLine(f"  • {FEEDBACK_DIAGNOSTICS_ATTACHMENT_FILENAME}"))
    if should_show_feedback_connectivity_details(category, feedback_diagnostics):
        lines.append(DisplayLine(""))
        lines.append(DisplayLine("Connectivity diagnostics", "title"))
        for diagnostic in _diagnostics(feedback_diagnostics):
            lines.append(DisplayLine(f"  - {diagnostic.headline}"))
            for detail in getattr(diagnostic, "details", []):
                lines.append(DisplayLine(f"    - {detail}", "dim"))
    return lines


def _category(category: FeedbackCategory) -> FeedbackCategory:
    if isinstance(category, FeedbackCategory):
        return category
    name = str(category)
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    normalized = name.replace("-", "_").upper()
    return FeedbackCategory[normalized]


def _diagnostics(feedback_diagnostics: FeedbackDiagnostics) -> list[Any]:
    value = getattr(feedback_diagnostics, "diagnostics", [])
    return value() if callable(value) else list(value)


def _diagnostics_empty(feedback_diagnostics: FeedbackDiagnostics) -> bool:
    return len(_diagnostics(feedback_diagnostics)) == 0


def _send(target: Any, event: dict[str, Any]) -> None:
    if target is None:
        return
    if hasattr(target, "send"):
        target.send(event)
    elif hasattr(target, "append"):
        target.append(event)
    elif callable(target):
        target(event)
    elif hasattr(target, "events"):
        target.events.append(event)


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event.lower()
    for attr in ("key", "code", "name"):
        value = getattr(key_event, attr, None)
        if value is not None:
            return str(value).lower()
    return str(key_event).lower()


def _has_modifier(key_event: Any) -> bool:
    if isinstance(key_event, str):
        return False
    return bool(getattr(key_event, "modifiers", None))


def _area_x(area: Any) -> int:
    if isinstance(area, dict):
        return int(area.get("x", 0))
    if isinstance(area, tuple) and len(area) >= 1:
        return int(area[0])
    return int(getattr(area, "x", 0))


def _area_y(area: Any) -> int:
    if isinstance(area, dict):
        return int(area.get("y", 0))
    if isinstance(area, tuple) and len(area) >= 2:
        return int(area[1])
    return int(getattr(area, "y", 0))


def _area_width(area: Any) -> int:
    if area is None:
        return 0
    if isinstance(area, dict):
        return int(area.get("width", 0))
    if isinstance(area, tuple) and len(area) >= 3:
        return int(area[2])
    return int(getattr(area, "width", 0))


def _area_height(area: Any) -> int:
    if area is None:
        return 0
    if isinstance(area, dict):
        return int(area.get("height", 0))
    if isinstance(area, tuple) and len(area) >= 4:
        return int(area[3])
    return int(getattr(area, "height", 0))


__all__ = [
    "BASE_CLI_BUG_ISSUE_URL",
    "CODEX_FEEDBACK_INTERNAL_URL",
    "DisplayLine",
    "FeedbackAudience",
    "FeedbackNoteView",
    "GUTTER",
    "RUST_MODULE",
    "SimpleTextArea",
    "WebHyperlinkHistoryCell",
    "cursor_pos",
    "desired_height",
    "feedback_classification",
    "feedback_disabled_params",
    "feedback_selection_params",
    "feedback_success_cell",
    "feedback_title_and_placeholder",
    "feedback_upload_consent_params",
    "gutter",
    "handle_key_event",
    "handle_paste",
    "is_complete",
    "issue_url_for_category",
    "make_feedback_item",
    "on_ctrl_c",
    "render",
    "should_show_feedback_connectivity_details",
    "slack_feedback_url",
    "upload_consent_header_lines",
]
