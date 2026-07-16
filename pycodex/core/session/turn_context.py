"""Turn-context helpers aligned with ``codex-core::session::turn_context``."""

from __future__ import annotations

from datetime import datetime, timezone as utc_timezone
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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


__all__ = ["local_iana_timezone", "local_time_context"]
