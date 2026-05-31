"""Execution policy helpers for command approval decisions.

Ported from the policy-independent parts of
``codex/codex-rs/core/src/exec_policy.rs``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pycodex.core.tool_sandboxing import ExecApprovalRequirement
from pycodex.protocol import (
    AskForApproval,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    PermissionProfile,
    SandboxPermissions,
)
from pycodex.shell_command import (
    command_might_be_dangerous,
    is_dangerous_powershell_words,
    is_known_safe_command,
    is_safe_powershell_words,
    parse_powershell_command_into_plain_commands,
    parse_shell_lc_plain_commands,
    parse_shell_lc_single_command_prefix,
)

PROMPT_CONFLICT_REASON = "approval required by policy, but AskForApproval is set to Never"
REJECT_SANDBOX_APPROVAL_REASON = "approval required by policy, but AskForApproval::Granular.sandbox_approval is false"
REJECT_RULES_APPROVAL_REASON = "approval required by policy rule, but AskForApproval::Granular.rules is false"


class Decision(str, Enum):
    ALLOW = "allow"
    PROMPT = "prompt"
    FORBIDDEN = "forbidden"


_DECISION_RANK = {
    Decision.ALLOW: 0,
    Decision.PROMPT: 1,
    Decision.FORBIDDEN: 2,
}


class ExecPolicyCommandOrigin(str, Enum):
    GENERIC = "generic"
    POWERSHELL = "powershell"


@dataclass(frozen=True)
class UnmatchedCommandContext:
    approval_policy: AskForApproval | GranularApprovalConfig
    permission_profile: PermissionProfile
    file_system_sandbox_policy: FileSystemSandboxPolicy
    sandbox_cwd: Path
    sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT
    used_complex_parsing: bool = False
    command_origin: ExecPolicyCommandOrigin = ExecPolicyCommandOrigin.GENERIC

    def __post_init__(self) -> None:
        if not isinstance(self.sandbox_cwd, Path):
            object.__setattr__(self, "sandbox_cwd", Path(self.sandbox_cwd))
        if not isinstance(self.command_origin, ExecPolicyCommandOrigin):
            object.__setattr__(self, "command_origin", ExecPolicyCommandOrigin(str(self.command_origin)))


@dataclass(frozen=True)
class ExecPolicyCommands:
    commands: tuple[tuple[str, ...], ...]
    used_complex_parsing: bool
    command_origin: ExecPolicyCommandOrigin


def prompt_is_rejected_by_policy(
    approval_policy: AskForApproval | GranularApprovalConfig,
    prompt_is_rule: bool,
) -> str | None:
    if approval_policy is AskForApproval.NEVER:
        return PROMPT_CONFLICT_REASON
    if isinstance(approval_policy, GranularApprovalConfig):
        if prompt_is_rule:
            return None if approval_policy.allows_rules_approval() else REJECT_RULES_APPROVAL_REASON
        return None if approval_policy.allows_sandbox_approval() else REJECT_SANDBOX_APPROVAL_REASON
    return None


def commands_for_exec_policy(command: Sequence[str]) -> ExecPolicyCommands:
    argv = tuple(str(item) for item in command)

    plain_commands = parse_shell_lc_plain_commands(argv)
    if _has_nonempty_commands(plain_commands):
        return ExecPolicyCommands(_commands_tuple(plain_commands), False, ExecPolicyCommandOrigin.GENERIC)

    if os.name == "nt":
        powershell_commands = parse_powershell_command_into_plain_commands(argv)
        if _has_nonempty_commands(powershell_commands):
            return ExecPolicyCommands(_commands_tuple(powershell_commands), False, ExecPolicyCommandOrigin.POWERSHELL)

    single_command = parse_shell_lc_single_command_prefix(argv)
    if single_command is not None:
        return ExecPolicyCommands((tuple(single_command),), True, ExecPolicyCommandOrigin.GENERIC)

    return ExecPolicyCommands((argv,), False, ExecPolicyCommandOrigin.GENERIC)


def commands_for_intercepted_exec_policy(
    program: str | Path,
    argv: Sequence[str],
    *,
    enable_shell_wrapper_parsing: bool,
) -> ExecPolicyCommands:
    if enable_shell_wrapper_parsing:
        from pycodex.core.tool_runtimes import commands_for_intercepted_exec_policy as runtime_candidates

        candidate = runtime_candidates(program, tuple(str(item) for item in argv))
        return ExecPolicyCommands(candidate.commands, candidate.used_complex_parsing, ExecPolicyCommandOrigin.GENERIC)
    joined = (str(program), *tuple(str(item) for item in argv)[1:])
    return ExecPolicyCommands((joined,), False, ExecPolicyCommandOrigin.GENERIC)


def render_decisions_for_intercepted_exec_policy(
    program: str | Path,
    argv: Sequence[str],
    context: UnmatchedCommandContext,
    *,
    enable_shell_wrapper_parsing: bool,
) -> tuple[Decision, ...]:
    commands = commands_for_intercepted_exec_policy(
        program,
        argv,
        enable_shell_wrapper_parsing=enable_shell_wrapper_parsing,
    )
    fallback_context = UnmatchedCommandContext(
        approval_policy=context.approval_policy,
        permission_profile=context.permission_profile,
        file_system_sandbox_policy=context.file_system_sandbox_policy,
        sandbox_cwd=context.sandbox_cwd,
        sandbox_permissions=context.sandbox_permissions,
        used_complex_parsing=commands.used_complex_parsing,
        command_origin=ExecPolicyCommandOrigin.GENERIC,
    )
    return tuple(render_decision_for_unmatched_command(command, fallback_context) for command in commands.commands)


def strongest_decision(decisions: Sequence[Decision | str]) -> Decision:
    normalized = tuple(Decision(decision) for decision in decisions)
    if not normalized:
        raise ValueError("decisions must not be empty")
    return max(normalized, key=lambda decision: _DECISION_RANK[decision])


def render_intercepted_exec_policy_decision(
    program: str | Path,
    argv: Sequence[str],
    context: UnmatchedCommandContext,
    *,
    enable_shell_wrapper_parsing: bool,
) -> Decision:
    return strongest_decision(
        render_decisions_for_intercepted_exec_policy(
            program,
            argv,
            context,
            enable_shell_wrapper_parsing=enable_shell_wrapper_parsing,
        )
    )


def exec_approval_requirement_for_decision(
    decision: Decision | str,
    *,
    forbidden_reason: str,
    prompt_reason: str | None = None,
) -> ExecApprovalRequirement:
    decision = Decision(decision)
    if decision is Decision.FORBIDDEN:
        return ExecApprovalRequirement.forbidden(forbidden_reason)
    if decision is Decision.PROMPT:
        return ExecApprovalRequirement.needs_approval(reason=prompt_reason)
    return ExecApprovalRequirement.skip()


def render_decision_for_unmatched_command(
    command: Sequence[str],
    context: UnmatchedCommandContext,
) -> Decision:
    argv = tuple(str(item) for item in command)
    if context.command_origin is ExecPolicyCommandOrigin.POWERSHELL:
        known_safe = is_safe_powershell_words(argv)
    else:
        known_safe = is_known_safe_command(argv)

    environment_lacks_sandbox_protections = (
        os.name == "nt"
        and profile_is_managed_read_only(
            context.permission_profile,
            context.file_system_sandbox_policy,
            context.sandbox_cwd,
        )
    )

    if known_safe and not context.used_complex_parsing and (
        context.approval_policy is AskForApproval.UNLESS_TRUSTED or environment_lacks_sandbox_protections
    ):
        return Decision.ALLOW

    if context.command_origin is ExecPolicyCommandOrigin.POWERSHELL:
        command_is_dangerous = is_dangerous_powershell_words(argv)
    else:
        command_is_dangerous = command_might_be_dangerous(argv)

    if command_is_dangerous or environment_lacks_sandbox_protections:
        if context.approval_policy is AskForApproval.NEVER:
            if context.permission_profile.type in {"disabled", "external"}:
                return Decision.ALLOW
            return Decision.FORBIDDEN
        return Decision.PROMPT

    if context.approval_policy in {AskForApproval.NEVER, AskForApproval.ON_FAILURE}:
        return Decision.ALLOW
    if context.approval_policy is AskForApproval.UNLESS_TRUSTED:
        return Decision.PROMPT

    if context.file_system_sandbox_policy.kind in {
        FileSystemSandboxKind.UNRESTRICTED,
        FileSystemSandboxKind.EXTERNAL_SANDBOX,
    }:
        return Decision.ALLOW
    if context.sandbox_permissions.requests_sandbox_override():
        return Decision.PROMPT
    return Decision.ALLOW


def profile_is_managed_read_only(
    permission_profile: PermissionProfile,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    sandbox_cwd: Path | str,
) -> bool:
    return (
        permission_profile.type == "managed"
        and file_system_sandbox_policy.kind is FileSystemSandboxKind.RESTRICTED
        and not file_system_sandbox_policy.has_full_disk_write_access()
        and len(file_system_sandbox_policy.get_writable_roots_with_cwd(sandbox_cwd)) == 0
    )


def _has_nonempty_commands(commands: list[list[str]] | None) -> bool:
    return commands is not None and bool(commands) and all(bool(item) for item in commands)


def _commands_tuple(commands: Sequence[Sequence[str]] | None) -> tuple[tuple[str, ...], ...]:
    if commands is None:
        return ()
    return tuple(tuple(str(item) for item in command) for command in commands)


__all__ = [
    "Decision",
    "ExecPolicyCommandOrigin",
    "ExecPolicyCommands",
    "PROMPT_CONFLICT_REASON",
    "REJECT_RULES_APPROVAL_REASON",
    "REJECT_SANDBOX_APPROVAL_REASON",
    "UnmatchedCommandContext",
    "commands_for_exec_policy",
    "commands_for_intercepted_exec_policy",
    "exec_approval_requirement_for_decision",
    "profile_is_managed_read_only",
    "prompt_is_rejected_by_policy",
    "render_decision_for_unmatched_command",
    "render_decisions_for_intercepted_exec_policy",
    "render_intercepted_exec_policy_decision",
    "strongest_decision",
]
