"""Requirements exec-policy TOML helpers ported from ``codex-config``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.execpolicy import Decision, ExecPolicyPrefixRule


class RequirementsExecPolicyDecisionToml(str, Enum):
    ALLOW = "allow"
    PROMPT = "prompt"
    FORBIDDEN = "forbidden"

    def as_decision(self) -> Decision:
        return Decision(self.value)


@dataclass(frozen=True)
class RequirementsExecPolicyPatternTokenToml:
    token: str | None = None
    any_of: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.token is not None and not isinstance(self.token, str):
            raise TypeError("token must be a string or None")
        if self.any_of is not None:
            if isinstance(self.any_of, (str, bytes)) or not isinstance(self.any_of, Sequence):
                raise TypeError("any_of must be a sequence of strings or None")
            object.__setattr__(self, "any_of", tuple(self.any_of))
            if not all(isinstance(item, str) for item in self.any_of):
                raise TypeError("any_of entries must be strings")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RequirementsExecPolicyPatternTokenToml":
        return cls(token=data.get("token"), any_of=data.get("any_of"))


@dataclass(frozen=True)
class RequirementsExecPolicyPrefixRuleToml:
    pattern: tuple[RequirementsExecPolicyPatternTokenToml, ...]
    decision: RequirementsExecPolicyDecisionToml | None = None
    justification: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.pattern, (str, bytes)) or not isinstance(self.pattern, Sequence):
            raise TypeError("pattern must be a sequence")
        object.__setattr__(
            self,
            "pattern",
            tuple(
                item
                if isinstance(item, RequirementsExecPolicyPatternTokenToml)
                else RequirementsExecPolicyPatternTokenToml.from_mapping(item)
                for item in self.pattern
            ),
        )
        if self.decision is not None and not isinstance(self.decision, RequirementsExecPolicyDecisionToml):
            object.__setattr__(self, "decision", RequirementsExecPolicyDecisionToml(str(self.decision)))
        if self.justification is not None and not isinstance(self.justification, str):
            raise TypeError("justification must be a string or None")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RequirementsExecPolicyPrefixRuleToml":
        return cls(
            pattern=tuple(data.get("pattern", ())),
            decision=data.get("decision"),
            justification=data.get("justification"),
        )


@dataclass(frozen=True)
class RequirementsExecPolicy:
    prefix_rules: tuple[ExecPolicyPrefixRule, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "prefix_rules", tuple(self.prefix_rules))

    @property
    def policy(self) -> Mapping[str, tuple[ExecPolicyPrefixRule, ...]]:
        return {"prefix_rules": self.prefix_rules}

    def as_ref(self) -> "RequirementsExecPolicy":
        return self

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RequirementsExecPolicy):
            return NotImplemented
        return _policy_fingerprint(self.prefix_rules) == _policy_fingerprint(other.prefix_rules)


@dataclass(frozen=True)
class RequirementsExecPolicyToml:
    prefix_rules: tuple[RequirementsExecPolicyPrefixRuleToml, ...]

    def __post_init__(self) -> None:
        if isinstance(self.prefix_rules, (str, bytes)) or not isinstance(self.prefix_rules, Sequence):
            raise TypeError("prefix_rules must be a sequence")
        object.__setattr__(
            self,
            "prefix_rules",
            tuple(
                item
                if isinstance(item, RequirementsExecPolicyPrefixRuleToml)
                else RequirementsExecPolicyPrefixRuleToml.from_mapping(item)
                for item in self.prefix_rules
            ),
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RequirementsExecPolicyToml":
        return cls(prefix_rules=tuple(data.get("prefix_rules", ())))

    def to_policy(self) -> Mapping[str, tuple[ExecPolicyPrefixRule, ...]]:
        return self.to_requirements_policy().policy

    def to_requirements_policy(self) -> RequirementsExecPolicy:
        if not self.prefix_rules:
            raise RequirementsExecPolicyParseError.empty_prefix_rules()

        rules: list[ExecPolicyPrefixRule] = []
        for rule_index, rule in enumerate(self.prefix_rules):
            if rule.justification is not None and not rule.justification.strip():
                raise RequirementsExecPolicyParseError.empty_justification(rule_index)
            if not rule.pattern:
                raise RequirementsExecPolicyParseError.empty_pattern(rule_index)

            pattern_tokens = tuple(
                _parse_pattern_token(token, rule_index, token_index)
                for token_index, token in enumerate(rule.pattern)
            )
            if rule.decision is None:
                raise RequirementsExecPolicyParseError.missing_decision(rule_index)
            if rule.decision is RequirementsExecPolicyDecisionToml.ALLOW:
                raise RequirementsExecPolicyParseError.allow_decision_not_allowed(rule_index)

            first_token, *remaining_tokens = pattern_tokens
            for head in _alternatives(first_token):
                rules.append(
                    ExecPolicyPrefixRule.new(
                        (head, *remaining_tokens),
                        rule.decision.as_decision().value,
                        rule.justification,
                    )
                )
        return RequirementsExecPolicy(tuple(rules))


class RequirementsExecPolicyParseError(ValueError):
    @classmethod
    def empty_prefix_rules(cls) -> "RequirementsExecPolicyParseError":
        return cls("empty_prefix_rules")

    @classmethod
    def empty_pattern(cls, rule_index: int) -> "RequirementsExecPolicyParseError":
        return cls("empty_pattern", rule_index=rule_index)

    @classmethod
    def invalid_pattern_token(
        cls,
        rule_index: int,
        token_index: int,
        reason: str,
    ) -> "RequirementsExecPolicyParseError":
        return cls("invalid_pattern_token", rule_index=rule_index, token_index=token_index, reason=reason)

    @classmethod
    def empty_justification(cls, rule_index: int) -> "RequirementsExecPolicyParseError":
        return cls("empty_justification", rule_index=rule_index)

    @classmethod
    def missing_decision(cls, rule_index: int) -> "RequirementsExecPolicyParseError":
        return cls("missing_decision", rule_index=rule_index)

    @classmethod
    def allow_decision_not_allowed(cls, rule_index: int) -> "RequirementsExecPolicyParseError":
        return cls("allow_decision_not_allowed", rule_index=rule_index)

    def __init__(
        self,
        kind: str,
        *,
        rule_index: int | None = None,
        token_index: int | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(kind)
        self.kind = kind
        self.rule_index = rule_index
        self.token_index = token_index
        self.reason = reason

    def __str__(self) -> str:
        if self.kind == "empty_prefix_rules":
            return "rules prefix_rules cannot be empty"
        if self.kind == "empty_pattern":
            return f"rules prefix_rule at index {self.rule_index} has an empty pattern"
        if self.kind == "invalid_pattern_token":
            return (
                f"rules prefix_rule at index {self.rule_index} has an invalid pattern token "
                f"at index {self.token_index}: {self.reason}"
            )
        if self.kind == "empty_justification":
            return f"rules prefix_rule at index {self.rule_index} has an empty justification"
        if self.kind == "missing_decision":
            return f"rules prefix_rule at index {self.rule_index} is missing a decision"
        if self.kind == "allow_decision_not_allowed":
            return (
                f"rules prefix_rule at index {self.rule_index} has decision 'allow', which is not "
                "permitted in requirements.toml: Codex merges these rules with other config and "
                "uses the most restrictive result (use 'prompt' or 'forbidden')"
            )
        return self.kind

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RequirementsExecPolicyParseError):
            return NotImplemented
        return (
            self.kind,
            self.rule_index,
            self.token_index,
            self.reason,
        ) == (
            other.kind,
            other.rule_index,
            other.token_index,
            other.reason,
        )


def _parse_pattern_token(
    token: RequirementsExecPolicyPatternTokenToml,
    rule_index: int,
    token_index: int,
) -> str | tuple[str, ...]:
    if token.token is not None and token.any_of is None:
        if not token.token.strip():
            raise RequirementsExecPolicyParseError.invalid_pattern_token(
                rule_index, token_index, "token cannot be empty"
            )
        return token.token
    if token.token is None and token.any_of is not None:
        if not token.any_of:
            raise RequirementsExecPolicyParseError.invalid_pattern_token(
                rule_index, token_index, "any_of cannot be empty"
            )
        if any(not alternative.strip() for alternative in token.any_of):
            raise RequirementsExecPolicyParseError.invalid_pattern_token(
                rule_index, token_index, "any_of cannot include empty tokens"
            )
        return token.any_of
    if token.token is not None and token.any_of is not None:
        raise RequirementsExecPolicyParseError.invalid_pattern_token(
            rule_index, token_index, "set either token or any_of, not both"
        )
    raise RequirementsExecPolicyParseError.invalid_pattern_token(
        rule_index, token_index, "set either token or any_of"
    )


def _alternatives(token: str | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(token, tuple):
        return token
    return (token,)


def _policy_fingerprint(rules: tuple[ExecPolicyPrefixRule, ...]) -> tuple[str, ...]:
    return tuple(sorted(f"{_rule_program(rule)}:{rule!r}" for rule in rules))


def _rule_program(rule: ExecPolicyPrefixRule) -> str:
    first = rule.pattern[0] if rule.pattern else ""
    if isinstance(first, tuple):
        return "|".join(first)
    return first


__all__ = [
    "RequirementsExecPolicy",
    "RequirementsExecPolicyDecisionToml",
    "RequirementsExecPolicyParseError",
    "RequirementsExecPolicyPatternTokenToml",
    "RequirementsExecPolicyPrefixRuleToml",
    "RequirementsExecPolicyToml",
]
