"""Permission profile menu construction for chat widgets.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/permissions_menu.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .._porting import RustTuiModule
from ..app_event import PermissionProfileSelection
from ..bottom_pane.list_selection_view import SelectionItem, SelectionViewParams

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::permissions_menu",
    source="codex/codex-rs/tui/src/chatwidget/permissions_menu.rs",
)

AUTO_REVIEW_DESCRIPTION = (
    "Same workspace-write permissions as Default, but eligible `on-request` approvals "
    "are routed through the auto-reviewer subagent."
)


@dataclass(frozen=True)
class ApprovalPreset:
    id: str
    label: str
    description: str
    approval: str
    permission_profile: str


@dataclass(frozen=True)
class CustomPermissionProfileSummary:
    id: str
    description: str | None = None


@dataclass(frozen=True)
class PermissionMenuAction:
    kind: str
    selection: PermissionProfileSelection
    return_to_permissions: bool = False


@dataclass
class PermissionMenuConfig:
    active_profile_id: str | None = None
    approval_policy: str = "on-request"
    approvals_reviewer: str = "user"
    guardian_approval_enabled: bool = False
    custom_permission_profiles: tuple[CustomPermissionProfileSummary, ...] = ()
    disabled_reasons: dict[str, str] = field(default_factory=dict)


@dataclass
class PermissionMenuResult:
    view: SelectionViewParams | None = None
    errors: list[str] = field(default_factory=list)


def builtin_approval_presets() -> list[ApprovalPreset]:
    return [
        ApprovalPreset(
            id="read-only",
            label="Read Only",
            description="Can read files and answer questions. Cannot edit files or run commands.",
            approval="on-request",
            permission_profile="read-only",
        ),
        ApprovalPreset(
            id="auto",
            label="Default",
            description="Can read files, edit files, and run commands in the workspace. (Identical to Agent mode)",
            approval="on-request",
            permission_profile="workspace-write",
        ),
        ApprovalPreset(
            id="full-access",
            label="Full Access",
            description="Can read files, edit files, and run commands with no sandbox.",
            approval="on-request",
            permission_profile="danger-full-access",
        ),
    ]


def open_permission_profiles_popup(
    config: PermissionMenuConfig,
    presets: Iterable[ApprovalPreset] | None = None,
) -> PermissionMenuResult:
    preset_list = list(builtin_approval_presets() if presets is None else presets)
    by_id = {preset.id: preset for preset in preset_list}

    missing = _first_missing_required_preset(by_id)
    if missing is not None:
        return PermissionMenuResult(
            errors=[f"Internal error: missing the '{missing}' approval preset."]
        )

    read_only = by_id["read-only"]
    default = by_id["auto"]
    full_access = by_id["full-access"]

    items = [
        builtin_permission_mode_selection_item(
            config,
            default,
            ":workspace",
            default.description.replace(" (Identical to Agent mode)", ""),
            default.approval,
            "user",
        )
    ]
    if config.guardian_approval_enabled:
        items.append(
            builtin_permission_mode_selection_item(
                config,
                default,
                ":workspace",
                AUTO_REVIEW_DESCRIPTION,
                "on-request",
                "auto-review",
            )
        )
    items.append(
        builtin_permission_mode_selection_item(
            config,
            full_access,
            ":danger-no-sandbox",
            full_access.description,
            full_access.approval,
            "user",
        )
    )
    items.append(
        builtin_permission_mode_selection_item(
            config,
            read_only,
            ":read-only",
            read_only.description,
            read_only.approval,
            "user",
        )
    )
    items.extend(
        permission_profile_selection_item(
            profile.id,
            profile.id,
            profile.description or "Configured permission profile.",
            config.active_profile_id,
        )
        for profile in config.custom_permission_profiles
    )

    return PermissionMenuResult(
        view=SelectionViewParams(
            title="Update Model Permissions",
            footer_hint="standard-popup-hint",
            items=items,
            header=(),
        )
    )


def builtin_permission_mode_selection_item(
    config: PermissionMenuConfig,
    preset: ApprovalPreset,
    id: str,
    description: str,
    approval_policy: str,
    approvals_reviewer: str,
) -> SelectionItem:
    label = "Auto-review" if approvals_reviewer == "auto-review" else preset.label
    selection = PermissionProfileSelection(
        profile_id=id,
        approval_policy=approval_policy,
        approvals_reviewer=approvals_reviewer,
        display_label=label,
    )
    return SelectionItem(
        name=label,
        description=description,
        is_current=(
            config.active_profile_id == id
            and config.approval_policy == approval_policy
            and config.approvals_reviewer == approvals_reviewer
        ),
        actions=permission_mode_actions(preset, label, approvals_reviewer, selection, True),
        dismiss_on_select=True,
        disabled_reason=config.disabled_reasons.get(id) or config.disabled_reasons.get(preset.id),
    )


def permission_profile_selection_item(
    label: str,
    id: str,
    description: str,
    active_profile_id: str | None,
) -> SelectionItem:
    selection = PermissionProfileSelection(
        profile_id=id,
        approval_policy=None,
        approvals_reviewer=None,
        display_label=id,
    )
    return SelectionItem(
        name=label,
        description=description,
        is_current=active_profile_id == id,
        actions=permission_profile_selection_actions(selection),
        dismiss_on_select=True,
    )


def permission_profile_selection_actions(
    selection: PermissionProfileSelection,
) -> list[PermissionMenuAction]:
    return [PermissionMenuAction(kind="select_permission_profile", selection=selection)]


def permission_mode_actions(
    _preset: ApprovalPreset,
    _label: str,
    _approvals_reviewer: str,
    profile_selection: PermissionProfileSelection | None,
    return_to_permissions: bool,
) -> list[PermissionMenuAction]:
    if profile_selection is None:
        raise NotImplementedError(
            "approval preset actions without a PermissionProfileSelection are outside permissions_menu"
        )
    return [
        PermissionMenuAction(
            kind="select_permission_profile",
            selection=profile_selection,
            return_to_permissions=return_to_permissions,
        )
    ]


def _first_missing_required_preset(by_id: dict[str, ApprovalPreset]) -> str | None:
    for required in ("read-only", "auto", "full-access"):
        if required not in by_id:
            return required
    return None


__all__ = [
    "AUTO_REVIEW_DESCRIPTION",
    "ApprovalPreset",
    "CustomPermissionProfileSummary",
    "PermissionMenuAction",
    "PermissionMenuConfig",
    "PermissionMenuResult",
    "RUST_MODULE",
    "builtin_approval_presets",
    "builtin_permission_mode_selection_item",
    "open_permission_profiles_popup",
    "permission_mode_actions",
    "permission_profile_selection_actions",
    "permission_profile_selection_item",
]
