"""Rust-aligned port of ``execpolicy-legacy/src/opt.rs``."""



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

from .arg_type import ArgType



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
