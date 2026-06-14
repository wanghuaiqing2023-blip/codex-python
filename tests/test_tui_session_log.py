import json
from dataclasses import dataclass

from pycodex.tui.app_event import AppEvent
from pycodex.tui.session_log import (
    SessionLogger,
    log_inbound_app_event,
    log_outbound_op,
    log_session_end,
    maybe_init,
    write_record,
)


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@dataclass
class Provider:
    name: str


@dataclass
class Config:
    log_dir: object
    cwd: str
    model: str
    model_provider_id: str
    model_provider: Provider


def test_maybe_init_respects_env_and_writes_header(tmp_path) -> None:
    # Rust source: session_log.rs::maybe_init.
    logger = SessionLogger.new()
    config = Config(tmp_path, "/repo", "gpt-5", "openai", Provider("OpenAI"))
    explicit = tmp_path / "session.jsonl"

    maybe_init(config, env={"CODEX_TUI_RECORD_SESSION": "0", "CODEX_TUI_SESSION_LOG_PATH": str(explicit)}, logger=logger)
    assert not logger.is_enabled()

    maybe_init(config, env={"CODEX_TUI_RECORD_SESSION": "yes", "CODEX_TUI_SESSION_LOG_PATH": str(explicit)}, logger=logger)
    rows = _read_jsonl(explicit)
    assert rows[0]["dir"] == "meta"
    assert rows[0]["kind"] == "session_start"
    assert rows[0]["cwd"] == "/repo"
    assert rows[0]["model"] == "gpt-5"
    assert rows[0]["model_provider_id"] == "openai"
    assert rows[0]["model_provider_name"] == "OpenAI"


def test_logger_open_truncates_and_writes_json_lines(tmp_path) -> None:
    path = tmp_path / "nested" / "session.jsonl"
    path.parent.mkdir()
    path.write_text("old\n", encoding="utf-8")
    logger = SessionLogger.new()
    logger.open(path)
    logger.write_json_line({"kind": "one"})
    assert _read_jsonl(path) == [{"kind": "one"}]


def test_logger_open_keeps_first_file_like_once_lock(tmp_path) -> None:
    # Rust: SessionLogger::open uses OnceLock::get_or_init, so later opens do not replace the file.
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    logger = SessionLogger.new()

    logger.open(first)
    logger.open(second)
    logger.write_json_line({"kind": "kept"})

    assert _read_jsonl(first) == [{"kind": "kept"}]
    assert second.read_text(encoding="utf-8") == ""


def test_inbound_app_event_records_special_variants(tmp_path) -> None:
    path = tmp_path / "session.jsonl"
    logger = SessionLogger.new()
    logger.open(path)

    class Cell:
        def transcript_lines(self, _width):
            return ["a", "b"]

    log_inbound_app_event(AppEvent.new_session(), logger)
    log_inbound_app_event(AppEvent.clear_ui(), logger)
    log_inbound_app_event(AppEvent.insert_history_cell(Cell()), logger)
    log_inbound_app_event(AppEvent.start_file_search("abc"), logger)
    log_inbound_app_event(AppEvent.file_search_result("abc", [1, 2, 3]), logger)

    rows = _read_jsonl(path)
    assert [row["kind"] for row in rows] == [
        "new_session",
        "clear_ui",
        "insert_history_cell",
        "file_search_start",
        "file_search_result",
    ]
    assert rows[2]["lines"] == 2
    assert rows[3]["query"] == "abc"
    assert rows[4]["matches"] == 3


def test_inbound_app_event_records_generic_variant_and_pet_results(tmp_path) -> None:
    path = tmp_path / "session.jsonl"
    logger = SessionLogger.new()
    logger.open(path)

    log_inbound_app_event(AppEvent.of("PetPreviewLoaded", request_id=7, result="pet"), logger)
    log_inbound_app_event(AppEvent.of("PetSelectionLoaded", request_id=8, pet_id="fox", result=RuntimeError("x")), logger)
    log_inbound_app_event(AppEvent.commit_tick(), logger)

    rows = _read_jsonl(path)
    assert rows[0]["variant"] == "PetPreviewLoaded"
    assert rows[0]["request_id"] == 7
    assert rows[0]["ok"] is True
    assert rows[1]["variant"] == "PetSelectionLoaded"
    assert rows[1]["pet_id"] == "fox"
    assert rows[1]["ok"] is False
    assert rows[2]["variant"] == "CommitTick"


def test_outbound_op_session_end_and_write_record(tmp_path) -> None:
    path = tmp_path / "session.jsonl"
    logger = SessionLogger.new()
    logger.open(path)

    write_record("x", "custom", {"a": 1}, logger)
    log_outbound_op({"op": "review"}, logger)
    log_session_end(logger)

    rows = _read_jsonl(path)
    assert rows[0]["dir"] == "x"
    assert rows[0]["kind"] == "custom"
    assert rows[0]["payload"] == {"a": 1}
    assert rows[1]["dir"] == "from_tui"
    assert rows[1]["kind"] == "op"
    assert rows[2]["dir"] == "meta"
    assert rows[2]["kind"] == "session_end"

def test_disabled_logger_paths_are_noops(tmp_path) -> None:
    logger = SessionLogger.new()

    logger.write_json_line({"kind": "ignored"})
    log_inbound_app_event(AppEvent.new_session(), logger)
    log_outbound_op({"op": "ignored"}, logger)
    log_session_end(logger)

    assert list(tmp_path.iterdir()) == []


def test_maybe_init_uses_default_log_dir_when_path_is_not_explicit(tmp_path) -> None:
    logger = SessionLogger.new()
    config = Config(tmp_path, "/repo", "gpt-5", "openai", Provider("OpenAI"))

    maybe_init(config, env={"CODEX_TUI_RECORD_SESSION": "TRUE"}, logger=logger)

    logs = list(tmp_path.glob("session-*.jsonl"))
    assert len(logs) == 1
    rows = _read_jsonl(logs[0])
    assert rows[0]["kind"] == "session_start"
    assert rows[0]["dir"] == "meta"

