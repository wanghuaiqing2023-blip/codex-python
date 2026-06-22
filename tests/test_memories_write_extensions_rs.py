from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from pycodex.memories.write import (
    memory_extensions_root,
    prune_old_extension_resources_with_now,
    resource_timestamp,
    seed_extension_instructions,
)


def test_seeds_instructions_without_overwriting_existing_file(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/extensions/ad_hoc.rs + src/extensions/ad_hoc_tests.rs::seeds_instructions_without_overwriting_existing_file
    # Contract: ad-hoc extension instructions are created once and existing customized instructions are preserved.
    memory_root = tmp_path / "memories"
    instructions_path = memory_extensions_root(memory_root) / "ad_hoc" / "instructions.md"

    asyncio.run(seed_extension_instructions(memory_root))

    seeded = instructions_path.read_text(encoding="utf-8")
    assert seeded.startswith("# Ad-hoc notes")
    assert '[ad-hoc note]' in seeded

    instructions_path.write_text("custom instructions", encoding="utf-8")
    asyncio.run(seed_extension_instructions(memory_root))

    assert instructions_path.read_text(encoding="utf-8") == "custom instructions"


def test_prunes_only_old_resources_from_extensions_with_instructions(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/extensions/prune.rs + src/extensions/prune_tests.rs::prunes_only_old_resources_from_extensions_with_instructions
    # Contract: only timestamped markdown resources at or before the seven-day cutoff are removed, and only for extensions with instructions.
    memory_root = tmp_path / "memories"
    extensions_root = memory_extensions_root(memory_root)
    chronicle_resources = extensions_root / "chronicle" / "resources"
    chronicle_resources.mkdir(parents=True)
    (extensions_root / "chronicle" / "instructions.md").write_text("instructions", encoding="utf-8")

    now = datetime.strptime("2026-04-14T12-00-00", "%Y-%m-%dT%H-%M-%S").replace(tzinfo=UTC)
    old_file = chronicle_resources / "2026-04-06T11-59-59-abcd-10min-old.md"
    exact_cutoff_file = chronicle_resources / "2026-04-07T12-00-00-abcd-10min-cutoff.md"
    recent_file = chronicle_resources / "2026-04-08T12-00-00-abcd-10min-recent.md"
    invalid_file = chronicle_resources / "not-a-timestamp.md"
    for path in (old_file, exact_cutoff_file, recent_file, invalid_file):
        path.write_text("resource", encoding="utf-8")

    ignored_resources = extensions_root / "ignored" / "resources"
    ignored_resources.mkdir(parents=True)
    ignored_old_file = ignored_resources / "2026-04-06T11-59-59-abcd-10min-old.md"
    ignored_old_file.write_text("ignored", encoding="utf-8")

    asyncio.run(prune_old_extension_resources_with_now(memory_root, now))

    assert not old_file.exists()
    assert not exact_cutoff_file.exists()
    assert recent_file.exists()
    assert invalid_file.exists()
    assert ignored_old_file.exists()


def test_parses_timestamp_prefix_from_resource_file_name() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/extensions/prune.rs + src/extensions/prune_tests.rs::parses_timestamp_prefix_from_resource_file_name
    # Contract: resource timestamps parse from the first 19 filename bytes using the extension resource filename format.
    parsed = resource_timestamp("2026-04-06T11-59-59-abcd-10min-old.md")

    assert parsed is not None
    assert int(parsed.timestamp()) == 1_775_476_799
    assert resource_timestamp("not-a-timestamp.md") is None
