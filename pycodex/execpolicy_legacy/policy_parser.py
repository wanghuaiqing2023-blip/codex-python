"""Rust-aligned port of ``execpolicy-legacy/src/policy_parser.rs``."""



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

from .opt import Opt

from .policy import Policy

from .program import ProgramSpec



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

@dataclass(frozen=True)
class ForbiddenProgramRegex:
    """Rust ``ForbiddenProgramRegex`` projection used by ``Policy``."""

    regex: str | Pattern[str]
    reason: str

    def compiled(self) -> Pattern[str]:
        if isinstance(self.regex, str):
            return re.compile(self.regex)
        return self.regex

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
