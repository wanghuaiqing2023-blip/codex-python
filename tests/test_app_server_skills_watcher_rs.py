import asyncio
from pathlib import Path

from pycodex.app_server.skills_watcher import (
    WATCHER_THROTTLE_INTERVAL_SECONDS,
    WATCHER_THROTTLE_INTERVAL_TEST_SECONDS,
    event_loop_iteration_projection,
    event_loop_spawn_projection,
    register_thread_config,
    shutdown_projection,
    skills_watcher_new_projection,
    watch_paths_from_skill_roots,
)


class FakeConfig:
    cwd = Path("project")
    config_layer_stack = ("user", "project")

    def plugins_config_input(self):
        return {"plugins": True}

    def bundled_skills_enabled(self) -> bool:
        return True


class FakePluginOutcome:
    def effective_plugin_skill_roots(self):
        return (Path("plugin-skills"),)


class FakePluginsManager:
    def __init__(self) -> None:
        self.received_input = None

    async def plugins_for_config(self, plugins_input):
        self.received_input = plugins_input
        return FakePluginOutcome()


class FakeSkillsManager:
    def __init__(self) -> None:
        self.received_input = None
        self.received_filesystem = None

    async def skill_roots_for_config(self, skills_input, filesystem):
        self.received_input = skills_input
        self.received_filesystem = filesystem
        return [{"path": "repo-skills"}, Path("user-skills")]


class FakeEnvironment:
    def __init__(self, *, remote: bool) -> None:
        self.remote = remote

    def is_remote(self) -> bool:
        return self.remote

    def get_filesystem(self):
        return "local-fs"


class FakeEnvironmentManager:
    def __init__(self, environments):
        self.environments = dict(environments)

    def get_environment(self, environment_id):
        return self.environments.get(environment_id)


class FakeThreadManager:
    def __init__(self, environments) -> None:
        self._environment_manager = FakeEnvironmentManager(environments)
        self._plugins_manager = FakePluginsManager()
        self._skills_manager = FakeSkillsManager()

    def environment_manager(self):
        return self._environment_manager

    def plugins_manager(self):
        return self._plugins_manager

    def skills_manager(self):
        return self._skills_manager


def test_skills_watcher_new_projection_records_real_watcher_setup() -> None:
    # Rust: SkillsWatcher::new registers subscriber, creates shutdown token/drop guard, spawns loop.
    projection = skills_watcher_new_projection()

    assert projection.file_watcher_kind == "real"
    assert projection.subscriber_registered is True
    assert projection.shutdown_token_created is True
    assert projection.shutdown_drop_guard_created is True
    assert projection.event_loop_spawned is True
    assert projection.warning is None


def test_skills_watcher_new_projection_falls_back_to_noop_watcher_on_init_error() -> None:
    # Rust: FileWatcher::new error warns and uses FileWatcher::noop().
    projection = skills_watcher_new_projection(file_watcher_error="denied")

    assert projection.file_watcher_kind == "noop"
    assert projection.warning == "failed to initialize skills file watcher: denied"


def test_register_thread_config_without_environment_selection_returns_default_registration() -> None:
    # Rust: empty environments returns WatchRegistration::default().
    projection = asyncio.run(register_thread_config(FakeConfig(), FakeThreadManager({}), ()))

    assert projection.reason == "no_environment_selection"
    assert projection.registration.to_mapping() == {"paths": []}


def test_register_thread_config_unknown_environment_warns_and_returns_default() -> None:
    # Rust: unknown selected environment warns and returns WatchRegistration::default().
    projection = asyncio.run(
        register_thread_config(FakeConfig(), FakeThreadManager({}), ({"environment_id": "missing"},))
    )

    assert projection.reason == "unknown_environment"
    assert projection.warning == "failed to register skills watcher for unknown environment `missing`"
    assert projection.registration.to_mapping() == {"paths": []}


def test_register_thread_config_remote_environment_returns_default() -> None:
    # Rust: remote environments are not watched.
    manager = FakeThreadManager({"remote": FakeEnvironment(remote=True)})
    projection = asyncio.run(register_thread_config(FakeConfig(), manager, ({"environment_id": "remote"},)))

    assert projection.reason == "remote_environment"
    assert projection.registration.to_mapping() == {"paths": []}


def test_register_thread_config_local_environment_builds_skills_input_and_recursive_roots() -> None:
    # Rust: local environment builds SkillsLoadInput and registers recursive WatchPath roots.
    manager = FakeThreadManager({"local": FakeEnvironment(remote=False)})
    projection = asyncio.run(register_thread_config(FakeConfig(), manager, ({"environment_id": "local"},)))

    assert projection.reason == "registered"
    assert projection.environment_id == "local"
    assert projection.skills_input is not None
    assert projection.skills_input.cwd == Path("project")
    assert projection.skills_input.effective_skill_roots == (Path("plugin-skills"),)
    assert projection.skills_input.config_layer_stack == ("user", "project")
    assert projection.skills_input.bundled_skills_enabled is True
    assert projection.registration.to_mapping() == {
        "paths": [
            {"path": "repo-skills", "recursive": True},
            {"path": "user-skills", "recursive": True},
        ]
    }


def test_watch_paths_from_skill_roots_marks_every_root_recursive() -> None:
    # Rust: skill roots are mapped to WatchPath { recursive: true }.
    paths = watch_paths_from_skill_roots(({"path": "a"}, Path("b")))

    assert [path.to_mapping() for path in paths] == [
        {"path": "a", "recursive": True},
        {"path": "b", "recursive": True},
    ]


def test_event_loop_iteration_clears_cache_and_sends_skills_changed() -> None:
    # Rust: each watch event clears cache and sends ServerNotification::SkillsChanged.
    projection = event_loop_iteration_projection(object())

    assert projection.actions == ("clear_skills_cache", "send_skills_changed")
    assert projection.notification is not None
    assert projection.notification.to_mapping() == {
        "type": "SkillsChanged",
        "method": "skills/changed",
        "params": {},
    }


def test_event_loop_iteration_none_breaks_loop() -> None:
    # Rust: rx.recv() None breaks the listener loop.
    assert event_loop_iteration_projection(None).actions == ("break",)


def test_event_loop_spawn_without_runtime_warns_and_returns() -> None:
    # Rust: Handle::try_current failure warns and skips listener.
    assert event_loop_spawn_projection(tokio_runtime_available=False).actions == ("warn_no_tokio_runtime", "return")


def test_shutdown_projection_cancels_shutdown_token_and_constants_match_rust_cfgs() -> None:
    # Rust: shutdown cancels the token; throttle is 10s normally and 50ms under cfg(test).
    assert shutdown_projection() == ("cancel_shutdown_token",)
    assert WATCHER_THROTTLE_INTERVAL_SECONDS == 10
    assert WATCHER_THROTTLE_INTERVAL_TEST_SECONDS == 0.05
