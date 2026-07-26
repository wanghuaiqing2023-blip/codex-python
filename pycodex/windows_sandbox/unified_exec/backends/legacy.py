"""Direct restricted-token unified-exec backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from ...process import create_process_as_user_popen
from ...spawn_prep import (
    WindowsSandboxSpawnPrepError,
    apply_legacy_session_acl_rules,
    prepare_legacy_session_security,
    prepare_legacy_spawn_context,
)


def spawn_windows_sandbox_session_legacy(
    permission_profile: Any,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    command: Sequence[str],
    cwd: str | Path,
    env_map: Mapping[str, str],
    _timeout_ms: int | None,
    additional_deny_read_paths: Sequence[str | Path],
    additional_deny_write_paths: Sequence[str | Path],
    tty: bool,
    stdin_open: bool,
    use_private_desktop: bool,
):
    if additional_deny_read_paths:
        raise WindowsSandboxSpawnPrepError(
            "deny-read overrides require the elevated Windows sandbox backend"
        )
    prepared_env = dict(env_map)
    context = prepare_legacy_spawn_context(
        permission_profile,
        permission_profile_cwd,
        codex_home,
        cwd,
        prepared_env,
        command,
    )
    if not context.permissions.has_full_disk_read_access():
        raise WindowsSandboxSpawnPrepError(
            "Restricted read-only access requires the elevated "
            "Windows sandbox backend"
        )
    with prepare_legacy_session_security(
        context,
        codex_home,
        prepared_env,
    ) as security:
        apply_legacy_session_acl_rules(
            context,
            codex_home,
            prepared_env,
            security,
            additional_deny_write_paths=additional_deny_write_paths,
        )
        return create_process_as_user_popen(
            security.token,
            command,
            cwd,
            prepared_env,
            stdin_open=stdin_open,
            tty=tty,
            merge_stderr=False,
            use_private_desktop=use_private_desktop,
        )


__all__ = ["spawn_windows_sandbox_session_legacy"]
