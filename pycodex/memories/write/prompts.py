"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from pathlib import Path
from pycodex.protocol import AgentStatus, BaseInstructions, ContentItem, ModelInfo, Op, RateLimitSnapshot, RateLimitWindow, ReasoningEffort, ReasoningSummary, ResponseItem, TokenUsage, TruncationPolicyConfig, UserInput
from pycodex.utils.output_truncation import truncate_text

_TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "codex"
    / "codex-rs"
    / "memories"
    / "write"
    / "templates"
    / "memories"
)
_STAGE_ONE_INPUT_TEMPLATE = (_TEMPLATE_ROOT / "stage_one_input.md").read_text(encoding="utf-8")
_CONSOLIDATION_PROMPT_TEMPLATE = (_TEMPLATE_ROOT / "consolidation.md").read_text(encoding="utf-8")

def build_consolidation_prompt(memory_root_path: str | Path) -> str:
    memory_root_path = Path(memory_root_path)
    extensions_root = memory_extensions_root(memory_root_path)
    extensions_exist = extensions_root.is_dir()
    extension_structure = _render_template(_EXTENSIONS_FOLDER_STRUCTURE_TEMPLATE, memory_extensions_root=_display_path(extensions_root)) if extensions_exist else ''
    extension_inputs = _render_template(_EXTENSIONS_PRIMARY_INPUTS_TEMPLATE, memory_extensions_root=_display_path(extensions_root)) if extensions_exist else ''
    return _render_template(_CONSOLIDATION_PROMPT_TEMPLATE, memory_root=_display_path(memory_root_path), memory_extensions_folder_structure=extension_structure, memory_extensions_primary_inputs=extension_inputs, phase2_workspace_diff_file=PHASE2_WORKSPACE_DIFF_FILENAME)


def build_stage_one_input_message(model_info: ModelInfo, rollout_path: str | Path, rollout_cwd: str | Path, rollout_contents: str) -> str:
    resolved = model_info.resolved_context_window()
    if resolved is not None and resolved > 0:
        effective = resolved * model_info.effective_context_window_percent // 100
        rollout_token_limit = max(effective * STAGE_ONE_CONTEXT_WINDOW_PERCENT // 100, 1)
    else:
        rollout_token_limit = STAGE_ONE_DEFAULT_ROLLOUT_TOKEN_LIMIT
    truncated = truncate_text(str(rollout_contents), TruncationPolicyConfig.tokens(rollout_token_limit))
    return _render_template(_STAGE_ONE_INPUT_TEMPLATE, rollout_path=_display_path(Path(rollout_path)), rollout_cwd=_display_path(Path(rollout_cwd)), rollout_contents=truncated)


def _display_path(value: Path) -> str:
    return Path(value).as_posix()


def _render_template(template: str, **values: str) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace('{{ ' + key + ' }}', value)
    return rendered


def _clamp(value: int, low: int, high: int) -> int:
    return min(max(value, low), high)


from pycodex.memories.write import memory_extensions_root
from pycodex.memories.write.prompt_blocks import EXTENSIONS_FOLDER_STRUCTURE as _EXTENSIONS_FOLDER_STRUCTURE_TEMPLATE
from pycodex.memories.write.prompt_blocks import EXTENSIONS_PRIMARY_INPUTS as _EXTENSIONS_PRIMARY_INPUTS_TEMPLATE
from pycodex.memories.write.stage_one import CONTEXT_WINDOW_PERCENT as STAGE_ONE_CONTEXT_WINDOW_PERCENT
from pycodex.memories.write.stage_one import DEFAULT_ROLLOUT_TOKEN_LIMIT as STAGE_ONE_DEFAULT_ROLLOUT_TOKEN_LIMIT
from pycodex.memories.write.workspace_diff import FILENAME as PHASE2_WORKSPACE_DIFF_FILENAME
