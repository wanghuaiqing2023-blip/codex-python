"""History mention encoding/decoding for ``codex-tui::mention_codec``.

Rust source: ``codex/codex-rs/tui/src/mention_codec.rs``.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="mention_codec",
    source="codex/codex-rs/tui/src/mention_codec.rs",
)

TOOL_MENTION_SIGIL = "$"
PLUGIN_TEXT_MENTION_SIGIL = "@"


@dataclass(eq=True)
class LinkedMention:
    mention: str
    path: str


@dataclass(eq=True)
class DecodedHistoryText:
    text: str
    mentions: list[LinkedMention]


def encode_history_mentions(text: str, mentions: list[LinkedMention]) -> str:
    if not mentions or text == "":
        return text

    mentions_by_name: dict[str, Deque[str]] = defaultdict(deque)
    for mention in mentions:
        mentions_by_name[mention.mention].append(mention.path)

    out: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == TOOL_MENTION_SIGIL:
            name_start = index + 1
            if name_start < len(text) and is_mention_name_char(text[name_start]):
                name_end = name_start + 1
                while name_end < len(text) and is_mention_name_char(text[name_end]):
                    name_end += 1
                name = text[name_start:name_end]
                queue = mentions_by_name.get(name)
                if queue:
                    path = queue.popleft()
                    out.append(f"[{TOOL_MENTION_SIGIL}{name}]({path})")
                    index = name_end
                    continue
        out.append(text[index])
        index += 1
    return "".join(out)


def decode_history_mentions(text: str, *, preserve_plugin_sigil: bool = False) -> DecodedHistoryText:
    out: list[str] = []
    mentions: list[LinkedMention] = []
    index = 0
    while index < len(text):
        if text[index] == "[":
            parsed = parse_history_linked_mention(text, index)
            if parsed is not None:
                name, path, end_index = parsed
                sigil = PLUGIN_TEXT_MENTION_SIGIL if preserve_plugin_sigil and path.startswith("plugin://") else TOOL_MENTION_SIGIL
                out.append(sigil + name)
                mentions.append(LinkedMention(name, path))
                index = end_index
                continue
        out.append(text[index])
        index += 1
    return DecodedHistoryText(text="".join(out), mentions=mentions)


def parse_history_linked_mention(text: str, start: int) -> tuple[str, str, int] | None:
    parsed = parse_linked_tool_mention(text, start, TOOL_MENTION_SIGIL)
    if parsed is not None:
        name, path, _ = parsed
        if not is_common_env_var(name) and is_tool_path(path):
            return parsed

    parsed = parse_linked_tool_mention(text, start, PLUGIN_TEXT_MENTION_SIGIL)
    if parsed is not None:
        name, path, _ = parsed
        if not is_common_env_var(name) and path.startswith("plugin://"):
            return parsed
    return None


def parse_linked_tool_mention(text: str, start: int, sigil: str) -> tuple[str, str, int] | None:
    sigil_index = start + 1
    if sigil_index >= len(text) or text[sigil_index] != sigil:
        return None

    name_start = sigil_index + 1
    if name_start >= len(text) or not is_mention_name_char(text[name_start]):
        return None

    name_end = name_start + 1
    while name_end < len(text) and is_mention_name_char(text[name_end]):
        name_end += 1

    if name_end >= len(text) or text[name_end] != "]":
        return None

    path_start = name_end + 1
    while path_start < len(text) and text[path_start].isspace():
        path_start += 1
    if path_start >= len(text) or text[path_start] != "(":
        return None

    path_end = path_start + 1
    while path_end < len(text) and text[path_end] != ")":
        path_end += 1
    if path_end >= len(text) or text[path_end] != ")":
        return None

    path = text[path_start + 1 : path_end].strip()
    if not path:
        return None
    name = text[name_start:name_end]
    return name, path, path_end + 1


def is_mention_name_char(ch: str | int) -> bool:
    if isinstance(ch, int):
        ch = chr(ch)
    return ch.isascii() and (ch.isalnum() or ch in {"_", "-"})


def is_common_env_var(name: str) -> bool:
    return name.upper() in {
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "PWD",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "TERM",
        "XDG_CONFIG_HOME",
    }


def is_tool_path(path: str) -> bool:
    normalized_name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return (
        path.startswith("app://")
        or path.startswith("mcp://")
        or path.startswith("plugin://")
        or path.startswith("skill://")
        or normalized_name.lower() == "skill.md"
    )


__all__ = [
    "DecodedHistoryText",
    "LinkedMention",
    "PLUGIN_TEXT_MENTION_SIGIL",
    "RUST_MODULE",
    "TOOL_MENTION_SIGIL",
    "decode_history_mentions",
    "encode_history_mentions",
    "is_common_env_var",
    "is_mention_name_char",
    "is_tool_path",
    "parse_history_linked_mention",
    "parse_linked_tool_mention",
]
