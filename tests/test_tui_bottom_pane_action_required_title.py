"""Parity tests for Rust ``codex-tui::bottom_pane::action_required_title``."""

from pycodex.tui.bottom_pane.action_required_title import (
    ACTION_REQUIRED_PREVIEW_PREFIX,
    build_action_required_title_text,
)
from pycodex.tui.bottom_pane.title_setup import TerminalTitleItem


def test_action_required_preview_prefix_matches_rust_constant() -> None:
    assert ACTION_REQUIRED_PREVIEW_PREFIX == "[ ! ] Action Required"


def test_build_action_required_title_text_filters_spinner_and_excluded_items() -> None:
    # Rust contract: start with prefix, skip Spinner and excluded items, append
    # Some(value) results from value_for, and join with " | ".
    items = [
        TerminalTitleItem.APP_NAME,
        TerminalTitleItem.SPINNER,
        TerminalTitleItem.PROJECT,
        TerminalTitleItem.GIT_BRANCH,
    ]
    excluded = [TerminalTitleItem.PROJECT]
    values = {
        TerminalTitleItem.APP_NAME: "Codex",
        TerminalTitleItem.PROJECT: "ignored-project",
        TerminalTitleItem.GIT_BRANCH: "main",
    }

    assert (
        build_action_required_title_text(
            ACTION_REQUIRED_PREVIEW_PREFIX,
            items,
            excluded,
            values.get,
        )
        == "[ ! ] Action Required | Codex | main"
    )


def test_build_action_required_title_text_omits_none_values_but_keeps_prefix() -> None:
    assert (
        build_action_required_title_text(
            "prefix",
            [TerminalTitleItem.APP_NAME, TerminalTitleItem.MODEL],
            [],
            lambda item: "Codex" if item is TerminalTitleItem.APP_NAME else None,
        )
        == "prefix | Codex"
    )

    assert build_action_required_title_text("prefix", [TerminalTitleItem.SPINNER], [], lambda item: "ignored") == "prefix"


def test_build_action_required_title_text_with_no_items_returns_prefix() -> None:
    # Rust source: parts starts as vec![prefix.to_string()] and is joined even when items is empty.
    assert build_action_required_title_text("prefix", [], [], lambda item: "ignored") == "prefix"


def test_build_action_required_title_text_preserves_order_duplicates_and_skips_callbacks() -> None:
    seen: list[TerminalTitleItem] = []

    def value_for(item: TerminalTitleItem) -> str:
        seen.append(item)
        return item.value

    rendered = build_action_required_title_text(
        "prefix",
        [
            TerminalTitleItem.APP_NAME,
            TerminalTitleItem.SPINNER,
            TerminalTitleItem.GIT_BRANCH,
            TerminalTitleItem.APP_NAME,
            TerminalTitleItem.MODEL,
        ],
        [TerminalTitleItem.MODEL],
        value_for,
    )

    assert rendered == "prefix | app-name | git-branch | app-name"
    assert seen == [
        TerminalTitleItem.APP_NAME,
        TerminalTitleItem.GIT_BRANCH,
        TerminalTitleItem.APP_NAME,
    ]
