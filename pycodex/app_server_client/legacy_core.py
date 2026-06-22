"""Compatibility re-exports for Rust ``codex-app-server-client::legacy_core``.

The Rust crate exposes this nested module as a transitional bridge while
callers migrate from direct ``codex-core`` imports to app-server protocol APIs.
Python mirrors that boundary by re-exporting already-ported ``pycodex.core``
helpers instead of duplicating implementations in ``app_server_client``.
"""

from __future__ import annotations

from pycodex.core import config, connectors, otel_init, personality_migration
from pycodex.core import review_format, review_prompts, test_support, util
from pycodex.core import windows_sandbox
from pycodex.core.agents_md import DEFAULT_AGENTS_MD_FILENAME, LOCAL_AGENTS_MD_FILENAME
from pycodex.core.exec_policy import (
    check_execpolicy_for_warnings,
    format_exec_policy_error_with_source,
)
from pycodex.core.mcp import McpManager
from pycodex.core.web_search import web_search_detail
from pycodex.core.windows_sandbox_read_grants import grant_read_root_non_elevated

__all__ = [
    "DEFAULT_AGENTS_MD_FILENAME",
    "LOCAL_AGENTS_MD_FILENAME",
    "McpManager",
    "check_execpolicy_for_warnings",
    "config",
    "connectors",
    "format_exec_policy_error_with_source",
    "grant_read_root_non_elevated",
    "otel_init",
    "personality_migration",
    "review_format",
    "review_prompts",
    "test_support",
    "util",
    "web_search_detail",
    "windows_sandbox",
]
