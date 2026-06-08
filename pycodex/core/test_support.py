"""Test-only helpers exposed for cross-package integration tests.

Rust source:
- ``codex/codex-rs/core/src/test_support.rs``

Production code should not depend on this module.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.models_manager import (
    ModelsManagerConfig,
    builtin_collaboration_mode_presets as _builtin_collaboration_mode_presets,
    construct_model_info_offline_for_tests,
    get_model_offline_for_tests,
)
from pycodex.models_manager.test_support import _bundled_model_presets
from pycodex.protocol import CollaborationModeMask, ModelInfo, ModelPreset

from . import thread_manager
from . import unified_exec
from .thread_manager import StartThreadOptions, ThreadManager


@dataclass(frozen=True)
class TestAuthManager:
    auth: Any
    codex_home: Path | None = None


@dataclass(frozen=True)
class TestModelsManager:
    codex_home: Path
    auth_manager: Any
    provider: Any

    async def list_models(self, _refresh_strategy: Any = None) -> list[ModelPreset]:
        return list(all_model_presets())

    async def get_default_model(self, model: str | None = None, _refresh_strategy: Any = None) -> str:
        return get_model_offline(model)

    async def get_model_info(self, model: str, config: ModelsManagerConfig | Any) -> ModelInfo:
        return construct_model_info_offline(model, config)

    def list_collaboration_modes(self) -> list[CollaborationModeMask]:
        return builtin_collaboration_mode_presets()


_TEST_MODEL_PRESETS: list[ModelPreset] | None = None


def set_thread_manager_test_mode(enabled: bool) -> None:
    thread_manager.set_thread_manager_test_mode_for_tests(enabled)


def set_deterministic_process_ids(enabled: bool) -> None:
    unified_exec.set_deterministic_process_ids_for_tests(enabled)


def auth_manager_from_auth(auth: Any) -> TestAuthManager:
    return TestAuthManager(auth=auth)


def auth_manager_from_auth_with_home(auth: Any, codex_home: str | Path) -> TestAuthManager:
    return TestAuthManager(auth=auth, codex_home=Path(codex_home))


def thread_manager_with_models_provider(auth: Any, provider: Any) -> ThreadManager:
    return ThreadManager(auth_manager=auth_manager_from_auth(auth), models_manager=models_manager_with_provider(Path(), auth, provider))


def thread_manager_with_models_provider_and_home(
    auth: Any,
    provider: Any,
    codex_home: str | Path,
    environment_manager: Any,
) -> ThreadManager:
    auth_manager = auth_manager_from_auth_with_home(auth, codex_home)
    return ThreadManager(
        auth_manager=auth_manager,
        environment_manager=environment_manager,
        models_manager=models_manager_with_provider(Path(codex_home), auth_manager, provider),
    )


def thread_manager_with_models_provider_home_and_state(
    auth: Any,
    provider: Any,
    codex_home: str | Path,
    environment_manager: Any,
    state_db: Any | None = None,
) -> ThreadManager:
    manager = thread_manager_with_models_provider_and_home(auth, provider, codex_home, environment_manager)
    manager._state_db = state_db
    return manager


async def start_thread_with_user_shell_override(
    manager: ThreadManager,
    config: Any,
    user_shell_override: Any,
) -> Any:
    method = getattr(manager, "start_thread_with_user_shell_override_for_tests", None)
    if callable(method):
        return await _maybe_await(method(config, user_shell_override))
    return await manager.start_thread(StartThreadOptions(config=config))


async def resume_thread_from_rollout_with_user_shell_override(
    manager: ThreadManager,
    config: Any,
    rollout_path: str | Path,
    auth_manager: Any,
    user_shell_override: Any,
) -> Any:
    method = getattr(manager, "resume_thread_from_rollout_with_user_shell_override_for_tests", None)
    if callable(method):
        return await _maybe_await(method(config, Path(rollout_path), auth_manager, user_shell_override))
    return await manager.start_thread(StartThreadOptions(config=config, initial_history=()))


def models_manager_with_provider(codex_home: str | Path, auth_manager: Any, provider: Any) -> TestModelsManager:
    return TestModelsManager(codex_home=Path(codex_home), auth_manager=auth_manager, provider=provider)


def get_model_offline(model: str | None = None) -> str:
    return get_model_offline_for_tests(model)


def construct_model_info_offline(model: str, config: Any) -> ModelInfo:
    manager_config = _to_models_manager_config(config)
    return construct_model_info_offline_for_tests(model, manager_config)


def all_model_presets() -> list[ModelPreset]:
    global _TEST_MODEL_PRESETS
    if _TEST_MODEL_PRESETS is None:
        _TEST_MODEL_PRESETS = _bundled_model_presets()
    return _TEST_MODEL_PRESETS


def builtin_collaboration_mode_presets() -> list[CollaborationModeMask]:
    return _builtin_collaboration_mode_presets()


def _to_models_manager_config(config: Any) -> ModelsManagerConfig:
    if isinstance(config, ModelsManagerConfig):
        return config
    converter = getattr(config, "to_models_manager_config", None)
    if callable(converter):
        converted = converter()
        if not isinstance(converted, ModelsManagerConfig):
            raise TypeError("to_models_manager_config must return ModelsManagerConfig")
        return converted
    return ModelsManagerConfig(
        model_context_window=getattr(config, "model_context_window", None),
        model_auto_compact_token_limit=getattr(config, "model_auto_compact_token_limit", None),
        tool_output_token_limit=getattr(config, "tool_output_token_limit", None),
        base_instructions=getattr(config, "base_instructions", None),
        personality_enabled=bool(getattr(config, "personality_enabled", False)),
        model_supports_reasoning_summaries=getattr(config, "model_supports_reasoning_summaries", None),
        model_catalog=getattr(config, "model_catalog", None),
    )


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "TestAuthManager",
    "TestModelsManager",
    "all_model_presets",
    "auth_manager_from_auth",
    "auth_manager_from_auth_with_home",
    "builtin_collaboration_mode_presets",
    "construct_model_info_offline",
    "get_model_offline",
    "models_manager_with_provider",
    "resume_thread_from_rollout_with_user_shell_override",
    "set_deterministic_process_ids",
    "set_thread_manager_test_mode",
    "start_thread_with_user_shell_override",
    "thread_manager_with_models_provider",
    "thread_manager_with_models_provider_and_home",
    "thread_manager_with_models_provider_home_and_state",
]
