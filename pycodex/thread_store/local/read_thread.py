"""Rust ``codex-thread-store::local::read_thread`` owner."""

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
    list_threads_from_state_metadata,
    parse_cursor,
    read_thread_item_from_rollout,
    read_session_meta_line,
    rollout_date_parts,
    search_rollout_paths,
)

from ..error import ThreadStoreError
from ..in_memory import InMemoryThreadStore
from ..thread_metadata_sync import parse_session_timestamp
from ..types import *
from ..types import (
    _clearable_to_optional_value,
    _enum_or_value,
    _metadata_enum_string,
)

from .helpers import (
    _git_info_from_rollout_item,
    _maybe_await,
    distinct_thread_metadata_title,
    rollout_path_is_archived,
    stored_thread_from_rollout_item,
)

def _merge_state_git_info(metadata: Any, existing_git_info: Any) -> Any:
    fallback_sha = _git_sha(existing_git_info)
    fallback_branch = _git_branch(existing_git_info)
    fallback_origin_url = _git_origin_url(existing_git_info)
    sha = getattr(metadata, "git_sha", None) or fallback_sha
    branch = getattr(metadata, "git_branch", None) or fallback_branch
    origin_url = getattr(metadata, "git_origin_url", None) or fallback_origin_url
    if sha is None and branch is None and origin_url is None:
        return None
    return GitInfoPatch(sha=sha, branch=branch, origin_url=origin_url)

def _git_sha(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "sha", None) or getattr(value, "commit_hash", None)

def _git_info_from_state_metadata(metadata: Any) -> Any:
    sha = getattr(metadata, "git_sha", None)
    branch = getattr(metadata, "git_branch", None)
    origin_url = getattr(metadata, "git_origin_url", None)
    if sha is None and branch is None and origin_url is None:
        return None
    return GitInfoPatch(sha=sha, branch=branch, origin_url=origin_url)

def _read_thread_from_rollout_path(
    store: LocalThreadStore,
    rollout_path: Path,
    *,
    include_archived: bool,
    include_history: bool,
) -> StoredThread:
    rollout_path = Path(rollout_path)
    archived = rollout_path_is_archived(store.config.codex_home or Path(), rollout_path)
    if archived and not include_archived:
        meta = read_session_meta_line(rollout_path).meta
        raise ThreadStoreError.invalid_request(f"thread {meta.id} is archived")
    item = read_thread_item_from_rollout(rollout_path)
    if item is None or item.thread_id is None:
        thread = _stored_thread_from_session_meta(store, rollout_path, archived=archived)
    else:
        thread = stored_thread_from_rollout_item(store, item, archived=archived)
        try:
            meta_line = read_session_meta_line(rollout_path)
        except ValueError:
            meta_line = None
        if meta_line is not None:
            meta = meta_line.meta
            thread = replace(
                thread,
                forked_from_id=ThreadId.from_string(str(meta.forked_from_id)) if meta.forked_from_id else None,
                model_provider=meta.model_provider or thread.model_provider,
            )
        thread_name = find_thread_name_by_id(store.config.codex_home or Path(), thread.thread_id)
        if thread_name is not None and thread_name.strip():
            thread = replace(thread, name=thread_name)
    if include_history:
        thread = replace(thread, history=_load_history_from_rollout_path(thread.thread_id, rollout_path))
    return thread

async def _read_state_thread_metadata(store: LocalThreadStore, thread_id: ThreadId) -> Any | None:
    state_db = getattr(store, "_state_db", None)
    if state_db is None:
        return None
    getter = getattr(state_db, "get_thread", None)
    if not callable(getter):
        return None
    try:
        return await _maybe_await(getter(thread_id))
    except Exception:
        return None

def _state_metadata_forked_from_id(rollout_path: Path) -> ThreadId | None:
    try:
        meta = read_session_meta_line(rollout_path).meta
    except Exception:
        return None
    return ThreadId.from_string(str(meta.forked_from_id)) if meta.forked_from_id else None

def _parse_sandbox_or_default(value: Any) -> SandboxPolicy:
    if isinstance(value, SandboxPolicy):
        return value
    if isinstance(value, str):
        if value == "danger-full-access":
            return SandboxPolicy.danger_full_access()
        if value == "workspace-write":
            return SandboxPolicy.workspace_write()
        if value == "read-only":
            return SandboxPolicy.new_read_only_policy()
    if isinstance(value, Mapping):
        try:
            return SandboxPolicy.from_mapping(value)
        except Exception:
            return SandboxPolicy.new_read_only_policy()
    return SandboxPolicy.new_read_only_policy()

def _stored_thread_from_session_meta(store: LocalThreadStore, rollout_path: Path, *, archived: bool) -> StoredThread:
    meta_line = read_session_meta_line(rollout_path)
    meta = meta_line.meta
    thread_id = ThreadId.from_string(str(meta.id))
    created_at = parse_session_timestamp(meta.timestamp) or datetime.now(timezone.utc)
    try:
        updated_at = datetime.fromtimestamp(Path(rollout_path).stat().st_mtime, timezone.utc)
    except OSError:
        updated_at = created_at
    return StoredThread(
        thread_id=thread_id,
        rollout_path=Path(rollout_path),
        forked_from_id=ThreadId.from_string(str(meta.forked_from_id)) if meta.forked_from_id else None,
        preview="",
        name=None,
        model_provider=meta.model_provider or store.config.default_model_provider_id,
        model=None,
        reasoning_effort=None,
        created_at=created_at,
        updated_at=updated_at,
        archived_at=updated_at if archived else None,
        cwd=Path(meta.cwd),
        cli_version=meta.cli_version,
        source=SessionSource.from_startup_arg(meta.source),
        thread_source=ThreadSource.parse(meta.thread_source) if meta.thread_source else None,
        agent_nickname=meta.agent_nickname,
        agent_role=meta.agent_role,
        agent_path=meta.agent_path,
        git_info=meta_line.git,
        approval_mode=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.new_read_only_policy(),
        token_usage=None,
        first_user_message=None,
        history=None,
    )

def _git_branch(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "branch", None)

def _git_origin_url(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "origin_url", None) or getattr(value, "repository_url", None)

def _load_history_from_rollout_path(thread_id: ThreadId, rollout_path: Path) -> StoredThreadHistory:
    try:
        items, _rollout_thread_id, _parse_errors = RolloutRecorder.load_rollout_items(rollout_path)
    except OSError as exc:
        raise ThreadStoreError.internal(f"failed to load thread history {rollout_path}: {exc}") from exc
    return StoredThreadHistory(thread_id, tuple(items))

def _parse_approval_or_default(value: Any) -> AskForApproval:
    if isinstance(value, AskForApproval):
        return value
    if isinstance(value, str) and value:
        try:
            return AskForApproval.parse(value)
        except Exception:
            return AskForApproval.ON_REQUEST
    return AskForApproval.ON_REQUEST

def _state_metadata_can_satisfy_read(
    store: LocalThreadStore,
    metadata: Any,
    params: ReadThreadParams,
) -> bool:
    if not params.include_archived:
        if getattr(metadata, "archived_at", None) is not None:
            return False
        rollout_path = getattr(metadata, "rollout_path", None)
        if rollout_path is not None and rollout_path_is_archived(store.config.codex_home or Path(), Path(rollout_path)):
            return False
    if not params.include_history:
        return True
    rollout_path = getattr(metadata, "rollout_path", None)
    if rollout_path is None or not Path(rollout_path).exists():
        return False
    try:
        thread = _read_thread_from_rollout_path(
            store,
            Path(rollout_path),
            include_archived=params.include_archived,
            include_history=False,
        )
    except Exception:
        return False
    return str(thread.thread_id) == str(params.thread_id)

def _stored_thread_from_state_metadata(store: LocalThreadStore, metadata: Any) -> StoredThread:
    thread_id = ThreadId.from_string(str(getattr(metadata, "id")))
    rollout_path = Path(getattr(metadata, "rollout_path"))
    first_user_message = getattr(metadata, "first_user_message", None)
    preview = getattr(metadata, "preview", None) or first_user_message or ""
    title = distinct_thread_metadata_title(metadata)
    if title is None:
        title = find_thread_name_by_id(store.config.codex_home or Path(), thread_id)
        if title is not None and not title.strip():
            title = None
    return StoredThread(
        thread_id=thread_id,
        rollout_path=rollout_path,
        forked_from_id=_state_metadata_forked_from_id(rollout_path),
        preview=preview,
        name=title,
        model_provider=getattr(metadata, "model_provider", None) or store.config.default_model_provider_id,
        model=getattr(metadata, "model", None),
        reasoning_effort=getattr(metadata, "reasoning_effort", None),
        created_at=getattr(metadata, "created_at"),
        updated_at=getattr(metadata, "updated_at"),
        archived_at=getattr(metadata, "archived_at", None),
        cwd=Path(getattr(metadata, "cwd", Path())),
        cli_version=getattr(metadata, "cli_version", "") or "",
        source=SessionSource.from_startup_arg(getattr(metadata, "source", "unknown") or "unknown"),
        thread_source=getattr(metadata, "thread_source", None),
        agent_nickname=getattr(metadata, "agent_nickname", None),
        agent_role=getattr(metadata, "agent_role", None),
        agent_path=getattr(metadata, "agent_path", None),
        git_info=_git_info_from_state_metadata(metadata),
        approval_mode=_parse_approval_or_default(getattr(metadata, "approval_mode", None)),
        sandbox_policy=_parse_sandbox_or_default(getattr(metadata, "sandbox_policy", None)),
        token_usage=None,
        first_user_message=first_user_message,
        history=None,
    )

async def read_thread_by_rollout_path(store: Any, params: ReadThreadByRolloutPathParams) -> StoredThread:
    path = params.rollout_path
    if not path.is_absolute():
        path = (store.config.codex_home or Path()).joinpath(path)
    try:
        path = path.resolve(strict=True)
    except OSError as exc:
        raise ThreadStoreError.invalid_request(f"failed to resolve rollout path `{path}`: {exc}") from exc
    thread = _read_thread_from_rollout_path(
        store,
        path,
        include_archived=params.include_archived,
        include_history=params.include_history,
    )
    metadata = await _read_state_thread_metadata(store, thread.thread_id)
    if metadata is not None:
        thread = replace(thread, git_info=_merge_state_git_info(metadata, thread.git_info))
    return thread

async def load_history(store: Any, params: LoadThreadHistoryParams) -> StoredThreadHistory:
    if params.thread_id in store._histories:
        return await InMemoryThreadStore.load_history(store, params)
    rollout_path = store._resolve_local_rollout_path(params.thread_id, params.include_archived)
    if rollout_path is None:
        raise ThreadStoreError.invalid_request(f"no rollout found for thread id {params.thread_id}")
    return _load_history_from_rollout_path(params.thread_id, rollout_path)

async def read_thread(store: Any, params: ReadThreadParams) -> StoredThread:
    if params.thread_id in store._created_threads:
        return await InMemoryThreadStore.read_thread(store, params)
    metadata = await _read_state_thread_metadata(store, params.thread_id)
    if metadata is not None and _state_metadata_can_satisfy_read(store, metadata, params):
        thread = _stored_thread_from_state_metadata(store, metadata)
        if not params.include_history:
            rollout_path = getattr(metadata, "rollout_path", None)
            if rollout_path is not None:
                try:
                    rollout_thread = _read_thread_from_rollout_path(
                        store,
                        Path(rollout_path),
                        include_archived=params.include_archived,
                        include_history=False,
                    )
                except Exception:
                    rollout_thread = None
                if (
                    rollout_thread is not None
                    and str(rollout_thread.thread_id) == str(params.thread_id)
                    and (params.include_archived or rollout_thread.archived_at is None)
                    and rollout_thread.preview
                ):
                    thread = replace(
                        rollout_thread,
                        name=thread.name if thread.name is not None else rollout_thread.name,
                        git_info=thread.git_info,
                    )
        if params.include_history:
            thread = replace(thread, history=_load_history_from_rollout_path(params.thread_id, thread.rollout_path))
        return thread
    rollout_path = store._resolve_local_rollout_path(params.thread_id, params.include_archived)
    if rollout_path is None:
        raise ThreadStoreError.invalid_request(f"no rollout found for thread id {params.thread_id}")
    thread = _read_thread_from_rollout_path(
        store,
        rollout_path,
        include_archived=params.include_archived,
        include_history=params.include_history,
    )
    if str(thread.thread_id) != str(params.thread_id):
        raise ThreadStoreError.invalid_request(f"no rollout found for thread id {params.thread_id}")
    return thread
