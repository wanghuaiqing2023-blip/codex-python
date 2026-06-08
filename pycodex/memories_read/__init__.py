"""Python port of ``codex-memories-read`` public API.

Rust source:
- ``codex/codex-rs/memories/read/src/lib.rs``
"""

from __future__ import annotations

from pathlib import Path

from pycodex.utils.absolute_path import AbsolutePathBuf


def memory_root(codex_home: AbsolutePathBuf | str | Path) -> AbsolutePathBuf:
    base = codex_home if isinstance(codex_home, AbsolutePathBuf) else AbsolutePathBuf.from_absolute_path_checked(codex_home)
    return base.join("memories")


__all__ = ["memory_root"]
