"""Update version parsing helpers.

Ported from ``codex/codex-rs/tui/src/update_versions.rs``.
"""

from __future__ import annotations

U64_MAX = 18_446_744_073_709_551_615


def is_newer(latest: str, current: str) -> bool | None:
    latest_version = parse_version(latest)
    current_version = parse_version(current)
    if latest_version is None or current_version is None:
        return None
    return latest_version > current_version


def extract_version_from_latest_tag(latest_tag_name: str) -> str:
    if not isinstance(latest_tag_name, str):
        raise TypeError("latest_tag_name must be a string")
    prefix = "rust-v"
    if not latest_tag_name.startswith(prefix):
        raise ValueError(f"Failed to parse latest tag name '{latest_tag_name}'")
    return latest_tag_name[len(prefix) :]


def is_source_build_version(version: str) -> bool:
    return parse_version(version) == (0, 0, 0)


def parse_version(version: str) -> tuple[int, int, int] | None:
    if not isinstance(version, str):
        raise TypeError("version must be a string")
    parts = version.strip().split(".")
    if len(parts) < 3:
        return None
    parsed: list[int] = []
    for part in parts[:3]:
        if not part or any(ch < "0" or ch > "9" for ch in part):
            return None
        value = int(part)
        if value > U64_MAX:
            return None
        parsed.append(value)
    return (parsed[0], parsed[1], parsed[2])
