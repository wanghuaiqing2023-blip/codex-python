"""Configuration shape for ``codex-models-manager::config``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pycodex.protocol import ModelsResponse


@dataclass
class ModelsManagerConfig:
    model_context_window: int | None = None
    model_auto_compact_token_limit: int | None = None
    tool_output_token_limit: int | None = None
    base_instructions: str | None = None
    personality_enabled: bool = False
    model_supports_reasoning_summaries: bool | None = None
    model_catalog: ModelsResponse | None = None

    def __post_init__(self) -> None:
        self.model_context_window = _optional_int(self.model_context_window, "model_context_window")
        self.model_auto_compact_token_limit = _optional_int(
            self.model_auto_compact_token_limit,
            "model_auto_compact_token_limit",
        )
        self.tool_output_token_limit = _optional_int(self.tool_output_token_limit, "tool_output_token_limit")
        if self.base_instructions is not None and not isinstance(self.base_instructions, str):
            raise TypeError("base_instructions must be a string or None")
        if not isinstance(self.personality_enabled, bool):
            raise TypeError("personality_enabled must be a bool")
        if self.model_supports_reasoning_summaries is not None and not isinstance(
            self.model_supports_reasoning_summaries,
            bool,
        ):
            raise TypeError("model_supports_reasoning_summaries must be a bool or None")
        self.model_catalog = _optional_models_response(self.model_catalog)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ModelsManagerConfig":
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise TypeError("ModelsManagerConfig must be a mapping or None")
        _reject_unknown_fields(
            value,
            {
                "model_context_window",
                "model_auto_compact_token_limit",
                "tool_output_token_limit",
                "base_instructions",
                "personality_enabled",
                "model_supports_reasoning_summaries",
                "model_catalog",
            },
        )
        return cls(
            model_context_window=value.get("model_context_window"),
            model_auto_compact_token_limit=value.get("model_auto_compact_token_limit"),
            tool_output_token_limit=value.get("tool_output_token_limit"),
            base_instructions=value.get("base_instructions"),
            personality_enabled=bool(value.get("personality_enabled", False)),
            model_supports_reasoning_summaries=value.get("model_supports_reasoning_summaries"),
            model_catalog=value.get("model_catalog"),
        )

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.model_context_window is not None:
            result["model_context_window"] = self.model_context_window
        if self.model_auto_compact_token_limit is not None:
            result["model_auto_compact_token_limit"] = self.model_auto_compact_token_limit
        if self.tool_output_token_limit is not None:
            result["tool_output_token_limit"] = self.tool_output_token_limit
        if self.base_instructions is not None:
            result["base_instructions"] = self.base_instructions
        if self.personality_enabled:
            result["personality_enabled"] = self.personality_enabled
        if self.model_supports_reasoning_summaries is not None:
            result["model_supports_reasoning_summaries"] = self.model_supports_reasoning_summaries
        if self.model_catalog is not None:
            result["model_catalog"] = self.model_catalog
        return result


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer or None")
    return value


def _optional_models_response(value: Any) -> ModelsResponse | None:
    if value is None:
        return None
    if isinstance(value, ModelsResponse):
        return value
    if isinstance(value, Mapping):
        return ModelsResponse.from_mapping(value)
    raise TypeError("model_catalog must be ModelsResponse, mapping, or None")


def _reject_unknown_fields(value: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = [str(key) for key in value if key not in allowed]
    if unknown:
        raise ValueError(f"unknown fields for ModelsManagerConfig: {', '.join(unknown)}")


__all__ = ["ModelsManagerConfig"]
