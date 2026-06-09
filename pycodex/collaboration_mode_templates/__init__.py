"""Port of Rust ``codex-collaboration-mode-templates``.

Rust source:
- ``codex/codex-rs/collaboration-mode-templates/src/lib.rs``

The Rust crate exposes four ``include_str!`` constants. Python keeps the same
public constant shape by loading package-local template files at import time.
"""

from __future__ import annotations

from importlib.resources import files


def _template_text(name: str) -> str:
    return files(__package__).joinpath("templates", name).read_text(encoding="utf-8")


PLAN = _template_text("plan.md")
DEFAULT = _template_text("default.md")
EXECUTE = _template_text("execute.md")
PAIR_PROGRAMMING = _template_text("pair_programming.md")


__all__ = [
    "DEFAULT",
    "EXECUTE",
    "PAIR_PROGRAMMING",
    "PLAN",
]
