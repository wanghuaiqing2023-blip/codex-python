"""Rust parity tests for ``codex-app-server/src/request_processors/catalog_processor.rs``."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pycodex.app_server.request_processors_catalog_processor import (
    CatalogRequestProcessor,
    CatalogRequestProcessorError,
    ConfigEdit,
    errors_to_info,
    hook_errors_to_info,
    hooks_to_info,
    list_collaboration_modes,
    list_models,
    mock_experimental_method_inner,
    paginate_items,
    skills_to_info,
)
from pycodex.app_server_protocol import (
    CollaborationModeMask,
    Model,
    ModelListParams,
    MockExperimentalMethodParams,
    PermissionProfileListParams,
    ReasoningEffortOption,
)
from pycodex.protocol import ReasoningEffort


def _model(model_id: str) -> Model:
    return Model(
        id=model_id,
        model=model_id,
        upgrade=None,
        upgrade_info=None,
        availability_nux=None,
        display_name=model_id.upper(),
        description=model_id,
        hidden=False,
        supported_reasoning_efforts=(ReasoningEffortOption(ReasoningEffort.LOW, "low"),),
        default_reasoning_effort=ReasoningEffort.LOW,
    )


class ThreadManager:
    def __init__(self) -> None:
        self.include_hidden = None
        self.models = (_model("a"), _model("b"), _model("c"))
        self.modes = (CollaborationModeMask(name="plan"),)
        self.skills_cache_cleared = False

    def supported_models(self, include_hidden: bool):
        self.include_hidden = include_hidden
        return self.models

    def list_collaboration_modes(self):
        return self.modes

    def clear_skills_cache(self):
        self.skills_cache_cleared = True


class ConfigManager:
    def __init__(self) -> None:
        self.edits = []
        self.plugin_cache_cleared = False
        self.layers = {
            "effective_config": {
                "permissions": {
                    "entries": {
                        "zeta": {"description": "last"},
                        "alpha": {"description": "first"},
                    }
                }
            }
        }

    def load_config_layers(self, _fallback):
        return self.layers

    def apply_skill_config_edit(self, edit: ConfigEdit):
        self.edits.append(edit)

    def clear_plugin_cache(self):
        self.plugin_cache_cleared = True


class AuthManager:
    def auth(self):
        return object()


def test_list_models_matches_rust_pagination_and_hidden_flag() -> None:
    manager = ThreadManager()

    response = asyncio.run(list_models(manager, ModelListParams(limit=0, include_hidden=True)))

    assert manager.include_hidden is True
    assert [model.id for model in response.data] == ["a"]
    assert response.next_cursor == "1"


def test_list_models_rejects_invalid_cursor_like_rust() -> None:
    manager = ThreadManager()

    with pytest.raises(CatalogRequestProcessorError) as excinfo:
        asyncio.run(list_models(manager, ModelListParams(cursor="nope")))

    assert excinfo.value.error.message == "invalid cursor: nope"


def test_paginate_rejects_cursor_past_total_with_rust_message() -> None:
    with pytest.raises(CatalogRequestProcessorError) as excinfo:
        paginate_items((1, 2), None, "3", "models")

    assert excinfo.value.error.message == "cursor 3 exceeds total models 2"


def test_list_collaboration_modes_wraps_thread_manager_masks() -> None:
    response = asyncio.run(list_collaboration_modes(ThreadManager(), None))

    assert response.data[0].name == "plan"


def test_permission_profile_list_prepends_builtins_and_sorts_configured_profiles() -> None:
    processor = CatalogRequestProcessor.new(AuthManager(), ThreadManager(), {}, ConfigManager(), object())

    response = asyncio.run(processor.permission_profile_list(PermissionProfileListParams()))

    assert [profile.id for profile in response.data] == [
        "read-only",
        "workspace",
        "danger-full-access",
        "alpha",
        "zeta",
    ]


def test_mock_experimental_method_echoes_value() -> None:
    response = mock_experimental_method_inner(MockExperimentalMethodParams(value={"hello": "world"}))

    assert response.echoed == {"hello": "world"}


def test_skills_to_info_maps_enabled_flag_interface_dependencies_and_errors() -> None:
    skill = {
        "name": "review",
        "description": "Review code",
        "short_description": "Review",
        "interface": {"type": "chat"},
        "dependencies": {"tools": [{"name": "shell", "description": "run commands"}]},
        "path": "C:/repo/.codex/skills/review",
        "scope": "user",
    }

    metadata = skills_to_info([skill], disabled_paths=[skill["path"]])[0]
    error = errors_to_info([{"path": skill["path"], "message": "bad yaml"}])[0]

    assert metadata.enabled is False
    assert metadata.interface.type == "chat"
    assert metadata.dependencies.tools[0].name == "shell"
    assert error.message == "bad yaml"


def test_hooks_to_info_and_hook_errors_preserve_catalog_fields() -> None:
    hook = {
        "key": "abc",
        "event_name": "preToolUse",
        "handler_type": "command",
        "matcher": ".*",
        "command": "echo hi",
        "timeout_sec": 3,
        "status_message": "running",
        "source_path": "C:/repo/AGENTS.md",
        "source": "project",
        "plugin_id": None,
        "display_order": 5,
        "enabled": True,
        "is_managed": False,
        "current_hash": "hash",
        "trust_status": "trusted",
    }

    metadata = hooks_to_info([hook])[0]
    error = hook_errors_to_info([{"path": "C:/repo/AGENTS.md", "message": "bad hook"}])[0]

    assert metadata.key == "abc"
    assert metadata.event_name == "preToolUse"
    assert metadata.enabled is True
    assert error.message == "bad hook"


def test_workspace_plugins_enabled_falls_back_true_on_error() -> None:
    class Cache:
        def codex_plugins_enabled_for_workspace(self, _config, _auth):
            raise RuntimeError("settings unavailable")

    processor = CatalogRequestProcessor.new(AuthManager(), ThreadManager(), {}, ConfigManager(), Cache())

    assert asyncio.run(processor.workspace_codex_plugins_enabled({}, object())) is True


def test_skills_config_write_requires_exactly_one_selector_and_clears_caches() -> None:
    thread_manager = ThreadManager()
    config_manager = ConfigManager()
    processor = CatalogRequestProcessor.new(AuthManager(), thread_manager, {}, config_manager, object())

    response = asyncio.run(processor.skills_config_write({"name": "review", "enabled": True}))

    assert response.effective_enabled is True
    assert config_manager.edits == [ConfigEdit("name", "review", True)]
    assert config_manager.plugin_cache_cleared is True
    assert thread_manager.skills_cache_cleared is True

    with pytest.raises(CatalogRequestProcessorError) as excinfo:
        asyncio.run(processor.skills_config_write({"name": "review", "path": "C:/x", "enabled": True}))

    assert "exactly one of path or name" in excinfo.value.error.message
