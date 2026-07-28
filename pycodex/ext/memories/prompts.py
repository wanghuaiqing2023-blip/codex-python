"""Developer-prompt contribution from Rust ``memories/src/prompts.rs``."""

from __future__ import annotations

from pathlib import Path

from pycodex.protocol import TruncationPolicyConfig
from pycodex.utils.output_truncation import truncate_text

MEMORY_TOOL_DEVELOPER_INSTRUCTIONS_SUMMARY_TOKEN_LIMIT = 2_500
_TEMPLATE_PATH = Path(__file__).parent / "templates" / "memories" / "read_path.md"


def parse_embedded_template(source: str, template_name: str) -> str:
    if not isinstance(source, str):
        raise TypeError(f"embedded template {template_name} must be text")
    for variable in ("base_path", "memory_summary"):
        if f"{{{{ {variable} }}}}" not in source:
            raise ValueError(f"embedded template {template_name} is missing {variable}")
    return source


async def build_memory_tool_developer_instructions(
    codex_home: str | Path,
) -> str | None:
    base_path = Path(codex_home) / "memories"
    summary_path = base_path / "memory_summary.md"
    try:
        memory_summary = summary_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    memory_summary = truncate_text(
        memory_summary,
        TruncationPolicyConfig.tokens(
            MEMORY_TOOL_DEVELOPER_INSTRUCTIONS_SUMMARY_TOKEN_LIMIT
        ),
    )
    if not memory_summary:
        return None
    template = parse_embedded_template(
        _TEMPLATE_PATH.read_text(encoding="utf-8"),
        "memories/read_path.md",
    )
    return template.replace("{{ base_path }}", str(base_path)).replace(
        "{{ memory_summary }}",
        memory_summary,
    )


__all__ = [
    "build_memory_tool_developer_instructions",
    "parse_embedded_template",
]
