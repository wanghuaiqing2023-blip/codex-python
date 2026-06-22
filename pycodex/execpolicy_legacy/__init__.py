"""Dependency-light facade for Rust ``codex-execpolicy-legacy``.

Currently ported module contract:
- ``src/sed_command.rs`` safe sed print-command parser.
- ``src/arg_type.rs`` argument type validation.
- ``src/arg_matcher.rs`` argument matcher cardinality/type projection.
- ``src/valid_exec.rs`` accepted exec value objects.
- ``src/arg_resolver.rs`` positional argument pattern resolution.
- ``src/opt.rs`` command-line option value objects.
- ``src/program.rs`` program-spec argument/option checking.
- ``src/policy.rs`` policy-level program selection and forbidden matching.
- ``src/policy_parser.rs`` dependency-light policy DSL parser.
- ``src/execv_checker.rs`` path allow-list validation and system-path
  executable selection.
- ``src/main.rs`` CLI classification/output contract.
"""

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


def parse_sed_command(sed_command: str) -> None:
    """Mirror ``codex-execpolicy-legacy/src/sed_command.rs``.

    Rust currently accepts only commands shaped like ``122,202p`` where both
    bounds parse as unsigned 64-bit integers.
    """

    if sed_command.endswith("p"):
        stripped = sed_command[:-1]
        if "," in stripped:
            first, rest = stripped.split(",", 1)
            if _parse_u64(first) is not None and _parse_u64(rest) is not None:
                return None
    raise SedCommandNotProvablySafe(sed_command)


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


class OptMetaKind(str, Enum):
    FLAG = "Flag"
    VALUE = "Value"


@dataclass(frozen=True)
class OptMeta:
    """Rust ``OptMeta`` projection."""

    kind: OptMetaKind | str
    arg_type: ArgType | None = None

    def __post_init__(self) -> None:
        if isinstance(self.kind, OptMetaKind):
            object.__setattr__(self, "kind", self.kind.value)

    @classmethod
    def flag(cls) -> "OptMeta":
        return cls(OptMetaKind.FLAG)

    @classmethod
    def value(cls, arg_type: ArgType) -> "OptMeta":
        return cls(OptMetaKind.VALUE, arg_type)

    def to_mapping(self) -> dict[str, object]:
        if self.kind == OptMetaKind.FLAG.value:
            return {"type": "Flag"}
        if self.kind == OptMetaKind.VALUE.value:
            return {
                "type": "Value",
                "arg_type": self.arg_type.to_mapping() if self.arg_type else None,
            }
        raise ValueError(f"unknown OptMeta kind: {self.kind}")


@dataclass(frozen=True)
class Opt:
    """Rust ``Opt`` projection."""

    opt: str
    meta: OptMeta
    required: bool

    @classmethod
    def new(cls, opt: str, meta: OptMeta, required: bool) -> "Opt":
        return cls(opt=str(opt), meta=meta, required=bool(required))

    @classmethod
    def flag(cls, name: str) -> "Opt":
        return cls.new(name, OptMeta.flag(), False)

    @classmethod
    def value(cls, name: str, matcher: ArgMatcher, required: bool = False) -> "Opt":
        return cls.new(name, OptMeta.value(matcher.arg_type()), required)

    def name(self) -> str:
        return self.opt

    def to_mapping(self) -> dict[str, object]:
        return {
            "opt": self.opt,
            "meta": self.meta.to_mapping(),
            "required": self.required,
        }

    def __str__(self) -> str:
        return f"opt({self.opt})"


@dataclass(frozen=True)
class PositionalArg:
    """Rust ``PositionalArg`` projection."""

    index: int
    value: str

    def to_mapping(self) -> dict[str, int | str]:
        return {"index": self.index, "value": self.value}


@dataclass(frozen=True)
class ExecCall:
    """Rust ``ExecCall`` projection used by ``ProgramSpec``."""

    program: str
    args: tuple[str, ...]

    @classmethod
    def new(cls, program: str, args: list[str] | tuple[str, ...]) -> "ExecCall":
        return cls(program=str(program), args=tuple(str(arg) for arg in args))

    def to_mapping(self) -> dict[str, object]:
        return {"program": self.program, "args": list(self.args)}

    def __str__(self) -> str:
        if not self.args:
            return self.program
        return " ".join((self.program, *self.args))


@dataclass(frozen=True)
class ExecArg:
    """Rust ``main.rs`` ExecArg projection."""

    program: str
    args: tuple[str, ...] = ()

    @classmethod
    def new(cls, program: str, args: list[str] | tuple[str, ...] = ()) -> "ExecArg":
        return cls(program=str(program), args=tuple(str(arg) for arg in args))

    @classmethod
    def from_json(cls, value: str) -> "ExecArg":
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise TypeError("exec JSON must decode to an object")
        program = decoded.get("program")
        if not isinstance(program, str):
            raise TypeError("exec.program must be a string")
        args = decoded.get("args", [])
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise TypeError("exec.args must be a list of strings")
        return cls.new(program, args)

    def to_exec_call(self) -> ExecCall:
        return ExecCall.new(self.program, self.args)


MATCHED_BUT_WRITES_FILES_EXIT_CODE = 12
MIGHT_BE_SAFE_EXIT_CODE = 13
FORBIDDEN_EXIT_CODE = 14


@dataclass(frozen=True)
class MatchedArg:
    """Rust ``MatchedArg`` projection."""

    index: int
    arg_type: ArgType
    value: str

    @classmethod
    def new(cls, index: int, arg_type: ArgType, value: str) -> "MatchedArg":
        arg_type.validate(value)
        return cls(index=index, arg_type=arg_type, value=str(value))

    def to_mapping(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": self.arg_type.to_mapping(),
            "value": self.value,
        }


def resolve_observed_args_with_patterns(
    program: str,
    args: list[PositionalArg] | tuple[PositionalArg, ...],
    arg_patterns: list[ArgMatcher] | tuple[ArgMatcher, ...],
) -> list[MatchedArg]:
    """Mirror ``codex-execpolicy-legacy/src/arg_resolver.rs``."""

    observed_args = tuple(args)
    patterns = tuple(arg_patterns)
    partitioned = _partition_args(program, patterns)

    matched_args: list[MatchedArg] = []

    prefix = _get_range_checked(observed_args, 0, partitioned.num_prefix_args)
    prefix_arg_index = 0
    for pattern in partitioned.prefix_patterns:
        n = pattern.cardinality().is_exact()
        if n is None:
            raise InternalInvariantViolation("expected exact cardinality")
        for positional_arg in prefix[prefix_arg_index : prefix_arg_index + n]:
            matched_args.append(
                MatchedArg.new(
                    positional_arg.index,
                    pattern.arg_type(),
                    positional_arg.value,
                )
            )
        prefix_arg_index += n

    if partitioned.num_suffix_args > len(observed_args):
        raise NotEnoughArgs(program, observed_args, patterns)

    initial_suffix_args_index = len(observed_args) - partitioned.num_suffix_args
    if prefix_arg_index > initial_suffix_args_index:
        raise PrefixOverlapsSuffix()

    if partitioned.vararg_pattern is not None:
        pattern = partitioned.vararg_pattern
        vararg = _get_range_checked(
            observed_args,
            prefix_arg_index,
            initial_suffix_args_index,
        )
        cardinality = pattern.cardinality()
        if cardinality is ArgMatcherCardinality.ONE:
            raise InternalInvariantViolation(
                "vararg pattern should not have cardinality of one"
            )
        if cardinality is ArgMatcherCardinality.AT_LEAST_ONE and not vararg:
            raise VarargMatcherDidNotMatchAnything(program, pattern)
        for positional_arg in vararg:
            matched_args.append(
                MatchedArg.new(
                    positional_arg.index,
                    pattern.arg_type(),
                    positional_arg.value,
                )
            )

    suffix = _get_range_checked(
        observed_args,
        initial_suffix_args_index,
        len(observed_args),
    )
    suffix_arg_index = 0
    for pattern in partitioned.suffix_patterns:
        n = pattern.cardinality().is_exact()
        if n is None:
            raise InternalInvariantViolation("expected exact cardinality")
        for positional_arg in suffix[suffix_arg_index : suffix_arg_index + n]:
            matched_args.append(
                MatchedArg.new(
                    positional_arg.index,
                    pattern.arg_type(),
                    positional_arg.value,
                )
            )
        suffix_arg_index += n

    if len(matched_args) < len(observed_args):
        extra_args = _get_range_checked(observed_args, len(matched_args), len(observed_args))
        raise UnexpectedArguments(program, tuple(extra_args))

    return matched_args


class _CallableString(str):
    def __call__(self) -> str:
        return str(self)


@dataclass(frozen=True)
class MatchedOpt:
    """Rust ``MatchedOpt`` projection."""

    name: _CallableString
    value: str
    arg_type: ArgType

    @classmethod
    def new(cls, name: str, value: str, arg_type: ArgType) -> "MatchedOpt":
        arg_type.validate(value)
        return cls(name=_CallableString(name), value=str(value), arg_type=arg_type)

    def to_mapping(self) -> dict[str, object]:
        return {
            "name": str(self.name),
            "value": self.value,
            "type": self.arg_type.to_mapping(),
        }


@dataclass(frozen=True)
class MatchedFlag:
    """Rust ``MatchedFlag`` projection."""

    name: str

    @classmethod
    def new(cls, name: str) -> "MatchedFlag":
        return cls(name=str(name))

    def to_mapping(self) -> dict[str, str]:
        return {"name": self.name}


@dataclass(frozen=True)
class ValidExec:
    """Rust ``ValidExec`` projection."""

    program: str
    flags: tuple[MatchedFlag, ...]
    opts: tuple[MatchedOpt, ...]
    args: tuple[MatchedArg, ...]
    system_path: tuple[str, ...]

    @classmethod
    def new(
        cls,
        program: str,
        args: list[MatchedArg] | tuple[MatchedArg, ...],
        system_path: list[str] | tuple[str, ...],
    ) -> "ValidExec":
        return cls(
            program=str(program),
            flags=(),
            opts=(),
            args=tuple(args),
            system_path=tuple(str(path) for path in system_path),
        )

    def might_write_files(self) -> bool:
        return any(opt.arg_type.might_write_file() for opt in self.opts) or any(
            arg.arg_type.might_write_file() for arg in self.args
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "program": self.program,
            "flags": [flag.to_mapping() for flag in self.flags],
            "opts": [opt.to_mapping() for opt in self.opts],
            "args": [arg.to_mapping() for arg in self.args],
            "system_path": list(self.system_path),
        }


@dataclass(frozen=True)
class Forbidden:
    """Rust ``Forbidden`` enum projection."""

    kind: str
    program: str | None = None
    exec_call: ExecCall | None = None
    arg: str | None = None
    exec: ValidExec | None = None

    @classmethod
    def program_cause(cls, program: str, exec_call: ExecCall) -> "Forbidden":
        return cls(kind="Program", program=program, exec_call=exec_call)

    @classmethod
    def arg_cause(cls, arg: str, exec_call: ExecCall) -> "Forbidden":
        return cls(kind="Arg", arg=arg, exec_call=exec_call)

    @classmethod
    def exec_cause(cls, exec: ValidExec) -> "Forbidden":
        return cls(kind="Exec", exec=exec)

    def to_mapping(self) -> dict[str, object]:
        if self.kind == "Program":
            return {
                "type": "Program",
                "program": self.program,
                "exec_call": self.exec_call.to_mapping() if self.exec_call else None,
            }
        if self.kind == "Arg":
            return {
                "type": "Arg",
                "arg": self.arg,
                "exec_call": self.exec_call.to_mapping() if self.exec_call else None,
            }
        if self.kind == "Exec":
            return {
                "type": "Exec",
                "exec": self.exec.to_mapping() if self.exec else None,
            }
        raise ValueError(f"unknown Forbidden kind: {self.kind}")


@dataclass(frozen=True)
class MatchedExec:
    """Rust ``MatchedExec`` enum projection."""

    kind: str
    exec: ValidExec | None = None
    cause: Forbidden | None = None
    reason: str | None = None

    @classmethod
    def match(cls, exec: ValidExec) -> "MatchedExec":
        return cls(kind="Match", exec=exec)

    @classmethod
    def forbidden(cls, cause: Forbidden, reason: str) -> "MatchedExec":
        return cls(kind="Forbidden", cause=cause, reason=reason)

    def to_mapping(self) -> dict[str, object]:
        if self.kind == "Match":
            return {"type": "Match", "exec": self.exec.to_mapping() if self.exec else None}
        if self.kind == "Forbidden":
            return {
                "type": "Forbidden",
                "cause": self.cause.to_mapping() if self.cause else None,
                "reason": self.reason,
            }
        raise ValueError(f"unknown MatchedExec kind: {self.kind}")


@dataclass(frozen=True)
class PositiveExampleFailedCheck:
    """Rust ``PositiveExampleFailedCheck`` projection."""

    program: str
    args: tuple[str, ...]
    error: Error


@dataclass(frozen=True)
class NegativeExamplePassedCheck:
    """Rust ``NegativeExamplePassedCheck`` projection."""

    program: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class ForbiddenProgramRegex:
    """Rust ``ForbiddenProgramRegex`` projection used by ``Policy``."""

    regex: str | Pattern[str]
    reason: str

    def compiled(self) -> Pattern[str]:
        if isinstance(self.regex, str):
            return re.compile(self.regex)
        return self.regex


@dataclass(frozen=True)
class ProgramSpec:
    """Rust ``ProgramSpec`` projection."""

    program: str
    system_path: tuple[str, ...]
    option_bundling: bool
    combined_format: bool
    allowed_options: dict[str, Opt]
    arg_patterns: tuple[ArgMatcher, ...]
    forbidden: str | None = None
    should_match: tuple[tuple[str, ...], ...] = ()
    should_not_match: tuple[tuple[str, ...], ...] = ()
    required_options: frozenset[str] = frozenset()

    @classmethod
    def new(
        cls,
        program: str,
        system_path: list[str] | tuple[str, ...],
        option_bundling: bool,
        combined_format: bool,
        allowed_options: dict[str, Opt],
        arg_patterns: list[ArgMatcher] | tuple[ArgMatcher, ...],
        forbidden: str | None = None,
        should_match: list[list[str]] | tuple[tuple[str, ...], ...] = (),
        should_not_match: list[list[str]] | tuple[tuple[str, ...], ...] = (),
    ) -> "ProgramSpec":
        required_options = frozenset(
            name for name, opt in allowed_options.items() if opt.required
        )
        return cls(
            program=str(program),
            system_path=tuple(str(path) for path in system_path),
            option_bundling=bool(option_bundling),
            combined_format=bool(combined_format),
            allowed_options=dict(allowed_options),
            arg_patterns=tuple(arg_patterns),
            forbidden=forbidden,
            should_match=tuple(tuple(str(arg) for arg in args) for args in should_match),
            should_not_match=tuple(
                tuple(str(arg) for arg in args) for args in should_not_match
            ),
            required_options=required_options,
        )

    def check(self, exec_call: ExecCall) -> MatchedExec:
        expecting_option_value: tuple[str, ArgType] | None = None
        positional_args: list[PositionalArg] = []
        matched_flags: list[MatchedFlag] = []
        matched_opts: list[MatchedOpt] = []

        for index, arg in enumerate(exec_call.args):
            if expecting_option_value is not None:
                name, arg_type = expecting_option_value
                if arg.startswith("-"):
                    raise OptionFollowedByOptionInsteadOfValue(self.program, name, arg)
                matched_opts.append(MatchedOpt.new(name, arg, arg_type))
                expecting_option_value = None
            elif arg == "--":
                raise DoubleDashNotSupportedYet(self.program)
            elif arg.startswith("-"):
                opt = self.allowed_options.get(arg)
                if opt is not None:
                    if opt.meta.kind == OptMetaKind.FLAG.value:
                        matched_flags.append(MatchedFlag.new(arg))
                        continue
                    if opt.meta.kind == OptMetaKind.VALUE.value and opt.meta.arg_type is not None:
                        expecting_option_value = (arg, opt.meta.arg_type)
                        continue
                raise UnknownOption(self.program, arg)
            else:
                positional_args.append(PositionalArg(index=index, value=arg))

        if expecting_option_value is not None:
            name, _arg_type = expecting_option_value
            raise OptionMissingValue(self.program, name)

        matched_args = resolve_observed_args_with_patterns(
            self.program,
            positional_args,
            self.arg_patterns,
        )

        matched_opt_names = {str(opt.name) for opt in matched_opts}
        if not matched_opt_names.issuperset(self.required_options):
            missing = tuple(sorted(self.required_options.difference(matched_opt_names)))
            raise MissingRequiredOptions(self.program, missing)

        exec_match = ValidExec(
            program=self.program,
            flags=tuple(matched_flags),
            opts=tuple(matched_opts),
            args=tuple(matched_args),
            system_path=self.system_path,
        )
        if self.forbidden is not None:
            return MatchedExec.forbidden(Forbidden.exec_cause(exec_match), self.forbidden)
        return MatchedExec.match(exec_match)

    def verify_should_match_list(self) -> list[PositiveExampleFailedCheck]:
        violations: list[PositiveExampleFailedCheck] = []
        for good in self.should_match:
            exec_call = ExecCall(program=self.program, args=good)
            try:
                self.check(exec_call)
            except Error as error:
                violations.append(
                    PositiveExampleFailedCheck(
                        program=self.program,
                        args=good,
                        error=error,
                    )
                )
        return violations

    def verify_should_not_match_list(self) -> list[NegativeExamplePassedCheck]:
        violations: list[NegativeExamplePassedCheck] = []
        for bad in self.should_not_match:
            exec_call = ExecCall(program=self.program, args=bad)
            try:
                self.check(exec_call)
            except Error:
                continue
            violations.append(
                NegativeExamplePassedCheck(program=self.program, args=bad)
            )
        return violations


@dataclass(frozen=True)
class Policy:
    """Rust ``Policy`` projection."""

    programs: dict[str, tuple[ProgramSpec, ...]]
    forbidden_program_regexes: tuple[ForbiddenProgramRegex, ...] = ()
    forbidden_substrings_pattern: Pattern[str] | None = None

    @classmethod
    def new(
        cls,
        programs: dict[str, list[ProgramSpec] | tuple[ProgramSpec, ...]],
        forbidden_program_regexes: (
            list[ForbiddenProgramRegex] | tuple[ForbiddenProgramRegex, ...]
        ) = (),
        forbidden_substrings: list[str] | tuple[str, ...] = (),
    ) -> "Policy":
        forbidden_substrings_pattern = None
        if forbidden_substrings:
            escaped_substrings = "|".join(re.escape(item) for item in forbidden_substrings)
            forbidden_substrings_pattern = re.compile(f"({escaped_substrings})")
        return cls(
            programs={program: tuple(specs) for program, specs in programs.items()},
            forbidden_program_regexes=tuple(forbidden_program_regexes),
            forbidden_substrings_pattern=forbidden_substrings_pattern,
        )

    def check(self, exec_call: ExecCall) -> MatchedExec:
        program = exec_call.program
        for forbidden in self.forbidden_program_regexes:
            if forbidden.compiled().search(program):
                return MatchedExec.forbidden(
                    Forbidden.program_cause(program, exec_call),
                    forbidden.reason,
                )

        for arg in exec_call.args:
            if (
                self.forbidden_substrings_pattern is not None
                and self.forbidden_substrings_pattern.search(arg)
            ):
                return MatchedExec.forbidden(
                    Forbidden.arg_cause(arg, exec_call),
                    f"arg `{arg}` contains forbidden substring",
                )

        last_error: Error = NoSpecForProgram(program)
        for spec in self.programs.get(program, ()):
            try:
                return spec.check(exec_call)
            except Error as error:
                last_error = error
        raise last_error

    def check_each_good_list_individually(self) -> list[PositiveExampleFailedCheck]:
        violations: list[PositiveExampleFailedCheck] = []
        for spec_list in self.programs.values():
            for spec in spec_list:
                violations.extend(spec.verify_should_match_list())
        return violations

    def check_each_bad_list_individually(self) -> list[NegativeExamplePassedCheck]:
        violations: list[NegativeExamplePassedCheck] = []
        for spec_list in self.programs.values():
            for spec in spec_list:
                violations.extend(spec.verify_should_not_match_list())
        return violations


@dataclass(frozen=True)
class ExecvChecker:
    """Rust ``ExecvChecker`` projection.

    The caller supplies readable/writeable folders in canonical form, matching
    the Rust module contract.
    """

    execv_policy: Policy

    @classmethod
    def new(cls, execv_policy: Policy) -> "ExecvChecker":
        return cls(execv_policy=execv_policy)

    def match(self, exec_call: ExecCall) -> MatchedExec:
        return self.execv_policy.check(exec_call)

    def check(
        self,
        valid_exec: ValidExec,
        cwd: str | Path | None,
        readable_folders: list[str | Path] | tuple[str | Path, ...],
        writeable_folders: list[str | Path] | tuple[str | Path, ...],
    ) -> str:
        readable_roots = tuple(Path(folder) for folder in readable_folders)
        writeable_roots = tuple(Path(folder) for folder in writeable_folders)

        for arg_type, value in [
            *((arg.arg_type, arg.value) for arg in valid_exec.args),
            *((opt.arg_type, opt.value) for opt in valid_exec.opts),
        ]:
            if arg_type.kind == ArgTypeKind.READABLE_FILE.value:
                readable_file = _ensure_absolute_path(value, cwd)
                _check_path_in_folders(
                    readable_file,
                    readable_roots,
                    ReadablePathNotInReadableFolders,
                )
            elif arg_type.kind == ArgTypeKind.WRITEABLE_FILE.value:
                writeable_file = _ensure_absolute_path(value, cwd)
                _check_path_in_folders(
                    writeable_file,
                    writeable_roots,
                    WriteablePathNotInWriteableFolders,
                )

        program = valid_exec.program
        for system_path in valid_exec.system_path:
            if _is_executable_file(system_path):
                program = system_path
                break
        return program


def check_command(policy: Policy, exec_arg: ExecArg, require_safe: bool = False) -> tuple[dict[str, object], int]:
    """Mirror Rust ``main.rs::check_command``."""

    exec_call = exec_arg.to_exec_call()
    try:
        matched = policy.check(exec_call)
    except Error as error:
        exit_code = MIGHT_BE_SAFE_EXIT_CODE if require_safe else 0
        return (
            {
                "result": "unverified",
                "error": error.to_mapping() if hasattr(error, "to_mapping") else str(error),
            },
            exit_code,
        )

    if matched.kind == "Match" and matched.exec is not None:
        if matched.exec.might_write_files():
            exit_code = MATCHED_BUT_WRITES_FILES_EXIT_CODE if require_safe else 0
            return (
                {"result": "match", "match": _valid_exec_to_rust_json(matched.exec)},
                exit_code,
            )
        return (
            {"result": "safe", "match": _valid_exec_to_rust_json(matched.exec)},
            0,
        )

    if matched.kind == "Forbidden" and matched.cause is not None:
        exit_code = FORBIDDEN_EXIT_CODE if require_safe else 0
        return (
            {
                "result": "forbidden",
                "reason": matched.reason or "",
                "cause": _forbidden_to_rust_json(matched.cause),
            },
            exit_code,
        )

    raise InternalInvariantViolation(f"unknown matched exec result: {matched!r}")


def run_main(
    argv: list[str] | tuple[str, ...],
    stdout: TextIOBase | None = None,
    stderr: TextIOBase | None = None,
) -> int:
    """Dependency-light entry point for Rust ``src/main.rs`` behavior."""

    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    args = list(argv)
    require_safe = False
    policy_path: Path | None = None

    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--require-safe":
            require_safe = True
            del args[index]
            continue
        if arg in {"--policy", "-p"}:
            if index + 1 >= len(args):
                raise ValueError(f"{arg} requires a path")
            policy_path = Path(args[index + 1])
            del args[index : index + 2]
            continue
        break

    if not args:
        print("no command provided", file=err)
        return 1

    command = args[0]
    if command == "check":
        if len(args) == 1:
            print("no command provided", file=err)
            return 1
        exec_arg = ExecArg.new(args[1], args[2:])
    elif command == "check-json":
        if len(args) != 2:
            raise ValueError("check-json requires one JSON argument")
        exec_arg = ExecArg.from_json(args[1])
    else:
        raise ValueError(f"unknown command: {command}")

    if policy_path is None:
        policy = get_default_policy()
    else:
        policy = PolicyParser.new(str(policy_path), policy_path.read_text(encoding="utf-8")).parse()

    output, exit_code = check_command(policy, exec_arg, require_safe)
    print(json.dumps(output, separators=(",", ":")), file=out)
    return exit_code


def main(
    argv: list[str] | tuple[str, ...] | None = None,
    stdout: TextIOBase | None = None,
    stderr: TextIOBase | None = None,
) -> int:
    """Run the dependency-light legacy execpolicy CLI wrapper."""

    return run_main(tuple(sys.argv[1:] if argv is None else argv), stdout, stderr)


@dataclass(frozen=True)
class PolicyParser:
    """Rust ``PolicyParser`` projection."""

    policy_source: str
    unparsed_policy: str

    @classmethod
    def new(cls, policy_source: str, unparsed_policy: str) -> "PolicyParser":
        return cls(policy_source=str(policy_source), unparsed_policy=str(unparsed_policy))

    def parse(self) -> Policy:
        builder = _PolicyBuilder()

        def define_program(
            program: str,
            system_path: list[str] | None = None,
            option_bundling: bool | None = None,
            combined_format: bool | None = None,
            options: list[Opt] | None = None,
            args: list[ArgMatcher | str] | None = None,
            forbidden: str | None = None,
            should_match: list[list[str]] | None = None,
            should_not_match: list[list[str]] | None = None,
        ) -> None:
            allowed_options: dict[str, Opt] = {}
            for option in options or []:
                name = option.name()
                if name in allowed_options:
                    raise ValueError(f"duplicate flag: {name}")
                allowed_options[name] = option

            arg_patterns: list[ArgMatcher] = []
            for arg in args or []:
                matcher = ArgMatcher.unpack_value(arg)
                if matcher is None:
                    raise TypeError(f"cannot unpack policy arg matcher: {arg!r}")
                arg_patterns.append(matcher)

            builder.add_program_spec(
                ProgramSpec.new(
                    program=program,
                    system_path=system_path or [],
                    option_bundling=option_bundling or False,
                    combined_format=combined_format or False,
                    allowed_options=allowed_options,
                    arg_patterns=arg_patterns,
                    forbidden=forbidden,
                    should_match=should_match or [],
                    should_not_match=should_not_match or [],
                )
            )

        def forbid_substrings(strings: list[str]) -> None:
            builder.add_forbidden_substrings([str(item) for item in strings])

        def forbid_program_regex(regex: str, reason: str) -> None:
            re.compile(regex)
            builder.add_forbidden_program_regex(
                ForbiddenProgramRegex(regex=regex, reason=reason)
            )

        def opt(name: str, type: ArgMatcher, required: bool | None = None) -> Opt:  # noqa: A002
            matcher = ArgMatcher.unpack_value(type)
            if matcher is None:
                raise TypeError(f"cannot unpack option matcher: {type!r}")
            return Opt.value(name, matcher, required=required or False)

        def flag(name: str) -> Opt:
            return Opt.flag(name)

        globals_map: dict[str, object] = {
            "__builtins__": {},
            "ARG_OPAQUE_VALUE": ArgMatcher.opaque_non_file(),
            "ARG_RFILE": ArgMatcher.readable_file(),
            "ARG_WFILE": ArgMatcher.writeable_file(),
            "ARG_RFILES": ArgMatcher.readable_files(),
            "ARG_RFILES_OR_CWD": ArgMatcher.readable_files_or_cwd(),
            "ARG_POS_INT": ArgMatcher.positive_integer(),
            "ARG_SED_COMMAND": ArgMatcher.sed_command(),
            "ARG_UNVERIFIED_VARARGS": ArgMatcher.unverified_varargs(),
            "define_program": define_program,
            "forbid_substrings": forbid_substrings,
            "forbid_program_regex": forbid_program_regex,
            "opt": opt,
            "flag": flag,
        }
        code = compile(self.unparsed_policy, self.policy_source, "exec")
        exec(code, globals_map, globals_map)
        return builder.build()


class _PolicyBuilder:
    def __init__(self) -> None:
        self.programs: dict[str, list[ProgramSpec]] = {}
        self.forbidden_program_regexes: list[ForbiddenProgramRegex] = []
        self.forbidden_substrings: list[str] = []

    def add_program_spec(self, program_spec: ProgramSpec) -> None:
        self.programs.setdefault(program_spec.program, []).append(program_spec)

    def add_forbidden_substrings(self, substrings: list[str]) -> None:
        self.forbidden_substrings.extend(substrings)

    def add_forbidden_program_regex(self, forbidden: ForbiddenProgramRegex) -> None:
        self.forbidden_program_regexes.append(forbidden)

    def build(self) -> Policy:
        return Policy.new(
            programs=self.programs,
            forbidden_program_regexes=self.forbidden_program_regexes,
            forbidden_substrings=self.forbidden_substrings,
        )


def _default_policy_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "codex"
        / "codex-rs"
        / "execpolicy-legacy"
        / "src"
        / "default.policy"
    )


def get_default_policy() -> Policy:
    default_policy_path = _default_policy_path()
    return PolicyParser.new(
        "#default",
        default_policy_path.read_text(encoding="utf-8"),
    ).parse()


@dataclass(frozen=True)
class _PartitionedArgs:
    num_prefix_args: int = 0
    num_suffix_args: int = 0
    prefix_patterns: tuple[ArgMatcher, ...] = ()
    suffix_patterns: tuple[ArgMatcher, ...] = ()
    vararg_pattern: ArgMatcher | None = None


def _partition_args(
    program: str,
    arg_patterns: tuple[ArgMatcher, ...],
) -> _PartitionedArgs:
    in_prefix = True
    num_prefix_args = 0
    num_suffix_args = 0
    prefix_patterns: list[ArgMatcher] = []
    suffix_patterns: list[ArgMatcher] = []
    vararg_pattern: ArgMatcher | None = None

    for pattern in arg_patterns:
        exact = pattern.cardinality().is_exact()
        if exact is not None:
            if in_prefix:
                prefix_patterns.append(pattern)
                num_prefix_args += exact
            else:
                suffix_patterns.append(pattern)
                num_suffix_args += exact
        elif vararg_pattern is None:
            vararg_pattern = pattern
            in_prefix = False
        else:
            raise MultipleVarargPatterns(program, vararg_pattern, pattern)

    return _PartitionedArgs(
        num_prefix_args=num_prefix_args,
        num_suffix_args=num_suffix_args,
        prefix_patterns=tuple(prefix_patterns),
        suffix_patterns=tuple(suffix_patterns),
        vararg_pattern=vararg_pattern,
    )


def _get_range_checked(
    values: tuple[PositionalArg, ...],
    start: int,
    end: int,
) -> tuple[PositionalArg, ...]:
    if start > end:
        raise RangeStartExceedsEnd(start, end)
    if end > len(values):
        raise RangeEndOutOfBounds(end, len(values))
    return values[start:end]


def _ensure_absolute_path(path: str, cwd: str | Path | None) -> Path:
    file = Path(path)
    try:
        if not file.is_absolute():
            if cwd is None:
                raise CannotCheckRelativePath(file)
            file = Path(cwd) / file
        return file.resolve(strict=False)
    except CannotCheckRelativePath:
        raise
    except OSError as exc:
        raise CannotCanonicalizePath(path, exc.__class__.__name__) from exc


def _check_path_in_folders(
    file: Path,
    folders: tuple[Path, ...],
    error_type: type[ReadablePathNotInReadableFolders]
    | type[WriteablePathNotInWriteableFolders],
) -> None:
    for folder in folders:
        try:
            file.relative_to(folder)
            return None
        except ValueError:
            continue
    raise error_type(file, folders)


def _is_executable_file(path: str) -> bool:
    file = Path(path)
    if not file.is_file():
        return False
    if os.name == "nt":
        return True
    return os.access(file, os.X_OK)


def _arg_type_to_rust_json(arg_type: ArgType) -> object:
    if arg_type.kind == "Literal":
        return {"Literal": arg_type.literal_value or ""}
    return str(arg_type.kind)


def _valid_exec_to_rust_json(valid_exec: ValidExec) -> dict[str, object]:
    return {
        "program": valid_exec.program,
        "flags": [{"name": flag.name} for flag in valid_exec.flags],
        "opts": [
            {
                "name": str(opt.name),
                "value": opt.value,
                "type": _arg_type_to_rust_json(opt.arg_type),
            }
            for opt in valid_exec.opts
        ],
        "args": [
            {
                "index": arg.index,
                "type": _arg_type_to_rust_json(arg.arg_type),
                "value": arg.value,
            }
            for arg in valid_exec.args
        ],
        "system_path": list(valid_exec.system_path),
    }


def _exec_call_to_rust_json(exec_call: ExecCall) -> dict[str, object]:
    return {"program": exec_call.program, "args": list(exec_call.args)}


def _forbidden_to_rust_json(forbidden: Forbidden) -> dict[str, object]:
    if forbidden.kind == "Program" and forbidden.exec_call is not None:
        return {
            "Program": {
                "program": forbidden.program,
                "exec_call": _exec_call_to_rust_json(forbidden.exec_call),
            }
        }
    if forbidden.kind == "Arg" and forbidden.exec_call is not None:
        return {
            "Arg": {
                "arg": forbidden.arg,
                "exec_call": _exec_call_to_rust_json(forbidden.exec_call),
            }
        }
    if forbidden.kind == "Exec" and forbidden.exec is not None:
        return {"Exec": {"exec": _valid_exec_to_rust_json(forbidden.exec)}}
    raise InternalInvariantViolation(f"unknown forbidden cause: {forbidden!r}")


def _parse_u64(value: str) -> int | None:
    if not value or not value.isascii() or not value.isdecimal():
        return None
    parsed = int(value, 10)
    if parsed > 2**64 - 1:
        return None
    return parsed


__all__ = [
    "ArgMatcher",
    "ArgMatcherCardinality",
    "ArgMatcherKind",
    "ArgType",
    "ArgTypeKind",
    "CannotCanonicalizePath",
    "CannotCheckRelativePath",
    "DoubleDashNotSupportedYet",
    "EmptyFileName",
    "Error",
    "ExecArg",
    "ExecCall",
    "ExecvChecker",
    "FORBIDDEN_EXIT_CODE",
    "Forbidden",
    "ForbiddenProgramRegex",
    "InvalidPositiveInteger",
    "InternalInvariantViolation",
    "LiteralValueDidNotMatch",
    "MATCHED_BUT_WRITES_FILES_EXIT_CODE",
    "MatchedArg",
    "MatchedExec",
    "MatchedFlag",
    "MatchedOpt",
    "MissingRequiredOptions",
    "MIGHT_BE_SAFE_EXIT_CODE",
    "MultipleVarargPatterns",
    "NegativeExamplePassedCheck",
    "NoSpecForProgram",
    "NotEnoughArgs",
    "Opt",
    "OptMeta",
    "OptMetaKind",
    "OptionFollowedByOptionInsteadOfValue",
    "OptionMissingValue",
    "PositionalArg",
    "PositiveExampleFailedCheck",
    "Policy",
    "PolicyParser",
    "PrefixOverlapsSuffix",
    "ProgramSpec",
    "RangeEndOutOfBounds",
    "RangeStartExceedsEnd",
    "ReadablePathNotInReadableFolders",
    "SedCommandNotProvablySafe",
    "UnexpectedArguments",
    "UnknownOption",
    "ValidExec",
    "VarargMatcherDidNotMatchAnything",
    "WriteablePathNotInWriteableFolders",
    "check_command",
    "get_default_policy",
    "main",
    "parse_sed_command",
    "resolve_observed_args_with_patterns",
    "run_main",
]
