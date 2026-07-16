"""System skill installation aligned with the Rust ``codex-skills`` crate."""

from .system import (
    SYSTEM_SKILLS_MARKER_FILENAME,
    embedded_system_skills_fingerprint,
    install_system_skills,
    system_cache_root_dir,
    uninstall_system_skills,
)

__all__ = [
    "SYSTEM_SKILLS_MARKER_FILENAME",
    "embedded_system_skills_fingerprint",
    "install_system_skills",
    "system_cache_root_dir",
    "uninstall_system_skills",
]
