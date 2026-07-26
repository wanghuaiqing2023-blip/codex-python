"""Rust ``codex-thread-store::local::update_thread_metadata`` owner."""

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
    _maybe_await,
    distinct_thread_metadata_title,
    rollout_path_is_archived,
)
from .read_thread import (
    _git_branch,
    _git_info_from_state_metadata,
    _git_origin_url,
    _git_sha,
    _read_state_thread_metadata,
    _read_thread_from_rollout_path,
    _stored_thread_from_state_metadata,
)

def _normalize_cwd(cwd: Path) -> Path:
    try:
        return Path(cwd).resolve(strict=False)
    except OSError:
        return Path(cwd)

def _append_thread_git_info_to_rollout(
    rollout_path: Path,
    thread_id: ThreadId,
    *,
    sha: str | None,
    branch: str | None,
    origin_url: str | None,
    memory_mode: str | ThreadMemoryMode | None,
) -> None:
    session_meta = read_session_meta_line(rollout_path)
    if str(session_meta.meta.id) != str(thread_id):
        raise ThreadStoreError.internal(
            "failed to set thread git metadata: "
            f"rollout session metadata id mismatch: expected {thread_id}, found {session_meta.meta.id}"
        )
    memory_value = _enum_or_value(memory_mode) if memory_mode is not None else None
    meta = replace(session_meta.meta, memory_mode=memory_value)
    git = GitInfo(commit_hash=sha, branch=branch, repository_url=origin_url)
    append_rollout_item_to_path(rollout_path, RolloutItem.session_meta(SessionMetaLine(meta=meta, git=git)))

async def _apply_thread_git_info_update(
    store: LocalThreadStore,
    thread_id: ThreadId,
    rollout_path: Path,
    patch: GitInfoPatch,
) -> GitInfoPatch:
    state_db = getattr(store, "_state_db", None)
    if state_db is None:
        raise ThreadStoreError.internal(f"sqlite state db unavailable for thread {thread_id}")
    metadata = await _read_state_thread_metadata(store, thread_id)
    if metadata is None:
        metadata = _state_metadata_from_rollout(store, thread_id, rollout_path)
        upserter = getattr(state_db, "upsert_thread", None)
        if not callable(upserter):
            raise ThreadStoreError.internal(f"sqlite state db unavailable for thread {thread_id}")
        try:
            await _maybe_await(upserter(metadata))
        except Exception as exc:
            raise ThreadStoreError.internal(f"failed to update thread metadata for {thread_id}: {exc}") from exc
    memory_mode = None
    getter = getattr(state_db, "get_thread_memory_mode", None)
    if callable(getter):
        memory_mode = await _maybe_await(getter(thread_id))
    existing_git_info = _git_info_from_state_metadata(metadata)
    sha, branch, origin_url = _resolve_git_info_patch(existing_git_info, patch)
    _append_thread_git_info_to_rollout(
        rollout_path,
        thread_id,
        sha=sha,
        branch=branch,
        origin_url=origin_url,
        memory_mode=memory_mode,
    )
    updater = getattr(state_db, "update_thread_git_info", None)
    if not callable(updater):
        raise ThreadStoreError.internal(f"sqlite state db unavailable for thread {thread_id}")
    try:
        updated = await _maybe_await(updater(thread_id, sha, branch, origin_url))
    except Exception as exc:
        raise ThreadStoreError.internal(f"failed to update git metadata for thread {thread_id}: {exc}") from exc
    if updated is False:
        raise ThreadStoreError.internal(f"thread metadata disappeared before update completed: {thread_id}")
    return GitInfoPatch(sha=sha, branch=branch, origin_url=origin_url)

async def _apply_observed_metadata_update(
    store: LocalThreadStore,
    thread_id: ThreadId,
    patch: ThreadMetadataPatch,
    *,
    include_archived: bool,
    rollout_path: Path | None,
) -> Any:
    state_db = getattr(store, "_state_db", None)
    if state_db is None:
        return None
    existing = await _read_state_thread_metadata(store, thread_id)
    if existing is None:
        if rollout_path is None:
            rollout_path = store._resolve_local_rollout_path(thread_id, include_archived)
        if rollout_path is None:
            raise ThreadStoreError.invalid_request(f"thread not found: {thread_id}")
        metadata = _state_metadata_from_rollout(store, thread_id, rollout_path)
    else:
        metadata = existing
        if rollout_path is not None:
            setattr(metadata, "rollout_path", rollout_path)
    if patch.rollout_path is not None:
        setattr(metadata, "rollout_path", patch.rollout_path)
    if patch.preview is not None:
        setattr(metadata, "preview", patch.preview)
    if patch.name is not None:
        setattr(metadata, "title", _clearable_to_optional_value(patch.name) or "")
    if patch.title is not None:
        setattr(metadata, "title", patch.title)
    if patch.model_provider is not None:
        setattr(metadata, "model_provider", patch.model_provider)
    if patch.model is not None:
        setattr(metadata, "model", patch.model)
    if patch.reasoning_effort is not None:
        setattr(metadata, "reasoning_effort", patch.reasoning_effort)
    if patch.created_at is not None:
        setattr(metadata, "created_at", patch.created_at)
    if patch.updated_at is not None:
        setattr(metadata, "updated_at", patch.updated_at)
    if patch.source is not None:
        setattr(metadata, "source", _metadata_enum_string(patch.source))
    if patch.thread_source is not None:
        setattr(metadata, "thread_source", _clearable_to_optional_value(patch.thread_source))
    if patch.agent_nickname is not None:
        setattr(metadata, "agent_nickname", _clearable_to_optional_value(patch.agent_nickname))
    if patch.agent_role is not None:
        setattr(metadata, "agent_role", _clearable_to_optional_value(patch.agent_role))
    if patch.agent_path is not None:
        setattr(metadata, "agent_path", _clearable_to_optional_value(patch.agent_path))
    if patch.cwd is not None:
        setattr(metadata, "cwd", _normalize_cwd(patch.cwd))
    if patch.cli_version is not None:
        setattr(metadata, "cli_version", patch.cli_version)
    if patch.approval_mode is not None:
        setattr(metadata, "approval_mode", _enum_or_value(patch.approval_mode))
    if patch.sandbox_policy is not None:
        setattr(metadata, "sandbox_policy", _metadata_enum_string(patch.sandbox_policy))
    if patch.token_usage is not None:
        total_tokens = getattr(patch.token_usage, "total_tokens", None)
        if total_tokens is not None:
            setattr(metadata, "tokens_used", max(0, int(total_tokens)))
    if patch.first_user_message is not None:
        setattr(metadata, "first_user_message", patch.first_user_message)
    archived = rollout_path_is_archived(store.config.codex_home or Path(), Path(getattr(metadata, "rollout_path")))
    if archived and getattr(metadata, "archived_at", None) is None:
        setattr(metadata, "archived_at", getattr(metadata, "updated_at", datetime.now(timezone.utc)))
    upserter = getattr(state_db, "upsert_thread", None)
    if callable(upserter):
        await _maybe_await(upserter(metadata))
    return metadata

def _resolve_clearable_git_field(value: Any, existing: str | None) -> str | None:
    if value is None:
        return existing
    if is_clear_field(value):
        return None
    return str(value)

def _append_thread_memory_mode_to_rollout(
    rollout_path: Path,
    thread_id: ThreadId,
    memory_mode: ThreadMemoryMode,
) -> None:
    session_meta = read_session_meta_line(rollout_path)
    if str(session_meta.meta.id) != str(thread_id):
        raise ThreadStoreError.internal(
            "failed to set thread memory mode: "
            f"rollout session metadata id mismatch: expected {thread_id}, found {session_meta.meta.id}"
        )
    meta = replace(session_meta.meta, memory_mode=_enum_or_value(memory_mode))
    append_rollout_item_to_path(rollout_path, RolloutItem.session_meta(SessionMetaLine(meta=meta, git=None)))

def _stored_thread_from_rollout_path(
    thread_id: ThreadId,
    rollout_path: Path,
    default_provider: str,
    *,
    patch: ThreadMetadataPatch,
) -> StoredThread:
    meta = read_session_meta_line(rollout_path).meta
    created_at = parse_session_timestamp(meta.timestamp) or datetime.now(timezone.utc)
    return StoredThread(
        thread_id=thread_id,
        rollout_path=rollout_path,
        forked_from_id=meta.forked_from_id,
        preview=patch.preview or patch.first_user_message or "",
        name=_clearable_to_optional_value(patch.name),
        model_provider=patch.model_provider or meta.model_provider or default_provider,
        model=patch.model,
        reasoning_effort=patch.reasoning_effort,
        created_at=patch.created_at or created_at,
        updated_at=patch.updated_at or created_at,
        archived_at=None,
        cwd=patch.cwd or meta.cwd,
        cli_version=patch.cli_version or meta.cli_version,
        source=patch.source or meta.source,
        thread_source=_clearable_to_optional_value(patch.thread_source, meta.thread_source),
        agent_nickname=_clearable_to_optional_value(patch.agent_nickname, meta.agent_nickname),
        agent_role=_clearable_to_optional_value(patch.agent_role, meta.agent_role),
        agent_path=_clearable_to_optional_value(patch.agent_path, meta.agent_path),
        git_info=None,
        approval_mode=patch.approval_mode or AskForApproval.ON_REQUEST,
        sandbox_policy=patch.sandbox_policy or SandboxPolicy.new_read_only_policy(),
        token_usage=patch.token_usage,
        first_user_message=patch.first_user_message,
        history=None,
    )

def _patch_has_observed_metadata_facts(patch: ThreadMetadataPatch) -> bool:
    return any(
        value is not None
        for value in (
            patch.rollout_path,
            patch.preview,
            patch.title,
            patch.model_provider,
            patch.model,
            patch.reasoning_effort,
            patch.created_at,
            patch.updated_at,
            patch.source,
            patch.thread_source,
            patch.agent_nickname,
            patch.agent_role,
            patch.agent_path,
            patch.cwd,
            patch.cli_version,
            patch.approval_mode,
            patch.sandbox_policy,
            patch.token_usage,
            patch.first_user_message,
        )
    )

def _handle_sqlite_write_exception(patch: ThreadMetadataPatch, exc: BaseException) -> None:
    if _sqlite_write_failure_should_block(patch) or not _sqlite_write_error_is_best_effort(exc):
        if isinstance(exc, ThreadStoreError):
            raise exc
        raise ThreadStoreError.internal(f"failed to update thread metadata: {exc}") from exc

async def _apply_thread_name_update(store: LocalThreadStore, thread_id: ThreadId, name: str) -> None:
    state_db = getattr(store, "_state_db", None)
    if state_db is None:
        return
    updater = getattr(state_db, "update_thread_title", None)
    if callable(updater):
        updated = await _maybe_await(updater(thread_id, name))
        if updated is False:
            metadata = await _read_state_thread_metadata(store, thread_id)
            if metadata is None:
                return
            setattr(metadata, "title", name)
            upserter = getattr(state_db, "upsert_thread", None)
            if callable(upserter):
                await _maybe_await(upserter(metadata))
        return
    metadata = await _read_state_thread_metadata(store, thread_id)
    if metadata is None:
        return
    setattr(metadata, "title", name)
    upserter = getattr(state_db, "upsert_thread", None)
    if callable(upserter):
        await _maybe_await(upserter(metadata))

def _sqlite_write_failure_should_block(patch: ThreadMetadataPatch) -> bool:
    return patch.git_info is not None and not _patch_has_observed_metadata_facts(patch)

def _state_metadata_from_rollout(store: LocalThreadStore, thread_id: ThreadId, rollout_path: Path) -> Any:
    from pycodex.state.model.thread_metadata import ThreadMetadataBuilder

    meta = read_session_meta_line(rollout_path).meta
    created_at = parse_session_timestamp(meta.timestamp) or datetime.now(timezone.utc)
    builder = ThreadMetadataBuilder.new(
        thread_id,
        rollout_path,
        created_at,
        SessionSource.from_startup_arg(meta.source),
    )
    builder.model_provider = meta.model_provider
    builder.thread_source = meta.thread_source
    builder.agent_nickname = meta.agent_nickname
    builder.agent_role = meta.agent_role
    builder.agent_path = meta.agent_path
    builder.cwd = Path(meta.cwd)
    builder.cli_version = meta.cli_version
    metadata = builder.build(store.config.default_model_provider_id)
    if rollout_path_is_archived(store.config.codex_home or Path(), rollout_path):
        metadata.archived_at = metadata.updated_at
    return metadata

def _sqlite_write_error_is_best_effort(exc: BaseException) -> bool:
    return not isinstance(exc, ThreadStoreError) or exc.kind == "internal"

def _resolve_git_info_patch(existing_git_info: Any, patch: GitInfoPatch) -> tuple[str | None, str | None, str | None]:
    return (
        _resolve_clearable_git_field(patch.sha, _git_sha(existing_git_info)),
        _resolve_clearable_git_field(patch.branch, _git_branch(existing_git_info)),
        _resolve_clearable_git_field(patch.origin_url, _git_origin_url(existing_git_info)),
    )

async def update_thread_metadata(store: Any, params: UpdateThreadMetadataParams) -> StoredThread:
    if params.patch.is_empty():
        return await store.read_thread(
            ReadThreadParams(
                thread_id=params.thread_id,
                include_archived=params.include_archived,
                include_history=False,
              )
          )
    observed_metadata_update = _patch_has_observed_metadata_facts(params.patch)
    if params.thread_id in store._created_threads:
        stored: StoredThread | None = await InMemoryThreadStore.update_thread_metadata(store, params)
    else:
        existing_patch = store._metadata_updates.get(params.thread_id, ThreadMetadataPatch())
        store._metadata_updates[params.thread_id] = existing_patch.merge(params.patch)
        stored = None
    if (
        params.thread_id in store._live_recorders
        and (params.patch.name is not None or params.patch.memory_mode is not None or params.patch.git_info is not None)
    ):
        await store.persist_thread(params.thread_id)
    rollout_path = store._resolve_local_rollout_path(params.thread_id, params.include_archived)
    observed_metadata = None
    if observed_metadata_update:
        try:
            observed_metadata = await _apply_observed_metadata_update(
                store,
                params.thread_id,
                params.patch,
                include_archived=params.include_archived,
                rollout_path=rollout_path,
            )
        except Exception as exc:
            _handle_sqlite_write_exception(params.patch, exc)
            observed_metadata = None
        if rollout_path is None:
            rollout_path = Path(getattr(observed_metadata, "rollout_path")) if observed_metadata is not None else None
    if params.patch.memory_mode is not None:
        if rollout_path is None:
            raise ThreadStoreError.internal(f"thread metadata unavailable before memory mode update: {params.thread_id}")
        _append_thread_memory_mode_to_rollout(rollout_path, params.thread_id, params.patch.memory_mode)
    if params.patch.name is not None:
        name = _clearable_to_optional_value(params.patch.name)
        append_thread_name(store.config.codex_home or Path(), params.thread_id, "" if name is None else name)
        try:
            await _apply_thread_name_update(store, params.thread_id, "" if name is None else name)
        except Exception as exc:
            _handle_sqlite_write_exception(params.patch, exc)
    if rollout_path is not None and params.thread_id not in store._created_threads:
        stored = _read_thread_from_rollout_path(
            store,
            rollout_path,
            include_archived=params.include_archived,
            include_history=False,
        )
    if params.patch.git_info is not None:
        if rollout_path is None:
            raise ThreadStoreError.internal(f"thread metadata unavailable before git update: {params.thread_id}")
        git_info = await _apply_thread_git_info_update(store, params.thread_id, rollout_path, params.patch.git_info)
        if stored is None:
            stored = _read_thread_from_rollout_path(
                store,
                rollout_path,
                include_archived=params.include_archived,
                include_history=False,
            )
        stored = replace(stored, git_info=git_info)
    if observed_metadata is not None and rollout_path is not None:
        try:
            rollout_thread = _read_thread_from_rollout_path(
                store,
                rollout_path,
                include_archived=params.include_archived,
                include_history=False,
            )
            stored = replace(
                rollout_thread,
                name=distinct_thread_metadata_title(observed_metadata) or rollout_thread.name,
                git_info=_git_info_from_state_metadata(observed_metadata) or rollout_thread.git_info,
            )
        except Exception:
            stored = _stored_thread_from_state_metadata(store, observed_metadata)
    if stored is None:
        raise ThreadStoreError.invalid_request(f"thread not found: {params.thread_id}")
    return stored
