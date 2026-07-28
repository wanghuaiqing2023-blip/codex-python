from __future__ import annotations

import pycodex.core_skills.manager as manager


def test_injection_uses_one_continuous_python_package() -> None:
    from pycodex.core_skills.injection import SkillInjection

    assert SkillInjection.__module__ == "pycodex.core_skills.injection"


def test_loader_owns_skill_root_and_loading() -> None:
    # Rust module: codex-core-skills/src/loader.rs.
    from pycodex.core_skills.loader import SkillRoot, load_skills_from_roots

    assert SkillRoot.__module__ == "pycodex.core_skills.loader"
    assert load_skills_from_roots.__module__ == "pycodex.core_skills.loader"
    assert not hasattr(manager, "SkillRoot")


def test_core_skills_system_owns_uninstall() -> None:
    # Rust module: codex-core-skills/src/system.rs.
    from pycodex.core_skills.system import uninstall_system_skills

    assert uninstall_system_skills.__module__ == "pycodex.core_skills.system"
