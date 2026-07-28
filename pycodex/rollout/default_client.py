"""Rust-aligned re-export for ``codex-rollout::default_client``."""

from pycodex.login.auth.default_client import (
    CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR,
    DEFAULT_ORIGINATOR,
    RESIDENCY_HEADER_NAME,
    USER_AGENT_HEADER_NAME,
    CodexHttpClient,
    CodexRequestBuilder,
    Originator,
    ResidencyRequirement,
    SetOriginatorError,
    build_reqwest_client,
    create_client,
    default_headers,
    get_codex_user_agent,
    is_first_party_chat_originator,
    is_first_party_originator,
    is_sandboxed,
    originator,
    sanitize_user_agent,
    set_default_client_residency_requirement,
    set_default_originator,
    set_user_agent_suffix,
    try_build_reqwest_client,
)

__all__ = [name for name in globals() if not name.startswith("_")]
