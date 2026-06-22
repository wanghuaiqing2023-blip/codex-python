"""Constraint helpers ported from ``codex-config``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
ConstraintValidator = Callable[[T], None]
ConstraintNormalizer = Callable[[T], T]


@dataclass(frozen=True)
class RequirementSource:
    kind: str = "unknown"
    domain: str | None = None
    key: str | None = None
    file: str | None = None

    @classmethod
    def unknown(cls) -> "RequirementSource":
        return cls("unknown")

    @classmethod
    def mdm_managed_preferences(cls, domain: str, key: str) -> "RequirementSource":
        return cls("mdm_managed_preferences", domain=domain, key=key)

    @classmethod
    def cloud_requirements(cls) -> "RequirementSource":
        return cls("cloud_requirements")

    @classmethod
    def system_requirements_toml(cls, file: str) -> "RequirementSource":
        return cls("system_requirements_toml", file=file)

    @classmethod
    def legacy_managed_config_toml_from_file(cls, file: str) -> "RequirementSource":
        return cls("legacy_managed_config_toml_from_file", file=file)

    @classmethod
    def legacy_managed_config_toml_from_mdm(cls) -> "RequirementSource":
        return cls("legacy_managed_config_toml_from_mdm")

    def __str__(self) -> str:
        if self.kind == "unknown":
            return "<unspecified>"
        if self.kind == "mdm_managed_preferences":
            return f"MDM {self.domain}:{self.key}"
        if self.kind == "cloud_requirements":
            return "cloud requirements"
        if self.kind in {"system_requirements_toml", "legacy_managed_config_toml_from_file"}:
            return self.file or ""
        if self.kind == "legacy_managed_config_toml_from_mdm":
            return "MDM managed_config.toml (legacy)"
        return self.kind


class ConstraintError(ValueError):
    @classmethod
    def invalid_value(
        cls,
        *,
        field_name: str,
        candidate: str,
        allowed: str,
        requirement_source: RequirementSource | None = None,
    ) -> "ConstraintError":
        source = requirement_source or RequirementSource.unknown()
        return cls(
            "invalid_value",
            field_name=field_name,
            candidate=candidate,
            allowed=allowed,
            requirement_source=source,
        )

    @classmethod
    def empty_field(cls, field_name: str) -> "ConstraintError":
        return cls("empty_field", field_name=field_name)

    @classmethod
    def exec_policy_parse(
        cls,
        *,
        requirement_source: RequirementSource,
        reason: str,
    ) -> "ConstraintError":
        return cls("exec_policy_parse", requirement_source=requirement_source, reason=reason)

    def __init__(
        self,
        kind: str,
        *,
        field_name: str | None = None,
        candidate: str | None = None,
        allowed: str | None = None,
        requirement_source: RequirementSource | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(kind)
        self.kind = kind
        self.field_name = field_name
        self.candidate = candidate
        self.allowed = allowed
        self.requirement_source = requirement_source
        self.reason = reason

    def __str__(self) -> str:
        if self.kind == "invalid_value":
            return (
                f"invalid value for `{self.field_name}`: `{self.candidate}` is not in the allowed set "
                f"{self.allowed} (set by {self.requirement_source})"
            )
        if self.kind == "empty_field":
            return f"field `{self.field_name}` cannot be empty"
        if self.kind == "exec_policy_parse":
            return f"invalid rules in requirements (set by {self.requirement_source}): {self.reason}"
        return self.kind

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ConstraintError):
            return NotImplemented
        return (
            self.kind,
            self.field_name,
            self.candidate,
            self.allowed,
            self.requirement_source,
            self.reason,
        ) == (
            other.kind,
            other.field_name,
            other.candidate,
            other.allowed,
            other.requirement_source,
            other.reason,
        )


class Constrained(Generic[T]):
    def __init__(
        self,
        value: T,
        validator: ConstraintValidator[T] | None = None,
        normalizer: ConstraintNormalizer[T] | None = None,
    ) -> None:
        self._validator: ConstraintValidator[T] = validator or (lambda _candidate: None)
        self._normalizer = normalizer
        self._value = normalizer(value) if normalizer is not None else value
        self._validator(self._value)

    @classmethod
    def new(cls, initial_value: T, validator: ConstraintValidator[T]) -> "Constrained[T]":
        return cls(initial_value, validator=validator)

    @classmethod
    def normalized(cls, initial_value: T, normalizer: ConstraintNormalizer[T]) -> "Constrained[T]":
        return cls(initial_value, normalizer=normalizer)

    @classmethod
    def allow_any(cls, initial_value: T) -> "Constrained[T]":
        return cls(initial_value)

    @classmethod
    def allow_only(cls, only_value: T) -> "Constrained[T]":
        def validate(candidate: T) -> None:
            if candidate != only_value:
                raise ConstraintError.invalid_value(
                    field_name="<unknown>",
                    candidate=repr(candidate),
                    allowed=f"[{only_value!r}]",
                    requirement_source=RequirementSource.unknown(),
                )

        return cls(only_value, validator=validate)

    @classmethod
    def allow_any_from_default(cls, default: T | None = None) -> "Constrained[T | None]":
        return cls.allow_any(default)

    def get(self) -> T:
        return self._value

    def value(self) -> T:
        return self._value

    def can_set(self, candidate: T) -> None:
        self._validator(candidate)

    def add_validator(self, validator: ConstraintValidator[T]) -> None:
        existing_validator = self._validator

        def combined(candidate: T) -> None:
            existing_validator(candidate)
            validator(candidate)

        combined(self._value)
        self._validator = combined

    def set(self, value: T) -> None:
        next_value = self._normalizer(value) if self._normalizer is not None else value
        self._validator(next_value)
        self._value = next_value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Constrained):
            return self._value == other
        return self._value == other._value

    def __repr__(self) -> str:
        return f"Constrained(value={self._value!r})"


ConstraintResult = None


__all__ = [
    "Constrained",
    "ConstraintError",
    "ConstraintResult",
    "RequirementSource",
]
