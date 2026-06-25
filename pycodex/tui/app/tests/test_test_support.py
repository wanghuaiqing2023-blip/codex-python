"""Parity tests for codex-rs/tui/src/app/test_support.rs."""

import asyncio

from pycodex.protocol import SessionSource
from pycodex.tui.app.test_support import (
    TestAppFixturePlan as AppFixturePlan,
    TestSessionTelemetry as SessionTelemetry,
    app_enabled_in_effective_config,
    make_test_app,
    test_session_telemetry as build_test_session_telemetry,
)


class ConfigLayerStack:
    def __init__(self, effective):
        self._effective = effective

    def effective_config(self):
        return self._effective


class Config:
    def __init__(self, effective, model_info=None, model_slugs=None):
        self.config_layer_stack = ConfigLayerStack(effective)
        self.model_info = model_info
        self.model_slugs = model_slugs or {}


class ModelInfo:
    slug = "model-info-slug"


def test_make_test_app_returns_semantic_fixture_plan():
    plan = asyncio.run(make_test_app())

    assert plan == AppFixturePlan()
    assert plan.chat_widget == "make_chatwidget_manual_with_sender"
    assert plan.session_telemetry == "test_session_telemetry"


def test_test_session_telemetry_matches_rust_test_defaults():
    telemetry = build_test_session_telemetry(Config({}, model_slugs={"gpt-5": "gpt-5-slug"}), "gpt-5")

    assert isinstance(telemetry, SessionTelemetry)
    assert telemetry.model == "gpt-5"
    assert telemetry.model_slug == "gpt-5-slug"
    assert telemetry.account_id is None
    assert telemetry.account_email is None
    assert telemetry.auth_mode is None
    assert telemetry.originator == "test_originator"
    assert telemetry.log_user_prompts is False
    assert telemetry.app_version == "test"
    assert telemetry.session_source == SessionSource.cli()


def test_test_session_telemetry_falls_back_to_model_info_slug_or_model():
    assert build_test_session_telemetry(Config({}, model_info=ModelInfo()), "o4").model_slug == "model-info-slug"
    assert build_test_session_telemetry(Config({}), "o4").model_slug == "o4"


def test_app_enabled_in_effective_config_reads_nested_apps_table():
    config = Config({"apps": {"github": {"enabled": True}, "linear": {"enabled": False}}})

    assert app_enabled_in_effective_config(config, "github") is True
    assert app_enabled_in_effective_config(config, "linear") is False


def test_app_enabled_in_effective_config_returns_none_for_missing_or_non_bool_values():
    config = Config({"apps": {"github": {"enabled": "yes"}, "empty": {}}})

    assert app_enabled_in_effective_config(config, "github") is None
    assert app_enabled_in_effective_config(config, "empty") is None
    assert app_enabled_in_effective_config(config, "missing") is None
    assert app_enabled_in_effective_config(object(), "github") is None

def test_app_enabled_in_effective_config_returns_none_without_apps_table():
    assert app_enabled_in_effective_config(Config({}), "github") is None
    assert app_enabled_in_effective_config(Config({"apps": "not-a-table"}), "github") is None

