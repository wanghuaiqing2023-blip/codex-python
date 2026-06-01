"""Execution policy helpers for command approval decisions.

Ported from the policy-independent parts of
``codex/codex-rs/core/src/exec_policy.rs``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pycodex.core.tool_sandboxing import ExecApprovalRequirement
from pycodex.protocol import (
    AskForApproval,
    ExecPolicyAmendment,
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
BANNED_PREFIX_SUGGESTIONS = (
    ("python3",),
    ("python3", "-"),
    ("python3", "-c"),
    ("python",),
    ("python", "-"),
    ("python", "-c"),
    ("py",),
    ("py", "-3"),
    ("pythonw",),
    ("pyw",),
    ("pypy",),
    ("pypy3",),
    ("git",),
    ("bash",),
    ("bash", "-lc"),
    ("sh",),
    ("sh", "-c"),
    ("sh", "-lc"),
    ("zsh",),
    ("zsh", "-lc"),
    ("/bin/zsh",),
    ("/bin/zsh", "-lc"),
    ("/bin/bash",),
    ("/bin/bash", "-lc"),
    ("pwsh",),
    ("pwsh", "-Command"),
    ("pwsh", "-c"),
    ("powershell",),
    ("powershell", "-Command"),
    ("powershell", "-c"),
    ("powershell.exe",),
    ("powershell.exe", "-Command"),
    ("powershell.exe", "-c"),
    ("env",),
    ("sudo",),
    ("node",),
    ("node", "-e"),
    ("perl",),
    ("perl", "-e"),
    ("ruby",),
    ("ruby", "-e"),
    ("php",),
    ("php", "-r"),
    ("lua",),
    ("lua", "-e"),
    ("osascript",),
)


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


@dataclass(frozen=True)
class ExecApprovalRequest:
    command: tuple[str, ...]
    approval_policy: AskForApproval | GranularApprovalConfig
    permission_profile: PermissionProfile
    file_system_sandbox_policy: FileSystemSandboxPolicy
    sandbox_cwd: Path
    sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT
    prefix_rule: tuple[str, ...] | None = None
    matched_rules: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _commands_tuple((self.command,))[0])
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be PermissionProfile")
        if not isinstance(self.file_system_sandbox_policy, FileSystemSandboxPolicy):
            raise TypeError("file_system_sandbox_policy must be FileSystemSandboxPolicy")
        if not isinstance(self.sandbox_cwd, Path):
            object.__setattr__(self, "sandbox_cwd", Path(self.sandbox_cwd))
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(self.sandbox_permissions))
        if self.prefix_rule is not None:
            object.__setattr__(self, "prefix_rule", _commands_tuple((self.prefix_rule,))[0])
        object.__setattr__(self, "matched_rules", tuple(self.matched_rules))


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
    enable_shell_wrapper_parsing: bool = True,
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


def create_exec_approval_requirement_for_command(
    request: ExecApprovalRequest | Mapping[str, object],
) -> ExecApprovalRequirement:
    if not isinstance(request, ExecApprovalRequest):
        request = ExecApprovalRequest(**dict(request))  # type: ignore[arg-type]
    parsed = commands_for_exec_policy(request.command)
    auto_amendment_allowed = not parsed.used_complex_parsing
    fallback_context = UnmatchedCommandContext(
        approval_policy=request.approval_policy,
        permission_profile=request.permission_profile,
        file_system_sandbox_policy=request.file_system_sandbox_policy,
        sandbox_cwd=request.sandbox_cwd,
        sandbox_permissions=request.sandbox_permissions,
        used_complex_parsing=parsed.used_complex_parsing,
        command_origin=parsed.command_origin,
    )
    fallback_decisions = tuple(render_decision_for_unmatched_command(command, fallback_context) for command in parsed.commands)
    policy_decisions = tuple(
        decision
        for rule in request.matched_rules
        for decision in (_policy_match_decision(rule),)
        if decision is not None
    )
    decisions = fallback_decisions + policy_decisions
    decision = strongest_decision(decisions)
    requested_amendment = (
        derive_requested_execpolicy_amendment_from_prefix_rule(
            request.prefix_rule,
            request.matched_rules,
            parsed.commands,
        )
        if auto_amendment_allowed
        else None
    )

    if decision is Decision.FORBIDDEN:
        return ExecApprovalRequirement.forbidden(derive_forbidden_reason(request.command, request.matched_rules))
    if decision is Decision.PROMPT:
        prompt_is_rule = any(_is_policy_match(rule) for rule in request.matched_rules)
        rejected_reason = prompt_is_rejected_by_policy(request.approval_policy, prompt_is_rule)
        if rejected_reason is not None:
            return ExecApprovalRequirement.forbidden(rejected_reason)
        proposed = requested_amendment
        if proposed is None and auto_amendment_allowed:
            proposed = _first_amendment_for_decision(parsed.commands, fallback_decisions, Decision.PROMPT)
        return ExecApprovalRequirement.needs_approval(
            reason=derive_prompt_reason(request.command, request.matched_rules),
            proposed_execpolicy_amendment=proposed,
        )

    proposed = None
    if auto_amendment_allowed:
        proposed = _first_amendment_for_decision(parsed.commands, fallback_decisions, Decision.ALLOW)
    return ExecApprovalRequirement.skip(proposed_execpolicy_amendment=proposed)


def derive_requested_execpolicy_amendment_from_prefix_rule(
    prefix_rule: Sequence[str] | None,
    matched_rules: Sequence[object] = (),
    commands: Sequence[Sequence[str]] | None = None,
) -> ExecPolicyAmendment | None:
    if prefix_rule is None:
        return None
    prefix = _commands_tuple((prefix_rule,))[0]
    if not prefix:
        return None
    if prefix in BANNED_PREFIX_SUGGESTIONS:
        return None
    if any(_is_policy_match(rule) for rule in matched_rules):
        return None
    candidate_commands = commands if commands is not None else (prefix,)
    if not prefix_rule_would_approve_all_commands(prefix, candidate_commands):
        return None
    return ExecPolicyAmendment.new(list(prefix))


def prefix_rule_would_approve_all_commands(
    prefix_rule: Sequence[str],
    commands: Sequence[Sequence[str]],
) -> bool:
    prefix = _commands_tuple((prefix_rule,))[0]
    if not prefix:
        return False
    command_tuples = _commands_tuple(commands)
    return all(_command_starts_with(command, prefix) for command in command_tuples)


def derive_prompt_reason(command: Sequence[str], matched_rules: Sequence[object]) -> str | None:
    prompt_matches = tuple(
        match
        for rule in matched_rules
        for match in (_prefix_rule_match(rule),)
        if match is not None and match.get("decision") == Decision.PROMPT.value
    )
    if not prompt_matches:
        return None
    match = max(prompt_matches, key=lambda item: len(_matched_prefix(item)))
    justification = match.get("justification")
    rendered = _render_command(command)
    if isinstance(justification, str) and justification:
        return f"`{rendered}` requires approval: {justification}"
    return f"`{rendered}` requires approval by policy"


def derive_forbidden_reason(command: Sequence[str], matched_rules: Sequence[object]) -> str:
    forbidden_matches = tuple(
        match
        for rule in matched_rules
        for match in (_prefix_rule_match(rule),)
        if match is not None and match.get("decision") == Decision.FORBIDDEN.value
    )
    rendered = _render_command(command)
    if not forbidden_matches:
        return f"`{rendered}` rejected: blocked by policy"
    match = max(forbidden_matches, key=lambda item: len(_matched_prefix(item)))
    justification = match.get("justification")
    if isinstance(justification, str) and justification:
        return f"`{rendered}` rejected: {justification}"
    prefix = _render_command(_matched_prefix(match))
    return f"`{rendered}` rejected: policy forbids commands starting with `{prefix}`"


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


def _command_starts_with(command: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return len(command) >= len(prefix) and command[: len(prefix)] == prefix


def _is_policy_match(rule: object) -> bool:
    if _prefix_rule_match(rule) is not None:
        return True
    kind = getattr(rule, "kind", None) or getattr(rule, "type", None)
    if kind in {"prefix_rule", "PrefixRuleMatch", "prefixRuleMatch"}:
        return True
    return rule.__class__.__name__ in {"PrefixRuleMatch", "PrefixRule"}


def _policy_match_decision(rule: object) -> Decision | None:
    match = _prefix_rule_match(rule)
    if match is None:
        decision = getattr(rule, "decision", None)
    else:
        decision = match.get("decision")
    try:
        return Decision(str(decision))
    except ValueError:
        return None


def _prefix_rule_match(rule: object) -> Mapping[str, object] | None:
    if isinstance(rule, Mapping):
        for key in ("prefixRuleMatch", "prefix_rule_match"):
            value = rule.get(key)
            if isinstance(value, Mapping):
                return value
        kind = rule.get("kind") or rule.get("type") or rule.get("rule_type")
        if kind in {"prefix_rule", "PrefixRuleMatch", "prefixRuleMatch"}:
            return rule
    for attr in ("prefixRuleMatch", "prefix_rule_match"):
        value = getattr(rule, attr, None)
        if isinstance(value, Mapping):
            return value
    kind = getattr(rule, "kind", None) or getattr(rule, "type", None)
    if kind in {"prefix_rule", "PrefixRuleMatch", "prefixRuleMatch"}:
        return _object_policy_match_mapping(rule)
    return None


def _object_policy_match_mapping(rule: object) -> Mapping[str, object]:
    data: dict[str, object] = {}
    for attr in ("matchedPrefix", "matched_prefix", "decision", "justification"):
        value = getattr(rule, attr, None)
        if value is not None:
            data[attr] = value
    return data


def _matched_prefix(match: Mapping[str, object]) -> tuple[str, ...]:
    value = match.get("matchedPrefix")
    if value is None:
        value = match.get("matched_prefix")
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return ()


def _first_amendment_for_decision(
    commands: Sequence[Sequence[str]],
    decisions: Sequence[Decision],
    decision: Decision,
) -> ExecPolicyAmendment | None:
    for command, command_decision in zip(commands, decisions, strict=False):
        if command_decision is decision:
            return ExecPolicyAmendment.new(list(command))
    return None


def _render_command(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


__all__ = [
    "BANNED_PREFIX_SUGGESTIONS",
    "Decision",
    "ExecPolicyCommandOrigin",
    "ExecPolicyCommands",
    "ExecApprovalRequest",
    "PROMPT_CONFLICT_REASON",
    "REJECT_RULES_APPROVAL_REASON",
    "REJECT_SANDBOX_APPROVAL_REASON",
    "UnmatchedCommandContext",
    "commands_for_exec_policy",
    "commands_for_intercepted_exec_policy",
    "create_exec_approval_requirement_for_command",
    "derive_forbidden_reason",
    "derive_prompt_reason",
    "derive_requested_execpolicy_amendment_from_prefix_rule",
    "exec_approval_requirement_for_decision",
    "prefix_rule_would_approve_all_commands",
    "profile_is_managed_read_only",
    "prompt_is_rejected_by_policy",
    "render_decision_for_unmatched_command",
    "render_decisions_for_intercepted_exec_policy",
    "render_intercepted_exec_policy_decision",
    "strongest_decision",
]
