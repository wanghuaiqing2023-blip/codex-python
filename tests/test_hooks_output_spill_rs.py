"""Rust-derived tests for ``codex-hooks/src/output_spill.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/output_spill.rs``

Rust tests mirrored:
- ``small_hook_output_remains_inline``
- ``large_hook_output_spills_to_file``
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pycodex.hooks import HOOK_OUTPUTS_DIR
from pycodex.hooks import HookOutputSpiller
from pycodex.protocol import HookPromptFragment
from pycodex.protocol import ThreadId


def _spill_path_from_output(output: str) -> Path:
    for line in output.splitlines():
        if line.startswith("Full hook output saved to: "):
            return Path(line.removeprefix("Full hook output saved to: "))
    raise AssertionError("spill path missing")


def test_small_hook_output_remains_inline(tmp_path: Path) -> None:
    # Rust crate/module/test: codex-hooks/src/output_spill.rs via
    # src/output_spill_tests.rs::small_hook_output_remains_inline.
    # Contract: small text stays model-visible and no hook_outputs directory
    # is created.
    output_dir = tmp_path / HOOK_OUTPUTS_DIR
    spiller = HookOutputSpiller(output_dir=output_dir)

    output = asyncio.run(spiller.maybe_spill_text(ThreadId.new(), "short"))

    assert output == "short"
    assert not output_dir.exists()


def test_large_hook_output_spills_to_file(tmp_path: Path) -> None:
    # Rust crate/module/test: codex-hooks/src/output_spill.rs via
    # src/output_spill_tests.rs::large_hook_output_spills_to_file.
    # Contract: oversized hook output is written in full under
    # hook_outputs/<thread_id>/ and the model-visible output contains a
    # truncation preview plus a recovery path.
    text = "hook output " * 1_000
    thread_id = ThreadId.new()
    output_dir = tmp_path / HOOK_OUTPUTS_DIR
    spiller = HookOutputSpiller(output_dir=output_dir)

    output = asyncio.run(spiller.maybe_spill_text(thread_id, text))

    assert "tokens truncated" in output
    path = _spill_path_from_output(output)
    assert path.read_text(encoding="utf-8") == text
    assert path.parent == output_dir / str(thread_id)
    assert path.name.endswith(".txt")


def test_maybe_spill_texts_preserves_order_and_spills_individually(tmp_path: Path) -> None:
    # Rust crate/module/source contract: codex-hooks/src/output_spill.rs
    # maybe_spill_texts processes each text through maybe_spill_text in input
    # order.
    long_text = "hook output " * 1_000
    spiller = HookOutputSpiller(output_dir=tmp_path / HOOK_OUTPUTS_DIR)

    outputs = asyncio.run(
        spiller.maybe_spill_texts(ThreadId.new(), ["short", long_text])
    )

    assert outputs[0] == "short"
    assert "Full hook output saved to: " in outputs[1]
    assert _spill_path_from_output(outputs[1]).read_text(encoding="utf-8") == long_text


def test_maybe_spill_prompt_fragments_preserves_hook_run_id(tmp_path: Path) -> None:
    # Rust crate/module/source contract: codex-hooks/src/output_spill.rs
    # maybe_spill_prompt_fragments rewrites only fragment.text and preserves
    # hook_run_id.
    long_text = "hook output " * 1_000
    spiller = HookOutputSpiller(output_dir=tmp_path / HOOK_OUTPUTS_DIR)
    fragment = HookPromptFragment(text=long_text, hook_run_id="hook-run-1")

    outputs = asyncio.run(
        spiller.maybe_spill_prompt_fragments(ThreadId.new(), [fragment])
    )

    assert len(outputs) == 1
    assert outputs[0].hook_run_id == "hook-run-1"
    assert "Full hook output saved to: " in outputs[0].text
