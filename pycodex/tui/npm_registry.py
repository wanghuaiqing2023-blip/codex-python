"""Behavior port for Rust ``codex-tui::npm_registry``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Union

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="npm_registry",
    source="codex/codex-rs/tui/src/npm_registry.rs",
    status="complete",
)

PACKAGE_URL = "https://registry.npmjs.org/@openai%2fcodex"


@dataclass(frozen=True)
class NpmPackageDist:
    tarball: Optional[str] = None
    integrity: Optional[str] = None

    @classmethod
    def from_mapping(cls, mapping: Optional[Mapping[str, Any]]) -> Optional["NpmPackageDist"]:
        if mapping is None:
            return None
        return cls(
            tarball=_optional_str(mapping.get("tarball"), "dist.tarball"),
            integrity=_optional_str(mapping.get("integrity"), "dist.integrity"),
        )


@dataclass(frozen=True)
class NpmPackageVersionInfo:
    dist: Optional[NpmPackageDist] = None

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "NpmPackageVersionInfo":
        return cls(dist=NpmPackageDist.from_mapping(_optional_mapping(mapping.get("dist"))))


@dataclass(frozen=True)
class NpmPackageInfo:
    dist_tags: Dict[str, str]
    versions: Dict[str, NpmPackageVersionInfo]

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "NpmPackageInfo":
        dist_tags_raw = _required_mapping(mapping.get("dist-tags"), "dist-tags")
        versions_raw = _required_mapping(mapping.get("versions"), "versions")
        dist_tags = {
            _required_str(key, "dist-tags key"): _required_str(value, f"dist-tags.{key}")
            for key, value in dist_tags_raw.items()
        }
        versions = {
            _required_str(version, "versions key"): NpmPackageVersionInfo.from_mapping(
                _required_mapping(info, f"versions.{version}")
            )
            for version, info in versions_raw.items()
        }
        return cls(dist_tags=dist_tags, versions=versions)


def ensure_version_ready(package_info: Union[NpmPackageInfo, Mapping[str, Any]], version: str) -> None:
    info = _coerce_package_info(package_info)
    version = str(version).strip()

    latest = info.dist_tags.get("latest")
    if latest is None:
        raise ValueError("npm package is missing latest dist-tag")
    if latest != version:
        raise ValueError(f"npm latest dist-tag points to {latest}, expected GitHub release {version}")

    version_info_with_dist(info, version)


def version_info_with_dist(
    package_info: Union[NpmPackageInfo, Mapping[str, Any]], version: str
) -> NpmPackageVersionInfo:
    info = _coerce_package_info(package_info)
    version = str(version)
    try:
        version_info = info.versions[version]
    except KeyError as exc:
        raise ValueError(f"npm package version {version} is missing") from exc

    dist = version_info.dist
    if dist is None:
        raise ValueError(f"npm package version {version} is missing dist metadata")
    if not dist.tarball:
        raise ValueError(f"npm package version {version} is missing dist.tarball")
    if not dist.integrity:
        raise ValueError(f"npm package version {version} is missing dist.integrity")
    return version_info


def version_json(version: str) -> Dict[str, Any]:
    version = str(version)
    return {
        "dist": {
            "integrity": f"sha512-{version}",
            "tarball": f"https://registry.npmjs.org/@openai/codex/-/codex-{version}.tgz",
        }
    }


def package_info(github_latest: str, npm_latest: str) -> NpmPackageInfo:
    github_latest = str(github_latest)
    return NpmPackageInfo.from_mapping(
        {
            "dist-tags": {"latest": str(npm_latest)},
            "versions": {github_latest: version_json(github_latest)},
        }
    )


def ready_version_requires_latest_dist_tag_and_root_dist() -> None:
    latest = "1.2.3"
    ensure_version_ready(package_info(latest, latest), latest)


def ready_version_rejects_stale_latest_dist_tag() -> None:
    try:
        ensure_version_ready(package_info("1.2.3", "1.2.2"), "1.2.3")
    except ValueError as err:
        if "latest dist-tag" not in str(err):
            raise AssertionError(f"error should name stale latest dist-tag: {err}") from err
        return
    raise AssertionError("npm latest dist-tag must match GitHub latest")


def ready_version_rejects_missing_root_dist() -> None:
    package = NpmPackageInfo.from_mapping({"dist-tags": {"latest": "1.2.3"}, "versions": {"1.2.3": {}}})
    try:
        ensure_version_ready(package, "1.2.3")
    except ValueError as err:
        if "missing dist metadata" not in str(err):
            raise AssertionError(f"error should name missing dist metadata: {err}") from err
        return
    raise AssertionError("root package must have dist metadata")


def _coerce_package_info(package_info: Union[NpmPackageInfo, Mapping[str, Any]]) -> NpmPackageInfo:
    if isinstance(package_info, NpmPackageInfo):
        return package_info
    return NpmPackageInfo.from_mapping(package_info)


def _required_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be an object")
    return value


def _optional_mapping(value: Any) -> Optional[Mapping[str, Any]]:
    if value is None:
        return None
    return _required_mapping(value, "dist")


def _required_str(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _optional_str(value: Any, field: str) -> Optional[str]:
    if value is None:
        return None
    return _required_str(value, field)


__all__ = [
    "NpmPackageDist",
    "NpmPackageInfo",
    "NpmPackageVersionInfo",
    "PACKAGE_URL",
    "RUST_MODULE",
    "ensure_version_ready",
    "package_info",
    "ready_version_rejects_missing_root_dist",
    "ready_version_rejects_stale_latest_dist_tag",
    "ready_version_requires_latest_dist_tag_and_root_dist",
    "version_info_with_dist",
    "version_json",
]
