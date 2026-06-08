"""Session service handle container aligned with ``codex-core::state::service``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SessionServices:
    """Python coordinate for Rust ``SessionServices``.

    Rust stores session-wide service handles in this struct. Python keeps the
    same field names as an interface container so runtime code and tests can
    use ``session.services.<field>`` consistently while individual service
    implementations continue to live in their owning modules.
    """

    mcp_connection_manager: Any = None
    mcp_startup_cancellation_token: Any = None
    unified_exec_manager: Any = None
    shell_zsh_path: Path | None = None
    main_execve_wrapper_exe: Path | None = None
    analytics_events_client: Any = None
    hooks: Any = None
    rollout_thread_trace: Any = None
    user_shell: Any = None
    shell_snapshot_tx: Any = None
    show_raw_agent_reasoning: bool = False
    exec_policy: Any = None
    auth_manager: Any = None
    models_manager: Any = None
    session_telemetry: Any = None
    tool_approvals: Any = None
    guardian_rejections: Any = None
    guardian_rejection_circuit_breaker: Any = None
    runtime_handle: Any = None
    skills_manager: Any = None
    plugins_manager: Any = None
    mcp_manager: Any = None
    extensions: Any = None
    session_extension_data: Any = None
    thread_extension_data: Any = None
    agent_control: Any = None
    network_proxy: Any = None
    network_proxy_audit_metadata: Any = None
    managed_network_requirements_configured: bool = False
    network_approval: Any = None
    state_db: Any = None
    live_thread: Any = None
    thread_store: Any = None
    attestation_provider: Any = None
    model_client: Any = None
    code_mode_service: Any = None
    environment_manager: Any = None

    def __post_init__(self) -> None:
        if self.shell_zsh_path is not None and not isinstance(self.shell_zsh_path, Path):
            self.shell_zsh_path = Path(self.shell_zsh_path)
        if self.main_execve_wrapper_exe is not None and not isinstance(
            self.main_execve_wrapper_exe,
            Path,
        ):
            self.main_execve_wrapper_exe = Path(self.main_execve_wrapper_exe)
        if not isinstance(self.show_raw_agent_reasoning, bool):
            raise TypeError("show_raw_agent_reasoning must be bool")
        if not isinstance(self.managed_network_requirements_configured, bool):
            raise TypeError("managed_network_requirements_configured must be bool")


__all__ = ["SessionServices"]
