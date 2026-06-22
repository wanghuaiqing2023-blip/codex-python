import pytest

from pycodex.network_proxy import (
    Host,
    NetworkMode,
    compile_allowlist_globset,
    compile_denylist_globset,
    is_global_wildcard_domain_pattern,
    is_loopback_host,
    is_non_public_ip,
    normalize_host,
)


def test_method_allowed_full_allows_everything() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: method_allowed_full_allows_everything
    # Contract: full mode allows any HTTP method token.
    assert NetworkMode.FULL.allows_method("GET")
    assert NetworkMode.FULL.allows_method("POST")
    assert NetworkMode.FULL.allows_method("CONNECT")


def test_method_allowed_limited_allows_only_safe_methods() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: method_allowed_limited_allows_only_safe_methods
    # Contract: limited mode allows only GET/HEAD/OPTIONS.
    assert NetworkMode.LIMITED.allows_method("GET")
    assert NetworkMode.LIMITED.allows_method("HEAD")
    assert NetworkMode.LIMITED.allows_method("OPTIONS")
    assert not NetworkMode.LIMITED.allows_method("POST")
    assert not NetworkMode.LIMITED.allows_method("CONNECT")


def test_compile_globset_normalizes_trailing_dots() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: compile_globset_normalizes_trailing_dots
    # Contract: exact domain patterns normalize case and trailing dot.
    set_ = compile_denylist_globset(["Example.COM."])

    assert set_.is_match("example.com")
    assert not set_.is_match("api.example.com")


def test_compile_globset_normalizes_wildcards() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: compile_globset_normalizes_wildcards
    # Contract: `*.domain` matches strict subdomains but not the apex.
    set_ = compile_denylist_globset(["*.Example.COM."])

    assert set_.is_match("api.example.com")
    assert not set_.is_match("example.com")


def test_compile_globset_supports_mid_label_wildcards() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: compile_globset_supports_mid_label_wildcards
    # Contract: mid-label `*` is a normal glob wildcard inside one host label sequence.
    set_ = compile_denylist_globset(["region*.v2.argotunnel.com"])

    assert set_.is_match("region1.v2.argotunnel.com")
    assert set_.is_match("region.v2.argotunnel.com")
    assert not set_.is_match("xregion1.v2.argotunnel.com")
    assert not set_.is_match("foo.region1.v2.argotunnel.com")


def test_compile_globset_normalizes_apex_and_subdomains() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: compile_globset_normalizes_apex_and_subdomains
    # Contract: `**.domain` matches apex and strict subdomains.
    set_ = compile_denylist_globset(["**.Example.COM."])

    assert set_.is_match("example.com")
    assert set_.is_match("api.example.com")


def test_compile_globset_normalizes_bracketed_ipv6_literals() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: compile_globset_normalizes_bracketed_ipv6_literals
    # Contract: bracketed IPv6 literal patterns match unbracketed hosts.
    set_ = compile_denylist_globset(["[::1]"])

    assert set_.is_match("::1")


def test_compile_globset_preserves_scoped_ipv6_literals() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: compile_globset_preserves_scoped_ipv6_literals
    # Contract: IPv6 scope IDs normalize `%25` to `%` and remain exact.
    set_ = compile_denylist_globset(["[fe80::1%25lo0]"])

    assert set_.is_match("fe80::1%lo0")
    assert not set_.is_match("fe80::1%lo1")
    assert not set_.is_match("fe80::1")


def test_is_loopback_host_handles_localhost_variants() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: is_loopback_host_handles_localhost_variants
    # Contract: localhost is normalized case-insensitively and accepts a trailing dot.
    assert is_loopback_host(Host.parse("localhost"))
    assert is_loopback_host(Host.parse("localhost."))
    assert is_loopback_host(Host.parse("LOCALHOST"))
    assert not is_loopback_host(Host.parse("notlocalhost"))


def test_is_loopback_host_handles_ip_literals() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: is_loopback_host_handles_ip_literals
    # Contract: loopback IP literals are recognized after host normalization.
    assert is_loopback_host(Host.parse("127.0.0.1"))
    assert is_loopback_host(Host.parse("::1"))
    assert not is_loopback_host(Host.parse("1.2.3.4"))


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.0.1",
        "100.64.0.1",
        "192.0.0.1",
        "192.0.2.1",
        "198.18.0.1",
        "198.51.100.1",
        "203.0.113.1",
        "240.0.0.1",
        "0.1.2.3",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
    ],
)
def test_is_non_public_ip_rejects_private_loopback_and_reserved_ranges(ip: str) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: is_non_public_ip_rejects_private_and_loopback_ranges
    # Contract: SSRF-sensitive private, loopback, reserved, test, and mapped ranges are non-public.
    assert is_non_public_ip(ip)


def test_is_non_public_ip_allows_public_ranges() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust test: is_non_public_ip_rejects_private_and_loopback_ranges
    # Contract: public IPv4 and IPv4-mapped IPv6 literals are allowed.
    assert not is_non_public_ip("8.8.8.8")
    assert not is_non_public_ip("::ffff:8.8.8.8")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  ExAmPlE.CoM  ", "example.com"),
        ("example.com:1234", "example.com"),
        ("2001:db8::1", "2001:db8::1"),
        ("example.com.", "example.com"),
        ("ExAmPlE.CoM.", "example.com"),
        ("example.com.:443", "example.com"),
        ("[::1]", "::1"),
        ("[::1]:443", "::1"),
        ("fe80::1%lo0", "fe80::1%lo0"),
        ("[fe80::1%lo0]", "fe80::1%lo0"),
        ("[fe80::1%25lo0]", "fe80::1%lo0"),
    ],
)
def test_normalize_host_matches_rust_policy_cases(value: str, expected: str) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust tests: normalize_host_*
    # Contract: host fragments are normalized for policy matching.
    assert normalize_host(value) == expected


def test_compile_denylist_rejects_global_wildcard_but_allowlist_accepts_it() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/policy.rs
    # Rust items: compile_allowlist_globset, compile_denylist_globset, is_global_wildcard_domain_pattern
    # Contract: global wildcards are allowed only for allowlist compilation.
    assert is_global_wildcard_domain_pattern("*")
    with pytest.raises(ValueError, match="unsupported global wildcard"):
        compile_denylist_globset(["*"])

    assert compile_allowlist_globset(["*"]).is_match("anything.example")


def test_runtime_compile_globset_is_case_insensitive() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: compile_globset_is_case_insensitive
    # Contract: compiled domain globsets match candidate hosts case-insensitively.
    set_ = compile_denylist_globset(["ExAmPle.CoM"])

    assert set_.is_match("example.com")
    assert set_.is_match("EXAMPLE.COM")


def test_runtime_compile_globset_wildcard_boundaries() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust tests: compile_globset_excludes_apex_for_subdomain_patterns,
    # compile_globset_includes_apex_for_double_wildcard_patterns
    # Contract: "*.domain" excludes apex while "**.domain" includes apex and subdomains.
    subdomain_only = compile_denylist_globset(["*.openai.com"])
    apex_and_subdomain = compile_denylist_globset(["**.openai.com"])

    assert subdomain_only.is_match("api.openai.com")
    assert not subdomain_only.is_match("openai.com")
    assert not subdomain_only.is_match("evilopenai.com")
    assert apex_and_subdomain.is_match("openai.com")
    assert apex_and_subdomain.is_match("api.openai.com")
    assert not apex_and_subdomain.is_match("evilopenai.com")


def test_runtime_compile_globset_rejects_bracketed_global_wildcards() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust tests: compile_globset_rejects_bracketed_global_wildcard,
    # compile_globset_rejects_double_wildcard_bracketed_global_wildcard
    # Contract: denylist compilation rejects bracket-normalized global wildcard patterns.
    with pytest.raises(ValueError, match="unsupported global wildcard"):
        compile_denylist_globset(["[*]"])
    with pytest.raises(ValueError, match="unsupported global wildcard"):
        compile_denylist_globset(["**.[*]"])


def test_runtime_compile_globset_dedupes_patterns_without_changing_behavior() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: compile_globset_dedupes_patterns_without_changing_behavior
    # Contract: duplicate patterns are deduplicated without changing match behavior.
    set_ = compile_denylist_globset(["example.com", "example.com"])

    assert set_.is_match("example.com")
    assert set_.is_match("EXAMPLE.COM")
    assert not set_.is_match("not-example.com")


def test_runtime_compile_globset_rejects_invalid_patterns() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: compile_globset_rejects_invalid_patterns
    # Contract: invalid glob syntax is rejected during denylist compilation.
    with pytest.raises(ValueError):
        compile_denylist_globset(["["])
