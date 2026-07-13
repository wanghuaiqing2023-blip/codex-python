# Parity source: codex-rs/tui/src/exec_command.rs

from pathlib import Path

from pycodex.tui.exec_command import (
    escape_command,
    relativize_to_home,
    split_command_string,
    strip_bash_lc_and_escape,
)


def test_escape_command_matches_rust_shlex_join_example():
    args = ["foo", "bar baz", "weird&stuff"]

    assert escape_command(args) == "foo 'bar baz' 'weird&stuff'"


def test_strip_bash_lc_and_escape_extracts_common_shell_scripts():
    assert strip_bash_lc_and_escape(["bash", "-lc", "echo hello"]) == "echo hello"
    assert strip_bash_lc_and_escape(["zsh", "-lc", "echo hello"]) == "echo hello"
    assert strip_bash_lc_and_escape(["/usr/bin/zsh", "-lc", "echo hello"]) == "echo hello"
    assert strip_bash_lc_and_escape(["/bin/bash", "-lc", "echo hello"]) == "echo hello"


def test_strip_bash_lc_and_escape_falls_back_to_escaped_command():
    assert strip_bash_lc_and_escape(["python", "-c", "print('hi')"]) == "python -c 'print('\"'\"'hi'\"'\"')'"


def test_split_command_string_round_trips_shell_wrappers():
    command = escape_command(["/bin/zsh", "-lc", "python3 -c 'print(\"Hello, world!\")'"])

    assert split_command_string(command) == [
        "/bin/zsh",
        "-lc",
        "python3 -c 'print(\"Hello, world!\")'",
    ]


def test_split_command_string_preserves_non_roundtrippable_windows_commands():
    command = r'C:\Program Files\Git\bin\bash.exe -lc "echo hi"'

    assert split_command_string(command) == [command]


def test_split_command_string_reverses_shlex_joined_powershell_argv():
    # Rust owner: codex-shell-command::parse_command::shlex_join and
    # codex-tui::exec_command::strip_bash_lc_and_escape. The Python terminal
    # adapter must preserve Windows path separators while reversing the
    # app-server command string back into the original argv.
    argv = [
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.EXE",
        "-NoProfile",
        "-Command",
        "Write-Output 'SHELL_COMMAND_OK'",
    ]
    command = escape_command(argv)

    assert split_command_string(command) == argv
    assert strip_bash_lc_and_escape(split_command_string(command)) == "Write-Output 'SHELL_COMMAND_OK'"


def test_split_command_string_returns_original_on_invalid_shell_syntax():
    command = "echo 'unterminated"

    assert split_command_string(command) == [command]


def test_split_command_string_accepts_roundtrip_equivalent_non_windows_command():
    assert split_command_string("echo hello") == ["echo", "hello"]


def test_relativize_to_home_returns_relative_path_inside_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    child = tmp_path / "projects" / "repo"

    assert relativize_to_home(child) == Path("projects/repo")


def test_relativize_to_home_returns_empty_path_for_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert relativize_to_home(tmp_path) == Path("")


def test_relativize_to_home_returns_none_for_relative_or_outside_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    assert relativize_to_home("relative/path") is None
    assert relativize_to_home(tmp_path / "other") is None
