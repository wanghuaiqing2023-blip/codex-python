from __future__ import annotations

from .fragment import ContextualUserFragmentBase


class LegacyApplyPatchExecCommandWarning(ContextualUserFragmentBase):
    @classmethod
    def matches_text(cls, text: str) -> bool:
        trimmed = text.strip()
        return trimmed.startswith("Warning: apply_patch was requested via ") and trimmed.endswith(
            "Use the apply_patch tool instead of exec_command."
        )


__all__ = ["LegacyApplyPatchExecCommandWarning"]
