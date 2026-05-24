"""MCP approval metadata keys.

Ported from ``codex/codex-rs/protocol/src/mcp_approval_meta.rs``.
"""

APPROVAL_KIND_KEY = "codex_approval_kind"
APPROVAL_KIND_MCP_TOOL_CALL = "mcp_tool_call"
APPROVAL_KIND_TOOL_SUGGESTION = "tool_suggestion"
REQUEST_TYPE_KEY = "codex_request_type"
REQUEST_TYPE_APPROVAL_REQUEST = "approval_request"
APPROVALS_REVIEWER_KEY = "approvals_reviewer"
PERSIST_KEY = "persist"
PERSIST_SESSION = "session"
PERSIST_ALWAYS = "always"
SOURCE_KEY = "source"
SOURCE_CONNECTOR = "connector"
CONNECTOR_ID_KEY = "connector_id"
CONNECTOR_NAME_KEY = "connector_name"
CONNECTOR_DESCRIPTION_KEY = "connector_description"
TOOL_NAME_KEY = "tool_name"
TOOL_TITLE_KEY = "tool_title"
TOOL_DESCRIPTION_KEY = "tool_description"
TOOL_PARAMS_KEY = "tool_params"
TOOL_PARAMS_DISPLAY_KEY = "tool_params_display"
