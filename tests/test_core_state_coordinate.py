from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.core import state
from pycodex.core.state import additional_context, auto_compact_window, service, session, turn


def test_state_root_reexports_rust_mod_items() -> None:
    # Rust source: codex/codex-rs/core/src/state/mod.rs
    # Rust crate/module: codex-core::state
    # Contract: mod.rs re-exports the selected state child-module items.
    assert state.AdditionalContextStore is additional_context.AdditionalContextStore
    assert state.AutoCompactWindowSnapshot is auto_compact_window.AutoCompactWindowSnapshot
    assert state.SessionServices is service.SessionServices
    assert state.SessionState is session.SessionState
    assert state.ActiveTurn is turn.ActiveTurn
    assert state.MailboxDeliveryPhase is turn.MailboxDeliveryPhase
    assert state.PendingRequestPermissions is turn.PendingRequestPermissions
    assert state.RunningTask is turn.RunningTask
    assert state.TaskKind is turn.TaskKind
    assert state.TurnState is turn.TurnState


def test_session_services_uses_rust_field_names_as_interface_container() -> None:
    # Rust source: codex/codex-rs/core/src/state/service.rs::SessionServices
    # Contract: session-wide service handles are accessible by Rust field name.
    services = state.SessionServices(
        unified_exec_manager="exec",
        shell_zsh_path="bin/zsh",
        main_execve_wrapper_exe="bin/wrapper",
        show_raw_agent_reasoning=True,
        managed_network_requirements_configured=True,
        model_client="model-client",
        environment_manager="environment-manager",
    )

    assert services.unified_exec_manager == "exec"
    assert services.shell_zsh_path == Path("bin/zsh")
    assert services.main_execve_wrapper_exe == Path("bin/wrapper")
    assert services.show_raw_agent_reasoning is True
    assert services.managed_network_requirements_configured is True
    assert services.model_client == "model-client"
    assert services.environment_manager == "environment-manager"
    assert hasattr(services, "guardian_rejection_circuit_breaker")
    assert hasattr(services, "thread_extension_data")


def test_session_services_rejects_non_bool_flags() -> None:
    with pytest.raises(TypeError):
        state.SessionServices(show_raw_agent_reasoning=1)
    with pytest.raises(TypeError):
        state.SessionServices(managed_network_requirements_configured=1)
