"""Python port of ``codex-models-manager`` top-level public API.

Rust source:
- ``codex/codex-rs/models-manager/src/lib.rs``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pycodex.app_server_protocol import AuthMode
from pycodex.protocol import ModelsResponse

from .cache import (
    CACHE_FILE,
    ModelsCache,
    ModelsCacheManager,
    models_response_from_fetch_result,
)
from .collaboration_mode_presets import (
    KNOWN_MODE_NAMES_TEMPLATE_KEY,
    builtin_collaboration_mode_presets,
    default_mode_instructions,
    format_mode_names,
)
from .config import ModelsManagerConfig
from .model_presets import (
    HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG,
    HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG,
    model_presets_from_models,
)

def bundled_models_response() -> dict[str, Any]:
    import json

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


from .model_info import (  # noqa: E402
    BASE_INSTRUCTIONS,
    DEFAULT_PERSONALITY_HEADER,
    LOCAL_FRIENDLY_TEMPLATE,
    LOCAL_PRAGMATIC_TEMPLATE,
    PERSONALITY_PLACEHOLDER,
    local_personality_messages_for_slug,
    model_info_from_slug,
    with_config_overrides,
)
from .manager import (  # noqa: E402
    DEFAULT_MODEL_CACHE_TTL,
    MODEL_CACHE_FILE,
    CachedModelsManager,
    ModelsEndpointClient,
    OpenAiModelsManager,
    RefreshStrategy,
    StaticModelsManager,
    build_available_models,
    construct_model_info_from_candidates,
    current_auth_uses_codex_backend,
    default_model_from_available,
    find_model_by_longest_prefix,
    find_model_by_namespaced_suffix,
    is_chatgpt_auth_mode,
    load_remote_models_from_file,
)
from .test_support import (  # noqa: E402
    construct_model_info_offline_for_tests,
    get_model_offline_for_tests,
)


__all__ = [
    "AuthMode",
    "BASE_INSTRUCTIONS",
    "CACHE_FILE",
    "CachedModelsManager",
    "DEFAULT_MODEL_CACHE_TTL",
    "DEFAULT_PERSONALITY_HEADER",
    "HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG",
    "HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG",
    "KNOWN_MODE_NAMES_TEMPLATE_KEY",
    "LOCAL_FRIENDLY_TEMPLATE",
    "LOCAL_PRAGMATIC_TEMPLATE",
    "ModelsCache",
    "ModelsCacheManager",
    "ModelsManagerConfig",
    "MODEL_CACHE_FILE",
    "ModelsEndpointClient",
    "PERSONALITY_PLACEHOLDER",
    "OpenAiModelsManager",
    "RefreshStrategy",
    "StaticModelsManager",
    "builtin_collaboration_mode_presets",
    "build_available_models",
    "bundled_models_response",
    "client_version_to_whole",
    "construct_model_info_from_candidates",
    "construct_model_info_offline_for_tests",
    "current_auth_uses_codex_backend",
    "default_mode_instructions",
    "default_model_from_available",
    "find_model_by_longest_prefix",
    "find_model_by_namespaced_suffix",
    "format_mode_names",
    "get_model_offline_for_tests",
    "is_chatgpt_auth_mode",
    "load_remote_models_from_file",
    "local_personality_messages_for_slug",
    "model_info_from_slug",
    "model_presets_from_models",
    "with_config_overrides",
]
