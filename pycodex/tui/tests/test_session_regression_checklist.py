from __future__ import annotations

from pathlib import Path


REQUIRED_P0_IDS = {
    "P0-startup",
    "P0-mcp-warning",
    "P0-input-turn",
    "P0-stream-status",
    "P0-assistant-no-dup",
    "P0-tools",
    "P0-reasoning",
    "P0-long-reply",
    "P0-exit-resume",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _table_rows(markdown: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"ID", "---"}:
            continue
        rows.append(cells)
    return rows


def test_tui_session_regression_checklist_tracks_all_p0_scenarios() -> None:
    # Rust-derived project-process guard:
    # P0 TUI closeout claims require Rust crate/module ownership, native
    # Rust/Python evidence, and Python tests for each common session scenario.
    text = (_repo_root() / "TUI_SESSION_REGRESSION_CHECKLIST.md").read_text(encoding="utf-8")
    rows = {cells[0]: cells for cells in _table_rows(text) if cells[0].startswith("P0-")}

    assert set(rows) == REQUIRED_P0_IDS
    for row_id, cells in rows.items():
        assert len(cells) == 8, row_id
        _row_id, _scenario, rust_boundary, rust_anchor, native_evidence, python_evidence, status, remaining_gap = cells
        assert "codex-" in rust_boundary, row_id
        assert rust_anchor and rust_anchor != "-", row_id
        assert "test_" in native_evidence or "ConPTY" in native_evidence, row_id
        assert "test_" in python_evidence or "tests" in python_evidence, row_id
        assert status in {"open", "in_progress", "mostly_closed", "closed"}, row_id
        assert remaining_gap and remaining_gap != "-", row_id


def test_tui_authoritative_docs_keep_terminal_product_contract() -> None:
    # Project-process guard derived from the fixed codex-tui baseline:
    # the supported product path is terminal-only, while detailed P0/P1
    # evidence remains in the common-session regression checklist.
    readme = (_repo_root() / "pycodex" / "tui" / "README.md").read_text(encoding="utf-8")
    checklist = (_repo_root() / "TUI_SESSION_REGRESSION_CHECKLIST.md").read_text(encoding="utf-8")

    assert "The supported product path is the real terminal TUI" in readme
    assert "does not\nmaintain a Textual path" in readme
    assert "event_stream" in readme
    assert "custom_terminal diff/flush" in readme
    assert "Further changes require an observable fixed-baseline behavior difference" in readme
    assert "## P0 Checklist" in checklist
    assert "## P1 Checklist" in checklist


def test_tui_session_regression_checklist_keeps_live_smoke_commands() -> None:
    text = (_repo_root() / "TUI_SESSION_REGRESSION_CHECKLIST.md").read_text(encoding="utf-8")

    assert "PYCODEX_RUN_LIVE_OAUTH_TUI" in text
    assert "python -m pycodex --no-alt-screen" in text
    assert "请分析当前这个项目是做什么的" in text
