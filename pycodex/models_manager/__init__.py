"""Python port of ``codex-models-manager`` top-level public API.

Rust source:
- ``codex/codex-rs/models-manager/src/lib.rs``
- ``codex/codex-rs/models-manager/src/config.rs``
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ModelsManagerConfig:
    model_context_window: int | None = None
    model_auto_compact_token_limit: int | None = None
    tool_output_token_limit: int | None = None
    base_instructions: str | None = None
    personality_enabled: bool = False
    model_supports_reasoning_summaries: bool | None = None
    model_catalog: dict[str, Any] | None = None


def bundled_models_response() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    models_json = root / "codex" / "codex-rs" / "models-manager" / "models.json"
    return json.loads(models_json.read_text(encoding="utf-8"))


def client_version_to_whole(version: str | None = None) -> str:
    if version is None:
        return "0.0.0"
    parts = version.split("-", 1)[0].split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


from .test_support import (  # noqa: E402
    builtin_collaboration_mode_presets,
    construct_model_info_from_candidates,
    construct_model_info_offline_for_tests,
    get_model_offline_for_tests,
    model_info_from_slug,
    with_config_overrides,
)


__all__ = [
    "ModelsManagerConfig",
    "builtin_collaboration_mode_presets",
    "bundled_models_response",
    "client_version_to_whole",
    "construct_model_info_from_candidates",
    "construct_model_info_offline_for_tests",
    "get_model_offline_for_tests",
    "model_info_from_slug",
    "with_config_overrides",
]
