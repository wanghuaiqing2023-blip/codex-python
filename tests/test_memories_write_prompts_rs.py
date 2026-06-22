from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from pycodex.memories.write import (
    STAGE_ONE_CONTEXT_WINDOW_PERCENT,
    STAGE_ONE_DEFAULT_ROLLOUT_TOKEN_LIMIT,
    build_consolidation_prompt,
    build_stage_one_input_message,
)
from pycodex.models_manager.model_info import model_info_from_slug
from pycodex.protocol import TruncationPolicyConfig
from pycodex.utils.output_truncation import truncate_text


def test_build_stage_one_input_message_truncates_rollout_using_model_context_window() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/prompts.rs + src/prompts_tests.rs::build_stage_one_input_message_truncates_rollout_using_model_context_window
    # Contract: rollout text is truncated using resolved context window * model effective percent * stage-one percent.
    input_text = f"{'a' * 700_000}middle{'z' * 700_000}"
    model_info = replace(model_info_from_slug("gpt-5.3-codex"), context_window=123_000)
    expected_rollout_token_limit = (
        (123_000 * model_info.effective_context_window_percent) // 100
    ) * STAGE_ONE_CONTEXT_WINDOW_PERCENT // 100
    expected_truncated = truncate_text(input_text, TruncationPolicyConfig.tokens(expected_rollout_token_limit))

    message = build_stage_one_input_message(
        model_info,
        Path("/tmp/rollout.jsonl"),
        Path("/tmp"),
        input_text,
    )

    assert "tokens truncated" in expected_truncated
    assert expected_truncated.startswith("a")
    assert expected_truncated.endswith("z")
    assert expected_truncated in message


def test_build_stage_one_input_message_uses_default_limit_when_model_context_window_missing() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/prompts.rs + src/prompts_tests.rs::build_stage_one_input_message_uses_default_limit_when_model_context_window_missing
    # Contract: missing context_window and max_context_window falls back to stage_one::DEFAULT_ROLLOUT_TOKEN_LIMIT.
    input_text = f"{'a' * 700_000}middle{'z' * 700_000}"
    model_info = replace(
        model_info_from_slug("gpt-5.3-codex"),
        context_window=None,
        max_context_window=None,
    )
    expected_truncated = truncate_text(
        input_text,
        TruncationPolicyConfig.tokens(STAGE_ONE_DEFAULT_ROLLOUT_TOKEN_LIMIT),
    )

    message = build_stage_one_input_message(
        model_info,
        Path("/tmp/rollout.jsonl"),
        Path("/tmp"),
        input_text,
    )

    assert expected_truncated in message


def test_build_consolidation_prompt_points_to_workspace_diff_and_extension_tree(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/prompts.rs + src/prompts_tests.rs::build_consolidation_prompt_points_to_workspace_diff_and_extension_tree
    # Contract: consolidation prompt points to the generated workspace diff and includes extension guidance only when extensions dir exists.
    memory_root = tmp_path / "memories"
    memory_extensions_root = memory_root / "extensions"
    memory_extensions_root.mkdir(parents=True)

    prompt = build_consolidation_prompt(memory_root)

    assert "Memory workspace diff:" in prompt
    assert "phase2_workspace_diff.md" in prompt
    assert f"Memory extensions (under {memory_extensions_root.as_posix()}/):" in prompt
    assert "workspace diff shows deleted extension resource files" in prompt
