"""App metadata protocol types ported from ``protocol/v2/apps.rs``."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar

JsonValue = Any
_T = TypeVar("_T")


@dataclass(frozen=True)
class AppsListParams:
    cursor: str | None = None
    limit: int | None = None
    thread_id: str | None = None
    force_refetch: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "cursor", _optional_str(self.cursor, "cursor"))
        object.__setattr__(self, "limit", _optional_u32(self.limit, "limit"))
        object.__setattr__(self, "thread_id", _optional_str(self.thread_id, "thread_id"))
        object.__setattr__(
            self,
            "force_refetch",
            _ensure_bool(self.force_refetch, "force_refetch"),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppsListParams":
        _ensure_mapping(value, "AppsListParams")
        return cls(
            cursor=_optional_str(_pick(value, "cursor"), "cursor"),
            limit=_optional_u32(_pick(value, "limit"), "limit"),
            thread_id=_optional_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            force_refetch=_ensure_bool(
                _pick(value, "force_refetch", "forceRefetch", default=False),
                "force_refetch",
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "cursor": self.cursor,
            "limit": self.limit,
            "thread_id": self.thread_id,
            "force_refetch": self.force_refetch,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "cursor": self.cursor,
            "limit": self.limit,
            "threadId": self.thread_id,
        }
        if self.force_refetch:
            result["forceRefetch"] = self.force_refetch
        return result


@dataclass(frozen=True)
class AppBranding:
    category: str | None = None
    developer: str | None = None
    website: str | None = None
    privacy_policy: str | None = None
    terms_of_service: str | None = None
    is_discoverable_app: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", _optional_str(self.category, "category"))
        object.__setattr__(self, "developer", _optional_str(self.developer, "developer"))
        object.__setattr__(self, "website", _optional_str(self.website, "website"))
        object.__setattr__(
            self,
            "privacy_policy",
            _optional_str(self.privacy_policy, "privacy_policy"),
        )
        object.__setattr__(
            self,
            "terms_of_service",
            _optional_str(self.terms_of_service, "terms_of_service"),
        )
        object.__setattr__(
            self,
            "is_discoverable_app",
            _ensure_bool(self.is_discoverable_app, "is_discoverable_app"),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppBranding":
        _ensure_mapping(value, "AppBranding")
        return cls(
            category=_optional_str(_pick(value, "category"), "category"),
            developer=_optional_str(_pick(value, "developer"), "developer"),
            website=_optional_str(_pick(value, "website"), "website"),
            privacy_policy=_optional_str(
                _pick(value, "privacy_policy", "privacyPolicy"),
                "privacy_policy",
            ),
            terms_of_service=_optional_str(
                _pick(value, "terms_of_service", "termsOfService"),
                "terms_of_service",
            ),
            is_discoverable_app=_ensure_bool(
                _pick(value, "is_discoverable_app", "isDiscoverableApp", default=False),
                "is_discoverable_app",
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "category": self.category,
            "developer": self.developer,
            "website": self.website,
            "privacy_policy": self.privacy_policy,
            "terms_of_service": self.terms_of_service,
            "is_discoverable_app": self.is_discoverable_app,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "category": self.category,
            "developer": self.developer,
            "website": self.website,
            "privacyPolicy": self.privacy_policy,
            "termsOfService": self.terms_of_service,
            "isDiscoverableApp": self.is_discoverable_app,
        }


@dataclass(frozen=True)
class AppReview:
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _ensure_str(self.status, "status"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppReview":
        _ensure_mapping(value, "AppReview")
        return cls(status=_ensure_str(value["status"], "status"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"status": self.status}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class AppScreenshot:
    url: str | None = None
    file_id: str | None = None
    user_prompt: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "url", _optional_str(self.url, "url"))
        object.__setattr__(self, "file_id", _optional_str(self.file_id, "file_id"))
        object.__setattr__(self, "user_prompt", _ensure_str(self.user_prompt, "user_prompt"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppScreenshot":
        _ensure_mapping(value, "AppScreenshot")
        return cls(
            url=_optional_str(_pick(value, "url"), "url"),
            file_id=_optional_str(_pick(value, "file_id", "fileId"), "file_id"),
            user_prompt=_ensure_str(
                _pick(value, "user_prompt", "userPrompt"),
                "user_prompt",
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "url": self.url,
            "file_id": self.file_id,
            "user_prompt": self.user_prompt,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "url": self.url,
            "fileId": self.file_id,
            "userPrompt": self.user_prompt,
        }


@dataclass(frozen=True)
class AppMetadata:
    review: AppReview | None = None
    categories: tuple[str, ...] | None = None
    sub_categories: tuple[str, ...] | None = None
    seo_description: str | None = None
    screenshots: tuple[AppScreenshot, ...] | None = None
    developer: str | None = None
    version: str | None = None
    version_id: str | None = None
    version_notes: str | None = None
    first_party_type: str | None = None
    first_party_requires_install: bool | None = None
    show_in_composer_when_unlinked: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "review", _optional_dataclass(self.review, AppReview, "review"))
        object.__setattr__(self, "categories", _optional_string_tuple(self.categories, "categories"))
        object.__setattr__(
            self,
            "sub_categories",
            _optional_string_tuple(self.sub_categories, "sub_categories"),
        )
        object.__setattr__(
            self,
            "seo_description",
            _optional_str(self.seo_description, "seo_description"),
        )
        object.__setattr__(
            self,
            "screenshots",
            _optional_dataclass_tuple(self.screenshots, AppScreenshot, "screenshots"),
        )
        object.__setattr__(self, "developer", _optional_str(self.developer, "developer"))
        object.__setattr__(self, "version", _optional_str(self.version, "version"))
        object.__setattr__(self, "version_id", _optional_str(self.version_id, "version_id"))
        object.__setattr__(
            self,
            "version_notes",
            _optional_str(self.version_notes, "version_notes"),
        )
        object.__setattr__(
            self,
            "first_party_type",
            _optional_str(self.first_party_type, "first_party_type"),
        )
        object.__setattr__(
            self,
            "first_party_requires_install",
            _optional_bool(self.first_party_requires_install, "first_party_requires_install"),
        )
        object.__setattr__(
            self,
            "show_in_composer_when_unlinked",
            _optional_bool(
                self.show_in_composer_when_unlinked,
                "show_in_composer_when_unlinked",
            ),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppMetadata":
        _ensure_mapping(value, "AppMetadata")
        review_value = _pick(value, "review")
        screenshots_value = _pick(value, "screenshots")
        return cls(
            review=None if review_value is None else AppReview.from_mapping(review_value),
            categories=_optional_string_tuple(_pick(value, "categories"), "categories"),
            sub_categories=_optional_string_tuple(
                _pick(value, "sub_categories", "subCategories"),
                "sub_categories",
            ),
            seo_description=_optional_str(
                _pick(value, "seo_description", "seoDescription"),
                "seo_description",
            ),
            screenshots=None
            if screenshots_value is None
            else tuple(AppScreenshot.from_mapping(item) for item in _iterable(screenshots_value, "screenshots")),
            developer=_optional_str(_pick(value, "developer"), "developer"),
            version=_optional_str(_pick(value, "version"), "version"),
            version_id=_optional_str(_pick(value, "version_id", "versionId"), "version_id"),
            version_notes=_optional_str(
                _pick(value, "version_notes", "versionNotes"),
                "version_notes",
            ),
            first_party_type=_optional_str(
                _pick(value, "first_party_type", "firstPartyType"),
                "first_party_type",
            ),
            first_party_requires_install=_optional_bool(
                _pick(value, "first_party_requires_install", "firstPartyRequiresInstall"),
                "first_party_requires_install",
            ),
            show_in_composer_when_unlinked=_optional_bool(
                _pick(value, "show_in_composer_when_unlinked", "showInComposerWhenUnlinked"),
                "show_in_composer_when_unlinked",
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "review": None if self.review is None else self.review.to_mapping(),
            "categories": None if self.categories is None else list(self.categories),
            "sub_categories": None if self.sub_categories is None else list(self.sub_categories),
            "seo_description": self.seo_description,
            "screenshots": None
            if self.screenshots is None
            else [screenshot.to_mapping() for screenshot in self.screenshots],
            "developer": self.developer,
            "version": self.version,
            "version_id": self.version_id,
            "version_notes": self.version_notes,
            "first_party_type": self.first_party_type,
            "first_party_requires_install": self.first_party_requires_install,
            "show_in_composer_when_unlinked": self.show_in_composer_when_unlinked,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "review": None if self.review is None else self.review.to_camel_mapping(),
            "categories": None if self.categories is None else list(self.categories),
            "subCategories": None if self.sub_categories is None else list(self.sub_categories),
            "seoDescription": self.seo_description,
            "screenshots": None
            if self.screenshots is None
            else [screenshot.to_camel_mapping() for screenshot in self.screenshots],
            "developer": self.developer,
            "version": self.version,
            "versionId": self.version_id,
            "versionNotes": self.version_notes,
            "firstPartyType": self.first_party_type,
            "firstPartyRequiresInstall": self.first_party_requires_install,
            "showInComposerWhenUnlinked": self.show_in_composer_when_unlinked,
        }


@dataclass(frozen=True)
class AppInfo:
    id: str
    name: str
    description: str | None = None
    logo_url: str | None = None
    logo_url_dark: str | None = None
    distribution_channel: str | None = None
    branding: AppBranding | Mapping[str, JsonValue] | None = None
    app_metadata: AppMetadata | Mapping[str, JsonValue] | None = None
    labels: Mapping[str, str] | None = None
    install_url: str | None = None
    is_accessible: bool = False
    is_enabled: bool = True
    plugin_display_names: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "description", _optional_str(self.description, "description"))
        object.__setattr__(self, "logo_url", _optional_str(self.logo_url, "logo_url"))
        object.__setattr__(self, "logo_url_dark", _optional_str(self.logo_url_dark, "logo_url_dark"))
        object.__setattr__(
            self,
            "distribution_channel",
            _optional_str(self.distribution_channel, "distribution_channel"),
        )
        object.__setattr__(
            self,
            "branding",
            _optional_dataclass(self.branding, AppBranding, "branding"),
        )
        object.__setattr__(
            self,
            "app_metadata",
            _optional_dataclass(self.app_metadata, AppMetadata, "app_metadata"),
        )
        object.__setattr__(self, "labels", _optional_string_map(self.labels, "labels"))
        object.__setattr__(self, "install_url", _optional_str(self.install_url, "install_url"))
        object.__setattr__(self, "is_accessible", _ensure_bool(self.is_accessible, "is_accessible"))
        object.__setattr__(self, "is_enabled", _ensure_bool(self.is_enabled, "is_enabled"))
        object.__setattr__(
            self,
            "plugin_display_names",
            _string_tuple(self.plugin_display_names, "plugin_display_names"),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppInfo":
        _ensure_mapping(value, "AppInfo")
        branding_value = _pick(value, "branding")
        metadata_value = _pick(value, "app_metadata", "appMetadata")
        return cls(
            id=_ensure_str(value["id"], "id"),
            name=_ensure_str(value["name"], "name"),
            description=_optional_str(_pick(value, "description"), "description"),
            logo_url=_optional_str(_pick(value, "logo_url", "logoUrl"), "logo_url"),
            logo_url_dark=_optional_str(_pick(value, "logo_url_dark", "logoUrlDark"), "logo_url_dark"),
            distribution_channel=_optional_str(
                _pick(value, "distribution_channel", "distributionChannel"),
                "distribution_channel",
            ),
            branding=None if branding_value is None else AppBranding.from_mapping(branding_value),
            app_metadata=None if metadata_value is None else AppMetadata.from_mapping(metadata_value),
            labels=_optional_string_map(_pick(value, "labels"), "labels"),
            install_url=_optional_str(_pick(value, "install_url", "installUrl"), "install_url"),
            is_accessible=_ensure_bool(
                _pick(value, "is_accessible", "isAccessible", default=False),
                "is_accessible",
            ),
            is_enabled=_ensure_bool(
                _pick(value, "is_enabled", "isEnabled", default=True),
                "is_enabled",
            ),
            plugin_display_names=_string_tuple(
                _pick(value, "plugin_display_names", "pluginDisplayNames", default=()),
                "plugin_display_names",
            ),
        )

    def to_summary(self) -> "AppSummary":
        return AppSummary(
            id=self.id,
            name=self.name,
            description=self.description,
            install_url=self.install_url,
            needs_auth=False,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "logo_url": self.logo_url,
            "logo_url_dark": self.logo_url_dark,
            "distribution_channel": self.distribution_channel,
            "branding": None if self.branding is None else self.branding.to_mapping(),
            "app_metadata": None if self.app_metadata is None else self.app_metadata.to_mapping(),
            "labels": None if self.labels is None else dict(self.labels),
            "install_url": self.install_url,
            "is_accessible": self.is_accessible,
            "is_enabled": self.is_enabled,
            "plugin_display_names": list(self.plugin_display_names),
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "logoUrl": self.logo_url,
            "logoUrlDark": self.logo_url_dark,
            "distributionChannel": self.distribution_channel,
            "branding": None if self.branding is None else self.branding.to_camel_mapping(),
            "appMetadata": None if self.app_metadata is None else self.app_metadata.to_camel_mapping(),
            "labels": None if self.labels is None else dict(self.labels),
            "installUrl": self.install_url,
            "isAccessible": self.is_accessible,
            "isEnabled": self.is_enabled,
            "pluginDisplayNames": list(self.plugin_display_names),
        }


@dataclass(frozen=True)
class AppSummary:
    id: str
    name: str
    description: str | None = None
    install_url: str | None = None
    needs_auth: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "description", _optional_str(self.description, "description"))
        object.__setattr__(self, "install_url", _optional_str(self.install_url, "install_url"))
        object.__setattr__(self, "needs_auth", _ensure_bool(self.needs_auth, "needs_auth"))

    @classmethod
    def from_app_info(cls, value: AppInfo | Mapping[str, JsonValue]) -> "AppSummary":
        info = value if isinstance(value, AppInfo) else AppInfo.from_mapping(value)
        return info.to_summary()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppSummary":
        _ensure_mapping(value, "AppSummary")
        return cls(
            id=_ensure_str(value["id"], "id"),
            name=_ensure_str(value["name"], "name"),
            description=_optional_str(_pick(value, "description"), "description"),
            install_url=_optional_str(_pick(value, "install_url", "installUrl"), "install_url"),
            needs_auth=_ensure_bool(_pick(value, "needs_auth", "needsAuth"), "needs_auth"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "install_url": self.install_url,
            "needs_auth": self.needs_auth,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "installUrl": self.install_url,
            "needsAuth": self.needs_auth,
        }


@dataclass(frozen=True)
class AppsListResponse:
    data: tuple[AppInfo, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _dataclass_tuple(self.data, AppInfo, "data"))
        object.__setattr__(self, "next_cursor", _optional_str(self.next_cursor, "next_cursor"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppsListResponse":
        _ensure_mapping(value, "AppsListResponse")
        return cls(
            data=tuple(AppInfo.from_mapping(item) for item in _iterable(value["data"], "data")),
            next_cursor=_optional_str(_pick(value, "next_cursor", "nextCursor"), "next_cursor"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "data": [item.to_mapping() for item in self.data],
            "next_cursor": self.next_cursor,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "data": [item.to_camel_mapping() for item in self.data],
            "nextCursor": self.next_cursor,
        }


@dataclass(frozen=True)
class AppListUpdatedNotification:
    data: tuple[AppInfo, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _dataclass_tuple(self.data, AppInfo, "data"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppListUpdatedNotification":
        _ensure_mapping(value, "AppListUpdatedNotification")
        return cls(data=tuple(AppInfo.from_mapping(item) for item in _iterable(value["data"], "data")))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"data": [item.to_mapping() for item in self.data]}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"data": [item.to_camel_mapping() for item in self.data]}


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


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_bool(value: JsonValue, field_name: str) -> bool | None:
    if value is None:
        return None
    return _ensure_bool(value, field_name)


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _optional_u32(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**32 - 1:
        raise TypeError(f"{field_name} must be an unsigned 32-bit integer")
    return value


def _iterable(value: JsonValue, field_name: str) -> Iterable[JsonValue]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable")
    return value


def _string_tuple(value: JsonValue, field_name: str) -> tuple[str, ...]:
    return tuple(_ensure_str(item, f"{field_name} item") for item in _iterable(value, field_name))


def _optional_string_tuple(value: JsonValue, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _string_tuple(value, field_name)


def _optional_string_map(value: JsonValue, field_name: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return {
        _ensure_str(key, f"{field_name} key"): _ensure_str(item, f"{field_name} value")
        for key, item in value.items()
    }


def _optional_dataclass(value: JsonValue, cls: type[_T], field_name: str) -> _T | None:
    if value is None:
        return None
    if isinstance(value, cls):
        return value
    if isinstance(value, Mapping) and hasattr(cls, "from_mapping"):
        return cls.from_mapping(value)  # type: ignore[attr-defined,no-any-return]
    raise TypeError(f"{field_name} must be {cls.__name__} or mapping")


def _dataclass_tuple(value: JsonValue, cls: type[_T], field_name: str) -> tuple[_T, ...]:
    result: list[_T] = []
    for item in _iterable(value, field_name):
        coerced = _optional_dataclass(item, cls, f"{field_name} item")
        if coerced is None:
            raise TypeError(f"{field_name} item must not be None")
        result.append(coerced)
    return tuple(result)


def _optional_dataclass_tuple(value: JsonValue, cls: type[_T], field_name: str) -> tuple[_T, ...] | None:
    if value is None:
        return None
    return _dataclass_tuple(value, cls, field_name)


def deepcopy_json(value: JsonValue) -> JsonValue:
    """Return a defensive copy for callers that still need raw JSON values."""

    return copy.deepcopy(value)


__all__ = [
    "AppBranding",
    "AppInfo",
    "AppListUpdatedNotification",
    "AppMetadata",
    "AppReview",
    "AppScreenshot",
    "AppSummary",
    "AppsListParams",
    "AppsListResponse",
    "deepcopy_json",
]
