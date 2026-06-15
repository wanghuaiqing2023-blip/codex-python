"""Review preset selection and custom review prompt helpers.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/review_popups.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Union

from .._porting import RustTuiModule
from ..bottom_pane.list_selection_view import SelectionItem, SelectionViewParams

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


__all__ = [
    "CommitLogEntry",
    "RUST_MODULE",
    "ReviewPopupAction",
    "custom_review_prompt_action",
    "open_review_popup",
    "show_review_branch_picker",
    "show_review_branch_picker_with_branches",
    "show_review_commit_picker",
    "show_review_commit_picker_with_entries",
    "show_review_custom_prompt",
]
