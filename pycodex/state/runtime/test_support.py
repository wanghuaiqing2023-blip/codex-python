"""Runtime test-support helpers ported from ``codex-state/src/runtime/test_support.rs``."""

from __future__ import annotations

import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pycodex.protocol import AskForApproval, ReasoningEffort, SandboxPolicy, ThreadId

from ..extract import enum_to_string
from ..model import ThreadMetadata

TEST_THREAD_METADATA_TIMESTAMP = 1_700_000_000


def unique_temp_dir() -> Path:
    nanos = time.time_ns()
    return Path(tempfile.gettempdir()) / f"codex-state-runtime-test-{nanos}-{uuid.uuid4()}"


def test_thread_metadata(
    codex_home: Path | str,
    thread_id: ThreadId,
    cwd: Path | str,
) -> ThreadMetadata:
    if not isinstance(thread_id, ThreadId):
        raise TypeError("thread_id must be a ThreadId")
    codex_home_path = _path(codex_home, "codex_home")
    cwd_path = _path(cwd, "cwd")
    now = datetime.fromtimestamp(TEST_THREAD_METADATA_TIMESTAMP, tz=UTC)
    return ThreadMetadata(
        id=thread_id,
        rollout_path=codex_home_path / f"rollout-{thread_id}.jsonl",
        created_at=now,
        updated_at=now,
        source="cli",
        thread_source=None,
        agent_nickname=None,
        agent_role=None,
        agent_path=None,
        model_provider="test-provider",
        model="gpt-5",
        reasoning_effort=ReasoningEffort.MEDIUM,
        cwd=cwd_path,
        cli_version="0.0.0",
        title="",
        preview="hello",
        sandbox_policy=enum_to_string(SandboxPolicy.new_read_only_policy()),
        approval_mode=enum_to_string(AskForApproval.ON_REQUEST),
        tokens_used=0,
        first_user_message="hello",
        archived_at=None,
        git_sha=None,
        git_branch=None,
        git_origin_url=None,
    )


def _path(value: Path | str, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a string or Path")
    return Path(value)


__all__ = ["TEST_THREAD_METADATA_TIMESTAMP", "test_thread_metadata", "unique_temp_dir"]
