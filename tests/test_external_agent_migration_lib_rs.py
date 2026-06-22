"""Parity tests for ``codex-external-agent-migration/src/lib.rs``."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from pycodex.external_agent_migration import (
    build_mcp_config_from_external,
    count_missing_commands,
    count_missing_subagents,
    hook_migration_event_names,
    hooks_migration_description,
    import_commands,
    import_hooks,
    import_subagents,
    missing_command_names,
    missing_subagent_names,
    rewrite_external_agent_terms,
)


def test_mcp_migration_skips_placeholder_args_and_unsupported_transports(tmp_path: Path) -> None:
    # Rust source: mcp_migration_skips_placeholder_args and
    # mcp_migration_skips_unsupported_transports.
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "db": {"command": "db-server", "args": ["${DATABASE_URL}"]},
                    "legacy-sse": {"type": "sse", "url": "https://example.invalid/sse"},
                    "vault": {
                        "url": "https://example.invalid/vault",
                        "headers": {"Authorization": "Bearer ${VAULT_TOKEN:-dev-token}"},
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    assert build_mcp_config_from_external(tmp_path) == {
        "mcp_servers": {
            "vault": {
                "url": "https://example.invalid/vault",
                "bearer_token_env_var": "VAULT_TOKEN",
            }
        }
    }


def test_mcp_migration_project_entries_and_home_preserve_repo_servers(tmp_path: Path) -> None:
    # Rust source: matching project entries are read from repo/home
    # `.claude.json`, and repo servers win over home project entries.
    project = tmp_path / "repo"
    project.mkdir()
    external_agent_home = tmp_path / ".claude"
    external_agent_home.mkdir()
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"shared": {"command": "repo-server"}}}),
        encoding="utf-8",
    )
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "projects": {
                    str(project): {
                        "mcpServers": {
                            "home-only": {"command": "home-only-server"},
                            "shared": {"command": "home-server"},
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert build_mcp_config_from_external(project, external_agent_home) == {
        "mcp_servers": {
            "home-only": {"command": "home-only-server"},
            "shared": {"command": "repo-server"},
        }
    }


def test_mcp_migration_skips_disabled_servers(tmp_path: Path) -> None:
    # Rust source: mcp_migration_skips_disabled_servers.
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "enabled": {"command": "enabled-server"},
                    "explicit-disabled": {"command": "disabled-server", "disabled": True},
                    "not-enabled": {"command": "not-enabled-server"},
                }
            }
        ),
        encoding="utf-8",
    )

    assert build_mcp_config_from_external(
        tmp_path,
        settings={
            "enabledMcpjsonServers": ["enabled"],
            "disabledMcpjsonServers": ["explicit-disabled"],
        },
    ) == {"mcp_servers": {"enabled": {"command": "enabled-server"}}}


def test_import_hooks_filters_unsupported_handlers_and_rewrites_paths(tmp_path: Path) -> None:
    # Rust source: hook_migration_ignores_unsupported_handlers and
    # hook_command_paths_rewrite_to_target_hook_dir.
    source = tmp_path / ".claude"
    hooks_dir = source / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "approve.py").write_text("new script", encoding="utf-8")
    (source / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "if": "tool_input.command contains 'rm'",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 .claude/hooks/policy_gate.py",
                                }
                            ],
                        },
                        {
                            "matcher": "Edit",
                            "hooks": [
                                {
                                    "type": "command",
                                    "if": "Bash(rm *)",
                                    "command": "python3 .claude/hooks/policy_gate.py",
                                },
                                {"type": "http", "url": "https://example.invalid/hook"},
                            ],
                        },
                    ],
                    "PermissionRequest": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 .claude/hooks/approve.py",
                                }
                            ],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    target = tmp_path / ".codex" / "hooks.json"

    assert hooks_migration_description(source, target) == f"Migrate hooks from {source} to {target}"
    assert hook_migration_event_names(source, target) == ["PermissionRequest"]
    assert import_hooks(source, target) is True

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {
        "hooks": {
            "PermissionRequest": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 '{tmp_path / '.codex' / 'hooks' / 'approve.py'}'",
                        }
                    ],
                }
            ]
        }
    }
    assert (tmp_path / ".codex" / "hooks" / "approve.py").read_text(encoding="utf-8") == "new script"


def test_import_hooks_honors_disable_override_and_drops_negative_timeouts(tmp_path: Path) -> None:
    # Rust source: hook_migration_honors_settings_local_disable_override and
    # hook_migration_drops_negative_timeouts.
    source = tmp_path / ".claude"
    source.mkdir()
    (source / "settings.json").write_text(
        json.dumps({"disableAllHooks": True, "hooks": {"SessionStart": [{"hooks": [{"command": "echo project"}]}]}}),
        encoding="utf-8",
    )
    (source / "settings.local.json").write_text(
        json.dumps(
            {
                "disableAllHooks": False,
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "local",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "echo local",
                                    "timeout": -1,
                                }
                            ],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    target = tmp_path / ".codex" / "hooks.json"
    assert import_hooks(source, target) is True
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": "echo project"}]},
                {"matcher": "local", "hooks": [{"type": "command", "command": "echo local"}]},
            ]
        }
    }


def test_import_hooks_does_not_overwrite_existing_target_scripts(tmp_path: Path) -> None:
    # Rust source: hook_script_copy_keeps_existing_target_scripts.
    source = tmp_path / ".claude"
    source_hooks = source / "hooks"
    target_hooks = tmp_path / ".codex" / "hooks"
    source_hooks.mkdir(parents=True)
    target_hooks.mkdir(parents=True)
    (source_hooks / "check.py").write_text("new script", encoding="utf-8")
    (target_hooks / "check.py").write_text("existing script", encoding="utf-8")
    (source / "settings.json").write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": "python3 .claude/hooks/check.py"}]}]}}),
        encoding="utf-8",
    )

    assert import_hooks(source, tmp_path / ".codex" / "hooks.json") is True
    assert (target_hooks / "check.py").read_text(encoding="utf-8") == "existing script"


def test_subagent_import_requires_fields_and_renders_codex_toml(tmp_path: Path) -> None:
    # Rust source: subagent_requires_minimum_codex_agent_fields and
    # subagent_preserves_default_model_when_source_model_is_present.
    source_agents = tmp_path / "agents"
    target_agents = tmp_path / ".codex" / "agents"
    source_agents.mkdir()
    (source_agents / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Review claude code\nmodel: source-opus\neffort: max\npermissionMode: acceptEdits\n---\nReview CLAUDE.md carefully.\n",
        encoding="utf-8",
    )
    (source_agents / "incomplete.md").write_text("---\nname: incomplete\n---\nBody.\n", encoding="utf-8")

    assert missing_subagent_names(source_agents, target_agents) == ["reviewer"]
    assert count_missing_subagents(source_agents, target_agents) == 1
    assert import_subagents(source_agents, target_agents) == 1

    rendered = tomllib.loads((target_agents / "reviewer.toml").read_text(encoding="utf-8"))
    assert rendered == {
        "name": "reviewer",
        "description": "Review Codex",
        "model_reasoning_effort": "xhigh",
        "sandbox_mode": "workspace-write",
        "developer_instructions": "Review AGENTS.md carefully.",
    }


def test_subagent_accepts_crlf_frontmatter_and_dotted_file_stems(tmp_path: Path) -> None:
    # Rust source: frontmatter_accepts_crlf_delimiters and
    # subagent_target_preserves_dotted_file_stem.
    source_agents = tmp_path / "agents"
    target_agents = tmp_path / ".codex" / "agents"
    source_agents.mkdir()
    (source_agents / "security.audit.md").write_text(
        "---\r\nname: security\r\ndescription: Review code\r\n---\r\nInvestigate carefully.\r\n",
        encoding="utf-8",
    )

    assert import_subagents(source_agents, target_agents) == 1
    assert (target_agents / "security.audit.toml").exists()


def test_command_import_names_nested_paths_and_skips_runtime_expansion(tmp_path: Path) -> None:
    # Rust source: command_skill_names_include_nested_paths and
    # commands_with_provider_runtime_expansion_are_skipped.
    source_commands = tmp_path / "commands"
    target_skills = tmp_path / ".codex" / "skills"
    (source_commands / "pr").mkdir(parents=True)
    (source_commands / "pr" / "review.md").write_text(
        "---\ndescription: Review PR with claude\n---\nReview CLAUDE.md\n",
        encoding="utf-8",
    )
    (source_commands / "deploy.md").write_text(
        "---\ndescription: Deploy\n---\nDeploy $ARGUMENTS from @release.yaml\n",
        encoding="utf-8",
    )

    assert missing_command_names(source_commands, target_skills) == ["source-command-pr-review"]
    assert count_missing_commands(source_commands, target_skills) == 1
    assert import_commands(source_commands, target_skills) == 1
    skill = (target_skills / "source-command-pr-review" / "SKILL.md").read_text(encoding="utf-8")
    assert "description: \"Review PR with Codex\"" in skill
    assert "Review AGENTS.md" in skill


def test_command_slug_collisions_are_skipped(tmp_path: Path) -> None:
    # Rust source: command_slug_collisions_are_skipped.
    source_commands = tmp_path / "commands"
    target_skills = tmp_path / ".codex" / "skills"
    source_commands.mkdir()
    (source_commands / "foo-bar.md").write_text("---\ndescription: First\n---\nRun first.\n", encoding="utf-8")
    (source_commands / "foo_bar.md").write_text("---\ndescription: Second\n---\nRun second.\n", encoding="utf-8")

    assert missing_command_names(source_commands, target_skills) == []
    assert import_commands(source_commands, target_skills) == 0


def test_rewrite_external_agent_terms_obeys_word_boundaries() -> None:
    # Rust source: rewrite_external_agent_terms uses case-insensitive word boundaries.
    assert rewrite_external_agent_terms("CLAUDE.md and claude-code, not myclaude_var") == (
        "AGENTS.md and Codex, not myclaude_var"
    )
