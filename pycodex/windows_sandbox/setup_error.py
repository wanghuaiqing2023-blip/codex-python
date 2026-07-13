"""Structured elevated-setup failures.

Rust owner: ``codex-windows-sandbox::setup_error`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class SetupErrorCode(str, Enum):
    ORCHESTRATOR_SANDBOX_DIR_CREATE_FAILED = "orchestrator_sandbox_dir_create_failed"
    ORCHESTRATOR_ELEVATION_CHECK_FAILED = "orchestrator_elevation_check_failed"
    ORCHESTRATOR_PAYLOAD_SERIALIZE_FAILED = "orchestrator_payload_serialize_failed"
    ORCHESTRATOR_HELPER_LAUNCH_FAILED = "orchestrator_helper_launch_failed"
    ORCHESTRATOR_HELPER_LAUNCH_CANCELED = "orchestrator_helper_launch_canceled"
    ORCHESTRATOR_HELPER_EXIT_NONZERO = "orchestrator_helper_exit_nonzero"
    ORCHESTRATOR_HELPER_REPORT_READ_FAILED = "orchestrator_helper_report_read_failed"
    HELPER_REQUEST_ARGS_FAILED = "helper_request_args_failed"
    HELPER_SANDBOX_DIR_CREATE_FAILED = "helper_sandbox_dir_create_failed"
    HELPER_LOG_FAILED = "helper_log_failed"
    HELPER_USER_PROVISION_FAILED = "helper_user_provision_failed"
    HELPER_USERS_GROUP_CREATE_FAILED = "helper_users_group_create_failed"
    HELPER_USER_CREATE_OR_UPDATE_FAILED = "helper_user_create_or_update_failed"
    HELPER_DPAPI_PROTECT_FAILED = "helper_dpapi_protect_failed"
    HELPER_USERS_FILE_WRITE_FAILED = "helper_users_file_write_failed"
    HELPER_SETUP_MARKER_WRITE_FAILED = "helper_setup_marker_write_failed"
    HELPER_SID_RESOLVE_FAILED = "helper_sid_resolve_failed"
    HELPER_CAPABILITY_SID_FAILED = "helper_capability_sid_failed"
    HELPER_FIREWALL_COM_INIT_FAILED = "helper_firewall_com_init_failed"
    HELPER_FIREWALL_POLICY_ACCESS_FAILED = "helper_firewall_policy_access_failed"
    HELPER_FIREWALL_POLICY_INEFFECTIVE = "helper_firewall_policy_ineffective"
    HELPER_FIREWALL_RULE_CREATE_OR_ADD_FAILED = "helper_firewall_rule_create_or_add_failed"
    HELPER_FIREWALL_RULE_VERIFY_FAILED = "helper_firewall_rule_verify_failed"
    HELPER_READ_ACL_HELPER_SPAWN_FAILED = "helper_read_acl_helper_spawn_failed"
    HELPER_SANDBOX_LOCK_FAILED = "helper_sandbox_lock_failed"
    HELPER_UNKNOWN_ERROR = "helper_unknown_error"


@dataclass(frozen=True)
class SetupErrorReport:
    code: SetupErrorCode
    message: str

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}

    @classmethod
    def from_mapping(cls, value: object) -> "SetupErrorReport":
        if not isinstance(value, dict):
            raise ValueError("setup error report must be an object")
        code = value.get("code")
        message = value.get("message")
        if not isinstance(code, str) or not isinstance(message, str):
            raise ValueError("setup error report requires string code and message")
        return cls(SetupErrorCode(code), message)


class SetupFailure(RuntimeError):
    def __init__(self, code: SetupErrorCode, message: str) -> None:
        self.code = SetupErrorCode(code)
        self.message = str(message)
        super().__init__(f"{self.code.value}: {self.message}")


def setup_error_path(codex_home: str | Path) -> Path:
    return Path(codex_home) / ".sandbox" / "setup_error.json"


def clear_setup_error_report(codex_home: str | Path) -> None:
    try:
        setup_error_path(codex_home).unlink()
    except FileNotFoundError:
        pass


def write_setup_error_report(codex_home: str | Path, report: SetupErrorReport) -> None:
    path = setup_error_path(codex_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_mapping(), indent=2), encoding="utf-8")


def read_setup_error_report(codex_home: str | Path) -> SetupErrorReport | None:
    path = setup_error_path(codex_home)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    return SetupErrorReport.from_mapping(value)


__all__ = [
    "SetupErrorCode",
    "SetupErrorReport",
    "SetupFailure",
    "clear_setup_error_report",
    "read_setup_error_report",
    "setup_error_path",
    "write_setup_error_report",
]
