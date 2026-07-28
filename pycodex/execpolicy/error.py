"""Rust-aligned codex-execpolicy module."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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

Error = ExecPolicyError
Result = object

__all__ = ['Error', 'ErrorLocation', 'ExecPolicyError', 'InvalidDecisionError', 'InvalidExampleError', 'InvalidPatternError', 'InvalidRuleError', 'ExampleDidMatchError', 'ExampleDidNotMatchError', 'Result', 'TextPosition', 'TextRange']
