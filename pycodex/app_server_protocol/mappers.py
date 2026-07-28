"""Conversions owned by ``protocol/mappers.rs``."""

from __future__ import annotations

from .command_exec import CommandExecParams
from .permissions import SandboxPolicy
from .v1 import ExecOneOffCommandParams

_I64_MAX = 2**63 - 1


def command_exec_params_from_v1(value: ExecOneOffCommandParams) -> CommandExecParams:
    if not isinstance(value, ExecOneOffCommandParams):
        raise TypeError("value must be ExecOneOffCommandParams")
    timeout_ms = value.timeout_ms
    if timeout_ms is not None and timeout_ms > _I64_MAX:
        timeout_ms = 60_000
    sandbox_policy = (
        None
        if value.sandbox_policy is None
        else SandboxPolicy.from_core(value.sandbox_policy)
    )
    return CommandExecParams(
        command=value.command,
        timeout_ms=timeout_ms,
        cwd=value.cwd,
        sandbox_policy=sandbox_policy,
    )


__all__ = ["command_exec_params_from_v1"]

