"""Parity tests for codex-rs/tui/src/bottom_pane/hooks_browser_view.rs."""

from pathlib import Path

from pycodex.tui.bottom_pane.hooks_browser_view import (
    COUNT_COLUMN_WIDTH,
    EVENT_COLUMN_WIDTH,
    HOOK_EVENT_ORDER,
    HookMetadata,
    HookSource,
    HookTrustStatus,
    HooksBrowserPage,
    HooksBrowserView,
    event_description,
    event_label,
    hook,
    hook_is_active,
    review_needed_message,
)
from pycodex.tui.ratatui_bridge import Color as RatatuiColor
from pycodex.tui.ratatui_bridge import Modifier as RatatuiModifier
from pycodex.tui.app_event import AppEvent
from pycodex.tui.app_event_sender import AppEventSender


def test_event_rows_count_installed_active_and_review_needed_hooks():
    trusted = hook("path:trusted", "PreToolUse", enabled=True)
    managed = hook(
        "path:managed",
        "PreToolUse",
        source=HookSource.SYSTEM.value,
        enabled=True,
        is_managed=True,
        display_order=1,
    )
    untrusted = hook("path:untrusted", "PreToolUse", enabled=True, display_order=2)
    untrusted.trust_status = HookTrustStatus.UNTRUSTED.value

    view = HooksBrowserView.new([managed, untrusted, trusted], [], [])
    row = next(row for row in view.event_rows() if row.event_name == "PreToolUse")

    assert row.installed == 3
    assert row.active == 2
    assert row.needs_review == 1
    assert hook_is_active(untrusted) is False


def test_review_needed_event_is_selected_by_default():
    untrusted = hook("path:untrusted", "PermissionRequest", enabled=False)
    untrusted.trust_status = HookTrustStatus.UNTRUSTED.value

    view = HooksBrowserView.new([untrusted], [], [])

    assert view.selected_event() == "PermissionRequest"


def test_enter_opens_handlers_and_escape_returns_to_selected_event():
    view = HooksBrowserView.new([hook("path:trusted", "PermissionRequest")], [], [])
    view.state.selected_idx = 1

    view.handle_key_event("enter")

    assert view.page == HooksBrowserPage.HANDLERS
    assert view.page_event == "PermissionRequest"
    assert view.state.selected_idx == 0

    view.handle_key_event("esc")

    assert view.page == HooksBrowserPage.EVENTS
    assert view.selected_event() == "PermissionRequest"


def test_toggle_unmanaged_handler_emits_set_enabled_event():
    sent = []
    view = HooksBrowserView.new(
        [hook("plugin:superpowers", "PreToolUse", source="Plugin", plugin_id="superpowers", enabled=True)],
        [],
        [],
        app_event_tx=sent.append,
    )
    view.state.selected_idx = 0
    view.handle_key_event("enter")

    view.handle_key_event(" ")

    assert sent == [{"type": "SetHookEnabled", "key": "plugin:superpowers", "enabled": False}]
    assert view.entry.hooks[0].enabled is False


def test_space_does_not_toggle_managed_or_review_needed_handlers():
    managed = hook("path:managed", "PreToolUse", is_managed=True, enabled=True)
    review_needed = hook("path:untrusted", "PreToolUse", enabled=True, display_order=1)
    review_needed.trust_status = HookTrustStatus.UNTRUSTED.value
    view = HooksBrowserView.new([managed, review_needed], [], [])
    view.state.selected_idx = 0
    view.handle_key_event("enter")

    view.handle_key_event(" ")
    view.move_down()
    view.handle_key_event(" ")

    assert view.emitted_events == []
    assert managed.enabled is True
    assert review_needed.enabled is True


def test_trust_selected_hook_preserves_enablement_and_emits_trust_event():
    review_needed = hook("path:modified", "PreToolUse", enabled=False)
    review_needed.trust_status = HookTrustStatus.MODIFIED.value
    review_needed.current_hash = "sha256:current"
    view = HooksBrowserView.new([review_needed], [], [])
    view.state.selected_idx = 0
    view.handle_key_event("enter")

    view.handle_key_event("t")

    assert review_needed.enabled is False
    assert review_needed.trust_status == HookTrustStatus.TRUSTED.value
    assert view.emitted_events == [
        {"type": "TrustHook", "key": "path:modified", "current_hash": "sha256:current"}
    ]


def test_trust_selected_hook_sends_typed_app_event_to_product_bus():
    queued = []
    review_needed = hook("path:modified", "PreToolUse", enabled=False)
    review_needed.trust_status = HookTrustStatus.MODIFIED.value
    review_needed.current_hash = "sha256:current"
    view = HooksBrowserView.new(
        [review_needed],
        [],
        [],
        AppEventSender(queued.append),
    )
    view.handle_key_event("enter")

    view.handle_key_event("t")

    assert queued == [
        AppEvent.of(
            "TrustHook",
            key="path:modified",
            current_hash="sha256:current",
        )
    ]


def test_trust_all_hooks_only_emits_review_needed_updates():
    untrusted = hook("path:untrusted", "PreToolUse", enabled=False)
    untrusted.trust_status = HookTrustStatus.UNTRUSTED.value
    modified = hook("path:modified", "Stop", enabled=False, display_order=1)
    modified.trust_status = HookTrustStatus.MODIFIED.value
    trusted = hook("path:trusted", "PreToolUse", enabled=True, display_order=2)
    view = HooksBrowserView.new([untrusted, modified, trusted], [], [])

    view.handle_key_event("t")

    assert [hook.trust_status for hook in view.entry.hooks] == [
        HookTrustStatus.TRUSTED.value,
        HookTrustStatus.TRUSTED.value,
        HookTrustStatus.TRUSTED.value,
    ]
    assert view.emitted_events == [
        {
            "type": "TrustHooks",
            "updates": [
                {"key": "path:untrusted", "current_hash": "sha256:current"},
                {"key": "path:modified", "current_hash": "sha256:current"},
            ],
        }
    ]


def test_render_lines_include_issues_footer_and_empty_handler_detail():
    view = HooksBrowserView.new(
        [],
        ["skipped invalid matcher for PreToolUse"],
        [{"path": "/tmp/hooks.json", "message": "failed to parse hooks config"}],
    )

    lines = view.render_lines(width=112)

    assert "Issues" in lines
    assert "⚠ skipped invalid matcher for PreToolUse" in lines
    assert "■ /tmp/hooks.json: failed to parse hooks config" in lines
    assert lines[-1] == "Press enter to view hooks; esc to close"

    view.state.selected_idx = 0
    view.handle_key_event("enter")
    assert "No hooks installed for this event." in view.render_lines(width=112)


def test_helper_messages_and_ctrl_c_match_bottom_pane_boundaries():
    view = HooksBrowserView.new([HookMetadata(key="path:k", event_name="PreToolUse")], [], [])

    assert review_needed_message(0) is None
    assert review_needed_message(1) == "1 hook needs review before it can run."
    assert view.prefer_esc_to_handle_key_event() is True
    assert view.on_ctrl_c() == "handled"
    assert view.is_complete() is True


def test_rust_hook_event_labels_descriptions_order_and_fixed_columns():
    """Port Rust event_label, event_description, and event_table_lines."""

    expected = (
        ("PreToolUse", "Before a tool executes"),
        ("PermissionRequest", "When permission is requested"),
        ("PostToolUse", "After a tool executes"),
        ("PreCompact", "Before context compaction"),
        ("PostCompact", "After context compaction"),
        ("SessionStart", "When a new session starts"),
        ("UserPromptSubmit", "When the user submits a prompt"),
        ("SubagentStart", "When a subagent is created"),
        ("SubagentStop", "Right before a subagent ends its turn"),
        ("Stop", "Right before Codex ends its turn"),
    )
    view = HooksBrowserView.new([], [], [])

    assert HOOK_EVENT_ORDER == tuple(event for event, _description in expected)
    assert tuple(
        (event_label(event), event_description(event)) for event in HOOK_EVENT_ORDER
    ) == expected
    assert view.event_table_lines() == [
        f"{'Event':<{EVENT_COLUMN_WIDTH}}"
        f"{'Installed':<{COUNT_COLUMN_WIDTH}}"
        f"{'Active':<{COUNT_COLUMN_WIDTH}}Description",
        *[
            f"{event:<{EVENT_COLUMN_WIDTH}}"
            f"{0:<{COUNT_COLUMN_WIDTH}}"
            f"{0:<{COUNT_COLUMN_WIDTH}}{description}"
            for event, description in expected
        ],
    ]
    assert all("|" not in line and not line.startswith("> ") for line in view.event_table_lines())


def test_terminal_event_page_uses_rust_inset_and_span_styles():
    """Port Rust event_header_lines and selected event row styling."""

    view = HooksBrowserView.new([], [], [])
    lines = view.terminal_lines(width=112)

    assert lines[0].text == "  Hooks"
    assert RatatuiModifier.BOLD in lines[0].spans[1].style.modifiers
    assert lines[0].spans[1].style.fg is None
    assert RatatuiModifier.DIM in lines[1].spans[1].style.modifiers

    selected = next(line for line in lines if line.text.lstrip().startswith("PreToolUse"))
    assert not selected.text.lstrip().startswith("> ")
    assert all(span.style.fg == RatatuiColor.Cyan for span in selected.spans[1:])
    assert all(RatatuiModifier.BOLD in span.style.modifiers for span in selected.spans[1:])

    ordinary = next(
        line for line in lines if line.text.lstrip().startswith("PermissionRequest")
    )
    assert ordinary.spans[1].style.fg is None
    assert RatatuiModifier.DIM in ordinary.spans[2].style.modifiers
    assert RatatuiModifier.DIM in ordinary.spans[-1].style.modifiers
    assert lines[-1].text == "  Press enter to view hooks; esc to close"
    assert RatatuiModifier.DIM in lines[-1].spans[1].style.modifiers


def test_review_column_and_warning_styles_follow_rust_contract():
    """Port Rust renders_event_browser_with_review_column_when_needed."""

    untrusted = hook("path:untrusted", "PreToolUse", enabled=False)
    untrusted.trust_status = HookTrustStatus.UNTRUSTED.value
    view = HooksBrowserView.new([untrusted], [], [])
    view.move_down()
    lines = view.terminal_lines(width=112)

    warning = next(line for line in lines if "1 hook needs review" in line.text)
    assert warning.spans[1].style.fg == RatatuiColor.Yellow
    header = next(line for line in lines if "Installed" in line.text)
    assert header.text.lstrip() == (
        f"{'Event':<{EVENT_COLUMN_WIDTH}}"
        f"{'Installed':<{COUNT_COLUMN_WIDTH}}"
        f"{'Active':<{COUNT_COLUMN_WIDTH}}"
        f"{'Review':<{COUNT_COLUMN_WIDTH}}Description"
    )
    row = next(line for line in lines if line.text.lstrip().startswith("PreToolUse"))
    assert row.spans[4].content.strip() == "1"
    assert row.spans[4].style.fg == RatatuiColor.Yellow
    assert view.render_footer() == "Press t to trust all; enter to review hooks; esc to close"


def test_handler_rows_details_sources_trust_and_styles_match_rust():
    """Port Rust hooks_browser_handlers and detail helper snapshots."""

    metadata = hook(
        "plugin:superpowers",
        "preToolUse",
        source="plugin",
        plugin_id="superpowers@openai-curated",
        command="${CODEX_PLUGIN_ROOT}/hooks/pre-tool-use-check.sh",
    )
    metadata.matcher = "Bash"
    metadata.timeout_sec = 30
    metadata.source_path = Path("/tmp/hooks.json")
    view = HooksBrowserView.new([metadata], [], [])
    view.handle_key_event("enter")

    assert view.handler_row_lines("PreToolUse", 112) == ["[x] Hook 1"]
    assert view.detail_lines("PreToolUse", 112) == [
        "Event     PreToolUse",
        "Matcher   Bash",
        "Source    Plugin - superpowers@openai-curated",
        "Command   ${CODEX_PLUGIN_ROOT}/hooks/pre-tool-use-check.sh",
        "Timeout   30s",
        "Trust     Trusted",
    ]
    lines = view.terminal_lines(width=112)
    row = next(line for line in lines if "[x] Hook 1" in line.text)
    assert row.spans[1].style.fg == RatatuiColor.Cyan
    assert RatatuiModifier.BOLD in row.spans[1].style.modifiers
    source = next(line for line in lines if "Plugin - superpowers" in line.text)
    assert source.spans[1].content == "Source    "
    assert RatatuiModifier.DIM in source.spans[2].style.modifiers
    assert view.render_footer() == "Press space or enter to toggle; esc to go back"


def test_review_handler_and_source_trust_labels_match_rust():
    metadata = hook("path:modified", "PreToolUse", source="user", enabled=True)
    metadata.trust_status = HookTrustStatus.MODIFIED.value
    metadata.source_path = Path("/tmp/hooks.json")
    view = HooksBrowserView.new([metadata], [], [])
    view.handle_key_event("enter")

    assert view.handler_row_lines("PreToolUse", 112) == ["[!] Hook 1 · modified"]
    assert "Source    User config - " in "\n".join(view.detail_lines("PreToolUse", 112))
    assert "Trust     Modified since last trusted - review required" in view.detail_lines(
        "PreToolUse", 112
    )
    assert view.render_footer() == "Press t to trust; esc to go back"
    row = next(line for line in view.terminal_lines(width=112) if "[!] Hook 1" in line.text)
    assert row.spans[1].style.fg == RatatuiColor.Yellow
    assert RatatuiModifier.BOLD in row.spans[1].style.modifiers


def test_handler_navigation_keeps_selection_visible_and_home_end_work():
    hooks = [
        hook(f"path:{index}", "PreToolUse", display_order=index)
        for index in range(10)
    ]
    view = HooksBrowserView.new(hooks, [], [])
    view.handle_key_event("enter")

    for _ in range(9):
        view.handle_key_event("down")
    assert view.state.selected_idx == 9
    assert view.state.scroll_top == 2

    view.handle_key_event("g")
    assert view.state.selected_idx == 0
    assert view.state.scroll_top == 0
    view.handle_key_event("G")
    assert view.state.selected_idx == 9
    assert view.state.scroll_top == 2
    visible_rows = [line for line in view.terminal_lines(width=112) if "Hook " in line.text]
    assert len(visible_rows) == 8
    assert any("Hook 10" in line.text for line in visible_rows)


def test_desired_height_reserves_rust_menu_surface_and_footer_rows():
    view = HooksBrowserView.new([], [], [])
    assert view.desired_height(112) == len(view.event_page_lines()) + 3

    view.handle_key_event("enter")
    # Two header rows, one blank row, one empty-state row, then the menu
    # surface's trailing inset and footer reservation.
    assert view.desired_height(112) == 7
