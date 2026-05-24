"""Execution output protocol helpers.

Ported from ``codex/codex-rs/protocol/src/exec_output.rs``.

The Rust implementation uses encoding detectors from third-party crates. This
Python port stays in the standard library and mirrors the tested behavior with
explicit UTF-8, Windows-1252 punctuation, CP1251, CP866, Latin-1, and lossy
fallback handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Generic, TypeVar


T = TypeVar("T", str, bytes)

WINDOWS_1252_PUNCT_BYTES = frozenset((0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x99))
COMMON_CYRILLIC = frozenset("абвгдежзийклмнопрстуфхцчшщьыя")


@dataclass(frozen=True)
class StreamOutput(Generic[T]):
    text: T
    truncated_after_lines: int | None = None

    @classmethod
    def new(cls, text: str) -> "StreamOutput[str]":
        return cls(text=text)

    def from_utf8_lossy(self) -> "StreamOutput[str]":
        if isinstance(self.text, bytes):
            text = bytes_to_string_smart(self.text)
        else:
            text = str(self.text)
        return StreamOutput(text=text, truncated_after_lines=self.truncated_after_lines)


@dataclass(frozen=True)
class ExecToolCallOutput:
    exit_code: int = 0
    stdout: StreamOutput[str] = StreamOutput.new("")
    stderr: StreamOutput[str] = StreamOutput.new("")
    aggregated_output: StreamOutput[str] = StreamOutput.new("")
    duration: timedelta = timedelta(0)
    timed_out: bool = False


def bytes_to_string_smart(data: bytes) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    if _looks_like_windows_1252_punctuation(data):
        decoded = _decode_strict(data, "cp1252")
        if decoded is not None:
            return decoded

    if _has_ascii_word(data):
        decoded = _decode_strict(data, "cp1252") or _decode_strict(data, "latin1")
        if decoded is not None:
            return decoded

    cyrillic_encoding = "cp866" if any(0x80 <= byte <= 0xAF for byte in data) else "cp1251"
    decoded = _decode_strict(data, cyrillic_encoding)
    if decoded is not None and _cyrillic_score(decoded) >= 3:
        return decoded

    return data.decode("utf-8", errors="replace")


def _decode_strict(data: bytes, encoding: str) -> str | None:
    try:
        return data.decode(encoding)
    except UnicodeDecodeError:
        return None


def _looks_like_windows_1252_punctuation(data: bytes) -> bool:
    saw_extended_punctuation = False
    saw_ascii_word = False
    for byte in data:
        if byte >= 0xA0:
            return False
        if 0x80 <= byte <= 0x9F:
            if byte not in WINDOWS_1252_PUNCT_BYTES:
                return False
            saw_extended_punctuation = True
        if _is_ascii_alpha(byte):
            saw_ascii_word = True
    return saw_extended_punctuation and saw_ascii_word


def _has_ascii_word(data: bytes) -> bool:
    return any(_is_ascii_alpha(byte) for byte in data)


def _is_ascii_alpha(byte: int) -> bool:
    return (ord("A") <= byte <= ord("Z")) or (ord("a") <= byte <= ord("z"))


def _cyrillic_score(text: str) -> int:
    score = 0
    for character in text:
        if character.isspace() or character.isascii():
            continue
        lowered = character.lower()
        if lowered in COMMON_CYRILLIC:
            score += 1
        elif "\u0400" <= lowered <= "\u04ff":
            score += 0
        else:
            score -= 2
    return score
