"""Rust-aligned codex-execpolicy module."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from .decision import Decision
from .error import ExampleDidMatchError, ExampleDidNotMatchError, InvalidRuleError

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
        raise InvalidRuleError("network_rule host cannot be empty")
    if "://" in host or "/" in host or "?" in host or "#" in host:
        raise InvalidRuleError(
            "network_rule host must be a hostname or IP literal (without scheme or path)"
        )

    if host.startswith("["):
        close = host.find("]")
        if close == -1:
            raise InvalidRuleError("network_rule host has an invalid bracketed IPv6 literal")
        inside = host[1:close]
        rest = host[close + 1 :]
        port_ok = rest.startswith(":") and rest[1:].isdigit() and bool(rest[1:])
        if rest and not port_ok:
            raise InvalidRuleError(f"network_rule host contains an unsupported suffix: {raw}")
        host = inside
    elif host.count(":") == 1:
        candidate, port = host.rsplit(":", 1)
        if candidate and port and port.isdigit():
            host = candidate

    normalized = host.rstrip(".").strip().lower()
    if not normalized:
        raise InvalidRuleError("network_rule host cannot be empty")
    if "*" in normalized:
        raise InvalidRuleError(
            "network_rule host must be a specific host; wildcards are not allowed"
        )
    if any(ch.isspace() for ch in normalized):
        raise InvalidRuleError("network_rule host cannot contain whitespace")
    return normalized

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

    def __iter__(self):
        yield self.first
        yield from (token.value for token in self.rest)

    def __len__(self) -> int:
        return len(self.rest) + 1

    def __getitem__(self, index: int):
        return tuple(self)[index]


@dataclass(frozen=True)
class PrefixRule:
    pattern: PrefixPattern
    decision: Decision = Decision.ALLOW
    justification: str | None = None

    @property
    def program(self) -> str:
        return self.pattern.first

    @classmethod
    def new(
        cls,
        pattern: Sequence[str | Sequence[str]],
        decision: Decision | str,
        justification: str | None = None,
    ) -> "PrefixRule":
        tokens = tuple(
            PatternToken.alts(item) if not isinstance(item, str) else PatternToken.single(item)
            for item in pattern
        )
        if not tokens:
            raise ValueError("prefix rule pattern cannot be empty")
        first, *rest = tokens
        if not isinstance(first.value, str):
            raise ValueError("prefix rule first token must be a string")
        return cls(
            PrefixPattern(first.value, tuple(rest)),
            Decision.parse(decision),
            justification,
        )

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

class Rule:
    def program(self) -> str:
        raise NotImplementedError("Rule.program is implemented by concrete execpolicy rule types")

    def matches(self, cmd: Sequence[str]) -> RuleMatch | None:
        raise NotImplementedError("Rule.matches is implemented by concrete execpolicy rule types")


RuleRef = Rule

__all__ = ['NetworkRule', 'NetworkRuleProtocol', 'PatternToken', 'PrefixPattern', 'PrefixRule', 'Rule', 'RuleMatch', 'RuleRef', 'normalize_network_rule_host', 'validate_match_examples', 'validate_not_match_examples']
