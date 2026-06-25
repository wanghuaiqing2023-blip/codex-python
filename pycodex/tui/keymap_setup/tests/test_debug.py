"""Parity tests for Rust ``codex-tui::keymap_setup::debug``.

Rust source: ``codex/codex-rs/tui/src/keymap_setup/debug.rs``.
"""

from pycodex.tui.keymap_setup.debug import (
    DELAYED_MISSING_KEY_HINT,
    MISSING_KEY_HINT_DELAY,
    SHORT_MISSING_KEY_HINT,
    build_keymap_debug_view,
    key_event_debug_summary,
    key_modifiers_debug_label,
)


def test_initial_and_delayed_missing_key_hints() -> None:
    now = 100.0
    view = build_keymap_debug_view({}, {}, clock=lambda: now)

    lines = view.lines_at(80, now)
    assert "Keypress Inspector" in lines[0]
    assert SHORT_MISSING_KEY_HINT in lines
    assert "Waiting for a keypress..." in lines
    assert view.should_show_delayed_hint(now + MISSING_KEY_HINT_DELAY - 0.1) is False
    assert view.should_show_delayed_hint(now + MISSING_KEY_HINT_DELAY) is True
    assert DELAYED_MISSING_KEY_HINT in " ".join(view.lines_at(120, now + MISSING_KEY_HINT_DELAY))


def test_handle_key_event_ignores_release_and_reports_detected_key() -> None:
    view = build_keymap_debug_view({}, {}, clock=lambda: 0.0)

    view.handle_key_event({"code": "x", "kind": "release"})
    assert view.last_report is None

    view.handle_key_event({"code": "x", "modifiers": {"control", "shift"}, "kind": "press"})
    assert view.last_report is not None
    assert view.last_report.detected.display_label() == "ctrl+shift+x"
    assert view.last_report.config_key == "ctrl+shift+x"
    assert "code='x', modifiers=ctrl|shift, kind=Press" == view.last_report.raw_event


def test_debug_view_reports_matching_actions_and_none_state() -> None:
    view = build_keymap_debug_view({"matches": {"ctrl+x": [
        {
            "context": "global",
            "action": "interrupt",
            "label": "Interrupt",
            "description": "Stop current task",
            "source": {"label": "custom"},
        }
    ]}}, {})

    view.handle_key_event({"code": "x", "modifiers": {"control"}})
    lines = view.lines(120)
    assert "Detected: ctrl+x" in lines
    assert "Config key: ctrl+x" in lines
    assert "Assigned actions:" in lines
    assert any("global.interrupt (Interrupt) - Stop current task [custom]" in line for line in lines)

    empty = build_keymap_debug_view({}, {})
    empty.handle_key_event({"code": "z"})
    assert "  none" in empty.lines(80)


def test_view_completion_ctrl_c_esc_preference_and_next_frame_delay() -> None:
    now = 10.0
    view = build_keymap_debug_view({}, {}, clock=lambda: now)
    assert view.is_complete() is False
    assert view.prefer_esc_to_handle_key_event() is True
    assert view.next_frame_delay() == MISSING_KEY_HINT_DELAY

    assert view.on_ctrl_c() == "handled"
    assert view.is_complete() is True

    view.handle_key_event({"code": "esc"})
    assert view.next_frame_delay() is None


def test_key_debug_helpers_format_modifiers_in_rust_order() -> None:
    assert key_modifiers_debug_label(set()) == "none"
    assert key_modifiers_debug_label({"shift", "control", "alt"}) == "ctrl|alt|shift"
    assert key_event_debug_summary({"code": "enter", "modifiers": {"alt"}, "kind": "repeat"}) == "code='enter', modifiers=alt, kind=Repeat"

def test_unsupported_config_key_is_reported_as_wrapped_error_text() -> None:
    view = build_keymap_debug_view({}, {})

    view.handle_key_event({"code": None})

    assert view.last_report is not None
    assert isinstance(view.last_report.config_key, Exception)
    assert any(line.startswith("Config key: unsupported -") for line in view.lines(80))


def test_callable_matcher_and_plain_source_are_rendered_like_debug_matches() -> None:
    def matcher(event):
        assert event["code"] == "k"
        return [
            {
                "context": "editor",
                "action": "move_up",
                "label": "Move Up",
                "description": "Move cursor up",
                "source": "default",
            }
        ]

    view = build_keymap_debug_view({"matching_actions_for_key_event": matcher}, {})

    view.handle_key_event({"code": "k"})

    assert any("editor.move_up (Move Up) - Move cursor up [default]" in line for line in view.lines(120))

