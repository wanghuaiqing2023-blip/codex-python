import asyncio
from datetime import datetime, timezone
from pathlib import Path

from pycodex.state import file_modified_time_utc


def _run(coro):
    return asyncio.run(coro)


def test_file_modified_time_utc_returns_utc_timestamp(tmp_path: Path) -> None:
    # Rust crate: codex-state
    # Rust module/item: src/paths.rs::file_modified_time_utc
    # Behavior contract: read filesystem metadata and convert modified time to UTC.
    path = tmp_path / "sample.txt"
    path.write_text("hello", encoding="utf-8")

    result = _run(file_modified_time_utc(path))

    assert isinstance(result, datetime)
    assert result.tzinfo is timezone.utc
    assert abs(result.timestamp() - path.stat().st_mtime) < 1


def test_file_modified_time_utc_returns_none_for_missing_path(tmp_path: Path) -> None:
    # Rust crate: codex-state
    # Rust module/item: src/paths.rs::file_modified_time_utc
    # Behavior contract: metadata errors are swallowed and represented as None.
    result = _run(file_modified_time_utc(tmp_path / "missing.txt"))

    assert result is None


def test_file_modified_time_utc_returns_none_when_stat_fails(monkeypatch) -> None:
    # Rust crate: codex-state
    # Rust module/item: src/paths.rs::file_modified_time_utc
    # Behavior contract: metadata extraction errors are swallowed.
    def raise_os_error(self):
        raise OSError("metadata unavailable")

    monkeypatch.setattr(Path, "stat", raise_os_error)

    assert _run(file_modified_time_utc("any-path")) is None
