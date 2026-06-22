"""Parity checks for codex-login server.rs helper behavior."""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse

from pycodex.login.pkce import PkceCodes
from pycodex.login.server import (
    DEFAULT_ISSUER,
    ServerOptions,
    build_authorize_url,
    compose_success_url,
    ensure_workspace_allowed,
    html_escape,
    is_missing_codex_entitlement_error,
    parse_token_endpoint_error,
    redact_sensitive_query_value,
    render_login_error_page,
    sanitize_url_for_logging,
)


def _jwt(auth_claims: dict[str, object]) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode("ascii").rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"https://api.openai.com/auth": auth_claims}, separators=(",", ":")).encode()
    ).decode("ascii").rstrip("=")
    return f"{header}.{payload}.sig"


def test_server_options_new_matches_rust_defaults(tmp_path) -> None:
    # Source: codex/codex-rs/login/src/server.rs
    # Rust crate: codex-login
    # Rust module: src/server.rs
    # Contract: ServerOptions::new sets default issuer, port, and browser flags.
    opts = ServerOptions.new(tmp_path, "client", ["acct"], "file")

    assert opts.issuer == DEFAULT_ISSUER
    assert opts.port == 1455
    assert opts.open_browser is True
    assert opts.force_state is None
    assert opts.forced_chatgpt_workspace_id == ["acct"]


def test_build_authorize_url_includes_pkce_state_scope_and_workspace() -> None:
    # Source: codex/codex-rs/login/src/server.rs build_authorize_url
    pkce = PkceCodes(code_verifier="verifier", code_challenge="challenge")
    url = build_authorize_url("https://issuer.example/", "client", "http://localhost/cb", pkce, "state", ["a", "b"])
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.geturl().startswith("https://issuer.example/oauth/authorize?")
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client"]
    assert query["redirect_uri"] == ["http://localhost/cb"]
    assert query["code_challenge"] == ["challenge"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == ["state"]
    assert query["allowed_workspace_id"] == ["a,b"]


def test_parse_token_endpoint_error_matches_rust_precedence() -> None:
    # Source: codex/codex-rs/login/src/server.rs parse_token_endpoint_error tests.
    assert parse_token_endpoint_error("").display_message == "unknown error"
    detail = parse_token_endpoint_error('{"error":"invalid_grant","error_description":"expired"}')
    assert detail.error_code == "invalid_grant"
    assert detail.error_message == "expired"
    assert detail.display_message == "expired"
    nested = parse_token_endpoint_error('{"error":{"code":"proxy_auth_required","message":"proxy required"}}')
    assert nested.error_code == "proxy_auth_required"
    assert nested.display_message == "proxy required"
    assert parse_token_endpoint_error("service unavailable").display_message == "service unavailable"


def test_sensitive_url_redaction_preserves_safe_shape() -> None:
    # Source: codex/codex-rs/login/src/server.rs redaction helpers.
    assert redact_sensitive_query_value("code", "abc123") == "<redacted>"
    assert redact_sensitive_query_value("redirect_uri", "http://localhost") == "http://localhost"
    assert (
        sanitize_url_for_logging("https://user:pass@example.com/base?token=abc123&env=prod#frag")
        == "https://example.com/base?token=%3Credacted%3E&env=prod"
    )
    assert sanitize_url_for_logging("not a url") == "<invalid-url>"


def test_compose_success_url_and_workspace_restriction() -> None:
    # Source: codex/codex-rs/login/src/server.rs compose_success_url/ensure_workspace_allowed.
    id_token = _jwt(
        {
            "organization_id": "org",
            "project_id": "proj",
            "completed_platform_onboarding": False,
            "is_org_owner": True,
            "chatgpt_account_id": "acct",
        }
    )
    access_token = _jwt({"chatgpt_plan_type": "plus"})
    url = urlparse(compose_success_url(1455, DEFAULT_ISSUER, id_token, access_token, True))
    query = parse_qs(url.query)

    assert query["needs_setup"] == ["true"]
    assert query["org_id"] == ["org"]
    assert query["project_id"] == ["proj"]
    assert query["plan_type"] == ["plus"]
    assert query["codex_streamlined_login"] == ["true"]
    assert ensure_workspace_allowed(["acct"], id_token) is None
    assert ensure_workspace_allowed(["other"], id_token) == "Login is restricted to workspace id(s) other."


def test_login_error_page_escapes_dynamic_fields_and_entitlement_copy() -> None:
    # Source: codex/codex-rs/login/src/server.rs render_login_error_page tests.
    body = render_login_error_page("<bad>", "code&value", '"quoted"').decode("utf-8")
    assert html_escape("Sign-in could not be completed") in body
    assert "&lt;bad&gt;" in body
    assert "code&amp;value" in body
    assert "&quot;quoted&quot;" in body

    assert is_missing_codex_entitlement_error("access_denied", "missing_codex_entitlement")
    entitlement = render_login_error_page("access denied", "access_denied", "missing_codex_entitlement").decode("utf-8")
    assert "You do not have access to Codex" in entitlement
    assert "Contact your workspace administrator" in entitlement
    assert "missing_codex_entitlement" not in entitlement
