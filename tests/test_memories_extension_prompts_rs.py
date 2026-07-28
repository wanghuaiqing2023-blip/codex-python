from __future__ import annotations

import asyncio
from pathlib import Path

from pycodex.ext.memories.prompts import (
    build_memory_tool_developer_instructions,
    parse_embedded_template,
)


def test_prompt_is_absent_without_nonempty_summary(tmp_path: Path) -> None:
    assert asyncio.run(build_memory_tool_developer_instructions(tmp_path)) is None
    memories = tmp_path / "memories"
    memories.mkdir()
    (memories / "memory_summary.md").write_text(" \n", encoding="utf-8")
    assert asyncio.run(build_memory_tool_developer_instructions(tmp_path)) is None


def test_prompt_renders_rust_template_with_summary_and_path(tmp_path: Path) -> None:
    memories = tmp_path / "memories"
    memories.mkdir()
    (memories / "memory_summary.md").write_text("project convention", encoding="utf-8")

    prompt = asyncio.run(build_memory_tool_developer_instructions(tmp_path))

    assert prompt is not None
    assert "## Memory" in prompt
    assert str(memories) in prompt
    assert "project convention" in prompt


def test_embedded_template_requires_rust_variables() -> None:
    template = "{{ base_path }} -- {{ memory_summary }}"
    assert parse_embedded_template(template, "test") == template
