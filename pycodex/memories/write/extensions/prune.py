"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import os

async def prune_old_extension_resources(memory_root_path: str | Path) -> None:
    await prune_old_extension_resources_with_now(memory_root_path, datetime.now(UTC))


async def prune_old_extension_resources_with_now(memory_root_path: str | Path, now: datetime) -> None:
    normalized_now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    cutoff = normalized_now.astimezone(UTC) - timedelta(days=EXTENSION_RESOURCE_RETENTION_DAYS)
    extensions_root = memory_extensions_root(memory_root_path)
    try:
        extension_entries = list(os.scandir(extensions_root))
    except FileNotFoundError:
        return
    except OSError:
        return
    for extension_entry in extension_entries:
        try:
            is_extension_dir = extension_entry.is_dir(follow_symlinks=False)
        except OSError:
            continue
        if not is_extension_dir:
            continue
        extension_path = Path(extension_entry.path)
        if not (extension_path / 'instructions.md').exists():
            continue
        resources_path = extension_path / 'resources'
        try:
            resource_entries = list(os.scandir(resources_path))
        except FileNotFoundError:
            continue
        except OSError:
            continue
        for resource_entry in resource_entries:
            try:
                is_file = resource_entry.is_file(follow_symlinks=False)
            except OSError:
                continue
            if not is_file:
                continue
            file_name = resource_entry.name
            if not file_name.endswith('.md'):
                continue
            resource_time = resource_timestamp(file_name)
            if resource_time is None or resource_time > cutoff:
                continue
            try:
                Path(resource_entry.path).unlink()
            except FileNotFoundError:
                pass
            except OSError:
                continue


def resource_timestamp(file_name: str) -> datetime | None:
    timestamp = file_name[:19]
    try:
        parsed = datetime.strptime(timestamp, FILENAME_TS_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


from pycodex.memories.write import memory_extensions_root
from pycodex.memories.write.extension_resources import FILENAME_TS_FORMAT
from pycodex.memories.write.extension_resources import RETENTION_DAYS as EXTENSION_RESOURCE_RETENTION_DAYS
