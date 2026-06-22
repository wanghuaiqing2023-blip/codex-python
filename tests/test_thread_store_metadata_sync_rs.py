from __future__ import annotations

from pathlib import Path

from pycodex.protocol import (
    CompactedItem,
    EventMsg,
    RolloutItem,
    SessionMeta,
    SessionMetaLine,
    SessionSource,
    ThreadGoal,
    ThreadGoalStatus,
    ThreadGoalUpdatedEvent,
    ThreadId,
    ThreadMemoryMode,
    UserMessageEvent,
)
from pycodex.thread_store import (
    ResumeThreadParams,
    ThreadEventPersistenceMode,
    ThreadMetadataSync,
    ThreadPersistenceMetadata,
)


def thread_id(hex_tail: str = "000000000001") -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{hex_tail}")


def resume_params(thread: ThreadId, history: list[RolloutItem]) -> ResumeThreadParams:
    return ResumeThreadParams(
        thread_id=thread,
        rollout_path=None,
        history=tuple(history),
        include_archived=False,
        metadata=ThreadPersistenceMetadata(
            cwd=None,
            model_provider="test-provider",
            memory_mode=ThreadMemoryMode.ENABLED,
        ),
        event_persistence_mode=ThreadEventPersistenceMode.LIMITED,
    )


def user_message(message: str) -> UserMessageEvent:
    return UserMessageEvent(message=message, images=None, local_images=(), text_elements=())


def user_item(message: str) -> RolloutItem:
    return RolloutItem.event_msg(EventMsg.with_payload("user_message", user_message(message)))


def session_meta(thread: ThreadId) -> SessionMetaLine:
    return SessionMetaLine(
        meta=SessionMeta(
            id=thread,
            timestamp="2025-01-03T12:00:00Z",
            cwd=Path(),
            originator="",
            cli_version="",
            source=SessionSource.exec(),
        ),
        git=None,
    )


def goal_update(thread: ThreadId, objective: str) -> ThreadGoalUpdatedEvent:
    return ThreadGoalUpdatedEvent(
        thread_id=thread,
        turn_id=None,
        goal=ThreadGoal(
            thread_id=thread,
            objective=objective,
            status=ThreadGoalStatus.ACTIVE,
            token_budget=None,
            tokens_used=0,
            time_used_seconds=0,
            created_at=0,
            updated_at=0,
        ),
    )


def test_resume_history_keeps_derived_metadata_pending_until_applied() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/thread_metadata_sync.rs::resume_history_keeps_derived_metadata_pending_until_applied
    # Contract: resume history derives metadata, take_pending_update is retry-safe, and mark_applied clears matching generation.
    thread = thread_id()
    sync = ThreadMetadataSync.for_resume(
        resume_params(
            thread,
            [
                RolloutItem.session_meta(session_meta(thread)),
                user_item("hello metadata"),
            ],
        )
    )

    update = sync.take_pending_update()
    assert update is not None
    assert update.patch.created_at is not None
    assert update.patch.created_at.isoformat() == "2025-01-03T12:00:00+00:00"
    assert update.patch.preview == "hello metadata"
    assert update.patch.title == "hello metadata"
    assert update.patch.first_user_message == "hello metadata"
    assert update.patch.updated_at is None
    assert sync.take_pending_update() is not None

    sync.mark_pending_update_applied(update)
    assert sync.take_pending_update() is None


def test_goal_update_sets_preview_without_overriding_existing_preview() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/thread_metadata_sync.rs::goal_update_sets_preview_without_overriding_existing_preview
    # Contract: a goal objective claims preview first while the first user message still fills title/first_user_message.
    thread = thread_id()
    sync = ThreadMetadataSync.for_resume(
        resume_params(
            thread,
            [
                RolloutItem.event_msg(EventMsg.with_payload("thread_goal_updated", goal_update(thread, "ship the refactor"))),
                user_item("first user text"),
            ],
        )
    )

    update = sync.take_pending_update()
    assert update is not None
    assert update.patch.preview == "ship the refactor"
    assert update.patch.first_user_message == "first user text"
    assert update.patch.title == "first user text"


def test_later_user_messages_do_not_emit_existing_preview_fields() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/thread_metadata_sync.rs::later_user_messages_do_not_emit_existing_preview_fields
    # Contract: once preview/title/first_user_message are seen, later user messages only touch updated_at.
    thread = thread_id()
    sync = ThreadMetadataSync.for_resume(resume_params(thread, [user_item("first user text")]))
    pending = sync.take_pending_update()
    assert pending is not None
    sync.mark_pending_update_applied(pending)

    update = sync.observe_appended_items([user_item("later user text")])
    assert update is not None
    assert update.patch.preview is None
    assert update.patch.title is None
    assert update.patch.first_user_message is None
    assert update.patch.updated_at is not None


def test_metadata_irrelevant_items_coalesce_updated_at_touches() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/thread_metadata_sync.rs::metadata_irrelevant_items_coalesce_updated_at_touches
    # Contract: metadata-irrelevant appends coalesce updated_at touches inside the touch interval but keep a barrier update pending.
    thread = thread_id()
    sync = ThreadMetadataSync.for_resume(resume_params(thread, []))
    item = RolloutItem.compacted(CompactedItem(message="compacted", replacement_history=None))

    first = sync.observe_appended_items([item])
    assert first is not None
    assert first.patch.updated_at is not None
    sync.mark_pending_update_applied(first)

    assert sync.observe_appended_items([item]) is None
    assert sync.take_pending_update() is not None


def test_resume_history_waits_for_append_before_flushing_metadata() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/thread_metadata_sync.rs::resume_history_waits_for_append_before_flushing_metadata
    # Contract: resume-derived metadata is deferred from existing-history flush until the first append barrier.
    thread = thread_id()
    sync = ThreadMetadataSync.for_resume(
        resume_params(
            thread,
            [
                RolloutItem.session_meta(session_meta(thread)),
                user_item("hello metadata"),
            ],
        )
    )

    assert sync.take_pending_update_for_existing_history() is None
    assert sync.observe_appended_items([user_item("new append")]) is not None
