from pathlib import Path

from pycodex.skills import (
    SYSTEM_SKILLS_MARKER_FILENAME,
    embedded_system_skills_fingerprint,
    install_system_skills,
    system_cache_root_dir,
    uninstall_system_skills,
)


def test_install_system_skills_writes_embedded_tree_and_matching_marker(tmp_path: Path) -> None:
    # Rust crate/module: codex-skills::install_system_skills.
    install_system_skills(tmp_path)

    root = system_cache_root_dir(tmp_path)
    assert (root / "skill-creator" / "SKILL.md").is_file()
    assert (root / "skill-creator" / "scripts" / "init_skill.py").is_file()
    assert (root / SYSTEM_SKILLS_MARKER_FILENAME).read_text(encoding="utf-8").strip() == (
        embedded_system_skills_fingerprint()
    )


def test_install_system_skills_replaces_stale_tree_and_matching_marker_is_noop(tmp_path: Path) -> None:
    # Rust crate/module: codex-skills marker fast path and stale replacement.
    install_system_skills(tmp_path)
    root = system_cache_root_dir(tmp_path)
    retained = root / "retained.txt"
    retained.write_text("keep while marker matches", encoding="utf-8")

    install_system_skills(tmp_path)
    assert retained.is_file()

    (root / SYSTEM_SKILLS_MARKER_FILENAME).write_text("stale\n", encoding="utf-8")
    install_system_skills(tmp_path)
    assert not retained.exists()

    uninstall_system_skills(tmp_path)
    assert not root.exists()
