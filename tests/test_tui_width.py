from pycodex.tui.width import usable_content_width
from pycodex.tui.width import usable_content_width_u16


def test_width_helpers_reject_values_outside_rust_unsigned_domains() -> None:
    try:
        usable_content_width(1.5, 0)  # type: ignore[arg-type]
    except TypeError as exc:
        assert "int" in str(exc)
    else:
        raise AssertionError("usize-compatible width should reject non-int inputs")

    try:
        usable_content_width(-1, 0)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("negative usize-compatible width should be rejected")

    try:
        usable_content_width_u16(65536, 0)
    except ValueError as exc:
        assert "u16" in str(exc)
    else:
        raise AssertionError("u16 wrapper should reject values above u16::MAX")


def test_usable_content_width_returns_none_when_reserved_exhausts_width() -> None:
    # Rust: codex-rs/tui/src/width.rs::tests::usable_content_width_returns_none_when_reserved_exhausts_width
    assert usable_content_width(0, 0) is None
    assert usable_content_width(2, 2) is None
    assert usable_content_width(3, 4) is None
    assert usable_content_width(5, 4) == 1


def test_usable_content_width_u16_matches_usize_variant() -> None:
    # Rust: codex-rs/tui/src/width.rs::tests::usable_content_width_u16_matches_usize_variant
    assert usable_content_width_u16(2, 2) is None
    assert usable_content_width_u16(5, 4) == 1


def test_usable_content_width_u16_accepts_u16_max_boundary() -> None:
    # Python dynamic guardrail for Rust's u16 input domain.
    assert usable_content_width_u16(65535, 65534) == 1
    assert usable_content_width_u16(65535, 65535) is None
