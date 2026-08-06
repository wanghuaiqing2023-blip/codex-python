"""Turn-context helpers aligned with ``codex-core::session::turn_context``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone as utc_timezone
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pycodex.ext.extension_api import ExtensionData
from pycodex.features import Feature
from pycodex.protocol import (
    AskForApproval,
    FileSystemSandboxPolicy,
    PermissionProfile,
    SandboxPolicy,
    SessionSource,
    TruncationPolicyConfig,
    WindowsSandboxLevel,
)


# CLDR's primary (territory 001) mappings for Windows zones commonly seen by
# Codex. Unknown Windows identifiers deliberately take Rust's UTC fallback
# rather than leaking a localized display name into model context.
_WINDOWS_TO_IANA = {
    "AUS Central Standard Time": "Australia/Darwin",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "Alaskan Standard Time": "America/Anchorage",
    "Arab Standard Time": "Asia/Riyadh",
    "Arabian Standard Time": "Asia/Dubai",
    "Atlantic Standard Time": "America/Halifax",
    "Azerbaijan Standard Time": "Asia/Baku",
    "Canada Central Standard Time": "America/Regina",
    "Central America Standard Time": "America/Guatemala",
    "Central Asia Standard Time": "Asia/Almaty",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "Central Pacific Standard Time": "Pacific/Guadalcanal",
    "Central Standard Time": "America/Chicago",
    "China Standard Time": "Asia/Shanghai",
    "E. Africa Standard Time": "Africa/Nairobi",
    "E. Australia Standard Time": "Australia/Brisbane",
    "E. Europe Standard Time": "Europe/Chisinau",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Eastern Standard Time": "America/New_York",
    "Egypt Standard Time": "Africa/Cairo",
    "FLE Standard Time": "Europe/Kiev",
    "GMT Standard Time": "Europe/London",
    "GTB Standard Time": "Europe/Bucharest",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "India Standard Time": "Asia/Calcutta",
    "Israel Standard Time": "Asia/Jerusalem",
    "Japan Standard Time": "Asia/Tokyo",
    "Korea Standard Time": "Asia/Seoul",
    "Mexico Standard Time": "America/Mexico_City",
    "Mountain Standard Time": "America/Denver",
    "Myanmar Standard Time": "Asia/Rangoon",
    "New Zealand Standard Time": "Pacific/Auckland",
    "Pacific SA Standard Time": "America/Santiago",
    "Pacific Standard Time": "America/Los_Angeles",
    "Russian Standard Time": "Europe/Moscow",
    "SA Eastern Standard Time": "America/Cayenne",
    "SA Pacific Standard Time": "America/Bogota",
    "Singapore Standard Time": "Asia/Singapore",
    "South Africa Standard Time": "Africa/Johannesburg",
    "Taipei Standard Time": "Asia/Taipei",
    "Tokyo Standard Time": "Asia/Tokyo",
    "US Eastern Standard Time": "America/Indianapolis",
    "US Mountain Standard Time": "America/Phoenix",
    "UTC": "Etc/UTC",
    "UTC+12": "Etc/GMT-12",
    "UTC-02": "Etc/GMT+2",
    "UTC-11": "Etc/GMT+11",
    "W. Australia Standard Time": "Australia/Perth",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "W. Europe Standard Time": "Europe/Berlin",
    "West Asia Standard Time": "Asia/Tashkent",
    "West Pacific Standard Time": "Pacific/Port_Moresby",
}


@dataclass(frozen=True)
class TurnContext:
    cwd: Path
    turn_id: str | None = None
    model_info: Any = None
    provider: Any = None
    auth_manager: Any = None
    user_instructions: str | None = None
    developer_instructions: str | None = None
    compact_prompt: str | None = None
    config: Any = None
    available_models: tuple[Any, ...] = ()
    permission_profile: PermissionProfile = field(default_factory=PermissionProfile.disabled)
    windows_sandbox_level: WindowsSandboxLevel = WindowsSandboxLevel.DISABLED
    approval_policy: Any = AskForApproval.ON_REQUEST
    sandbox_policy: SandboxPolicy = field(default_factory=SandboxPolicy.danger_full_access)
    file_system_sandbox_policy: FileSystemSandboxPolicy | None = None
    features: Any = None
    collaboration_mode: Any = None
    realtime_active: bool = False
    personality: Any = None
    reasoning_effort: Any = None
    reasoning_summary: Any = "auto"
    service_tier: Any = None
    current_date: str | None = None
    timezone: str | None = None
    network: Any = None
    environments: Any = None
    final_output_json_schema: Any = None
    goal_tools_enabled: bool = False
    server_model_warning_emitted: bool = False
    model_verification_emitted: bool = False
    truncation_policy: TruncationPolicyConfig = field(
        default_factory=lambda: TruncationPolicyConfig.tokens(10_000)
    )
    session_source: SessionSource = field(default_factory=SessionSource.default)
    extension_data: ExtensionData | None = None
    turn_skills: Any = None

    @property
    def sub_id(self) -> str:
        return str(self.turn_id or "")

    def apps_enabled(self) -> bool:
        """Match Rust ``TurnContext::apps_enabled`` for the current auth."""

        uses_codex_backend = _current_auth_uses_codex_backend(self.auth_manager)
        enabled_for_auth = getattr(self.features, "apps_enabled_for_auth", None)
        if callable(enabled_for_auth):
            try:
                return bool(enabled_for_auth(uses_codex_backend))
            except Exception:
                return False
        enabled = getattr(self.features, "enabled", None)
        if not callable(enabled):
            return False
        try:
            return bool(enabled(Feature.APPS)) and uses_codex_backend
        except Exception:
            return False


def _current_auth_uses_codex_backend(auth_manager: Any) -> bool:
    if auth_manager is None:
        return False
    current = getattr(auth_manager, "current_auth_uses_codex_backend", None)
    if callable(current):
        try:
            return bool(current())
        except Exception:
            return False
    uses_codex_backend = getattr(auth_manager, "uses_codex_backend", None)
    if callable(uses_codex_backend):
        try:
            return bool(uses_codex_backend())
        except Exception:
            return False
    return bool(uses_codex_backend)


def local_time_context() -> tuple[str, str]:
    """Return the local date and IANA zone, with Rust's UTC fallback."""

    timezone_name = local_iana_timezone()
    if timezone_name is None:
        now = datetime.now(utc_timezone.utc)
        return now.strftime("%Y-%m-%d"), "Etc/UTC"
    now = datetime.now().astimezone()
    return now.strftime("%Y-%m-%d"), timezone_name


def local_iana_timezone() -> str | None:
    """Resolve the host timezone without returning localized display names."""

    configured = os.environ.get("TZ")
    if configured and _is_iana_timezone(configured):
        return configured

    local_tz = datetime.now().astimezone().tzinfo
    for attribute in ("key", "zone"):
        candidate = getattr(local_tz, attribute, None)
        if isinstance(candidate, str) and _is_iana_timezone(candidate):
            return candidate

    windows_id = _windows_timezone_key_name()
    if windows_id is not None:
        candidate = _WINDOWS_TO_IANA.get(windows_id)
        if candidate is not None and _is_iana_timezone(candidate):
            return candidate
    return None


def _windows_timezone_key_name() -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg

        key_path = r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            value, _kind = winreg.QueryValueEx(key, "TimeZoneKeyName")
    except (ImportError, OSError):
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _is_iana_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        return False
    return True


__all__ = ["TurnContext", "local_iana_timezone", "local_time_context"]
