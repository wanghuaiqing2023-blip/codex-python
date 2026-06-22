"""Parity tests for ``codex-app-server/src/request_processors/feedback_processor.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from pycodex.app_server.request_processors_feedback_processor import (
    AppServerFeedbackUploadOptions,
    FeedbackRequestProcessor,
    FeedbackRequestProcessorError,
    auto_review_rollout_filename,
    windows_sandbox_log_attachment,
)
from pycodex.app_server_protocol import FeedbackUploadParams
from pycodex.feedback import WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME, FeedbackAttachment


@dataclass
class FakeSnapshot:
    thread_id: str
    uploads: list[AppServerFeedbackUploadOptions] = field(default_factory=list)

    def upload_feedback(self, options: AppServerFeedbackUploadOptions) -> None:
        self.uploads.append(options)


@dataclass
class FakeFeedback:
    snapshot_value: FakeSnapshot
    requested_thread_ids: list[str | None] = field(default_factory=list)

    def snapshot(self, thread_id: str | None) -> FakeSnapshot:
        self.requested_thread_ids.append(thread_id)
        return self.snapshot_value


@dataclass
class FakeThread:
    rollout: Path | None = None
    guardian: Path | None = None

    def rollout_path(self) -> Path | None:
        return self.rollout

    async def guardian_trunk_rollout_path(self) -> Path | None:
        return self.guardian


@dataclass
class FakeThreadManager:
    threads: dict[str, FakeThread] = field(default_factory=dict)
    subtree_ids: list[str] | Exception = field(default_factory=list)
    source: str = "cli"

    async def list_agent_subtree_thread_ids(self, thread_id: str) -> list[str]:
        if isinstance(self.subtree_ids, Exception):
            raise self.subtree_ids
        return list(self.subtree_ids)

    async def get_thread(self, thread_id: str) -> FakeThread:
        if thread_id not in self.threads:
            raise KeyError(thread_id)
        return self.threads[thread_id]

    def session_source(self) -> str:
        return self.source


@dataclass
class FakeStateDb:
    descendants: dict[str, list[str]] = field(default_factory=dict)
    rollout_paths: dict[str, Path] = field(default_factory=dict)
    feedback_logs: object | None = None
    queried_thread_ids: list[list[str]] = field(default_factory=list)

    async def list_thread_spawn_descendants_with_status(self, thread_id: str, status: str) -> list[str]:
        return list(self.descendants.get(status, ()))

    async def find_rollout_path_by_id(self, thread_id: str, _archived_only: object | None = None) -> Path | None:
        return self.rollout_paths.get(thread_id)

    async def query_feedback_logs_for_threads(self, thread_ids: list[str]) -> object | None:
        self.queried_thread_ids.append(thread_ids)
        return self.feedback_logs


@dataclass
class FakeLogDb:
    flushed: bool = False

    async def flush(self) -> None:
        self.flushed = True


@dataclass
class FakeCachedAuth:
    calls: list[str] = field(default_factory=list)

    def get_chatgpt_user_id(self) -> str:
        self.calls.append("get_chatgpt_user_id")
        return "chatgpt-user"

    def get_account_id(self) -> str:
        self.calls.append("get_account_id")
        return "account-id"


@dataclass
class FakeAuthManager:
    cached: FakeCachedAuth

    def auth_cached(self) -> FakeCachedAuth:
        return self.cached


def test_disabled_config_rejects_feedback_upload() -> None:
    # Rust: upload_feedback_response returns invalid_request when config.feedback_enabled is false.
    processor = FeedbackRequestProcessor(
        auth_manager=None,
        thread_manager=FakeThreadManager(),
        config={"feedback_enabled": False},
        feedback=FakeFeedback(FakeSnapshot("thread-1")),
    )

    try:
        asyncio.run(processor.feedback_upload({"classification": "bug"}))
    except FeedbackRequestProcessorError as exc:
        assert exc.error.code == -32600
        assert exc.error.message == "sending feedback is disabled by configuration"
    else:
        raise AssertionError("expected disabled feedback to be rejected")


def test_upload_without_logs_passes_snapshot_options() -> None:
    # Rust: no-log uploads skip log attachment collection and pass classification/reason/tags/session_source.
    snapshot = FakeSnapshot("thread-1")
    feedback = FakeFeedback(snapshot)
    processor = FeedbackRequestProcessor(
        auth_manager=None,
        thread_manager=FakeThreadManager(source="app"),
        config={"feedback_enabled": True},
        feedback=feedback,
    )

    response = asyncio.run(
        processor.feedback_upload(
            FeedbackUploadParams(
                classification="bug",
                reason="broken",
                thread_id="thread-1",
                include_logs=False,
                tags={"user_tag": "kept"},
            )
        )
    )

    assert response.thread_id == "thread-1"
    assert feedback.requested_thread_ids == ["thread-1"]
    assert len(snapshot.uploads) == 1
    options = snapshot.uploads[0]
    assert options.classification == "bug"
    assert options.reason == "broken"
    assert options.tags == {"user_tag": "kept"}
    assert options.include_logs is False
    assert options.extra_attachment_paths == ()
    assert options.session_source == "app"


def test_cached_auth_feedback_tag_hooks_match_rust_method_names() -> None:
    # Rust: upload_feedback_response logs get_chatgpt_user_id and get_account_id when auth is cached.
    cached_auth = FakeCachedAuth()
    snapshot = FakeSnapshot("thread-1")
    processor = FeedbackRequestProcessor(
        auth_manager=FakeAuthManager(cached_auth),
        thread_manager=FakeThreadManager(),
        config={"feedback_enabled": True},
        feedback=FakeFeedback(snapshot),
    )

    asyncio.run(processor.feedback_upload({"classification": "bug"}))

    assert cached_auth.calls == ["get_chatgpt_user_id", "get_account_id"]


def test_include_logs_collects_rollouts_sqlite_logs_doctor_tags_and_extra_files(tmp_path: Path) -> None:
    # Rust: include_logs flushes log DB, collects subtree rollout files, sqlite logs, doctor report,
    # Windows sandbox log, guardian trunk rollout, and explicit extra log files with path dedupe.
    root_rollout = tmp_path / "root.jsonl"
    child_rollout = tmp_path / "child.jsonl"
    guardian_rollout = tmp_path / "guardian.jsonl"
    extra_log = tmp_path / "extra.log"
    sandbox_log = tmp_path / "windows.log"
    for path in (root_rollout, child_rollout, guardian_rollout, extra_log, sandbox_log):
        path.write_text("log", encoding="utf-8")

    snapshot = FakeSnapshot("root")
    log_db = FakeLogDb()
    state_db = FakeStateDb(feedback_logs={"rows": [1]})
    thread_manager = FakeThreadManager(
        subtree_ids=["root", "child"],
        threads={
            "root": FakeThread(rollout=root_rollout, guardian=guardian_rollout),
            "child": FakeThread(rollout=child_rollout),
        },
    )
    doctor_attachment = FeedbackAttachment(filename="codex-doctor-report.json", data=b"{}")

    async def doctor_report(_config: object) -> object:
        return SimpleNamespace(attachment=doctor_attachment, tags={"doctor_ok_count": "1", "user_tag": "doctor"})

    processor = FeedbackRequestProcessor(
        auth_manager=None,
        thread_manager=thread_manager,
        config={"feedback_enabled": True, "codex_home": tmp_path},
        feedback=FakeFeedback(snapshot),
        log_db=log_db,
        state_db=state_db,
        doctor_report_factory=doctor_report,
        windows_log_resolver=lambda _home: sandbox_log,
    )

    asyncio.run(
        processor.feedback_upload(
            {
                "classification": "bug",
                "threadId": "root",
                "includeLogs": True,
                "extraLogFiles": [extra_log, root_rollout],
                "tags": {"user_tag": "kept"},
            }
        )
    )

    assert log_db.flushed is True
    assert state_db.queried_thread_ids == [["root", "child"]]
    options = snapshot.uploads[0]
    assert options.logs_override == {"rows": [1]}
    assert options.extra_attachments == (doctor_attachment,)
    assert options.tags == {"user_tag": "kept", "doctor_ok_count": "1"}
    assert [(item.path, item.filename) for item in options.extra_attachment_paths] == [
        (root_rollout, None),
        (child_rollout, None),
        (guardian_rollout, "auto-review-rollout-root.jsonl"),
        (sandbox_log, WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME),
        (extra_log, None),
    ]


def test_subtree_listing_falls_back_to_state_db_descendants(tmp_path: Path) -> None:
    # Rust: subtree-list errors fall back to the requested thread plus state DB Open/Closed descendants.
    state_db = FakeStateDb(
        descendants={"Open": ["open-child"], "Closed": ["closed-child"]},
        rollout_paths={
            "root": tmp_path / "root.jsonl",
            "open-child": tmp_path / "open.jsonl",
            "closed-child": tmp_path / "closed.jsonl",
        },
    )
    for path in state_db.rollout_paths.values():
        path.write_text("log", encoding="utf-8")
    snapshot = FakeSnapshot("root")
    processor = FeedbackRequestProcessor(
        auth_manager=None,
        thread_manager=FakeThreadManager(subtree_ids=RuntimeError("missing manager tree")),
        config={"feedback_enabled": True},
        feedback=FakeFeedback(snapshot),
        state_db=state_db,
    )

    asyncio.run(
        processor.feedback_upload(
            FeedbackUploadParams(classification="bug", thread_id="root", include_logs=True)
        )
    )

    assert [item.path for item in snapshot.uploads[0].extra_attachment_paths] == [
        state_db.rollout_paths["root"],
        state_db.rollout_paths["open-child"],
        state_db.rollout_paths["closed-child"],
    ]


def test_resolve_rollout_path_falls_back_to_state_db(tmp_path: Path) -> None:
    # Rust: resolve_rollout_path tries live thread first, then state_db.find_rollout_path_by_id.
    fallback = tmp_path / "archived.jsonl"
    processor = FeedbackRequestProcessor(
        auth_manager=None,
        thread_manager=FakeThreadManager(),
        config={},
        feedback=FakeFeedback(FakeSnapshot("archived")),
        state_db=FakeStateDb(rollout_paths={"archived": fallback}),
    )

    assert asyncio.run(processor.resolve_rollout_path("archived")) == fallback


def test_auto_review_rollout_filename_matches_rust_format() -> None:
    assert auto_review_rollout_filename("abc") == "auto-review-rollout-abc.jsonl"


def test_windows_sandbox_log_attachment_uses_current_log(tmp_path: Path) -> None:
    # Rust Windows-only test adapted with an injected resolver so it is platform-neutral.
    log_path = tmp_path / "sandbox.log"
    log_path.write_text("current", encoding="utf-8")

    attachment = windows_sandbox_log_attachment(tmp_path, resolver=lambda home: home / "sandbox.log")

    assert attachment is not None
    assert attachment.path == log_path
    assert attachment.filename == WINDOWS_SANDBOX_LOG_ATTACHMENT_FILENAME
