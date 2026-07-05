"""Model protocol types ported from ``protocol/v2/model.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pycodex.protocol import InputModality, ReasoningEffort

JsonValue = Any


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc


class ModelRerouteReason(_StringEnum):
    HIGH_RISK_CYBER_ACTIVITY = "highRiskCyberActivity"


class ModelVerification(_StringEnum):
    TRUSTED_ACCESS_FOR_CYBER = "trustedAccessForCyber"


def default_input_modalities() -> tuple[InputModality, InputModality]:
    return (InputModality.TEXT, InputModality.IMAGE)


@dataclass(frozen=True)
class ModelProviderCapabilitiesReadParams:
    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, JsonValue] | None = None,
    ) -> "ModelProviderCapabilitiesReadParams":
        if value is not None and not isinstance(value, Mapping):
            raise TypeError("ModelProviderCapabilitiesReadParams mapping must be a mapping")
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class ModelProviderCapabilitiesReadResponse:
    namespace_tools: bool
    image_generation: bool
    web_search: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "namespace_tools", _ensure_bool(self.namespace_tools, "namespace_tools"))
        object.__setattr__(self, "image_generation", _ensure_bool(self.image_generation, "image_generation"))
        object.__setattr__(self, "web_search", _ensure_bool(self.web_search, "web_search"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ModelProviderCapabilitiesReadResponse":
        _ensure_mapping(value, "ModelProviderCapabilitiesReadResponse")
        return cls(
            namespace_tools=_ensure_bool(_pick(value, "namespace_tools", "namespaceTools"), "namespace_tools"),
            image_generation=_ensure_bool(_pick(value, "image_generation", "imageGeneration"), "image_generation"),
            web_search=_ensure_bool(_pick(value, "web_search", "webSearch"), "web_search"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "namespace_tools": self.namespace_tools,
            "image_generation": self.image_generation,
            "web_search": self.web_search,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "namespaceTools": self.namespace_tools,
            "imageGeneration": self.image_generation,
            "webSearch": self.web_search,
        }


@dataclass(frozen=True)
class ModelListParams:
    cursor: str | None = None
    limit: int | None = None
    include_hidden: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cursor", _optional_str(self.cursor, "cursor"))
        object.__setattr__(self, "limit", _optional_u32(self.limit, "limit"))
        object.__setattr__(self, "include_hidden", _optional_bool(self.include_hidden, "include_hidden"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "ModelListParams":
        if value is None:
            return cls()
        _ensure_mapping(value, "ModelListParams")
        return cls(
            cursor=_optional_str(_pick(value, "cursor"), "cursor"),
            limit=_optional_u32(_pick(value, "limit"), "limit"),
            include_hidden=_optional_bool(_pick(value, "include_hidden", "includeHidden"), "include_hidden"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"cursor": self.cursor, "limit": self.limit, "include_hidden": self.include_hidden}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"cursor": self.cursor, "limit": self.limit, "includeHidden": self.include_hidden}


@dataclass(frozen=True)
class ModelAvailabilityNux:
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))

    @classmethod
    def from_core(cls, value: Any) -> "ModelAvailabilityNux":
        message = getattr(value, "message", None)
        return cls(message=_ensure_str(message, "message"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ModelAvailabilityNux":
        _ensure_mapping(value, "ModelAvailabilityNux")
        return cls(message=_ensure_str(value["message"], "message"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"message": self.message}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class ModelServiceTier:
    id: str
    name: str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "description", _ensure_str(self.description, "description"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ModelServiceTier":
        _ensure_mapping(value, "ModelServiceTier")
        return cls(
            id=_ensure_str(value["id"], "id"),
            name=_ensure_str(value["name"], "name"),
            description=_ensure_str(value["description"], "description"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"id": self.id, "name": self.name, "description": self.description}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class ModelUpgradeInfo:
    model: str
    upgrade_copy: str | None = None
    model_link: str | None = None
    migration_markdown: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "model", _ensure_str(self.model, "model"))
        object.__setattr__(self, "upgrade_copy", _optional_str(self.upgrade_copy, "upgrade_copy"))
        object.__setattr__(self, "model_link", _optional_str(self.model_link, "model_link"))
        object.__setattr__(self, "migration_markdown", _optional_str(self.migration_markdown, "migration_markdown"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ModelUpgradeInfo":
        _ensure_mapping(value, "ModelUpgradeInfo")
        return cls(
            model=_ensure_str(value["model"], "model"),
            upgrade_copy=_optional_str(_pick(value, "upgrade_copy", "upgradeCopy"), "upgrade_copy"),
            model_link=_optional_str(_pick(value, "model_link", "modelLink"), "model_link"),
            migration_markdown=_optional_str(
                _pick(value, "migration_markdown", "migrationMarkdown"),
                "migration_markdown",
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "model": self.model,
            "upgrade_copy": self.upgrade_copy,
            "model_link": self.model_link,
            "migration_markdown": self.migration_markdown,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "model": self.model,
            "upgradeCopy": self.upgrade_copy,
            "modelLink": self.model_link,
            "migrationMarkdown": self.migration_markdown,
        }


@dataclass(frozen=True)
class ReasoningEffortOption:
    reasoning_effort: ReasoningEffort | str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasoning_effort", _reasoning_effort(self.reasoning_effort, "reasoning_effort"))
        object.__setattr__(self, "description", _ensure_str(self.description, "description"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ReasoningEffortOption":
        _ensure_mapping(value, "ReasoningEffortOption")
        return cls(
            reasoning_effort=_reasoning_effort(
                _pick(value, "reasoning_effort", "reasoningEffort"),
                "reasoning_effort",
            ),
            description=_ensure_str(value["description"], "description"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"reasoning_effort": self.reasoning_effort.value, "description": self.description}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"reasoningEffort": self.reasoning_effort.value, "description": self.description}


@dataclass(frozen=True)
class Model:
    id: str
    model: str
    upgrade: str | None
    upgrade_info: ModelUpgradeInfo | Mapping[str, JsonValue] | None
    availability_nux: ModelAvailabilityNux | Mapping[str, JsonValue] | None
    display_name: str
    description: str
    hidden: bool
    supported_reasoning_efforts: tuple[ReasoningEffortOption, ...]
    default_reasoning_effort: ReasoningEffort | str
    input_modalities: tuple[InputModality, ...] = field(default_factory=default_input_modalities)
    supports_personality: bool = False
    additional_speed_tiers: tuple[str, ...] = ()
    service_tiers: tuple[ModelServiceTier, ...] = ()
    default_service_tier: str | None = None
    is_default: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "model", _ensure_str(self.model, "model"))
        object.__setattr__(self, "upgrade", _optional_str(self.upgrade, "upgrade"))
        object.__setattr__(self, "upgrade_info", _optional_dataclass(self.upgrade_info, ModelUpgradeInfo, "upgrade_info"))
        object.__setattr__(
            self,
            "availability_nux",
            _optional_dataclass(self.availability_nux, ModelAvailabilityNux, "availability_nux"),
        )
        object.__setattr__(self, "display_name", _ensure_str(self.display_name, "display_name"))
        object.__setattr__(self, "description", _ensure_str(self.description, "description"))
        object.__setattr__(self, "hidden", _ensure_bool(self.hidden, "hidden"))
        object.__setattr__(
            self,
            "supported_reasoning_efforts",
            _dataclass_tuple(self.supported_reasoning_efforts, ReasoningEffortOption, "supported_reasoning_efforts"),
        )
        object.__setattr__(
            self,
            "default_reasoning_effort",
            _reasoning_effort(self.default_reasoning_effort, "default_reasoning_effort"),
        )
        object.__setattr__(self, "input_modalities", _input_modalities(self.input_modalities))
        object.__setattr__(self, "supports_personality", _ensure_bool(self.supports_personality, "supports_personality"))
        object.__setattr__(
            self,
            "additional_speed_tiers",
            _string_tuple(self.additional_speed_tiers, "additional_speed_tiers"),
        )
        object.__setattr__(self, "service_tiers", _dataclass_tuple(self.service_tiers, ModelServiceTier, "service_tiers"))
        object.__setattr__(self, "default_service_tier", _optional_str(self.default_service_tier, "default_service_tier"))
        object.__setattr__(self, "is_default", _ensure_bool(self.is_default, "is_default"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "Model":
        _ensure_mapping(value, "Model")
        return cls(
            id=_ensure_str(value["id"], "id"),
            model=_ensure_str(value["model"], "model"),
            upgrade=_optional_str(_pick(value, "upgrade"), "upgrade"),
            upgrade_info=_optional_dataclass(_pick(value, "upgrade_info", "upgradeInfo"), ModelUpgradeInfo, "upgrade_info"),
            availability_nux=_optional_dataclass(
                _pick(value, "availability_nux", "availabilityNux"),
                ModelAvailabilityNux,
                "availability_nux",
            ),
            display_name=_ensure_str(_pick(value, "display_name", "displayName"), "display_name"),
            description=_ensure_str(value["description"], "description"),
            hidden=_ensure_bool(value["hidden"], "hidden"),
            supported_reasoning_efforts=_dataclass_tuple(
                _pick(value, "supported_reasoning_efforts", "supportedReasoningEfforts"),
                ReasoningEffortOption,
                "supported_reasoning_efforts",
            ),
            default_reasoning_effort=_reasoning_effort(
                _pick(value, "default_reasoning_effort", "defaultReasoningEffort"),
                "default_reasoning_effort",
            ),
            input_modalities=_input_modalities(_pick(value, "input_modalities", "inputModalities", default=None)),
            supports_personality=_ensure_bool(
                _pick(value, "supports_personality", "supportsPersonality", default=False),
                "supports_personality",
            ),
            additional_speed_tiers=_string_tuple(
                _pick(value, "additional_speed_tiers", "additionalSpeedTiers", default=()),
                "additional_speed_tiers",
            ),
            service_tiers=_dataclass_tuple(
                _pick(value, "service_tiers", "serviceTiers", default=()),
                ModelServiceTier,
                "service_tiers",
            ),
            default_service_tier=_optional_str(
                _pick(value, "default_service_tier", "defaultServiceTier"),
                "default_service_tier",
            ),
            is_default=_ensure_bool(_pick(value, "is_default", "isDefault"), "is_default"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _model_mapping(self, camel=False)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _model_mapping(self, camel=True)


@dataclass(frozen=True)
class ModelListResponse:
    data: tuple[Model, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _dataclass_tuple(self.data, Model, "data"))
        object.__setattr__(self, "next_cursor", _optional_str(self.next_cursor, "next_cursor"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ModelListResponse":
        _ensure_mapping(value, "ModelListResponse")
        return cls(
            data=_dataclass_tuple(value["data"], Model, "data"),
            next_cursor=_optional_str(_pick(value, "next_cursor", "nextCursor"), "next_cursor"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"data": [item.to_mapping() for item in self.data], "next_cursor": self.next_cursor}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"data": [item.to_camel_mapping() for item in self.data], "nextCursor": self.next_cursor}


@dataclass(frozen=True)
class ModelReroutedNotification:
    thread_id: str
    turn_id: str
    from_model: str
    to_model: str
    reason: ModelRerouteReason | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "from_model", _ensure_str(self.from_model, "from_model"))
        object.__setattr__(self, "to_model", _ensure_str(self.to_model, "to_model"))
        object.__setattr__(self, "reason", ModelRerouteReason.parse(self.reason))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ModelReroutedNotification":
        _ensure_mapping(value, "ModelReroutedNotification")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            turn_id=_ensure_str(_pick(value, "turn_id", "turnId"), "turn_id"),
            from_model=_ensure_str(_pick(value, "from_model", "fromModel"), "from_model"),
            to_model=_ensure_str(_pick(value, "to_model", "toModel"), "to_model"),
            reason=ModelRerouteReason.parse(value["reason"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "from_model": self.from_model,
            "to_model": self.to_model,
            "reason": self.reason.value,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "threadId": self.thread_id,
            "turnId": self.turn_id,
            "fromModel": self.from_model,
            "toModel": self.to_model,
            "reason": self.reason.value,
        }


@dataclass(frozen=True)
class ModelVerificationNotification:
    thread_id: str
    turn_id: str
    verifications: tuple[ModelVerification, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "verifications", tuple(ModelVerification.parse(item) for item in self.verifications))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ModelVerificationNotification":
        _ensure_mapping(value, "ModelVerificationNotification")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            turn_id=_ensure_str(_pick(value, "turn_id", "turnId"), "turn_id"),
            verifications=tuple(ModelVerification.parse(item) for item in _iterable(value["verifications"], "verifications")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "verifications": [item.value for item in self.verifications],
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "threadId": self.thread_id,
            "turnId": self.turn_id,
            "verifications": [item.value for item in self.verifications],
        }


def _model_mapping(value: Model, *, camel: bool) -> dict[str, JsonValue]:
    key = _camel_key if camel else (lambda name: name)
    return {
        "id": value.id,
        "model": value.model,
        "upgrade": value.upgrade,
        key("upgrade_info"): None if value.upgrade_info is None else value.upgrade_info.to_camel_mapping() if camel else value.upgrade_info.to_mapping(),
        key("availability_nux"): None if value.availability_nux is None else value.availability_nux.to_mapping(),
        key("display_name"): value.display_name,
        "description": value.description,
        "hidden": value.hidden,
        key("supported_reasoning_efforts"): [
            item.to_camel_mapping() if camel else item.to_mapping() for item in value.supported_reasoning_efforts
        ],
        key("default_reasoning_effort"): value.default_reasoning_effort.value,
        key("input_modalities"): [item.value for item in value.input_modalities],
        key("supports_personality"): value.supports_personality,
        key("additional_speed_tiers"): list(value.additional_speed_tiers),
        key("service_tiers"): [item.to_mapping() for item in value.service_tiers],
        key("default_service_tier"): value.default_service_tier,
        key("is_default"): value.is_default,
    }


def _camel_key(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


def _ensure_mapping(value: JsonValue, type_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} mapping must be a mapping")


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_bool(value: JsonValue, field_name: str) -> bool | None:
    if value is None:
        return None
    return _ensure_bool(value, field_name)


def _optional_u32(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**32 - 1:
        raise TypeError(f"{field_name} must be an unsigned 32-bit integer")
    return value


def _reasoning_effort(value: JsonValue, field_name: str) -> ReasoningEffort:
    if isinstance(value, ReasoningEffort):
        return value
    if isinstance(value, str):
        return ReasoningEffort.parse(value)
    raise TypeError(f"{field_name} must be a ReasoningEffort or string")


def _input_modalities(value: JsonValue) -> tuple[InputModality, ...]:
    if value is None:
        return default_input_modalities()
    return tuple(InputModality(item.value if isinstance(item, InputModality) else item) for item in _iterable(value, "input_modalities"))


def _iterable(value: JsonValue, field_name: str) -> Iterable[JsonValue]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable")
    return value


def _string_tuple(value: JsonValue, field_name: str) -> tuple[str, ...]:
    return tuple(_ensure_str(item, f"{field_name} item") for item in _iterable(value, field_name))


def _optional_dataclass(value: JsonValue, cls: type, field_name: str):
    if value is None:
        return None
    if isinstance(value, cls):
        return value
    if isinstance(value, Mapping) and hasattr(cls, "from_mapping"):
        return cls.from_mapping(value)
    raise TypeError(f"{field_name} must be {cls.__name__} or mapping")


def _dataclass_tuple(value: JsonValue, cls: type, field_name: str) -> tuple:
    result = []
    for item in _iterable(value, field_name):
        if isinstance(item, cls):
            result.append(item)
        elif isinstance(item, Mapping) and hasattr(cls, "from_mapping"):
            result.append(cls.from_mapping(item))
        else:
            raise TypeError(f"{field_name} item must be {cls.__name__} or mapping")
    return tuple(result)


__all__ = [
    "Model",
    "ModelAvailabilityNux",
    "ModelListParams",
    "ModelListResponse",
    "ModelProviderCapabilitiesReadParams",
    "ModelProviderCapabilitiesReadResponse",
    "ModelRerouteReason",
    "ModelReroutedNotification",
    "ModelServiceTier",
    "ModelUpgradeInfo",
    "ModelVerification",
    "ModelVerificationNotification",
    "ReasoningEffortOption",
    "default_input_modalities",
]
