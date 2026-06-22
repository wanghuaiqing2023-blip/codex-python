import os
import tempfile

import pytest

from pycodex.linux_sandbox import exec_util


def test_argv_to_cstrings_converts_strings_to_bytes() -> None:
    # Rust source: codex-linux-sandbox/src/exec_util.rs argv_to_cstrings()
    # pushes a CString for each argv entry.
    assert exec_util.argv_to_cstrings(["bwrap", "--ro-bind", "/a"]) == [
        b"bwrap",
        b"--ro-bind",
        b"/a",
    ]


def test_argv_to_cstrings_rejects_interior_nul() -> None:
    # Rust source: CString::new(arg.as_str()) panics on interior NUL.
    with pytest.raises(ValueError, match="failed to convert argv to CString"):
        exec_util.argv_to_cstrings(["bad\x00arg"])


def test_preserved_files_are_made_inheritable() -> None:
    # Rust test: preserved_files_are_made_inheritable.
    with tempfile.TemporaryFile() as file:
        fd = file.fileno()
        os.set_inheritable(fd, False)

        exec_util.make_files_inheritable([file])

        assert os.get_inheritable(fd) is True


def test_make_files_inheritable_accepts_raw_file_descriptors() -> None:
    with tempfile.TemporaryFile() as file:
        fd = file.fileno()
        os.set_inheritable(fd, False)

        exec_util.make_files_inheritable([fd])

        assert os.get_inheritable(fd) is True
