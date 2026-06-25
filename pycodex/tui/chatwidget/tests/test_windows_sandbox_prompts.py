from __future__ import annotations

from types import SimpleNamespace

from pycodex.tui.chatwidget.windows_sandbox_prompts import (
    clear_windows_sandbox_setup_status_plan,
    describe_permission_profile,
    maybe_prompt_windows_sandbox_enable,
    maybe_prompt_windows_sandbox_enable_plan,
    windows_sandbox_enable_prompt_plan,
    windows_sandbox_fallback_prompt_plan,
    windows_sandbox_setup_status_plan,
    world_writable_warning_confirmation_plan,
    world_writable_warning_details,
)


def test_describe_permission_profile_matches_rust_labels() -> None:
    assert describe_permission_profile("Disabled") == "Full Access mode"
    assert describe_permission_profile("WorkspaceWrite") == "Agent mode"
    assert describe_permission_profile("ReadOnly") == "Read-Only mode"
    assert describe_permission_profile("Custom", cwd_writable=True) == "Agent mode"


def test_world_writable_warning_details_platform_and_hide_gates() -> None:
    visible = SimpleNamespace(notices=SimpleNamespace(hide_world_writable_warning=False))
    hidden = SimpleNamespace(notices=SimpleNamespace(hide_world_writable_warning=True))

    assert world_writable_warning_details(visible, is_windows=False, scan_failed=True) is None
    assert world_writable_warning_details(hidden, is_windows=True, scan_failed=True) is None
    assert world_writable_warning_details(visible, is_windows=True, scan_failed=False) is None
    assert world_writable_warning_details(
        visible,
        is_windows=True,
        scan_failed=True,
        sample_paths=["C:/tmp"],
        extra_count=2,
    ) == (["C:/tmp"], 2, True)


def test_world_writable_warning_confirmation_actions_and_samples() -> None:
    plan = world_writable_warning_confirmation_plan(
        mode_label="Agent mode",
        sample_paths=["C:/a", "C:/b"],
        extra_count=4,
        failed_scan=False,
        preset=object(),
    )

    assert "writable by Everyone" in plan.header_lines[0]
    assert "  - C:/a" in plan.header_lines
    assert "and 4 more" in plan.header_lines
    assert plan.items[0].actions == ("skip_next_world_writable_scan", "apply_approval_preset")
    assert plan.items[1].actions == (
        "update_world_writable_warning_acknowledged",
        "persist_world_writable_warning_acknowledged",
        "apply_approval_preset",
    )


def test_world_writable_warning_failed_scan_and_profile_selection_branch() -> None:
    # Rust: chatwidget::windows_sandbox_prompts::open_world_writable_warning_confirmation
    # uses the failed-scan warning text and lets profile_selection override preset actions.
    plan = world_writable_warning_confirmation_plan(
        mode_label="Read-Only mode",
        sample_paths=["C:/unsafe"],
        extra_count=0,
        failed_scan=True,
        preset=object(),
        profile_selection=object(),
    )

    assert "couldn't complete the world-writable scan" in plan.header_lines[0]
    assert "Read-Only mode" in plan.header_lines[0]
    assert "  - C:/unsafe" in plan.header_lines
    assert "and 0 more" not in plan.header_lines
    assert plan.items[0].actions == (
        "skip_next_world_writable_scan",
        "apply_permission_profile_selection",
    )
    assert plan.items[1].actions == (
        "update_world_writable_warning_acknowledged",
        "persist_world_writable_warning_acknowledged",
        "apply_permission_profile_selection",
    )


def test_windows_sandbox_enable_prompt_legacy_and_elevated() -> None:
    legacy = windows_sandbox_enable_prompt_plan(elevated_nux_enabled=False)
    elevated = windows_sandbox_enable_prompt_plan(elevated_nux_enabled=True)

    assert legacy.items[0].name == "Enable experimental sandbox"
    assert legacy.items[0].actions == ("enable_windows_sandbox_legacy",)
    assert elevated.items[0].actions == (
        "telemetry_elevated_prompt_accept",
        "begin_windows_sandbox_elevated_setup",
    )
    assert elevated.items[2].actions == ("telemetry_elevated_prompt_quit", "exit_shutdown_first")


def test_windows_sandbox_fallback_prompt_actions() -> None:
    plan = windows_sandbox_fallback_prompt_plan()

    assert plan.items[0].name == "Try setting up admin sandbox again"
    assert plan.items[1].actions == (
        "telemetry_fallback_use_legacy",
        "begin_windows_sandbox_legacy_setup",
    )
    assert plan.items[2].actions == ("telemetry_fallback_prompt_quit", "exit_shutdown_first")


def test_maybe_prompt_and_setup_status_plans() -> None:
    assert maybe_prompt_windows_sandbox_enable(
        show_now=True,
        windows_sandbox_level="Disabled",
        has_auto_preset=True,
    )
    assert not maybe_prompt_windows_sandbox_enable(
        show_now=True,
        windows_sandbox_level="Enabled",
        has_auto_preset=True,
    )
    prompt = maybe_prompt_windows_sandbox_enable_plan(
        show_now=True,
        windows_sandbox_level="Disabled",
        has_auto_preset=True,
        elevated_nux_enabled=False,
    )
    assert prompt is not None
    assert prompt.items[0].name == "Enable experimental sandbox"
    assert maybe_prompt_windows_sandbox_enable_plan(
        show_now=False,
        windows_sandbox_level="Disabled",
        has_auto_preset=True,
        elevated_nux_enabled=True,
    ) is None
    assert windows_sandbox_setup_status_plan() == (
        "disable_composer_input",
        "ensure_status_indicator",
        "hide_interrupt_hint",
        "set_status_setting_up_sandbox",
        "request_redraw",
    )
    assert clear_windows_sandbox_setup_status_plan() == (
        "enable_composer_input",
        "hide_status_indicator",
        "request_redraw",
    )
