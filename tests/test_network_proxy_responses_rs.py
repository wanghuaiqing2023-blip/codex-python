from pycodex.network_proxy import (
    NetworkDecisionSource,
    NetworkPolicyDecision,
    NetworkProtocol,
    PolicyDecisionDetails,
    REASON_DENIED,
    REASON_METHOD_NOT_ALLOWED,
    REASON_MITM_HOOK_DENIED,
    REASON_MITM_REQUIRED,
    REASON_NOT_ALLOWED,
    REASON_NOT_ALLOWED_LOCAL,
    REASON_PROXY_DISABLED,
    blocked_header_value,
    blocked_message,
    blocked_message_with_policy,
    blocked_text_response,
    blocked_text_response_with_policy,
    json_response,
    text_response,
)


def details(reason: str = REASON_NOT_ALLOWED) -> PolicyDecisionDetails:
    return PolicyDecisionDetails(
        decision=NetworkPolicyDecision.ASK,
        reason=reason,
        source=NetworkDecisionSource.DECIDER,
        protocol=NetworkProtocol.HTTPS_CONNECT,
        host="api.example.com",
        port=443,
    )


def test_blocked_message_with_policy_returns_human_message() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/responses.rs
    # Rust test: blocked_message_with_policy_returns_human_message
    # Contract: policy details do not alter the stable human message for the reason.
    assert blocked_message_with_policy(REASON_NOT_ALLOWED, details()) == "Domain not in allowlist."


def test_blocked_header_value_maps_reason_categories() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/responses.rs
    # Rust item: blocked_header_value
    # Contract: x-proxy-error header values are stable reason categories.
    assert blocked_header_value(REASON_NOT_ALLOWED) == "blocked-by-allowlist"
    assert blocked_header_value(REASON_NOT_ALLOWED_LOCAL) == "blocked-by-allowlist"
    assert blocked_header_value(REASON_DENIED) == "blocked-by-denylist"
    assert blocked_header_value(REASON_METHOD_NOT_ALLOWED) == "blocked-by-method-policy"
    assert blocked_header_value(REASON_MITM_HOOK_DENIED) == "blocked-by-mitm-hook"
    assert blocked_header_value(REASON_MITM_REQUIRED) == "blocked-by-mitm-required"
    assert blocked_header_value("unknown") == "blocked-by-policy"


def test_blocked_message_maps_reason_text() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/responses.rs
    # Rust item: blocked_message
    # Contract: blocked body messages match Rust text exactly.
    assert blocked_message(REASON_NOT_ALLOWED) == "Domain not in allowlist."
    assert (
        blocked_message(REASON_NOT_ALLOWED_LOCAL)
        == "Sandbox policy blocks local/private network addresses."
    )
    assert blocked_message(REASON_DENIED) == "Domain denied by the sandbox policy."
    assert blocked_message(REASON_METHOD_NOT_ALLOWED) == "Method not allowed in limited mode."
    assert (
        blocked_message(REASON_MITM_HOOK_DENIED)
        == "HTTPS request denied by MITM hook policy."
    )
    assert blocked_message(REASON_MITM_REQUIRED) == "MITM required for limited HTTPS."
    assert blocked_message(REASON_PROXY_DISABLED) == "network proxy is disabled"
    assert blocked_message("unknown") == "Request blocked by network policy."


def test_blocked_text_response_shape_matches_rust() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/responses.rs
    # Rust items: blocked_text_response, blocked_text_response_with_policy
    # Contract: blocked responses are 403 text/plain with x-proxy-error and stable body text.
    response = blocked_text_response(REASON_METHOD_NOT_ALLOWED)
    assert response.status == 403
    assert response.headers == {
        "content-type": "text/plain",
        "x-proxy-error": "blocked-by-method-policy",
    }
    assert response.body == "Method not allowed in limited mode."

    with_policy = blocked_text_response_with_policy(REASON_NOT_ALLOWED, details())
    assert with_policy.status == 403
    assert with_policy.headers["content-type"] == "text/plain"
    assert with_policy.headers["x-proxy-error"] == "blocked-by-allowlist"
    assert with_policy.body == "Domain not in allowlist."


def test_text_and_json_response_shape_matches_rust_helpers() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/responses.rs
    # Rust items: text_response, json_response
    # Contract: helper responses set the Rust status/content-type/body shape.
    text = text_response(201, "created")
    assert text.status == 201
    assert text.headers == {"content-type": "text/plain"}
    assert text.body == "created"

    json = json_response({"ok": True, "items": [1, 2]})
    assert json.status == 200
    assert json.headers == {"content-type": "application/json"}
    assert json.body == '{"ok":true,"items":[1,2]}'

    fallback = json_response({"bad": object()})
    assert fallback.status == 200
    assert fallback.body == "{}"
