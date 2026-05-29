"""Config protocol types.

Ported from:

- ``codex/codex-rs/protocol/src/config_types.rs``
- ``codex/codex-rs/protocol/src/protocol.rs`` for ``AskForApproval``
- ``codex/codex-rs/utils/cli/src/sandbox_mode_cli_arg.rs``
- ``codex/codex-rs/utils/cli/src/approval_mode_cli_arg.rs``

The Rust code relies on Serde rename rules and clap value enums. This Python
port represents those values as string enums so JSON/TOML-facing names stay
explicit and stable without any third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from pathlib import Path


UPSTREAM_CONFIG_TYPES = "codex/codex-rs/protocol/src/config_types.rs"
UPSTREAM_PROTOCOL = "codex/codex-rs/protocol/src/protocol.rs"


class ConfigTypeParseError(ValueError):
    """Raised when a config enum cannot parse a serialized value."""


class _StringEnum(str, Enum):
    """String enum with explicit parse and JSON helpers."""

    @classmethod
    def parse(cls, raw: str):
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ConfigTypeParseError(f"invalid {cls.__name__} value `{raw}`; expected one of: {choices}") from exc

    def to_json(self) -> str:
        return str(self.value)


class AutoCompactTokenLimitScope(_StringEnum):
    TOTAL = "total"
    BODY_AFTER_PREFIX = "body_after_prefix"

    @classmethod
    def default(cls) -> "AutoCompactTokenLimitScope":
        return cls.TOTAL


class ReasoningSummary(_StringEnum):
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"
    NONE = "none"

    @classmethod
    def default(cls) -> "ReasoningSummary":
        return cls.AUTO


class ReasoningEffort(_StringEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"

    @classmethod
    def default(cls) -> "ReasoningEffort":
        return cls.MEDIUM


class Verbosity(_StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def default(cls) -> "Verbosity":
        return cls.MEDIUM


class SandboxMode(_StringEnum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"

    @classmethod
    def default(cls) -> "SandboxMode":
        return cls.READ_ONLY


class ApprovalsReviewer(_StringEnum):
    USER = "user"
    AUTO_REVIEW = "guardian_subagent"

    @classmethod
    def default(cls) -> "ApprovalsReviewer":
        return cls.USER

    @classmethod
    def parse(cls, raw: str) -> "ApprovalsReviewer":
        if raw == "auto_review":
            return cls.AUTO_REVIEW
        return super().parse(raw)


class ShellEnvironmentPolicyInherit(_StringEnum):
    CORE = "core"
    ALL = "all"
    NONE = "none"

    @classmethod
    def default(cls) -> "ShellEnvironmentPolicyInherit":
        return cls.ALL


@dataclass(frozen=True)
class ShellEnvironmentPolicy:
    inherit: ShellEnvironmentPolicyInherit = ShellEnvironmentPolicyInherit.ALL
    ignore_default_excludes: bool = True
    exclude: tuple[str, ...] = ()
    set_values: dict[str, str] = field(default_factory=dict)
    include_only: tuple[str, ...] = ()
    use_profile: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "inherit", ShellEnvironmentPolicyInherit(self.inherit))
        if not isinstance(self.ignore_default_excludes, bool):
            raise TypeError("ignore_default_excludes must be a bool")
        if isinstance(self.exclude, str):
            raise TypeError("exclude must be a list of strings")
        object.__setattr__(self, "exclude", tuple(self.exclude))
        if not all(isinstance(item, str) for item in self.exclude):
            raise TypeError("exclude entries must be strings")
        if not isinstance(self.set_values, dict):
            raise TypeError("set_values must be a mapping")
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in self.set_values.items()):
            raise TypeError("set_values keys and values must be strings")
        if isinstance(self.include_only, str):
            raise TypeError("include_only must be a list of strings")
        object.__setattr__(self, "include_only", tuple(self.include_only))
        if not all(isinstance(item, str) for item in self.include_only):
            raise TypeError("include_only entries must be strings")
        if not isinstance(self.use_profile, bool):
            raise TypeError("use_profile must be a bool")

    @classmethod
    def default(cls) -> "ShellEnvironmentPolicy":
        return cls()


class WindowsSandboxLevel(_StringEnum):
    DISABLED = "disabled"
    RESTRICTED_TOKEN = "restricted-token"
    ELEVATED = "elevated"

    @classmethod
    def default(cls) -> "WindowsSandboxLevel":
        return cls.DISABLED


class Personality(_StringEnum):
    NONE = "none"
    FRIENDLY = "friendly"
    PRAGMATIC = "pragmatic"


class WebSearchMode(_StringEnum):
    DISABLED = "disabled"
    CACHED = "cached"
    LIVE = "live"

    @classmethod
    def default(cls) -> "WebSearchMode":
        return cls.CACHED


class WebSearchContextSize(_StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class WebSearchLocation:
    country: str | None = None
    region: str | None = None
    city: str | None = None
    timezone: str | None = None

    def merge(self, other: "WebSearchLocation") -> "WebSearchLocation":
        return WebSearchLocation(
            country=other.country if other.country is not None else self.country,
            region=other.region if other.region is not None else self.region,
            city=other.city if other.city is not None else self.city,
            timezone=other.timezone if other.timezone is not None else self.timezone,
        )


@dataclass(frozen=True)
class WebSearchToolConfig:
    context_size: WebSearchContextSize | None = None
    allowed_domains: tuple[str, ...] | None = None
    location: WebSearchLocation | None = None

    def merge(self, other: "WebSearchToolConfig") -> "WebSearchToolConfig":
        if self.location is not None and other.location is not None:
            location = self.location.merge(other.location)
        else:
            location = other.location if other.location is not None else self.location
        return WebSearchToolConfig(
            context_size=other.context_size if other.context_size is not None else self.context_size,
            allowed_domains=other.allowed_domains if other.allowed_domains is not None else self.allowed_domains,
            location=location,
        )


@dataclass(frozen=True)
class WebSearchFilters:
    allowed_domains: tuple[str, ...] | None = None


class WebSearchUserLocationType(_StringEnum):
    APPROXIMATE = "approximate"

    @classmethod
    def default(cls) -> "WebSearchUserLocationType":
        return cls.APPROXIMATE


@dataclass(frozen=True)
class WebSearchUserLocation:
    type: WebSearchUserLocationType = WebSearchUserLocationType.APPROXIMATE
    country: str | None = None
    region: str | None = None
    city: str | None = None
    timezone: str | None = None

    @classmethod
    def from_location(cls, location: WebSearchLocation) -> "WebSearchUserLocation":
        return cls(
            country=location.country,
            region=location.region,
            city=location.city,
            timezone=location.timezone,
        )


@dataclass(frozen=True)
class WebSearchConfig:
    filters: WebSearchFilters | None = None
    user_location: WebSearchUserLocation | None = None
    search_context_size: WebSearchContextSize | None = None

    @classmethod
    def from_tool_config(cls, config: WebSearchToolConfig) -> "WebSearchConfig":
        return cls(
            filters=WebSearchFilters(config.allowed_domains) if config.allowed_domains is not None else None,
            user_location=WebSearchUserLocation.from_location(config.location) if config.location is not None else None,
            search_context_size=config.context_size,
        )


SERVICE_TIER_DEFAULT_REQUEST_VALUE = "default"


class ServiceTier(_StringEnum):
    FAST = "fast"
    FLEX = "flex"

    def request_value(self) -> str:
        if self is ServiceTier.FAST:
            return "priority"
        return self.value

    @classmethod
    def from_request_value(cls, value: str) -> "ServiceTier | None":
        if value in {"fast", "priority"}:
            return cls.FAST
        if value == "flex":
            return cls.FLEX
        return None


class ForcedLoginMethod(_StringEnum):
    CHATGPT = "chatgpt"
    API = "api"


DEFAULT_PROVIDER_AUTH_TIMEOUT_MS = 5_000
DEFAULT_PROVIDER_AUTH_REFRESH_INTERVAL_MS = 300_000


@dataclass(frozen=True)
class ModelProviderAuthInfo:
    command: str
    args: tuple[str, ...] = ()
    timeout_ms: int = DEFAULT_PROVIDER_AUTH_TIMEOUT_MS
    refresh_interval_ms: int = DEFAULT_PROVIDER_AUTH_REFRESH_INTERVAL_MS
    cwd: Path = Path(".")

    def __post_init__(self) -> None:
        if self.timeout_ms <= 0:
            raise ValueError("model_providers.<id>.auth.timeout_ms must be non-zero")
        if self.refresh_interval_ms < 0:
            raise ValueError("model_providers.<id>.auth.refresh_interval_ms must be non-negative")

    def timeout(self) -> timedelta:
        return timedelta(milliseconds=self.timeout_ms)

    def refresh_interval(self) -> timedelta | None:
        if self.refresh_interval_ms == 0:
            return None
        return timedelta(milliseconds=self.refresh_interval_ms)


class TrustLevel(_StringEnum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class AltScreenMode(_StringEnum):
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"

    @classmethod
    def default(cls) -> "AltScreenMode":
        return cls.AUTO


class ModeKind(_StringEnum):
    PLAN = "plan"
    DEFAULT = "default"
    PAIR_PROGRAMMING = "pair_programming"
    EXECUTE = "execute"

    @classmethod
    def default(cls) -> "ModeKind":
        return cls.DEFAULT

    @classmethod
    def parse(cls, raw: str) -> "ModeKind":
        if raw in {"code", "pair_programming", "execute", "custom"}:
            return cls.DEFAULT
        return super().parse(raw)

    def display_name(self) -> str:
        if self is ModeKind.PLAN:
            return "Plan"
        if self is ModeKind.PAIR_PROGRAMMING:
            return "Pair Programming"
        if self is ModeKind.EXECUTE:
            return "Execute"
        return "Default"

    def is_tui_visible(self) -> bool:
        return self in TUI_VISIBLE_COLLABORATION_MODES

    def allows_request_user_input(self) -> bool:
        return self is ModeKind.PLAN


TUI_VISIBLE_COLLABORATION_MODES = (ModeKind.DEFAULT, ModeKind.PLAN)
_UNSET = object()


@dataclass(frozen=True)
class Settings:
    model: str
    reasoning_effort: ReasoningEffort | None = None
    developer_instructions: str | None = None


@dataclass(frozen=True)
class CollaborationMode:
    mode: ModeKind
    settings: Settings

    def model(self) -> str:
        return self.settings.model

    def reasoning_effort(self) -> ReasoningEffort | None:
        return self.settings.reasoning_effort

    def with_updates(
        self,
        model: str | object = _UNSET,
        effort: ReasoningEffort | None | object = _UNSET,
        developer_instructions: str | None | object = _UNSET,
    ) -> "CollaborationMode":
        return CollaborationMode(
            mode=self.mode,
            settings=Settings(
                model=self.settings.model if model is _UNSET else str(model),
                reasoning_effort=self.settings.reasoning_effort if effort is _UNSET else effort,
                developer_instructions=(
                    self.settings.developer_instructions
                    if developer_instructions is _UNSET
                    else developer_instructions
                ),
            ),
        )

    def apply_mask(self, mask: "CollaborationModeMask") -> "CollaborationMode":
        return CollaborationMode(
            mode=self.mode if mask.mode is None else mask.mode,
            settings=Settings(
                model=self.settings.model if mask.model is None else mask.model,
                reasoning_effort=(
                    self.settings.reasoning_effort
                    if mask.reasoning_effort is _UNSET
                    else mask.reasoning_effort
                ),
                developer_instructions=(
                    self.settings.developer_instructions
                    if mask.developer_instructions is _UNSET
                    else mask.developer_instructions
                ),
            ),
        )


@dataclass(frozen=True)
class CollaborationModeMask:
    name: str
    mode: ModeKind | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffort | None | object = _UNSET
    developer_instructions: str | None | object = _UNSET


class AskForApproval(_StringEnum):
    UNLESS_TRUSTED = "untrusted"
    ON_FAILURE = "on-failure"
    ON_REQUEST = "on-request"
    NEVER = "never"

    @classmethod
    def default(cls) -> "AskForApproval":
        return cls.ON_REQUEST

    @classmethod
    def parse_cli(cls, raw: str) -> "AskForApproval":
        """Parse ``ApprovalModeCliArg`` and map it to protocol values."""

        if raw == "untrusted":
            return cls.UNLESS_TRUSTED
        return cls.parse(raw)


class ProfileV2NameParseError(ValueError):
    """Matches the validation surface of upstream ``ProfileV2Name``."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid --profile value `{value}`; pass a plain name such as `work`")
        self.value = value


class ProfileV2Name(str):
    """Validated plain profile-v2 name.

    Upstream accepts only ASCII letters, digits, underscores, and hyphens.
    """

    def __new__(cls, value: str) -> "ProfileV2Name":
        if not _is_valid_profile_v2_name(value):
            raise ProfileV2NameParseError(value)
        return str.__new__(cls, value)

    @classmethod
    def parse(cls, value: str) -> "ProfileV2Name":
        return cls(value)

    def as_str(self) -> str:
        return str(self)


def _is_valid_profile_v2_name(value: str) -> bool:
    return bool(value) and all(character.isascii() and (character.isalnum() or character in "_-") for character in value)
