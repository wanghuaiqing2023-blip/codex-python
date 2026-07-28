"""Rust-aligned port of ``execpolicy-legacy/src/error.rs``."""



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





class Error(Exception):
    """Base error for legacy exec-policy parity helpers."""

@dataclass(frozen=True)
class LiteralValueDidNotMatch(Error):
    """Rust ``Error::LiteralValueDidNotMatch`` projection."""

    expected: str
    actual: str

    def to_mapping(self) -> dict[str, str]:
        return {
            "type": "LiteralValueDidNotMatch",
            "expected": self.expected,
            "actual": self.actual,
        }

class EmptyFileName(Error):
    """Rust ``Error::EmptyFileName`` projection."""

    def to_mapping(self) -> dict[str, str]:
        return {"type": "EmptyFileName"}

@dataclass(frozen=True)
class InvalidPositiveInteger(Error):
    """Rust ``Error::InvalidPositiveInteger`` projection."""

    value: str

    def to_mapping(self) -> dict[str, str]:
        return {"type": "InvalidPositiveInteger", "value": self.value}

@dataclass(frozen=True)
class SedCommandNotProvablySafe(Error):
    """Rust ``Error::SedCommandNotProvablySafe`` projection."""

    command: str

    def __str__(self) -> str:
        return f"sed command is not provably safe: {self.command}"

    def to_mapping(self) -> dict[str, str]:
        return {"type": "SedCommandNotProvablySafe", "command": self.command}

@dataclass(frozen=True)
class UnexpectedArguments(Error):
    """Rust ``Error::UnexpectedArguments`` projection."""

    program: str
    observed_args: tuple["PositionalArg", ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "type": "UnexpectedArguments",
            "program": self.program,
            "args": [arg.to_mapping() for arg in self.observed_args],
        }

@dataclass(frozen=True)
class MultipleVarargPatterns(Error):
    """Rust ``Error::MultipleVarargPatterns`` projection."""

    program: str
    first: "ArgMatcher"
    second: "ArgMatcher"

    def to_mapping(self) -> dict[str, object]:
        return {
            "type": "MultipleVarargPatterns",
            "program": self.program,
            "first": self.first.to_mapping(),
            "second": self.second.to_mapping(),
        }

@dataclass(frozen=True)
class RangeStartExceedsEnd(Error):
    """Rust ``Error::RangeStartExceedsEnd`` projection."""

    start: int
    end: int

    def to_mapping(self) -> dict[str, int | str]:
        return {"type": "RangeStartExceedsEnd", "start": self.start, "end": self.end}

@dataclass(frozen=True)
class RangeEndOutOfBounds(Error):
    """Rust ``Error::RangeEndOutOfBounds`` projection."""

    end: int
    length: int

    def to_mapping(self) -> dict[str, int | str]:
        return {"type": "RangeEndOutOfBounds", "end": self.end, "len": self.length}

class PrefixOverlapsSuffix(Error):
    """Rust ``Error::PrefixOverlapsSuffix`` projection."""

    def to_mapping(self) -> dict[str, str]:
        return {"type": "PrefixOverlapsSuffix"}

@dataclass(frozen=True)
class NotEnoughArgs(Error):
    """Rust ``Error::NotEnoughArgs`` projection."""

    program: str
    observed_args: tuple["PositionalArg", ...]
    arg_patterns: tuple["ArgMatcher", ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "type": "NotEnoughArgs",
            "program": self.program,
            "args": [arg.to_mapping() for arg in self.observed_args],
            "arg_patterns": [pattern.to_mapping() for pattern in self.arg_patterns],
        }

@dataclass(frozen=True)
class InternalInvariantViolation(Error):
    """Rust ``Error::InternalInvariantViolation`` projection."""

    message: str

    def to_mapping(self) -> dict[str, str]:
        return {"type": "InternalInvariantViolation", "message": self.message}

@dataclass(frozen=True)
class VarargMatcherDidNotMatchAnything(Error):
    """Rust ``Error::VarargMatcherDidNotMatchAnything`` projection."""

    program: str
    matcher: "ArgMatcher"

    def to_mapping(self) -> dict[str, object]:
        return {
            "type": "VarargMatcherDidNotMatchAnything",
            "program": self.program,
            "matcher": self.matcher.to_mapping(),
        }

@dataclass(frozen=True)
class OptionMissingValue(Error):
    """Rust ``Error::OptionMissingValue`` projection."""

    program: str
    option: str

    def to_mapping(self) -> dict[str, str]:
        return {
            "type": "OptionMissingValue",
            "program": self.program,
            "option": self.option,
        }

@dataclass(frozen=True)
class OptionFollowedByOptionInsteadOfValue(Error):
    """Rust ``Error::OptionFollowedByOptionInsteadOfValue`` projection."""

    program: str
    option: str
    value: str

    def to_mapping(self) -> dict[str, str]:
        return {
            "type": "OptionFollowedByOptionInsteadOfValue",
            "program": self.program,
            "option": self.option,
            "value": self.value,
        }

@dataclass(frozen=True)
class UnknownOption(Error):
    """Rust ``Error::UnknownOption`` projection."""

    program: str
    option: str

    def to_mapping(self) -> dict[str, str]:
        return {
            "type": "UnknownOption",
            "program": self.program,
            "option": self.option,
        }

@dataclass(frozen=True)
class DoubleDashNotSupportedYet(Error):
    """Rust ``Error::DoubleDashNotSupportedYet`` projection."""

    program: str

    def to_mapping(self) -> dict[str, str]:
        return {"type": "DoubleDashNotSupportedYet", "program": self.program}

@dataclass(frozen=True)
class MissingRequiredOptions(Error):
    """Rust ``Error::MissingRequiredOptions`` projection."""

    program: str
    options: tuple[str, ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "type": "MissingRequiredOptions",
            "program": self.program,
            "options": list(self.options),
        }

@dataclass(frozen=True)
class NoSpecForProgram(Error):
    """Rust ``Error::NoSpecForProgram`` projection."""

    program: str

    def to_mapping(self) -> dict[str, str]:
        return {"type": "NoSpecForProgram", "program": self.program}

@dataclass(frozen=True)
class ReadablePathNotInReadableFolders(Error):
    """Rust ``Error::ReadablePathNotInReadableFolders`` projection."""

    file: Path
    folders: tuple[Path, ...]

    def __init__(
        self,
        file: str | Path,
        folders: list[str | Path] | tuple[str | Path, ...],
    ) -> None:
        object.__setattr__(self, "file", Path(file))
        object.__setattr__(self, "folders", tuple(Path(folder) for folder in folders))

    def to_mapping(self) -> dict[str, object]:
        return {
            "type": "ReadablePathNotInReadableFolders",
            "file": str(self.file),
            "folders": [str(folder) for folder in self.folders],
        }

@dataclass(frozen=True)
class WriteablePathNotInWriteableFolders(Error):
    """Rust ``Error::WriteablePathNotInWriteableFolders`` projection."""

    file: Path
    folders: tuple[Path, ...]

    def __init__(
        self,
        file: str | Path,
        folders: list[str | Path] | tuple[str | Path, ...],
    ) -> None:
        object.__setattr__(self, "file", Path(file))
        object.__setattr__(self, "folders", tuple(Path(folder) for folder in folders))

    def to_mapping(self) -> dict[str, object]:
        return {
            "type": "WriteablePathNotInWriteableFolders",
            "file": str(self.file),
            "folders": [str(folder) for folder in self.folders],
        }

@dataclass(frozen=True)
class CannotCheckRelativePath(Error):
    """Rust ``Error::CannotCheckRelativePath`` projection."""

    file: Path

    def __init__(self, file: str | Path) -> None:
        object.__setattr__(self, "file", Path(file))

    def to_mapping(self) -> dict[str, str]:
        return {"type": "CannotCheckRelativePath", "file": str(self.file)}

@dataclass(frozen=True)
class CannotCanonicalizePath(Error):
    """Rust ``Error::CannotCanonicalizePath`` projection."""

    file: str
    error: str

    def to_mapping(self) -> dict[str, str]:
        return {
            "type": "CannotCanonicalizePath",
            "file": self.file,
            "error": self.error,
        }
