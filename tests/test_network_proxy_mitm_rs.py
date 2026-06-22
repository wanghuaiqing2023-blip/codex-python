from __future__ import annotations

import asyncio
from pathlib import Path

from pycodex.network_proxy import (
    ConfigState,
    InjectedHeaderConfig,
    MitmHook,
    MitmHookActions,
    MitmHookActionsConfig,
    MitmHookConfig,
    MitmHookMatchConfig,
    MitmPolicyContext,
    NetworkMode,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyState,
    REASON_METHOD_NOT_ALLOWED,
    REASON_MITM_HOOK_DENIED,
    REASON_NOT_ALLOWED_LOCAL,
    ResolvedInjectedHeader,
    SecretSource,
    StaticNetworkProxyReloader,
    apply_mitm_hook_actions,
    authority_header_value,
    build_https_uri,
    extract_request_host,
    mitm_blocking_response,
    path_and_query,
    path_for_log,
)


def github_write_hook() -> MitmHookConfig:
    return MitmHookConfig(
        host="api.github.com",
        matcher=MitmHookMatchConfig(
            methods=["POST", "PUT"],
            path_prefixes=["/repos/openai/"],
        ),
        actions=MitmHookActionsConfig(
            strip_request_headers=["authorization"],
            inject_request_headers=[
                InjectedHeaderConfig(
                    name="authorization",
                    secret_env_var="CODEX_GITHUB_TOKEN",
                    prefix="Bearer ",
                )
            ],
        ),
    )


def network_proxy_state_for_policy(config: NetworkProxyConfig) -> NetworkProxyState:
    state = ConfigState(config, NetworkProxyConstraints())
    async def public_dns_lookup(_host: str, _port: int):
        return [("8.8.8.8", 443)]

    return NetworkProxyState(
        state,
        StaticNetworkProxyReloader(state),
        dns_lookup=public_dns_lookup,
    )


def policy_ctx(
    app_state: NetworkProxyState,
    mode: NetworkMode,
    target_host: str,
    target_port: int,
) -> MitmPolicyContext:
    return MitmPolicyContext(
        target_host=target_host,
        target_port=target_port,
        mode=mode,
        app_state=app_state,
    )


def request(method: str, uri: str, headers: dict[str, str] | None = None) -> dict[str, object]:
    return {"method": method, "uri": uri, "headers": headers or {}}


def test_mitm_request_host_prefers_host_header_then_uri_authority() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/mitm.rs
    # Rust item: extract_request_host
    # Contract: MITM host extraction uses the Host header when it is valid, otherwise falls back to URI authority.
    assert (
        extract_request_host(request("GET", "https://uri.example/v1", {"host": "header.example"}))
        == "header.example"
    )
    assert extract_request_host(request("GET", "https://uri.example/v1")) == "uri.example"
    assert extract_request_host(request("GET", "/v1/responses")) is None


def test_mitm_authority_header_value_formats_default_port_and_ipv6() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/mitm.rs
    # Rust item: authority_header_value
    # Contract: Host header / URI authority formatting omits default HTTPS port and brackets IPv6 literals.
    assert authority_header_value("api.example.com", 443) == "api.example.com"
    assert authority_header_value("api.example.com", 8443) == "api.example.com:8443"
    assert authority_header_value("2001:db8::1", 443) == "[2001:db8::1]"
    assert authority_header_value("2001:db8::1", 8443) == "[2001:db8::1]:8443"


def test_mitm_build_https_uri_and_path_helpers_match_rust_source_contract() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/mitm.rs
    # Rust items: build_https_uri, path_and_query, path_for_log
    # Contract: forwarded MITM requests rebuild an HTTPS URI with path+query, while log paths drop the query.
    uri = build_https_uri("api.example.com:8443", "/v1/responses?api_key=secret")

    assert uri == "https://api.example.com:8443/v1/responses?api_key=secret"
    assert path_and_query(uri) == "/v1/responses?api_key=secret"
    assert path_for_log(uri) == "/v1/responses"
    assert path_and_query("https://api.example.com") == "/"
    assert path_for_log("https://api.example.com?token=secret") == "/"


def test_mitm_policy_blocks_disallowed_method_and_records_telemetry() -> None:
    # Rust: codex-network-proxy/src/mitm_tests.rs::mitm_policy_blocks_disallowed_method_and_records_telemetry.
    config = NetworkProxyConfig()
    config.network.set_allowed_domains(["example.com"])
    app_state = network_proxy_state_for_policy(config)
    ctx = policy_ctx(app_state, NetworkMode.LIMITED, "example.com", 443)

    response = asyncio.run(
        mitm_blocking_response(
            request("POST", "/v1/responses?api_key=secret", {"host": "example.com"}),
            ctx,
        )
    )

    assert response is not None
    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-method-policy"
    blocked = asyncio.run(app_state.drain_blocked())
    assert len(blocked) == 1
    assert blocked[0].reason == REASON_METHOD_NOT_ALLOWED
    assert blocked[0].method == "POST"
    assert blocked[0].host == "example.com"
    assert blocked[0].port == 443


def test_mitm_policy_rejects_host_mismatch() -> None:
    # Rust: mitm_tests.rs::mitm_policy_rejects_host_mismatch.
    config = NetworkProxyConfig()
    config.network.set_allowed_domains(["example.com"])
    app_state = network_proxy_state_for_policy(config)
    ctx = policy_ctx(app_state, NetworkMode.FULL, "example.com", 443)

    response = asyncio.run(mitm_blocking_response(request("GET", "/", {"host": "evil.example"}), ctx))

    assert response is not None
    assert response.status == 400
    assert asyncio.run(app_state.blocked_snapshot()) == []


def test_mitm_policy_rechecks_local_private_target_after_connect() -> None:
    # Rust: mitm_tests.rs::mitm_policy_rechecks_local_private_target_after_connect.
    config = NetworkProxyConfig()
    config.network.set_allowed_domains(["example.com"])
    config.network.allow_local_binding = False
    app_state = network_proxy_state_for_policy(config)
    ctx = policy_ctx(app_state, NetworkMode.FULL, "10.0.0.1", 443)

    response = asyncio.run(
        mitm_blocking_response(
            request("GET", "/health?token=secret", {"host": "10.0.0.1"}),
            ctx,
        )
    )

    assert response is not None
    assert response.status == 403
    blocked = asyncio.run(app_state.drain_blocked())
    assert len(blocked) == 1
    assert blocked[0].reason == REASON_NOT_ALLOWED_LOCAL
    assert blocked[0].host == "10.0.0.1"
    assert blocked[0].port == 443


def test_mitm_policy_allows_matching_hooked_write_in_full_mode(tmp_path: Path) -> None:
    # Rust: mitm_tests.rs::mitm_policy_allows_matching_hooked_write_in_full_mode.
    secret_file = tmp_path / "github-token"
    secret_file.write_text("ghp-secret\n", encoding="utf-8")
    hook = github_write_hook()
    hook.actions.inject_request_headers[0] = InjectedHeaderConfig(
        name="authorization",
        secret_file=str(secret_file),
        prefix="Bearer ",
    )
    config = NetworkProxyConfig()
    config.network.mitm = True
    config.network.mitm_hooks = [hook]
    config.network.mode = NetworkMode.FULL
    config.network.set_allowed_domains(["api.github.com"])
    app_state = network_proxy_state_for_policy(config)
    ctx = policy_ctx(app_state, NetworkMode.FULL, "api.github.com", 443)

    response = asyncio.run(
        mitm_blocking_response(
            request("POST", "/repos/openai/codex/issues", {"host": "api.github.com"}),
            ctx,
        )
    )

    assert response is None
    assert asyncio.run(app_state.blocked_snapshot()) == []


def test_mitm_policy_blocks_matching_hooked_write_in_limited_mode() -> None:
    # Rust: mitm_tests.rs::mitm_policy_blocks_matching_hooked_write_in_limited_mode.
    hook = github_write_hook()
    hook.actions.inject_request_headers.clear()
    config = NetworkProxyConfig()
    config.network.mitm = True
    config.network.mitm_hooks = [hook]
    config.network.mode = NetworkMode.LIMITED
    config.network.set_allowed_domains(["api.github.com"])
    app_state = network_proxy_state_for_policy(config)
    ctx = policy_ctx(app_state, NetworkMode.LIMITED, "api.github.com", 443)

    response = asyncio.run(
        mitm_blocking_response(
            request("POST", "/repos/openai/codex/issues", {"host": "api.github.com"}),
            ctx,
        )
    )

    assert response is not None
    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-method-policy"
    blocked = asyncio.run(app_state.drain_blocked())
    assert len(blocked) == 1
    assert blocked[0].reason == REASON_METHOD_NOT_ALLOWED
    assert blocked[0].method == "POST"
    assert blocked[0].host == "api.github.com"
    assert blocked[0].port == 443


def test_mitm_policy_blocks_hook_miss_for_hooked_host_and_records_telemetry_in_full_mode(tmp_path: Path) -> None:
    # Rust: mitm_tests.rs::mitm_policy_blocks_hook_miss_for_hooked_host_and_records_telemetry_in_full_mode.
    secret_file = tmp_path / "github-token"
    secret_file.write_text("ghp-secret\n", encoding="utf-8")
    hook = github_write_hook()
    hook.actions.inject_request_headers[0] = InjectedHeaderConfig(
        name="authorization",
        secret_file=str(secret_file),
        prefix="Bearer ",
    )
    config = NetworkProxyConfig()
    config.network.mitm = True
    config.network.mitm_hooks = [hook]
    config.network.mode = NetworkMode.FULL
    config.network.set_allowed_domains(["api.github.com"])
    app_state = network_proxy_state_for_policy(config)
    ctx = policy_ctx(app_state, NetworkMode.FULL, "api.github.com", 443)

    response = asyncio.run(
        mitm_blocking_response(
            request(
                "GET",
                "/repos/openai/codex/issues?token=secret",
                {"host": "api.github.com", "authorization": "Bearer user-supplied"},
            ),
            ctx,
        )
    )

    assert response is not None
    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-mitm-hook"
    blocked = asyncio.run(app_state.drain_blocked())
    assert len(blocked) == 1
    assert blocked[0].reason == REASON_MITM_HOOK_DENIED
    assert blocked[0].method == "GET"
    assert blocked[0].host == "api.github.com"
    assert blocked[0].port == 443


def test_apply_mitm_hook_actions_replaces_authorization_header() -> None:
    # Rust: mitm_tests.rs::apply_mitm_hook_actions_replaces_authorization_header.
    headers = {
        "authorization": "Bearer user-supplied",
        "x-request-id": "req_123",
    }
    actions = MitmHookActions(
        strip_request_headers=("authorization",),
        inject_request_headers=(
            ResolvedInjectedHeader(
                name="authorization",
                value="Bearer secret-token",
                source=SecretSource.file("/tmp/github-token"),
            ),
        ),
    )

    apply_mitm_hook_actions(headers, actions)

    assert headers["authorization"] == "Bearer secret-token"
    assert headers["x-request-id"] == "req_123"
