"""TUI application command model.

Upstream source: ``codex/codex-rs/tui/src/app_command.rs``.
Rust represents app commands as a large enum with constructor helpers. Python
uses a semantic variant object with the same constructor names and payload keys.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="app_command", source="codex/codex-rs/tui/src/app_command.rs")


@dataclass(frozen=True)
class AppCommand:
    """Semantic equivalent of Rust ``app_command::AppCommand`` variants."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def interrupt(cls) -> "AppCommand":
        return cls("Interrupt")

    @classmethod
    def clean_background_terminals(cls) -> "AppCommand":
        return cls("CleanBackgroundTerminals")

    @classmethod
    def realtime_conversation_start(cls, transport: Any | None, voice: Any | None) -> "AppCommand":
        return cls("RealtimeConversationStart", {"transport": transport, "voice": voice})

    @classmethod
    def realtime_conversation_audio(cls, frame: Any) -> "AppCommand":
        return cls("RealtimeConversationAudio", {"frame": frame})

    @classmethod
    def realtime_conversation_close(cls) -> "AppCommand":
        return cls("RealtimeConversationClose")

    @classmethod
    def run_user_shell_command(cls, command: str) -> "AppCommand":
        return cls("RunUserShellCommand", {"command": command})

    @classmethod
    def user_turn(
        cls,
        items: list[Any],
        cwd: str | Path,
        approval_policy: Any,
        active_permission_profile: Any | None,
        model: str,
        effort: Any | None,
        summary: Any | None,
        service_tier: Any | None,
        final_output_json_schema: Any | None,
        collaboration_mode: Any | None,
        personality: Any | None,
    ) -> "AppCommand":
        return cls(
            "UserTurn",
            {
                "items": list(items),
                "cwd": Path(cwd),
                "approval_policy": approval_policy,
                "approvals_reviewer": None,
                "active_permission_profile": active_permission_profile,
                "model": model,
                "effort": effort,
                "summary": summary,
                "service_tier": service_tier,
                "final_output_json_schema": final_output_json_schema,
                "collaboration_mode": collaboration_mode,
                "personality": personality,
            },
        )

    @classmethod
    def override_turn_context(
        cls,
        cwd: str | Path | None = None,
        approval_policy: Any | None = None,
        approvals_reviewer: Any | None = None,
        permission_profile: Any | None = None,
        active_permission_profile: Any | None = None,
        windows_sandbox_level: Any | None = None,
        model: str | None = None,
        effort: Any | None = None,
        summary: Any | None = None,
        service_tier: Any | None = None,
        collaboration_mode: Any | None = None,
        personality: Any | None = None,
    ) -> "AppCommand":
        return cls(
            "OverrideTurnContext",
            {
                "cwd": None if cwd is None else Path(cwd),
                "approval_policy": approval_policy,
                "approvals_reviewer": approvals_reviewer,
                "permission_profile": permission_profile,
                "active_permission_profile": active_permission_profile,
                "windows_sandbox_level": windows_sandbox_level,
                "model": model,
                "effort": effort,
                "summary": summary,
                "service_tier": service_tier,
                "collaboration_mode": collaboration_mode,
                "personality": personality,
            },
        )

    @classmethod
    def exec_approval(cls, id: str, turn_id: str | None, decision: Any) -> "AppCommand":
        return cls("ExecApproval", {"id": id, "turn_id": turn_id, "decision": decision})

    @classmethod
    def patch_approval(cls, id: str, decision: Any) -> "AppCommand":
        return cls("PatchApproval", {"id": id, "decision": decision})

    @classmethod
    def resolve_elicitation(
        cls,
        server_name: str,
        request_id: Any,
        decision: Any,
        content: Any | None,
        meta: Any | None,
    ) -> "AppCommand":
        return cls(
            "ResolveElicitation",
            {
                "server_name": server_name,
                "request_id": request_id,
                "decision": decision,
                "content": content,
                "meta": meta,
            },
        )

    @classmethod
    def user_input_answer(cls, id: str, response: Any) -> "AppCommand":
        return cls("UserInputAnswer", {"id": id, "response": response})

    @classmethod
    def request_permissions_response(cls, id: str, response: Any) -> "AppCommand":
        return cls("RequestPermissionsResponse", {"id": id, "response": response})

    @classmethod
    def reload_user_config(cls) -> "AppCommand":
        return cls("ReloadUserConfig")

    @classmethod
    def list_skills(cls, cwds: list[str | Path], force_reload: bool) -> "AppCommand":
        return cls("ListSkills", {"cwds": [Path(cwd) for cwd in cwds], "force_reload": force_reload})

    @classmethod
    def compact(cls) -> "AppCommand":
        return cls("Compact")

    @classmethod
    def set_thread_name(cls, name: str) -> "AppCommand":
        return cls("SetThreadName", {"name": name})

    @classmethod
    def shutdown(cls) -> "AppCommand":
        return cls("Shutdown")

    @classmethod
    def thread_rollback(cls, num_turns: int) -> "AppCommand":
        return cls("ThreadRollback", {"num_turns": int(num_turns)})

    @classmethod
    def review(cls, target: Any) -> "AppCommand":
        return cls("Review", {"target": target})

    @classmethod
    def approve_guardian_denied_action(cls, event: Any) -> "AppCommand":
        return cls("ApproveGuardianDeniedAction", {"event": event})

    def is_review(self) -> bool:
        return self.kind == "Review"


def from_(value: AppCommand) -> AppCommand:
    """Mirror Rust ``impl From<&AppCommand> for AppCommand`` clone behavior."""

    if not isinstance(value, AppCommand):
        raise TypeError("value must be AppCommand")
    return AppCommand(value.kind, deepcopy(value.payload))


__all__ = [
    "AppCommand",
    "RUST_MODULE",
    "from_",
]
