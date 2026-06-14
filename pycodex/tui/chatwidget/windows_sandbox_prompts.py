"""Windows sandbox prompts and warning surfaces for ``ChatWidget``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/windows_sandbox_prompts.rs``.

Rust builds ratatui selection views and dispatches AppEvents from closures.  The
Python port represents those prompts as semantic prompt/action plans.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::windows_sandbox_prompts", source="codex/codex-rs/tui/src/chatwidget/windows_sandbox_prompts.rs")


WINDOWS_SANDBOX_LEARN_MORE_URL = "https://developers.openai.com/codex/windows"


@dataclass(frozen=True)
class PromptItemPlan:
    name: str
    description: str | None
    actions: tuple[str, ...]
    dismiss_on_select: bool = True


@dataclass(frozen=True)
class PromptPlan:
    header_lines: tuple[str, ...]
    items: tuple[PromptItemPlan, ...]
    footer_hint: str | None = "standard_popup_hint_line"
    title: str | None = None


def describe_permission_profile(profile: Any, *, cwd_writable: bool | None = None) -> str:
    text = str(getattr(profile, "value", getattr(profile, "name", profile))).lower()
    if "disabled" in text or "full" in text:
        return "Full Access mode"
    if cwd_writable is True or "workspace" in text or "agent" in text:
        return "Agent mode"
    return "Read-Only mode"


def world_writable_warning_details(
    config: Any,
    *,
    is_windows: bool = False,
    scan_failed: bool = False,
    sample_paths: list[str] | None = None,
    extra_count: int = 0,
) -> tuple[list[str], int, bool] | None:
    if not is_windows:
        return None
    notices = getattr(config, "notices", None)
    if bool(getattr(notices, "hide_world_writable_warning", False)):
        return None
    if not scan_failed:
        return None
    return (sample_paths or [], extra_count, True)


def world_writable_warning_confirmation_plan(
    *,
    mode_label: str,
    sample_paths: list[str] | None = None,
    extra_count: int = 0,
    failed_scan: bool = False,
    preset: Any | None = None,
    profile_selection: Any | None = None,
) -> PromptPlan:
    if failed_scan:
        header = (
            "We couldn't complete the world-writable scan, so protections cannot be verified. "
            f"The Windows sandbox cannot guarantee protection in {mode_label}.",
        )
    else:
        header = (
            "The Windows sandbox cannot protect writes to folders that are writable by Everyone.",
            "Consider removing write access for Everyone from the following folders:",
        )
    if sample_paths:
        header += ("",)
        header += tuple(f"  - {path}" for path in sample_paths)
        if extra_count > 0:
            header += (f"and {extra_count} more",)

    continue_actions = []
    if preset is not None:
        continue_actions.append("skip_next_world_writable_scan")
    if profile_selection is not None:
        continue_actions.append("apply_permission_profile_selection")
    elif preset is not None:
        continue_actions.append("apply_approval_preset")

    remember_actions = [
        "update_world_writable_warning_acknowledged",
        "persist_world_writable_warning_acknowledged",
    ]
    if profile_selection is not None:
        remember_actions.append("apply_permission_profile_selection")
    elif preset is not None:
        remember_actions.append("apply_approval_preset")

    return PromptPlan(
        header_lines=header,
        items=(
            PromptItemPlan(
                name="Continue",
                description=f"Apply {mode_label} for this session",
                actions=tuple(continue_actions),
            ),
            PromptItemPlan(
                name="Continue and don't warn again",
                description=f"Enable {mode_label} and remember this choice",
                actions=tuple(remember_actions),
            ),
        ),
    )


def windows_sandbox_enable_prompt_plan(
    *,
    elevated_nux_enabled: bool,
) -> PromptPlan:
    if not elevated_nux_enabled:
        return PromptPlan(
            header_lines=(
                "Agent mode on Windows uses an experimental sandbox to limit network and filesystem access.",
                f"Learn more: {WINDOWS_SANDBOX_LEARN_MORE_URL}",
            ),
            items=(
                PromptItemPlan("Enable experimental sandbox", None, ("enable_windows_sandbox_legacy",)),
                PromptItemPlan("Go back", None, ("open_approvals_popup",)),
            ),
            title=None,
        )
    return PromptPlan(
        header_lines=(
            "Set up the Codex agent sandbox to protect your files and control network access. "
            f"Learn more <{WINDOWS_SANDBOX_LEARN_MORE_URL}>",
        ),
        items=(
            PromptItemPlan(
                "Set up default sandbox (requires Administrator permissions)",
                None,
                ("telemetry_elevated_prompt_accept", "begin_windows_sandbox_elevated_setup"),
            ),
            PromptItemPlan(
                "Use non-admin sandbox (higher risk if prompt injected)",
                None,
                ("telemetry_elevated_prompt_use_legacy", "begin_windows_sandbox_legacy_setup"),
            ),
            PromptItemPlan(
                "Quit",
                None,
                ("telemetry_elevated_prompt_quit", "exit_shutdown_first"),
            ),
        ),
        title=None,
    )


def windows_sandbox_fallback_prompt_plan() -> PromptPlan:
    return PromptPlan(
        header_lines=(
            "Couldn't set up your sandbox with Administrator permissions",
            "",
            "You can still use Codex in a non-admin sandbox. It carries greater risk if prompt injected.",
            f"Learn more <{WINDOWS_SANDBOX_LEARN_MORE_URL}>",
        ),
        items=(
            PromptItemPlan(
                "Try setting up admin sandbox again",
                None,
                ("telemetry_fallback_retry_elevated", "begin_windows_sandbox_elevated_setup"),
            ),
            PromptItemPlan(
                "Use Codex with non-admin sandbox",
                None,
                ("telemetry_fallback_use_legacy", "begin_windows_sandbox_legacy_setup"),
            ),
            PromptItemPlan(
                "Quit",
                None,
                ("telemetry_fallback_prompt_quit", "exit_shutdown_first"),
            ),
        ),
        title=None,
    )


def maybe_prompt_windows_sandbox_enable(
    *,
    show_now: bool,
    windows_sandbox_level: str,
    has_auto_preset: bool,
) -> bool:
    return bool(show_now and windows_sandbox_level.lower() == "disabled" and has_auto_preset)


def windows_sandbox_setup_status_plan() -> tuple[str, ...]:
    return (
        "disable_composer_input",
        "ensure_status_indicator",
        "hide_interrupt_hint",
        "set_status_setting_up_sandbox",
        "request_redraw",
    )


def clear_windows_sandbox_setup_status_plan() -> tuple[str, ...]:
    return ("enable_composer_input", "hide_status_indicator", "request_redraw")


__all__ = [
    "PromptItemPlan",
    "PromptPlan",
    "RUST_MODULE",
    "WINDOWS_SANDBOX_LEARN_MORE_URL",
    "clear_windows_sandbox_setup_status_plan",
    "describe_permission_profile",
    "maybe_prompt_windows_sandbox_enable",
    "windows_sandbox_enable_prompt_plan",
    "windows_sandbox_fallback_prompt_plan",
    "windows_sandbox_setup_status_plan",
    "world_writable_warning_confirmation_plan",
    "world_writable_warning_details",
]
