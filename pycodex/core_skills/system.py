"""System skill lifecycle owned by ``codex-core-skills::system``."""

from __future__ import annotations

from pathlib import Path
import shutil

from pycodex.skills import install_system_skills, system_cache_root_dir


def uninstall_system_skills(codex_home: Path | str) -> None:
    destination = system_cache_root_dir(codex_home)
    if destination.exists():
        shutil.rmtree(destination)


__all__ = [
    "install_system_skills",
    "system_cache_root_dir",
    "uninstall_system_skills",
]
