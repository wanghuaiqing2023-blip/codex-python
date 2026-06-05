"""Connector helpers aligned with Rust ``codex-rs/connectors``."""

from .accessible import AccessibleConnectorTool, collect_accessible_connectors
from .merge import (
    merge_connectors,
    merge_plugin_connectors,
    merge_plugin_connectors_with_accessible,
    plugin_connector_to_app_info,
)
from .metadata import (
    coerce_app_info,
    connector_install_url,
    connector_name_slug,
    normalize_connector_value,
    replace_app_info,
    sanitize_name,
    sort_connectors_by_accessibility_and_name,
)

__all__ = [
    "AccessibleConnectorTool",
    "coerce_app_info",
    "collect_accessible_connectors",
    "connector_install_url",
    "connector_name_slug",
    "merge_connectors",
    "merge_plugin_connectors",
    "merge_plugin_connectors_with_accessible",
    "normalize_connector_value",
    "plugin_connector_to_app_info",
    "replace_app_info",
    "sanitize_name",
    "sort_connectors_by_accessibility_and_name",
]
