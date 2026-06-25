from pycodex.tui.bottom_pane.status_line_setup import (
    STATUS_LINE_USE_THEME_COLORS_ITEM_ID,
    StatusLineItem,
    StatusLineSetupView,
    line_text,
    parse_status_line_items,
)
from pycodex.tui.bottom_pane.status_surface_preview import StatusSurfacePreviewData, StatusSurfacePreviewItem


def test_status_line_item_canonical_and_legacy_ids():
    assert str(StatusLineItem.CONTEXT_USED) == "context-used"
    assert StatusLineItem.parse("context-used") is StatusLineItem.CONTEXT_USED
    assert StatusLineItem.parse("context-usage") is StatusLineItem.CONTEXT_USED
    assert str(StatusLineItem.PROJECT_ROOT) == "project-name"
    assert StatusLineItem.parse("project") is StatusLineItem.PROJECT_ROOT
    assert StatusLineItem.parse("project-root") is StatusLineItem.PROJECT_ROOT
    assert str(StatusLineItem.MODEL_NAME) == "model"
    assert StatusLineItem.parse("model-name") is StatusLineItem.MODEL_NAME
    assert str(StatusLineItem.STATUS) == "run-state"
    assert StatusLineItem.parse("status") is StatusLineItem.STATUS
    assert StatusLineItem.parse("approval") is StatusLineItem.APPROVAL_MODE
    assert StatusLineItem.parse("session-id") is StatusLineItem.SESSION_ID


def test_git_and_title_only_items_are_parseable():
    assert StatusLineItem.parse("pull-request-number") is StatusLineItem.PULL_REQUEST_NUMBER
    assert StatusLineItem.parse("branch-changes") is StatusLineItem.BRANCH_CHANGES
    assert StatusLineItem.parse("context-remaining") is StatusLineItem.CONTEXT_REMAINING
    assert str(StatusLineItem.CONTEXT_REMAINING) == "context-remaining"
    assert parse_status_line_items(["run-state", "task-progress"]) == [StatusLineItem.STATUS, StatusLineItem.TASK_PROGRESS]


def test_all_status_line_items_have_rust_descriptions_and_preview_items():
    expected_preview_items = {
        StatusLineItem.MODEL_NAME: StatusSurfacePreviewItem.MODEL,
        StatusLineItem.MODEL_WITH_REASONING: StatusSurfacePreviewItem.MODEL_WITH_REASONING,
        StatusLineItem.CURRENT_DIR: StatusSurfacePreviewItem.CURRENT_DIR,
        StatusLineItem.PROJECT_ROOT: StatusSurfacePreviewItem.PROJECT_ROOT,
        StatusLineItem.GIT_BRANCH: StatusSurfacePreviewItem.GIT_BRANCH,
        StatusLineItem.PULL_REQUEST_NUMBER: StatusSurfacePreviewItem.PULL_REQUEST_NUMBER,
        StatusLineItem.BRANCH_CHANGES: StatusSurfacePreviewItem.BRANCH_CHANGES,
        StatusLineItem.STATUS: StatusSurfacePreviewItem.STATUS,
        StatusLineItem.PERMISSIONS: StatusSurfacePreviewItem.PERMISSIONS,
        StatusLineItem.APPROVAL_MODE: StatusSurfacePreviewItem.APPROVAL_MODE,
        StatusLineItem.CONTEXT_REMAINING: StatusSurfacePreviewItem.CONTEXT_REMAINING,
        StatusLineItem.CONTEXT_USED: StatusSurfacePreviewItem.CONTEXT_USED,
        StatusLineItem.FIVE_HOUR_LIMIT: StatusSurfacePreviewItem.FIVE_HOUR_LIMIT,
        StatusLineItem.WEEKLY_LIMIT: StatusSurfacePreviewItem.WEEKLY_LIMIT,
        StatusLineItem.CODEX_VERSION: StatusSurfacePreviewItem.CODEX_VERSION,
        StatusLineItem.CONTEXT_WINDOW_SIZE: StatusSurfacePreviewItem.CONTEXT_WINDOW_SIZE,
        StatusLineItem.USED_TOKENS: StatusSurfacePreviewItem.USED_TOKENS,
        StatusLineItem.TOTAL_INPUT_TOKENS: StatusSurfacePreviewItem.TOTAL_INPUT_TOKENS,
        StatusLineItem.TOTAL_OUTPUT_TOKENS: StatusSurfacePreviewItem.TOTAL_OUTPUT_TOKENS,
        StatusLineItem.SESSION_ID: StatusSurfacePreviewItem.SESSION_ID,
        StatusLineItem.FAST_MODE: StatusSurfacePreviewItem.FAST_MODE,
        StatusLineItem.RAW_OUTPUT: StatusSurfacePreviewItem.RAW_OUTPUT,
        StatusLineItem.THREAD_TITLE: StatusSurfacePreviewItem.THREAD_TITLE,
        StatusLineItem.TASK_PROGRESS: StatusSurfacePreviewItem.TASK_PROGRESS,
    }

    assert set(StatusLineItem.iter()) == set(expected_preview_items)
    for item, preview_item in expected_preview_items.items():
        assert item.preview_item() is preview_item
        assert item.description()


def test_preview_uses_runtime_values_and_placeholders():
    preview = StatusSurfacePreviewData.from_iter([(StatusLineItem.MODEL_NAME.preview_item(), "gpt-5"), (StatusLineItem.CURRENT_DIR.preview_item(), "/repo")])
    text = line_text(preview.status_line_for_items([StatusLineItem.MODEL_NAME, StatusLineItem.CURRENT_DIR], True))
    assert "gpt-5" in text
    assert "/repo" in text
    placeholder_text = line_text(preview.status_line_for_items([StatusLineItem.MODEL_NAME, StatusLineItem.GIT_BRANCH], True))
    assert "gpt-5" in placeholder_text
    assert "feat/awesome-feature" in placeholder_text


def test_preview_includes_thread_title():
    preview = StatusSurfacePreviewData.from_iter([(StatusLineItem.MODEL_NAME.preview_item(), "gpt-5"), (StatusLineItem.THREAD_TITLE.preview_item(), "Roadmap cleanup")])
    text = line_text(preview.status_line_for_items([StatusLineItem.MODEL_NAME, StatusLineItem.THREAD_TITLE], True))
    assert "gpt-5" in text
    assert "Roadmap cleanup" in text


def test_setup_view_orders_configured_items_first_dedupes_and_adds_theme_toggle():
    preview = StatusSurfacePreviewData.from_iter([(StatusLineItem.MODEL_NAME.preview_item(), "gpt-5-codex")])
    view = StatusLineSetupView.new(["model-name", "current-dir", "model", "unknown"], True, preview, [], None)
    assert view.picker.items[0].id == STATUS_LINE_USE_THEME_COLORS_ITEM_ID
    assert view.picker.items[0].enabled is True
    assert [item.id for item in view.picker.items[1:3]] == ["model", "current-dir"]
    assert [item.id for item in view.picker.items].count("model") == 1
    assert view.picker.ordering_enabled is True


def test_rate_limit_select_item_uses_runtime_copy():
    preview = StatusSurfacePreviewData.from_iter([(StatusLineItem.FIVE_HOUR_LIMIT.preview_item(), "5h 82% left")])
    item = StatusLineSetupView.status_line_select_item(StatusLineItem.FIVE_HOUR_LIMIT, True, preview)
    assert item.id == "five-hour-limit"
    assert item.enabled is True
    assert "limit" in item.name
    assert item.description


def test_confirm_sends_status_line_setup_and_cancel_sends_cancelled():
    events = []
    view = StatusLineSetupView.new(["model", "current-dir"], False, StatusSurfacePreviewData(), events, None)
    view.picker.items[0].enabled = True
    view.picker.confirm_selection()
    assert events[-1]["type"] == "StatusLineSetup"
    assert events[-1]["items"] == [StatusLineItem.MODEL_NAME, StatusLineItem.CURRENT_DIR]
    assert events[-1]["use_theme_colors"] is True
    assert view.is_complete()
    cancel_events = []
    cancel_view = StatusLineSetupView.new(None, True, StatusSurfacePreviewData(), cancel_events, None)
    assert cancel_view.on_ctrl_c() == "Handled"
    assert cancel_events[-1] == {"type": "StatusLineSetupCancelled"}
    assert cancel_view.is_complete()


def test_render_lines_uses_runtime_preview_values():
    preview = StatusSurfacePreviewData.from_iter([(StatusLineItem.MODEL_NAME.preview_item(), "gpt-5-codex"), (StatusLineItem.CURRENT_DIR.preview_item(), "~/codex-rs"), (StatusLineItem.GIT_BRANCH.preview_item(), "jif/statusline-preview")])
    view = StatusLineSetupView.new(["model", "current-dir", "git-branch"], True, preview, [], None)
    rendered = view.render_lines(72)
    assert "Configure Status Line" in rendered
    assert "gpt-5-codex" in rendered
    assert "~/codex-rs" in rendered
    assert "jif/statusline-preview" in rendered
