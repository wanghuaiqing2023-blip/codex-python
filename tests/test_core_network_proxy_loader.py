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
    NetworkDomainPermission,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkToml,
    apply_exec_policy_network_rules,
    apply_network_constraints,
    collect_layer_mtimes,
    is_user_controlled_layer,
    normalize_host,
    overlay_network_domain_permissions,
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


if __name__ == "__main__":
    unittest.main()
