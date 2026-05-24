"""Parse shell commands into Codex display summaries.

Ported from ``codex/codex-rs/shell-command/src/parse_command.rs`` with a
standard-library shell tokenizer instead of tree-sitter. The public protocol
shape is identical; the parser intentionally falls back to ``unknown`` when the
script is not a plain word-only command sequence.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Iterable, Sequence

from pycodex.protocol.parse_command import ParsedCommand


CONNECTORS = {"&&", "||", "|", ";"}
POWERSHELL_FLAGS = {"-nologo", "-noprofile", "-command", "-c"}


def shlex_join(tokens: Sequence[str]) -> str:
    if any("\0" in token for token in tokens):
        return "<command included NUL byte>"
    return shlex.join(list(tokens))


def _shlex_split(value: str) -> list[str] | None:
    try:
        return shlex.split(value)
    except ValueError:
        return None


def _executable_name(path: str) -> str:
    normalized = path.replace("\\", "/").rstrip("/")
    name = normalized.rsplit("/", 1)[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def _is_bashish(path: str) -> bool:
    return _executable_name(path) in {"bash", "zsh", "sh"}


def _is_powershellish(path: str) -> bool:
    return _executable_name(path) in {"powershell", "pwsh"}


def extract_bash_command(command: Sequence[str]) -> tuple[str, str] | None:
    if len(command) != 3:
        return None
    shell, flag, script = command
    if flag not in {"-lc", "-c"} or not _is_bashish(shell):
        return None
    return shell, script


def extract_powershell_command(command: Sequence[str]) -> tuple[str, str] | None:
    if len(command) < 3 or not _is_powershellish(command[0]):
        return None
    index = 1
    while index + 1 < len(command):
        flag = command[index]
        flag_lc = flag.lower()
        if flag_lc not in POWERSHELL_FLAGS:
            return None
        if flag_lc in {"-command", "-c"}:
            return command[0], command[index + 1]
        index += 1
    return None


def extract_shell_command(command: Sequence[str]) -> tuple[str, str] | None:
    return extract_bash_command(command) or extract_powershell_command(command)


def parse_command(command: Sequence[str]) -> list[ParsedCommand]:
    parsed = parse_command_impl(command)
    deduped: list[ParsedCommand] = []
    for item in parsed:
        if deduped and deduped[-1] == item:
            continue
        deduped.append(item)
    if any(item.type == "unknown" for item in deduped):
        return [_single_unknown_for_command(command)]
    return deduped


def _single_unknown_for_command(command: Sequence[str]) -> ParsedCommand:
    extracted = extract_shell_command(command)
    if extracted is not None:
        return ParsedCommand.unknown(extracted[1])
    return ParsedCommand.unknown(shlex_join(command))


def parse_command_impl(command: Sequence[str]) -> list[ParsedCommand]:
    shell_commands = parse_shell_lc_commands(command)
    if shell_commands is not None:
        return shell_commands

    powershell = extract_powershell_command(command)
    if powershell is not None:
        return [ParsedCommand.unknown(powershell[1])]

    normalized = normalize_tokens(command)
    parts = split_on_connectors(normalized) if contains_connectors(normalized) else [normalized]

    commands: list[ParsedCommand] = []
    cwd: str | None = None
    for tokens in parts:
        if tokens and tokens[0] == "cd":
            target = cd_target(tokens[1:])
            if target is not None:
                cwd = join_paths(cwd, target) if cwd is not None else target
            continue
        parsed = _apply_cwd_to_read(summarize_main_tokens(tokens), cwd)
        commands.append(parsed)

    return simplify_commands(commands)


def parse_shell_lc_plain_commands(command: Sequence[str]) -> list[list[str]] | None:
    """Return word-only commands from a bash/zsh/sh wrapper.

    This mirrors ``bash::parse_shell_lc_plain_commands`` for callers that need a
    safety-oriented argv view. It is intentionally conservative with the
    standard library tokenizer: unsupported shell punctuation, redirection, and
    subshell-like tokens return ``None``.
    """

    extracted = extract_bash_command(command)
    if extracted is None:
        return None
    tokens = _shlex_split(extracted[1])
    if tokens is None or _contains_unsupported_shell_token(tokens):
        return None
    if _has_empty_connector_segment(tokens):
        return None
    commands = split_on_connectors(tokens) if contains_connectors(tokens) else [tokens]
    if not commands or any(not item for item in commands):
        return None
    return commands


def parse_shell_lc_single_command_prefix(command: Sequence[str]) -> list[str] | None:
    """Return the command words before a single heredoc redirect.

    Upstream uses tree-sitter to accept a single command with ``<<`` and reject
    other redirects, chained commands, substitutions, and assignment prefixes.
    This stdlib port keeps the same conservative surface for exec-policy
    matching.
    """

    extracted = extract_bash_command(command)
    if extracted is None:
        return None
    script = extracted[1]
    if "<<" not in script or "<<<" in script:
        return None

    prefix, rest = script.split("<<", 1)
    prefix = prefix.strip()
    if not prefix or any(marker in prefix for marker in (";", "|", "&", ">", "<", "$", "`", "(", ")", "{", "}")):
        return None

    newline_index = rest.find("\n")
    if newline_index < 0:
        return None
    heredoc_header = rest[:newline_index].strip()
    heredoc_body = rest[newline_index + 1 :]

    delimiter_tokens = _shlex_split(heredoc_header)
    if delimiter_tokens is None or len(delimiter_tokens) != 1:
        return None
    delimiter = delimiter_tokens[0]
    if not delimiter:
        return None

    lines = heredoc_body.splitlines()
    terminator_index = next((index for index, line in enumerate(lines) if line.strip() == delimiter), None)
    if terminator_index is None:
        return None
    if any(line.strip() for line in lines[terminator_index + 1 :]):
        return None

    words = _shlex_split(prefix)
    if words is None or not words:
        return None
    if "=" in words[0]:
        return None
    if _contains_unsupported_shell_token(words):
        return None
    return words


def simplify_commands(commands: list[ParsedCommand]) -> list[ParsedCommand]:
    while True:
        next_commands = simplify_once(commands)
        if next_commands is None:
            return commands
        commands = next_commands


def simplify_once(commands: Sequence[ParsedCommand]) -> list[ParsedCommand] | None:
    if len(commands) <= 1:
        return None

    first = commands[0]
    first_tokens = _shlex_split(first.cmd) if first.type == "unknown" else None
    if first_tokens and first_tokens[:1] == ["echo"]:
        return list(commands[1:])

    for index, item in enumerate(commands):
        tokens = _shlex_split(item.cmd) if item.type == "unknown" else None
        if tokens and tokens[:1] == ["cd"] and len(commands) > index + 1:
            return list(commands[:index]) + list(commands[index + 1 :])

    for index, item in enumerate(commands):
        if item.type == "unknown" and item.cmd == "true":
            return list(commands[:index]) + list(commands[index + 1 :])

    for index, item in enumerate(commands):
        tokens = _shlex_split(item.cmd) if item.type == "unknown" else None
        if tokens and tokens[0] == "nl" and all(token.startswith("-") for token in tokens[1:]):
            return list(commands[:index]) + list(commands[index + 1 :])

    return None


def is_valid_sed_n_arg(arg: str | None) -> bool:
    if arg is None or not arg.endswith("p"):
        return False
    core = arg[:-1]
    parts = core.split(",")
    if len(parts) == 1:
        return bool(parts[0]) and parts[0].isdigit()
    if len(parts) == 2:
        return bool(parts[0]) and bool(parts[1]) and parts[0].isdigit() and parts[1].isdigit()
    return False


def sed_read_path(args: Sequence[str]) -> str | None:
    args_no_connector = trim_at_connector(args)
    if "-n" not in args_no_connector:
        return None
    has_range_script = False
    index = 0
    while index < len(args_no_connector):
        arg = args_no_connector[index]
        if arg in {"-e", "--expression"}:
            if is_valid_sed_n_arg(args_no_connector[index + 1] if index + 1 < len(args_no_connector) else None):
                has_range_script = True
            index += 2
            continue
        if arg in {"-f", "--file"}:
            index += 2
            continue
        index += 1
    if not has_range_script:
        has_range_script = any(
            not arg.startswith("-") and is_valid_sed_n_arg(arg)
            for arg in args_no_connector
        )
    if not has_range_script:
        return None
    candidates = skip_flag_values(args_no_connector, ["-e", "-f", "--expression", "--file"])
    non_flags = [arg for arg in candidates if not arg.startswith("-")]
    if not non_flags:
        return None
    if is_valid_sed_n_arg(non_flags[0]):
        return non_flags[1] if len(non_flags) > 1 else None
    return non_flags[0]


def normalize_tokens(cmd: Sequence[str]) -> list[str]:
    if len(cmd) >= 2 and cmd[0] in {"yes", "y"} and cmd[1] == "|":
        return list(cmd[2:])
    if len(cmd) >= 2 and cmd[0] in {"no", "n"} and cmd[1] == "|":
        return list(cmd[2:])
    if len(cmd) == 3 and cmd[0] in {"bash", "zsh"} and cmd[1] in {"-c", "-lc"}:
        return _shlex_split(cmd[2]) or list(cmd)
    return list(cmd)


def contains_connectors(tokens: Sequence[str]) -> bool:
    return any(token in CONNECTORS for token in tokens)


def _has_empty_connector_segment(tokens: Sequence[str]) -> bool:
    previous_was_connector = True
    for token in tokens:
        if token in CONNECTORS:
            if previous_was_connector:
                return True
            previous_was_connector = True
        else:
            previous_was_connector = False
    return previous_was_connector


def split_on_connectors(tokens: Sequence[str]) -> list[list[str]]:
    out: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in CONNECTORS:
            if current:
                out.append(current)
                current = []
        else:
            current.append(token)
    if current:
        out.append(current)
    return out


def trim_at_connector(tokens: Sequence[str]) -> list[str]:
    for index, token in enumerate(tokens):
        if token in CONNECTORS:
            return list(tokens[:index])
    return list(tokens)


def short_display_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    trimmed = normalized.rstrip("/")
    for part in reversed(trimmed.split("/")):
        if part and part not in {"build", "dist", "node_modules", "src"}:
            return part
    return trimmed


def skip_flag_values(args: Sequence[str], flags_with_vals: Iterable[str]) -> list[str]:
    flags = set(flags_with_vals)
    out: list[str] = []
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == "--":
            out.extend(args[index + 1 :])
            break
        if arg.startswith("--") and "=" in arg:
            continue
        if arg in flags:
            if index + 1 < len(args):
                skip_next = True
            continue
        out.append(arg)
    return out


def positional_operands(args: Sequence[str], flags_with_vals: Iterable[str]) -> list[str]:
    flags = set(flags_with_vals)
    out: list[str] = []
    after_double_dash = False
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if after_double_dash:
            out.append(arg)
            continue
        if arg == "--":
            after_double_dash = True
            continue
        if arg.startswith("--") and "=" in arg:
            continue
        if arg in flags:
            if index + 1 < len(args):
                skip_next = True
            continue
        if arg.startswith("-"):
            continue
        out.append(arg)
    return out


def first_non_flag_operand(args: Sequence[str], flags_with_vals: Iterable[str]) -> str | None:
    operands = positional_operands(args, flags_with_vals)
    return operands[0] if operands else None


def single_non_flag_operand(args: Sequence[str], flags_with_vals: Iterable[str]) -> str | None:
    operands = positional_operands(args, flags_with_vals)
    return operands[0] if len(operands) == 1 else None


def parse_grep_like(main_cmd: Sequence[str], args: Sequence[str]) -> ParsedCommand:
    args_no_connector = trim_at_connector(args)
    operands: list[str] = []
    pattern: str | None = None
    after_double_dash = False
    index = 0
    while index < len(args_no_connector):
        arg = args_no_connector[index]
        index += 1
        if after_double_dash:
            operands.append(arg)
            continue
        if arg == "--":
            after_double_dash = True
            continue
        if arg in {"-e", "--regexp", "-f", "--file"}:
            if index < len(args_no_connector) and pattern is None:
                pattern = args_no_connector[index]
            index += 1
            continue
        if arg in {
            "-m",
            "--max-count",
            "-C",
            "--context",
            "-A",
            "--after-context",
            "-B",
            "--before-context",
        }:
            index += 1
            continue
        if arg.startswith("-"):
            continue
        operands.append(arg)
    has_pattern = pattern is not None
    query = pattern if pattern is not None else (operands[0] if operands else None)
    path_index = 0 if has_pattern else 1
    path = short_display_path(operands[path_index]) if len(operands) > path_index else None
    return ParsedCommand.search(cmd=shlex_join(main_cmd), query=query, path=path)


def awk_data_file_operand(args: Sequence[str]) -> str | None:
    if not args:
        return None
    args_no_connector = trim_at_connector(args)
    has_script_file = any(arg in {"-f", "--file"} for arg in args_no_connector)
    candidates = skip_flag_values(
        args_no_connector,
        ["-F", "-v", "-f", "--field-separator", "--assign", "--file"],
    )
    non_flags = [arg for arg in candidates if not arg.startswith("-")]
    if has_script_file:
        return non_flags[0] if non_flags else None
    if len(non_flags) >= 2:
        return non_flags[1]
    return None


def python_walks_files(args: Sequence[str]) -> bool:
    args_no_connector = trim_at_connector(args)
    index = 0
    while index < len(args_no_connector):
        arg = args_no_connector[index]
        index += 1
        if arg == "-c" and index < len(args_no_connector):
            script = args_no_connector[index]
            return any(
                marker in script
                for marker in (
                    "os.walk",
                    "os.listdir",
                    "os.scandir",
                    "glob.glob",
                    "glob.iglob",
                    "pathlib.Path",
                    ".rglob(",
                )
            )
    return False


def is_python_command(cmd: str) -> bool:
    return (
        cmd in {"python", "python2", "python3"}
        or cmd.startswith("python2.")
        or cmd.startswith("python3.")
    )


def cd_target(args: Sequence[str]) -> str | None:
    target: str | None = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            return args[index + 1] if index + 1 < len(args) else None
        if arg in {"-L", "-P"} or arg.startswith("-"):
            index += 1
            continue
        target = arg
        index += 1
    return target


def is_pathish(value: str) -> bool:
    return (
        value in {".", ".."}
        or value.startswith("./")
        or value.startswith("../")
        or "/" in value
        or "\\" in value
    )


def parse_fd_query_and_path(tail: Sequence[str]) -> tuple[str | None, str | None]:
    args_no_connector = trim_at_connector(tail)
    candidates = skip_flag_values(
        args_no_connector,
        ["-t", "--type", "-e", "--extension", "-E", "--exclude", "--search-path"],
    )
    non_flags = [arg for arg in candidates if not arg.startswith("-")]
    if len(non_flags) == 1:
        one = non_flags[0]
        if is_pathish(one):
            return None, short_display_path(one)
        return one, None
    if len(non_flags) >= 2:
        return non_flags[0], short_display_path(non_flags[1])
    return None, None


def parse_find_query_and_path(tail: Sequence[str]) -> tuple[str | None, str | None]:
    args_no_connector = trim_at_connector(tail)
    path = None
    for arg in args_no_connector:
        if not arg.startswith("-") and arg not in {"!", "(", ")"}:
            path = short_display_path(arg)
            break
    query = None
    for index, arg in enumerate(args_no_connector):
        if arg in {"-name", "-iname", "-path", "-regex"} and index + 1 < len(args_no_connector):
            query = args_no_connector[index + 1]
            break
    return query, path


def parse_shell_lc_commands(original: Sequence[str]) -> list[ParsedCommand] | None:
    extracted = extract_bash_command(original)
    if extracted is None:
        return None
    script = extracted[1]
    script_tokens = _shlex_split(script)
    if script_tokens is None or _contains_unsupported_shell_token(script_tokens):
        return [ParsedCommand.unknown(script)]

    all_commands = split_on_connectors(script_tokens) if contains_connectors(script_tokens) else [script_tokens]
    if not all_commands:
        return [ParsedCommand.unknown(script)]

    had_multiple_commands = len(all_commands) > 1
    filtered_commands = drop_small_formatting_commands(all_commands)
    if not filtered_commands:
        return [ParsedCommand.unknown(script)]

    commands: list[ParsedCommand] = []
    cwd: str | None = None
    for tokens in filtered_commands:
        if tokens and tokens[0] == "cd":
            target = cd_target(tokens[1:])
            if target is not None:
                cwd = join_paths(cwd, target) if cwd is not None else target
            continue
        commands.append(_apply_cwd_to_read(summarize_main_tokens(tokens), cwd))

    if len(commands) > 1:
        commands = [item for item in commands if not (item.type == "unknown" and item.cmd == "true")]
        commands = simplify_commands(commands)

    if len(commands) == 1:
        had_connectors = had_multiple_commands or contains_connectors(script_tokens)
        commands = [_with_shell_script_command(commands[0], script, script_tokens, had_connectors)]

    return commands


def _contains_unsupported_shell_token(tokens: Sequence[str]) -> bool:
    for token in tokens:
        if token in {"<", ">", ">>", "<<", "<<<", "2>", "2>>", "&>", "&>>", "(", ")", "{", "}"}:
            return True
        if token.startswith((">", "<")):
            return True
        if any(char in token for char in "(){}"):
            return True
    return False


def _with_shell_script_command(
    command: ParsedCommand,
    script: str,
    script_tokens: Sequence[str],
    had_connectors: bool,
) -> ParsedCommand:
    if command.type == "read":
        if had_connectors:
            has_pipe = "|" in script_tokens
            has_sed_n = any(script_tokens[index] == "sed" and script_tokens[index + 1] == "-n" for index in range(len(script_tokens) - 1))
            if has_pipe and has_sed_n:
                return ParsedCommand.read(cmd=script, name=command.name or "", path=command.path or "")
            return command
        return ParsedCommand.read(cmd=shlex_join(script_tokens), name=command.name or "", path=command.path or "")
    if command.type == "list_files":
        return command if had_connectors else ParsedCommand.list_files(cmd=shlex_join(script_tokens), path=_path_as_str(command.path))
    if command.type == "search":
        return command if had_connectors else ParsedCommand.search(
            cmd=shlex_join(script_tokens),
            query=command.query,
            path=_path_as_str(command.path),
        )
    return command


def is_small_formatting_command(tokens: Sequence[str]) -> bool:
    if not tokens:
        return False
    cmd = tokens[0]
    if cmd in {"wc", "tr", "cut", "sort", "uniq", "tee", "column", "yes", "printf"}:
        return True
    if cmd == "xargs":
        return not is_mutating_xargs_command(tokens)
    if cmd == "awk":
        return awk_data_file_operand(tokens[1:]) is None
    if cmd == "head":
        if len(tokens) == 1:
            return True
        if len(tokens) == 2:
            return tokens[1].startswith("-")
        if len(tokens) == 3 and tokens[1] in {"-n", "-c"} and tokens[2].isdigit():
            return True
        return False
    if cmd == "tail":
        if len(tokens) == 1:
            return True
        if len(tokens) == 2:
            return tokens[1].startswith("-")
        if len(tokens) == 3 and tokens[1] in {"-n", "-c"}:
            value = tokens[2][1:] if tokens[2].startswith("+") else tokens[2]
            return value.isdigit()
        return False
    if cmd == "sed":
        return sed_read_path(tokens[1:]) is None
    return False


def is_mutating_xargs_command(tokens: Sequence[str]) -> bool:
    subcommand = xargs_subcommand(tokens)
    return subcommand is not None and xargs_is_mutating_subcommand(subcommand)


def xargs_subcommand(tokens: Sequence[str]) -> list[str] | None:
    if not tokens or tokens[0] != "xargs":
        return None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            rest = list(tokens[index + 1 :])
            return rest or None
        if not token.startswith("-"):
            rest = list(tokens[index:])
            return rest or None
        takes_value = token in {"-E", "-e", "-I", "-L", "-n", "-P", "-s"}
        index += 2 if takes_value and len(token) == 2 else 1
    return None


def xargs_is_mutating_subcommand(tokens: Sequence[str]) -> bool:
    if not tokens:
        return False
    head, tail = tokens[0], tokens[1:]
    if head in {"perl", "ruby"}:
        return xargs_has_in_place_flag(tail)
    if head == "sed":
        return xargs_has_in_place_flag(tail) or "--in-place" in tail
    if head == "rg":
        return "--replace" in tail
    return False


def xargs_has_in_place_flag(tokens: Sequence[str]) -> bool:
    return any(token == "-i" or token.startswith("-i") or token == "-pi" or token.startswith("-pi") for token in tokens)


def drop_small_formatting_commands(commands: list[list[str]]) -> list[list[str]]:
    return [tokens for tokens in commands if not is_small_formatting_command(tokens)]


def summarize_main_tokens(main_cmd: Sequence[str]) -> ParsedCommand:
    if not main_cmd:
        return ParsedCommand.unknown("")
    head, tail = main_cmd[0], list(main_cmd[1:])
    cmd = shlex_join(main_cmd)

    if head in {"ls", "eza", "exa"}:
        flags = (
            ["-I", "-w", "--block-size", "--format", "--time-style", "--color", "--quoting-style"]
            if head == "ls"
            else ["-I", "--ignore-glob", "--color", "--sort", "--time-style", "--time"]
        )
        path = first_non_flag_operand(tail, flags)
        return ParsedCommand.list_files(cmd=cmd, path=short_display_path(path) if path is not None else None)
    if head == "tree":
        path = first_non_flag_operand(tail, ["-L", "-P", "-I", "--charset", "--filelimit", "--sort"])
        return ParsedCommand.list_files(cmd=cmd, path=short_display_path(path) if path is not None else None)
    if head == "du":
        path = first_non_flag_operand(tail, ["-d", "--max-depth", "-B", "--block-size", "--exclude", "--time-style"])
        return ParsedCommand.list_files(cmd=cmd, path=short_display_path(path) if path is not None else None)
    if head in {"rg", "rga", "ripgrep-all"}:
        args_no_connector = trim_at_connector(tail)
        has_files_flag = "--files" in args_no_connector
        candidates = skip_flag_values(
            args_no_connector,
            ["-g", "--glob", "--iglob", "-t", "--type", "--type-add", "--type-not", "-m", "--max-count", "-A", "-B", "-C", "--context", "--max-depth"],
        )
        non_flags = [arg for arg in candidates if not arg.startswith("-")]
        if has_files_flag:
            path = short_display_path(non_flags[0]) if non_flags else None
            return ParsedCommand.list_files(cmd=cmd, path=path)
        query = non_flags[0] if non_flags else None
        path = short_display_path(non_flags[1]) if len(non_flags) > 1 else None
        return ParsedCommand.search(cmd=cmd, query=query, path=path)
    if head == "git":
        if tail and tail[0] == "grep":
            return parse_grep_like(main_cmd, tail[1:])
        if tail and tail[0] == "ls-files":
            path = first_non_flag_operand(tail[1:], ["--exclude", "--exclude-from", "--pathspec-from-file"])
            return ParsedCommand.list_files(cmd=cmd, path=short_display_path(path) if path is not None else None)
        return ParsedCommand.unknown(cmd)
    if head == "fd":
        query, path = parse_fd_query_and_path(tail)
        if query is not None:
            return ParsedCommand.search(cmd=cmd, query=query, path=path)
        return ParsedCommand.list_files(cmd=cmd, path=path)
    if head == "find":
        query, path = parse_find_query_and_path(tail)
        if query is not None:
            return ParsedCommand.search(cmd=cmd, query=query, path=path)
        return ParsedCommand.list_files(cmd=cmd, path=path)
    if head in {"grep", "egrep", "fgrep"}:
        return parse_grep_like(main_cmd, tail)
    if head in {"ag", "ack", "pt"}:
        args_no_connector = trim_at_connector(tail)
        candidates = skip_flag_values(args_no_connector, ["-G", "-g", "--file-search-regex", "--ignore-dir", "--ignore-file", "--path-to-ignore"])
        non_flags = [arg for arg in candidates if not arg.startswith("-")]
        query = non_flags[0] if non_flags else None
        path = short_display_path(non_flags[1]) if len(non_flags) > 1 else None
        return ParsedCommand.search(cmd=cmd, query=query, path=path)
    if head == "cat":
        return _single_file_read_or_unknown(cmd, tail, [])
    if head in {"bat", "batcat"}:
        return _single_file_read_or_unknown(cmd, tail, ["--theme", "--language", "--style", "--terminal-width", "--tabs", "--line-range", "--map-syntax"])
    if head == "less":
        return _single_file_read_or_unknown(cmd, tail, ["-p", "-P", "-x", "-y", "-z", "-j", "--pattern", "--prompt", "--tabs", "--shift", "--jump-target"])
    if head == "more":
        return _single_file_read_or_unknown(cmd, tail, [])
    if head == "head":
        return _head_or_tail_read("head", main_cmd, tail)
    if head == "tail":
        return _head_or_tail_read("tail", main_cmd, tail)
    if head == "awk":
        path = awk_data_file_operand(tail)
        if path is not None:
            return ParsedCommand.read(cmd=cmd, name=short_display_path(path), path=Path(path))
        return ParsedCommand.unknown(cmd)
    if head == "nl":
        candidates = skip_flag_values(tail, ["-s", "-w", "-v", "-i", "-b"])
        path = next((arg for arg in candidates if not arg.startswith("-")), None)
        if path is not None:
            return ParsedCommand.read(cmd=cmd, name=short_display_path(path), path=Path(path))
        return ParsedCommand.unknown(cmd)
    if head == "sed":
        path = sed_read_path(tail)
        if path is not None:
            return ParsedCommand.read(cmd=cmd, name=short_display_path(path), path=Path(path))
        return ParsedCommand.unknown(cmd)
    if is_python_command(head):
        if python_walks_files(tail):
            return ParsedCommand.list_files(cmd=cmd, path=None)
        return ParsedCommand.unknown(cmd)
    return ParsedCommand.unknown(cmd)


def _single_file_read_or_unknown(cmd: str, tail: Sequence[str], flags_with_vals: Iterable[str]) -> ParsedCommand:
    path = single_non_flag_operand(tail, flags_with_vals)
    if path is None:
        return ParsedCommand.unknown(cmd)
    return ParsedCommand.read(cmd=cmd, name=short_display_path(path), path=Path(path))


def _head_or_tail_read(kind: str, main_cmd: Sequence[str], tail: Sequence[str]) -> ParsedCommand:
    cmd = shlex_join(main_cmd)
    has_valid_n = False
    if tail:
        first = tail[0]
        if first == "-n" and len(tail) >= 2:
            value = tail[1]
            if kind == "tail" and value.startswith("+"):
                value = value[1:]
            has_valid_n = bool(value) and value.isdigit()
        elif first.startswith("-n"):
            value = first[2:]
            if kind == "tail" and value.startswith("+"):
                value = value[1:]
            has_valid_n = bool(value) and value.isdigit()
    if has_valid_n:
        candidates: list[str] = []
        index = 0
        while index < len(tail):
            if index == 0 and tail[index] == "-n" and index + 1 < len(tail):
                value = tail[index + 1]
                check = value[1:] if kind == "tail" and value.startswith("+") else value
                if check and check.isdigit():
                    index += 2
                    continue
            candidates.append(tail[index])
            index += 1
        path = next((item for item in candidates if not item.startswith("-")), None)
        if path is not None:
            return ParsedCommand.read(cmd=cmd, name=short_display_path(path), path=Path(path))
    if len(tail) == 1 and not tail[0].startswith("-"):
        return ParsedCommand.read(cmd=cmd, name=short_display_path(tail[0]), path=Path(tail[0]))
    return ParsedCommand.unknown(cmd)


def _path_as_str(path: Path | str | None) -> str | None:
    return str(path) if path is not None else None


def _apply_cwd_to_read(parsed: ParsedCommand, cwd: str | None) -> ParsedCommand:
    if parsed.type == "read" and cwd is not None:
        return ParsedCommand.read(parsed.cmd, parsed.name or "", join_paths(cwd, str(parsed.path or "")))
    return parsed


def is_abs_like(path: str) -> bool:
    candidate = Path(path)
    if candidate.is_absolute():
        return True
    if len(path) >= 3 and path[1] == ":" and path[2] == "\\" and path[0].isalpha():
        return True
    return path.startswith("\\\\")


def join_paths(base: str | None, rel: str) -> str:
    if is_abs_like(rel):
        return rel
    if not base:
        return rel
    return str(Path(base) / rel)


__all__ = [
    "extract_bash_command",
    "extract_powershell_command",
    "extract_shell_command",
    "parse_command",
    "parse_command_impl",
    "parse_shell_lc_plain_commands",
    "parse_shell_lc_single_command_prefix",
    "shlex_join",
]
