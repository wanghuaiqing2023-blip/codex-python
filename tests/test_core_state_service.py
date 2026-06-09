from pathlib import Path

import pytest

from pycodex.core.state.service import SessionServices


def test_session_services_preserves_service_handles_and_normalizes_paths():
    # Rust source: codex-rs/core/src/state/service.rs::SessionServices.
    # Contract: the struct is a session-wide service handle container with
    # stable field names; Python preserves those names and normalizes path-like
    # fields for consumers.
    auth_manager = object()
    models_manager = object()

    services = SessionServices(
        shell_zsh_path="C:/tools/zsh.exe",
        main_execve_wrapper_exe="C:/tools/wrapper.exe",
        auth_manager=auth_manager,
        models_manager=models_manager,
        show_raw_agent_reasoning=True,
        managed_network_requirements_configured=True,
    )

    assert services.shell_zsh_path == Path("C:/tools/zsh.exe")
    assert services.main_execve_wrapper_exe == Path("C:/tools/wrapper.exe")
    assert services.auth_manager is auth_manager
    assert services.models_manager is models_manager
    assert services.show_raw_agent_reasoning is True
    assert services.managed_network_requirements_configured is True


def test_session_services_rejects_non_bool_flags():
    with pytest.raises(TypeError, match="show_raw_agent_reasoning must be bool"):
        SessionServices(show_raw_agent_reasoning="yes")

    with pytest.raises(TypeError, match="managed_network_requirements_configured must be bool"):
        SessionServices(managed_network_requirements_configured=1)
