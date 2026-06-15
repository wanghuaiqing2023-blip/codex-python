from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.config.config_requirements import (
    AppRequirementToml,
    AppToolRequirementToml,
    AppToolsRequirementsToml,
    AppsRequirementsToml,
    ConfigRequirements,
    ConfigRequirementsToml,
    ConfigRequirementsWithSources,
    FilesystemConstraints,
    FilesystemDenyReadPattern,
    McpServerIdentity,
    McpServerRequirement,
    NetworkDomainPermissionToml,
    NetworkDomainPermissionsToml,
    NetworkUnixSocketPermissionToml,
    NetworkUnixSocketPermissionsToml,
    PermissionsRequirementsToml,
    PluginRequirementsToml,
    SandboxModeRequirement,
    WebSearchModeRequirement,
    merge_app_requirements_descending,
    sandbox_mode_requirement_for_permission_profile,
)
from pycodex.config.constraint import ConstraintError, RequirementSource
from pycodex.config.hook_config import ManagedHooksRequirementsToml
from pycodex.config.mcp_types import AppToolApproval
from pycodex.execpolicy import Decision
from pycodex.protocol.config_types import ApprovalsReviewer, AskForApproval, WebSearchMode
from pycodex.protocol.models import NetworkSandboxPolicy, PermissionProfile


def test_network_requirements_canonical_domains_and_unix_sockets() -> None:
    # Rust: network_requirements_are_preserved_as_constraints_with_source.
    req = ConfigRequirementsToml.from_toml(
        """
        [experimental_network]
        enabled = true
        allow_upstream_proxy = false
        dangerously_allow_all_unix_sockets = true
        managed_allowed_domains_only = true
        allow_local_binding = false

        [experimental_network.domains]
        "example.com" = "allow"
        "blocked.example.com" = "deny"

        [experimental_network.unix_sockets]
        "/var/run/docker.sock" = "allow"
        "/tmp/socket" = "none"
        """
    )

    assert req.network.enabled is True
    assert req.network.allow_upstream_proxy is False
    assert req.network.domains == NetworkDomainPermissionsToml(
        {
            "example.com": NetworkDomainPermissionToml.ALLOW,
            "blocked.example.com": NetworkDomainPermissionToml.DENY,
        }
    )
    assert req.network.domains.allowed_domains() == ["example.com"]
    assert req.network.domains.denied_domains() == ["blocked.example.com"]
    assert req.network.unix_sockets == NetworkUnixSocketPermissionsToml(
        {
            "/var/run/docker.sock": NetworkUnixSocketPermissionToml.ALLOW,
            "/tmp/socket": NetworkUnixSocketPermissionToml.NONE,
        }
    )
    assert req.network.unix_sockets.allow_unix_sockets() == ["/var/run/docker.sock"]
    assert req.network.allow_local_binding is False


def test_legacy_network_requirements_normalize_to_canonical_shapes() -> None:
    # Rust: legacy_network_requirements_are_preserved_as_constraints_with_source.
    req = ConfigRequirementsToml.from_toml(
        """
        [experimental_network]
        enabled = true
        allowed_domains = ["example.com"]
        denied_domains = ["blocked.example.com"]
        allow_unix_sockets = ["/var/run/docker.sock"]
        """
    )

    assert req.network.domains.allowed_domains() == ["example.com"]
    assert req.network.domains.denied_domains() == ["blocked.example.com"]
    assert req.network.unix_sockets.allow_unix_sockets() == ["/var/run/docker.sock"]


def test_mixed_legacy_and_canonical_network_requirements_are_rejected() -> None:
    # Rust: mixed_legacy_and_canonical_network_requirements_are_rejected.
    with pytest.raises(ValueError, match="experimental_network.domains"):
        ConfigRequirementsToml.from_toml(
            """
            [experimental_network]
            allowed_domains = ["example.com"]

            [experimental_network.domains]
            "example.org" = "allow"
            """
        )
    with pytest.raises(ValueError, match="experimental_network.unix_sockets"):
        ConfigRequirementsToml.from_toml(
            """
            [experimental_network]
            allow_unix_sockets = ["/tmp/socket"]

            [experimental_network.unix_sockets]
            "/tmp/other" = "allow"
            """
        )


def test_filesystem_requirements_reject_profile_shape_and_normalize_globs(tmp_path: Path, monkeypatch) -> None:
    # Rust: filesystem_requirements_table_cannot_define_a_permission_profile /
    # deserialize_filesystem_deny_read_glob_requirements.
    with pytest.raises(ValueError, match="reserved for requirements-level filesystem constraints"):
        ConfigRequirementsToml.from_toml(
            """
            [permissions.filesystem]
            extends = ":workspace"
            """
        )

    monkeypatch.chdir(tmp_path)
    req = ConfigRequirementsToml.from_toml(
        """
        [permissions.filesystem]
        deny_read = ["./private/**/*.txt"]
        """
    )

    constraints = FilesystemConstraints.from_permissions(req.permissions)
    assert constraints.deny_read == (
        FilesystemDenyReadPattern(str(tmp_path / "private" / "**" / "*.txt")),
    )
    assert constraints.deny_read[0].contains_glob()


def test_config_requirements_toml_deserializes_managed_permission_profiles() -> None:
    # Rust: deserialize_managed_permission_profiles.
    requirements = ConfigRequirementsToml.from_toml(
        """
        allowed_permissions = ["managed-standard", "managed-build"]

        [permissions.managed-standard]
        extends = ":workspace"

        [permissions.managed-build]
        extends = "managed-standard"
        """
    )

    assert requirements.allowed_permissions == ("managed-standard", "managed-build")
    assert requirements.permissions is not None
    assert "managed-standard" in requirements.permissions.profiles
    assert requirements.permissions.profiles["managed-build"].extends == "managed-standard"
    assert not requirements.is_empty()


def test_apps_requirements_and_descending_merge() -> None:
    # Rust: deserialize_apps_requirements / deserialize_apps_tool_requirements /
    # merge_app_requirements_descending_*.
    req = ConfigRequirementsToml.from_toml(
        """
        [apps.connector_123123]
        enabled = false

        [apps.connector_123123.tools."calendar/list_events"]
        approval_mode = "prompt"
        """
    )

    assert req.apps.apps["connector_123123"] == AppRequirementToml(
        enabled=False,
        tools=AppToolsRequirementsToml(
            {"calendar/list_events": AppToolRequirementToml(AppToolApproval.PROMPT)}
        ),
    )

    high = AppsRequirementsToml({"connector": AppRequirementToml(enabled=True)})
    low = AppsRequirementsToml({"connector": AppRequirementToml(enabled=False)})
    assert merge_app_requirements_descending(high, low).apps["connector"].enabled is False

    high_tool = AppsRequirementsToml(
        {
            "connector": AppRequirementToml(
                tools=AppToolsRequirementsToml({"tool": AppToolRequirementToml(AppToolApproval.APPROVE)})
            )
        }
    )
    low_tool = AppsRequirementsToml(
        {
            "connector": AppRequirementToml(
                tools=AppToolsRequirementsToml({"tool": AppToolRequirementToml(AppToolApproval.PROMPT)})
            )
        }
    )
    assert (
        merge_app_requirements_descending(high_tool, low_tool)
        .apps["connector"]
        .tools
        .tools["tool"]
        .approval_mode
        == AppToolApproval.APPROVE
    )


def test_remote_sandbox_config_first_match_overrides_top_level() -> None:
    # Rust: remote_sandbox_config_first_match_overrides_top_level.
    req = ConfigRequirementsToml.from_toml(
        """
        allowed_sandbox_modes = ["read-only"]

        [[remote_sandbox_config]]
        hostname_patterns = ["build-*.example.com"]
        allowed_sandbox_modes = ["workspace-write"]

        [[remote_sandbox_config]]
        hostname_patterns = ["*"]
        allowed_sandbox_modes = ["danger-full-access"]
        """
    )

    req.apply_remote_sandbox_config("BUILD-01.EXAMPLE.COM.")
    assert req.allowed_sandbox_modes == (SandboxModeRequirement.WORKSPACE_WRITE,)


def test_remote_sandbox_config_non_match_preserves_top_level() -> None:
    # Rust: remote_sandbox_config_non_match_preserves_top_level.
    req = ConfigRequirementsToml.from_toml(
        """
        allowed_sandbox_modes = ["read-only"]

        [[remote_sandbox_config]]
        hostname_patterns = ["build-*.example.com"]
        allowed_sandbox_modes = ["read-only", "workspace-write"]
        """
    )

    req.apply_remote_sandbox_config("laptop.example.com")
    requirements = ConfigRequirements.from_sources(_with_unknown_source(req))

    with pytest.raises(ConstraintError, match="sandbox_mode"):
        requirements.permission_profile.value.can_set(PermissionProfile.disabled())


def test_remote_sandbox_config_does_not_override_higher_precedence_sandbox_modes() -> None:
    # Rust: remote_sandbox_config_does_not_override_higher_precedence_sandbox_modes.
    high = ConfigRequirementsToml.from_toml('allowed_sandbox_modes = ["read-only"]\n')
    high.apply_remote_sandbox_config("runner-01.ci.example.com")
    low = ConfigRequirementsToml.from_toml(
        """
        [[remote_sandbox_config]]
        hostname_patterns = ["runner-*.ci.example.com"]
        allowed_sandbox_modes = ["read-only", "workspace-write"]
        """
    )
    low.apply_remote_sandbox_config("runner-01.ci.example.com")

    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(RequirementSource.cloud_requirements(), high)
    target.merge_unset_fields(RequirementSource.unknown(), low)
    requirements = ConfigRequirements.from_sources(target)

    with pytest.raises(ConstraintError, match="sandbox_mode"):
        requirements.permission_profile.value.can_set(PermissionProfile.workspace_write())


def test_mcp_and_plugin_requirements_parse_identity_tables() -> None:
    # Rust: mcp_servers / plugin mcp_servers identity parsing.
    req = ConfigRequirementsToml.from_toml(
        """
        [mcp_servers.docs.identity]
        command = "docs-server"

        [mcp_servers.remote.identity]
        url = "https://example.com/mcp"

        [plugins."sample@test".mcp_servers.sample.identity]
        command = "sample-server"
        """
    )

    assert req.mcp_servers == {
        "docs": McpServerRequirement(McpServerIdentity.command("docs-server")),
        "remote": McpServerRequirement(McpServerIdentity.url("https://example.com/mcp")),
    }
    assert req.plugins == {
        "sample@test": PluginRequirementsToml(
            {"sample": McpServerRequirement(McpServerIdentity.command("sample-server"))}
        )
    }


def test_config_requirements_is_empty_treats_blank_guardian_as_empty() -> None:
    # Rust: blank_guardian_policy_config_is_empty.
    assert ConfigRequirementsToml.from_toml('guardian_policy_config = "   "\n').is_empty()
    assert not ConfigRequirementsToml.from_toml("allow_appshots = false\n").is_empty()


def test_merge_unset_fields_fills_missing_values_and_sets_sources() -> None:
    # Rust: merge_unset_fields_fills_missing_values.
    source = RequirementSource.mdm_managed_preferences("com.codex", "allowed_approval_policies")
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        source,
        ConfigRequirementsToml.from_toml('allowed_approval_policies = ["on-request"]\n'),
    )

    assert target.allowed_approval_policies.value == (AskForApproval.ON_REQUEST,)
    assert target.allowed_approval_policies.source == source


def test_merge_unset_fields_does_not_overwrite_existing_values() -> None:
    # Rust: merge_unset_fields_does_not_overwrite_existing_values.
    existing_source = RequirementSource.legacy_managed_config_toml_from_mdm()
    later_source = RequirementSource.mdm_managed_preferences("com.codex", "allowed_approval_policies")
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        existing_source,
        ConfigRequirementsToml.from_toml('allowed_approval_policies = ["never"]\n'),
    )
    target.merge_unset_fields(
        later_source,
        ConfigRequirementsToml.from_toml('allowed_approval_policies = ["on-request"]\n'),
    )

    assert target.allowed_approval_policies.value == (AskForApproval.NEVER,)
    assert target.allowed_approval_policies.source == existing_source


def test_merge_unset_fields_merges_apps_across_sources_with_enabled_evaluation() -> None:
    # Rust: merge_unset_fields_merges_apps_across_sources_with_enabled_evaluation.
    higher_source = RequirementSource.cloud_requirements()
    lower_source = RequirementSource.legacy_managed_config_toml_from_mdm()
    target = ConfigRequirementsWithSources()

    target.merge_unset_fields(
        higher_source,
        ConfigRequirementsToml(
            apps=AppsRequirementsToml(
                {
                    "connector_high": AppRequirementToml(enabled=True),
                    "connector_shared": AppRequirementToml(enabled=True),
                }
            )
        ),
    )
    target.merge_unset_fields(
        lower_source,
        ConfigRequirementsToml(
            apps=AppsRequirementsToml(
                {
                    "connector_low": AppRequirementToml(enabled=False),
                    "connector_shared": AppRequirementToml(enabled=False),
                }
            )
        ),
    )

    assert target.apps.value == AppsRequirementsToml(
        {
            "connector_high": AppRequirementToml(enabled=True),
            "connector_low": AppRequirementToml(enabled=False),
            "connector_shared": AppRequirementToml(enabled=False),
        }
    )
    assert target.apps.source == higher_source


def test_merge_unset_fields_apps_empty_higher_source_does_not_block_lower_disables() -> None:
    # Rust: merge_unset_fields_apps_empty_higher_source_does_not_block_lower_disables.
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(RequirementSource.cloud_requirements(), ConfigRequirementsToml(apps=AppsRequirementsToml()))
    target.merge_unset_fields(
        RequirementSource.legacy_managed_config_toml_from_mdm(),
        ConfigRequirementsToml(apps=AppsRequirementsToml({"connector": AppRequirementToml(enabled=False)})),
    )

    assert target.apps.value == AppsRequirementsToml({"connector": AppRequirementToml(enabled=False)})


def test_merge_unset_fields_ignores_blank_guardian_policy_and_into_toml_drops_sources() -> None:
    source = RequirementSource.cloud_requirements()
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(source, ConfigRequirementsToml(guardian_policy_config="   ", allow_appshots=False))

    assert target.guardian_policy_config is None
    assert target.allow_appshots.value is False
    assert target.into_toml().allow_appshots is False


def test_config_requirements_from_sources_builds_allowed_policy_constraints() -> None:
    # Rust: constraint_error_includes_requirement_source for approval/reviewer constraints.
    source = RequirementSource.system_requirements_toml("/tmp/requirements.toml")
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        source,
        ConfigRequirementsToml.from_toml(
            """
            allowed_approval_policies = ["on-request"]
            allowed_approvals_reviewers = ["auto_review"]
            """
        ),
    )

    requirements = ConfigRequirements.from_sources(target)
    assert requirements.approval_policy.value.get() == AskForApproval.ON_REQUEST
    assert requirements.approvals_reviewer.value.get() == ApprovalsReviewer.AUTO_REVIEW
    with pytest.raises(ConstraintError, match="set by /tmp/requirements.toml"):
        requirements.approval_policy.value.can_set(AskForApproval.NEVER)
    with pytest.raises(ConstraintError, match="approvals_reviewer"):
        requirements.approvals_reviewer.value.can_set(ApprovalsReviewer.USER)


def test_config_requirements_from_sources_parses_legacy_approvals_reviewer_value() -> None:
    # Rust: deserialize_legacy_allowed_approvals_reviewer.
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        RequirementSource.unknown(),
        ConfigRequirementsToml.from_toml(
            'allowed_approvals_reviewers = ["guardian_subagent", "user"]\n'
        ),
    )

    requirements = ConfigRequirements.from_sources(target)
    assert requirements.approvals_reviewer.value.get() == ApprovalsReviewer.AUTO_REVIEW
    requirements.approvals_reviewer.value.can_set(ApprovalsReviewer.USER)


def test_config_requirements_from_sources_web_search_allows_disabled_even_when_not_listed() -> None:
    source = RequirementSource.cloud_requirements()
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        source,
        ConfigRequirementsToml(allowed_web_search_modes=(WebSearchModeRequirement.LIVE,)),
    )

    requirements = ConfigRequirements.from_sources(target)
    assert requirements.web_search_mode.value.get() == WebSearchMode.LIVE
    requirements.web_search_mode.value.can_set(WebSearchMode.DISABLED)
    with pytest.raises(ConstraintError, match="web_search_mode"):
        requirements.web_search_mode.value.can_set(WebSearchMode.CACHED)


def test_config_requirements_from_sources_builds_sandbox_mode_constraint() -> None:
    # Rust: ConfigRequirements::try_from allowed_sandbox_modes maps candidate
    # PermissionProfile values through sandbox_mode_requirement_for_permission_profile.
    source = RequirementSource.system_requirements_toml("/tmp/requirements.toml")
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        source,
        ConfigRequirementsToml(
            allowed_sandbox_modes=(
                SandboxModeRequirement.READ_ONLY,
                SandboxModeRequirement.WORKSPACE_WRITE,
            )
        ),
    )

    requirements = ConfigRequirements.from_sources(target)
    assert requirements.permission_profile.value.get() == PermissionProfile.read_only()
    requirements.permission_profile.value.can_set(PermissionProfile.workspace_write())
    with pytest.raises(ConstraintError, match="sandbox_mode"):
        requirements.permission_profile.value.can_set(PermissionProfile.disabled())


def test_config_requirements_from_sources_rejects_sandbox_modes_without_read_only() -> None:
    # Rust requires read-only in allowed_sandbox_modes so the default profile can
    # always be represented.
    source = RequirementSource.cloud_requirements()
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        source,
        ConfigRequirementsToml(
            allowed_sandbox_modes=(SandboxModeRequirement.WORKSPACE_WRITE,),
        ),
    )

    with pytest.raises(ConstraintError, match="must include 'read-only'"):
        ConfigRequirements.from_sources(target)


def test_sandbox_mode_requirement_for_permission_profile_matches_rust_mapping() -> None:
    # Rust: sandbox_mode_requirement_for_permission_profile.
    assert sandbox_mode_requirement_for_permission_profile(PermissionProfile.read_only()) is SandboxModeRequirement.READ_ONLY
    assert (
        sandbox_mode_requirement_for_permission_profile(PermissionProfile.workspace_write())
        is SandboxModeRequirement.WORKSPACE_WRITE
    )
    assert (
        sandbox_mode_requirement_for_permission_profile(PermissionProfile.disabled())
        is SandboxModeRequirement.DANGER_FULL_ACCESS
    )
    assert (
        sandbox_mode_requirement_for_permission_profile(PermissionProfile.external(NetworkSandboxPolicy.ENABLED))
        is SandboxModeRequirement.EXTERNAL_SANDBOX
    )


def test_config_requirements_from_sources_projects_network_and_filesystem() -> None:
    source = RequirementSource.cloud_requirements()
    permissions = PermissionsRequirementsToml.from_mapping({"filesystem": {"deny_read": ["/tmp/private"]}})
    network = ConfigRequirementsToml.from_toml(
        """
        [experimental_network]
        enabled = true
        allowed_domains = ["example.com"]
        """
    ).network
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        source,
        ConfigRequirementsToml(
            network=network,
            permissions=permissions,
        ),
    )

    requirements = ConfigRequirements.from_sources(target)
    assert requirements.network.value.enabled is True
    assert requirements.network.value.domains.allowed_domains() == ["example.com"]
    assert requirements.filesystem.value.deny_read[0].as_str().endswith("private")


def test_config_requirements_from_sources_parses_exec_policy_rules() -> None:
    # Rust: deserialize_exec_policy_requirements.
    source = RequirementSource.unknown()
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        source,
        ConfigRequirementsToml.from_toml(
            """
            [rules]
            prefix_rules = [
                { pattern = [{ token = "rm" }], decision = "forbidden" },
            ]
            """
        ),
    )

    requirements = ConfigRequirements.from_sources(target)
    assert requirements.exec_policy_source() == source
    assert requirements.exec_policy is not None
    rule = requirements.exec_policy.value.prefix_rules[0]
    assert rule.pattern == ("rm",)
    assert rule.decision is Decision.FORBIDDEN


def test_config_requirements_from_sources_exec_policy_error_includes_source() -> None:
    # Rust: exec_policy_error_includes_requirement_source.
    source = RequirementSource.system_requirements_toml("/tmp/requirements.toml")
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        source,
        ConfigRequirementsToml.from_toml(
            """
            [rules]
            prefix_rules = [
                { pattern = [{ token = "rm" }] },
            ]
            """
        ),
    )

    with pytest.raises(ConstraintError) as caught:
        ConfigRequirements.from_sources(target)

    assert caught.value == ConstraintError.exec_policy_parse(
        requirement_source=source,
        reason="rules prefix_rule at index 0 is missing a decision",
    )


def test_config_requirements_merge_unset_fields_does_not_overwrite_existing_hooks() -> None:
    # Rust: merge_unset_fields_does_not_overwrite_existing_hooks.
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        RequirementSource.cloud_requirements(),
        ConfigRequirementsToml.from_toml(
            """
            [hooks]
            managed_dir = "/cloud/hooks"

            [[hooks.PreToolUse]]
            matcher = "^Bash$"

            [[hooks.PreToolUse.hooks]]
            type = "command"
            command = "python3 /cloud/hooks/pre.py"
            """
        ),
    )
    target.merge_unset_fields(
        RequirementSource.system_requirements_toml("/tmp/requirements.toml"),
        ConfigRequirementsToml.from_toml(
            """
            [hooks]
            managed_dir = "/system/hooks"

            [[hooks.PreToolUse]]
            matcher = "^Bash$"

            [[hooks.PreToolUse.hooks]]
            type = "command"
            command = "python3 /system/hooks/pre.py"
            """
        ),
    )

    assert target.hooks.value.managed_dir == Path("/cloud/hooks")
    assert target.hooks.source == RequirementSource.cloud_requirements()
    assert target.into_toml().hooks.managed_dir == Path("/cloud/hooks")


def test_config_requirements_from_sources_managed_hooks_rejects_drift() -> None:
    # Rust: managed_hooks_constraint_rejects_drift.
    requirements = ConfigRequirements.from_sources(
        _with_unknown_source(
            ConfigRequirementsToml.from_toml(
                """
                [hooks]
                managed_dir = "/enterprise/hooks"

                [[hooks.PreToolUse]]
                matcher = "^Bash$"

                [[hooks.PreToolUse.hooks]]
                type = "command"
                command = "python3 /enterprise/hooks/pre.py"
                """
            )
        )
    )

    assert requirements.managed_hooks is not None
    with pytest.raises(ConstraintError, match="hooks"):
        requirements.managed_hooks.value.set(
            ManagedHooksRequirementsToml(managed_dir=Path("/other/hooks"))
        )


def test_config_requirements_from_sources_ignores_empty_managed_hooks() -> None:
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        RequirementSource.unknown(),
        ConfigRequirementsToml(hooks=ManagedHooksRequirementsToml(managed_dir=Path("/enterprise/hooks"))),
    )

    requirements = ConfigRequirements.from_sources(target)
    assert requirements.managed_hooks is None


def test_config_requirements_from_sources_rejects_empty_allowed_lists() -> None:
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(
        RequirementSource.cloud_requirements(),
        ConfigRequirementsToml(allowed_approval_policies=()),
    )

    with pytest.raises(ConstraintError, match="allowed_approval_policies"):
        ConfigRequirements.from_sources(target)


def _with_unknown_source(config: ConfigRequirementsToml) -> ConfigRequirementsWithSources:
    target = ConfigRequirementsWithSources()
    target.merge_unset_fields(RequirementSource.unknown(), config)
    return target
