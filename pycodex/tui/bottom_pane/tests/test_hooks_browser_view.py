"""Parity tests for codex-rs/tui/src/bottom_pane/hooks_browser_view.rs."""

from pycodex.tui.bottom_pane.hooks_browser_view import (
    HookMetadata,
    HookSource,
    HookTrustStatus,
    HooksBrowserPage,
    HooksBrowserView,
    hook,
    hook_is_active,
    review_needed_message,
)


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
    view.state.selected_idx = 9

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
    view.state.selected_idx = 2
    view.handle_key_event("enter")

    view.handle_key_event(" ")

    assert sent == [{"type": "SetHookEnabled", "key": "plugin:superpowers", "enabled": False}]
    assert view.entry.hooks[0].enabled is False


def test_space_does_not_toggle_managed_or_review_needed_handlers():
    managed = hook("path:managed", "PreToolUse", is_managed=True, enabled=True)
    review_needed = hook("path:untrusted", "PreToolUse", enabled=True, display_order=1)
    review_needed.trust_status = HookTrustStatus.UNTRUSTED.value
    view = HooksBrowserView.new([managed, review_needed], [], [])
    view.state.selected_idx = 2
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
    view.state.selected_idx = 2
    view.handle_key_event("enter")

    view.handle_key_event("t")

    assert review_needed.enabled is False
    assert review_needed.trust_status == HookTrustStatus.TRUSTED.value
    assert view.emitted_events == [
        {"type": "TrustHook", "key": "path:modified", "current_hash": "sha256:current"}
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
    assert "! skipped invalid matcher for PreToolUse" in lines
    assert "x /tmp/hooks.json: failed to parse hooks config" in lines
    assert lines[-1] == "Press Enter to view hooks; Esc to close"

    view.state.selected_idx = 2
    view.handle_key_event("enter")
    assert "No hooks installed for this event." in view.render_lines(width=112)


def test_helper_messages_and_ctrl_c_match_bottom_pane_boundaries():
    view = HooksBrowserView.new([HookMetadata(key="path:k", event_name="PreToolUse")], [], [])

    assert review_needed_message(0) is None
    assert review_needed_message(1) == "1 hook need review before they can run."
    assert view.prefer_esc_to_handle_key_event() is True
    assert view.on_ctrl_c() == "handled"
    assert view.is_complete() is True
