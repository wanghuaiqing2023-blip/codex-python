# pycodex.network_proxy

Rust crate: `codex-network-proxy`
Rust path: `codex/codex-rs/network-proxy`

This package carries dependency-light Python projections of the network proxy
configuration and policy helpers used by core configuration and sandbox
startup paths.

## Module Coverage

| Rust module | Python surface | Status | Notes |
|---|---|---|---|
| `src/config.rs` | `pycodex.network_proxy` | complete | Rust defaults, domain permission precedence, unix socket allowlist validation, proxy address display, runtime bind-address resolution, and loopback clamping are covered by Rust-derived tests. |
| `src/state.rs` | `pycodex.network_proxy` | complete | Constraint/state dataclasses, `NetworkProxyConstraintError`, `build_config_state`, and `validate_policy_against_constraints` are covered by Rust-derived tests for managed boolean, mode, domain, wildcard, global allow/deny wildcard runtime-state construction, and unix-socket restrictions. |
| `src/runtime.rs` | `pycodex.network_proxy` | complete | Lightweight `NetworkProxySpec`, static reloader, config-state building, `HostBlockDecision`/`HostBlockReason`, dependency-light host policy checks including deny-over-allow precedence, allowlist-match requirements, wildcard apex behavior, local/private literal guards, exact scoped IPv6 allow/deny handling, blocked-request buffer/log-line behavior, DNS/private-address fail-closed guard behavior, dynamic allow/deny domain mutation, runtime config accessors, mode updates, unix-socket allowlist checks, and reload-on-demand/force-reload state replacement are covered. |
| `src/policy.rs` | `pycodex.network_proxy` | complete | Host normalization, loopback/private IP classification, network mode method checks, global wildcard detection, invalid glob rejection, dedupe behavior, case-insensitive glob matching, and allow/deny domain pattern matching are covered by Rust-derived tests. |
| `src/network_policy.rs` | `pycodex.network_proxy`, `pycodex.protocol.network_policy` | complete | Request/decision enums, decider mapping, domain/non-domain audit event field projection, metadata/default fields, and NotAllowed decider override behavior are covered by Rust-derived tests. |
| `src/reasons.rs` | `pycodex.network_proxy` | complete | Stable `REASON_*` strings and `HostBlockReason.as_str()` projections are covered by source-derived tests. |
| `src/responses.rs` | `pycodex.network_proxy` | complete | Text/JSON response helpers, blocked reason categories, human messages, and with-policy wrappers are covered by Rust-derived/source-derived tests. |
| `src/connect_policy.rs` | `pycodex.network_proxy` | complete | Dependency-light `TargetCheckedTcpConnector` projection covers direct target non-public IP rejection, allow-local-binding state/config policy, and proxy-address bypass semantics with Rust-derived tests. |
| `src/upstream.rs` | `pycodex.network_proxy` | complete | Dependency-light `ProxyConfig`, proxy env parsing, CONNECT proxy selection, upstream route projection, and `UpstreamClient` constructor semantics are covered by source-derived tests. |
| `src/http_proxy.rs` | `pycodex.network_proxy` | complete | Absolute-form Host header validation, hop-by-hop request-header stripping, `json_blocked`/`BlockedResponse` optional-field serialization, dependency-light CONNECT accept policy, a live stdlib HTTP/1 CONNECT listener/direct-tunnel/upstream-proxy route slice, plain HTTP unix-socket method/platform/allowlist preflight, plain HTTP host/policy/method preflight, and live stdlib plain HTTP direct/upstream-proxy forwarding are covered by Rust-derived/source-derived tests. |
| `src/proxy.rs` | `pycodex.network_proxy` | complete | Proxy env key lookup/detection, managed proxy environment overrides including macOS Codex-marked `GIT_SSH_COMMAND` preservation/refresh behavior, Windows loopback bind clamping, busy-port fallback listener reservation, builder address selection, runtime settings replacement guards, env application, stdlib HTTP/SOCKS task startup from reserved listeners, handle wait/shutdown semantics, and drop-time unfinished task cancellation are covered by Rust-derived/source-derived tests. |
| `src/mitm_hook.rs` | `pycodex.network_proxy` | complete | Dependency-light hook config validation, env/file secret resolution, path/query/header matcher compilation, literal/pattern prefixes, and request evaluation are covered by Rust-derived tests. |
| `src/mitm.rs` | `pycodex.network_proxy` | complete | MITM policy blocking, method clamp, host mismatch, local/private recheck, hook match/miss behavior, blocked telemetry, hook action header replacement, and request Host/authority/URI/path helper contracts are covered by Rust-derived/source-derived tests. |
| `src/socks5.rs` | `pycodex.network_proxy` | complete | Dependency-light SOCKS5 TCP/UDP policy inspection covers proxy-disabled, limited-mode, MITM-required, blocked telemetry, and non-domain audit event behavior from Rust tests. The stdlib SOCKS5 TCP no-auth CONNECT listener/relay and UDP ASSOCIATE/relay slices are covered by real local socket tests. |
| `src/certs.rs` | `pycodex.network_proxy` | complete | Managed MITM CA path shape, Unix key-file validation, and atomic create-new file persistence are covered by Rust-derived/source-derived tests. |

## Native Runtime Differences

The Python port intentionally does not embed Rust's Rama, rustls, Tokio `JoinHandle`, native MITM TLS termination, or real CA/host certificate generation stack. Those are non-blocking implementation differences for the dependency-light port. The stable policy/config/runtime/helper behavior and live stdlib HTTP/SOCKS socket slices are covered by Rust-derived tests, including real local socket relay tests.

`codex-network-proxy` is `complete` for the dependency-light Python projection.

## Tests

- `tests/test_network_proxy_config_rs.py`
- `tests/test_network_proxy_state_rs.py`
- `tests/test_network_proxy_policy_rs.py`
- `tests/test_network_proxy_network_policy_rs.py`
- `tests/test_network_proxy_reasons_rs.py`
- `tests/test_network_proxy_responses_rs.py`
- `tests/test_network_proxy_connect_policy_rs.py`
- `tests/test_network_proxy_upstream_rs.py`
- `tests/test_network_proxy_runtime_blocked_rs.py`
- `tests/test_network_proxy_runtime_dns_rs.py`
- `tests/test_network_proxy_runtime_domains_rs.py`
- `tests/test_network_proxy_runtime_accessors_rs.py`
- `tests/test_network_proxy_runtime_reload_rs.py`
- `tests/test_network_proxy_http_proxy_rs.py`
- `tests/test_network_proxy_proxy_rs.py`
- `tests/test_network_proxy_mitm_hook_rs.py`
- `tests/test_network_proxy_mitm_rs.py`
- `tests/test_network_proxy_socks5_rs.py`
- `tests/test_network_proxy_certs_rs.py`
- Existing core integration coverage in `tests/test_core_network_proxy_loader.py`,
  `tests/test_config_permissions_toml.py`, and `tests/test_core_config_permissions.py`.
