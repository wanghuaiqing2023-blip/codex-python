from __future__ import annotations

import asyncio
from pathlib import Path

from pycodex.git_utils import GitBaselineChange, GitBaselineChangeStatus, GitBaselineDiff
from pycodex.memories.write import (
    PHASE2_WORKSPACE_DIFF_FILENAME,
    PHASE2_WORKSPACE_DIFF_MAX_BYTES,
    memory_workspace_diff,
    prepare_memory_workspace,
    previous_char_boundary,
    render_workspace_diff_file,
    reset_memory_workspace_baseline,
    write_workspace_diff,
)


def test_render_workspace_diff_file_bounds_large_diff() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/workspace.rs + src/workspace_tests.rs::render_workspace_diff_file_bounds_large_diff
    # Contract: rendered workspace diff includes status rows and truncates large unified diffs at the configured byte limit.
    diff = GitBaselineDiff(
        changes=[GitBaselineChange(GitBaselineChangeStatus.MODIFIED, "MEMORY.md")],
        unified_diff="a" * (PHASE2_WORKSPACE_DIFF_MAX_BYTES + 128),
    )

    rendered = render_workspace_diff_file(diff)

    assert "- M MEMORY.md" in rendered
    assert f"[workspace diff truncated at {PHASE2_WORKSPACE_DIFF_MAX_BYTES} bytes]" in rendered
    assert rendered.endswith("```\n")


def test_reset_memory_workspace_baseline_removes_generated_diff(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/workspace.rs + src/workspace_tests.rs::reset_memory_workspace_baseline_removes_generated_diff
    # Contract: reset removes the generated phase2 diff artifact before making the current memory root the new baseline.
    root = tmp_path / "memories"
    asyncio.run(prepare_memory_workspace(root))
    (root / "MEMORY.md").write_text("memory", encoding="utf-8")
    asyncio.run(
        write_workspace_diff(
            root,
            GitBaselineDiff(
                changes=[GitBaselineChange(GitBaselineChangeStatus.ADDED, "MEMORY.md")],
                unified_diff="+memory\n",
            ),
        )
    )

    asyncio.run(reset_memory_workspace_baseline(root))

    assert not (root / PHASE2_WORKSPACE_DIFF_FILENAME).exists()
    diff = asyncio.run(memory_workspace_diff(root))
    assert diff.changes == []


def test_prepare_memory_workspace_recovers_unusable_git_dir(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/workspace.rs + src/workspace_tests.rs::prepare_memory_workspace_recovers_unusable_git_dir
    # Contract: an unusable .git directory is replaced with a usable baseline repository.
    root = tmp_path / "memories"
    (root / ".git").mkdir(parents=True)
    (root / "MEMORY.md").write_text("memory", encoding="utf-8")

    asyncio.run(prepare_memory_workspace(root))

    diff = asyncio.run(memory_workspace_diff(root))
    assert diff.changes == []


def test_previous_char_boundary_handles_multibyte_text() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/workspace.rs + src/workspace_tests.rs::previous_char_boundary_handles_multibyte_text
    # Contract: byte truncation backs up to the previous UTF-8 character boundary.
    assert previous_char_boundary("aé", 2) == 1
