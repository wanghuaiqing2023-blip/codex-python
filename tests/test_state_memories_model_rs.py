from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from pycodex.protocol import ThreadId
from pycodex.state.model.memories import (
    Phase2JobClaimOutcome,
    Phase2JobClaimed,
    Stage1JobClaim,
    Stage1JobClaimOutcome,
    Stage1JobClaimed,
    Stage1Output,
    Stage1StartupClaimParams,
    claimed_phase2,
    claimed_stage1,
)


THREAD_ID = ThreadId.from_string("00000000-0000-0000-0000-000000000123")


def test_stage1_output_normalizes_paths_and_datetimes() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/memories.rs::Stage1Output
    # Behavior contract: stored stage-1 output carries thread/path/timestamp,
    # memory, summary, slug, CWD, and git branch fields.
    naive = datetime(2026, 1, 1, 12, 0, 0)
    plus_two = timezone(timedelta(hours=2))
    output = Stage1Output(
        thread_id=THREAD_ID,
        rollout_path="/tmp/rollout.jsonl",
        source_updated_at=naive,
        raw_memory="remember this",
        rollout_summary="summary",
        rollout_slug="slug",
        cwd="/tmp/workspace",
        git_branch="main",
        generated_at=datetime(2026, 1, 1, 14, 30, tzinfo=plus_two),
    )

    assert output.thread_id == THREAD_ID
    assert output.rollout_path == Path("/tmp/rollout.jsonl")
    assert output.source_updated_at == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert output.raw_memory == "remember this"
    assert output.rollout_summary == "summary"
    assert output.rollout_slug == "slug"
    assert output.cwd == Path("/tmp/workspace")
    assert output.git_branch == "main"
    assert output.generated_at == datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)


def test_stage1_claim_outcomes_and_claimed_variant_shape() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/memories.rs::Stage1JobClaimOutcome
    # Behavior contract: non-claimed outcomes have stable names, while the
    # Claimed variant carries an ownership token.
    assert Stage1JobClaimOutcome.SKIPPED_UP_TO_DATE.value == "skipped_up_to_date"
    assert Stage1JobClaimOutcome.SKIPPED_RUNNING.value == "skipped_running"
    assert Stage1JobClaimOutcome.SKIPPED_RETRY_BACKOFF.value == "skipped_retry_backoff"
    assert Stage1JobClaimOutcome.SKIPPED_RETRY_EXHAUSTED.value == "skipped_retry_exhausted"

    claimed = claimed_stage1("lease-1")

    assert claimed == Stage1JobClaimed(ownership_token="lease-1")


def test_stage1_job_claim_keeps_thread_interface_and_token() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/memories.rs::Stage1JobClaim
    # Behavior contract: a claimed stage-1 job contains thread metadata plus
    # the ownership token.
    thread_metadata = object()
    claim = Stage1JobClaim(thread=thread_metadata, ownership_token="lease-2")

    assert claim.thread is thread_metadata
    assert claim.ownership_token == "lease-2"


def test_stage1_startup_claim_params_validate_usize_i64_and_sources() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/memories.rs::Stage1StartupClaimParams
    # Behavior contract: startup scan/claim limits are usize-like, age/lease
    # settings are i64-like, and allowed sources are string slices.
    params = Stage1StartupClaimParams(
        scan_limit=100,
        max_claimed=10,
        max_age_days=30,
        min_rollout_idle_hours=6,
        allowed_sources=["cli", "exec"],
        lease_seconds=300,
    )

    assert params.scan_limit == 100
    assert params.max_claimed == 10
    assert params.max_age_days == 30
    assert params.min_rollout_idle_hours == 6
    assert params.allowed_sources == ("cli", "exec")
    assert params.lease_seconds == 300


def test_phase2_claim_outcomes_and_claimed_variant_shape() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/memories.rs::Phase2JobClaimOutcome
    # Behavior contract: non-claimed phase-2 outcomes have stable names, while
    # the Claimed variant carries an ownership token and input watermark.
    assert Phase2JobClaimOutcome.SKIPPED_RETRY_UNAVAILABLE.value == "skipped_retry_unavailable"
    assert Phase2JobClaimOutcome.SKIPPED_COOLDOWN.value == "skipped_cooldown"
    assert Phase2JobClaimOutcome.SKIPPED_RUNNING.value == "skipped_running"

    claimed = claimed_phase2("lease-3", 42)

    assert claimed == Phase2JobClaimed(ownership_token="lease-3", input_watermark=42)


def test_memories_model_rejects_invalid_scalar_domains() -> None:
    # Rust crate: codex-state
    # Rust module/items: src/model/memories.rs model structs
    # Behavior contract: Python enforces Rust-compatible scalar domains for
    # identifiers, strings, timestamps, usize, and i64 fields.
    with pytest.raises(TypeError, match="thread_id must be a ThreadId"):
        Stage1Output(
            thread_id="not-a-thread-id",
            rollout_path="/tmp/rollout.jsonl",
            source_updated_at=datetime.now(timezone.utc),
            raw_memory="memory",
            rollout_summary="summary",
            rollout_slug=None,
            cwd="/tmp/workspace",
            git_branch=None,
            generated_at=datetime.now(timezone.utc),
        )

    with pytest.raises(TypeError, match="ownership_token must be a string"):
        claimed_stage1(123)

    with pytest.raises(ValueError, match="scan_limit must be non-negative"):
        Stage1StartupClaimParams(
            scan_limit=-1,
            max_claimed=1,
            max_age_days=1,
            min_rollout_idle_hours=1,
            allowed_sources=(),
            lease_seconds=1,
        )

    with pytest.raises(TypeError, match="allowed_sources must be a sequence of strings"):
        Stage1StartupClaimParams(
            scan_limit=1,
            max_claimed=1,
            max_age_days=1,
            min_rollout_idle_hours=1,
            allowed_sources="cli",
            lease_seconds=1,
        )

    with pytest.raises(ValueError, match="input_watermark must fit"):
        claimed_phase2("lease-4", 2**63)
