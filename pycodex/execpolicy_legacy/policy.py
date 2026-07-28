"""Rust-aligned port of ``execpolicy-legacy/src/policy.rs``."""



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



from .error import Error, NoSpecForProgram

from .exec_call import ExecCall

from .program import Forbidden, MatchedExec, NegativeExamplePassedCheck, PositiveExampleFailedCheck, ProgramSpec



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
