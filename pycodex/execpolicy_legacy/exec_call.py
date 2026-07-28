"""Rust-aligned port of ``execpolicy-legacy/src/exec_call.rs``."""



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
