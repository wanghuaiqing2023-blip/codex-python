from datetime import datetime, timezone
from pathlib import Path
import uuid

from pycodex.core import (
    backfill_watermark_for_path,
    backfill_sessions,
    builder_from_items,
    builder_from_session_meta,
    extract_metadata_from_rollout,
    init_state_runtime_with_backfill,
    normalize_cwd_for_state_db,
    parse_timestamp_to_utc,
)
import json
from pycodex.rollout import GitInfo, SessionMeta, SessionMetaLine


class FakeBackfillRuntime:
    def __init__(self, *, last_watermark: str | None = None):
        self.status = None
        self.last_watermark = last_watermark
        self.threads = {}
        self.memory_modes = {}
        self.checkpoints = []
        self.complete_watermark = None

    def get_backfill_state(self):
        return {"status": self.status, "last_watermark": self.last_watermark}

    def try_claim_backfill(self):
        return True

    def mark_backfill_running(self):
        self.status = "running"

    def upsert_thread(self, metadata):
        self.threads[metadata.id] = metadata

    def set_thread_memory_mode(self, thread_id, memory_mode):
        self.memory_modes[thread_id] = memory_mode

    def checkpoint_backfill(self, watermark):
        self.last_watermark = watermark
        self.checkpoints.append(watermark)

    def mark_backfill_complete(self, watermark):
        self.status = "complete"
        self.complete_watermark = watermark

    def get_thread(self, thread_id):
        return self.threads.get(thread_id)


def test_parse_timestamp_to_utc_accepts_filename_timestamp_and_rfc3339():
    # Rust: codex-rollout/src/metadata.rs parse_timestamp_to_utc.
    assert parse_timestamp_to_utc("2026-01-27T12-34-56") == datetime(2026, 1, 27, 12, 34, 56, tzinfo=timezone.utc)
    assert parse_timestamp_to_utc("2026-01-27T12:34:56Z") == datetime(2026, 1, 27, 12, 34, 56, tzinfo=timezone.utc)
    assert parse_timestamp_to_utc("not-a-timestamp") is None


def test_builder_from_items_falls_back_to_filename(tmp_path: Path):
    # Rust: codex-rollout/src/metadata_tests.rs builder_from_items_falls_back_to_filename.
    thread_id = str(uuid.uuid4())
    path = tmp_path / f"rollout-2026-01-27T12-34-56-{thread_id}.jsonl"

    builder = builder_from_items([{"type": "compacted", "payload": {}}], path)

    assert builder is not None
    assert builder.id == thread_id
    assert builder.rollout_path == path
    assert builder.created_at == datetime(2026, 1, 27, 12, 34, 56, tzinfo=timezone.utc)
    assert builder.source == "vscode"
    assert builder.cwd == Path()
    assert builder.sandbox_policy == "read-only"
    assert builder.approval_mode == "on-request"


def test_builder_from_items_uses_session_meta_before_filename(tmp_path: Path):
    # Rust: codex-rollout/src/metadata.rs builder_from_items prefers RolloutItem::SessionMeta.
    filename_id = str(uuid.uuid4())
    meta_id = str(uuid.uuid4())
    path = tmp_path / f"rollout-2026-01-27T12-34-56-{filename_id}.jsonl"
    payload = {
        "id": meta_id,
        "timestamp": "2026-01-28T01:02:03Z",
        "cwd": str(tmp_path),
        "originator": "cli",
        "cli_version": "0.0.0",
        "source": "cli",
        "thread_source": "user",
        "model_provider": "openai",
        "git": {
            "commit_hash": "abc123",
            "branch": "main",
            "repository_url": "https://example.test/repo.git",
        },
    }

    builder = builder_from_items([{"type": "session_meta", "payload": payload}], path)

    assert builder is not None
    assert builder.id == meta_id
    assert builder.created_at == datetime(2026, 1, 28, 1, 2, 3, tzinfo=timezone.utc)
    assert builder.source == "cli"
    assert builder.thread_source == "user"
    assert builder.cwd == tmp_path
    assert builder.cli_version == "0.0.0"
    assert builder.model_provider == "openai"
    assert builder.git_sha == "abc123"
    assert builder.git_branch == "main"
    assert builder.git_origin_url == "https://example.test/repo.git"


def test_builder_from_items_finds_session_meta_after_non_metadata_item(tmp_path: Path):
    # Rust: codex-rollout/src/metadata.rs builder_from_items uses iter().find_map.
    filename_id = str(uuid.uuid4())
    meta_id = str(uuid.uuid4())
    path = tmp_path / f"rollout-2026-01-27T12-34-56-{filename_id}.jsonl"

    builder = builder_from_items(
        [
            {"type": "compacted", "payload": {"message": "noop"}},
            {
                "type": "session_meta",
                "payload": {
                    "id": meta_id,
                    "timestamp": "2026-01-28T01:02:03Z",
                    "cwd": str(tmp_path),
                    "originator": "cli",
                    "cli_version": "0.0.0",
                    "source": "cli",
                },
            },
        ],
        path,
    )

    assert builder is not None
    assert builder.id == meta_id
    assert builder.source == "cli"


def test_builder_from_session_meta_rejects_invalid_timestamp(tmp_path: Path):
    # Rust: codex-rollout/src/metadata.rs builder_from_session_meta returns None when timestamp parsing fails.
    line = SessionMetaLine(
        meta=SessionMeta(
            id=str(uuid.uuid4()),
            timestamp="not-a-timestamp",
            cwd=str(tmp_path),
            originator="cli",
            cli_version="0.0.0",
        ),
        git=GitInfo(commit_hash="abc123"),
    )

    assert builder_from_session_meta(line, tmp_path / "rollout.jsonl") is None


def test_extract_metadata_from_rollout_uses_session_meta(tmp_path: Path):
    # Rust: codex-rollout/src/metadata_tests.rs extract_metadata_from_rollout_uses_session_meta.
    thread_id = str(uuid.uuid4())
    path = tmp_path / f"rollout-2026-01-27T12-34-56-{thread_id}.jsonl"
    payload = {
        "id": thread_id,
        "timestamp": "2026-01-27T12:34:56Z",
        "cwd": str(tmp_path),
        "originator": "cli",
        "cli_version": "0.0.0",
        "source": "vscode",
        "model_provider": "openai",
        "memory_mode": None,
    }
    line = {"timestamp": "2026-01-27T12:34:56Z", "type": "session_meta", "payload": payload}
    path.write_text(json.dumps(line, separators=(",", ":")) + "\n", encoding="utf-8")

    outcome = extract_metadata_from_rollout(path, "openai")

    assert outcome.metadata.id == thread_id
    assert outcome.metadata.rollout_path == path
    assert outcome.metadata.created_at == datetime(2026, 1, 27, 12, 34, 56, tzinfo=timezone.utc)
    assert outcome.metadata.updated_at >= outcome.metadata.created_at
    assert outcome.metadata.model_provider == "openai"
    assert outcome.metadata.cwd == tmp_path
    assert outcome.metadata.cli_version == "0.0.0"
    assert outcome.memory_mode is None
    assert outcome.parse_errors == 0


def test_extract_metadata_from_rollout_returns_latest_memory_mode(tmp_path: Path):
    # Rust: codex-rollout/src/metadata_tests.rs extract_metadata_from_rollout_returns_latest_memory_mode.
    thread_id = str(uuid.uuid4())
    path = tmp_path / f"rollout-2026-01-27T12-34-56-{thread_id}.jsonl"
    base_payload = {
        "id": thread_id,
        "timestamp": "2026-01-27T12:34:56Z",
        "cwd": str(tmp_path),
        "originator": "cli",
        "cli_version": "0.0.0",
        "source": "vscode",
        "model_provider": "openai",
        "memory_mode": None,
    }
    polluted_payload = {**base_payload, "memory_mode": "polluted"}
    lines = [
        {"timestamp": "2026-01-27T12:34:56Z", "type": "session_meta", "payload": base_payload},
        {"timestamp": "2026-01-27T12:35:00Z", "type": "session_meta", "payload": polluted_payload},
    ]
    path.write_text("\n".join(json.dumps(line, separators=(",", ":")) for line in lines) + "\n", encoding="utf-8")

    outcome = extract_metadata_from_rollout(path, "openai")

    assert outcome.memory_mode == "polluted"


def test_backfill_watermark_for_path_strips_codex_home_and_normalizes_separators(tmp_path: Path):
    # Rust: codex-rollout/src/metadata.rs backfill_watermark_for_path.
    codex_home = tmp_path / "codex-home"
    path = codex_home / "sessions" / "2026" / "01" / "27" / "rollout.jsonl"

    assert backfill_watermark_for_path(codex_home, path) == "sessions/2026/01/27/rollout.jsonl"
    assert backfill_watermark_for_path(codex_home, Path("C:/outside/rollout.jsonl")).endswith("C:/outside/rollout.jsonl")


def test_backfill_sessions_resumes_from_watermark_and_marks_complete(tmp_path: Path):
    # Rust: codex-rollout/src/metadata_tests.rs backfill_sessions_resumes_from_watermark_and_marks_complete.
    codex_home = tmp_path
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())
    sessions = codex_home / "sessions"
    sessions.mkdir()
    first_path = sessions / f"rollout-2026-01-27T12-34-56-{first_id}.jsonl"
    second_path = sessions / f"rollout-2026-01-27T12-35-56-{second_id}.jsonl"
    for path, thread_id, timestamp in (
        (first_path, first_id, "2026-01-27T12:34:56Z"),
        (second_path, second_id, "2026-01-27T12:35:56Z"),
    ):
        payload = {
            "id": thread_id,
            "timestamp": timestamp,
            "cwd": str(codex_home),
            "originator": "cli",
            "cli_version": "0.0.0",
            "source": "vscode",
            "model_provider": "test-provider",
            "memory_mode": None,
        }
        line = {"timestamp": timestamp, "type": "session_meta", "payload": payload}
        path.write_text(json.dumps(line, separators=(",", ":")) + "\n", encoding="utf-8")

    runtime = FakeBackfillRuntime(last_watermark=backfill_watermark_for_path(codex_home, first_path))

    stats = backfill_sessions(runtime, codex_home, "test-provider")

    assert stats.scanned == 1
    assert stats.upserted == 1
    assert stats.failed == 0
    assert first_id not in runtime.threads
    assert second_id in runtime.threads
    assert runtime.status == "complete"
    assert runtime.complete_watermark == backfill_watermark_for_path(codex_home, second_path)
    assert runtime.memory_modes[second_id] == "enabled"


def test_backfill_sessions_preserves_existing_git_branch_and_fills_missing_git_fields(tmp_path: Path):
    # Rust: codex-rollout/src/metadata_tests.rs backfill_sessions_preserves_existing_git_branch_and_fills_missing_git_fields.
    codex_home = tmp_path
    thread_id = str(uuid.uuid4())
    sessions = codex_home / "sessions"
    sessions.mkdir()
    path = sessions / f"rollout-2026-01-27T12-34-56-{thread_id}.jsonl"
    payload = {
        "id": thread_id,
        "timestamp": "2026-01-27T12:34:56Z",
        "cwd": str(codex_home),
        "originator": "cli",
        "cli_version": "0.0.0",
        "source": "vscode",
        "model_provider": "test-provider",
        "git": {
            "commit_hash": "rollout-sha",
            "branch": "rollout-branch",
            "repository_url": "git@example.com:openai/codex.git",
        },
    }
    line = {"timestamp": "2026-01-27T12:34:56Z", "type": "session_meta", "payload": payload}
    path.write_text(json.dumps(line, separators=(",", ":")) + "\n", encoding="utf-8")
    existing = extract_metadata_from_rollout(path, "test-provider").metadata
    existing = existing.prefer_existing_git_info(
        type("ExistingGit", (), {"git_sha": None, "git_branch": "sqlite-branch", "git_origin_url": None})()
    )
    runtime = FakeBackfillRuntime()
    runtime.threads[thread_id] = existing

    stats = backfill_sessions(runtime, codex_home, "test-provider")

    persisted = runtime.threads[thread_id]
    assert stats.upserted == 1
    assert persisted.git_sha == "rollout-sha"
    assert persisted.git_branch == "sqlite-branch"
    assert persisted.git_origin_url == "git@example.com:openai/codex.git"


def test_backfill_sessions_normalizes_cwd_before_upsert(tmp_path: Path):
    # Rust: codex-rollout/src/metadata_tests.rs backfill_sessions_normalizes_cwd_before_upsert.
    codex_home = tmp_path
    thread_id = str(uuid.uuid4())
    sessions = codex_home / "sessions"
    sessions.mkdir()
    path = sessions / f"rollout-2026-01-27T12-34-56-{thread_id}.jsonl"
    session_cwd = codex_home / "."
    payload = {
        "id": thread_id,
        "timestamp": "2026-01-27T12:34:56Z",
        "cwd": str(session_cwd),
        "originator": "cli",
        "cli_version": "0.0.0",
        "source": "vscode",
        "model_provider": "test-provider",
    }
    line = {"timestamp": "2026-01-27T12:34:56Z", "type": "session_meta", "payload": payload}
    path.write_text(json.dumps(line, separators=(",", ":")) + "\n", encoding="utf-8")
    runtime = FakeBackfillRuntime()

    backfill_sessions(runtime, codex_home, "test-provider")

    assert runtime.threads[thread_id].cwd == normalize_cwd_for_state_db(session_cwd)


def test_backfill_sessions_marks_archived_rollout_metadata(tmp_path: Path):
    # Rust: codex-rollout/src/metadata.rs sets archived_at for archived rollout roots.
    codex_home = tmp_path
    thread_id = str(uuid.uuid4())
    archived = codex_home / "archived_sessions"
    archived.mkdir()
    path = archived / f"rollout-2026-01-27T12-34-56-{thread_id}.jsonl"
    payload = {
        "id": thread_id,
        "timestamp": "2026-01-27T12:34:56Z",
        "cwd": str(codex_home),
        "originator": "cli",
        "cli_version": "0.0.0",
        "source": "vscode",
        "model_provider": "test-provider",
    }
    line = {"timestamp": "2026-01-27T12:34:56Z", "type": "session_meta", "payload": payload}
    path.write_text(json.dumps(line, separators=(",", ":")) + "\n", encoding="utf-8")
    runtime = FakeBackfillRuntime()

    stats = backfill_sessions(runtime, codex_home, "test-provider")

    assert stats.upserted == 1
    assert runtime.threads[thread_id].archived_at is not None
    assert runtime.threads[thread_id].archived_at == runtime.threads[thread_id].updated_at


def test_state_db_init_backfills_before_returning(tmp_path: Path):
    # Rust: codex-rollout/src/recorder_tests.rs::state_db_init_backfills_before_returning.
    codex_home = tmp_path
    thread_id = str(uuid.uuid4())
    rollout_path = (
        codex_home
        / "sessions"
        / "2026"
        / "01"
        / "27"
        / f"rollout-2026-01-27T12-34-56-{thread_id}.jsonl"
    )
    rollout_path.parent.mkdir(parents=True)
    payload = {
        "id": thread_id,
        "timestamp": "2026-01-27T12:34:56Z",
        "cwd": str(codex_home),
        "originator": "test",
        "cli_version": "test",
        "source": "cli",
        "model_provider": None,
    }
    lines = [
        {"timestamp": "2026-01-27T12:34:56Z", "type": "session_meta", "payload": payload},
        {
            "timestamp": "2026-01-27T12:34:57Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "hello from startup backfill", "kind": "plain"},
        },
    ]
    rollout_path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    runtime = FakeBackfillRuntime()

    returned = init_state_runtime_with_backfill(runtime, codex_home, "test-provider")

    assert returned is runtime
    metadata = runtime.get_thread(thread_id)
    assert metadata is not None
    assert metadata.rollout_path == rollout_path
    assert runtime.status == "complete"
