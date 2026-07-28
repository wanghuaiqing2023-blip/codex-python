"""Rust-aligned port of ``execpolicy-legacy/src/program.rs``."""



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



from .arg_matcher import ArgMatcher

from .arg_resolver import PositionalArg, resolve_observed_args_with_patterns

from .arg_type import ArgType

from .error import DoubleDashNotSupportedYet, Error, MissingRequiredOptions, OptionFollowedByOptionInsteadOfValue, OptionMissingValue, UnknownOption

from .exec_call import ExecCall

from .opt import Opt, OptMetaKind

from .valid_exec import MatchedFlag, MatchedOpt, ValidExec



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
