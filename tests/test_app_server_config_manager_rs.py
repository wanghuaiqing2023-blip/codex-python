from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.app_server.config_manager import (
    Arg0DispatchPaths,
    ConfigBuildRequest,
    ConfigManager,
    ConfigOverrides,
    apply_runtime_feature_enablement,
    protected_feature_keys,
)
from pycodex.config import CloudRequirementsLoader, ConfigLayerStack, LoaderOverrides, NoopThreadConfigLoader
from pycodex.features import Feature


class FakeFeatures:
    def __init__(self) -> None:
        self.calls: list[tuple[Feature, bool]] = []

    def set_enabled(self, feature: Feature, enabled: bool) -> None:
        self.calls.append((feature, enabled))


@dataclass
class FakeConfig:
    cwd: Path = Path("C:/work")
    config_layer_stack: object = None
    features: FakeFeatures = None
    codex_self_exe: Path | None = None
    codex_linux_sandbox_exe: Path | None = None
    main_execve_wrapper_exe: Path | None = None

    def __post_init__(self) -> None:
        if self.config_layer_stack is None:
            self.config_layer_stack = ConfigLayerStack()
        if self.features is None:
            self.features = FakeFeatures()


def test_current_handles_and_replace_methods_match_rust_storage_contract() -> None:
    # Rust source: ConfigManager::new stores handles; current_* returns clones/handles, replacements swap loaders.
    initial_cloud = CloudRequirementsLoader()
    replacement_cloud = CloudRequirementsLoader()
    replacement_thread = NoopThreadConfigLoader()

    def cloud_factory(auth_manager: object, chatgpt_base_url: str, codex_home: Path) -> CloudRequirementsLoader:
        assert auth_manager == "auth"
        assert chatgpt_base_url == "https://chatgpt.example"
        assert codex_home == Path("C:/codex")
        return replacement_cloud

    manager = ConfigManager(
        Path("C:/codex"),
        [("model", "gpt-5")],
        cloud_requirements=initial_cloud,
        cloud_requirements_factory=cloud_factory,
    )

    assert manager.codex_home() == Path("C:/codex")
    assert manager.current_cli_overrides() == [("model", "gpt-5")]
    assert manager.current_cloud_requirements() is initial_cloud

    manager.replace_cloud_requirements_loader("auth", "https://chatgpt.example")
    manager.replace_thread_config_loader(replacement_thread)

    assert manager.current_cloud_requirements() is replacement_cloud
    assert manager.current_thread_config_loader() is replacement_thread


@pytest.mark.asyncio
async def test_load_with_cli_overrides_merges_request_and_extracts_bypass_hook_trust() -> None:
    # Rust source: load_with_cli_overrides removes bypass_hook_trust, requires bool, then chains CLI and request overrides.
    captured: list[ConfigBuildRequest] = []

    async def builder(request: ConfigBuildRequest) -> FakeConfig:
        captured.append(request)
        return FakeConfig()

    manager = ConfigManager(
        Path("C:/codex"),
        loader_overrides=LoaderOverrides(user_config_profile="work"),
        strict_config=True,
        config_builder=builder,
    )

    config = await manager.load_with_cli_overrides(
        [("model", "gpt-5")],
        {"approval_policy": "never", "bypass_hook_trust": True},
        ConfigOverrides(),
        Path("C:/repo"),
    )

    assert isinstance(config, FakeConfig)
    assert captured[0].cli_overrides == (("model", "gpt-5"), ("approval_policy", "never"))
    assert captured[0].strict_config is True
    assert captured[0].fallback_cwd == Path("C:/repo")
    assert captured[0].harness_overrides.bypass_hook_trust is True
    assert captured[0].loader_overrides.user_config_profile == "work"


@pytest.mark.asyncio
async def test_load_with_cli_overrides_rejects_non_bool_bypass_hook_trust() -> None:
    # Rust source: non-bool bypass_hook_trust maps to InvalidData with this exact message.
    manager = ConfigManager(Path("C:/codex"), config_builder=lambda _request: FakeConfig())

    with pytest.raises(ValueError, match="`bypass_hook_trust` override must be a boolean"):
        await manager.load_with_overrides({"bypass_hook_trust": "yes"}, ConfigOverrides())


@pytest.mark.asyncio
async def test_load_latest_config_for_thread_rebuilds_and_applies_runtime_state() -> None:
    # Rust source: load_latest_config_for_thread refreshes for thread cwd, rebuilds preserving session layers, then
    # applies runtime feature enablement and arg0 dispatch paths.
    refreshed = FakeConfig(cwd=Path("C:/thread"))
    rebuilt = FakeConfig(
        config_layer_stack={
            "effective_config": {"features": {"request_permissions_tool": False}},
            "requirements_toml": {},
        },
    )

    async def builder(request: ConfigBuildRequest) -> FakeConfig:
        assert request.fallback_cwd == Path("C:/thread")
        return refreshed

    class ThreadConfig:
        cwd = Path("C:/thread")

        async def rebuild_preserving_session_layers(self, incoming: FakeConfig) -> FakeConfig:
            assert incoming is refreshed
            return rebuilt

    manager = ConfigManager(
        Path("C:/codex"),
        arg0_paths=Arg0DispatchPaths(
            codex_self_exe=Path("C:/bin/codex.exe"),
            codex_linux_sandbox_exe=Path("C:/bin/sandbox.exe"),
            main_execve_wrapper_exe=Path("C:/bin/wrapper.exe"),
        ),
        config_builder=builder,
    )
    manager.extend_runtime_feature_enablement(
        {
            "terminal_resize_reflow": False,
            "request_permissions_tool": True,
            "made_up_feature": True,
        }
    )

    result = await manager.load_latest_config_for_thread(ThreadConfig())

    assert result is rebuilt
    assert rebuilt.features.calls == [(Feature.TERMINAL_RESIZE_REFLOW, False)]
    assert rebuilt.codex_self_exe == Path("C:/bin/codex.exe")
    assert rebuilt.codex_linux_sandbox_exe == Path("C:/bin/sandbox.exe")
    assert rebuilt.main_execve_wrapper_exe == Path("C:/bin/wrapper.exe")


@pytest.mark.asyncio
async def test_load_config_layers_delegates_current_state_to_loader() -> None:
    # Rust source: load_config_layers_state receives codex_home, cwd, current overrides, options, cloud requirements,
    # and the current thread config loader.
    captured = []

    async def layers_loader(request):
        captured.append(request)
        return "layers"

    cloud = CloudRequirementsLoader()
    thread_loader = NoopThreadConfigLoader()
    manager = ConfigManager(
        Path("C:/codex"),
        [("model", "gpt-5")],
        LoaderOverrides(user_config_profile="profile"),
        strict_config=True,
        cloud_requirements=cloud,
        thread_config_loader=thread_loader,
        config_layers_loader=layers_loader,
    )

    assert await manager.load_config_layers_for_cwd(Path("C:/repo")) == "layers"
    request = captured[0]
    assert request.codex_home == Path("C:/codex")
    assert request.cwd == Path("C:/repo")
    assert request.cli_overrides == (("model", "gpt-5"),)
    assert request.options.strict_config is True
    assert request.options.loader_overrides.user_config_profile == "profile"
    assert request.cloud_requirements is cloud
    assert request.thread_config_loader is thread_loader


def test_protected_feature_keys_combines_effective_config_and_requirements() -> None:
    # Rust source: protected_feature_keys takes [features] keys plus requirements_toml.feature_requirements.entries.
    stack = {
        "effective_config": {
            "features": {
                "request_permissions_tool": True,
                "terminal_resize_reflow": False,
            }
        },
        "requirements_toml": {
            "feature_requirements": {
                "entries": {
                    "web_search_request": {},
                }
            }
        },
    }

    assert protected_feature_keys(stack) == {
        "request_permissions_tool",
        "terminal_resize_reflow",
        "web_search_request",
    }


def test_apply_runtime_feature_enablement_skips_protected_and_unknown_features() -> None:
    # Rust source: runtime feature enablement skips protected keys and unknown feature names.
    config = FakeConfig(
        config_layer_stack={
            "effective_config": {"features": {"request_permissions_tool": False}},
            "requirements_toml": SimpleNamespace(
                feature_requirements=SimpleNamespace(entries={"web_search_request": object()})
            ),
        }
    )

    apply_runtime_feature_enablement(
        config,
        {
            "request_permissions_tool": True,
            "web_search_request": False,
            "terminal_resize_reflow": False,
            "not_a_feature": True,
        },
    )

    assert config.features.calls == [(Feature.TERMINAL_RESIZE_REFLOW, False)]


@pytest.mark.asyncio
async def test_load_default_config_adds_user_profile_layer_when_loader_overrides_present() -> None:
    # Rust source: load_default_config injects an empty user profile layer when user path/profile override is present.
    class Stack:
        def __init__(self) -> None:
            self.calls = []

        def effective_config(self) -> dict:
            return {}

        def with_user_config_profile(self, user_config_path: Path, profile: str | None, user_config: dict) -> "Stack":
            self.calls.append((user_config_path, profile, user_config))
            return self

    stack = Stack()
    config = FakeConfig(config_layer_stack=stack)
    manager = ConfigManager(
        Path("C:/codex"),
        loader_overrides=LoaderOverrides(user_config_profile="profile"),
        default_config_loader=lambda _manager: config,
    )

    assert await manager.load_default_config() is config
    assert stack.calls == [(Path("C:/codex/config.toml"), "profile", {})]
