"""Matcher inline module from ``logs_client.rs``."""


def apply_patch(message: str) -> bool:
    return "ToolCall: apply_patch" in message


__all__ = ["apply_patch"]
