"""List-available-plugins-to-install handler facade.

Rust source:
``codex/codex-rs/core/src/tools/handlers/list_available_plugins_to_install.rs``.

The Python implementation shares the request-plugin-install flow module because
Rust's list and request handlers operate over the same discoverable-tool data
contracts.
"""

from __future__ import annotations

from .request_plugin_install import (
    MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS,
    ListAvailablePluginsToInstallHandler,
    create_list_available_plugins_to_install_tool,
)

__all__ = [
    "MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS",
    "ListAvailablePluginsToInstallHandler",
    "create_list_available_plugins_to_install_tool",
]
