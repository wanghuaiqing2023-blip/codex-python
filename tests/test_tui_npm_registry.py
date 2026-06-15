from __future__ import annotations

import pytest

from pycodex.tui.npm_registry import (
    PACKAGE_URL,
    NpmPackageInfo,
    ensure_version_ready,
    package_info,
    ready_version_rejects_missing_root_dist,
    ready_version_rejects_stale_latest_dist_tag,
    ready_version_requires_latest_dist_tag_and_root_dist,
    version_info_with_dist,
)


def test_package_url_matches_rust_release_registry_url() -> None:
    assert PACKAGE_URL == "https://registry.npmjs.org/@openai%2fcodex"


def test_ready_version_requires_latest_dist_tag_and_root_dist() -> None:
    ready_version_requires_latest_dist_tag_and_root_dist()


def test_ready_version_rejects_stale_latest_dist_tag() -> None:
    ready_version_rejects_stale_latest_dist_tag()


def test_ready_version_rejects_missing_root_dist() -> None:
    ready_version_rejects_missing_root_dist()


def test_ready_version_rejects_missing_latest_dist_tag() -> None:
    package = {"dist-tags": {}, "versions": {"1.2.3": {"dist": {"tarball": "url", "integrity": "sha"}}}}

    with pytest.raises(ValueError, match="missing latest dist-tag"):
        ensure_version_ready(package, "1.2.3")


def test_ready_version_rejects_missing_version_tarball_and_integrity() -> None:
    with pytest.raises(ValueError, match="version 1.2.3 is missing"):
        ensure_version_ready({"dist-tags": {"latest": "1.2.3"}, "versions": {}}, "1.2.3")

    with pytest.raises(ValueError, match="missing dist.tarball"):
        ensure_version_ready({"dist-tags": {"latest": "1.2.3"}, "versions": {"1.2.3": {"dist": {"integrity": "sha"}}}}, "1.2.3")

    with pytest.raises(ValueError, match="missing dist.integrity"):
        ensure_version_ready({"dist-tags": {"latest": "1.2.3"}, "versions": {"1.2.3": {"dist": {"tarball": "url"}}}}, "1.2.3")


def test_version_is_trimmed_before_latest_dist_tag_comparison() -> None:
    ensure_version_ready(package_info("1.2.3", "1.2.3"), " 1.2.3 ")


def test_version_info_with_dist_returns_parsed_version_info() -> None:
    package = NpmPackageInfo.from_mapping(
        {
            "dist-tags": {"latest": "1.2.3"},
            "versions": {"1.2.3": {"dist": {"tarball": "url", "integrity": "sha"}}},
        }
    )

    info = version_info_with_dist(package, "1.2.3")

    assert info.dist is not None
    assert info.dist.tarball == "url"
    assert info.dist.integrity == "sha"


def test_package_info_requires_object_maps_like_serde() -> None:
    with pytest.raises(TypeError, match="dist-tags must be an object"):
        NpmPackageInfo.from_mapping({"dist-tags": [], "versions": {}})

    with pytest.raises(TypeError, match="versions must be an object"):
        NpmPackageInfo.from_mapping({"dist-tags": {}, "versions": []})


def test_package_info_rejects_non_string_fields_like_serde() -> None:
    with pytest.raises(TypeError, match="dist-tags.latest must be a string"):
        NpmPackageInfo.from_mapping({"dist-tags": {"latest": 123}, "versions": {}})

    with pytest.raises(TypeError, match="dist.tarball must be a string"):
        NpmPackageInfo.from_mapping(
            {
                "dist-tags": {"latest": "1.2.3"},
                "versions": {"1.2.3": {"dist": {"tarball": 123, "integrity": "sha"}}},
            }
        )

    with pytest.raises(TypeError, match="dist.integrity must be a string"):
        NpmPackageInfo.from_mapping(
            {
                "dist-tags": {"latest": "1.2.3"},
                "versions": {"1.2.3": {"dist": {"tarball": "url", "integrity": 123}}},
            }
        )
