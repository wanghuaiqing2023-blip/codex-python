from pycodex.tui.debug_config import (
    ConfigLayerEntry,
    ConfigLayerSource,
    ConfigLayerSourceKind,
    ConfigLayerStack,
    flatten_toml_key_values,
    format_config_layer_source,
    format_approval_policy,
    format_approvals_reviewer,
    format_managed_hooks_requirements,
    format_network_constraints,
    format_web_search_mode_requirement,
    join_or_empty,
    new_debug_config_output,
    normalize_allowed_web_search_modes,
    render_debug_config_lines,
    render_mdm_layer_details,
    render_session_flag_details,
    render_to_text,
    requirement_line,
    session_all_proxy_url,
)


def test_session_all_proxy_url_uses_socks_or_http():
    # Rust: codex-tui, debug_config.rs, session_all_proxy_url_* tests.
    assert session_all_proxy_url("127.0.0.1:3128", "127.0.0.1:8081", True) == "socks5h://127.0.0.1:8081"
    assert session_all_proxy_url("127.0.0.1:3128", "127.0.0.1:8081", False) == "http://127.0.0.1:3128"


def test_debug_config_output_lists_all_layers_including_disabled():
    # Rust: codex-tui, debug_config.rs, debug_config_output_lists_all_layers_including_disabled.
    stack = ConfigLayerStack(
        layers=(
            ConfigLayerEntry(ConfigLayerSource(ConfigLayerSourceKind.SYSTEM, file="/etc/codex/config.toml")),
            ConfigLayerEntry(
                ConfigLayerSource(ConfigLayerSourceKind.PROJECT, dot_codex_folder="/repo/.codex"),
                disabled_reason="project is untrusted",
            ),
        )
    )

    rendered = render_to_text(render_debug_config_lines(stack))

    assert "(enabled)" in rendered
    assert "(disabled)" in rendered
    assert "reason: project is untrusted" in rendered
    assert "Requirements:" in rendered
    assert "  <none>" in rendered


def test_render_session_flag_details_flattens_sorted_key_value_pairs():
    # Rust: codex-tui, debug_config.rs, debug_config_output_lists_session_flag_key_value_pairs.
    lines = render_session_flag_details(
        {
            "model": "gpt-5",
            "sandbox_workspace_write": {
                "network_access": True,
                "writable_roots": ["/tmp"],
            },
        }
    )

    assert '     - model = "gpt-5"' in lines
    assert "     - sandbox_workspace_write.network_access = true" in lines
    assert '     - sandbox_workspace_write.writable_roots = ["/tmp"]' in lines


def test_render_mdm_layer_details_preserves_raw_multiline_value():
    # Rust: codex-tui, debug_config.rs, debug_config_output_shows_legacy_mdm_layer_value.
    raw = '# managed by MDM\nmodel = "managed_model"\napproval_policy = "never"'
    layer = ConfigLayerEntry(ConfigLayerSource(ConfigLayerSourceKind.LEGACY_MANAGED_MDM), raw_toml_text=raw)

    rendered = "\n".join(render_mdm_layer_details(layer))

    assert "MDM value:" in rendered
    assert "# managed by MDM" in rendered
    assert 'model = "managed_model"' in rendered
    assert 'approval_policy = "never"' in rendered


def test_render_mdm_layer_details_empty_value_matches_rust_branch():
    layer = ConfigLayerEntry(ConfigLayerSource(ConfigLayerSourceKind.LEGACY_MANAGED_MDM), raw_toml_text="")

    assert render_mdm_layer_details(layer) == ["     MDM value: <empty>"]


def test_requirement_and_join_helpers_match_visible_text_contract():
    assert join_or_empty([]) == "<empty>"
    assert join_or_empty(["one", "two"]) == "one, two"
    assert requirement_line("allowed_approval_policies", "on-request", "cloud requirements") == (
        "  - allowed_approval_policies: on-request (source: cloud requirements)"
    )


def test_requirement_value_formatters_match_rust_display_names():
    # Rust: codex-tui, debug_config.rs, debug_config_output_lists_requirement_sources.
    assert format_approval_policy("OnRequest") == "on-request"
    assert format_approvals_reviewer("AutoReview") == "guardian_subagent"
    assert format_web_search_mode_requirement("Cached") == "cached"


def test_normalize_allowed_web_search_modes_adds_disabled_and_handles_empty():
    # Rust: codex-tui, debug_config.rs, debug_config_output_normalizes_empty_web_search_mode_list.
    assert normalize_allowed_web_search_modes([]) == ["disabled"]
    assert normalize_allowed_web_search_modes(["cached"]) == ["cached", "disabled"]
    assert normalize_allowed_web_search_modes(["cached", "disabled"]) == ["cached", "disabled"]


def test_debug_config_output_lists_requirement_sources() -> None:
    # Rust: codex-tui, debug_config.rs, debug_config_output_lists_requirement_sources.
    stack = ConfigLayerStack(
        requirements={
            "approval_policy": {"source": "CloudRequirements"},
            "approvals_reviewer": {"source": "LegacyManagedConfigTomlFromMdm"},
            "permission_profile": {"source": "/etc/codex/requirements.toml"},
            "web_search_mode": {"source": "CloudRequirements"},
            "allow_managed_hooks_only": {"source": "CloudRequirements"},
            "allow_appshots": {"source": "CloudRequirements"},
            "guardian_policy_config_source": "CloudRequirements",
            "feature_requirements": {
                "value": {"entries": {"guardian_approval": True}},
                "source": "CloudRequirements",
            },
            "mcp_servers": {"source": "LegacyManagedConfigTomlFromMdm"},
            "enforce_residency": {"source": "CloudRequirements"},
            "network": {
                "value": {"enabled": True, "domains": {"entries": {"example.com": "Allow"}}},
                "source": "CloudRequirements",
            },
            "filesystem": {
                "value": {"deny_read": ["/home/alice/.gitconfig"]},
                "source": "/etc/codex/requirements.toml",
            },
        },
        requirements_toml={
            "allowed_approval_policies": ["OnRequest"],
            "allowed_approvals_reviewers": ["AutoReview"],
            "allowed_sandbox_modes": ["ReadOnly"],
            "allowed_web_search_modes": ["Cached"],
            "allow_managed_hooks_only": True,
            "allow_appshots": False,
            "guardian_policy_config": "Use the managed guardian policy.",
            "mcp_servers": {"docs": {"identity": "command"}},
            "enforce_residency": "Us",
        },
    )

    rendered = render_to_text(render_debug_config_lines(stack))

    assert "allowed_approval_policies: on-request (source: cloud requirements)" in rendered
    assert "allowed_approvals_reviewers: guardian_subagent (source: MDM managed_config.toml (legacy))" in rendered
    assert "allowed_sandbox_modes: read-only (source: /etc/codex/requirements.toml)" in rendered
    assert "allowed_web_search_modes: cached, disabled (source: cloud requirements)" in rendered
    assert "allow_managed_hooks_only: true (source: cloud requirements)" in rendered
    assert "allow_appshots: false (source: cloud requirements)" in rendered
    assert "guardian_policy_config: configured (source: cloud requirements)" in rendered
    assert "features: guardian_approval=true (source: cloud requirements)" in rendered
    assert "mcp_servers: docs (source: MDM managed_config.toml (legacy))" in rendered
    assert "enforce_residency: us (source: cloud requirements)" in rendered
    assert "experimental_network: enabled=true, domains={example.com=allow} (source: cloud requirements)" in rendered
    assert "permissions.filesystem.deny_read: /home/alice/.gitconfig (source: /etc/codex/requirements.toml)" in rendered
    assert "  - rules:" not in rendered


def test_format_network_constraints_domains_and_unix_sockets_are_sorted():
    # Rust: codex-tui, debug_config.rs, debug_config_output_formats_unix_socket_permissions.
    rendered = format_network_constraints(
        {
            "enabled": True,
            "domains": {"entries": {"example.com": "Allow"}},
            "unix_sockets": {
                "entries": {
                    "/tmp/codex.sock": "Allow",
                    "/tmp/blocked.sock": "None",
                }
            },
        }
    )

    assert "enabled=true" in rendered
    assert "domains={example.com=allow}" in rendered
    assert "unix_sockets={/tmp/blocked.sock=none, /tmp/codex.sock=allow}" in rendered


def test_format_network_constraints_preserves_rust_scalar_field_order():
    # Rust: format_network_constraints appends scalar flags in source order.
    rendered = format_network_constraints(
        {
            "enabled": True,
            "http_port": 3128,
            "socks_port": 1080,
            "allow_upstream_proxy": False,
            "dangerously_allow_non_loopback_proxy": True,
            "dangerously_allow_all_unix_sockets": False,
            "managed_allowed_domains_only": True,
            "allow_local_binding": False,
        }
    )

    assert rendered == (
        "enabled=true, http_port=3128, socks_port=1080, allow_upstream_proxy=false, "
        "dangerously_allow_non_loopback_proxy=true, dangerously_allow_all_unix_sockets=false, "
        "managed_allowed_domains_only=true, allow_local_binding=false"
    )


def test_format_config_layer_source_variants():
    assert format_config_layer_source(ConfigLayerSource(ConfigLayerSourceKind.SESSION_FLAGS)) == "session-flags"
    assert (
        format_config_layer_source(ConfigLayerSource(ConfigLayerSourceKind.LEGACY_MANAGED_MDM))
        == "legacy managed_config.toml (MDM)"
    )
    assert (
        format_config_layer_source(ConfigLayerSource(ConfigLayerSourceKind.MDM, domain="com.openai", key="Codex"))
        == "MDM (com.openai:Codex)"
    )


def test_new_debug_config_output_appends_session_runtime_proxy_lines():
    config = {"config_layer_stack": ConfigLayerStack(), "permissions": {"network": {"socks_enabled": True}}}
    proxy = {"http_addr": "127.0.0.1:3128", "socks_addr": "127.0.0.1:8081"}

    rendered = new_debug_config_output(config, proxy).text()

    assert "Session runtime:" in rendered
    assert "HTTP_PROXY  = http://127.0.0.1:3128" in rendered
    assert "ALL_PROXY   = socks5h://127.0.0.1:8081" in rendered


def test_flatten_toml_key_values_uses_value_for_scalar_root():
    pairs = []
    flatten_toml_key_values("value", None, pairs)

    assert pairs == [("<value>", '"value"')]


def test_format_managed_hooks_requirements_includes_dirs_and_handlers():
    rendered = format_managed_hooks_requirements(
        {"managed_dir": "/enterprise/hooks", "windows_managed_dir": r"C:\enterprise\hooks", "handlers": 1}
    )

    assert "managed_dir=/enterprise/hooks" in rendered
    assert r"windows_managed_dir=C:\enterprise\hooks" in rendered
    assert "handlers=1" in rendered
