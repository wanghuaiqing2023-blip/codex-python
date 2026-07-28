"""Port of ``codex-config/src/loader/macos.rs``."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping

from .. import toml_compat as _toml
from ..config_requirements import ConfigRequirementsToml
from ..config_requirements import ConfigRequirementsWithSources
from ..config_toml import ConfigToml
from ..constraint import RequirementSource


MANAGED_PREFERENCES_APPLICATION_ID = "com.openai.codex"
MANAGED_PREFERENCES_CONFIG_KEY = "config_toml_base64"
MANAGED_PREFERENCES_REQUIREMENTS_KEY = "requirements_toml_base64"


def managed_config_from_mdm_raw_toml(
    raw_toml: str | None,
    *,
    strict_config: bool = False,
):
    from .layer_io import ManagedConfigFromMdm

    if raw_toml is None or not raw_toml.strip():
        return None
    parsed = _toml.loads(raw_toml)
    if not isinstance(parsed, Mapping):
        raise TypeError("managed preferences config must contain a TOML table")
    if strict_config:
        ConfigToml.from_mapping(parsed)
    return ManagedConfigFromMdm(parsed, raw_toml)


def managed_config_from_mdm_base64(
    encoded: str | None,
    *,
    strict_config: bool = False,
):
    if encoded is None or not encoded.strip():
        return None
    try:
        raw_toml = base64.b64decode(
            encoded.encode("ascii"),
            validate=True,
        ).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(
            "managed preferences config must be base64-encoded UTF-8 TOML"
        ) from exc
    return managed_config_from_mdm_raw_toml(
        raw_toml,
        strict_config=strict_config,
    )


def managed_preferences_requirements_source() -> RequirementSource:
    return RequirementSource.mdm_managed_preferences(
        MANAGED_PREFERENCES_APPLICATION_ID,
        MANAGED_PREFERENCES_REQUIREMENTS_KEY,
    )


def managed_requirements_from_mdm_base64(
    encoded: str | None,
) -> ConfigRequirementsToml | None:
    if encoded is None or not encoded.strip():
        return None
    try:
        raw_toml = base64.b64decode(
            encoded.strip().encode("ascii"),
            validate=True,
        ).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(
            "managed requirements must be base64-encoded UTF-8 TOML"
        ) from exc
    return ConfigRequirementsToml.from_toml(raw_toml)


def load_managed_admin_requirements_toml(
    target: ConfigRequirementsWithSources,
    override_base64: str | None = None,
    *,
    hostname: str | None = None,
) -> None:
    from . import merge_requirements_with_remote_sandbox_config

    requirements = managed_requirements_from_mdm_base64(override_base64)
    if requirements is None:
        return
    merge_requirements_with_remote_sandbox_config(
        target,
        managed_preferences_requirements_source(),
        requirements,
        hostname=hostname,
    )


__all__ = [
    "MANAGED_PREFERENCES_APPLICATION_ID",
    "MANAGED_PREFERENCES_CONFIG_KEY",
    "MANAGED_PREFERENCES_REQUIREMENTS_KEY",
    "load_managed_admin_requirements_toml",
    "managed_config_from_mdm_base64",
    "managed_config_from_mdm_raw_toml",
    "managed_preferences_requirements_source",
    "managed_requirements_from_mdm_base64",
]
