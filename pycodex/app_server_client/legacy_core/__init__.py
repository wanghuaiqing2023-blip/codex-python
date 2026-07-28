"""Transitional re-exports owned by Rust ``legacy_core``."""

from pycodex.core.agents_md import DEFAULT_AGENTS_MD_FILENAME, LOCAL_AGENTS_MD_FILENAME
from pycodex.core.exec_policy import (
    check_execpolicy_for_warnings,
    format_exec_policy_error_with_source,
)
from pycodex.core.mcp import McpManager
from pycodex.core.web_search import web_search_detail
from pycodex.core.windows_sandbox_read_grants import grant_read_root_non_elevated

from . import (
    config,
    connectors,
    otel_init,
    personality_migration,
    review_format,
    review_prompts,
    test_support,
    util,
    windows_sandbox,
)

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
