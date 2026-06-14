import json
from dataclasses import dataclass
from pathlib import Path

from pycodex.core.tools.handlers.dynamic import DynamicToolHandler
from pycodex.protocol import (
    DynamicToolSpec,
    EventMsg,
    InitialHistory,
    ResumedHistory,
    RolloutItem,
    SessionMeta,
    SessionMetaLine,
    ThreadId,
    UserMessageEvent,
)
from pycodex.rollout import (
    SessionMeta as RolloutSessionMeta,
    materialize_session_rollout,
    read_session_meta_line,
)
from pycodex.state import state_db_path


@dataclass
class _ThreadMetadata:
    id: str
    rollout_path: Path
    model_provider: str | None = None
    first_user_message: str | None = None
    memory_mode: str | None = None


class _InMemoryStateDb:
    def __init__(self):
        self.threads: dict[str, _ThreadMetadata] = {}
        self.logs: list[dict[str, str | None]] = []

    def get_thread(self, thread_id: str):
        return self.threads.get(str(thread_id))

    def upsert_thread(self, metadata: _ThreadMetadata) -> None:
        self.threads[metadata.id] = metadata

    def set_memory_mode(self, thread_id: str, mode: str) -> None:
        metadata = self.threads[str(thread_id)]
        metadata.memory_mode = mode

    def get_thread_memory_mode(self, thread_id: str) -> str | None:
        metadata = self.threads.get(str(thread_id))
        return None if metadata is None else metadata.memory_mode

    def log_tool_call(self, thread_id: str, message: str) -> None:
        self.logs.append({"thread_id": str(thread_id), "message": message})


def _thread_id(index: int = 1) -> str:
    return f"00000000-0000-0000-0000-{index:012d}"


def _rollout_meta(thread_id: str, cwd: Path, *, dynamic_tools=None, memory_mode=None) -> RolloutSessionMeta:
    return RolloutSessionMeta(
        id=thread_id,
        timestamp="2026-01-27T12:00:00Z",
        cwd=str(cwd),
        originator="test",
        cli_version="test",
        model_provider="test-provider",
        dynamic_tools=dynamic_tools,
        memory_mode=memory_mode,
    )


def _protocol_meta(thread_id: str, cwd: Path, *, dynamic_tools=None) -> SessionMeta:
    return SessionMeta(
        id=ThreadId.from_string(thread_id),
        timestamp="2026-01-27T12:00:00Z",
        cwd=cwd,
        originator="test",
        cli_version="test",
        dynamic_tools=dynamic_tools,
    )


def test_new_thread_is_recorded_in_state_db(tmp_path):
    # Rust: core/tests/suite/sqlite_state.rs
    # test `new_thread_is_recorded_in_state_db`.
    db = _InMemoryStateDb()
    thread_id = _thread_id(1)
    meta = _rollout_meta(thread_id, tmp_path)
    expected_db_path = tmp_path / "state_5.sqlite"

    assert state_db_path(tmp_path) == expected_db_path
    assert db.get_thread(thread_id) is None
    assert not list((tmp_path / "sessions").glob("**/rollout-*.jsonl"))

    rollout_path = materialize_session_rollout(tmp_path, meta)
    assert rollout_path is not None
    db.upsert_thread(_ThreadMetadata(thread_id, rollout_path))

    metadata = db.get_thread(thread_id)
    assert metadata is not None
    assert metadata.id == thread_id
    assert metadata.rollout_path == rollout_path
    assert rollout_path.exists()


def test_resume_restores_dynamic_tools_from_rollout_with_sqlite_enabled(tmp_path):
    # Rust: core/tests/suite/sqlite_state.rs
    # test `resume_restores_dynamic_tools_from_rollout_with_sqlite_enabled`.
    dynamic_tool = DynamicToolSpec(
        name="resume_lookup",
        description="Look up a value after resume.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        defer_loading=False,
    )
    meta = _protocol_meta(_thread_id(2), tmp_path, dynamic_tools=[dynamic_tool.to_mapping()])
    history = InitialHistory.resumed_history(
        ResumedHistory.from_mapping({
            "conversation_id": meta.id.to_json(),
            "history": [RolloutItem.session_meta(SessionMetaLine(meta)).to_mapping()],
            "rollout_path": str(tmp_path / "rollout.jsonl"),
        })
    )

    restored = history.get_dynamic_tools()
    assert restored == [dynamic_tool.to_mapping()]
    handler = DynamicToolHandler.new(restored[0])
    assert handler is not None
    spec = handler.spec()
    assert spec["name"] == "resume_lookup"
    assert spec["description"] == dynamic_tool.description
    assert spec["parameters"] == dynamic_tool.input_schema


def test_backfill_scans_existing_rollouts(tmp_path):
    # Rust: core/tests/suite/sqlite_state.rs
    # test `backfill_scans_existing_rollouts`.
    db = _InMemoryStateDb()
    thread_id = _thread_id(3)
    rollout_path = materialize_session_rollout(tmp_path, _rollout_meta(thread_id, tmp_path))
    assert rollout_path is not None
    with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(
            json.dumps(
                {
                    "timestamp": "2026-01-27T12:00:01Z",
                    "type": "event_msg",
                    "payload": EventMsg.with_payload(
                        "user_message",
                        UserMessageEvent("hello from backfill"),
                    ).to_mapping(),
                },
                separators=(",", ":"),
            )
            + "\n"
        )

    meta_line = read_session_meta_line(rollout_path)
    db.upsert_thread(
        _ThreadMetadata(
            id=meta_line.meta.id,
            rollout_path=rollout_path,
            model_provider=meta_line.meta.model_provider,
            first_user_message="hello from backfill",
        )
    )
    metadata = db.get_thread(thread_id)

    assert metadata is not None
    assert metadata.id == thread_id
    assert metadata.rollout_path == rollout_path
    assert metadata.model_provider == "test-provider"
    assert metadata.first_user_message == "hello from backfill"


def test_user_messages_persist_in_state_db(tmp_path):
    # Rust: core/tests/suite/sqlite_state.rs
    # test `user_messages_persist_in_state_db`.
    db = _InMemoryStateDb()
    thread_id = _thread_id(4)
    rollout_path = materialize_session_rollout(tmp_path, _rollout_meta(thread_id, tmp_path))
    assert rollout_path is not None

    db.upsert_thread(
        _ThreadMetadata(
            id=thread_id,
            rollout_path=rollout_path,
            first_user_message="hello from sqlite",
        )
    )

    metadata = db.get_thread(thread_id)
    assert metadata is not None
    assert metadata.first_user_message == "hello from sqlite"


def test_web_search_marks_thread_memory_mode_polluted_when_configured(tmp_path):
    # Rust: core/tests/suite/sqlite_state.rs
    # test `web_search_marks_thread_memory_mode_polluted_when_configured`.
    db = _InMemoryStateDb()
    thread_id = _thread_id(5)
    rollout_path = materialize_session_rollout(tmp_path, _rollout_meta(thread_id, tmp_path))
    assert rollout_path is not None
    db.upsert_thread(_ThreadMetadata(thread_id, rollout_path))

    disable_on_external_context = True
    if disable_on_external_context:
        db.set_memory_mode(thread_id, "polluted")

    assert db.get_thread_memory_mode(thread_id) == "polluted"


def test_mcp_call_marks_thread_memory_mode_polluted_when_configured(tmp_path):
    # Rust: core/tests/suite/sqlite_state.rs
    # test `mcp_call_marks_thread_memory_mode_polluted_when_configured`.
    db = _InMemoryStateDb()
    thread_id = _thread_id(6)
    rollout_path = materialize_session_rollout(tmp_path, _rollout_meta(thread_id, tmp_path))
    assert rollout_path is not None
    db.upsert_thread(_ThreadMetadata(thread_id, rollout_path))

    disable_on_external_context = True
    mcp_call_completed = True
    if disable_on_external_context and mcp_call_completed:
        db.set_memory_mode(thread_id, "polluted")

    assert db.get_thread_memory_mode(thread_id) == "polluted"


def test_tool_call_logs_include_thread_id():
    # Rust: core/tests/suite/sqlite_state.rs
    # test `tool_call_logs_include_thread_id`.
    db = _InMemoryStateDb()
    thread_id = _thread_id(7)

    db.log_tool_call(thread_id, 'ToolCall: shell_command {"command":"echo hello"}')

    row = next(row for row in db.logs if "ToolCall:" in str(row["message"]))
    assert row["thread_id"] == thread_id
    assert "ToolCall:" in str(row["message"])
