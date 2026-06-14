from pycodex.tui.bottom_pane.title_setup import (
    MultiSelectItem,
    TerminalTitleItem,
    TerminalTitleSetupView,
    parse_terminal_title_items,
    preview_line_for_title_items,
)


def test_parse_terminal_title_items_preserves_order_matches_rust():
    assert parse_terminal_title_items(["project-name", "activity", "run-state", "thread-title"]) == [
        TerminalTitleItem.PROJECT,
        TerminalTitleItem.SPINNER,
        TerminalTitleItem.STATUS,
        TerminalTitleItem.THREAD,
    ]


def test_parse_terminal_title_items_rejects_invalid_ids_matches_rust():
    assert parse_terminal_title_items(["project", "not-a-title-item"]) is None


def test_canonical_ids_and_legacy_aliases_match_rust_tests():
    assert str(TerminalTitleItem.SPINNER) == "activity"
    assert TerminalTitleItem.from_id("spinner") is TerminalTitleItem.SPINNER
    assert str(TerminalTitleItem.PROJECT) == "project-name"
    assert TerminalTitleItem.from_id("project") is TerminalTitleItem.PROJECT
    assert str(TerminalTitleItem.THREAD) == "thread-title"
    assert TerminalTitleItem.from_id("thread") is TerminalTitleItem.THREAD
    assert str(TerminalTitleItem.MODEL) == "model"
    assert TerminalTitleItem.from_id("model-name") is TerminalTitleItem.MODEL
    assert str(TerminalTitleItem.STATUS) == "run-state"
    assert TerminalTitleItem.from_id("status") is TerminalTitleItem.STATUS
    assert str(TerminalTitleItem.MODEL_WITH_REASONING) == "model-with-reasoning"


def test_parse_accepts_all_kebab_case_variants_from_rust_test():
    ids = [
        "app-name",
        "context-remaining",
        "context-used",
        "five-hour-limit",
        "git-branch",
        "activity",
        "current-dir",
        "project-name",
        "model",
        "model-with-reasoning",
        "weekly-limit",
        "codex-version",
        "used-tokens",
        "total-input-tokens",
        "total-output-tokens",
        "session-id",
        "fast-mode",
    ]
    assert parse_terminal_title_items(ids) == [
        TerminalTitleItem.APP_NAME,
        TerminalTitleItem.CONTEXT_REMAINING,
        TerminalTitleItem.CONTEXT_USED,
        TerminalTitleItem.FIVE_HOUR_LIMIT,
        TerminalTitleItem.GIT_BRANCH,
        TerminalTitleItem.SPINNER,
        TerminalTitleItem.CURRENT_DIR,
        TerminalTitleItem.PROJECT,
        TerminalTitleItem.MODEL,
        TerminalTitleItem.MODEL_WITH_REASONING,
        TerminalTitleItem.WEEKLY_LIMIT,
        TerminalTitleItem.CODEX_VERSION,
        TerminalTitleItem.USED_TOKENS,
        TerminalTitleItem.TOTAL_INPUT_TOKENS,
        TerminalTitleItem.TOTAL_OUTPUT_TOKENS,
        TerminalTitleItem.SESSION_ID,
        TerminalTitleItem.FAST_MODE,
    ]


def test_preview_line_joins_non_spinner_items_with_pipe_and_omits_missing_values():
    preview = preview_line_for_title_items(
        [TerminalTitleItem.PROJECT, TerminalTitleItem.STATUS, TerminalTitleItem.THREAD],
        {"ProjectName": "repo", "Status": "Ready"},
    )
    assert preview == "repo | Ready"


def test_preview_item_and_separator_rules_match_rust():
    assert TerminalTitleItem.SPINNER.preview_item() is None
    assert TerminalTitleItem.PROJECT.preview_item() == "ProjectName"
    assert TerminalTitleItem.STATUS.preview_item() == "Status"

    assert TerminalTitleItem.PROJECT.separator_from_previous(None) == ""
    assert TerminalTitleItem.STATUS.separator_from_previous(TerminalTitleItem.PROJECT) == " | "
    assert TerminalTitleItem.SPINNER.separator_from_previous(TerminalTitleItem.PROJECT) == " "
    assert TerminalTitleItem.STATUS.separator_from_previous(TerminalTitleItem.SPINNER) == " "


def test_preview_line_with_activity_uses_action_required_title_builder():
    # Rust source: preview_line_for_title_items calls
    # build_action_required_title_text when Spinner is selected, so Spinner is
    # omitted and the action-required prefix is joined with remaining values by
    # " | ".
    preview = preview_line_for_title_items(
        [TerminalTitleItem.PROJECT, TerminalTitleItem.SPINNER, TerminalTitleItem.STATUS],
        {"ProjectName": "repo", "Status": "Working"},
    )
    assert preview == "[ ! ] Action Required | repo | Working"


def test_title_setup_view_orders_configured_unique_items_before_disabled_remainder():
    view = TerminalTitleSetupView.new(
        ["project-name", "activity", "project", "run-state", "unknown"],
        {"ProjectName": "repo", "Status": "Ready"},
    )

    assert [item.id for item in view.items[:3]] == ["project-name", "activity", "run-state"]
    assert [item.enabled for item in view.items[:3]] == [True, True, True]
    assert all(isinstance(item, MultiSelectItem) for item in view.items)
    assert view.items[0].description == TerminalTitleItem.PROJECT.description()


def test_title_select_item_uses_rate_limit_preview_names_and_descriptions():
    preview_data = {
        "FiveHourLimit.name": "5h remaining",
        "FiveHourLimit.description": "primary quota",
    }
    item = TerminalTitleSetupView.title_select_item(TerminalTitleItem.FIVE_HOUR_LIMIT, True, preview_data)
    assert item.id == "five-hour-limit"
    assert item.name == "5h remaining"
    assert item.description == "primary quota"
    assert item.enabled
    assert item.orderable


def test_confirm_and_cancel_emit_semantic_events():
    view = TerminalTitleSetupView.new(["project-name"], {"ProjectName": "repo"})
    assert view.preview() == "repo"
    view.confirm()
    assert view.is_complete()
    assert view.emitted_events == [{"type": "TerminalTitleSetup", "items": [TerminalTitleItem.PROJECT]}]

    cancelled = TerminalTitleSetupView.new([], {})
    assert cancelled.on_ctrl_c() == "Handled"
    assert cancelled.emitted_events == [{"type": "TerminalTitleSetupCancelled"}]
