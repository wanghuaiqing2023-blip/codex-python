import tempfile
import time
import unittest
from pathlib import Path

from pycodex.execpolicy import Decision
from pycodex.network_proxy import (
    ConfigLayerEntry,
    ConfigLayerSource,
    LayerMtime,
    MtimeConfigReloader,
    NetworkConstraints,
    NetworkDomainPermission,
    NetworkMode,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxySpec,
    NetworkToml,
    apply_exec_policy_network_rules,
    apply_network_constraints,
    config_from_layers,
    collect_layer_mtimes,
    is_user_controlled_layer,
    network_constraints_from_trusted_layers,
    network_tables_from_toml,
    normalize_host,
    overlay_network_domain_permissions,
    selected_network_from_tables,
)
from pycodex.protocol.models import (
    ManagedFileSystemPermissions,
    NetworkSandboxPolicy,
    PermissionProfile,
)


class ExecPolicy:
    def __init__(self, allowed, denied) -> None:
        self.allowed = tuple(allowed)
        self.denied = tuple(denied)

    def compiled_network_domains(self):
        return self.allowed, self.denied


class Rule:
    def __init__(self, host: str, decision: Decision) -> None:
        self.host = host
        self.decision = decision


class RulePolicy:
    def __init__(self, rules) -> None:
        self.network_rules = tuple(rules)


class NetworkProxyLoaderTests(unittest.TestCase):
    def test_overlay_network_domain_entries(self) -> None:
        config = NetworkProxyConfig()

        overlay_network_domain_permissions(
            config,
            {
                "lower.example.com": NetworkDomainPermission.ALLOW,
                "blocked.example.com": NetworkDomainPermission.DENY,
            },
        )
        overlay_network_domain_permissions(config, {"higher.example.com": "allow"})

        self.assertEqual(config.network.allowed_domains(), ["lower.example.com", "higher.example.com"])
        self.assertEqual(config.network.denied_domains(), ["blocked.example.com"])

    def test_overlay_network_domain_overrides_matching_entries(self) -> None:
        config = NetworkProxyConfig()

        overlay_network_domain_permissions(
            config,
            {
                "shared.example.com": "deny",
                "other.example.com": "allow",
            },
        )
        overlay_network_domain_permissions(config, {"SHARED.EXAMPLE.COM.": "allow"})

        self.assertEqual(config.network.allowed_domains(), ["other.example.com", "shared.example.com"])
        self.assertIsNone(config.network.denied_domains())

    def test_apply_exec_policy_network_rules_overlay_network_lists(self) -> None:
        config = NetworkProxyConfig()
        config.network.set_allowed_domains(["config.example.com"])
        config.network.set_denied_domains(["blocked.example.com"])

        apply_exec_policy_network_rules(
            config,
            ExecPolicy(
                allowed=["blocked.example.com"],
                denied=["api.example.com"],
            ),
        )

        self.assertEqual(config.network.allowed_domains(), ["config.example.com", "blocked.example.com"])
        self.assertEqual(config.network.denied_domains(), ["api.example.com"])

    def test_apply_exec_policy_network_rules_accepts_rule_objects(self) -> None:
        config = NetworkProxyConfig()

        apply_exec_policy_network_rules(
            config,
            RulePolicy(
                [
                    Rule("api.example.com", Decision.FORBIDDEN),
                    Rule("cdn.example.com", Decision.ALLOW),
                ]
            ),
        )

        self.assertEqual(config.network.allowed_domains(), ["cdn.example.com"])
        self.assertEqual(config.network.denied_domains(), ["api.example.com"])

    def test_apply_network_constraints_overlays_domain_entries_and_flags(self) -> None:
        constraints = NetworkProxyConstraints()
        lower = NetworkToml(
            enabled=True,
            dangerously_allow_all_unix_sockets=True,
            domains={"blocked.example.com": "deny"},
        )
        higher = NetworkToml(
            allow_local_binding=True,
            domains={"api.example.com": "allow", "blocked.example.com": "allow"},
        )

        apply_network_constraints(lower, constraints)
        apply_network_constraints(higher, constraints)

        self.assertTrue(constraints.enabled)
        self.assertTrue(constraints.dangerously_allow_all_unix_sockets)
        self.assertTrue(constraints.allow_local_binding)
        self.assertEqual(constraints.allowed_domains, ["api.example.com", "blocked.example.com"])
        self.assertIsNone(constraints.denied_domains)

    def test_selected_network_from_tables_ignores_builtin_profile_without_permissions_table(self) -> None:
        # Rust source: codex-rs/core/src/network_proxy_loader_tests.rs
        # selected_network_from_tables_ignores_builtin_profile_without_permissions_table.
        parsed = network_tables_from_toml({"default_permissions": ":workspace"})

        self.assertIsNone(selected_network_from_tables(parsed))

    def test_selected_network_from_tables_rejects_unknown_builtin_profile_without_permissions_table(self) -> None:
        # Rust source: codex-rs/core/src/network_proxy_loader_tests.rs
        # selected_network_from_tables_rejects_unknown_builtin_profile_without_permissions_table.
        parsed = network_tables_from_toml({"default_permissions": ":unknown"})

        with self.assertRaisesRegex(
            ValueError,
            "default_permissions refers to unknown built-in profile `:unknown`",
        ):
            selected_network_from_tables(parsed)

    def test_selected_network_from_tables_resolves_builtin_workspace_parent(self) -> None:
        # Rust source: codex-rs/core/src/network_proxy_loader_tests.rs
        # selected_network_from_tables_resolves_builtin_workspace_parent.
        network = selected_network_from_tables(
            network_tables_from_toml(
                {
                    "default_permissions": "dev",
                    "permissions": {
                        "dev": {
                            "extends": ":workspace",
                            "network": {
                                "enabled": True,
                                "domains": {"child.example.com": "allow"},
                            },
                        }
                    },
                }
            )
        )

        self.assertEqual(network.enabled, True)
        self.assertEqual(network.domains, {"child.example.com": "allow"})

    def test_selected_network_from_tables_resolves_permission_profile_inheritance(self) -> None:
        # Rust source: codex-rs/core/src/network_proxy_loader_tests.rs
        # selected_network_from_tables_resolves_permission_profile_inheritance.
        network = selected_network_from_tables(
            network_tables_from_toml(
                {
                    "default_permissions": "dev",
                    "permissions": {
                        "base": {
                            "network": {
                                "enabled": True,
                                "dangerously_allow_all_unix_sockets": True,
                                "domains": {
                                    "base.example.com": "allow",
                                    "shared.example.com": "deny",
                                },
                            }
                        },
                        "dev": {
                            "extends": "base",
                            "network": {
                                "allow_local_binding": True,
                                "domains": {
                                    "child.example.com": "allow",
                                    "shared.example.com": "allow",
                                },
                            },
                        },
                    },
                }
            )
        )

        self.assertTrue(network.enabled)
        self.assertTrue(network.dangerously_allow_all_unix_sockets)
        self.assertTrue(network.allow_local_binding)
        self.assertEqual(
            network.domains,
            {
                "base.example.com": "allow",
                "child.example.com": "allow",
                "shared.example.com": "allow",
            },
        )

    def test_config_from_layers_resolves_inherited_profiles_across_layers(self) -> None:
        # Rust source: codex-rs/core/src/network_proxy_loader_tests.rs
        # config_from_layers_resolves_inherited_profiles_across_layers.
        config = config_from_layers(
            [
                ConfigLayerEntry(
                    ConfigLayerSource.session_flags(),
                    {"permissions": {"base": {"network": {"domains": {"base.example.com": "allow"}}}}},
                ),
                ConfigLayerEntry(
                    ConfigLayerSource.session_flags(),
                    {
                        "default_permissions": "dev",
                        "permissions": {
                            "dev": {
                                "extends": "base",
                                "network": {"domains": {"child.example.com": "allow"}},
                            }
                        },
                    },
                ),
            ]
        )

        self.assertEqual(config.network.allowed_domains(), ["base.example.com", "child.example.com"])

    def test_config_from_layers_uses_only_the_final_selected_profile_network(self) -> None:
        # Rust source: codex-rs/core/src/network_proxy_loader_tests.rs
        # config_from_layers_uses_only_the_final_selected_profile_network.
        config = config_from_layers(
            [
                ConfigLayerEntry(
                    ConfigLayerSource.session_flags(),
                    {
                        "default_permissions": "dev",
                        "permissions": {
                            "dev": {"network": {"domains": {"lower.example.com": "allow"}}}
                        },
                    },
                ),
                ConfigLayerEntry(ConfigLayerSource.session_flags(), {"default_permissions": ":workspace"}),
            ]
        )

        self.assertIsNone(config.network.allowed_domains())
        self.assertIsNone(config.network.denied_domains())

    def test_trusted_constraints_use_only_the_final_selected_profile_network(self) -> None:
        # Rust source: codex-rs/core/src/network_proxy_loader_tests.rs
        # trusted_constraints_use_only_the_final_selected_profile_network.
        constraints = network_constraints_from_trusted_layers(
            [
                ConfigLayerEntry(
                    ConfigLayerSource.system("/tmp/system.toml"),
                    {
                        "default_permissions": "dev",
                        "permissions": {
                            "dev": {"network": {"domains": {"managed.example.com": "allow"}}}
                        },
                    },
                ),
                ConfigLayerEntry(
                    ConfigLayerSource.legacy_managed_config_toml_from_file("/tmp/managed.toml"),
                    {"default_permissions": ":workspace"},
                ),
            ]
        )

        self.assertIsNone(constraints.allowed_domains)
        self.assertIsNone(constraints.denied_domains)

    def test_user_controlled_layer_matches_rust(self) -> None:
        self.assertTrue(is_user_controlled_layer(ConfigLayerSource.user("/tmp/user.toml")))
        self.assertTrue(is_user_controlled_layer(ConfigLayerSource.project("/tmp/.codex")))
        self.assertTrue(is_user_controlled_layer(ConfigLayerSource.session_flags()))
        self.assertFalse(is_user_controlled_layer(ConfigLayerSource.system("/tmp/system.toml")))
        self.assertFalse(
            is_user_controlled_layer(
                ConfigLayerSource.legacy_managed_config_toml_from_file("/tmp/managed.toml")
            )
        )

    def test_collect_layer_mtimes_uses_config_paths_and_skips_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            system = root / "system.toml"
            user = root / "user.toml"
            project_dir = root / ".codex"
            project_dir.mkdir()
            project_config = project_dir / "config.toml"
            for path in (system, user, project_config):
                path.write_text("", encoding="utf-8")

            mtimes = collect_layer_mtimes(
                [
                    ConfigLayerEntry(ConfigLayerSource.system(system)),
                    ConfigLayerEntry(ConfigLayerSource.user(user), enabled=False),
                    ConfigLayerEntry(ConfigLayerSource.project(project_dir)),
                    ConfigLayerEntry(ConfigLayerSource.session_flags()),
                ]
            )

            self.assertEqual([item.path for item in mtimes], [system, project_config])

    def test_mtime_reloader_detects_created_modified_and_deleted_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "config.toml"
            existing.write_text("a", encoding="utf-8")
            missing = root / "missing.toml"

            reloader = MtimeConfigReloader([LayerMtime.new(existing), LayerMtime.new(missing)])
            self.assertEqual(reloader.source_label(), "config layers")
            self.assertFalse(reloader.needs_reload())

            time.sleep(0.002)
            existing.write_text("b", encoding="utf-8")
            self.assertTrue(reloader.needs_reload())

            reloader.reload_now([LayerMtime.new(existing), LayerMtime.new(missing)])
            self.assertFalse(reloader.needs_reload())

            missing.write_text("now exists", encoding="utf-8")
            self.assertTrue(reloader.needs_reload())

            reloader.reload_now([LayerMtime.new(existing), LayerMtime.new(missing)])
            missing.unlink()
            self.assertTrue(reloader.needs_reload())

    def test_normalize_host_rejects_non_string(self) -> None:
        self.assertEqual(normalize_host("EXAMPLE.COM."), "example.com")
        with self.assertRaisesRegex(TypeError, "host must be a string"):
            normalize_host(123)  # type: ignore[arg-type]

    def test_network_proxy_spec_requirements_allowed_domains_are_baseline_for_user_allowlist(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec_tests.rs
        # requirements_allowed_domains_are_a_baseline_for_user_allowlist.
        config = NetworkProxyConfig()
        config.network.set_allowed_domains(["api.example.com"])
        requirements = NetworkConstraints(domains={"*.example.com": "allow"})

        spec = NetworkProxySpec.from_config_and_constraints(
            config,
            requirements,
            PermissionProfile.read_only(),
        )

        self.assertEqual(spec.config.network.allowed_domains(), ["*.example.com", "api.example.com"])
        self.assertEqual(spec.constraints.allowed_domains, ["*.example.com"])
        self.assertEqual(spec.constraints.allowlist_expansion_enabled, True)

    def test_network_proxy_spec_requirements_allowed_domains_do_not_override_user_denies(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec_tests.rs
        # requirements_allowed_domains_do_not_override_user_denies_for_same_pattern.
        config = NetworkProxyConfig()
        config.network.set_denied_domains(["api.example.com"])
        requirements = NetworkConstraints(domains={"api.example.com": "allow"})

        spec = NetworkProxySpec.from_config_and_constraints(
            config,
            requirements,
            PermissionProfile.workspace_write(),
        )

        self.assertIsNone(spec.config.network.allowed_domains())
        self.assertEqual(spec.config.network.denied_domains(), ["api.example.com"])
        self.assertEqual(spec.constraints.allowed_domains, ["api.example.com"])

    def test_network_proxy_spec_managed_unrestricted_profile_allows_domain_expansion(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec_tests.rs
        # managed_unrestricted_profile_allows_domain_expansion.
        config = NetworkProxyConfig()
        config.network.set_allowed_domains(["api.example.com"])
        permission_profile = PermissionProfile.managed(
            ManagedFileSystemPermissions.unrestricted(),
            NetworkSandboxPolicy.RESTRICTED,
        )

        spec = NetworkProxySpec.from_config_and_constraints(
            config,
            NetworkConstraints(domains={"*.example.com": "allow"}),
            permission_profile,
        )

        self.assertEqual(spec.config.network.allowed_domains(), ["*.example.com", "api.example.com"])
        self.assertEqual(spec.constraints.allowlist_expansion_enabled, True)

    def test_network_proxy_spec_disabled_profile_keeps_managed_lists_fixed(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec_tests.rs
        # danger_full_access_keeps_managed_allowlist_and_denylist_fixed.
        config = NetworkProxyConfig()
        config.network.set_allowed_domains(["evil.com"])
        config.network.set_denied_domains(["more-blocked.example.com"])
        requirements = NetworkConstraints(
            domains={
                "*.example.com": NetworkDomainPermission.ALLOW,
                "blocked.example.com": NetworkDomainPermission.DENY,
            }
        )

        spec = NetworkProxySpec.from_config_and_constraints(
            config,
            requirements,
            PermissionProfile.disabled(),
        )

        self.assertEqual(spec.config.network.allowed_domains(), ["*.example.com"])
        self.assertEqual(spec.config.network.denied_domains(), ["blocked.example.com"])
        self.assertEqual(spec.constraints.allowlist_expansion_enabled, False)
        self.assertEqual(spec.constraints.denylist_expansion_enabled, False)

    def test_network_proxy_spec_managed_allowed_domains_only_hard_denies_misses(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec_tests.rs
        # managed_allowed_domains_only_ignores_user_allowlist_and_hard_denies_misses.
        config = NetworkProxyConfig()
        config.network.set_allowed_domains(["api.example.com"])

        spec = NetworkProxySpec.from_config_and_constraints(
            config,
            NetworkConstraints(
                domains={"managed.example.com": "allow"},
                managed_allowed_domains_only=True,
            ),
            PermissionProfile.workspace_write(),
        )

        self.assertEqual(spec.config.network.allowed_domains(), ["managed.example.com"])
        self.assertEqual(spec.constraints.allowed_domains, ["managed.example.com"])
        self.assertEqual(spec.constraints.allowlist_expansion_enabled, False)
        self.assertTrue(spec.hard_deny_allowlist_misses)

    def test_network_proxy_spec_managed_allowed_domains_only_without_managed_list_blocks_users(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec_tests.rs
        # managed_allowed_domains_only_without_managed_allowlist_blocks_all_user_domains.
        for profile in (PermissionProfile.workspace_write(), PermissionProfile.disabled()):
            config = NetworkProxyConfig()
            config.network.set_allowed_domains(["api.example.com"])

            spec = NetworkProxySpec.from_config_and_constraints(
                config,
                NetworkConstraints(managed_allowed_domains_only=True),
                profile,
            )

            self.assertIsNone(spec.config.network.allowed_domains())
            self.assertEqual(spec.constraints.allowed_domains, [])
            self.assertEqual(spec.constraints.allowlist_expansion_enabled, False)
            self.assertTrue(spec.hard_deny_allowlist_misses)

    def test_network_proxy_spec_deny_only_requirements_do_not_create_allow_constraints_in_full_access(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec_tests.rs
        # deny_only_requirements_do_not_create_allow_constraints_in_full_access.
        config = NetworkProxyConfig()
        config.network.set_allowed_domains(["api.example.com"])

        spec = NetworkProxySpec.from_config_and_constraints(
            config,
            NetworkConstraints(domains={"managed-blocked.example.com": "deny"}),
            PermissionProfile.disabled(),
        )

        self.assertEqual(spec.config.network.allowed_domains(), ["api.example.com"])
        self.assertIsNone(spec.constraints.allowed_domains)
        self.assertIsNone(spec.constraints.allowlist_expansion_enabled)
        self.assertEqual(spec.config.network.denied_domains(), ["managed-blocked.example.com"])

    def test_network_proxy_spec_allow_only_requirements_do_not_create_deny_constraints_in_full_access(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec_tests.rs
        # allow_only_requirements_do_not_create_deny_constraints_in_full_access.
        config = NetworkProxyConfig()
        config.network.set_denied_domains(["blocked.example.com"])

        spec = NetworkProxySpec.from_config_and_constraints(
            config,
            NetworkConstraints(domains={"managed.example.com": "allow"}),
            PermissionProfile.disabled(),
        )

        self.assertEqual(spec.config.network.allowed_domains(), ["managed.example.com"])
        self.assertEqual(spec.config.network.denied_domains(), ["blocked.example.com"])
        self.assertIsNone(spec.constraints.denied_domains)
        self.assertIsNone(spec.constraints.denylist_expansion_enabled)

    def test_network_proxy_spec_requirements_denied_domains_are_baseline_for_default_mode(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec_tests.rs
        # requirements_denied_domains_are_a_baseline_for_default_mode.
        config = NetworkProxyConfig()
        config.network.set_denied_domains(["blocked.example.com"])

        spec = NetworkProxySpec.from_config_and_constraints(
            config,
            NetworkConstraints(domains={"managed-blocked.example.com": "deny"}),
            PermissionProfile.workspace_write(),
        )

        self.assertEqual(
            spec.config.network.denied_domains(),
            ["managed-blocked.example.com", "blocked.example.com"],
        )
        self.assertEqual(spec.constraints.denied_domains, ["managed-blocked.example.com"])
        self.assertEqual(spec.constraints.denylist_expansion_enabled, True)

    def test_network_proxy_spec_denylist_expansion_keeps_user_entries_mutable(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec_tests.rs
        # requirements_denylist_expansion_keeps_user_entries_mutable.
        config = NetworkProxyConfig()
        config.network.set_denied_domains(["blocked.example.com"])
        spec = NetworkProxySpec.from_config_and_constraints(
            config,
            NetworkConstraints(domains={"managed-blocked.example.com": "deny"}),
            PermissionProfile.workspace_write(),
        )

        spec.config.network.upsert_domain_permission("blocked.example.com", NetworkDomainPermission.ALLOW)

        self.assertEqual(spec.config.network.allowed_domains(), ["blocked.example.com"])
        self.assertEqual(spec.config.network.denied_domains(), ["managed-blocked.example.com"])

    def test_network_proxy_spec_ports_flags_and_exec_policy_rules(self) -> None:
        # Rust source: codex-rs/core/src/config/network_proxy_spec.rs::apply_requirements
        # and with_exec_policy_network_rules.
        spec = NetworkProxySpec.from_config_and_constraints(
            NetworkProxyConfig(),
            NetworkConstraints(
                enabled=True,
                http_port=43128,
                socks_port=43129,
                allow_upstream_proxy=True,
                dangerously_allow_non_loopback_proxy=True,
                dangerously_allow_all_unix_sockets=True,
                unix_sockets=("/tmp/socket",),
                allow_local_binding=True,
            ),
            PermissionProfile.workspace_write(),
        )

        self.assertTrue(spec.enabled())
        self.assertEqual(spec.proxy_host_and_port(), "127.0.0.1:43128")
        self.assertEqual(spec.config.network.socks_url, "http://127.0.0.1:43129")
        self.assertTrue(spec.config.network.allow_upstream_proxy)
        self.assertTrue(spec.config.network.dangerously_allow_non_loopback_proxy)
        self.assertTrue(spec.config.network.dangerously_allow_all_unix_sockets)
        self.assertEqual(spec.config.network.allow_unix_sockets, ["/tmp/socket"])
        self.assertTrue(spec.config.network.allow_local_binding)

        updated = spec.with_exec_policy_network_rules(
            ExecPolicy(allowed=["api.example.com"], denied=["blocked.example.com"])
        )

        self.assertEqual(updated.config.network.allowed_domains(), ["api.example.com"])
        self.assertEqual(updated.config.network.denied_domains(), ["blocked.example.com"])

    def test_network_proxy_spec_socks_enabled_reflects_config(self) -> None:
        config = NetworkProxyConfig()
        config.network.enable_socks5 = True
        config.network.mode = NetworkMode.FULL

        spec = NetworkProxySpec.from_config_and_constraints(config, None, PermissionProfile.workspace_write())

        self.assertTrue(spec.socks_enabled())
        self.assertEqual(spec.config.network.mode, NetworkMode.FULL)


if __name__ == "__main__":
    unittest.main()
