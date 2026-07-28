"""Environment redaction from Rust ``format_env_display.rs``."""

from collections.abc import Mapping, Sequence


def format_env_display(
    env: Mapping[str, str] | None,
    env_vars: Sequence[str],
) -> str:
    parts: list[str] = []
    if env is not None:
        parts.extend(f"{key}=*****" for key in sorted(env))
    parts.extend(f"{var}=*****" for var in env_vars)
    return ", ".join(parts) if parts else "-"


__all__ = ["format_env_display"]
