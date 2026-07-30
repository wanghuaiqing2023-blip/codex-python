"""Real CLI integration through the Rust-aligned core test-support package."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.core_test_support.test_codex import test_codex


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_core_test_support_builder_runs_real_pycodex_cli(tmp_path: Path) -> None:
    fixture = await (
        test_codex()
        .with_home(tmp_path / "codex-home")
        .with_model("gpt-5.6-sol")
        .build()
    )
    await fixture.write_file("input.txt", "core test support")

    completed = fixture.run("--version", timeout=30)

    assert completed.returncode == 0, completed.stderr
    assert "codex" in completed.stdout.lower()
    assert await fixture.read_file_text("input.txt") == "core test support"
