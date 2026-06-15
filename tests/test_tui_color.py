from pycodex.tui.color import blend
from pycodex.tui.color import is_light
from pycodex.tui.color import perceptual_distance


def test_is_light_uses_rust_luminance_threshold() -> None:
    # Rust: codex-rs/tui/src/color.rs::is_light behavior contract.
    assert is_light((255, 255, 255)) is True
    assert is_light((0, 0, 0)) is False
    assert is_light((128, 128, 128)) is False
    assert is_light((129, 129, 129)) is True


def test_blend_truncates_like_rust_u8_cast() -> None:
    # Rust: codex-rs/tui/src/color.rs::blend behavior contract.
    assert blend((255, 0, 0), (0, 0, 255), 0.5) == (127, 0, 127)
    assert blend((10, 20, 30), (110, 120, 130), 0.25) == (85, 95, 105)
    assert blend((1, 2, 3), (10, 20, 30), 1.0) == (1, 2, 3)
    assert blend((1, 2, 3), (10, 20, 30), 0.0) == (10, 20, 30)


def test_color_helpers_reject_values_outside_rust_u8_domain() -> None:
    # Python dynamic guardrail for Rust's u8 channel input domain.
    try:
        is_light((256, 0, 0))
    except ValueError as exc:
        assert "u8" in str(exc)
    else:
        raise AssertionError("u8 channel overflow should be rejected")

    try:
        blend((0, -1, 0), (0, 0, 0), 0.5)
    except ValueError as exc:
        assert "u8" in str(exc)
    else:
        raise AssertionError("negative u8 channel should be rejected")

    try:
        perceptual_distance((0, 0, 0), (1.5, 0, 0))  # type: ignore[arg-type]
    except TypeError as exc:
        assert "int" in str(exc)
    else:
        raise AssertionError("non-int u8 channel should be rejected")


def test_perceptual_distance_is_zero_for_identical_colors() -> None:
    # Rust: codex-rs/tui/src/color.rs::perceptual_distance behavior contract.
    assert perceptual_distance((10, 20, 30), (10, 20, 30)) == 0.0


def test_perceptual_distance_orders_obvious_contrast() -> None:
    # Rust uses CIE76-style Euclidean distance in Lab space approximation.
    black_white = perceptual_distance((0, 0, 0), (255, 255, 255))
    black_near_black = perceptual_distance((0, 0, 0), (5, 5, 5))
    assert black_white > black_near_black


def test_perceptual_distance_is_symmetric_and_matches_lab_formula_scale() -> None:
    # Rust converts both colors to Lab and returns Euclidean distance, so order
    # is symmetric. Black/white distance is approximately 100 with the D65
    # constants used in the module.
    a = (10, 20, 30)
    b = (200, 150, 100)
    assert perceptual_distance(a, b) == perceptual_distance(b, a)
    assert 99.9 < perceptual_distance((0, 0, 0), (255, 255, 255)) < 100.1
