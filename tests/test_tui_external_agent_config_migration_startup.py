import asyncio
from pathlib import Path

import pytest

from pycodex.tui.external_agent_config_migration import ExternalAgentConfigMigrationItem
from pycodex.tui.external_agent_config_migration_startup import (
    EXTERNAL_CONFIG_MIGRATION_PROMPT_COOLDOWN_SECS,
    Config,
    ExternalAgentConfigMigrationStartupOutcome,
    FeatureSet,
    external_agent_config_migration_success_message,
    external_config_migration_last_prompted_at,
    external_config_migration_project_key,
    handle_external_agent_config_migration_prompt_if_needed,
    is_external_config_migration_scope_cooling_down,
    persist_external_agent_config_migration_prompt_dismissal,
    persist_external_agent_config_migration_prompt_shown,
    should_show_external_agent_config_migration_prompt,
    visible_external_agent_config_migration_items,
)


def run(coro):
    return asyncio.run(coro)


def item(item_type="Config", description="", cwd=None):
    return ExternalAgentConfigMigrationItem(item_type=item_type, description=description, cwd=cwd)


def test_visible_external_agent_config_migration_items_omits_hidden_scopes_matches_rust():
    config = Config()
    config.notices.external_config_migration_prompts.home = True
    config.notices.external_config_migration_prompts.projects["/tmp/project"] = True

    visible = visible_external_agent_config_migration_items(
        config,
        [
            item("Config", "home", None),
            item("AgentsMd", "project", Path("/tmp/project")),
            item("Skills", "other project", Path("/tmp/other")),
        ],
        1_760_000_000,
    )

    assert visible == [item("Skills", "other project", Path("/tmp/other"))]


def test_visible_external_agent_config_migration_items_omits_recently_prompted_scopes_matches_rust():
    config = Config()
    prompts = config.notices.external_config_migration_prompts
    prompts.home_last_prompted_at = 1_760_000_000
    prompts.project_last_prompted_at["/tmp/project"] = 1_760_000_000

    visible = visible_external_agent_config_migration_items(
        config,
        [
            item("Config", "home", None),
            item("AgentsMd", "project", Path("/tmp/project")),
            item("Skills", "other project", Path("/tmp/other")),
        ],
        1_760_000_000 + EXTERNAL_CONFIG_MIGRATION_PROMPT_COOLDOWN_SECS - 1,
    )

    assert visible == [item("Skills", "other project", Path("/tmp/other"))]


def test_external_config_migration_scope_cooldown_expires_after_five_days_matches_rust():
    config = Config()
    config.notices.external_config_migration_prompts.home_last_prompted_at = 1_760_000_000

    assert is_external_config_migration_scope_cooling_down(
        config,
        None,
        1_760_000_000 + EXTERNAL_CONFIG_MIGRATION_PROMPT_COOLDOWN_SECS - 1,
    )
    assert not is_external_config_migration_scope_cooling_down(
        config,
        None,
        1_760_000_000 + EXTERNAL_CONFIG_MIGRATION_PROMPT_COOLDOWN_SECS,
    )


def test_external_agent_config_migration_success_message_mentions_plugins_when_present_matches_rust():
    message = external_agent_config_migration_success_message(
        [item("Config"), item("Plugins")]
    )

    assert message == (
        "External config migration completed. Plugin migration is still in progress and may take a few minutes."
    )


def test_external_agent_config_migration_success_message_omits_plugins_copy_when_absent_matches_rust():
    assert external_agent_config_migration_success_message([item("AgentsMd")]) == (
        "External config migration completed successfully."
    )


def test_external_agent_config_migration_prompt_requires_trust_nux_entry_matches_rust():
    config = Config(features=FeatureSet({"ExternalMigration"}))

    assert not should_show_external_agent_config_migration_prompt(config, False)
    assert should_show_external_agent_config_migration_prompt(config, True)


def test_project_key_and_last_prompt_lookup_match_scope_rules():
    config = Config()
    prompts = config.notices.external_config_migration_prompts
    prompts.home_last_prompted_at = 10
    prompts.project_last_prompted_at["/tmp/project"] = 20

    assert external_config_migration_project_key(Path("/tmp/project")) == "/tmp/project"
    assert external_config_migration_last_prompted_at(config, None) == 10
    assert external_config_migration_last_prompted_at(config, Path("/tmp/project")) == 20
    assert external_config_migration_last_prompted_at(config, Path("/tmp/other")) is None


def test_persist_prompt_shown_updates_home_and_project_timestamps_semantically():
    config = Config()

    run(
        persist_external_agent_config_migration_prompt_shown(
            config,
            [item(cwd=None), item(cwd=Path("/tmp/project"))],
            123,
        )
    )

    prompts = config.notices.external_config_migration_prompts
    assert prompts.home_last_prompted_at == 123
    assert prompts.project_last_prompted_at == {"/tmp/project": 123}
    assert ("home_last_prompted_at", 123) in config.applied_edits


def test_persist_prompt_dismissal_hides_home_and_unique_projects_semantically():
    config = Config()

    run(
        persist_external_agent_config_migration_prompt_dismissal(
            config,
            [item(cwd=None), item(cwd=Path("/tmp/project")), item(cwd=Path("/tmp/project"))],
        )
    )

    prompts = config.notices.external_config_migration_prompts
    assert prompts.home is True
    assert prompts.projects == {"/tmp/project": True}
    assert ("project", "/tmp/project", True) in config.applied_edits


class FakeAppServer:
    def __init__(self, detected, import_error=None):
        self.detected = detected
        self.imported = []
        self.import_error = import_error

    async def external_agent_config_detect(self, params):
        return {"items": list(self.detected)}

    async def external_agent_config_import(self, items):
        if self.import_error is not None:
            raise self.import_error
        self.imported.append(list(items))
        return None


def test_handle_prompt_skip_and_proceed_paths_are_semantic_runtime_slice():
    selected = [item("AgentsMd", cwd=Path("/tmp/project"))]
    config = Config(features=FeatureSet({"ExternalMigration"}), cwd=Path("/tmp/project"))
    app_server = FakeAppServer(selected)

    async def prompt_runner(tui, detected, selected_items, error):
        return type("Outcome", (), {"kind": "proceed", "items": tuple(selected_items)})()

    result = run(
        handle_external_agent_config_migration_prompt_if_needed(
            None,
            app_server,
            config,
            entered_trust_nux=True,
            prompt_runner=prompt_runner,
            now_unix_seconds=99,
        )
    )

    assert result == ExternalAgentConfigMigrationStartupOutcome.Continue(
        "External config migration completed successfully."
    )
    assert app_server.imported == [selected]


def test_handle_prompt_retries_after_import_failure_with_error_message():
    selected = [item("AgentsMd", cwd=Path("/tmp/project"))]
    config = Config(features=FeatureSet({"ExternalMigration"}), cwd=Path("/tmp/project"))
    prompt_errors = []

    class FailsOnceAppServer(FakeAppServer):
        def __init__(self, detected):
            super().__init__(detected)
            self.attempts = 0

        async def external_agent_config_import(self, items):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("temporary import failure")
            self.imported.append(list(items))
            return None

    app_server = FailsOnceAppServer(selected)

    async def prompt_runner(tui, detected, selected_items, error):
        prompt_errors.append(error)
        return type("Outcome", (), {"kind": "proceed", "items": tuple(selected_items)})()

    result = run(
        handle_external_agent_config_migration_prompt_if_needed(
            None,
            app_server,
            config,
            entered_trust_nux=True,
            prompt_runner=prompt_runner,
            now_unix_seconds=99,
        )
    )

    assert result == ExternalAgentConfigMigrationStartupOutcome.Continue(
        "External config migration completed successfully."
    )
    assert prompt_errors == [None, "Migration failed: temporary import failure"]
    assert app_server.imported == [selected]


def test_handle_prompt_requires_runner_when_visible_items_need_tui():
    config = Config(features=FeatureSet({"ExternalMigration"}))
    app_server = FakeAppServer([item("Config")])

    with pytest.raises(NotImplementedError):
        run(
            handle_external_agent_config_migration_prompt_if_needed(
                None,
                app_server,
                config,
                entered_trust_nux=True,
                now_unix_seconds=1,
            )
        )
