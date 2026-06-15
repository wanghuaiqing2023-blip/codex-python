"""Behavior port for Rust ``codex-tui::update_versions``.

Upstream source: ``codex/codex-rs/tui/src/update_versions.rs``.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="update_versions",
    source="codex/codex-rs/tui/src/update_versions.rs",
    status="complete",
)

_U64_MAX = 2**64 - 1


def is_newer(latest: str, current: str) -> Optional[bool]:
    parsed_latest = parse_version(latest)
    parsed_current = parse_version(current)
    if parsed_latest is None or parsed_current is None:
        return None
    return parsed_latest > parsed_current


def extract_version_from_latest_tag(latest_tag_name: str) -> str:
    prefix = "rust-v"
    if not latest_tag_name.startswith(prefix):
        raise ValueError(f"Failed to parse latest tag name '{latest_tag_name}'")
    return latest_tag_name[len(prefix) :]


def is_source_build_version(version: str) -> bool:
    return parse_version(version) == (0, 0, 0)


def parse_version(v: str) -> Optional[Tuple[int, int, int]]:
    parts = str(v).strip().split(".")
    if len(parts) < 3:
        return None
    parsed: List[int] = []
    for part in parts[:3]:
        if not part or part.startswith(("+", "-")) or not part.isdigit():
            return None
        value = int(part)
        if value > _U64_MAX:
            return None
        parsed.append(value)
    return parsed[0], parsed[1], parsed[2]


def extracts_version_from_latest_tag() -> None:
    assert extract_version_from_latest_tag("rust-v1.5.0") == "1.5.0"


def latest_tag_without_prefix_is_invalid() -> None:
    try:
        extract_version_from_latest_tag("v1.5.0")
    except ValueError:
        return
    raise AssertionError("expected invalid latest tag prefix")


def prerelease_version_is_not_considered_newer() -> None:
    assert is_newer("0.11.0-beta.1", "0.11.0") is None
    assert is_newer("1.0.0-rc.1", "1.0.0") is None


def plain_semver_comparisons_work() -> None:
    assert is_newer("0.11.1", "0.11.0") is True
    assert is_newer("0.11.0", "0.11.1") is False
    assert is_newer("1.0.0", "0.9.9") is True
    assert is_newer("0.9.9", "1.0.0") is False


def source_build_version_is_not_checked() -> None:
    assert is_source_build_version("0.0.0") is True
    assert is_source_build_version("0.1.0") is False


def whitespace_is_ignored() -> None:
    assert parse_version(" 1.2.3 \n") == (1, 2, 3)
    assert is_newer(" 1.2.3 ", "1.2.2") is True


__all__ = [
    "RUST_MODULE",
    "extract_version_from_latest_tag",
    "extracts_version_from_latest_tag",
    "is_newer",
    "is_source_build_version",
    "latest_tag_without_prefix_is_invalid",
    "parse_version",
    "plain_semver_comparisons_work",
    "prerelease_version_is_not_considered_newer",
    "source_build_version_is_not_checked",
    "whitespace_is_ignored",
]
