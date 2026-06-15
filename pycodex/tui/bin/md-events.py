"""Python boundary for Rust ``codex-tui::bin::md-events``.

The Rust binary reads all stdin, feeds it to ``pulldown_cmark::Parser``, and
prints each parser event with Rust ``Debug`` formatting. Python provides a
standard-library semantic event formatter for the common Markdown constructs
used by this diagnostic helper, keeping the module's CLI behavior usable without
pulling in a Markdown parser dependency.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional, TextIO

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bin::md-events",
    source="codex/codex-rs/tui/src/bin/md-events.rs",
    status="complete",
)


def format_stdin_read_error(error: Any) -> str:
    """Rust stderr text for a failed ``read_to_string`` call."""

    return f"failed to read stdin: {error}"


def markdown_events_debug(input_text: str) -> List[str]:
    """Return pulldown-cmark-like Debug event lines for common Markdown.

    Covered block constructs: paragraphs, ATX headings, fenced code blocks, and
    unordered lists. Covered inline constructs: text, soft breaks, emphasis,
    strong emphasis, inline code, and inline links. Unknown Markdown is emitted
    as plain paragraph text, which is safer than inventing unsupported events.
    """

    text = input_text.replace("\r\n", "\n").replace("\r", "\n")
    events: List[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "" and i == len(lines) - 1:
            break
        if not line.strip():
            i += 1
            continue

        fence = re.match(r"^```([^`]*)\s*$", line)
        if fence:
            info = fence.group(1).strip()
            body: List[str] = []
            i += 1
            while i < len(lines) and not re.match(r"^```\s*$", lines[i]):
                body.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            code = "\n".join(body)
            if body:
                code += "\n"
            events.append(f"Start(CodeBlock(Fenced({_borrowed(info)})))")
            events.append(f"Text({_borrowed(code)})")
            events.append("End(CodeBlock)")
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            level = "H" + str(len(heading.group(1)))
            events.append(f"Start(Heading {{ level: {level}, id: None, classes: [], attrs: [] }})")
            events.extend(_inline_events(heading.group(2)))
            events.append(f"End(Heading({level}))")
            i += 1
            continue

        if re.match(r"^\s*[-*+]\s+", line):
            events.append("Start(List(None))")
            while i < len(lines):
                item = re.match(r"^\s*[-*+]\s+(.*)$", lines[i])
                if item is None:
                    break
                events.append("Start(Item)")
                events.extend(_inline_events(item.group(1)))
                events.append("End(Item)")
                i += 1
            events.append("End(List(false))")
            continue

        paragraph: List[str] = []
        while (
            i < len(lines)
            and lines[i].strip()
            and not re.match(r"^(#{1,6})\s+", lines[i])
            and not re.match(r"^\s*[-*+]\s+", lines[i])
            and not re.match(r"^```", lines[i])
        ):
            paragraph.append(lines[i])
            i += 1
        events.append("Start(Paragraph)")
        for idx, part in enumerate(paragraph):
            if idx:
                events.append("SoftBreak")
            events.extend(_inline_events(part))
        events.append("End(Paragraph)")
    return events


def _inline_events(text: str) -> List[str]:
    events: List[str] = []
    pattern = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            events.append(f"Text({_borrowed(text[pos:match.start()])})")
        token = match.group(0)
        if token.startswith("**"):
            events.append("Start(Strong)")
            events.append(f"Text({_borrowed(token[2:-2])})")
            events.append("End(Strong)")
        elif token.startswith("*"):
            events.append("Start(Emphasis)")
            events.append(f"Text({_borrowed(token[1:-1])})")
            events.append("End(Emphasis)")
        elif token.startswith("`"):
            events.append(f"Code({_borrowed(token[1:-1])})")
        else:
            link = re.match(r"^\[([^\]]+)\]\(([^)]+)\)$", token)
            if link is not None:
                events.append(
                    "Start(Link { link_type: Inline, dest_url: "
                    + _borrowed(link.group(2))
                    + ", title: "
                    + _borrowed("")
                    + ", id: "
                    + _borrowed("")
                    + " })"
                )
                events.append(f"Text({_borrowed(link.group(1))})")
                events.append("End(Link)")
        pos = match.end()
    if pos < len(text):
        events.append(f"Text({_borrowed(text[pos:])})")
    if not events and text:
        events.append(f"Text({_borrowed(text)})")
    return events


def _borrowed(text: str) -> str:
    return "Borrowed(" + json.dumps(text, ensure_ascii=False) + ")"


def main(stdin: Optional[TextIO] = None, stdout: Optional[TextIO] = None, stderr: Optional[TextIO] = None) -> int:
    """Semantic CLI boundary for Rust ``main``."""

    import sys

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    try:
        input_text = stdin.read()
    except Exception as err:
        stderr.write(format_stdin_read_error(err) + "\n")
        return 1

    for event in markdown_events_debug(input_text):
        stdout.write(event + "\n")
    return 0


__all__ = [
    "RUST_MODULE",
    "format_stdin_read_error",
    "main",
    "markdown_events_debug",
]
