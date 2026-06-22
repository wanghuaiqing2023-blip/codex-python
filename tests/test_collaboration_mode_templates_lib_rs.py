from pathlib import Path

import pycodex.collaboration_mode_templates as templates


RUST_TEMPLATE_DIR = Path("codex/codex-rs/collaboration-mode-templates/templates")


def test_template_constants_match_rust_include_str_files() -> None:
    # Rust crate: codex-collaboration-mode-templates
    # Rust module: src/lib.rs
    # Rust items: PLAN, DEFAULT, EXECUTE, PAIR_PROGRAMMING
    # Contract: constants are exact include_str! contents from templates/*.md.
    assert templates.PLAN == (RUST_TEMPLATE_DIR / "plan.md").read_text(encoding="utf-8")
    assert templates.DEFAULT == (RUST_TEMPLATE_DIR / "default.md").read_text(encoding="utf-8")
    assert templates.EXECUTE == (RUST_TEMPLATE_DIR / "execute.md").read_text(encoding="utf-8")
    assert templates.PAIR_PROGRAMMING == (RUST_TEMPLATE_DIR / "pair_programming.md").read_text(encoding="utf-8")


def test_template_public_surface_matches_rust_constants() -> None:
    # Rust crate: codex-collaboration-mode-templates
    # Rust module: src/lib.rs
    # Contract: crate exposes exactly the four public template constants.
    assert templates.__all__ == [
        "DEFAULT",
        "EXECUTE",
        "PAIR_PROGRAMMING",
        "PLAN",
    ]
    for name in templates.__all__:
        value = getattr(templates, name)
        assert isinstance(value, str)
        assert value.endswith("\n")
