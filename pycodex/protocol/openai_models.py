"""Shared OpenAI/Codex model metadata types.

Ported from ``codex/codex-rs/protocol/src/openai_models.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .config_types import (
    SERVICE_TIER_DEFAULT_REQUEST_VALUE,
    Personality,
    ReasoningEffort,
    ReasoningSummary,
    ServiceTier,
    Verbosity,
)


JsonValue = Any
PERSONALITY_PLACEHOLDER = "{{ personality }}"
SPEED_TIER_FAST = "fast"
I32_MIN = -(2**31)
I32_MAX = 2**31 - 1
I64_MIN = -(2**63)
I64_MAX = 2**63 - 1


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, raw: str):
        try:
            return cls(raw)
        except ValueError as exc:
            raise ValueError(f"invalid {cls.__name__}: {raw}") from exc


class InputModality(_StringEnum):
    TEXT = "text"
    IMAGE = "image"


def default_input_modalities() -> tuple[InputModality, InputModality]:
    return (InputModality.TEXT, InputModality.IMAGE)


@dataclass(frozen=True)
class ReasoningEffortPreset:
    effort: ReasoningEffort
    description: str

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReasoningEffortPreset":
        data = _mapping(value, "reasoning effort preset")
        return cls(ReasoningEffort(_required_str(data, "effort")), _required_str(data, "description"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"effort": self.effort.value, "description": self.description}


@dataclass(frozen=True)
class ModelUpgrade:
    id: str
    migration_config_key: str
    reasoning_effort_mapping: dict[ReasoningEffort, ReasoningEffort] | None = None
    model_link: str | None = None
    upgrade_copy: str | None = None
    migration_markdown: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ModelUpgrade":
        data = _mapping(value, "model upgrade")
        raw_mapping = data.get("reasoning_effort_mapping")
        effort_mapping = None
        if isinstance(raw_mapping, dict):
            effort_mapping = {
                ReasoningEffort(str(key)): ReasoningEffort(str(mapped))
                for key, mapped in raw_mapping.items()
            }
        return cls(
            id=_required_str(data, "id"),
            reasoning_effort_mapping=effort_mapping,
            migration_config_key=_required_str(data, "migration_config_key"),
            model_link=_optional_str(data, "model_link"),
            upgrade_copy=_optional_str(data, "upgrade_copy"),
            migration_markdown=_optional_str(data, "migration_markdown"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"id": self.id, "migration_config_key": self.migration_config_key}
        if self.reasoning_effort_mapping is not None:
            data["reasoning_effort_mapping"] = {
                key.value: value.value for key, value in self.reasoning_effort_mapping.items()
            }
        if self.model_link is not None:
            data["model_link"] = self.model_link
        if self.upgrade_copy is not None:
            data["upgrade_copy"] = self.upgrade_copy
        if self.migration_markdown is not None:
            data["migration_markdown"] = self.migration_markdown
        return data


@dataclass(frozen=True)
class ModelAvailabilityNux:
    message: str

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ModelAvailabilityNux":
        data = _mapping(value, "model availability nux")
        return cls(_required_str(data, "message"))

    def to_mapping(self) -> dict[str, str]:
        return {"message": self.message}


@dataclass(frozen=True)
class ModelServiceTier:
    id: str
    name: str
    description: str

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ModelServiceTier":
        data = _mapping(value, "model service tier")
        return cls(
            id=_required_str(data, "id"),
            name=_required_str(data, "name"),
            description=_required_str(data, "description"),
        )

    def to_mapping(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "description": self.description}


@dataclass
class ModelPreset:
    id: str
    model: str
    display_name: str
    description: str
    default_reasoning_effort: ReasoningEffort
    supported_reasoning_efforts: tuple[ReasoningEffortPreset, ...]
    is_default: bool
    upgrade: ModelUpgrade | None
    show_in_picker: bool
    availability_nux: ModelAvailabilityNux | None
    supported_in_api: bool
    supports_personality: bool = False
    additional_speed_tiers: tuple[str, ...] = ()
    service_tiers: tuple[ModelServiceTier, ...] = ()
    default_service_tier: str | None = None
    input_modalities: tuple[InputModality, ...] = default_input_modalities()

    def __post_init__(self) -> None:
        self.supported_reasoning_efforts = tuple(self.supported_reasoning_efforts)
        self.additional_speed_tiers = tuple(self.additional_speed_tiers)
        self.service_tiers = tuple(self.service_tiers)
        self.input_modalities = tuple(self.input_modalities)

    @classmethod
    def from_model_info(cls, info: "ModelInfo") -> "ModelPreset":
        supports_personality = info.supports_personality()
        upgrade = None
        if info.upgrade is not None:
            upgrade = ModelUpgrade(
                id=info.upgrade.model,
                reasoning_effort_mapping=reasoning_effort_mapping_from_presets(info.supported_reasoning_levels),
                migration_config_key=info.slug,
                migration_markdown=info.upgrade.migration_markdown,
            )
        return cls(
            id=info.slug,
            model=info.slug,
            display_name=info.display_name,
            description=info.description or "",
            default_reasoning_effort=info.default_reasoning_level or ReasoningEffort.NONE,
            supported_reasoning_efforts=info.supported_reasoning_levels,
            supports_personality=supports_personality,
            additional_speed_tiers=info.additional_speed_tiers,
            service_tiers=info.service_tiers,
            default_service_tier=info.default_service_tier,
            is_default=False,
            upgrade=upgrade,
            show_in_picker=info.visibility is ModelVisibility.LIST,
            availability_nux=info.availability_nux,
            supported_in_api=info.supported_in_api,
            input_modalities=info.input_modalities,
        )

    def supports_fast_mode(self) -> bool:
        return any(tier.id == ServiceTier.FAST.request_value() for tier in self.service_tiers) or any(
            tier == SPEED_TIER_FAST for tier in self.additional_speed_tiers
        )

    @staticmethod
    def filter_by_auth(models: list["ModelPreset"] | tuple["ModelPreset", ...], chatgpt_mode: bool) -> list["ModelPreset"]:
        return [model for model in models if chatgpt_mode or model.supported_in_api]

    @staticmethod
    def mark_default_by_picker_visibility(models: list["ModelPreset"]) -> None:
        for preset in models:
            preset.is_default = False
        default = next((preset for preset in models if preset.show_in_picker), None)
        if default is None and models:
            default = models[0]
        if default is not None:
            default.is_default = True


class ModelVisibility(_StringEnum):
    LIST = "list"
    HIDE = "hide"
    NONE = "none"


class ConfigShellToolType(_StringEnum):
    DEFAULT = "default"
    LOCAL = "local"
    UNIFIED_EXEC = "unified_exec"
    DISABLED = "disabled"
    SHELL_COMMAND = "shell_command"


class ApplyPatchToolType(_StringEnum):
    FREEFORM = "freeform"


class WebSearchToolType(_StringEnum):
    TEXT = "text"
    TEXT_AND_IMAGE = "text_and_image"

    @classmethod
    def default(cls) -> "WebSearchToolType":
        return cls.TEXT


class TruncationMode(_StringEnum):
    BYTES = "bytes"
    TOKENS = "tokens"


@dataclass(frozen=True)
class TruncationPolicyConfig:
    mode: TruncationMode
    limit: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", TruncationMode(self.mode))
        object.__setattr__(self, "limit", _ensure_i64(self.limit, "limit"))

    @classmethod
    def bytes(cls, limit: int) -> "TruncationPolicyConfig":
        return cls(TruncationMode.BYTES, limit)

    @classmethod
    def tokens(cls, limit: int) -> "TruncationPolicyConfig":
        return cls(TruncationMode.TOKENS, limit)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TruncationPolicyConfig":
        data = _mapping(value, "truncation policy config")
        return cls(mode=TruncationMode(_required_str(data, "mode")), limit=_required_int(data, "limit"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"mode": self.mode.value, "limit": self.limit}


@dataclass(frozen=True)
class ClientVersion:
    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "major", _ensure_i32(self.major, "major"))
        object.__setattr__(self, "minor", _ensure_i32(self.minor, "minor"))
        object.__setattr__(self, "patch", _ensure_i32(self.patch, "patch"))

    @classmethod
    def from_value(cls, value: JsonValue) -> "ClientVersion":
        if not isinstance(value, list | tuple) or len(value) != 3:
            raise TypeError("client version must be a three-element array")
        return cls(*(_ensure_i32(item, "client version component") for item in value))

    def to_json(self) -> list[int]:
        return [self.major, self.minor, self.patch]


@dataclass(frozen=True)
class ModelInfo:
    slug: str
    display_name: str
    description: str | None
    supported_reasoning_levels: tuple[ReasoningEffortPreset, ...]
    shell_type: ConfigShellToolType
    visibility: ModelVisibility
    supported_in_api: bool
    priority: int
    upgrade: "ModelInfoUpgrade | None"
    base_instructions: str
    model_messages: "ModelMessages | None"
    supports_reasoning_summaries: bool
    truncation_policy: TruncationPolicyConfig
    supports_parallel_tool_calls: bool
    default_reasoning_level: ReasoningEffort | None = None
    additional_speed_tiers: tuple[str, ...] = ()
    service_tiers: tuple[ModelServiceTier, ...] = ()
    default_service_tier: str | None = None
    availability_nux: ModelAvailabilityNux | None = None
    default_reasoning_summary: ReasoningSummary = ReasoningSummary.AUTO
    support_verbosity: bool = False
    default_verbosity: Verbosity | None = None
    apply_patch_tool_type: ApplyPatchToolType | None = None
    web_search_tool_type: WebSearchToolType = WebSearchToolType.TEXT
    supports_image_detail_original: bool = False
    context_window: int | None = None
    max_context_window: int | None = None
    auto_compact_token_limit_value: int | None = None
    effective_context_window_percent: int = 95
    experimental_supported_tools: tuple[str, ...] = ()
    input_modalities: tuple[InputModality, ...] = default_input_modalities()
    used_fallback_model_metadata: bool = False
    supports_search_tool: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "supported_reasoning_levels", tuple(self.supported_reasoning_levels))
        object.__setattr__(self, "additional_speed_tiers", tuple(self.additional_speed_tiers))
        object.__setattr__(self, "service_tiers", tuple(self.service_tiers))
        object.__setattr__(self, "experimental_supported_tools", tuple(self.experimental_supported_tools))
        object.__setattr__(self, "input_modalities", tuple(self.input_modalities))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ModelInfo":
        data = _mapping(value, "model info")
        return cls(
            slug=_required_str(data, "slug"),
            display_name=_required_str(data, "display_name"),
            description=_optional_str(data, "description"),
            default_reasoning_level=_optional_enum(data, "default_reasoning_level", ReasoningEffort),
            supported_reasoning_levels=tuple(
                ReasoningEffortPreset.from_mapping(item)
                for item in _required_list(data, "supported_reasoning_levels")
            ),
            shell_type=ConfigShellToolType(_required_str(data, "shell_type")),
            visibility=ModelVisibility(_required_str(data, "visibility")),
            supported_in_api=_required_bool(data, "supported_in_api"),
            priority=_required_i32(data, "priority"),
            additional_speed_tiers=tuple(_optional_str_list(data, "additional_speed_tiers")),
            service_tiers=tuple(ModelServiceTier.from_mapping(item) for item in _optional_list(data, "service_tiers")),
            default_service_tier=_optional_str(data, "default_service_tier"),
            availability_nux=(
                ModelAvailabilityNux.from_mapping(data["availability_nux"])
                if data.get("availability_nux") is not None
                else None
            ),
            upgrade=ModelInfoUpgrade.from_mapping(data["upgrade"]) if data.get("upgrade") is not None else None,
            base_instructions=_required_str(data, "base_instructions"),
            model_messages=(
                ModelMessages.from_mapping(data["model_messages"]) if data.get("model_messages") is not None else None
            ),
            supports_reasoning_summaries=_required_bool(data, "supports_reasoning_summaries"),
            default_reasoning_summary=ReasoningSummary(data.get("default_reasoning_summary", ReasoningSummary.AUTO.value)),
            support_verbosity=_required_bool(data, "support_verbosity"),
            default_verbosity=_optional_enum(data, "default_verbosity", Verbosity),
            apply_patch_tool_type=_optional_enum(data, "apply_patch_tool_type", ApplyPatchToolType),
            web_search_tool_type=WebSearchToolType(data.get("web_search_tool_type", WebSearchToolType.TEXT.value)),
            truncation_policy=TruncationPolicyConfig.from_mapping(data["truncation_policy"]),
            supports_parallel_tool_calls=_required_bool(data, "supports_parallel_tool_calls"),
            supports_image_detail_original=_optional_bool_default(data, "supports_image_detail_original", False),
            context_window=_optional_int(data, "context_window"),
            max_context_window=_optional_int(data, "max_context_window"),
            auto_compact_token_limit_value=_optional_int(data, "auto_compact_token_limit"),
            effective_context_window_percent=_optional_int_default(data, "effective_context_window_percent", 95),
            experimental_supported_tools=tuple(_required_str_list(data, "experimental_supported_tools")),
            input_modalities=_parse_input_modalities(data.get("input_modalities")),
            supports_search_tool=_optional_bool_default(data, "supports_search_tool", False),
        )

    def resolved_context_window(self) -> int | None:
        return self.context_window if self.context_window is not None else self.max_context_window

    def auto_compact_token_limit(self) -> int | None:
        context_limit = None
        resolved = self.resolved_context_window()
        if resolved is not None:
            context_limit = (resolved * 9) // 10
        config_limit = self.auto_compact_token_limit_value
        if context_limit is not None:
            return min(config_limit, context_limit) if config_limit is not None else context_limit
        return config_limit

    def supports_personality(self) -> bool:
        return self.model_messages is not None and self.model_messages.supports_personality()

    def get_model_instructions(self, personality: Personality | None = None) -> str:
        if self.model_messages is not None and self.model_messages.instructions_template is not None:
            personality_message = self.model_messages.get_personality_message(personality) or ""
            return self.model_messages.instructions_template.replace(PERSONALITY_PLACEHOLDER, personality_message)
        return self.base_instructions

    def supports_service_tier(self, service_tier: str) -> bool:
        return any(tier.id == service_tier for tier in self.service_tiers)

    def service_tier_for_request(self, service_tier: str | None) -> str | None:
        if service_tier is None or service_tier == SERVICE_TIER_DEFAULT_REQUEST_VALUE:
            return None
        return service_tier if self.supports_service_tier(service_tier) else None

    def to_preset(self) -> ModelPreset:
        return ModelPreset.from_model_info(self)


@dataclass(frozen=True)
class ModelMessages:
    instructions_template: str | None
    instructions_variables: "ModelInstructionsVariables | None"

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ModelMessages":
        data = _mapping(value, "model messages")
        return cls(
            instructions_template=_optional_str(data, "instructions_template"),
            instructions_variables=(
                ModelInstructionsVariables.from_mapping(data["instructions_variables"])
                if data.get("instructions_variables") is not None
                else None
            ),
        )

    def has_personality_placeholder(self) -> bool:
        return self.instructions_template is not None and PERSONALITY_PLACEHOLDER in self.instructions_template

    def supports_personality(self) -> bool:
        return self.has_personality_placeholder() and self.instructions_variables is not None and self.instructions_variables.is_complete()

    def get_personality_message(self, personality: Personality | None = None) -> str | None:
        if self.instructions_variables is None:
            return None
        return self.instructions_variables.get_personality_message(personality)


@dataclass(frozen=True)
class ModelInstructionsVariables:
    personality_default: str | None = None
    personality_friendly: str | None = None
    personality_pragmatic: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ModelInstructionsVariables":
        data = _mapping(value, "model instructions variables")
        return cls(
            personality_default=_optional_str(data, "personality_default"),
            personality_friendly=_optional_str(data, "personality_friendly"),
            personality_pragmatic=_optional_str(data, "personality_pragmatic"),
        )

    def is_complete(self) -> bool:
        return (
            self.personality_default is not None
            and self.personality_friendly is not None
            and self.personality_pragmatic is not None
        )

    def get_personality_message(self, personality: Personality | None = None) -> str | None:
        if personality is Personality.NONE:
            return ""
        if personality is Personality.FRIENDLY:
            return self.personality_friendly
        if personality is Personality.PRAGMATIC:
            return self.personality_pragmatic
        return self.personality_default


@dataclass(frozen=True)
class ModelInfoUpgrade:
    model: str
    migration_markdown: str

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ModelInfoUpgrade":
        data = _mapping(value, "model info upgrade")
        return cls(model=_required_str(data, "model"), migration_markdown=_required_str(data, "migration_markdown"))

    @classmethod
    def from_model_upgrade(cls, upgrade: ModelUpgrade) -> "ModelInfoUpgrade":
        return cls(model=upgrade.id, migration_markdown=upgrade.migration_markdown or "")


@dataclass(frozen=True)
class ModelsResponse:
    models: tuple[ModelInfo, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "models", tuple(self.models))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ModelsResponse":
        data = _mapping(value, "models response")
        return cls(tuple(ModelInfo.from_mapping(item) for item in data.get("models", [])))


def reasoning_effort_mapping_from_presets(
    presets: tuple[ReasoningEffortPreset, ...] | list[ReasoningEffortPreset],
) -> dict[ReasoningEffort, ReasoningEffort] | None:
    if not presets:
        return None
    supported = [preset.effort for preset in presets]
    return {effort: nearest_effort(effort, supported) for effort in ReasoningEffort}


def effort_rank(effort: ReasoningEffort) -> int:
    return {
        ReasoningEffort.NONE: 0,
        ReasoningEffort.MINIMAL: 1,
        ReasoningEffort.LOW: 2,
        ReasoningEffort.MEDIUM: 3,
        ReasoningEffort.HIGH: 4,
        ReasoningEffort.XHIGH: 5,
    }[effort]


def nearest_effort(target: ReasoningEffort, supported: list[ReasoningEffort] | tuple[ReasoningEffort, ...]) -> ReasoningEffort:
    if not supported:
        return target
    target_rank = effort_rank(target)
    return min(supported, key=lambda candidate: abs(effort_rank(candidate) - target_rank))


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str(value: dict[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _required_int(value: dict[str, JsonValue], key: str) -> int:
    if key not in value:
        raise KeyError(key)
    return _ensure_i64(value[key], key)


def _optional_int(value: dict[str, JsonValue], key: str) -> int | None:
    raw = value.get(key)
    if raw is None:
        return None
    return _ensure_i64(raw, key)


def _optional_int_default(value: dict[str, JsonValue], key: str, default: int) -> int:
    raw = value.get(key, default)
    return _ensure_i64(raw, key)


def _ensure_int(value: JsonValue, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    return value


def _ensure_i32(value: JsonValue, label: str) -> int:
    value = _ensure_int(value, label)
    if not I32_MIN <= value <= I32_MAX:
        raise ValueError(f"{label} must fit in i32")
    return value


def _ensure_i64(value: JsonValue, label: str) -> int:
    value = _ensure_int(value, label)
    if not I64_MIN <= value <= I64_MAX:
        raise ValueError(f"{label} must fit in i64")
    return value


def _required_i32(value: dict[str, JsonValue], key: str) -> int:
    if key not in value:
        raise KeyError(key)
    return _ensure_i32(value[key], key)


def _required_bool(value: dict[str, JsonValue], key: str) -> bool:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, bool):
        raise TypeError(f"{key} must be a bool")
    return raw


def _optional_bool_default(value: dict[str, JsonValue], key: str, default: bool) -> bool:
    raw = value.get(key, default)
    if not isinstance(raw, bool):
        raise TypeError(f"{key} must be a bool")
    return raw


def _required_list(value: dict[str, JsonValue], key: str) -> list[JsonValue]:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, list):
        raise TypeError(f"{key} must be a list")
    return raw


def _optional_list(value: dict[str, JsonValue], key: str) -> list[JsonValue]:
    raw = value.get(key, [])
    if not isinstance(raw, list):
        raise TypeError(f"{key} must be a list")
    return raw


def _required_str_list(value: dict[str, JsonValue], key: str) -> list[str]:
    items = _required_list(value, key)
    for item in items:
        if not isinstance(item, str):
            raise TypeError(f"{key} entries must be strings")
    return items


def _optional_str_list(value: dict[str, JsonValue], key: str) -> list[str]:
    items = _optional_list(value, key)
    for item in items:
        if not isinstance(item, str):
            raise TypeError(f"{key} entries must be strings")
    return items


def _optional_enum(value: dict[str, JsonValue], key: str, enum_cls):
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return enum_cls(raw)


def _parse_input_modalities(value: JsonValue) -> tuple[InputModality, ...]:
    if value is None:
        return default_input_modalities()
    if not isinstance(value, list):
        raise TypeError("input_modalities must be a list")
    for item in value:
        if not isinstance(item, str):
            raise TypeError("input_modalities entries must be strings")
    return tuple(InputModality(item) for item in value)
