from __future__ import annotations

from datetime import date

from pycodex.windows_sandbox.logging import (
    current_log_file_path_for_codex_home,
    log_file_path_for_utc_date,
    log_note,
)


def test_log_file_path_for_utc_date_matches_fixed_rust_name(tmp_path) -> None:
    # Rust test: logging::tests::log_file_path_for_utc_date_matches_rolling_appender_name.
    assert log_file_path_for_utc_date(tmp_path, date(2026, 5, 21)).name == "sandbox.2026-05-21.log"


def test_log_note_writes_daily_log_and_codex_home_uses_sandbox_dir(tmp_path) -> None:
    # Rust tests: log_note_writes_to_daily_rolling_log and
    # current_log_file_path_for_codex_home_uses_sandbox_dir.
    sandbox = tmp_path / ".sandbox"
    sandbox.mkdir()
    log_note("hello daily log", sandbox)

    path = current_log_file_path_for_codex_home(tmp_path)
    assert path.parent == sandbox
    assert "hello daily log" in path.read_text(encoding="utf-8")
