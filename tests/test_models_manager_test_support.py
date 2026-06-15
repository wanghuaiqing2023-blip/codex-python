from dataclasses import replace

from pycodex.models_manager import ModelsManagerConfig
from pycodex.models_manager.test_support import (
    construct_model_info_offline_for_tests,
    get_model_offline_for_tests,
)
from pycodex.models_manager.model_info import model_info_from_slug
from pycodex.protocol import ModelVisibility, ModelsResponse


def _catalog_model(slug: str):
    return replace(
        model_info_from_slug(slug),
        display_name=f"{slug} display",
        visibility=ModelVisibility.LIST,
        priority=0,
        used_fallback_model_metadata=False,
    )


def test_get_model_offline_for_tests_uses_explicit_model_or_bundled_default() -> None:
    # Rust crate/module: codex-models-manager::test_support::get_model_offline_for_tests
    assert get_model_offline_for_tests("custom-model") == "custom-model"
    assert get_model_offline_for_tests()


def test_construct_model_info_offline_for_tests_uses_config_catalog_and_overrides() -> None:
    # Rust crate/module: codex-models-manager::test_support::construct_model_info_offline_for_tests
    config = ModelsManagerConfig(
        model_context_window=1234,
        model_catalog=ModelsResponse((_catalog_model("gpt-test"),)),
    )

    info = construct_model_info_offline_for_tests("gpt-test-preview", config)

    assert info.slug == "gpt-test-preview"
    assert info.display_name == "gpt-test display"
    assert info.context_window == 1234
    assert info.used_fallback_model_metadata is False
