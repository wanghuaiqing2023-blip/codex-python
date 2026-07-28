from __future__ import annotations

import importlib

from pycodex.tui import test_support as tui_test_support
from pycodex.utils import absolute_path


def test_absolutize_rs_has_a_distinct_python_owner() -> None:
    # Rust: codex-utils-absolute-path/src/absolutize.rs.
    module = importlib.import_module("pycodex.utils.absolute_path.absolutize")

    assert module.absolutize.__module__ == module.__name__
    assert module.absolutize_from.__module__ == module.__name__
    assert not hasattr(absolute_path, "_absolutize")


def test_test_support_rs_owns_the_helpers_reexported_by_tui() -> None:
    # Rust: absolute-path/src/lib.rs::test_support; tui/src/test_support.rs
    # re-exports these items instead of implementing a second copy.
    module = importlib.import_module("pycodex.utils.absolute_path.test_support")

    assert module.test_path_buf.__module__ == module.__name__
    assert module.PathBufExt.__module__ == module.__name__
    assert tui_test_support.test_path_buf is module.test_path_buf
    assert tui_test_support.PathBufExt is module.PathBufExt
