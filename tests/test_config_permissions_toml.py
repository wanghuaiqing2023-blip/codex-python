import unittest

from pycodex.config import (
    NetworkDomainPermissionToml,
    NetworkDomainPermissionsToml,
    NetworkMitmActionToml,
    NetworkMitmHookToml,
    NetworkMitmInjectedHeaderToml,
    NetworkMitmToml,
    NetworkToml,
    NetworkUnixSocketPermissionToml,
    NetworkUnixSocketPermissionsToml,
    PermissionProfileCycle,
    PermissionProfileToml,
    PermissionsToml,
    UndefinedParent,
    UndefinedProfile,
    UnsupportedBuiltInParent,
    WorkspaceRootsToml,
)
from pycodex.config.permissions_toml import (
    merge_permission_profiles,
    overlay_network_domain_permissions,
)
from pycodex.network_proxy import NetworkMode, NetworkProxyConfig


class ConfigPermissionsTomlTests(unittest.TestCase):
    def test_workspace_roots_enabled_roots_filters_false_entries(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/permissions_toml.rs::WorkspaceRootsToml::enabled_roots
        roots = WorkspaceRootsToml.from_mapping({"a": True, "b": False, "c": True})

        self.assertEqual(roots.enabled_roots(), ("a", "c"))

    def test_network_domain_and_unix_socket_helpers_match_rust_contract(self) -> None:
        # Rust module: NetworkDomainPermissionsToml and NetworkUnixSocketPermissionsToml.
        domains = NetworkDomainPermissionsToml.from_mapping(
            {"api.example.com": "allow", "blocked.example.com": "deny"}
        )
        unix_sockets = NetworkUnixSocketPermissionsToml.from_mapping(
            {"/tmp/a.sock": "allow", "/tmp/b.sock": "none"}
        )

        self.assertEqual(domains.allowed_domains(), ("api.example.com",))
        self.assertEqual(domains.denied_domains(), ("blocked.example.com",))
        self.assertEqual(unix_sockets.allow_unix_sockets(), ("/tmp/a.sock",))
        self.assertEqual(
            domains.entries["api.example.com"],
            NetworkDomainPermissionToml.ALLOW,
        )
        self.assertEqual(
            unix_sockets.entries["/tmp/b.sock"],
            NetworkUnixSocketPermissionToml.NONE,
        )

    def test_resolve_profile_merges_parent_chain_and_tracks_inherited_names(self) -> None:
        # Rust module: PermissionsToml::resolve_profile.
        permissions = PermissionsToml.from_mapping(
            {
                "base": {
                    "description": "base description is not inherited",
                    "filesystem": {"/repo": "read"},
                    "network": {
                        "enabled": False,
                        "domains": {"EXAMPLE.COM.": "deny", "base.example.com": "allow"},
                    },
                },
                "child": {
                    "description": "child description",
                    "extends": "base",
                    "network": {
                        "domains": {"example.com": "allow", "child.example.com": "deny"}
                    },
                },
            }
        )

        resolved = permissions.resolve_profile("child")

        self.assertEqual(resolved.inherited_profile_names, ("base",))
        self.assertEqual(resolved.profile.description, "child description")
        self.assertEqual(resolved.profile.extends, "base")
        self.assertEqual(resolved.profile.filesystem.entries, {"/repo": "read"})
        self.assertEqual(
            resolved.profile.network.domains.to_mapping(),
            {
                "example.com": "allow",
                "base.example.com": "allow",
                "child.example.com": "deny",
            },
        )

    def test_resolve_profile_uses_parent_callback_and_reports_error_shapes(self) -> None:
        permissions = PermissionsToml.from_mapping({"child": {"extends": "parent"}})

        resolved = permissions.resolve_profile(
            "child",
            lambda name: {"filesystem": {"/from-parent": "read"}} if name == "parent" else None,
        )
        self.assertEqual(resolved.inherited_profile_names, ("parent",))
        self.assertEqual(resolved.profile.filesystem.entries, {"/from-parent": "read"})

        with self.assertRaisesRegex(UndefinedProfile, "undefined profile `missing`"):
            permissions.resolve_profile("missing")
        with self.assertRaisesRegex(UndefinedParent, "extends undefined profile `missing-parent`"):
            PermissionsToml.from_mapping({"child": {"extends": "missing-parent"}}).resolve_profile(
                "child"
            )
        with self.assertRaisesRegex(UnsupportedBuiltInParent, "unsupported built-in profile `:workspace`"):
            PermissionsToml.from_mapping({"child": {"extends": ":workspace"}}).resolve_profile(
                "child"
            )
        with self.assertRaisesRegex(PermissionProfileCycle, "a -> b -> a"):
            PermissionsToml.from_mapping(
                {"a": {"extends": "b"}, "b": {"extends": "a"}}
            ).resolve_profile("a")

    def test_profile_and_network_reject_unknown_or_invalid_shapes(self) -> None:
        # Rust source: PermissionProfileToml and NetworkToml use schemars/serde
        # deny_unknown_fields, and permission enums use fixed lowercase values.
        with self.assertRaisesRegex(KeyError, "unknown"):
            PermissionProfileToml.from_mapping({"unknown": True})
        with self.assertRaisesRegex(KeyError, "unknown"):
            PermissionProfileToml.from_mapping({"network": {"unknown": True}})
        with self.assertRaisesRegex(ValueError, "invalid"):
            NetworkDomainPermissionsToml.from_mapping({"x": "invalid"})
        with self.assertRaisesRegex(ValueError, "invalid"):
            NetworkUnixSocketPermissionsToml.from_mapping({"/tmp/x": "invalid"})
        with self.assertRaisesRegex(ValueError, "glob_scan_max_depth"):
            PermissionProfileToml.from_mapping({"filesystem": {"glob_scan_max_depth": 0}})

    def test_merge_permission_profiles_drops_parent_metadata(self) -> None:
        parent = PermissionProfileToml.from_mapping(
            {
                "description": "parent",
                "extends": "ignored",
                "workspace_roots": {"/parent": True},
            }
        )
        child = PermissionProfileToml.from_mapping({"description": "child"})

        merged = merge_permission_profiles(parent, child)

        self.assertEqual(merged.description, "child")
        self.assertIsNone(merged.extends)
        self.assertEqual(merged.workspace_roots.entries, {"/parent": True})

    def test_network_toml_applies_to_network_proxy_config_like_rust(self) -> None:
        # Rust source: codex-config::permissions_toml::NetworkToml::apply_to_network_proxy_config.
        config = NetworkProxyConfig()
        config.network.set_allowed_domains(["base.example.com"])
        network = NetworkToml.from_mapping(
            {
                "enabled": True,
                "proxy_url": "http://127.0.0.1:43128",
                "enable_socks5": True,
                "socks_url": "http://127.0.0.1:19090",
                "enable_socks5_udp": True,
                "allow_upstream_proxy": True,
                "dangerously_allow_non_loopback_proxy": True,
                "dangerously_allow_all_unix_sockets": True,
                "mode": "full",
                "domains": {"OpenAI.com.": "allow", "base.example.com": "deny"},
                "unix_sockets": {"/tmp/base.sock": "allow", "/tmp/ignored.sock": "none"},
                "allow_local_binding": True,
            },
            normalize_domains=True,
        )

        self.assertIsNotNone(network)
        assert network is not None
        network.apply_to_network_proxy_config(config)

        self.assertTrue(config.network.enabled)
        self.assertEqual(config.network.proxy_url, "http://127.0.0.1:43128")
        self.assertTrue(config.network.enable_socks5)
        self.assertEqual(config.network.socks_url, "http://127.0.0.1:19090")
        self.assertTrue(config.network.enable_socks5_udp)
        self.assertTrue(config.network.allow_upstream_proxy)
        self.assertTrue(config.network.dangerously_allow_non_loopback_proxy)
        self.assertTrue(config.network.dangerously_allow_all_unix_sockets)
        self.assertIs(config.network.mode, NetworkMode.FULL)
        self.assertEqual(config.network.allowed_domains(), ["openai.com"])
        self.assertEqual(config.network.denied_domains(), ["base.example.com"])
        self.assertEqual(config.network.allow_unix_sockets, ["/tmp/base.sock"])
        self.assertTrue(config.network.allow_local_binding)
        self.assertFalse(config.network.mitm)

    def test_network_toml_to_proxy_config_preserves_mitm_hooks_and_order(self) -> None:
        # Rust tests: permissions_profile_network_to_proxy_config_preserves_mitm_hooks,
        # permissions_profile_network_to_proxy_config_preserves_mitm_hook_declaration_order.
        network = NetworkToml.from_mapping(
            {
                "mode": "full",
                "mitm": {
                    "actions": {
                        "strip_auth": {"strip_request_headers": ["authorization"]},
                        "inject_trace": {
                            "inject_request_headers": [
                                {
                                    "name": "x-trace",
                                    "secret_env_var": "TRACE_TOKEN",
                                    "prefix": "Bearer ",
                                }
                            ]
                        },
                    },
                    "hooks": {
                        "z_first": {
                            "host": "api.github.com",
                            "methods": ["POST"],
                            "path_prefixes": ["/repos/openai/"],
                            "action": ["strip_auth", "inject_trace"],
                        },
                        "a_second": {
                            "host": "api.github.com",
                            "methods": ["PUT"],
                            "path_prefixes": ["/repos/"],
                            "query": {"visibility": ["private"]},
                            "headers": {"accept": ["application/json"]},
                            "body": {"kind": "json"},
                            "action": ["strip_auth"],
                        },
                    },
                },
            }
        )

        self.assertIsNotNone(network)
        assert network is not None
        config = network.to_network_proxy_config()

        self.assertIs(config.network.mode, NetworkMode.FULL)
        self.assertTrue(config.network.mitm)
        self.assertEqual(
            [hook.matcher.path_prefixes for hook in config.network.mitm_hooks],
            [["/repos/openai/"], ["/repos/"]],
        )
        first = config.network.mitm_hooks[0]
        self.assertEqual(first.host, "api.github.com")
        self.assertEqual(first.matcher.methods, ["POST"])
        self.assertEqual(first.actions.strip_request_headers, ["authorization"])
        self.assertEqual(first.actions.inject_request_headers[0].name, "x-trace")
        self.assertEqual(
            first.actions.inject_request_headers[0].secret_env_var,
            "TRACE_TOKEN",
        )
        self.assertEqual(first.actions.inject_request_headers[0].prefix, "Bearer ")
        second = config.network.mitm_hooks[1]
        self.assertEqual(second.matcher.query, {"visibility": ["private"]})
        self.assertEqual(second.matcher.headers, {"accept": ["application/json"]})
        self.assertEqual(second.matcher.body, {"kind": "json"})

    def test_mitm_validation_matches_rust_fail_closed_rules(self) -> None:
        # Rust tests: config_toml_rejects_empty_mitm_action_reference_list,
        # config_toml_rejects_empty_mitm_action_definition.
        with self.assertRaisesRegex(ValueError, r"network\.mitm\.hooks\.github_write\.action must not be empty"):
            NetworkMitmToml.from_mapping(
                {
                    "hooks": {
                        "github_write": {
                            "host": "api.github.com",
                            "methods": ["POST"],
                            "path_prefixes": ["/repos/openai/"],
                            "action": [],
                        }
                    },
                    "actions": {"strip_auth": {"strip_request_headers": ["authorization"]}},
                }
            )
        with self.assertRaisesRegex(ValueError, r"network\.mitm\.actions\.strip_auth must define at least one operation"):
            NetworkMitmToml.from_mapping(
                {
                    "hooks": {
                        "github_write": {
                            "host": "api.github.com",
                            "methods": ["POST"],
                            "path_prefixes": ["/repos/openai/"],
                            "action": ["strip_auth"],
                        }
                    },
                    "actions": {"strip_auth": {}},
                }
            )

        mitm = NetworkMitmToml(
            hooks={
                "github_write": NetworkMitmHookToml(
                    host="api.github.com",
                    methods=("POST",),
                    path_prefixes=("/repos/openai/",),
                    action=("missing",),
                )
            },
            actions={
                "strip_auth": NetworkMitmActionToml(
                    strip_request_headers=("authorization",)
                )
            },
        )
        with self.assertRaisesRegex(ValueError, "references undefined action `missing`"):
            mitm.validate_action_references(mitm.actions or {})

    def test_overlay_network_domain_permissions_and_mitm_runtime_helpers(self) -> None:
        # Rust source: overlay_network_domain_permissions and MITM to_runtime helpers.
        config = NetworkProxyConfig()
        config.network.set_allowed_domains(["openai.com"])
        overlay_network_domain_permissions(
            config,
            NetworkDomainPermissionsToml.from_mapping(
                {"OpenAI.com.": "deny", "api.github.com": "allow"},
                normalize=True,
            ),
        )

        self.assertEqual(config.network.allowed_domains(), ["api.github.com"])
        self.assertEqual(config.network.denied_domains(), ["openai.com"])

        header = NetworkMitmInjectedHeaderToml(
            name="x-token",
            secret_file="/tmp/token",
            prefix="token ",
        ).to_runtime()
        self.assertEqual(header.name, "x-token")
        self.assertEqual(header.secret_file, "/tmp/token")
        self.assertEqual(header.prefix, "token ")


if __name__ == "__main__":
    unittest.main()
