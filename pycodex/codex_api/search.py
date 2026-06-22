"""Wire shapes for the Rust ``codex-api/src/search.rs`` contract."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields
from enum import Enum
from typing import Any
from typing import Iterable
from typing import Mapping
from typing import Sequence

from .common import Reasoning


class _LowerEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class FinanceAssetType(_LowerEnum):
    EQUITY = "equity"
    FUND = "fund"
    CRYPTO = "crypto"
    INDEX = "index"


class SportsToolName(_LowerEnum):
    SPORTS = "sports"


class SportsFunction(_LowerEnum):
    SCHEDULE = "schedule"
    STANDINGS = "standings"


class SportsLeague(_LowerEnum):
    NBA = "nba"
    WNBA = "wnba"
    NFL = "nfl"
    NHL = "nhl"
    MLB = "mlb"
    EPL = "epl"
    NCAAMB = "ncaamb"
    NCAAWB = "ncaawb"
    IPL = "ipl"


class SearchResponseLength(_LowerEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class LocationType(_LowerEnum):
    APPROXIMATE = "approximate"


class SearchContextSize(_LowerEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AllowedCaller(_LowerEnum):
    DIRECT = "direct"
    SHELL = "shell"
    CODE_INTERPRETER = "code_interpreter"


@dataclass(frozen=True)
class SearchQuery:
    q: str
    recency: int | None = None
    domains: Sequence[str] | None = None

    def __post_init__(self) -> None:
        _validate_optional_u64(self.recency, "recency")


@dataclass(frozen=True)
class OpenOperation:
    ref_id: str
    lineno: int | None = None

    def __post_init__(self) -> None:
        _validate_optional_u64(self.lineno, "lineno")


@dataclass(frozen=True)
class ClickOperation:
    ref_id: str
    id: int

    def __post_init__(self) -> None:
        _validate_u64(self.id, "id")


@dataclass(frozen=True)
class FindOperation:
    ref_id: str
    pattern: str


@dataclass(frozen=True)
class ScreenshotOperation:
    ref_id: str
    pageno: int

    def __post_init__(self) -> None:
        _validate_u64(self.pageno, "pageno")


@dataclass(frozen=True)
class FinanceOperation:
    ticker: str
    type: FinanceAssetType
    market: str | None = None


@dataclass(frozen=True)
class WeatherOperation:
    location: str
    start: str | None = None
    duration: int | None = None

    def __post_init__(self) -> None:
        _validate_optional_u64(self.duration, "duration")


@dataclass(frozen=True)
class SportsOperation:
    fn: SportsFunction
    league: SportsLeague
    tool: SportsToolName | None = None
    team: str | None = None
    opponent: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    num_games: int | None = None
    locale: str | None = None

    def __post_init__(self) -> None:
        _validate_optional_u64(self.num_games, "num_games")


@dataclass(frozen=True)
class TimeOperation:
    utc_offset: str


@dataclass(frozen=True)
class SearchCommands:
    search_query: Sequence[SearchQuery] | None = None
    image_query: Sequence[SearchQuery] | None = None
    open: Sequence[OpenOperation] | None = None
    click: Sequence[ClickOperation] | None = None
    find: Sequence[FindOperation] | None = None
    screenshot: Sequence[ScreenshotOperation] | None = None
    finance: Sequence[FinanceOperation] | None = None
    weather: Sequence[WeatherOperation] | None = None
    sports: Sequence[SportsOperation] | None = None
    time: Sequence[TimeOperation] | None = None
    response_length: SearchResponseLength | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return _dataclass_to_json_dict(self)


@dataclass(frozen=True)
class ApproximateLocation:
    type: LocationType = LocationType.APPROXIMATE
    country: str | None = None
    region: str | None = None
    city: str | None = None
    timezone: str | None = None


@dataclass(frozen=True)
class SearchFilters:
    allowed_domains: Sequence[str] | None = None
    blocked_domains: Sequence[str] | None = None


@dataclass(frozen=True)
class SearchImageSettings:
    max_results: int | None = None
    caption: bool | None = None

    def __post_init__(self) -> None:
        _validate_optional_u64(self.max_results, "max_results")


@dataclass(frozen=True)
class SearchSettings:
    user_location: ApproximateLocation | None = None
    search_context_size: SearchContextSize | None = None
    filters: SearchFilters | None = None
    image_settings: SearchImageSettings | None = None
    allowed_callers: Sequence[AllowedCaller] | None = None
    external_web_access: bool | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return _dataclass_to_json_dict(self)


@dataclass(frozen=True)
class SearchInput:
    value: str | Sequence[Any]

    @classmethod
    def text(cls, value: str) -> SearchInput:
        return cls(value)

    @classmethod
    def items(cls, value: Sequence[Any]) -> SearchInput:
        return cls(value)

    def to_json_value(self) -> Any:
        return _search_input_to_json(self.value)


@dataclass(frozen=True)
class SearchRequest:
    id: str
    model: str | None = None
    reasoning: Reasoning | None = None
    input: SearchInput | str | Sequence[Any] | None = None
    commands: SearchCommands | None = None
    settings: SearchSettings | None = None
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        _validate_optional_u64(self.max_output_tokens, "max_output_tokens")

    def to_json_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id}
        _put_optional(payload, "model", self.model)
        _put_optional(payload, "reasoning", self.reasoning)
        if self.input is not None:
            payload["input"] = _search_input_to_json(self.input)
        _put_optional(payload, "commands", self.commands)
        _put_optional(payload, "settings", self.settings)
        _put_optional(payload, "max_output_tokens", self.max_output_tokens)
        return payload


@dataclass(frozen=True)
class SearchResponse:
    encrypted_output: str

    @classmethod
    def from_json_dict(cls, payload: Mapping[str, Any]) -> SearchResponse:
        encrypted_output = payload.get("encrypted_output")
        if not isinstance(encrypted_output, str):
            raise ValueError("SearchResponse requires string encrypted_output")
        return cls(encrypted_output=encrypted_output)


def _put_optional(payload: dict[str, Any], key: str, value: Any | None) -> None:
    if value is not None:
        payload[key] = _to_json_value(value)


def _validate_optional_u64(value: object, field_name: str) -> None:
    if value is not None:
        _validate_u64(value, field_name)


def _validate_u64(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _search_input_to_json(value: SearchInput | str | Sequence[Any]) -> Any:
    if isinstance(value, SearchInput):
        return value.to_json_value()
    if isinstance(value, str):
        return value
    return [_to_json_value(item) for item in value]


def _dataclass_to_json_dict(value: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in fields(value):
        item = getattr(value, field.name)
        if item is not None:
            payload[field.name] = _to_json_value(item)
    return payload


def _to_json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_json_dict"):
        return value.to_json_dict()
    if hasattr(value, "to_json_value"):
        return value.to_json_value()
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if hasattr(value, "__dataclass_fields__"):
        return _dataclass_to_json_dict(value)
    if isinstance(value, Mapping):
        return {key: _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (str, bytes)):
        return value
    if isinstance(value, Iterable):
        return [_to_json_value(item) for item in value]
    return value
