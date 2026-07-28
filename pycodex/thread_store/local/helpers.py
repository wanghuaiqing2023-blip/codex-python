"""Rust ``codex-thread-store::local::helpers`` owner."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from pycodex.protocol import (
    AskForApproval,
    GitInfo,
    RolloutItem,
    SandboxPolicy,
    SessionMetaLine,
    SessionSource,
    ThreadId,
    ThreadMemoryMode,
    ThreadSource,
)
from pycodex.rollout import (
    ARCHIVED_SESSIONS_SUBDIR,
    RolloutRecorder,
    RolloutRecorderParams,
    append_rollout_item_to_path,
    append_thread_name,
    find_archived_thread_path_by_id_str,
    find_thread_name_by_id,
    find_thread_names_by_ids,
    find_thread_path_by_id_str,
    first_rollout_content_match_snippet,
    get_threads,
    get_threads_in_root,
    parse_cursor,
    read_thread_item_from_rollout,
    read_session_meta_line,
    rollout_date_parts,
    search_rollout_paths,
)
from pycodex.rollout.list import list_threads_from_state_metadata

from ..error import ThreadStoreError
from ..in_memory import InMemoryThreadStore
from ..thread_metadata_sync import parse_session_timestamp
from ..types import *
from ..types import (
    _clearable_to_optional_value,
    _enum_or_value,
    _metadata_enum_string,
)


def stored_thread_from_rollout_item(store: LocalThreadStore, item: Any, *, archived: bool) -> StoredThread:
    thread_id = ThreadId.from_string(str(item.thread_id))
    created_at = parse_session_timestamp(getattr(item, "created_at", None)) or datetime.now(timezone.utc)
    updated_at = parse_session_timestamp(getattr(item, "updated_at", None)) or created_at
    return StoredThread(
        thread_id=thread_id,
        rollout_path=Path(item.path),
        forked_from_id=None,
        preview=getattr(item, "preview", None) or getattr(item, "first_user_message", None) or "",
        name=None,
        model_provider=getattr(item, "model_provider", None) or store.config.default_model_provider_id,
        model=None,
        reasoning_effort=None,
        created_at=created_at,
        updated_at=updated_at,
        archived_at=updated_at if archived else None,
        cwd=Path(getattr(item, "cwd", None) or ""),
        cli_version=getattr(item, "cli_version", None) or "",
        source=_coerce_session_source(getattr(item, "source", None)),
        thread_source=None,
        agent_nickname=getattr(item, "agent_nickname", None),
        agent_role=getattr(item, "agent_role", None),
        agent_path=None,
        git_info=_git_info_from_rollout_item(item),
        approval_mode=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.new_read_only_policy(),
        token_usage=None,
        first_user_message=getattr(item, "first_user_message", None),
        history=None,
    )

def _git_info_from_rollout_item(item: Any) -> Any:
    sha = getattr(item, "git_sha", None)
    branch = getattr(item, "git_branch", None)
    origin_url = getattr(item, "git_origin_url", None)
    if sha is None and branch is None and origin_url is None:
        return None
    return GitInfoPatch(sha=sha, branch=branch, origin_url=origin_url)

def _coerce_session_source(value: Any) -> SessionSource:
    if isinstance(value, SessionSource):
        return value
    return SessionSource.from_startup_arg(str(value or "unknown"))

def touch_modified_time(path: Path) -> None:
    Path(path).touch(exist_ok=True)

def distinct_thread_metadata_title(metadata: Any) -> str | None:
    title = str(getattr(metadata, "title", "") or "").strip()
    first_user_message = getattr(metadata, "first_user_message", None)
    if not title or (isinstance(first_user_message, str) and first_user_message.strip() == title):
        return None
    return title

def rollout_path_is_archived(codex_home: Path, rollout_path: Path) -> bool:
    try:
        relative = Path(rollout_path).resolve().relative_to(Path(codex_home).resolve())
    except (OSError, ValueError):
        return False
    return relative.parts[:1] == ("archived_sessions",)

def scoped_rollout_path(root: Path, rollout_path: Path, root_name: str) -> Path:
    try:
        canonical_root = Path(root).resolve(strict=True)
    except OSError as exc:
        raise ThreadStoreError.internal(f"failed to resolve {root_name} directory `{root}`: {exc}") from exc
    try:
        canonical_rollout_path = Path(rollout_path).resolve(strict=True)
    except OSError as exc:
        raise ThreadStoreError.invalid_request(f"rollout path `{rollout_path}` must be in {root_name} directory") from exc
    try:
        canonical_rollout_path.relative_to(canonical_root)
    except ValueError as exc:
        raise ThreadStoreError.invalid_request(f"rollout path `{rollout_path}` must be in {root_name} directory") from exc
    return canonical_rollout_path

def set_thread_name_from_title(thread: StoredThread, title: str) -> StoredThread:
    if not title.strip() or thread.preview.strip() == title.strip():
        return thread
    return replace(thread, name=title)

async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value

def matching_rollout_file_name(rollout_path: Path, thread_id: ThreadId, display_path: Path) -> str:
    file_name = Path(rollout_path).name
    if not file_name:
        raise ThreadStoreError.invalid_request(f"rollout path `{display_path}` missing file name")
    if not file_name.endswith(f"{thread_id}.jsonl"):
        raise ThreadStoreError.invalid_request(f"rollout path `{display_path}` does not match thread id {thread_id}")
    return file_name
