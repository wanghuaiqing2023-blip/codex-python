import pytest

from pycodex.cloud_tasks import (
    ApplyCommand,
    Cli,
    Command,
    DiffCommand,
    ExecCommand,
    ListCommand,
    StatusCommand,
    parse_attempts,
    parse_limit,
)


def test_parse_attempts_matches_rust_value_parser():
    # Rust crate/module: codex-cloud-tasks/src/cli.rs::parse_attempts.
    assert parse_attempts("1") == 1
    assert parse_attempts("4") == 4
    with pytest.raises(ValueError, match="^attempts must be an integer between 1 and 4$"):
        parse_attempts("x")
    with pytest.raises(ValueError, match="^attempts must be between 1 and 4$"):
        parse_attempts("0")
    with pytest.raises(ValueError, match="^attempts must be between 1 and 4$"):
        parse_attempts("5")


def test_parse_limit_matches_rust_value_parser():
    # Rust crate/module: codex-cloud-tasks/src/cli.rs::parse_limit.
    assert parse_limit("1") == 1
    assert parse_limit("20") == 20
    with pytest.raises(ValueError, match="^limit must be an integer between 1 and 20$"):
        parse_limit("x")
    with pytest.raises(ValueError, match="^limit must be between 1 and 20$"):
        parse_limit("0")
    with pytest.raises(ValueError, match="^limit must be between 1 and 20$"):
        parse_limit("21")


def test_command_dataclasses_preserve_rust_defaults_and_validation():
    # Rust crate/module: codex-cloud-tasks/src/cli.rs command structs.
    exec_cmd = ExecCommand(query=None, environment="env-1")
    assert exec_cmd.query is None
    assert exec_cmd.environment == "env-1"
    assert exec_cmd.attempts == 1
    assert exec_cmd.branch is None

    list_cmd = ListCommand()
    assert list_cmd.environment is None
    assert list_cmd.limit == 20
    assert list_cmd.cursor is None
    assert list_cmd.json is False

    assert ApplyCommand("task", "4").attempt == 4
    assert DiffCommand("task", None).attempt is None
    with pytest.raises(ValueError, match="^attempts must be between 1 and 4$"):
        ExecCommand(query="q", environment="env", attempts=5)
    with pytest.raises(ValueError, match="^limit must be between 1 and 20$"):
        ListCommand(limit=99)


def test_cli_and_command_variant_shape_matches_rust_enum_names():
    # Rust crate/module: codex-cloud-tasks/src/cli.rs::Cli and Command enum.
    status = StatusCommand(task_id="task_1")
    assert Command.status(status).kind == "status"
    assert Command.status(status).value is status
    assert Command.exec(ExecCommand("q", "env")).kind == "exec"
    assert Command.list(ListCommand()).kind == "list"
    assert Command.apply(ApplyCommand("task")).kind == "apply"
    assert Command.diff(DiffCommand("task")).kind == "diff"

    cli = Cli(command=Command.status(status))
    assert cli.config_overrides == []
    assert cli.command == Command.status(status)
