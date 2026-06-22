from datetime import datetime, timezone
from pathlib import Path

import pytest

from pycodex.protocol import (
    AskForApproval,
    ReasoningEffort,
    SandboxPolicy,
    SessionSource,
    ThreadId,
    ThreadSource,
)
from pycodex.state.model.thread_metadata import (
    BackfillStats,
    SortKey,
    ThreadMetadata,
    ThreadMetadataBuilder,
    ThreadRow,
    anchor_from_item,
    datetime_to_epoch_millis,
    datetime_to_epoch_seconds,
    epoch_millis_to_datetime,
    epoch_seconds_to_datetime,
)


THREAD_ID = "00000000-0000-0000-0000-000000000123"


def _thread_row(reasoning_effort: str | None = None, **overrides: object) -> ThreadRow:
    values: dict[str, object] = {
        "id": THREAD_ID,
        "rollout_path": "/tmp/rollout-123.jsonl",
        "created_at": 1_700_000_000,
        "updated_at": 1_700_000_100,
        "source": "cli",
        "thread_source": None,
        "agent_nickname": None,
        "agent_role": None,
        "agent_path": None,
        "model_provider": "openai",
        "model": "gpt-5",
        "reasoning_effort": reasoning_effort,
        "cwd": "/tmp/workspace",
        "cli_version": "0.0.0",
        "title": "",
        "preview": "",
        "sandbox_policy": "read-only",
        "approval_mode": "on-request",
        "tokens_used": 1,
        "first_user_message": "",
        "archived_at": None,
        "git_sha": None,
        "git_branch": None,
        "git_origin_url": None,
    }
    values.update(overrides)
    return ThreadRow.from_mapping(values)


def _expected_metadata(reasoning_effort: ReasoningEffort | None = None) -> ThreadMetadata:
    return ThreadMetadata(
        id=ThreadId.from_string(THREAD_ID),
        rollout_path=Path("/tmp/rollout-123.jsonl"),
        created_at=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        updated_at=datetime.fromtimestamp(1_700_000_100, tz=timezone.utc),
        source="cli",
        thread_source=None,
        agent_nickname=None,
        agent_role=None,
        agent_path=None,
        model_provider="openai",
        model="gpt-5",
        reasoning_effort=reasoning_effort,
        cwd=Path("/tmp/workspace"),
        cli_version="0.0.0",
        title="",
        preview=None,
        sandbox_policy="read-only",
        approval_mode="on-request",
        tokens_used=1,
        first_user_message=None,
        archived_at=None,
        git_sha=None,
        git_branch=None,
        git_origin_url=None,
    )


def test_thread_row_parses_reasoning_effort() -> None:
    # Rust crate: codex-state
    # Rust module/test: src/model/thread_metadata.rs::thread_row_parses_reasoning_effort
    # Behavior contract: known persisted reasoning effort strings parse into
    # ReasoningEffort values during ThreadRow -> ThreadMetadata conversion.
    metadata = _thread_row("high").to_thread_metadata()

    assert metadata == _expected_metadata(ReasoningEffort.HIGH)


def test_thread_row_ignores_unknown_reasoning_effort_values() -> None:
    # Rust crate: codex-state
    # Rust module/test:
    # src/model/thread_metadata.rs::thread_row_ignores_unknown_reasoning_effort_values
    # Behavior contract: unknown future reasoning effort strings are lossy and
    # become None rather than rejecting the whole row.
    metadata = _thread_row("future").to_thread_metadata()

    assert metadata == _expected_metadata(None)


def test_thread_row_maps_empty_strings_and_optional_fields() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_metadata.rs::TryFrom<ThreadRow>
    # Behavior contract: empty preview/first_user_message become None while
    # optional thread/archive/git fields are parsed when present.
    metadata = _thread_row(
        "medium",
        preview="hello preview",
        first_user_message="first",
        thread_source="subagent",
        agent_nickname="worker",
        agent_role="reviewer",
        agent_path="/worker",
        archived_at=1_700_000_200,
        git_sha="abc123",
        git_branch="main",
        git_origin_url="https://example.test/repo.git",
    ).to_thread_metadata()

    assert metadata.preview == "hello preview"
    assert metadata.first_user_message == "first"
    assert metadata.thread_source is ThreadSource.SUBAGENT
    assert metadata.agent_nickname == "worker"
    assert metadata.agent_role == "reviewer"
    assert metadata.agent_path == "/worker"
    assert metadata.reasoning_effort is ReasoningEffort.MEDIUM
    assert metadata.archived_at == datetime.fromtimestamp(1_700_000_200, tz=timezone.utc)
    assert metadata.git_sha == "abc123"
    assert metadata.git_branch == "main"
    assert metadata.git_origin_url == "https://example.test/repo.git"


def test_thread_metadata_builder_fills_rust_defaults() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_metadata.rs::ThreadMetadataBuilder::build
    # Behavior contract: builder fills missing model/provider/runtime fields
    # from Rust defaults while canonicalizing timestamps to millisecond precision.
    created = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
    metadata = ThreadMetadataBuilder.new(
        ThreadId.from_string(THREAD_ID),
        "/tmp/rollout.jsonl",
        created,
        SessionSource.cli(),
    ).build("default-provider")

    assert metadata.id == ThreadId.from_string(THREAD_ID)
    assert metadata.rollout_path == Path("/tmp/rollout.jsonl")
    assert metadata.created_at == datetime(2026, 1, 1, 12, 0, 0, 123000, tzinfo=timezone.utc)
    assert metadata.updated_at == metadata.created_at
    assert metadata.source == "cli"
    assert metadata.model_provider == "default-provider"
    assert metadata.model is None
    assert metadata.reasoning_effort is None
    assert metadata.cwd == Path()
    assert metadata.cli_version == ""
    assert metadata.title == ""
    assert metadata.preview is None
    assert metadata.sandbox_policy == "read-only"
    assert metadata.approval_mode == "on-request"
    assert metadata.tokens_used == 0
    assert metadata.first_user_message is None
    assert metadata.archived_at is None


def test_prefer_existing_git_info_preserves_non_null_existing_fields() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_metadata.rs::ThreadMetadata::prefer_existing_git_info
    # Behavior contract: reconciliation keeps existing non-null Git fields.
    fresh = _expected_metadata()
    existing = _expected_metadata()
    existing.git_sha = "old-sha"
    existing.git_branch = "old-branch"
    existing.git_origin_url = "https://example.test/old.git"

    fresh.prefer_existing_git_info(existing)

    assert fresh.git_sha == "old-sha"
    assert fresh.git_branch == "old-branch"
    assert fresh.git_origin_url == "https://example.test/old.git"


def test_diff_fields_matches_rust_field_list_and_omits_thread_source() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_metadata.rs::ThreadMetadata::diff_fields
    # Behavior contract: Rust reports changed fields in a fixed list and
    # intentionally omits thread_source.
    left = _expected_metadata()
    right = _expected_metadata()
    right.thread_source = ThreadSource.USER
    right.title = "renamed"
    right.tokens_used = 42

    assert left.diff_fields(right) == ["title", "tokens_used"]


def test_anchor_and_epoch_helpers_match_rust_units() -> None:
    # Rust crate: codex-state
    # Rust module/items: anchor_from_item, datetime_to_epoch_*,
    # epoch_millis_to_datetime, epoch_seconds_to_datetime
    # Behavior contract: anchors pick the requested timestamp and old
    # millisecond-looking values before 2020 are treated as legacy seconds.
    metadata = _expected_metadata()
    assert anchor_from_item(metadata, SortKey.CREATED_AT).ts == metadata.created_at
    assert anchor_from_item(metadata, SortKey.UPDATED_AT).ts == metadata.updated_at

    dt = datetime(2026, 1, 1, 12, 0, 0, 123000, tzinfo=timezone.utc)
    assert datetime_to_epoch_millis(dt) == 1_767_268_800_123
    assert datetime_to_epoch_seconds(dt) == 1_767_268_800
    assert epoch_millis_to_datetime(1_700_000_000) == datetime.fromtimestamp(
        1_700_000_000, tz=timezone.utc
    )
    assert epoch_millis_to_datetime(1_700_000_000_123) == datetime.fromtimestamp(
        1_700_000_000, tz=timezone.utc
    ).replace(microsecond=123000)
    assert epoch_seconds_to_datetime(1_700_000_000) == datetime.fromtimestamp(
        1_700_000_000, tz=timezone.utc
    )


def test_thread_metadata_validation_rejects_invalid_row_and_stats_values() -> None:
    # Rust crate: codex-state
    # Rust module/items: ThreadRow::try_from_row, BackfillStats
    # Behavior contract: invalid row scalar domains and negative usize-like
    # counters are rejected.
    with pytest.raises(TypeError, match="id must be a string"):
        _thread_row(id=None)
    with pytest.raises(ValueError, match="tokens_used must fit"):
        _thread_row(tokens_used=2**63)
    with pytest.raises(ValueError, match="unknown thread source"):
        _thread_row(thread_source="future").to_thread_metadata()
    with pytest.raises(ValueError, match="scanned must be non-negative"):
        BackfillStats(scanned=-1)


def test_epoch_helpers_reject_invalid_timestamps() -> None:
    # Rust crate: codex-state
    # Rust module/items: epoch_millis_to_datetime, epoch_seconds_to_datetime
    # Behavior contract: invalid Unix timestamps fail.
    with pytest.raises(ValueError, match="invalid unix timestamp millis"):
        epoch_millis_to_datetime(2**63 - 1)
    with pytest.raises(ValueError, match="invalid unix timestamp seconds"):
        epoch_seconds_to_datetime(2**63 - 1)
