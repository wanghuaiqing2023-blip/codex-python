"""Rust-aligned port of ``execpolicy-legacy/src/sed_command.rs``."""



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



from .error import SedCommandNotProvablySafe



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

def _parse_u64(value: str) -> int | None:
    if not value or not value.isascii() or not value.isdecimal():
        return None
    parsed = int(value, 10)
    if parsed > 2**64 - 1:
        return None
    return parsed
