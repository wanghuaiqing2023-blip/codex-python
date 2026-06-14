"""Behavior port for Rust ``codex-tui::collaboration_modes``.

Upstream source: ``codex/codex-rs/tui/src/collaboration_modes.rs``.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Union

from pycodex.models_manager import builtin_collaboration_mode_presets
from pycodex.protocol import CollaborationModeMask, ModeKind

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="collaboration_modes",
    source="codex/codex-rs/tui/src/collaboration_modes.rs",
)


def _preset_mode(mask: Any) -> Optional[ModeKind]:
    mode = mask.get("mode") if isinstance(mask, dict) else getattr(mask, "mode", None)
    if mode is None:
        return None
    return mode if isinstance(mode, ModeKind) else ModeKind.parse(str(mode))


def _clone_mask(mask: CollaborationModeMask) -> CollaborationModeMask:
    if hasattr(mask, "__dataclass_fields__"):
        return CollaborationModeMask(
            name=mask.name,
            mode=mask.mode,
            model=mask.model,
            reasoning_effort=mask.reasoning_effort,
            developer_instructions=mask.developer_instructions,
        )
    return mask


def _is_tui_visible(mode: Optional[ModeKind]) -> bool:
    return mode is not None and mode.is_tui_visible()


def filtered_presets(
    model_catalog: Any = None,
    presets: Optional[Sequence[CollaborationModeMask]] = None,
) -> List[CollaborationModeMask]:
    """Return builtin collaboration mode presets whose mode is TUI-visible.

    Rust currently ignores ``ModelCatalog`` here.  Python preserves that
    parameter for call-shape parity and allows ``presets`` injection for
    behavior tests.
    """

    source = builtin_collaboration_mode_presets() if presets is None else list(presets)
    return [_clone_mask(mask) for mask in source if _is_tui_visible(_preset_mode(mask))]


def default_mask(
    model_catalog: Any = None,
    presets: Optional[Sequence[CollaborationModeMask]] = None,
) -> Optional[CollaborationModeMask]:
    visible = filtered_presets(model_catalog, presets=presets)
    for mask in visible:
        if _preset_mode(mask) is ModeKind.DEFAULT:
            return _clone_mask(mask)
    return _clone_mask(visible[0]) if visible else None


def mask_for_kind(
    model_catalog: Any,
    kind: Union[ModeKind, str],
    presets: Optional[Sequence[CollaborationModeMask]] = None,
) -> Optional[CollaborationModeMask]:
    mode_kind = kind if isinstance(kind, ModeKind) else ModeKind.parse(str(kind))
    if not mode_kind.is_tui_visible():
        return None
    for mask in filtered_presets(model_catalog, presets=presets):
        if _preset_mode(mask) is mode_kind:
            return _clone_mask(mask)
    return None


def next_mask(
    model_catalog: Any = None,
    current: Optional[CollaborationModeMask] = None,
    presets: Optional[Sequence[CollaborationModeMask]] = None,
) -> Optional[CollaborationModeMask]:
    """Cycle to the next collaboration mode preset in list order."""

    visible = filtered_presets(model_catalog, presets=presets)
    if not visible:
        return None
    current_kind = None if current is None else _preset_mode(current)
    next_index = 0
    for idx, mask in enumerate(visible):
        if _preset_mode(mask) == current_kind:
            next_index = (idx + 1) % len(visible)
            break
    return _clone_mask(visible[next_index])


def default_mode_mask(
    model_catalog: Any = None,
    presets: Optional[Sequence[CollaborationModeMask]] = None,
) -> Optional[CollaborationModeMask]:
    return mask_for_kind(model_catalog, ModeKind.DEFAULT, presets=presets)


def plan_mask(
    model_catalog: Any = None,
    presets: Optional[Sequence[CollaborationModeMask]] = None,
) -> Optional[CollaborationModeMask]:
    return mask_for_kind(model_catalog, ModeKind.PLAN, presets=presets)


def make_mask(name: str, mode: Optional[Union[ModeKind, str]]) -> CollaborationModeMask:
    parsed_mode = None if mode is None else (mode if isinstance(mode, ModeKind) else ModeKind.parse(str(mode)))
    return CollaborationModeMask(name=name, mode=parsed_mode)


__all__ = [
    "RUST_MODULE",
    "default_mask",
    "default_mode_mask",
    "filtered_presets",
    "make_mask",
    "mask_for_kind",
    "next_mask",
    "plan_mask",
]
