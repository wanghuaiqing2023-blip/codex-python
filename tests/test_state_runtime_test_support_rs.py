from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

import pycodex.state as state
import pycodex.state.runtime as runtime
from pycodex.protocol import ReasoningEffort, ThreadId
from pycodex.state.runtime.test_support import (
    TEST_THREAD_METADATA_TIMESTAMP,
    test_thread_metadata as make_test_thread_metadata,
    unique_temp_dir,
)


THREAD_ID = ThreadId.from_string("00000000-0000-0000-0000-000000000123")


def test_unique_temp_dir_matches_rust_prefix_timestamp_uuid_shape() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/runtime/test_support.rs::unique_temp_dir
    # Behavior contract: temp fixture paths live under the system temp dir and
    # use codex-state-runtime-test-{nanos}-{uuid}.
    path = unique_temp_dir()

    assert path.name.startswith("codex-state-runtime-test-")
    prefix = "codex-state-runtime-test-"
    suffix = path.name[len(prefix) :]
    nanos, uuid_text = suffix.split("-", 1)
    assert int(nanos) >= 0
    UUID(uuid_text)


def test_test_thread_metadata_matches_fixed_rust_fixture_values(tmp_path) -> None:
    # Rust crate: codex-state
    # Rust module/item: src/runtime/test_support.rs::test_thread_metadata
    # Behavior contract: fixture metadata uses Rust's fixed timestamp, rollout
    # path shape, provider/model/effort, policy strings, and empty optional
    # agent/archive/git fields.
    cwd = tmp_path / "workspace"

    metadata = make_test_thread_metadata(tmp_path, THREAD_ID, cwd)

    fixed = datetime.fromtimestamp(TEST_THREAD_METADATA_TIMESTAMP, tz=timezone.utc)
    assert metadata.id == THREAD_ID
    assert metadata.rollout_path == tmp_path / f"rollout-{THREAD_ID}.jsonl"
    assert metadata.created_at == fixed
    assert metadata.updated_at == fixed
    assert metadata.source == "cli"
    assert metadata.thread_source is None
    assert metadata.agent_nickname is None
    assert metadata.agent_role is None
    assert metadata.agent_path is None
    assert metadata.model_provider == "test-provider"
    assert metadata.model == "gpt-5"
    assert metadata.reasoning_effort is ReasoningEffort.MEDIUM
    assert metadata.cwd == cwd
    assert metadata.cli_version == "0.0.0"
    assert metadata.title == ""
    assert metadata.preview == "hello"
    assert metadata.sandbox_policy == "read-only"
    assert metadata.approval_mode == "on-request"
    assert metadata.tokens_used == 0
    assert metadata.first_user_message == "hello"
    assert metadata.archived_at is None
    assert metadata.git_sha is None
    assert metadata.git_branch is None
    assert metadata.git_origin_url is None


def test_test_thread_metadata_accepts_string_paths_and_rejects_bad_thread_id(tmp_path) -> None:
    # Rust crate: codex-state
    # Rust module/item: src/runtime/test_support.rs::test_thread_metadata
    # Behavior contract: Python keeps path convenience while preserving the
    # ThreadId interface constraint from Rust.
    metadata = make_test_thread_metadata(str(tmp_path), THREAD_ID, str(tmp_path / "cwd"))

    assert metadata.rollout_path == tmp_path / f"rollout-{THREAD_ID}.jsonl"
    assert metadata.cwd == tmp_path / "cwd"
    with pytest.raises(TypeError, match="thread_id must be a ThreadId"):
        make_test_thread_metadata(tmp_path, "not-a-thread-id", tmp_path)


def test_runtime_test_support_helpers_are_reexported() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/runtime/test_support.rs package export surface
    # Behavior contract: Python exposes these cfg-test-style helpers through
    # runtime and crate-root packages for neighboring tests.
    assert runtime.unique_temp_dir is unique_temp_dir
    assert runtime.test_thread_metadata is make_test_thread_metadata
    assert state.unique_temp_dir is unique_temp_dir
    assert state.test_thread_metadata is make_test_thread_metadata
