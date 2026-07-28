"""Rust-aligned port of ``execpolicy-legacy/src/arg_matcher.rs``."""



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



from .arg_type import ArgType



class ArgMatcherCardinality(str, Enum):
    ONE = "One"
    AT_LEAST_ONE = "AtLeastOne"
    ZERO_OR_MORE = "ZeroOrMore"

    def is_exact(self) -> int | None:
        if self is ArgMatcherCardinality.ONE:
            return 1
        return None

class ArgMatcherKind(str, Enum):
    OPAQUE_NON_FILE = "OpaqueNonFile"
    READABLE_FILE = "ReadableFile"
    WRITEABLE_FILE = "WriteableFile"
    READABLE_FILES = "ReadableFiles"
    READABLE_FILES_OR_CWD = "ReadableFilesOrCwd"
    POSITIVE_INTEGER = "PositiveInteger"
    SED_COMMAND = "SedCommand"
    UNVERIFIED_VARARGS = "UnverifiedVarargs"

@dataclass(frozen=True)
class ArgMatcher:
    """Rust ``ArgMatcher`` projection."""

    kind: ArgMatcherKind | str
    literal_value: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.kind, ArgMatcherKind):
            object.__setattr__(self, "kind", self.kind.value)

    @classmethod
    def literal(cls, value: str) -> "ArgMatcher":
        return cls("Literal", value)

    @classmethod
    def opaque_non_file(cls) -> "ArgMatcher":
        return cls(ArgMatcherKind.OPAQUE_NON_FILE)

    @classmethod
    def readable_file(cls) -> "ArgMatcher":
        return cls(ArgMatcherKind.READABLE_FILE)

    @classmethod
    def writeable_file(cls) -> "ArgMatcher":
        return cls(ArgMatcherKind.WRITEABLE_FILE)

    @classmethod
    def readable_files(cls) -> "ArgMatcher":
        return cls(ArgMatcherKind.READABLE_FILES)

    @classmethod
    def readable_files_or_cwd(cls) -> "ArgMatcher":
        return cls(ArgMatcherKind.READABLE_FILES_OR_CWD)

    @classmethod
    def positive_integer(cls) -> "ArgMatcher":
        return cls(ArgMatcherKind.POSITIVE_INTEGER)

    @classmethod
    def sed_command(cls) -> "ArgMatcher":
        return cls(ArgMatcherKind.SED_COMMAND)

    @classmethod
    def unverified_varargs(cls) -> "ArgMatcher":
        return cls(ArgMatcherKind.UNVERIFIED_VARARGS)

    @classmethod
    def unpack_value(cls, value: object) -> "ArgMatcher | None":
        """Mirror Rust ``UnpackValue``: Starlark strings become literals."""

        if isinstance(value, str):
            return cls.literal(value)
        if isinstance(value, cls):
            return value
        return None

    def cardinality(self) -> ArgMatcherCardinality:
        if self.kind in {
            "Literal",
            ArgMatcherKind.OPAQUE_NON_FILE.value,
            ArgMatcherKind.READABLE_FILE.value,
            ArgMatcherKind.WRITEABLE_FILE.value,
            ArgMatcherKind.POSITIVE_INTEGER.value,
            ArgMatcherKind.SED_COMMAND.value,
        }:
            return ArgMatcherCardinality.ONE
        if self.kind == ArgMatcherKind.READABLE_FILES.value:
            return ArgMatcherCardinality.AT_LEAST_ONE
        if self.kind in {
            ArgMatcherKind.READABLE_FILES_OR_CWD.value,
            ArgMatcherKind.UNVERIFIED_VARARGS.value,
        }:
            return ArgMatcherCardinality.ZERO_OR_MORE
        raise ValueError(f"unknown ArgMatcher kind: {self.kind}")

    def arg_type(self) -> ArgType:
        if self.kind == "Literal":
            return ArgType.literal(self.literal_value or "")
        if self.kind == ArgMatcherKind.OPAQUE_NON_FILE.value:
            return ArgType.opaque_non_file()
        if self.kind in {
            ArgMatcherKind.READABLE_FILE.value,
            ArgMatcherKind.READABLE_FILES.value,
            ArgMatcherKind.READABLE_FILES_OR_CWD.value,
        }:
            return ArgType.readable_file()
        if self.kind == ArgMatcherKind.WRITEABLE_FILE.value:
            return ArgType.writeable_file()
        if self.kind == ArgMatcherKind.POSITIVE_INTEGER.value:
            return ArgType.positive_integer()
        if self.kind == ArgMatcherKind.SED_COMMAND.value:
            return ArgType.sed_command()
        if self.kind == ArgMatcherKind.UNVERIFIED_VARARGS.value:
            return ArgType.unknown()
        raise ValueError(f"unknown ArgMatcher kind: {self.kind}")

    def to_mapping(self) -> dict[str, str]:
        if self.kind == "Literal":
            return {"type": "Literal", "value": self.literal_value or ""}
        return {"type": str(self.kind)}
