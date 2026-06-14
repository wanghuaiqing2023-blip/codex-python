from pycodex.tui.bottom_pane.status_line_style import line_text
from pycodex.tui.bottom_pane.status_surface_preview import RateLimitPreviewCopy
from pycodex.tui.bottom_pane.status_surface_preview import StatusSurfacePreviewData
from pycodex.tui.bottom_pane.status_surface_preview import StatusSurfacePreviewItem
from pycodex.tui.bottom_pane.status_surface_preview import rate_limit_preview_copy


def test_default_populates_all_rust_placeholders_in_iter_order():
    data = StatusSurfacePreviewData()

    assert StatusSurfacePreviewItem.iter()[0] is StatusSurfacePreviewItem.APP_NAME
    assert StatusSurfacePreviewItem.iter()[-1] is StatusSurfacePreviewItem.TASK_PROGRESS
    assert data.value_for(StatusSurfacePreviewItem.APP_NAME) == "codex"
    assert data.value_for(StatusSurfacePreviewItem.PROJECT_ROOT) == "my-project"
    assert data.value_for(StatusSurfacePreviewItem.MODEL) == "gpt-5.2-codex"
    assert data.value_for(StatusSurfacePreviewItem.MODEL_WITH_REASONING) == "gpt-5.2-codex medium"
    assert data.value_for(StatusSurfacePreviewItem.TASK_PROGRESS) == "Tasks 0/0"


def test_live_values_override_placeholders_and_placeholders_do_not_override_live_values():
    data = StatusSurfacePreviewData.from_iter(
        [
            (StatusSurfacePreviewItem.MODEL, "gpt-live"),
            ("current_dir", "/tmp/repo"),
        ]
    )

    assert data.value_for(StatusSurfacePreviewItem.MODEL) == "gpt-live"
    assert data.live_value_for(StatusSurfacePreviewItem.MODEL) == "gpt-live"
    data.set_placeholder(StatusSurfacePreviewItem.MODEL, "placeholder")
    assert data.value_for(StatusSurfacePreviewItem.MODEL) == "gpt-live"
    data.set_live(StatusSurfacePreviewItem.MODEL, "gpt-new")
    assert data.value_for(StatusSurfacePreviewItem.MODEL) == "gpt-new"
    assert data.value_for(StatusSurfacePreviewItem.CURRENT_DIR) == "/tmp/repo"


def test_suppress_placeholder_only_removes_placeholder_values():
    data = StatusSurfacePreviewData()

    data.suppress_placeholder(StatusSurfacePreviewItem.GIT_BRANCH)
    assert data.value_for(StatusSurfacePreviewItem.GIT_BRANCH) is None

    data.set_live(StatusSurfacePreviewItem.GIT_BRANCH, "main")
    data.suppress_placeholder(StatusSurfacePreviewItem.GIT_BRANCH)
    assert data.value_for(StatusSurfacePreviewItem.GIT_BRANCH) == "main"


def test_rate_limit_preview_copy_prefixes_and_fallbacks():
    assert rate_limit_preview_copy("  secondary usage 25%") == RateLimitPreviewCopy(
        "secondary-usage-limit",
        "Remaining usage on the secondary usage limit (omitted when unavailable)",
    )
    assert rate_limit_preview_copy("usage 75%").name == "usage-limit"
    assert rate_limit_preview_copy("5h 12%").name == "five-hour-limit"
    assert rate_limit_preview_copy("daily 12%").name == "daily-limit"
    assert rate_limit_preview_copy("weekly 12%").name == "weekly-limit"
    assert rate_limit_preview_copy("monthly 12%").name == "monthly-limit"
    assert rate_limit_preview_copy("annual 12%").name == "annual-limit"
    assert rate_limit_preview_copy("primary 12%") is None


def test_rate_limit_item_name_and_description_only_use_live_values():
    data = StatusSurfacePreviewData()

    assert data.rate_limit_item_name(StatusSurfacePreviewItem.FIVE_HOUR_LIMIT, "fallback") == "fallback"
    data.set_live(StatusSurfacePreviewItem.FIVE_HOUR_LIMIT, "5h 0%")
    assert data.rate_limit_item_name(StatusSurfacePreviewItem.FIVE_HOUR_LIMIT, "fallback") == "five-hour-limit"
    assert data.rate_limit_item_description(StatusSurfacePreviewItem.FIVE_HOUR_LIMIT, "fallback").startswith(
        "Remaining usage on the 5-hour"
    )


def test_status_line_for_items_maps_status_items_to_preview_values():
    data = StatusSurfacePreviewData.from_iter(
        [
            (StatusSurfacePreviewItem.MODEL, "gpt-live"),
            (StatusSurfacePreviewItem.CURRENT_DIR, "/repo"),
            (StatusSurfacePreviewItem.GIT_BRANCH, "main"),
        ]
    )

    line = data.status_line_for_items(["ModelName", "CurrentDir", "GitBranch"], True)

    assert line is not None
    assert line_text(line) == "gpt-live 路 /repo 路 main"
    assert line.spans[0].style.fg is not None


def test_status_line_for_items_returns_none_when_all_preview_values_are_absent():
    # Rust source: status_line_for_items filters through value_for and delegates
    # to status_line_from_segments; with no segments the semantic line is absent.
    data = StatusSurfacePreviewData()
    data.suppress_placeholder(StatusSurfacePreviewItem.MODEL)
    data.suppress_placeholder(StatusSurfacePreviewItem.GIT_BRANCH)

    assert data.status_line_for_items(["ModelName", "GitBranch"], True) is None
