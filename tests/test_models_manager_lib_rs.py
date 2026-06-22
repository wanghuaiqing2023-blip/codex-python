from pycodex.app_server_protocol import AuthMode as ProtocolAuthMode
from pycodex.models_manager import (
    AuthMode,
    ModelsManagerConfig,
    ModelsResponse,
    bundled_models_response,
    client_version_to_whole,
)
from pycodex.models_manager.manager import RefreshStrategy as ManagerRefreshStrategy
from pycodex.models_manager import RefreshStrategy


def test_lib_reexports_auth_mode_and_config() -> None:
    # Rust crate/module: codex-models-manager::lib
    # Behavior contract: lib.rs re-exports AuthMode and ModelsManagerConfig.
    assert AuthMode is ProtocolAuthMode
    assert ModelsManagerConfig().to_mapping() == {}


def test_lib_exposes_manager_refresh_strategy_singleton() -> None:
    # Rust crate/module: codex-models-manager::lib module graph exposes manager.
    assert RefreshStrategy is ManagerRefreshStrategy
    assert str(RefreshStrategy.ONLINE_IF_UNCACHED) == "online_if_uncached"


def test_bundled_models_response_loads_rust_models_json() -> None:
    # Rust source: bundled_models_response() parses include_str!("../models.json").
    response = ModelsResponse.from_mapping(bundled_models_response())

    assert response.models
    assert all(model.slug for model in response.models)


def test_client_version_to_whole_normalizes_python_supplied_versions() -> None:
    # Rust lib.rs returns the crate's major.minor.patch. The Python facade also
    # accepts explicit version strings for tests and provider shims.
    assert client_version_to_whole("1.2.3-alpha.4") == "1.2.3"
    assert client_version_to_whole("1.2") == "1.2.0"
    assert client_version_to_whole(None) == "0.0.0"
