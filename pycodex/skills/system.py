"""Install bundled skills like ``codex-skills/src/lib.rs``."""

from __future__ import annotations

from pathlib import Path
import shutil


SYSTEM_SKILLS_DIR_NAME = ".system"
SKILLS_DIR_NAME = "skills"
SYSTEM_SKILLS_MARKER_FILENAME = ".codex-system-skills.marker"

# Rust ``embedded_system_skills_fingerprint`` for the vendored upstream
# ``codex-skills/src/assets/samples`` snapshot.
_SYSTEM_SKILLS_FINGERPRINT = "c52476155cb4ff05"
_SYSTEM_SKILLS_SOURCE = Path(__file__).parent / "assets" / "samples"


def system_cache_root_dir(codex_home: Path | str) -> Path:
    return Path(codex_home) / SKILLS_DIR_NAME / SYSTEM_SKILLS_DIR_NAME


def embedded_system_skills_fingerprint() -> str:
    return _SYSTEM_SKILLS_FINGERPRINT


def install_system_skills(codex_home: Path | str) -> None:
    skills_root = Path(codex_home) / SKILLS_DIR_NAME
    skills_root.mkdir(parents=True, exist_ok=True)
    destination = system_cache_root_dir(codex_home)
    marker = destination / SYSTEM_SKILLS_MARKER_FILENAME
    expected = embedded_system_skills_fingerprint()
    if destination.is_dir() and _read_marker(marker) == expected:
        return
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(_SYSTEM_SKILLS_SOURCE, destination)
    marker.write_text(f"{expected}\n", encoding="utf-8")


def uninstall_system_skills(codex_home: Path | str) -> None:
    destination = system_cache_root_dir(codex_home)
    if destination.exists():
        shutil.rmtree(destination)


def _read_marker(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
