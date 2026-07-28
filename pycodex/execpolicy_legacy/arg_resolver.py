"""Rust-aligned port of ``execpolicy-legacy/src/arg_resolver.rs``."""



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



from .arg_matcher import ArgMatcher, ArgMatcherCardinality

from .error import InternalInvariantViolation, MultipleVarargPatterns, NotEnoughArgs, PrefixOverlapsSuffix, RangeEndOutOfBounds, RangeStartExceedsEnd, UnexpectedArguments, VarargMatcherDidNotMatchAnything

from .valid_exec import MatchedArg



@dataclass(frozen=True)
class PositionalArg:
    """Rust ``PositionalArg`` projection."""

    index: int
    value: str

    def to_mapping(self) -> dict[str, int | str]:
        return {"index": self.index, "value": self.value}

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
