"""Review preset selection and custom review prompt helpers.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/review_popups.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Union

from pycodex.git_utils import current_branch_name, local_git_branches, recent_commits
from pycodex.protocol import ReviewTarget

from .._porting import RustTuiModule
from ..bottom_pane.list_selection_view import SelectionItem, SelectionViewParams
from ..bottom_pane.custom_prompt_view import CustomPromptView
from ..bottom_pane.view_stack import TerminalSelectionTransition

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::review_popups",
    source="codex/codex-rs/tui/src/chatwidget/review_popups.rs",
    status="complete",
)


@dataclass(frozen=True)
class CommitLogEntry:
    sha: str
    subject: str
    timestamp: int = 0


@dataclass(frozen=True)
class ReviewPopupAction:
    kind: str
    cwd: Optional[Path] = None
    branch: Optional[str] = None
    sha: Optional[str] = None
    title: Optional[str] = None
    instructions: Optional[str] = None


def open_review_popup(cwd: Union[str, Path]) -> SelectionViewParams:
    cwd_path = Path(cwd)
    return SelectionViewParams(
        title="Select a review preset",
        footer_hint="standard-popup-hint",
        items=[
            SelectionItem(
                name="Review against a base branch",
                description="(PR Style)",
                actions=[ReviewPopupAction(kind="open_review_branch_picker", cwd=cwd_path)],
                dismiss_on_select=False,
                dismiss_parent_on_child_accept=True,
            ),
            SelectionItem(
                name="Review uncommitted changes",
                actions=[ReviewPopupAction(kind="review_uncommitted_changes")],
                dismiss_on_select=True,
            ),
            SelectionItem(
                name="Review a commit",
                actions=[ReviewPopupAction(kind="open_review_commit_picker", cwd=cwd_path)],
                dismiss_on_select=False,
                dismiss_parent_on_child_accept=True,
            ),
            SelectionItem(
                name="Custom review instructions",
                actions=[ReviewPopupAction(kind="open_review_custom_prompt")],
                dismiss_on_select=False,
                dismiss_parent_on_child_accept=True,
            ),
        ],
    )


def show_review_branch_picker(
    cwd: Union[str, Path],
    local_git_branches: Callable[[Path], Iterable[str]],
    current_branch_name: Callable[[Path], Optional[str]],
) -> SelectionViewParams:
    cwd_path = Path(cwd)
    return show_review_branch_picker_with_branches(
        local_git_branches(cwd_path),
        current_branch_name(cwd_path),
    )


def show_review_branch_picker_with_branches(
    branches: Iterable[str],
    current_branch: Optional[str],
) -> SelectionViewParams:
    current = current_branch or "(detached HEAD)"
    items = [
        SelectionItem(
            name=f"{current} -> {branch}",
            actions=[ReviewPopupAction(kind="review_base_branch", branch=branch)],
            dismiss_on_select=True,
            search_value=branch,
        )
        for branch in branches
    ]
    return SelectionViewParams(
        title="Select a base branch",
        footer_hint="standard-popup-hint",
        items=items,
        is_searchable=True,
        search_placeholder="Type to search branches",
    )


def show_review_commit_picker(
    cwd: Union[str, Path],
    recent_commits: Callable[[Path, int], Iterable[CommitLogEntry]],
    limit: int = 100,
) -> SelectionViewParams:
    return show_review_commit_picker_with_entries(recent_commits(Path(cwd), limit))


def show_review_commit_picker_with_entries(
    entries: Iterable[CommitLogEntry],
) -> SelectionViewParams:
    items = []  # type: List[SelectionItem]
    for entry in entries:
        items.append(
            SelectionItem(
                name=entry.subject,
                actions=[
                    ReviewPopupAction(
                        kind="review_commit",
                        sha=entry.sha,
                        title=entry.subject,
                    )
                ],
                dismiss_on_select=True,
                search_value=f"{entry.subject} {entry.sha}",
            )
        )
    return SelectionViewParams(
        title="Select a commit to review",
        footer_hint="standard-popup-hint",
        items=items,
        is_searchable=True,
        search_placeholder="Type to search commits",
    )


def show_review_custom_prompt() -> dict:
    return {
        "title": "Custom review instructions",
        "placeholder": "Type instructions and press Enter",
        "initial_text": "",
    }


def custom_review_prompt_action(prompt: str) -> Optional[ReviewPopupAction]:
    trimmed = prompt.strip()
    if not trimmed:
        return None
    return ReviewPopupAction(kind="review_custom", instructions=trimmed)


class TerminalReviewPopupController:
    """Terminal product-path controller for Rust ``chatwidget::review_popups``."""

    def __init__(self, app_runtime: Any, submit_review: Callable[[ReviewTarget, str], Any]) -> None:
        self.app_runtime = app_runtime
        self.submit_review = submit_review
        self._events: list[ReviewPopupAction] = []

    def open_view(self) -> SelectionViewParams:
        return open_review_popup(getattr(self.app_runtime, "cwd", Path.cwd()))

    def handle_command_with_args(self, args: str) -> None:
        action = custom_review_prompt_action(args)
        if action is not None:
            target = _review_target(action)
            if target is not None:
                self.submit_review(target, review_target_summary(target))

    def handle_events(self, events: tuple[object, ...]) -> TerminalSelectionTransition | None:
        pending = [*events, *self._events]
        self._events.clear()
        for event in pending:
            if not isinstance(event, ReviewPopupAction):
                continue
            if event.kind == "open_review_branch_picker":
                try:
                    return TerminalSelectionTransition(
                        show_review_branch_picker(
                            event.cwd or getattr(self.app_runtime, "cwd", Path.cwd()),
                            local_git_branches,
                            current_branch_name,
                        )
                    )
                except Exception as exc:
                    return TerminalSelectionTransition(_review_error_view("Unable to list branches", exc))
            if event.kind == "open_review_commit_picker":
                try:
                    entries = [
                        CommitLogEntry(entry.sha, entry.subject, getattr(entry, "timestamp", 0))
                        for entry in recent_commits(event.cwd or getattr(self.app_runtime, "cwd", Path.cwd()), 100)
                    ]
                    return TerminalSelectionTransition(show_review_commit_picker_with_entries(entries))
                except Exception as exc:
                    return TerminalSelectionTransition(_review_error_view("Unable to list commits", exc))
            if event.kind == "open_review_custom_prompt":
                view = CustomPromptView.new(
                    "Custom review instructions",
                    "Type instructions and press Enter",
                    "",
                    None,
                    lambda prompt: self._events.append(
                        ReviewPopupAction(kind="review_custom", instructions=prompt.strip())
                    ),
                )
                return TerminalSelectionTransition(view)
            target = _review_target(event)
            if target is not None:
                return TerminalSelectionTransition(
                    after_pop=lambda target=target: self.submit_review(target, review_target_summary(target))
                )
        return None


def _review_target(action: ReviewPopupAction) -> ReviewTarget | None:
    if action.kind == "review_uncommitted_changes":
        return ReviewTarget.uncommitted_changes()
    if action.kind == "review_base_branch" and action.branch:
        return ReviewTarget.base_branch(action.branch)
    if action.kind == "review_commit" and action.sha:
        return ReviewTarget.commit(action.sha, action.title)
    if action.kind == "review_custom" and action.instructions:
        return ReviewTarget.custom(action.instructions)
    return None


def review_target_summary(target: ReviewTarget) -> str:
    kind = str(getattr(target, "type", "")).lower()
    if kind == "basebranch":
        return f"Review changes against {target.branch or ''}"
    if kind == "commit":
        return f"Review commit {target.sha or ''}"
    if kind == "custom":
        return "Review custom instructions"
    return "Review current changes"


def _review_error_view(title: str, error: Exception) -> SelectionViewParams:
    return SelectionViewParams(
        title=title,
        footer_hint="standard-popup-hint",
        items=[SelectionItem(name=str(error), is_disabled=True, disabled_reason=str(error))],
    )


__all__ = [
    "CommitLogEntry",
    "RUST_MODULE",
    "ReviewPopupAction",
    "TerminalReviewPopupController",
    "review_target_summary",
    "custom_review_prompt_action",
    "open_review_popup",
    "show_review_branch_picker",
    "show_review_branch_picker_with_branches",
    "show_review_commit_picker",
    "show_review_commit_picker_with_entries",
    "show_review_custom_prompt",
]
