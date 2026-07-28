"""Rust-aligned codex-execpolicy module."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .decision import Decision
from .error import InvalidPatternError, InvalidRuleError
from .executable_name import executable_path_lookup_key
from .rule import NetworkRule, NetworkRuleProtocol, PrefixPattern, PrefixRule, PatternToken, RuleMatch, normalize_network_rule_host


def _strongest_decision(decisions: Sequence[Decision]) -> Decision:
    return max(decisions, key=lambda item: (Decision.ALLOW, Decision.PROMPT, Decision.FORBIDDEN).index(item))

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
        normalized_host = normalize_network_rule_host(host)
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
        decision = _strongest_decision(tuple(rule.decision for rule in matched_rules))
        return Evaluation(decision=decision, matched_rules=matched_rules)

@dataclass(frozen=True)
class MatchOptions:
    resolve_host_executables: bool = False

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
        decision=_strongest_decision(tuple(rule.decision for rule in matched_rules)),
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

__all__ = ['Evaluation', 'MatchOptions', 'Policy']
