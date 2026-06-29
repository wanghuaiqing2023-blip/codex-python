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


def test_tui_closeout_plan_marks_p13_common_status_semantics_closed() -> None:
    # Rust-derived project-process guard:
    # P1.3 startup/status now has Rust source/test anchors plus native
    # Rust/Python current-screen evidence for common-session behavior.
    text = (_repo_root() / "TUI_CLOSEOUT_PRIORITY_PLAN.md").read_text(encoding="utf-8")
    rows = {cells[0]: cells for cells in _table_rows(text) if cells[0].startswith("P1.")}

    assert "P1.3" in rows
    p13 = rows["P1.3"]
    assert len(p13) == 5
    assert "Common-session startup/status semantics are closed" in p13[3]
    assert "post-turn ready state" in p13[4]
    assert "native Rust/Python evidence" in p13[4]
    assert "P1.3 is now closed for common-session semantics" in text
    assert "Continue P1.3" not in text
    assert "Rust's ` \u00b7 ` status-line separator" in text


def test_tui_session_regression_checklist_keeps_live_smoke_commands() -> None:
    text = (_repo_root() / "TUI_SESSION_REGRESSION_CHECKLIST.md").read_text(encoding="utf-8")

    assert "PYCODEX_RUN_LIVE_OAUTH_TUI" in text
    assert "python -m pycodex --no-alt-screen" in text
    assert "请分析当前这个项目是做什么的" in text
