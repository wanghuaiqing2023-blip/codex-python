"""Rust-aligned port of ``execpolicy-legacy/src/valid_exec.rs``."""



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
