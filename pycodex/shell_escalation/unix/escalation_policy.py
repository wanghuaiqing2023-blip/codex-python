"""Policy interface for intercepted exec requests."""

from __future__ import annotations

from pathlib import Path

from .escalate_protocol import EscalationDecision


class EscalationPolicy:
    async def determine_action(
        self,
        file: Path,
        argv: list[str],
        workdir: Path,
    ) -> EscalationDecision:
        raise NotImplementedError(
            "codex-shell-escalation policy decision is not implemented"
        )


__all__ = ["EscalationPolicy"]
