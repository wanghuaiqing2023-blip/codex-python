from pathlib import Path
from tempfile import TemporaryDirectory

from pycodex.app_server.config.external_agent_config import (
    EXTERNAL_AGENT_CONFIG_DETECT_METRIC,
    EXTERNAL_AGENT_CONFIG_IMPORT_METRIC,
    EXTERNAL_AGENT_CONFIG_MD,
    EXTERNAL_AGENT_DIR,
    EXTERNAL_OFFICIAL_MARKETPLACE_NAME,
    EXTERNAL_OFFICIAL_MARKETPLACE_SOURCE,
    ExternalAgentConfigDetectOptions,
    ExternalAgentConfigMigrationItem,
    ExternalAgentConfigMigrationItemType,
    ExternalAgentConfigService,
    MarketplaceImportSource,
    MigrationDetails,
    NamedMigration,
    PendingPluginImport,
    PluginImportOutcome,
    PluginsMigration,
    build_config_from_external,
    collect_enabled_plugins,
    collect_marketplace_import_sources,
    default_external_agent_home,
    is_empty_toml_table,
    json_env_value_to_string,
    looks_like_relative_local_path,
    merge_json_settings,
    merge_missing_toml_values,
    migrated_mcp_server_names,
    migration_metric_tags,
    named_migrations,
    replace_case_insensitive_with_boundaries,
    resolve_external_marketplace_source,
    rewrite_external_agent_terms,
)


def test_external_agent_config_constants_match_rust():
    # Rust contract: constants at the top of src/config/external_agent_config.rs.
    assert EXTERNAL_AGENT_CONFIG_DETECT_METRIC == "codex.external_agent_config.detect"
    assert EXTERNAL_AGENT_CONFIG_IMPORT_METRIC == "codex.external_agent_config.import"
    assert EXTERNAL_AGENT_DIR == ".claude"
    assert EXTERNAL_AGENT_CONFIG_MD == "CLAUDE.md"
    assert EXTERNAL_OFFICIAL_MARKETPLACE_NAME == "claude-plugins-official"
    assert EXTERNAL_OFFICIAL_MARKETPLACE_SOURCE == "anthropics/claude-plugins-official"


def test_external_agent_config_data_shapes_match_rust_defaults():
    # Rust contract: migration detail/outcome structs derive Default with empty
    # vectors, and migration items carry item type, description, cwd, and details.
    details = MigrationDetails(
        plugins=(PluginsMigration("acme-tools", ("formatter",)),),
        mcp_servers=(NamedMigration("docs"),),
    )
    item = ExternalAgentConfigMigrationItem(
        ExternalAgentConfigMigrationItemType.PLUGINS,
        "Migrate enabled plugins",
        cwd=Path("/repo"),
        details=details,
    )

    assert ExternalAgentConfigDetectOptions(include_home=True).cwds is None
    assert MigrationDetails() == MigrationDetails((), (), (), (), (), ())
    assert PendingPluginImport(Path("/repo"), details).details is details
    assert PluginImportOutcome() == PluginImportOutcome((), (), (), ())
    assert item.item_type is ExternalAgentConfigMigrationItemType.PLUGINS
    assert item.description == "Migrate enabled plugins"
    assert item.cwd == Path("/repo")
    assert item.details == details


def test_external_agent_session_source_path_accepts_only_existing_jsonl_under_projects():
    # Rust contract: external_agent_session_source_path canonicalizes both the
    # candidate and external projects root, accepts only .jsonl files under it,
    # returns None for missing/non-jsonl/outside paths.
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        external_home = root / ".claude"
        projects = external_home / "projects"
        session = projects / "repo" / "session.jsonl"
        outside = root / "outside.jsonl"
        non_jsonl = projects / "repo" / "session.txt"
        session.parent.mkdir(parents=True)
        session.write_text("{}", encoding="utf-8")
        outside.write_text("{}", encoding="utf-8")
        non_jsonl.write_text("{}", encoding="utf-8")

        service = ExternalAgentConfigService.new_for_test(root / ".codex", external_home)

        assert service.external_agent_session_source_path(session) == session.resolve()
        assert service.external_agent_session_source_path(non_jsonl) is None
        assert service.external_agent_session_source_path(outside) is None
        assert service.external_agent_session_source_path(projects / "repo" / "missing.jsonl") is None


def test_default_external_agent_home_prefers_home_then_userprofile_then_relative():
    # Rust contract: HOME wins over USERPROFILE and missing home falls back to .claude.
    assert default_external_agent_home({"HOME": "/home/me", "USERPROFILE": "C:/Users/me"}) == Path("/home/me/.claude")
    assert default_external_agent_home({"USERPROFILE": "C:/Users/me"}) == Path("C:/Users/me/.claude")
    assert default_external_agent_home({}) == Path(".claude")


def test_merge_json_settings_recursively_overrides_existing_values():
    # Rust contract: local settings recursively merge into project settings,
    # overriding existing leaves and inserting missing keys.
    existing = {
        "env": {"FOO": "project", "PROJECT_ONLY": "yes"},
        "sandbox": {"enabled": False, "network": {"allowLocalBinding": True}},
    }
    incoming = {"env": {"FOO": "local", "LOCAL_ONLY": True}, "sandbox": {"enabled": True}}

    assert merge_json_settings(existing, incoming) is existing
    assert existing == {
        "env": {"FOO": "local", "PROJECT_ONLY": "yes", "LOCAL_ONLY": True},
        "sandbox": {"enabled": True, "network": {"allowLocalBinding": True}},
    }


def test_collect_enabled_plugins_filters_disabled_and_invalid_plugin_ids():
    # Rust contract: enabledPlugins keeps only true values whose keys parse as PluginId.
    settings = {
        "enabledPlugins": {
            "formatter@acme-tools": True,
            "disabled@acme-tools": False,
            "not-a-plugin-id": True,
            "empty@": True,
        }
    }

    assert collect_enabled_plugins(settings) == ["formatter@acme-tools"]


def test_collect_marketplace_import_sources_resolves_sources_and_adds_official_marketplace():
    # Rust contract: extraKnownMarketplaces accepts repo/url/path/source fields,
    # resolves ./ and ../ paths against source_root, and adds the official
    # marketplace when an enabled plugin references it.
    settings = {
        "enabledPlugins": {
            "tool@claude-plugins-official": True,
            "formatter@local-tools": True,
        },
        "extraKnownMarketplaces": {
            "local-tools": {"source": {"path": "./marketplace", "ref": "main"}},
            "url-tools": {"url": "https://example.invalid/tools", "ref": "v1"},
            "empty": {"source": "   "},
        },
    }

    assert collect_marketplace_import_sources(settings, Path("/repo")) == {
        "claude-plugins-official": MarketplaceImportSource("anthropics/claude-plugins-official", None),
        "local-tools": MarketplaceImportSource(str(Path("/repo") / "./marketplace"), "main"),
        "url-tools": MarketplaceImportSource("https://example.invalid/tools", "v1"),
    }


def test_relative_local_path_detection_matches_rust_prefixes():
    # Rust contract: only ./, ../, . and .. are treated as relative local paths.
    assert looks_like_relative_local_path("./plugins")
    assert looks_like_relative_local_path("../plugins")
    assert looks_like_relative_local_path(".")
    assert looks_like_relative_local_path("..")
    assert not looks_like_relative_local_path("plugins/local")
    assert resolve_external_marketplace_source("./plugins", Path("/repo")) == str(Path("/repo") / "./plugins")
    assert resolve_external_marketplace_source("owner/repo", Path("/repo")) == "owner/repo"


def test_rewrite_external_agent_terms_matches_case_insensitive_boundary_behavior():
    # Rust contract: CLAUDE.md is rewritten first, then Claude product/name
    # spellings are replaced on ASCII word boundaries.
    source = "Claude Code\nclaude\nCLAUDE-CODE\nSee CLAUDE.md\npreclaude post_claude"
    assert rewrite_external_agent_terms(source) == (
        "Codex\nCodex\nCodex\nSee AGENTS.md\npreclaude post_claude"
    )
    assert replace_case_insensitive_with_boundaries("xclaude claude!", "claude", "Codex") == "xclaude Codex!"


def test_build_config_from_external_projects_supported_settings_only():
    # Rust contract: env scalar values become shell_environment_policy.set,
    # null/list/object are skipped, and sandbox.enabled true sets workspace-write.
    settings = {
        "model": "claude",
        "env": {
            "FOO": "bar",
            "CI": False,
            "MAX_RETRIES": 3,
            "IGNORED": None,
            "LIST": ["a"],
            "MAP": {"x": 1},
        },
        "sandbox": {"enabled": True, "network": {"allowLocalBinding": True}},
    }

    assert build_config_from_external(settings) == {
        "shell_environment_policy": {
            "inherit": "core",
            "set": {"FOO": "bar", "CI": "false", "MAX_RETRIES": "3"},
        },
        "sandbox_mode": "workspace-write",
    }


def test_json_env_value_to_string_matches_rust_json_value_cases():
    assert json_env_value_to_string("value") == "value"
    assert json_env_value_to_string(True) == "true"
    assert json_env_value_to_string(False) == "false"
    assert json_env_value_to_string(3) == "3"
    assert json_env_value_to_string(None) is None
    assert json_env_value_to_string(["a"]) is None
    assert json_env_value_to_string({"x": 1}) is None


def test_merge_missing_toml_values_only_inserts_missing_keys():
    # Rust contract: recursive table merge inserts missing keys but preserves
    # existing scalar values.
    existing = {"a": {"keep": "old"}, "scalar": "old"}
    incoming = {"a": {"keep": "new", "added": "yes"}, "scalar": "new", "new": {"nested": True}}

    assert merge_missing_toml_values(existing, incoming) is True
    assert existing == {"a": {"keep": "old", "added": "yes"}, "scalar": "old", "new": {"nested": True}}


def test_migrated_mcp_server_names_named_migrations_and_empty_table():
    assert migrated_mcp_server_names({"mcp_servers": {"docs": {}, "api": {}}}) == ["api", "docs"]
    assert named_migrations(["docs", "api"]) == [
        type(named_migrations(["docs"])[0])("docs"),
        type(named_migrations(["api"])[0])("api"),
    ]
    assert is_empty_toml_table({}) is True
    assert is_empty_toml_table({"x": 1}) is False
    assert is_empty_toml_table("not-table") is False


def test_migration_metric_tags_include_counts_only_for_skill_like_items():
    assert migration_metric_tags(ExternalAgentConfigMigrationItemType.CONFIG, 7) == [
        ("migration_type", "config")
    ]
    assert migration_metric_tags(ExternalAgentConfigMigrationItemType.SKILLS, 7) == [
        ("migration_type", "skills"),
        ("skills_count", "7"),
    ]
    assert migration_metric_tags(ExternalAgentConfigMigrationItemType.SUBAGENTS, None) == [
        ("migration_type", "subagents"),
        ("skills_count", "0"),
    ]
    assert migration_metric_tags(ExternalAgentConfigMigrationItemType.COMMANDS, 2) == [
        ("migration_type", "commands"),
        ("skills_count", "2"),
    ]
