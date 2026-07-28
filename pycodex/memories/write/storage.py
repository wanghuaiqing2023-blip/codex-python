"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import UUID
from pycodex.config.types import DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION
from pycodex.state import Stage1Output

async def rebuild_raw_memories_file_from_memories(root: str | Path, memories: Iterable[Stage1Output], max_raw_memories_for_consolidation: int=DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION) -> None:
    await ensure_layout(root)
    retained = _retained_memories(list(memories), max_raw_memories_for_consolidation)
    body = '# Raw Memories\n\n'
    if not retained:
        raw_memories_file(root).write_text(body + 'No raw memories yet.\n', encoding='utf-8')
        return
    body += 'Merged stage-1 raw memories (stable ascending thread-id order):\n\n'
    for memory in retained:
        summary_file = f'{rollout_summary_file_stem(memory)}.md'
        body += f'## Thread `{memory.thread_id}`\n'
        body += f'updated_at: {_rfc3339(memory.source_updated_at)}\n'
        body += f'cwd: {_display_path(memory.cwd)}\n'
        body += f'rollout_path: {_display_path(memory.rollout_path)}\n'
        body += f'rollout_summary_file: {summary_file}\n\n'
        body += memory.raw_memory.strip()
        body += '\n\n'
    raw_memories_file(root).write_text(body, encoding='utf-8')


async def sync_rollout_summaries_from_memories(root: str | Path, memories: Iterable[Stage1Output], max_raw_memories_for_consolidation: int=DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION) -> None:
    await ensure_layout(root)
    retained = _retained_memories(list(memories), max_raw_memories_for_consolidation)
    keep = {rollout_summary_file_stem(memory) for memory in retained}
    summaries_dir = rollout_summaries_dir(root)
    if summaries_dir.exists():
        for path in summaries_dir.iterdir():
            if path.name.endswith('.md') and path.stem not in keep:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
    for memory in retained:
        _write_rollout_summary_for_thread(root, memory)


def rollout_summary_file_stem(memory: Stage1Output) -> str:
    return _rollout_summary_file_stem_from_parts(memory.thread_id, memory.source_updated_at, memory.rollout_slug)


def _write_rollout_summary_for_thread(root: str | Path, memory: Stage1Output) -> None:
    path = rollout_summaries_dir(root) / f'{rollout_summary_file_stem(memory)}.md'
    body = f'thread_id: {memory.thread_id}\n'
    body += f'updated_at: {_rfc3339(memory.source_updated_at)}\n'
    body += f'rollout_path: {_display_path(memory.rollout_path)}\n'
    body += f'cwd: {_display_path(memory.cwd)}\n'
    if memory.git_branch is not None:
        body += f'git_branch: {memory.git_branch}\n'
    body += '\n'
    body += memory.rollout_summary
    body += '\n'
    path.write_text(body, encoding='utf-8')


def _retained_memories(memories: list[Stage1Output], limit: int) -> list[Stage1Output]:
    return memories[:min(len(memories), max(0, int(limit)))]


def _rollout_summary_file_stem_from_parts(thread_id: str, source_updated_at: datetime, rollout_slug: str | None) -> str:
    slug_max_len = 60
    alphabet = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    hash_space = 14776336
    thread_id_text = str(thread_id)
    try:
        thread_uuid = UUID(thread_id_text)
    except ValueError:
        short_hash_seed = 0
        for byte in thread_id_text.encode('utf-8'):
            short_hash_seed = short_hash_seed * 31 + byte & 4294967295
        timestamp = _as_utc(source_updated_at)
    else:
        timestamp = _uuid_timestamp_or_source_time(thread_uuid, source_updated_at)
        short_hash_seed = thread_uuid.int & 4294967295
    short_hash_value = short_hash_seed % hash_space
    chars = ['0'] * 4
    for idx in range(len(chars) - 1, -1, -1):
        chars[idx] = alphabet[short_hash_value % len(alphabet)]
        short_hash_value //= len(alphabet)
    file_prefix = f"{timestamp.strftime('%Y-%m-%dT%H-%M-%S')}-{''.join(chars)}"
    if rollout_slug is None:
        return file_prefix
    slug = ''
    for ch in rollout_slug:
        if len(slug) >= slug_max_len:
            break
        slug += ch.lower() if ch.isascii() and ch.isalnum() else '_'
    slug = slug.rstrip('_')
    return file_prefix if not slug else f'{file_prefix}-{slug}'


def _uuid_timestamp_or_source_time(thread_uuid: UUID, source_updated_at: datetime) -> datetime:
    if thread_uuid.version == 7:
        millis = thread_uuid.int >> 80
        return datetime.fromtimestamp(millis / 1000, tz=UTC)
    if thread_uuid.version == 1:
        seconds = (thread_uuid.time - 122192928000000000) / 10000000
        return datetime.fromtimestamp(seconds, tz=UTC)
    return _as_utc(source_updated_at)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _rfc3339(value: datetime) -> str:
    return _as_utc(value).isoformat().replace('+00:00', 'Z')


from pycodex.memories.write import ensure_layout
from pycodex.memories.write import raw_memories_file
from pycodex.memories.write import rollout_summaries_dir
from pycodex.memories.write.prompts import _display_path
