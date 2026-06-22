from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pycodex.network_proxy import (
    HookEvaluation,
    InjectedHeaderConfig,
    MitmHookActionsConfig,
    MitmHookConfig,
    MitmHookMatchConfig,
    NetworkMode,
    NetworkProxyConfig,
    compile_mitm_hooks,
    compile_mitm_hooks_with_resolvers,
    evaluate_mitm_hooks,
    validate_mitm_hook_config,
)


def base_config() -> NetworkProxyConfig:
    config = NetworkProxyConfig()
    config.network.mitm = True
    config.network.mode = NetworkMode.LIMITED
    return config


def github_hook() -> MitmHookConfig:
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


def request(method: str, uri: str, headers: dict[str, str] | None = None) -> dict[str, object]:
    return {"method": method, "uri": uri, "headers": headers or {}}


def test_validate_requires_mitm_for_hooks() -> None:
    # Rust: codex-network-proxy/src/mitm_hook.rs::tests::validate_requires_mitm_for_hooks.
    config = base_config()
    config.network.mitm = False
    config.network.mitm_hooks = [github_hook()]

    with pytest.raises(ValueError, match="network.mitm_hooks requires network.mitm = true"):
        validate_mitm_hook_config(config)


def test_validate_allows_hooks_in_full_mode() -> None:
    # Rust: mitm_hook.rs::tests::validate_allows_hooks_in_full_mode.
    config = base_config()
    config.network.mode = NetworkMode.FULL
    config.network.mitm_hooks = [github_hook()]

    validate_mitm_hook_config(config)


def test_validate_rejects_body_matchers_for_now() -> None:
    # Rust: mitm_hook.rs::tests::validate_rejects_body_matchers_for_now.
    config = base_config()
    hook = github_hook()
    hook = MitmHookConfig(
        host=hook.host,
        matcher=MitmHookMatchConfig(
            methods=hook.matcher.methods,
            path_prefixes=hook.matcher.path_prefixes,
            body={"repository": "openai/codex"},
        ),
        actions=hook.actions,
    )
    config.network.mitm_hooks = [hook]

    with pytest.raises(ValueError, match="match.body is reserved"):
        validate_mitm_hook_config(config)


def test_validate_rejects_relative_secret_file() -> None:
    # Rust: mitm_hook.rs::tests::validate_rejects_relative_secret_file.
    config = base_config()
    hook = github_hook()
    hook.actions.inject_request_headers[0] = InjectedHeaderConfig(
        name="authorization",
        secret_file="token.txt",
        prefix="Bearer ",
    )
    config.network.mitm_hooks = [hook]

    with pytest.raises(ValueError, match="secret_file must be an absolute path"):
        validate_mitm_hook_config(config)


def test_validate_rejects_dual_secret_sources(tmp_path: Path) -> None:
    # Rust: mitm_hook.rs::tests::validate_rejects_dual_secret_sources.
    config = base_config()
    hook = github_hook()
    hook.actions.inject_request_headers[0] = InjectedHeaderConfig(
        name="authorization",
        secret_env_var="CODEX_GITHUB_TOKEN",
        secret_file=str(tmp_path / "github-token"),
    )
    config.network.mitm_hooks = [hook]

    with pytest.raises(ValueError, match="exactly one of secret_env_var or secret_file"):
        validate_mitm_hook_config(config)


def test_compile_resolves_env_backed_injected_headers() -> None:
    # Rust: mitm_hook.rs::tests::compile_resolves_env_backed_injected_headers.
    config = base_config()
    config.network.mitm_hooks = [github_hook()]

    hooks = compile_mitm_hooks_with_resolvers(
        config,
        resolve_env_var=lambda name: "ghp-secret" if name == "CODEX_GITHUB_TOKEN" else None,
        read_secret_file=lambda _path: pytest.fail("unexpected file lookup"),
    )

    compiled = hooks["api.github.com"]
    assert len(compiled) == 1
    injected = compiled[0].actions.inject_request_headers[0]
    assert injected.source.kind == "env_var"
    assert injected.source.value == "CODEX_GITHUB_TOKEN"
    assert injected.value == "Bearer ghp-secret"


def test_compile_resolves_file_backed_injected_headers(tmp_path: Path) -> None:
    # Rust: mitm_hook.rs::tests::compile_resolves_file_backed_injected_headers.
    secret_file = tmp_path / "github-token"
    secret_file.write_text("ghp-file-secret\n", encoding="utf-8")
    config = base_config()
    hook = github_hook()
    hook.actions.inject_request_headers[0] = InjectedHeaderConfig(
        name="authorization",
        secret_file=str(secret_file),
        prefix="Bearer ",
    )
    config.network.mitm_hooks = [hook]

    hooks = compile_mitm_hooks(config)

    assert hooks["api.github.com"][0].actions.inject_request_headers[0].value == "Bearer ghp-file-secret"


def test_evaluate_returns_first_matching_hook() -> None:
    # Rust: mitm_hook.rs::tests::evaluate_returns_first_matching_hook.
    config = base_config()
    first = github_hook()
    second = github_hook()
    second.actions.inject_request_headers[0] = InjectedHeaderConfig(
        name="authorization",
        secret_env_var="CODEX_GITHUB_TOKEN",
        prefix="Token ",
    )
    config.network.mitm_hooks = [first, second]
    hooks = compile_mitm_hooks_with_resolvers(
        config,
        resolve_env_var=lambda _name: "abc",
        read_secret_file=lambda _path: pytest.fail("unexpected file lookup"),
    )

    evaluation = evaluate_mitm_hooks(hooks, "api.github.com", request("POST", "/repos/openai/codex/issues"))

    assert evaluation.kind is HookEvaluation.MATCHED
    assert evaluation.actions is not None
    assert evaluation.actions.inject_request_headers[0].value == "Bearer abc"


def test_evaluate_matches_query_and_header_constraints() -> None:
    # Rust: mitm_hook.rs::tests::evaluate_matches_query_and_header_constraints.
    config = base_config()
    hook = github_hook()
    hook = replace(
        hook,
        matcher=replace(
            hook.matcher,
            query={"state": ["open", "triage"]},
            headers={"x-github-api-version": ["2022-11-28"]},
        ),
    )
    config.network.mitm_hooks = [hook]
    hooks = compile_mitm_hooks_with_resolvers(config, lambda _name: "abc", lambda _path: "unused")

    evaluation = evaluate_mitm_hooks(
        hooks,
        "api.github.com",
        request(
            "POST",
            "/repos/openai/codex/issues?state=open&per_page=10",
            {"x-github-api-version": "2022-11-28"},
        ),
    )

    assert evaluation.kind is HookEvaluation.MATCHED


def test_evaluate_matches_wildcard_path_query_and_header_constraints() -> None:
    # Rust: mitm_hook.rs::tests::evaluate_matches_wildcard_path_query_and_header_constraints.
    config = base_config()
    hook = github_hook()
    hook = replace(
        hook,
        matcher=replace(
            hook.matcher,
            path_prefixes=["pattern:/repos/*/codex/issues*"],
            query={"state": ["pattern:op*"]},
            headers={"x-github-api-version": ["pattern:2022*preview"]},
        ),
    )
    config.network.mitm_hooks = [hook]
    hooks = compile_mitm_hooks_with_resolvers(config, lambda _name: "abc", lambda _path: "unused")

    evaluation = evaluate_mitm_hooks(
        hooks,
        "api.github.com",
        request(
            "POST",
            "/repos/openai/codex/issues?state=open",
            {"x-github-api-version": "2022-11-28-preview"},
        ),
    )

    assert evaluation.kind is HookEvaluation.MATCHED


def test_validate_rejects_invalid_wildcard_path_pattern() -> None:
    # Rust: mitm_hook.rs::tests::validate_rejects_invalid_wildcard_path_pattern.
    config = base_config()
    hook = github_hook()
    hook = replace(hook, matcher=replace(hook.matcher, path_prefixes=["pattern:/repos/["]))
    config.network.mitm_hooks = [hook]

    with pytest.raises(ValueError, match="invalid glob pattern"):
        validate_mitm_hook_config(config)


def test_evaluate_path_wildcard_does_not_cross_segment_boundaries() -> None:
    # Rust: mitm_hook.rs::tests::evaluate_path_wildcard_does_not_cross_segment_boundaries.
    config = base_config()
    hook = github_hook()
    hook = replace(hook, matcher=replace(hook.matcher, path_prefixes=["pattern:/repos/*/codex/issues*"]))
    config.network.mitm_hooks = [hook]
    hooks = compile_mitm_hooks_with_resolvers(config, lambda _name: "abc", lambda _path: "unused")

    evaluation = evaluate_mitm_hooks(
        hooks,
        "api.github.com",
        request("POST", "/repos/openai/private/codex/issues"),
    )

    assert evaluation.kind is HookEvaluation.HOOKED_HOST_NO_MATCH


def test_evaluate_treats_glob_metacharacters_as_literal_without_glob_prefix() -> None:
    # Rust: mitm_hook.rs::tests::evaluate_treats_glob_metacharacters_as_literal_without_glob_prefix.
    config = base_config()
    hook = github_hook()
    hook = replace(
        hook,
        matcher=replace(
            hook.matcher,
            path_prefixes=["/repos/[draft]/"],
            query={"state": ["op*"]},
            headers={"x-github-api-version": ["2022-11-28[preview]"]},
        ),
    )
    config.network.mitm_hooks = [hook]
    hooks = compile_mitm_hooks_with_resolvers(config, lambda _name: "abc", lambda _path: "unused")

    exact = evaluate_mitm_hooks(
        hooks,
        "api.github.com",
        request(
            "POST",
            "/repos/[draft]/codex/issues?state=op*",
            {"x-github-api-version": "2022-11-28[preview]"},
        ),
    )
    non_literal = evaluate_mitm_hooks(
        hooks,
        "api.github.com",
        request(
            "POST",
            "/repos/draft/codex/issues?state=open",
            {"x-github-api-version": "2022-11-28-preview"},
        ),
    )

    assert exact.kind is HookEvaluation.MATCHED
    assert non_literal.kind is HookEvaluation.HOOKED_HOST_NO_MATCH


def test_evaluate_allows_literal_values_with_reserved_prefixes() -> None:
    # Rust: mitm_hook.rs::tests::evaluate_allows_literal_values_with_reserved_prefixes.
    config = base_config()
    hook = github_hook()
    hook = replace(
        hook,
        matcher=replace(
            hook.matcher,
            query={"state": ["literal:pattern:*"]},
            headers={"x-github-api-version": ["literal:pattern:*"]},
        ),
    )
    config.network.mitm_hooks = [hook]
    hooks = compile_mitm_hooks_with_resolvers(config, lambda _name: "abc", lambda _path: "unused")

    exact = evaluate_mitm_hooks(
        hooks,
        "api.github.com",
        request(
            "POST",
            "/repos/openai/codex/issues?state=pattern%3A%2A",
            {"x-github-api-version": "pattern:*"},
        ),
    )
    non_literal = evaluate_mitm_hooks(
        hooks,
        "api.github.com",
        request(
            "POST",
            "/repos/openai/codex/issues?state=pattern%3Aopen",
            {"x-github-api-version": "pattern:preview"},
        ),
    )

    assert exact.kind is HookEvaluation.MATCHED
    assert non_literal.kind is HookEvaluation.HOOKED_HOST_NO_MATCH


def test_evaluate_returns_hooked_host_no_match_when_query_constraint_fails() -> None:
    # Rust: mitm_hook.rs::tests::evaluate_returns_hooked_host_no_match_when_query_constraint_fails.
    config = base_config()
    hook = github_hook()
    hook = replace(hook, matcher=replace(hook.matcher, query={"state": ["open"]}))
    config.network.mitm_hooks = [hook]
    hooks = compile_mitm_hooks_with_resolvers(config, lambda _name: "abc", lambda _path: "unused")

    evaluation = evaluate_mitm_hooks(
        hooks,
        "api.github.com",
        request("POST", "/repos/openai/codex/issues?state=closed"),
    )

    assert evaluation.kind is HookEvaluation.HOOKED_HOST_NO_MATCH


def test_evaluate_returns_no_hooks_for_unconfigured_host() -> None:
    # Rust: mitm_hook.rs::tests::evaluate_returns_no_hooks_for_unconfigured_host.
    evaluation = evaluate_mitm_hooks({}, "api.github.com", request("POST", "/repos/openai/codex/issues"))

    assert evaluation.kind is HookEvaluation.NO_HOOKS_FOR_HOST
