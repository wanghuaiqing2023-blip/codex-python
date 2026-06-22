import unittest
from pathlib import Path

from pycodex.protocol import ParsedCommand
from pycodex.shell_command import (
    UTF8_OUTPUT_PREFIX,
    extract_powershell_command,
    parse_command,
    parse_powershell_command_into_plain_commands,
    parse_shell_lc_plain_commands,
    parse_shell_lc_single_command_prefix,
    prefix_powershell_script_with_utf8,
    shlex_join,
)
from pycodex.shell_command.parse_command import is_small_formatting_command


def split(value: str) -> list[str]:
    import shlex

    return shlex.split(value)


class ShellCommandParseCommandTests(unittest.TestCase):
    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust test: tests::git_status_is_unknown
    # Contract: shell.parse_command
    def test_shlex_join_and_unknown_commands(self):
        self.assertEqual(shlex_join(["rg", "-n", "BUG|FIXME", "-S"]), "rg -n 'BUG|FIXME' -S")
        self.assertEqual(parse_command(["git", "status"]), [ParsedCommand.unknown("git status")])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust test: tests::supports_git_grep_and_ls_files
    # Contract: shell.parse_command
    def test_supports_git_grep_and_ls_files(self):
        self.assertEqual(
            parse_command(split("git grep TODO src")),
            [ParsedCommand.search("git grep TODO src", query="TODO", path="src")],
        )
        self.assertEqual(
            parse_command(split("git ls-files --exclude target src")),
            [ParsedCommand.list_files("git ls-files --exclude target src", "src")],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_searching_for_navigate_to_route; tests::supports_rg_files_with_path_and_pipe
    # Contract: shell.parse_command
    def test_supports_rg_search_and_file_listing_in_bash(self):
        self.assertEqual(
            parse_command(["bash", "-lc", 'rg -n "navigate-to-route" -S']),
            [ParsedCommand.search("rg -n navigate-to-route -S", query="navigate-to-route")],
        )
        self.assertEqual(
            parse_command(["bash", "-lc", "rg --files webview/src | sed -n"]),
            [ParsedCommand.list_files("rg --files webview/src", "webview")],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::handles_git_pipe_wc; tests::bash_lc_redirect_not_quoted
    # Contract: shell.parse_command
    def test_bash_falls_back_to_full_script_when_unknown_or_unsupported(self):
        self.assertEqual(
            parse_command(["bash", "-lc", "git status | wc -l"]),
            [ParsedCommand.unknown("git status | wc -l")],
        )
        self.assertEqual(
            parse_command(["bash", "-lc", "echo foo > bar"]),
            [ParsedCommand.unknown("echo foo > bar")],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::keeps_mutating_xargs_pipeline; tests::collapses_plain_pipeline_when_any_stage_is_unknown
    # Contract: shell.parse_command
    def test_collapses_mutating_xargs_pipeline_to_unknown(self):
        command = split("rg -l OldName src | xargs perl -pi -e 's/OldName/NewName/g'")
        self.assertEqual(
            parse_command(command),
            [ParsedCommand.unknown(shlex_join(command))],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_cat; tests::bash_cd_then_cat_is_read
    # Contract: shell.display_summary
    def test_read_commands_and_cd_context(self):
        self.assertEqual(
            parse_command(split("cat pycodex/protocol/protocol.py")),
            [ParsedCommand.read("cat pycodex/protocol/protocol.py", "protocol.py", Path("pycodex/protocol/protocol.py"))],
        )
        self.assertEqual(
            parse_command(["bash", "-lc", "cd pycodex && sed -n 1,20p protocol/protocol.py"]),
            [ParsedCommand.read("sed -n '1,20p' protocol/protocol.py", "protocol.py", Path("pycodex") / "protocol/protocol.py")],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_cat; tests::zsh_lc_supports_cat; tests::supports_bat; tests::supports_batcat; tests::supports_less; tests::supports_more
    # Contract: shell.display_summary read commands
    def test_display_summary_read_file_viewer_variants(self):
        cases = [
            (
                ["bash", "-lc", "cat webview/README.md"],
                ParsedCommand.read("cat webview/README.md", "README.md", Path("webview/README.md")),
            ),
            (
                ["zsh", "-lc", "cat README.md"],
                ParsedCommand.read("cat README.md", "README.md", Path("README.md")),
            ),
            (
                ["bash", "-lc", "bat --theme TwoDark README.md"],
                ParsedCommand.read("bat --theme TwoDark README.md", "README.md", Path("README.md")),
            ),
            (
                ["bash", "-lc", "batcat README.md"],
                ParsedCommand.read("batcat README.md", "README.md", Path("README.md")),
            ),
            (
                ["bash", "-lc", "less -p TODO README.md"],
                ParsedCommand.read("less -p TODO README.md", "README.md", Path("README.md")),
            ),
            (
                ["bash", "-lc", "more README.md"],
                ParsedCommand.read("more README.md", "README.md", Path("README.md")),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_head_n; tests::supports_head_file_only; tests::supports_tail_n_plus; tests::supports_tail_n_last_lines; tests::supports_tail_file_only
    # Contract: shell.display_summary read command ranges
    def test_display_summary_head_tail_variants(self):
        cases = [
            "head -n 50 Cargo.toml",
            "head Cargo.toml",
            "tail -n +522 README.md",
            "tail -n 30 README.md",
            "tail README.md",
        ]
        expected_names = ["Cargo.toml", "Cargo.toml", "README.md", "README.md", "README.md"]
        for inner, name in zip(cases, expected_names):
            with self.subTest(inner=inner):
                self.assertEqual(
                    parse_command(["bash", "-lc", inner]),
                    [ParsedCommand.read(inner, name, Path(name))],
                )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_ls_with_pipe; tests::supports_eza_exa_tree_du
    # Contract: shell.display_summary list commands
    def test_display_summary_list_file_viewer_variants(self):
        self.assertEqual(
            parse_command(["bash", "-lc", "ls -la | sed -n '1,120p'"]),
            [ParsedCommand.list_files("ls -la")],
        )
        cases = [
            (
                split("eza --color=always src"),
                ParsedCommand.list_files("eza '--color=always' src", "src"),
            ),
            (
                split("exa -I target ."),
                ParsedCommand.list_files("exa -I target .", "."),
            ),
            (
                split("tree -L 2 src"),
                ParsedCommand.list_files("tree -L 2 src", "src"),
            ),
            (
                split("du -d 2 ."),
                ParsedCommand.list_files("du -d 2 .", "."),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_rg_files_with_path_and_pipe; tests::supports_rg_files_then_head
    # Contract: shell.display_summary list commands
    def test_display_summary_rg_files_pipeline_variants(self):
        self.assertEqual(
            parse_command(["bash", "-lc", "rg --files webview/src | sed -n"]),
            [ParsedCommand.list_files("rg --files webview/src", "webview")],
        )
        self.assertEqual(
            parse_command(["bash", "-lc", "rg --files | head -n 50"]),
            [ParsedCommand.list_files("rg --files")],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::rg_files_with_matches_flags_are_search; tests::rg_with_equals_style_flags
    # Contract: shell.display_summary search commands
    def test_display_summary_rg_search_variants(self):
        cases = [
            (
                split("rg -l TODO src"),
                ParsedCommand.search("rg -l TODO src", query="TODO", path="src"),
            ),
            (
                split("rg --files-with-matches TODO src"),
                ParsedCommand.search("rg --files-with-matches TODO src", query="TODO", path="src"),
            ),
            (
                split("rg --colors=never -n foo src"),
                ParsedCommand.search("rg '--colors=never' -n foo src", query="foo", path="src"),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_ag_ack_pt_rga; tests::ag_ack_pt_files_with_matches_flags_are_search
    # Contract: shell.display_summary search commands
    def test_display_summary_ag_ack_pt_search_variants(self):
        cases = [
            (
                split("ag TODO src"),
                ParsedCommand.search("ag TODO src", query="TODO", path="src"),
            ),
            (
                split("ack TODO src"),
                ParsedCommand.search("ack TODO src", query="TODO", path="src"),
            ),
            (
                split("pt TODO src"),
                ParsedCommand.search("pt TODO src", query="TODO", path="src"),
            ),
            (
                split("ag -l TODO src"),
                ParsedCommand.search("ag -l TODO src", query="TODO", path="src"),
            ),
            (
                split("ack -l TODO src"),
                ParsedCommand.search("ack -l TODO src", query="TODO", path="src"),
            ),
            (
                split("pt -l TODO src"),
                ParsedCommand.search("pt -l TODO src", query="TODO", path="src"),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_grep_recursive_current_dir; tests::supports_grep_query_with_slashes_not_shortened; tests::supports_grep_weird_backtick_in_query
    # Contract: shell.display_summary search commands
    def test_display_summary_grep_search_variants(self):
        cases = [
            (
                split("grep -R CODEX_SANDBOX_ENV_VAR -n ."),
                ParsedCommand.search("grep -R CODEX_SANDBOX_ENV_VAR -n .", query="CODEX_SANDBOX_ENV_VAR", path="."),
            ),
            (
                split("grep -R src/main.rs -n ."),
                ParsedCommand.search("grep -R src/main.rs -n .", query="src/main.rs", path="."),
            ),
            (
                split("grep -R COD`EX_SANDBOX -n"),
                ParsedCommand.search("grep -R 'COD`EX_SANDBOX' -n", query="COD`EX_SANDBOX"),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::cat_with_double_dash_and_sed_ranges; tests::bin_bash_lc_sed; tests::bin_zsh_lc_sed
    # Contract: shell.display_summary formatting/read pipelines
    def test_display_summary_sed_and_double_dash_read_variants(self):
        cases = [
            (
                split("cat -- ./-strange-file-name"),
                ParsedCommand.read("cat -- ./-strange-file-name", "-strange-file-name", Path("./-strange-file-name")),
            ),
            (
                split("sed -n '12,20p' Cargo.toml"),
                ParsedCommand.read("sed -n '12,20p' Cargo.toml", "Cargo.toml", Path("Cargo.toml")),
            ),
            (
                split("/bin/bash -lc \"sed -n '1,10p' Cargo.toml\""),
                ParsedCommand.read("sed -n '1,10p' Cargo.toml", "Cargo.toml", Path("Cargo.toml")),
            ),
            (
                split("/bin/zsh -lc \"sed -n '1,10p' Cargo.toml\""),
                ParsedCommand.read("sed -n '1,10p' Cargo.toml", "Cargo.toml", Path("Cargo.toml")),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust test: tests::drop_trailing_nl_in_pipeline
    # Contract: shell.display_summary formatting/read pipelines
    def test_display_summary_drops_trailing_nl_pipeline_stage(self):
        self.assertEqual(
            parse_command(split("rg --files | nl -ba")),
            [ParsedCommand.list_files("rg --files")],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::ls_with_time_style_and_path; tests::fd_file_finder_variants; tests::find_basic_name_filter; tests::find_type_only_path; tests::supports_cd_and_rg_files
    # Contract: shell.display_summary finder/path commands
    def test_display_summary_finder_path_and_cd_variants(self):
        cases = [
            (
                split("ls --time-style=long-iso ./dist"),
                ParsedCommand.list_files("ls '--time-style=long-iso' ./dist", "."),
            ),
            (
                split("fd -t f src/"),
                ParsedCommand.list_files("fd -t f src/", "src"),
            ),
            (
                split("fd main src"),
                ParsedCommand.search("fd main src", query="main", path="src"),
            ),
            (
                split("find . -name '*.rs'"),
                ParsedCommand.search("find . -name '*.rs'", query="*.rs", path="."),
            ),
            (
                split("find src -type f"),
                ParsedCommand.list_files("find src -type f", "src"),
            ),
            (
                split("cd codex-rs && rg --files"),
                ParsedCommand.list_files("rg --files"),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_python_walks_files; tests::supports_python3_walks_files; tests::python_without_file_walk_is_unknown; tests::supports_awk_with_file
    # Contract: shell.display_summary miscellaneous commands
    def test_display_summary_python_and_awk_misc_variants(self):
        cases = [
            (
                ["bash", "-lc", 'python -c "import os; print(os.listdir(\'.\'))"'],
                ParsedCommand.list_files("python -c 'import os; print(os.listdir('\"'\"'.'\"'\"'))'"),
            ),
            (
                ["bash", "-lc", 'python3 -c "import glob; print(glob.glob(\'*.rs\'))"'],
                ParsedCommand.list_files("python3 -c 'import glob; print(glob.glob('\"'\"'*.rs'\"'\"'))'"),
            ),
            (
                ["bash", "-lc", 'python -c "print(\'hello\')"'],
                ParsedCommand.unknown("python -c 'print('\"'\"'hello'\"'\"')'"),
            ),
            (
                ["bash", "-lc", "awk '{print $1}' Cargo.toml"],
                ParsedCommand.read("awk '{print $1}' Cargo.toml", "Cargo.toml", Path("Cargo.toml")),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::filters_out_printf; tests::drops_yes_in_pipelines; tests::preserves_rg_with_spaces; tests::strips_true_in_sequence; tests::strips_true_inside_bash_lc
    # Contract: shell.display_summary miscellaneous command filtering
    def test_display_summary_small_command_filtering_variants(self):
        self.assertEqual(
            parse_command(["bash", "-lc", 'printf "\\n===== ansi-escape/Cargo.toml =====\\n"; cat -- ansi-escape/Cargo.toml']),
            [ParsedCommand.read("cat -- ansi-escape/Cargo.toml", "Cargo.toml", Path("ansi-escape/Cargo.toml"))],
        )
        cases = [
            (
                ["bash", "-lc", "yes | rg --files"],
                ParsedCommand.list_files("rg --files"),
            ),
            (
                split("yes | rg -n 'foo bar' -S"),
                ParsedCommand.search("rg -n 'foo bar' -S", query="foo bar"),
            ),
            (
                split("true && rg --files"),
                ParsedCommand.list_files("rg --files"),
            ),
            (
                split("rg --files && true"),
                ParsedCommand.list_files("rg --files"),
            ),
            (
                ["bash", "-lc", "true && rg --files"],
                ParsedCommand.list_files("rg --files"),
            ),
            (
                ["bash", "-lc", "rg --files || true"],
                ParsedCommand.list_files("rg --files"),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::head_with_no_space; tests::tail_with_no_space; tests::bash_dash_c_pipeline_parsing; tests::ls_with_glob
    # Contract: shell.display_summary miscellaneous command syntax
    def test_display_summary_misc_shell_syntax_variants(self):
        cases = [
            (
                split("bash -lc 'head -n50 Cargo.toml'"),
                ParsedCommand.read("head -n50 Cargo.toml", "Cargo.toml", Path("Cargo.toml")),
            ),
            (
                split("bash -lc 'tail -n+10 README.md'"),
                ParsedCommand.read("tail -n+10 README.md", "README.md", Path("README.md")),
            ),
            (
                ["bash", "-c", "rg --files | head -n 1"],
                ParsedCommand.list_files("rg --files"),
            ),
            (
                split("ls -I '*.test.js'"),
                ParsedCommand.list_files("ls -I '*.test.js'"),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::cd_then_cat_is_single_read; tests::cd_with_double_dash_then_cat_is_read; tests::cd_with_multiple_operands_uses_last; tests::bash_cd_then_bar_is_same_as_bar; tests::bash_cd_then_cat_is_read
    # Contract: shell.display_summary cd context
    def test_display_summary_cd_context_residual_variants(self):
        cases = [
            (
                split("cd foo && cat foo.txt"),
                ParsedCommand.read("cat foo.txt", "foo.txt", Path("foo/foo.txt")),
            ),
            (
                split("cd -- -weird && cat foo.txt"),
                ParsedCommand.read("cat foo.txt", "foo.txt", Path("-weird/foo.txt")),
            ),
            (
                split("cd dir1 dir2 && cat foo.txt"),
                ParsedCommand.read("cat foo.txt", "foo.txt", Path("dir2/foo.txt")),
            ),
            (
                ["bash", "-lc", "cd foo && cat foo.txt"],
                ParsedCommand.read("cat foo.txt", "foo.txt", Path("foo/foo.txt")),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])
        self.assertEqual(
            parse_command(["bash", "-lc", "cd foo && bar"]),
            [ParsedCommand.unknown("cd foo && bar")],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_npm_run_build_is_unknown; tests::handles_complex_bash_command_head; tests::handles_complex_bash_command; tests::collapses_pipeline_with_helper_when_later_stage_is_unknown
    # Contract: shell.display_summary unknown/pipeline residuals
    def test_display_summary_unknown_and_complex_pipeline_residual_variants(self):
        self.assertEqual(
            parse_command(split("npm run build")),
            [ParsedCommand.unknown("npm run build")],
        )
        complex_head = "rg --version && node -v && pnpm -v && rg --files | wc -l && rg --files | head -n 40"
        self.assertEqual(
            parse_command(["bash", "-lc", complex_head]),
            [ParsedCommand.unknown(complex_head)],
        )
        self.assertEqual(
            parse_command(["bash", "-lc", "rg -n \"BUG|FIXME|TODO|XXX|HACK\" -S | head -n 200"]),
            [ParsedCommand.search("rg -n 'BUG|FIXME|TODO|XXX|HACK' -S", query="BUG|FIXME|TODO|XXX|HACK")],
        )
        command = split("rg --files | nl -ba | foo")
        self.assertEqual(parse_command(command), [ParsedCommand.unknown(shlex_join(command))])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_grep_recursive_specific_file; tests::supports_egrep_and_fgrep; tests::grep_files_with_matches_flags_are_search; tests::grep_with_query_and_path; tests::supports_single_string_script_with_cd_and_pipe
    # Contract: shell.display_summary search residuals
    def test_display_summary_search_residual_variants(self):
        cases = [
            (
                split("grep -R CODEX_SANDBOX_ENV_VAR -n core/src/spawn.rs"),
                ParsedCommand.search("grep -R CODEX_SANDBOX_ENV_VAR -n core/src/spawn.rs", query="CODEX_SANDBOX_ENV_VAR", path="spawn.rs"),
            ),
            (
                split("egrep -R TODO src"),
                ParsedCommand.search("egrep -R TODO src", query="TODO", path="src"),
            ),
            (
                split("fgrep -l TODO src"),
                ParsedCommand.search("fgrep -l TODO src", query="TODO", path="src"),
            ),
            (
                split("grep -l TODO src"),
                ParsedCommand.search("grep -l TODO src", query="TODO", path="src"),
            ),
            (
                split("grep --files-with-matches TODO src"),
                ParsedCommand.search("grep --files-with-matches TODO src", query="TODO", path="src"),
            ),
            (
                split("grep -L TODO src"),
                ParsedCommand.search("grep -L TODO src", query="TODO", path="src"),
            ),
            (
                split("grep -R TODO src"),
                ParsedCommand.search("grep -R TODO src", query="TODO", path="src"),
            ),
            (
                ["bash", "-lc", 'cd /Users/pakrym/code/codex && rg -n "codex_api" codex-rs -S | head -n 50'],
                ParsedCommand.search("rg -n codex_api codex-rs -S", query="codex_api", path="codex-rs"),
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::small_formatting_always_true_commands; tests::awk_behavior; tests::head_behavior; tests::tail_behavior; tests::sed_behavior; tests::empty_tokens_is_not_small
    # Contract: shell.display_summary small formatting residuals
    def test_display_summary_small_formatting_residual_variants(self):
        self.assertFalse(is_small_formatting_command([]))
        for command in ("wc", "tr", "cut", "sort", "uniq", "xargs", "tee", "column"):
            with self.subTest(command=command):
                self.assertTrue(is_small_formatting_command(split(command)))
                self.assertTrue(is_small_formatting_command(split(f"{command} -x")))
        true_cases = [
            "awk '{print $1}'",
            "head",
            "head -n 40",
            "tail",
            "tail -n +10",
            "tail -n 30",
            "tail -c 30",
            "tail -c +10",
            "sed",
            "sed -n 10p",
            "sed -n p file.txt",
            "sed -n +10p file.txt",
        ]
        false_cases = [
            "awk '{print $1}' Cargo.toml",
            "awk -f script.awk Cargo.toml",
            "head -n 40 file.txt",
            "head file.txt",
            "tail -n +10 file.txt",
            "tail -n 30 file.txt",
            "tail file.txt",
            "sed -n 10p file.txt",
            "sed -n -e 10p file.txt",
            "sed -n 10p -- file.txt",
            "sed -n 1,200p file.txt",
        ]
        for command in true_cases:
            with self.subTest(command=command, expected=True):
                self.assertTrue(is_small_formatting_command(split(command)))
        for command in false_cases:
            with self.subTest(command=command, expected=False):
                self.assertFalse(is_small_formatting_command(split(command)))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::supports_nl_then_sed_reading; tests::supports_sed_n; tests::supports_sed_n_then_nl_as_search; tests::shorten_path_on_windows
    # Contract: shell.display_summary read residuals
    def test_display_summary_read_residual_variants(self):
        inner = "nl -ba core/src/parse_command.rs | sed -n '1200,1720p'"
        self.assertEqual(
            parse_command(["bash", "-lc", inner]),
            [ParsedCommand.read(inner, "parse_command.rs", Path("core/src/parse_command.rs"))],
        )
        inner = "sed -n '2000,2200p' tui/src/history_cell.rs"
        self.assertEqual(
            parse_command(["bash", "-lc", inner]),
            [ParsedCommand.read(inner, "history_cell.rs", Path("tui/src/history_cell.rs"))],
        )
        self.assertEqual(
            parse_command(split("sed -n '260,640p' exec/src/event_processor_with_human_output.rs | nl -ba")),
            [
                ParsedCommand.read(
                    "sed -n '260,640p' exec/src/event_processor_with_human_output.rs",
                    "event_processor_with_human_output.rs",
                    Path("exec/src/event_processor_with_human_output.rs"),
                )
            ],
        )
        self.assertEqual(
            parse_command(split(r'cat "pkg\src\main.rs"')),
            [ParsedCommand.read(r"cat 'pkg\src\main.rs'", "main.rs", Path(r"pkg\src\main.rs"))],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/parse_command.rs
    # Rust tests: tests::powershell_command_is_stripped; tests::pwsh_with_noprofile_and_c_alias_is_stripped; tests::powershell_with_path_is_stripped
    # Contract: shell.display_summary PowerShell wrapper residuals
    def test_display_summary_powershell_wrapper_residual_variants(self):
        cases = [
            (["powershell", "-Command", "Get-ChildItem"], ParsedCommand.unknown("Get-ChildItem")),
            (["pwsh", "-NoProfile", "-c", "Write-Host hi"], ParsedCommand.unknown("Write-Host hi")),
            (["/usr/local/bin/powershell.exe", "-NoProfile", "-c", "Write-Host hi"], ParsedCommand.unknown("Write-Host hi")),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(parse_command(command), [expected])

    # Source: rust_source_inferred
    # Rust crate: codex-shell-command
    # Rust module: src/powershell.rs
    # Rust tests: tests::extracts_basic_powershell_command; tests::extracts_lowercase_flags; tests::extracts_full_path_powershell_command; tests::extracts_with_noprofile_and_alias
    # Contract: shell.powershell_parsing
    def test_powershell_wrapper_extracts_script(self):
        self.assertEqual(
            extract_powershell_command(["powershell", "-Command", "Write-Host hi"]),
            ("powershell", "Write-Host hi"),
        )
        self.assertEqual(
            extract_powershell_command(["powershell", "-nologo", "-command", "Write-Host hi"]),
            ("powershell", "Write-Host hi"),
        )
        self.assertEqual(
            extract_powershell_command(["/usr/local/bin/powershell.exe", "-Command", "Write-Host hi"]),
            ("/usr/local/bin/powershell.exe", "Write-Host hi"),
        )
        self.assertEqual(
            extract_powershell_command(["pwsh", "-NoProfile", "-c", "Write-Host hi"]),
            ("pwsh", "Write-Host hi"),
        )
        self.assertEqual(
            parse_command(["powershell.exe", "-NoProfile", "-Command", "Write-Host hi"]),
            [ParsedCommand.unknown("Write-Host hi")],
        )

    # Source: rust_source_inferred
    # Rust crate: codex-shell-command
    # Rust module: src/powershell.rs
    # Rust item: prefix_powershell_script_with_utf8
    # Contract: shell.powershell_parsing
    def test_powershell_utf8_prefix_is_added_once(self):
        command = ["pwsh", "-NoProfile", "-Command", "Write-Output hi"]
        self.assertEqual(
            prefix_powershell_script_with_utf8(command),
            ["pwsh", "-NoProfile", "-Command", f"{UTF8_OUTPUT_PREFIX}Write-Output hi"],
        )
        already_prefixed = ["pwsh", "-c", f"  {UTF8_OUTPUT_PREFIX}Write-Output hi"]
        self.assertEqual(prefix_powershell_script_with_utf8(already_prefixed), already_prefixed)
        non_powershell = ["bash", "-lc", "echo hi"]
        self.assertEqual(prefix_powershell_script_with_utf8(non_powershell), non_powershell)

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/powershell.rs
    # Rust tests: tests::parses_plain_powershell_commands; tests::parses_multiple_plain_powershell_commands
    # Contract: shell.powershell_parsing
    def test_powershell_plain_commands_parse_simple_ast_surface(self):
        self.assertEqual(
            parse_powershell_command_into_plain_commands(
                ["powershell.exe", "-NoProfile", "-Command", "echo hi"]
            ),
            [["echo", "hi"]],
        )
        self.assertEqual(
            parse_powershell_command_into_plain_commands(
                ["powershell.exe", "-NoProfile", "-Command", "Write-Output foo | Measure-Object"]
            ),
            [["Write-Output", "foo"], ["Measure-Object"]],
        )
        self.assertIsNone(
            parse_powershell_command_into_plain_commands(
                ["powershell.exe", "-NoProfile", "-EncodedCommand", "AAAA"]
            )
        )

    # Source: rust_source_inferred
    # Rust crate: codex-shell-command
    # Rust module: src/bash.rs
    # Rust items: parse_shell_lc_plain_commands; try_parse_word_only_commands_sequence
    # Contract: shell.bash_lc_parsing
    def test_bash_plain_commands_reject_empty_shell_segments(self):
        self.assertIsNone(parse_shell_lc_plain_commands(["bash", "-lc", ""]))
        self.assertIsNone(parse_shell_lc_plain_commands(["bash", "-lc", "  \n\t  "]))
        self.assertIsNone(parse_shell_lc_plain_commands(["bash", "-lc", "ls &&"]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/bash.rs
    # Rust tests: tests::accepts_single_simple_command; tests::accepts_multiple_commands_with_allowed_operators; tests::parse_zsh_lc_plain_commands
    # Contract: shell.bash_lc_parsing
    def test_bash_plain_commands_accept_simple_sequences(self):
        self.assertEqual(
            parse_shell_lc_plain_commands(["bash", "-lc", "ls -1"]),
            [["ls", "-1"]],
        )
        self.assertEqual(
            parse_shell_lc_plain_commands(["bash", "-lc", "ls && pwd; echo 'hi there' | wc -l"]),
            [["ls"], ["pwd"], ["echo", "hi there"], ["wc", "-l"]],
        )
        self.assertEqual(
            parse_shell_lc_plain_commands(["zsh", "-lc", "ls"]),
            [["ls"]],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/bash.rs
    # Rust tests: tests::extracts_double_and_single_quoted_strings; tests::accepts_double_quoted_strings_with_newlines; tests::accepts_numbers_as_words
    # Contract: shell.bash_lc_parsing
    def test_bash_plain_commands_accept_literal_words_and_quotes(self):
        self.assertEqual(
            parse_shell_lc_plain_commands(["bash", "-lc", 'echo "hello world"']),
            [["echo", "hello world"]],
        )
        self.assertEqual(
            parse_shell_lc_plain_commands(["bash", "-lc", "echo 'hi there'"]),
            [["echo", "hi there"]],
        )
        self.assertEqual(
            parse_shell_lc_plain_commands(["bash", "-lc", 'git commit -m "line1\nline2"']),
            [["git", "commit", "-m", "line1\nline2"]],
        )
        self.assertEqual(
            parse_shell_lc_plain_commands(["bash", "-lc", "echo 123 456"]),
            [["echo", "123", "456"]],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/bash.rs
    # Rust tests: tests::accepts_mixed_quote_concatenation; tests::accepts_concatenated_flag_and_value; tests::accepts_concatenated_flag_with_single_quotes
    # Contract: shell.bash_lc_parsing
    def test_bash_plain_commands_accept_literal_concatenation(self):
        self.assertEqual(
            parse_shell_lc_plain_commands(["bash", "-lc", "echo \"/usr\"'/'\"local\"/bin"]),
            [["echo", "/usr/local/bin"]],
        )
        self.assertEqual(
            parse_shell_lc_plain_commands(["bash", "-lc", "echo '/usr'\"/\"'local'/bin"]),
            [["echo", "/usr/local/bin"]],
        )
        self.assertEqual(
            parse_shell_lc_plain_commands(["bash", "-lc", 'rg -n "foo" -g"*.py"']),
            [["rg", "-n", "foo", "-g*.py"]],
        )
        self.assertEqual(
            parse_shell_lc_plain_commands(["bash", "-lc", "grep -n 'pattern' -g'*.txt'"]),
            [["grep", "-n", "pattern", "-g*.txt"]],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/bash.rs
    # Rust tests: tests::rejects_double_quoted_strings_with_expansions; tests::rejects_command_and_process_substitutions_and_expansions; tests::rejects_variable_assignment_prefix
    # Contract: shell.bash_lc_parsing
    def test_bash_plain_commands_reject_expansions_and_assignments(self):
        for script in (
            r'echo "hi ${USER}"',
            r'echo "$HOME"',
            "echo $(pwd)",
            "echo `pwd`",
            "echo $HOME",
            r'echo "hi $USER"',
            "FOO=bar ls",
            r'rg -g"$VAR" pattern',
            r'rg -g"${VAR}" pattern',
            r'rg -g"$(pwd)" pattern',
            r'rg -g"$(echo \'*.py\')" pattern',
        ):
            with self.subTest(script=script):
                self.assertIsNone(parse_shell_lc_plain_commands(["bash", "-lc", script]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/bash.rs
    # Rust tests: tests::rejects_parentheses_and_subshells; tests::rejects_redirections_and_unsupported_operators; tests::rejects_trailing_operator_parse_error; tests::rejects_empty_command_position_with_leading_operator; tests::rejects_empty_command_position_with_double_separator; tests::rejects_empty_command_position_with_empty_pipeline_segment
    # Contract: shell.bash_lc_parsing
    def test_bash_plain_commands_reject_unsupported_structure(self):
        for script in (
            "(ls)",
            "ls || (pwd && echo hi)",
            "ls > out.txt",
            "echo hi & echo bye",
            "ls &&",
            "&& ls",
            "ls ;; pwd",
            "ls | | wc",
        ):
            with self.subTest(script=script):
                self.assertIsNone(parse_shell_lc_plain_commands(["bash", "-lc", script]))

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/bash.rs
    # Rust test: tests::parse_shell_lc_single_command_prefix_supports_heredoc
    # Contract: shell.bash_lc_parsing
    def test_bash_single_command_prefix_supports_heredoc(self):
        self.assertEqual(
            parse_shell_lc_single_command_prefix(["zsh", "-lc", "python3 <<'PY'\nprint('hello')\nPY"]),
            ["python3"],
        )
        self.assertEqual(
            parse_shell_lc_single_command_prefix(["zsh", "-lc", "python3 << PY\nprint('hello')\nPY"]),
            ["python3"],
        )

    # Source: rust_test_migrated
    # Rust crate: codex-shell-command
    # Rust module: src/bash.rs
    # Rust tests: tests::parse_shell_lc_single_command_prefix_rejects_multi_command_scripts; tests::parse_shell_lc_single_command_prefix_rejects_non_heredoc_redirects; tests::parse_shell_lc_single_command_prefix_rejects_heredoc_with_extra_file_redirect; tests::parse_shell_lc_single_command_prefix_rejects_heredoc_with_variable_assignment; tests::parse_shell_lc_single_command_prefix_rejects_heredoc_command_with_word_expansion
    # Contract: shell.bash_lc_parsing
    def test_bash_single_command_prefix_rejects_complex_heredocs(self):
        self.assertIsNone(
            parse_shell_lc_single_command_prefix(["bash", "-lc", "python3 <<'PY'\nprint('hello')\nPY\necho done"])
        )
        self.assertIsNone(parse_shell_lc_single_command_prefix(["bash", "-lc", "echo hello > /tmp/out.txt"]))
        self.assertIsNone(
            parse_shell_lc_single_command_prefix(["bash", "-lc", "python3 <<'PY' > /tmp/out.txt\nprint('hello')\nPY"])
        )
        self.assertIsNone(
            parse_shell_lc_single_command_prefix(["bash", "-lc", "PATH=/tmp/evil:$PATH cat <<'EOF'\nhello\nEOF"])
        )
        self.assertIsNone(
            parse_shell_lc_single_command_prefix(["bash", "-lc", "python3 $((1<<2)) <<'PY'\nprint('hello')\nPY"])
        )
        self.assertIsNone(
            parse_shell_lc_single_command_prefix(["bash", "-lc", 'python3 <<< "$(rm -rf /)"'])
        )
        self.assertIsNone(
            parse_shell_lc_single_command_prefix(["bash", "-lc", "echo $((1<<2))"])
        )


if __name__ == "__main__":
    unittest.main()
