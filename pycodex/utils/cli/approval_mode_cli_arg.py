"""Approval CLI enum from Rust ``approval_mode_cli_arg.rs``."""

from enum import Enum


class ApprovalModeCliArg(Enum):
    UNTRUSTED = "untrusted"
    ON_FAILURE = "on-failure"
    ON_REQUEST = "on-request"
    NEVER = "never"

    def to_ask_for_approval(self) -> str:
        return {
            ApprovalModeCliArg.UNTRUSTED: "unless-trusted",
            ApprovalModeCliArg.ON_FAILURE: "on-failure",
            ApprovalModeCliArg.ON_REQUEST: "on-request",
            ApprovalModeCliArg.NEVER: "never",
        }[self]


__all__ = ["ApprovalModeCliArg"]
