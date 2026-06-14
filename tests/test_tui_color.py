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


def test_perceptual_distance_is_zero_for_identical_colors() -> None:
    # Rust: codex-rs/tui/src/color.rs::perceptual_distance behavior contract.
    assert perceptual_distance((10, 20, 30), (10, 20, 30)) == 0.0


def test_perceptual_distance_orders_obvious_contrast() -> None:
    # Rust uses CIE76-style Euclidean distance in Lab space approximation.
    black_white = perceptual_distance((0, 0, 0), (255, 255, 255))
    black_near_black = perceptual_distance((0, 0, 0), (5, 5, 5))
    assert black_white > black_near_black
