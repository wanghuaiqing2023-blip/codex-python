"""Rust-aligned port of ``execpolicy-legacy/src/arg_type.rs``."""



from __future__ import annotations

import os

import json

import re

import sys

from dataclasses import dataclass

from enum import Enum

from io import TextIOBase

from pathlib import Path

from re import Pattern



from .error import EmptyFileName, InvalidPositiveInteger, LiteralValueDidNotMatch

from .sed_command import parse_sed_command, _parse_u64



class ArgTypeKind(str, Enum):
    OPAQUE_NON_FILE = "OpaqueNonFile"
    READABLE_FILE = "ReadableFile"
    WRITEABLE_FILE = "WriteableFile"
    POSITIVE_INTEGER = "PositiveInteger"
    SED_COMMAND = "SedCommand"
    UNKNOWN = "Unknown"

@dataclass(frozen=True)
class ArgType:
    """Rust ``ArgType`` projection."""

    kind: ArgTypeKind | str
    literal_value: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.kind, ArgTypeKind):
            object.__setattr__(self, "kind", self.kind.value)

    @classmethod
    def literal(cls, value: str) -> "ArgType":
        return cls("Literal", value)

    @classmethod
    def opaque_non_file(cls) -> "ArgType":
        return cls(ArgTypeKind.OPAQUE_NON_FILE)

    @classmethod
    def readable_file(cls) -> "ArgType":
        return cls(ArgTypeKind.READABLE_FILE)

    @classmethod
    def writeable_file(cls) -> "ArgType":
        return cls(ArgTypeKind.WRITEABLE_FILE)

    @classmethod
    def positive_integer(cls) -> "ArgType":
        return cls(ArgTypeKind.POSITIVE_INTEGER)

    @classmethod
    def sed_command(cls) -> "ArgType":
        return cls(ArgTypeKind.SED_COMMAND)

    @classmethod
    def unknown(cls) -> "ArgType":
        return cls(ArgTypeKind.UNKNOWN)

    def validate(self, value: str) -> None:
        if self.kind == "Literal":
            if value != self.literal_value:
                raise LiteralValueDidNotMatch(
                    expected=self.literal_value or "",
                    actual=value,
                )
            return None
        if self.kind in {ArgTypeKind.READABLE_FILE.value, ArgTypeKind.WRITEABLE_FILE.value}:
            if value == "":
                raise EmptyFileName()
            return None
        if self.kind in {ArgTypeKind.OPAQUE_NON_FILE.value, ArgTypeKind.UNKNOWN.value}:
            return None
        if self.kind == ArgTypeKind.POSITIVE_INTEGER.value:
            parsed = _parse_u64(value)
            if parsed is None or parsed == 0:
                raise InvalidPositiveInteger(value)
            return None
        if self.kind == ArgTypeKind.SED_COMMAND.value:
            return parse_sed_command(value)
        raise ValueError(f"unknown ArgType kind: {self.kind}")

    def might_write_file(self) -> bool:
        return self.kind in {ArgTypeKind.WRITEABLE_FILE.value, ArgTypeKind.UNKNOWN.value}

    def to_mapping(self) -> dict[str, str]:
        if self.kind == "Literal":
            return {"type": "Literal", "value": self.literal_value or ""}
        return {"type": str(self.kind)}
