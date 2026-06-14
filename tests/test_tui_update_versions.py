import pytest

from pycodex.tui.update_versions import (
    extract_version_from_latest_tag,
    is_newer,
    is_source_build_version,
    parse_version,
)


def test_extracts_version_from_latest_tag():
    # Rust: codex-tui, update_versions.rs, extracts_version_from_latest_tag.
    assert extract_version_from_latest_tag("rust-v1.5.0") == "1.5.0"


def test_latest_tag_without_prefix_is_invalid():
    # Rust: codex-tui, update_versions.rs, latest_tag_without_prefix_is_invalid.
    with pytest.raises(ValueError, match="Failed to parse latest tag name 'v1.5.0'"):
        extract_version_from_latest_tag("v1.5.0")


def test_prerelease_version_is_not_considered_newer():
    # Rust: codex-tui, update_versions.rs, prerelease_version_is_not_considered_newer.
    assert is_newer("0.11.0-beta.1", "0.11.0") is None
    assert is_newer("1.0.0-rc.1", "1.0.0") is None


def test_plain_semver_comparisons_work():
    # Rust: codex-tui, update_versions.rs, plain_semver_comparisons_work.
    assert is_newer("0.11.1", "0.11.0") is True
    assert is_newer("0.11.0", "0.11.1") is False
    assert is_newer("1.0.0", "0.9.9") is True
    assert is_newer("0.9.9", "1.0.0") is False


def test_source_build_version_is_not_checked():
    # Rust: codex-tui, update_versions.rs, source_build_version_is_not_checked.
    assert is_source_build_version("0.0.0") is True
    assert is_source_build_version("0.1.0") is False


def test_whitespace_is_ignored():
    # Rust: codex-tui, update_versions.rs, whitespace_is_ignored.
    assert parse_version(" 1.2.3 \n") == (1, 2, 3)
    assert is_newer(" 1.2.3 ", "1.2.2") is True


def test_parse_version_matches_rust_u64_components():
    assert parse_version("1.2.3.4") == (1, 2, 3)
    assert parse_version("-1.2.3") is None
    assert parse_version("+1.2.3") is None
    assert parse_version("1. 2.3") is None
    assert parse_version("18446744073709551616.0.0") is None
