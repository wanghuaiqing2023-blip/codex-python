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

    @classmethod
    def parse(cls, raw: object) -> "Decision":
        if isinstance(raw, cls):
            return raw
        try:
            return cls(str(raw))
        except ValueError as exc:
            raise InvalidDecisionError(f"invalid decision: {raw}") from exc


@dataclass(frozen=True)
class TextPosition:
    line: int
    column: int


@dataclass(frozen=True)
class TextRange:
    start: TextPosition
    end: TextPosition


@dataclass(frozen=True)
class ErrorLocation:
    path: str
    range: TextRange


class ExecPolicyError(Exception):
    """Base error for codex-execpolicy parity helpers."""

    def location(self) -> ErrorLocation | None:
        return None

    def with_location(self, location: ErrorLocation) -> "ExecPolicyError":
        return self


class InvalidDecisionError(ExecPolicyError, ValueError):
    """Raised when an exec-policy decision string is not recognized."""


class InvalidPatternError(ExecPolicyError, ValueError):
    def __init__(self, pattern: str) -> None:
        super().__init__(f"invalid pattern element: {pattern}")


class InvalidExampleError(ExecPolicyError, ValueError):
    def __init__(self, example: str) -> None:
        super().__init__(f"invalid example: {example}")


class InvalidRuleError(ExecPolicyError, ValueError):
    def __init__(self, rule: str) -> None:
        super().__init__(f"invalid rule: {rule}")


def _rust_debug_string_list(values: Sequence[str]) -> str:
    import json

    return "[" + ", ".join(json.dumps(str(value), ensure_ascii=False) for value in values) + "]"


class ExampleDidNotMatchError(ExecPolicyError):
    def __init__(
        self,
        rules: Sequence[str],
        examples: Sequence[str],
        location: ErrorLocation | None = None,
    ) -> None:
        self.rules = tuple(str(rule) for rule in rules)
        self.examples = tuple(str(example) for example in examples)
        self._location = location
        super().__init__(
            "expected every example to match at least one rule. rules: "
            f"{_rust_debug_string_list(self.rules)}; unmatched examples: "
            f"{_rust_debug_string_list(self.examples)}"
        )

    def location(self) -> ErrorLocation | None:
        return self._location

    def with_location(self, location: ErrorLocation) -> "ExampleDidNotMatchError":
        if self._location is not None:
            return self
        return ExampleDidNotMatchError(self.rules, self.examples, location)


class ExampleDidMatchError(ExecPolicyError):
    def __init__(
        self,
        rule: str,
        example: str,
        location: ErrorLocation | None = None,
    ) -> None:
        self.rule = str(rule)
        self.example = str(example)
        self._location = location
        super().__init__(f"expected example to not match rule `{self.rule}`: {self.example}")

    def location(self) -> ErrorLocation | None:
        return self._location

    def with_location(self, location: ErrorLocation) -> "ExampleDidMatchError":
        if self._location is not None:
            return self
        return ExampleDidMatchError(self.rule, self.example, location)


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
class ExecPolicyPrefixRule:
    pattern: tuple[str | tuple[str, ...], ...]
    decision: Decision
    justification: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pattern", _prefix_rule_pattern_tuple(self.pattern))
        if not isinstance(self.decision, Decision):
            object.__setattr__(self, "decision", Decision(str(self.decision)))
        if self.justification is not None and not isinstance(self.justification, str):
            raise TypeError("justification must be a string or None")

    @classmethod
    def new(
        cls,
        pattern: Sequence[str | Sequence[str]],
        decision: Decision | str,
        justification: str | None = None,
    ) -> "ExecPolicyPrefixRule":
        return cls(_prefix_rule_pattern_tuple(pattern), Decision(str(decision)), justification)


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
        from pycodex.core.tools.runtimes import commands_for_intercepted_exec_policy as runtime_candidates

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
    from pycodex.core.tools.sandboxing import ExecApprovalRequirement

    decision = Decision(decision)
    if decision is Decision.FORBIDDEN:
        return ExecApprovalRequirement.forbidden(forbidden_reason)
    if decision is Decision.PROMPT:
        return ExecApprovalRequirement.needs_approval(reason=prompt_reason)
    return ExecApprovalRequirement.skip()


def create_exec_approval_requirement_for_command(
    request: ExecApprovalRequest | Mapping[str, object],
) -> ExecApprovalRequirement:
    from pycodex.core.tools.sandboxing import ExecApprovalRequirement

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
        prompt_is_rule = any(_policy_match_decision(rule) is Decision.PROMPT for rule in request.matched_rules)
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
        proposed = _try_derive_execpolicy_amendment_for_allow_rules(request.matched_rules)
    return ExecApprovalRequirement.skip(
        bypass_sandbox=_all_commands_explicitly_allowed_by_policy(parsed.commands, request.matched_rules),
        proposed_execpolicy_amendment=proposed,
    )


def match_exec_policy_rules_for_command(
    command: Sequence[str],
    rules: Sequence[object] = (),
) -> tuple[Mapping[str, object], ...]:
    """Return Rust-shaped prefix rule matches for a shell command."""

    if not rules:
        return ()
    parsed = commands_for_exec_policy(command)
    matches: list[Mapping[str, object]] = []
    seen: set[tuple[tuple[str, ...], str, str | None]] = set()
    for plain_command in parsed.commands:
        for rule in rules:
            match = _exec_policy_prefix_rule_match(rule, plain_command)
            if match is None:
                continue
            key = (
                _matched_prefix(match),
                str(match.get("decision")),
                match.get("justification") if isinstance(match.get("justification"), str) else None,
            )
            if key in seen:
                continue
            seen.add(key)
            matches.append({"prefixRuleMatch": dict(match)})
    return tuple(matches)


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


def _prefix_rule_pattern_tuple(pattern: Sequence[str | Sequence[str]]) -> tuple[str | tuple[str, ...], ...]:
    if not isinstance(pattern, Sequence) or isinstance(pattern, (str, bytes)) or not pattern:
        raise ValueError("prefix rule pattern must be a non-empty sequence")
    parsed: list[str | tuple[str, ...]] = []
    for token in pattern:
        if isinstance(token, str):
            parsed.append(token)
            continue
        if isinstance(token, Sequence) and not isinstance(token, (str, bytes)) and token:
            alternatives = tuple(str(item) for item in token)
            if not all(alternatives):
                raise ValueError("prefix rule alternatives must be non-empty strings")
            parsed.append(alternatives)
            continue
        raise ValueError("prefix rule pattern tokens must be strings or non-empty string sequences")
    return tuple(parsed)


def _exec_policy_prefix_rule_match(rule: object, command: tuple[str, ...]) -> Mapping[str, object] | None:
    prefix_match = _prefix_rule_match(rule)
    if prefix_match is not None:
        prefix = _matched_prefix(prefix_match)
        if prefix and _command_starts_with(command, prefix):
            return prefix_match
        return None
    parsed = _prefix_rule_from_object(rule)
    if parsed is None:
        return None
    pattern, decision, justification = parsed
    prefix = _rule_pattern_matched_prefix(pattern, command)
    if prefix is None:
        return None
    match: dict[str, object] = {"matchedPrefix": list(prefix), "decision": decision.value}
    if justification:
        match["justification"] = justification
    return match


def _prefix_rule_from_object(rule: object) -> tuple[tuple[str | tuple[str, ...], ...], Decision, str | None] | None:
    if isinstance(rule, ExecPolicyPrefixRule):
        return rule.pattern, rule.decision, rule.justification
    if isinstance(rule, Mapping):
        pattern = rule.get("pattern")
        decision = rule.get("decision")
        justification = rule.get("justification")
    else:
        pattern = getattr(rule, "pattern", None)
        decision = getattr(rule, "decision", None)
        justification = getattr(rule, "justification", None)
    if pattern is None or decision is None:
        return None
    try:
        parsed_pattern = _prefix_rule_pattern_tuple(pattern)  # type: ignore[arg-type]
        parsed_decision = Decision(str(getattr(decision, "value", decision)))
    except (TypeError, ValueError):
        return None
    parsed_justification = justification if isinstance(justification, str) and justification else None
    return parsed_pattern, parsed_decision, parsed_justification


def _rule_pattern_matched_prefix(
    pattern: tuple[str | tuple[str, ...], ...],
    command: tuple[str, ...],
) -> tuple[str, ...] | None:
    if len(command) < len(pattern):
        return None
    matched: list[str] = []
    for pattern_token, command_token in zip(pattern, command, strict=False):
        if isinstance(pattern_token, tuple):
            if command_token not in pattern_token:
                return None
            matched.append(command_token)
            continue
        if command_token != pattern_token:
            return None
        matched.append(command_token)
    return tuple(matched)


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


def _all_commands_explicitly_allowed_by_policy(
    commands: Sequence[Sequence[str]],
    matched_rules: Sequence[object],
) -> bool:
    if not commands or not matched_rules:
        return False
    normalized_commands = tuple(tuple(str(part) for part in command) for command in commands)
    for command in normalized_commands:
        command_allowed = False
        for rule in matched_rules:
            match = _prefix_rule_match(rule)
            if match is None:
                continue
            if _policy_match_decision(rule) is not Decision.ALLOW:
                continue
            prefix = _matched_prefix(match)
            if prefix and _command_starts_with(command, prefix):
                command_allowed = True
                break
        if not command_allowed:
            return False
    return True


def _try_derive_execpolicy_amendment_for_allow_rules(
    matched_rules: Sequence[object],
) -> ExecPolicyAmendment | None:
    if any(_prefix_rule_match(rule) is not None for rule in matched_rules):
        return None
    for rule in matched_rules:
        if _policy_match_decision(rule) is not Decision.ALLOW:
            continue
        command = None
        if isinstance(rule, Mapping):
            command = rule.get("command")
        else:
            command = getattr(rule, "command", None)
        if command:
            return ExecPolicyAmendment.new([str(part) for part in command])
    return None


def _render_command(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


__all__ = [
    "BANNED_PREFIX_SUGGESTIONS",
    "Decision",
    "ExecPolicyCommandOrigin",
    "ExecPolicyCommands",
    "ExecPolicyPrefixRule",
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
    "match_exec_policy_rules_for_command",
    "prefix_rule_would_approve_all_commands",
    "profile_is_managed_read_only",
    "prompt_is_rejected_by_policy",
    "render_decision_for_unmatched_command",
    "render_decisions_for_intercepted_exec_policy",
    "render_intercepted_exec_policy_decision",
    "strongest_decision",
]

# Rust parity: codex-execpolicy/src/amend.rs
class AmendError(Exception):
    """Raised when appending an exec policy amendment fails."""


class NetworkRuleProtocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5_TCP = "socks5_tcp"
    SOCKS5_UDP = "socks5_udp"

    @classmethod
    def parse(cls, raw: object) -> "NetworkRuleProtocol":
        value = str(raw)
        if value in ("https_connect", "http-connect"):
            value = "https"
        for protocol in cls:
            if protocol.value == value:
                return protocol
        raise AmendError(
            "invalid network rule: invalid rule: network_rule protocol must be one of "
            f"http, https, socks5_tcp, socks5_udp (got {raw})"
        )

    def as_policy_string(self) -> str:
        return self.value


def normalize_network_rule_host(raw: str) -> str:
    host = str(raw).strip()
    if not host:
        raise AmendError("invalid network rule: invalid rule: network_rule host cannot be empty")
    if "://" in host or "/" in host or "?" in host or "#" in host:
        raise AmendError(
            "invalid network rule: invalid rule: network_rule host must be a hostname or IP literal "
            "(without scheme or path)"
        )

    if host.startswith("["):
        close = host.find("]")
        if close == -1:
            raise AmendError(
                "invalid network rule: invalid rule: network_rule host has an invalid bracketed IPv6 literal"
            )
        inside = host[1:close]
        rest = host[close + 1 :]
        port_ok = rest.startswith(":") and rest[1:].isdigit() and bool(rest[1:])
        if rest and not port_ok:
            raise AmendError(
                f"invalid network rule: invalid rule: network_rule host contains an unsupported suffix: {raw}"
            )
        host = inside
    elif host.count(":") == 1:
        candidate, port = host.rsplit(":", 1)
        if candidate and port and port.isdigit():
            host = candidate

    normalized = host.rstrip(".").strip().lower()
    if not normalized:
        raise AmendError("invalid network rule: invalid rule: network_rule host cannot be empty")
    if "*" in normalized:
        raise AmendError(
            "invalid network rule: invalid rule: network_rule host must be a specific host; wildcards are not allowed"
        )
    if any(ch.isspace() for ch in normalized):
        raise AmendError("invalid network rule: invalid rule: network_rule host cannot contain whitespace")
    return normalized


def _json_policy_string(value: str) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _append_rule_line(policy_path: object, line: str) -> None:
    from pathlib import Path

    path = Path(policy_path)
    parent = path.parent
    if str(parent) in ("", "."):
        raise AmendError(f"policy path has no parent: {path}")
    try:
        parent.mkdir(parents=False, exist_ok=True)
    except OSError as exc:
        raise AmendError(f"failed to create policy directory {parent}: {exc}") from exc

    try:
        contents = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        raise AmendError(f"failed to read policy file {path}: {exc}") from exc

    if any(existing == line for existing in contents.splitlines()):
        return

    try:
        with path.open("a", encoding="utf-8") as handle:
            if contents and not contents.endswith("\n"):
                handle.write("\n")
            handle.write(f"{line}\n")
    except OSError as exc:
        raise AmendError(f"failed to write to policy file {path}: {exc}") from exc


def blocking_append_allow_prefix_rule(policy_path: object, prefix: Sequence[str]) -> None:
    tokens = [str(token) for token in prefix]
    if not tokens:
        raise AmendError("prefix rule requires at least one token")
    pattern = "[" + ", ".join(_json_policy_string(token) for token in tokens) + "]"
    _append_rule_line(policy_path, f'prefix_rule(pattern={pattern}, decision="allow")')


def blocking_append_network_rule(
    policy_path: object,
    host: str,
    protocol: object,
    decision: object,
    justification: str | None = None,
) -> None:
    normalized_host = normalize_network_rule_host(host)
    if justification is not None and not justification.strip():
        raise AmendError("invalid network rule: justification cannot be empty")

    parsed_protocol = protocol if isinstance(protocol, NetworkRuleProtocol) else NetworkRuleProtocol.parse(protocol)
    decision_value = getattr(decision, "value", decision)
    if decision_value == "forbidden":
        decision_text = "deny"
    elif decision_value in ("allow", "prompt"):
        decision_text = str(decision_value)
    else:
        raise AmendError(f"invalid network rule: unknown decision: {decision}")

    args = [
        f"host={_json_policy_string(normalized_host)}",
        f"protocol={_json_policy_string(parsed_protocol.as_policy_string())}",
        f"decision={_json_policy_string(decision_text)}",
    ]
    if justification is not None:
        args.append(f"justification={_json_policy_string(justification)}")
    _append_rule_line(policy_path, "network_rule(" + ", ".join(args) + ")")


try:
    __all__.extend(
        [
            "AmendError",
            "NetworkRuleProtocol",
            "normalize_network_rule_host",
            "blocking_append_allow_prefix_rule",
            "blocking_append_network_rule",
        ]
    )
except NameError:
    __all__ = [
        "AmendError",
        "NetworkRuleProtocol",
        "normalize_network_rule_host",
        "blocking_append_allow_prefix_rule",
        "blocking_append_network_rule",
    ]

# Rust parity: codex-execpolicy/src/executable_name.rs
def executable_lookup_key(raw: str) -> str:
    """Return the exec-policy lookup key for an executable token."""
    import os

    value = str(raw)
    if os.name == "nt":
        lowered = value.lower()
        for suffix in (".exe", ".cmd", ".bat", ".com"):
            if lowered.endswith(suffix):
                return lowered[: -len(suffix)]
        return lowered
    return value


def executable_path_lookup_key(path: object) -> str | None:
    """Return the exec-policy lookup key for the final component of a path."""
    from pathlib import Path

    name = Path(path).name
    if not name:
        return None
    return executable_lookup_key(name)


try:
    __all__.extend(["executable_lookup_key", "executable_path_lookup_key"])
except NameError:
    __all__ = ["executable_lookup_key", "executable_path_lookup_key"]

try:
    __all__.extend(
        [
            "ExecPolicyError",
            "InvalidDecisionError",
            "InvalidPatternError",
            "InvalidExampleError",
            "InvalidRuleError",
            "TextPosition",
            "TextRange",
            "ErrorLocation",
            "ExampleDidNotMatchError",
            "ExampleDidMatchError",
        ]
    )
except NameError:
    __all__ = [
        "ExecPolicyError",
        "InvalidDecisionError",
        "InvalidPatternError",
        "InvalidExampleError",
        "InvalidRuleError",
        "TextPosition",
        "TextRange",
        "ErrorLocation",
        "ExampleDidNotMatchError",
        "ExampleDidMatchError",
    ]

# Rust parity: codex-execpolicy/src/policy.rs direct Policy API slice
@dataclass(frozen=True)
class PatternToken:
    value: str | tuple[str, ...]

    @classmethod
    def single(cls, value: str) -> "PatternToken":
        return cls(str(value))

    @classmethod
    def alts(cls, alternatives: Sequence[str]) -> "PatternToken":
        return cls(tuple(str(item) for item in alternatives))

    def matches(self, token: str) -> bool:
        if isinstance(self.value, tuple):
            return str(token) in self.value
        return str(token) == self.value

    def alternatives(self) -> tuple[str, ...]:
        if isinstance(self.value, tuple):
            return self.value
        return (self.value,)


@dataclass(frozen=True)
class PrefixPattern:
    first: str
    rest: tuple[PatternToken, ...] = ()

    def matches_prefix(self, cmd: Sequence[str]) -> tuple[str, ...] | None:
        command = tuple(str(token) for token in cmd)
        pattern_length = len(self.rest) + 1
        if len(command) < pattern_length or command[0] != self.first:
            return None
        for pattern_token, command_token in zip(self.rest, command[1:pattern_length], strict=True):
            if not pattern_token.matches(command_token):
                return None
        return command[:pattern_length]


@dataclass(frozen=True)
class PrefixRule:
    pattern: PrefixPattern
    decision: Decision = Decision.ALLOW
    justification: str | None = None

    @property
    def program(self) -> str:
        return self.pattern.first

    def matches(self, cmd: Sequence[str]) -> "RuleMatch" | None:
        matched_prefix = self.pattern.matches_prefix(cmd)
        if matched_prefix is None:
            return None
        return RuleMatch.prefix_rule_match(matched_prefix, self.decision, justification=self.justification)


@dataclass(frozen=True)
class NetworkRule:
    host: str
    protocol: NetworkRuleProtocol
    decision: Decision
    justification: str | None = None


@dataclass(frozen=True)
class RuleMatch:
    kind: str
    decision: Decision
    matched_prefix: tuple[str, ...] = ()
    command: tuple[str, ...] = ()
    resolved_program: str | None = None
    justification: str | None = None

    @classmethod
    def prefix_rule_match(
        cls,
        matched_prefix: Sequence[str],
        decision: Decision | str,
        resolved_program: str | None = None,
        justification: str | None = None,
    ) -> "RuleMatch":
        return cls(
            kind="prefixRuleMatch",
            decision=Decision.parse(decision),
            matched_prefix=tuple(str(token) for token in matched_prefix),
            resolved_program=resolved_program,
            justification=justification,
        )

    @classmethod
    def heuristics_rule_match(cls, command: Sequence[str], decision: Decision | str) -> "RuleMatch":
        return cls(
            kind="heuristicsRuleMatch",
            decision=Decision.parse(decision),
            command=tuple(str(token) for token in command),
        )


@dataclass(frozen=True)
class Evaluation:
    decision: Decision
    matched_rules: tuple[RuleMatch, ...]

    def is_match(self) -> bool:
        return any(rule.kind != "heuristicsRuleMatch" for rule in self.matched_rules)


class Policy:
    def __init__(
        self,
        rules_by_program: Mapping[str, Sequence[PrefixRule]] | None = None,
        network_rules: Sequence[NetworkRule] = (),
    ) -> None:
        self._rules_by_program = {
            str(program): list(rules) for program, rules in (rules_by_program or {}).items()
        }
        self._network_rules = list(network_rules)

    @classmethod
    def empty(cls) -> "Policy":
        return cls()

    def rules(self) -> Mapping[str, tuple[PrefixRule, ...]]:
        return {program: tuple(rules) for program, rules in self._rules_by_program.items()}

    def network_rules(self) -> tuple[NetworkRule, ...]:
        return tuple(self._network_rules)

    def add_prefix_rule(self, prefix: Sequence[str], decision: Decision | str) -> None:
        tokens = tuple(str(token) for token in prefix)
        if not tokens:
            raise InvalidPatternError("prefix cannot be empty")
        first, *rest = tokens
        rule = PrefixRule(
            pattern=PrefixPattern(first=first, rest=tuple(PatternToken.single(token) for token in rest)),
            decision=Decision.parse(decision),
            justification=None,
        )
        self._rules_by_program.setdefault(first, []).append(rule)

    def add_network_rule(
        self,
        host: str,
        protocol: NetworkRuleProtocol | str,
        decision: Decision | str,
        justification: str | None = None,
    ) -> None:
        if justification is not None and not justification.strip():
            raise InvalidRuleError("justification cannot be empty")
        try:
            normalized_host = normalize_network_rule_host(host)
        except AmendError as exc:
            message = str(exc)
            prefix = "invalid network rule: invalid rule: "
            if message.startswith(prefix):
                message = message[len(prefix) :]
            raise InvalidRuleError(message) from exc
        parsed_protocol = protocol if isinstance(protocol, NetworkRuleProtocol) else NetworkRuleProtocol.parse(protocol)
        self._network_rules.append(
            NetworkRule(
                host=normalized_host,
                protocol=parsed_protocol,
                decision=Decision.parse(decision),
                justification=justification,
            )
        )

    def compiled_network_domains(self) -> tuple[list[str], list[str]]:
        allowed: list[str] = []
        denied: list[str] = []
        for rule in self._network_rules:
            if rule.decision is Decision.ALLOW:
                denied = [entry for entry in denied if entry != rule.host]
                allowed = [entry for entry in allowed if entry != rule.host]
                allowed.append(rule.host)
            elif rule.decision is Decision.FORBIDDEN:
                allowed = [entry for entry in allowed if entry != rule.host]
                denied = [entry for entry in denied if entry != rule.host]
                denied.append(rule.host)
        return allowed, denied

    def matches_for_command(
        self,
        cmd: Sequence[str],
        heuristics_fallback: object | None = None,
    ) -> tuple[RuleMatch, ...]:
        command = tuple(str(token) for token in cmd)
        matched_rules: list[RuleMatch] = []
        if command:
            for rule in self._rules_by_program.get(command[0], []):
                match = rule.matches(command)
                if match is not None:
                    matched_rules.append(match)
        if not matched_rules and heuristics_fallback is not None:
            decision = heuristics_fallback(command)  # type: ignore[operator]
            matched_rules.append(RuleMatch.heuristics_rule_match(command, decision))
        return tuple(matched_rules)

    def check(self, cmd: Sequence[str], heuristics_fallback: object) -> Evaluation:
        matched_rules = self.matches_for_command(cmd, heuristics_fallback)
        if not matched_rules:
            raise ValueError("invariant failed: matched_rules must be non-empty")
        decision = strongest_decision(tuple(rule.decision for rule in matched_rules))
        return Evaluation(decision=decision, matched_rules=matched_rules)


try:
    __all__.extend(
        [
            "PatternToken",
            "PrefixPattern",
            "PrefixRule",
            "NetworkRule",
            "RuleMatch",
            "Evaluation",
            "Policy",
        ]
    )
except NameError:
    __all__ = [
        "PatternToken",
        "PrefixPattern",
        "PrefixRule",
        "NetworkRule",
        "RuleMatch",
        "Evaluation",
        "Policy",
    ]

# Rust parity: codex-execpolicy/src/rule.rs example validation helpers
def _shell_join_for_example(example: Sequence[str]) -> str:
    import shlex

    return shlex.join(str(token) for token in example)


def validate_match_examples(
    policy: Policy,
    rules: Sequence[PrefixRule],
    matches: Sequence[Sequence[str]],
) -> None:
    unmatched_examples: list[str] = []
    for example in matches:
        if policy.matches_for_command(example, None):
            continue
        unmatched_examples.append(_shell_join_for_example(example))
    if unmatched_examples:
        raise ExampleDidNotMatchError([repr(rule) for rule in rules], unmatched_examples)


def validate_not_match_examples(
    policy: Policy,
    rules: Sequence[PrefixRule],
    not_matches: Sequence[Sequence[str]],
) -> None:
    del rules
    for example in not_matches:
        matches = policy.matches_for_command(example, None)
        if matches:
            raise ExampleDidMatchError(repr(matches[0]), _shell_join_for_example(example))


try:
    __all__.extend(["validate_match_examples", "validate_not_match_examples"])
except NameError:
    __all__ = ["validate_match_examples", "validate_not_match_examples"]

# Rust parity: codex-execpolicy/src/execpolicycheck.rs format_matches_json
def _rule_match_to_json_object(rule: RuleMatch) -> dict[str, object]:
    if rule.kind == "prefixRuleMatch":
        payload: dict[str, object] = {
            "matchedPrefix": list(rule.matched_prefix),
            "decision": rule.decision.value,
        }
        if rule.resolved_program is not None:
            payload["resolvedProgram"] = rule.resolved_program
        if rule.justification is not None:
            payload["justification"] = rule.justification
        return {"prefixRuleMatch": payload}
    if rule.kind == "heuristicsRuleMatch":
        return {
            "heuristicsRuleMatch": {
                "command": list(rule.command),
                "decision": rule.decision.value,
            }
        }
    raise ValueError(f"unsupported rule match kind: {rule.kind}")


def format_matches_json(matched_rules: Sequence[RuleMatch], pretty: bool = False) -> str:
    import json

    rules = tuple(matched_rules)
    output: dict[str, object] = {"matchedRules": [_rule_match_to_json_object(rule) for rule in rules]}
    if rules:
        output["decision"] = strongest_decision(tuple(rule.decision for rule in rules)).value
    if pretty:
        return json.dumps(output, indent=2, ensure_ascii=False)
    return json.dumps(output, separators=(",", ":"), ensure_ascii=False)


def load_policies(policy_paths: Sequence[object]) -> Policy:
    raise NotImplementedError(
        "codex-execpolicy load_policies depends on PolicyParser/Starlark policy loading, "
        "which is tracked as a separate module-scoped contract"
    )


try:
    __all__.extend(["format_matches_json", "load_policies"])
except NameError:
    __all__ = ["format_matches_json", "load_policies"]

# Rust parity: codex-execpolicy/src/lib.rs public export surface
Error = ExecPolicyError
Result = object


@dataclass(frozen=True)
class MatchOptions:
    resolve_host_executables: bool = False


class Rule:
    def program(self) -> str:
        raise NotImplementedError("Rule.program is implemented by concrete execpolicy rule types")

    def matches(self, cmd: Sequence[str]) -> RuleMatch | None:
        raise NotImplementedError("Rule.matches is implemented by concrete execpolicy rule types")


RuleRef = Rule


class PolicyParser:
    """Compatibility scaffold for Rust PolicyParser.

    Full Starlark policy parsing is tracked as a separate module-scoped behavior contract.
    """

    def __init__(self) -> None:
        self._blocked_sources: list[tuple[str, str]] = []

    def parse(self, policy_identifier: str, policy_source: str) -> None:
        self._blocked_sources.append((str(policy_identifier), str(policy_source)))
        raise NotImplementedError(
            "codex-execpolicy PolicyParser/Starlark policy parsing is tracked as a separate contract"
        )

    def build(self) -> Policy:
        if self._blocked_sources:
            raise NotImplementedError(
                "codex-execpolicy PolicyParser build requires completed parser parity"
            )
        return Policy.empty()


@dataclass(frozen=True)
class ExecPolicyCheckCommand:
    rules: tuple[Path, ...]
    command: tuple[str, ...]
    pretty: bool = False
    resolve_host_executables: bool = False

    def __init__(
        self,
        rules: Sequence[object],
        command: Sequence[str],
        pretty: bool = False,
        resolve_host_executables: bool = False,
    ) -> None:
        object.__setattr__(self, "rules", tuple(Path(rule) for rule in rules))
        object.__setattr__(self, "command", tuple(str(token) for token in command))
        object.__setattr__(self, "pretty", bool(pretty))
        object.__setattr__(self, "resolve_host_executables", bool(resolve_host_executables))

    def run(self) -> str:
        policy = load_policies(self.rules)
        matched_rules = policy.matches_for_command(self.command, None)
        return format_matches_json(matched_rules, pretty=self.pretty)


try:
    __all__.extend(
        [
            "Error",
            "Result",
            "MatchOptions",
            "Rule",
            "RuleRef",
            "PolicyParser",
            "ExecPolicyCheckCommand",
        ]
    )
except NameError:
    __all__ = [
        "Error",
        "Result",
        "MatchOptions",
        "Rule",
        "RuleRef",
        "PolicyParser",
        "ExecPolicyCheckCommand",
    ]

# Rust parity: codex-execpolicy/src/main.rs CLI dispatch surface
@dataclass(frozen=True)
class ExecPolicyCli:
    command: ExecPolicyCheckCommand


def parse_execpolicy_cli(args: Sequence[str]) -> ExecPolicyCli:
    tokens = [str(arg) for arg in args]
    if not tokens:
        raise ValueError("codex-execpolicy requires a subcommand: check")
    subcommand, *rest = tokens
    if subcommand != "check":
        raise ValueError(f"Unknown codex-execpolicy subcommand: {subcommand}")

    rules: list[Path] = []
    command: list[str] = []
    pretty = False
    resolve_host_executables = False
    index = 0
    while index < len(rest):
        token = rest[index]
        if token in ("-r", "--rules"):
            index += 1
            if index >= len(rest):
                raise ValueError("codex-execpolicy check requires --rules PATH")
            rules.append(Path(rest[index]))
        elif token == "--pretty":
            pretty = True
        elif token == "--resolve-host-executables":
            resolve_host_executables = True
        elif token == "--":
            command.extend(rest[index + 1 :])
            break
        else:
            command.extend(rest[index:])
            break
        index += 1

    if not rules:
        raise ValueError("codex-execpolicy check requires --rules")
    if not command:
        raise ValueError("codex-execpolicy check requires COMMAND")
    return ExecPolicyCli(
        ExecPolicyCheckCommand(
            rules=rules,
            command=command,
            pretty=pretty,
            resolve_host_executables=resolve_host_executables,
        )
    )


def run_execpolicy_cli(args: Sequence[str]) -> str:
    cli = parse_execpolicy_cli(args)
    return cli.command.run()


try:
    __all__.extend(["ExecPolicyCli", "parse_execpolicy_cli", "run_execpolicy_cli"])
except NameError:
    __all__ = ["ExecPolicyCli", "parse_execpolicy_cli", "run_execpolicy_cli"]

# Rust parity: codex-execpolicy/src/parser.rs restricted policy parser slice
def _literal_string(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise InvalidRuleError(f"{context} must be a string")
    return value


def _literal_string_list(value: object, context: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InvalidRuleError(f"{context} must be a list of strings")
    return list(value)


def _parse_pattern_literal(value: object) -> tuple[PatternToken, ...]:
    if not isinstance(value, list):
        raise InvalidPatternError(f"pattern must be a list (got {type(value).__name__})")
    if not value:
        raise InvalidPatternError("pattern cannot be empty")
    tokens: list[PatternToken] = []
    for item in value:
        if isinstance(item, str):
            tokens.append(PatternToken.single(item))
        elif isinstance(item, list):
            if not item:
                raise InvalidPatternError("pattern alternatives cannot be empty")
            if not all(isinstance(alt, str) for alt in item):
                raise InvalidPatternError("pattern alternative must be a string")
            tokens.append(PatternToken.single(item[0]) if len(item) == 1 else PatternToken.alts(item))
        else:
            raise InvalidPatternError(
                f"pattern element must be a string or list of strings (got {type(item).__name__})"
            )
    return tuple(tokens)


def _parse_example_literal(value: object) -> list[str]:
    import shlex

    if isinstance(value, str):
        parsed = shlex.split(value)
        if not parsed:
            raise InvalidExampleError("example cannot be an empty string")
        return parsed
    if isinstance(value, list):
        if not value:
            raise InvalidExampleError("example cannot be an empty list")
        if not all(isinstance(item, str) for item in value):
            raise InvalidExampleError("example tokens must be strings")
        return list(value)
    raise InvalidExampleError(f"example must be a string or list of strings (got {type(value).__name__})")


def _parse_examples_literal(value: object | None) -> list[list[str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidExampleError("examples must be a list")
    return [_parse_example_literal(item) for item in value]


def _literal_eval_node(node: object) -> object:
    import ast

    try:
        return ast.literal_eval(node)
    except Exception as exc:
        raise InvalidRuleError("policy parser slice only supports literal arguments") from exc


def _parse_policy_source_to_calls(policy_identifier: str, policy_source: str) -> list[object]:
    import ast

    try:
        module = ast.parse(policy_source, filename=policy_identifier)
    except SyntaxError as exc:
        raise InvalidRuleError(str(exc)) from exc
    calls: list[object] = []
    for statement in module.body:
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
            raise InvalidRuleError("policy parser slice only supports top-level rule calls")
        calls.append(statement.value)
    return calls


def _call_keyword_map(call: object) -> dict[str, object]:
    keywords: dict[str, object] = {}
    for keyword in call.keywords:  # type: ignore[attr-defined]
        if keyword.arg is None:
            raise InvalidRuleError("policy rule calls do not support **kwargs")
        keywords[keyword.arg] = _literal_eval_node(keyword.value)
    if call.args:  # type: ignore[attr-defined]
        raise InvalidRuleError("policy rule calls require keyword arguments")
    return keywords


class PolicyParser:
    """Restricted Python parser for the common execpolicy Starlark subset."""

    def __init__(self) -> None:
        self._policy = Policy.empty()

    def parse(self, policy_identifier: str, policy_source: str) -> None:
        import ast

        for call in _parse_policy_source_to_calls(str(policy_identifier), str(policy_source)):
            name = call.func.id if isinstance(call.func, ast.Name) else None  # type: ignore[attr-defined]
            kwargs = _call_keyword_map(call)
            if name == "prefix_rule":
                self._parse_prefix_rule(kwargs)
            elif name == "network_rule":
                self._parse_network_rule(kwargs)
            elif name == "host_executable":
                raise NotImplementedError(
                    "codex-execpolicy host_executable parser support is tracked as a separate contract"
                )
            else:
                raise InvalidRuleError(f"unknown policy rule function: {name}")

    def _parse_prefix_rule(self, kwargs: Mapping[str, object]) -> None:
        pattern = _parse_pattern_literal(kwargs.get("pattern"))
        raw_decision = kwargs.get("decision", Decision.ALLOW.value)
        decision = Decision.parse(_literal_string(raw_decision, "decision"))
        raw_justification = kwargs.get("justification")
        justification = None
        if raw_justification is not None:
            justification = _literal_string(raw_justification, "justification")
            if not justification.strip():
                raise InvalidRuleError("justification cannot be empty")
        matches = _parse_examples_literal(kwargs.get("match"))
        not_matches = _parse_examples_literal(kwargs.get("not_match"))

        first, *rest = pattern
        rules: list[PrefixRule] = []
        for head in first.alternatives():
            rule = PrefixRule(
                pattern=PrefixPattern(first=head, rest=tuple(rest)),
                decision=decision,
                justification=justification,
            )
            self._policy._rules_by_program.setdefault(head, []).append(rule)
            rules.append(rule)
        validate_not_match_examples(self._policy, rules, not_matches)
        validate_match_examples(self._policy, rules, matches)

    def _parse_network_rule(self, kwargs: Mapping[str, object]) -> None:
        host = _literal_string(kwargs.get("host"), "host")
        protocol = NetworkRuleProtocol.parse(_literal_string(kwargs.get("protocol"), "protocol"))
        raw_decision = _literal_string(kwargs.get("decision"), "decision")
        decision = Decision.FORBIDDEN if raw_decision == "deny" else Decision.parse(raw_decision)
        justification_value = kwargs.get("justification")
        justification = None
        if justification_value is not None:
            justification = _literal_string(justification_value, "justification")
        self._policy.add_network_rule(host, protocol, decision, justification)

    def build(self) -> Policy:
        return self._policy


def load_policies(policy_paths: Sequence[object]) -> Policy:
    parser = PolicyParser()
    for policy_path in policy_paths:
        path = Path(policy_path)
        try:
            contents = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise OSError(f"failed to read policy at {path}: {exc}") from exc
        try:
            parser.parse(str(path), contents)
        except Exception as exc:
            if isinstance(exc, NotImplementedError):
                raise
            raise type(exc)(f"failed to parse policy at {path}: {exc}") from exc
    return parser.build()

# Rust parity: codex-execpolicy parser/policy host_executable slice
def _validate_host_executable_name(name: str) -> None:
    raw = str(name)
    if not raw:
        raise InvalidRuleError("host_executable name cannot be empty")
    if Path(raw).name != raw or any(separator in raw for separator in ("/", "\\")):
        raise InvalidRuleError(f"host_executable name must be a bare executable name (got {raw})")


def _parse_literal_absolute_path(raw: str) -> Path:
    path = Path(str(raw))
    if not path.is_absolute():
        raise InvalidRuleError(f"host_executable paths must be absolute (got {raw})")
    return path


def _policy_set_host_executable_paths(self: Policy, name: str, paths: Sequence[object]) -> None:
    if not hasattr(self, "_host_executables_by_name"):
        self._host_executables_by_name = {}
    self._host_executables_by_name[str(name)] = tuple(str(Path(path)) for path in paths)


def _policy_host_executables(self: Policy) -> Mapping[str, tuple[str, ...]]:
    return dict(getattr(self, "_host_executables_by_name", {}))


def _policy_match_host_executable_rules(self: Policy, command: tuple[str, ...]) -> list[RuleMatch]:
    if not command:
        return []
    program = Path(command[0])
    if not program.is_absolute():
        return []
    basename = executable_path_lookup_key(program)
    if basename is None:
        return []
    rules = self._rules_by_program.get(basename, [])
    if not rules:
        return []
    mappings = getattr(self, "_host_executables_by_name", {})
    if basename in mappings and str(program) not in mappings[basename]:
        return []
    basename_command = (basename, *command[1:])
    matches: list[RuleMatch] = []
    for rule in rules:
        match = rule.matches(basename_command)
        if match is not None:
            matches.append(
                RuleMatch.prefix_rule_match(
                    match.matched_prefix,
                    match.decision,
                    resolved_program=str(program),
                    justification=match.justification,
                )
            )
    return matches


def _policy_matches_for_command_with_options(
    self: Policy,
    cmd: Sequence[str],
    heuristics_fallback: object | None = None,
    options: MatchOptions | None = None,
) -> tuple[RuleMatch, ...]:
    command = tuple(str(token) for token in cmd)
    matched_rules: list[RuleMatch] = []
    if command:
        for rule in self._rules_by_program.get(command[0], []):
            match = rule.matches(command)
            if match is not None:
                matched_rules.append(match)
    if not matched_rules and options is not None and options.resolve_host_executables:
        matched_rules.extend(_policy_match_host_executable_rules(self, command))
    if not matched_rules and heuristics_fallback is not None:
        decision = heuristics_fallback(command)  # type: ignore[operator]
        matched_rules.append(RuleMatch.heuristics_rule_match(command, decision))
    return tuple(matched_rules)


def _policy_matches_for_command(self: Policy, cmd: Sequence[str], heuristics_fallback: object | None = None) -> tuple[RuleMatch, ...]:
    return _policy_matches_for_command_with_options(self, cmd, heuristics_fallback, MatchOptions())


def _policy_check_with_options(
    self: Policy,
    cmd: Sequence[str],
    heuristics_fallback: object,
    options: MatchOptions,
) -> Evaluation:
    matched_rules = self.matches_for_command_with_options(cmd, heuristics_fallback, options)
    if not matched_rules:
        raise ValueError("invariant failed: matched_rules must be non-empty")
    return Evaluation(
        decision=strongest_decision(tuple(rule.decision for rule in matched_rules)),
        matched_rules=matched_rules,
    )


def _policy_check(self: Policy, cmd: Sequence[str], heuristics_fallback: object) -> Evaluation:
    return _policy_check_with_options(self, cmd, heuristics_fallback, MatchOptions())


Policy.set_host_executable_paths = _policy_set_host_executable_paths  # type: ignore[attr-defined]
Policy.host_executables = _policy_host_executables  # type: ignore[attr-defined]
Policy.matches_for_command_with_options = _policy_matches_for_command_with_options  # type: ignore[attr-defined]
Policy.matches_for_command = _policy_matches_for_command  # type: ignore[method-assign]
Policy.check_with_options = _policy_check_with_options  # type: ignore[attr-defined]
Policy.check = _policy_check  # type: ignore[method-assign]


_old_policy_parser_parse_prefix = PolicyParser._parse_prefix_rule
_old_policy_parser_parse_network = PolicyParser._parse_network_rule


def _policy_parser_parse(self: PolicyParser, policy_identifier: str, policy_source: str) -> None:
    import ast

    for call in _parse_policy_source_to_calls(str(policy_identifier), str(policy_source)):
        name = call.func.id if isinstance(call.func, ast.Name) else None  # type: ignore[attr-defined]
        kwargs = _call_keyword_map(call)
        if name == "prefix_rule":
            self._parse_prefix_rule(kwargs)
        elif name == "network_rule":
            self._parse_network_rule(kwargs)
        elif name == "host_executable":
            self._parse_host_executable(kwargs)
        else:
            raise InvalidRuleError(f"unknown policy rule function: {name}")


def _policy_parser_parse_host_executable(self: PolicyParser, kwargs: Mapping[str, object]) -> None:
    name = _literal_string(kwargs.get("name"), "name")
    _validate_host_executable_name(name)
    paths_value = kwargs.get("paths")
    paths = _literal_string_list(paths_value, "host_executable paths")
    parsed_paths: list[Path] = []
    lookup_name = executable_lookup_key(name)
    for raw in paths:
        path = _parse_literal_absolute_path(raw)
        path_name = executable_path_lookup_key(path)
        if path_name != lookup_name:
            raise InvalidRuleError(f"host_executable path `{raw}` must have basename `{name}`")
        if path not in parsed_paths:
            parsed_paths.append(path)
    self._policy.set_host_executable_paths(lookup_name, parsed_paths)


PolicyParser.parse = _policy_parser_parse  # type: ignore[method-assign]
PolicyParser._parse_host_executable = _policy_parser_parse_host_executable  # type: ignore[attr-defined]

try:
    __all__.extend(["_validate_host_executable_name"])
except NameError:
    __all__ = ["_validate_host_executable_name"]
