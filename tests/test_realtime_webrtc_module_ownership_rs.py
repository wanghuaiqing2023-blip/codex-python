"""Module ownership for ``codex-realtime-webrtc``."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _definitions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_lib_rs_does_not_own_native_helpers() -> None:
    definitions = _definitions(
        ROOT / "pycodex" / "realtime_webrtc" / "__init__.py"
    )

    assert "message_error" not in definitions
    assert "audio_level_to_peak" not in definitions


def test_native_rs_owns_native_helpers() -> None:
    path = ROOT / "pycodex" / "realtime_webrtc" / "native.py"

    assert path.is_file()
    assert {"message_error", "audio_level_to_peak"} <= _definitions(path)
