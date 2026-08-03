"""Rust-derived styled-cell contract for the ``/theme`` code preview.

The checked-in JSON is deliberately generated only by this module's explicit
CLI.  Normal tests load and compare it; they never update their own oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Iterable

from pycodex.tui.render.highlight import BUILTIN_THEME_NAMES
from pycodex.tui.theme_picker import PreviewDiffKind, PreviewRow, WIDE_PREVIEW_ROWS
from tests.e2e.support.vt_screen import VtColor, VtScreen, VtStyle

RUST_REVISION = "1c7832ffa37a3ab56f601497c00bfce120370bf9"
TWO_FACE_VERSION = "0.5.1"
TERMINAL_ROWS = 40
TERMINAL_COLS = 160
CONTRACT_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "tui" / "theme_preview_styles.json"


def _marker(kind: PreviewDiffKind) -> str:
    if kind == PreviewDiffKind.ADDED:
        return "+"
    if kind == PreviewDiffKind.REMOVED:
        return "-"
    return " "


def _source_sha256(rows: Iterable[PreviewRow] = WIDE_PREVIEW_ROWS) -> str:
    payload = "\n".join(
        f"{row.line_no}:{row.kind.value}:{row.code}" for row in rows
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def color_to_json(color: VtColor | None) -> Any:
    if color is None:
        return "default"
    value: Any = color.value
    if isinstance(value, tuple):
        value = list(value)
    return {"kind": color.kind, "value": value}


def style_to_json(style: VtStyle, *, ignore_foreground: bool = False) -> dict[str, Any]:
    modifiers = [
        name
        for name in ("bold", "dim", "italic", "underline", "reverse")
        if getattr(style, name)
    ]
    return {
        # A foreground on a blank cell is not visible. Ratatui may also omit
        # repainting it, leaving the prior VT foreground in that cell. Keep
        # background/modifiers (which are visible), but do not make invisible
        # whitespace foreground an accidental product contract.
        "fg": "ignored" if ignore_foreground else color_to_json(style.fg),
        "bg": color_to_json(style.bg),
        "modifiers": modifiers,
    }


def _style_runs(text: str, styles: list[VtStyle]) -> list[dict[str, Any]]:
    if not styles:
        return []
    normalized = [
        style_to_json(style, ignore_foreground=char.isspace())
        for char, style in zip(text, styles)
    ]
    result: list[dict[str, Any]] = []
    start = 0
    current = normalized[0]
    for offset, style in enumerate(normalized[1:], start=1):
        if style == current:
            continue
        result.append({"start": start, "end": offset, "style": current})
        start = offset
        current = style
    result.append({"start": start, "end": len(styles), "style": current})
    return result


def extract_preview_rows(
    screen: VtScreen,
    preview_rows: Iterable[PreviewRow],
) -> list[dict[str, Any]]:
    """Extract expected preview source rows from a final styled screen."""

    result: list[dict[str, Any]] = []
    for row in preview_rows:
        prefix = f"{row.line_no} {_marker(row.kind)}"
        probe = row.code[: min(len(row.code), 12)]
        needle = prefix + probe
        match: tuple[int, int] | None = None
        for screen_y, cells in enumerate(screen.rows):
            text = "".join(cell.char for cell in cells)
            start = text.find(needle)
            if start >= 0:
                match = (screen_y, start + len(prefix))
                break
        if match is None:
            raise AssertionError(
                f"preview row not found: line={row.line_no} kind={row.kind.value} code={row.code!r}"
            )
        screen_y, code_start = match
        cells = screen.rows[screen_y]
        available_text = "".join(cell.char for cell in cells[code_start:])
        visible_length = 0
        for expected_char, actual_char in zip(row.code, available_text):
            if expected_char != actual_char:
                break
            visible_length += 1
        visible_cells = list(cells[code_start : code_start + visible_length])
        visible_text = "".join(cell.char for cell in visible_cells)
        expected_text = row.code[:visible_length]
        if visible_length < len(probe) or visible_text != expected_text:
            raise AssertionError(
                f"preview text mismatch at source line {row.line_no}: "
                f"expected={expected_text!r} actual={visible_text!r}"
            )
        result.append(
            {
                "line_no": row.line_no,
                "kind": row.kind.value,
                "screen_y": screen_y,
                "code_start": code_start,
                "visible_text": visible_text,
                "runs": _style_runs(visible_text, [cell.style for cell in visible_cells]),
            }
        )
    return result


def extract_preview_contract(screen: VtScreen) -> list[dict[str, Any]]:
    """Extract the eight wide-preview code rows from a final styled screen."""

    return extract_preview_rows(screen, WIDE_PREVIEW_ROWS)


def extract_text_run_contract(screen: VtScreen, text: str) -> dict[str, Any]:
    """Extract one exact visible text range and its final cell styles."""

    for screen_y, cells in enumerate(screen.rows):
        row_text = "".join(cell.char for cell in cells)
        start = row_text.find(text)
        if start < 0:
            continue
        visible_cells = list(cells[start : start + len(text)])
        return {
            "screen_y": screen_y,
            "start": start,
            "visible_text": text,
            "runs": _style_runs(text, [cell.style for cell in visible_cells]),
        }
    raise AssertionError(f"styled text not found on final screen: {text!r}")


def load_theme_preview_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def generate_theme_preview_contract(native_exe: Path, output: Path = CONTRACT_PATH) -> dict[str, Any]:
    """Run the native product once per theme and explicitly rewrite the oracle."""

    if not native_exe.is_file():
        raise FileNotFoundError(f"native codex executable not found: {native_exe}")

    # Imported lazily so ordinary contract readers do not pull in the ConPTY
    # process harness or pytest.
    from tests.e2e.tui._slash_command_common import run_theme_slash_candidate, slash_candidate_pair

    rust, _python = slash_candidate_pair(native_exe)
    themes: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="codex-theme-oracle-") as artifact_root:
        artifact_dir = Path(artifact_root)
        for theme_name in BUILTIN_THEME_NAMES:
            transcript, request_count = run_theme_slash_candidate(
                rust,
                label="rust",
                theme_name=theme_name,
                artifact_dir=artifact_dir / theme_name,
                rows=TERMINAL_ROWS,
                cols=TERMINAL_COLS,
            )
            if request_count != 0:
                raise AssertionError(f"Rust /theme unexpectedly made {request_count} model requests")
            themes[theme_name] = extract_preview_contract(
                transcript.checkpoint_cells("preview", rows=TERMINAL_ROWS, cols=TERMINAL_COLS)
            )

    contract = {
        "schema_version": 1,
        "rust_revision": RUST_REVISION,
        "two_face_version": TWO_FACE_VERSION,
        "terminal": {"rows": TERMINAL_ROWS, "cols": TERMINAL_COLS},
        "preview_source_sha256": _source_sha256(),
        "theme_names": list(BUILTIN_THEME_NAMES),
        "themes": themes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return contract


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate the native Rust /theme styled-cell oracle")
    parser.add_argument("--native-exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=CONTRACT_PATH)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    contract = generate_theme_preview_contract(args.native_exe, args.output)
    print(f"wrote {len(contract['themes'])} themes to {args.output}")


if __name__ == "__main__":
    main()


__all__ = [
    "CONTRACT_PATH",
    "RUST_REVISION",
    "TERMINAL_COLS",
    "TERMINAL_ROWS",
    "TWO_FACE_VERSION",
    "extract_preview_contract",
    "extract_preview_rows",
    "extract_text_run_contract",
    "generate_theme_preview_contract",
    "load_theme_preview_contract",
    "style_to_json",
]
