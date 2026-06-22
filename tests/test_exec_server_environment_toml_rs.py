from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.exec_server import (
    DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT,
    DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
    ENVIRONMENTS_TOML_FILE,
    LOCAL_ENVIRONMENT_ID,
    DefaultEnvironmentProvider,
    EnvironmentDefault,
    EnvironmentToml,
    EnvironmentsToml,
    ExecServerError,
    ExecServerTransportKind,
    ExecServerTransportParams,
    StdioExecServerCommand,
    TomlEnvironmentProvider,
    environment_provider_from_codex_home,
    load_environments_toml,
)


def test_toml_provider_includes_local_and_adds_configured_environments() -> None:
    # Rust crate/module/test:
    # codex-exec-server/src/environment_toml.rs
    # toml_provider_includes_local_and_adds_configured_environments.
    provider = TomlEnvironmentProvider.new(
        EnvironmentsToml(
            default="ssh-dev",
            include_local=None,
            environments=[
                EnvironmentToml(id="devbox", url=" ws://127.0.0.1:8765 "),
                EnvironmentToml(
                    id="ssh-dev",
                    program=" ssh ",
                    args=["dev", "codex exec-server --listen stdio"],
                    env={"CODEX_LOG": "debug"},
                ),
            ],
        )
    )

    snapshot = provider.snapshot()
    environment_ids = [environment_id for environment_id, _environment in snapshot.environments]
    environments = dict(snapshot.environments)

    assert environment_ids == ["devbox", "ssh-dev"]
    assert snapshot.include_local is True
    assert LOCAL_ENVIRONMENT_ID not in environments
    assert environments["devbox"].exec_server_url() == "ws://127.0.0.1:8765"
    assert environments["ssh-dev"].is_remote() is True
    assert environments["ssh-dev"].exec_server_url() is None
    assert snapshot.default == EnvironmentDefault.environment_id_value("ssh-dev")


def test_toml_provider_default_selection_cases() -> None:
    # Rust tests: toml_provider_default_omitted_selects_local,
    # toml_provider_default_none_disables_default,
    # toml_provider_can_disable_local_environment, and
    # toml_provider_without_local_and_default_omitted_disables_default.
    assert TomlEnvironmentProvider.new(EnvironmentsToml()).snapshot().default == (
        EnvironmentDefault.environment_id_value(LOCAL_ENVIRONMENT_ID)
    )
    assert TomlEnvironmentProvider.new(EnvironmentsToml(default="none")).snapshot().default == (
        EnvironmentDefault.disabled()
    )

    no_local_with_default = TomlEnvironmentProvider.new(
        EnvironmentsToml(
            default="ssh-dev",
            include_local=False,
            environments=[EnvironmentToml(id="ssh-dev", program="ssh")],
        )
    ).snapshot()
    assert no_local_with_default.include_local is False
    assert no_local_with_default.default == EnvironmentDefault.environment_id_value("ssh-dev")

    no_local_no_default = TomlEnvironmentProvider.new(EnvironmentsToml(include_local=False)).snapshot()
    assert no_local_no_default.include_local is False
    assert no_local_no_default.default == EnvironmentDefault.disabled()


def test_toml_provider_rejects_invalid_environments() -> None:
    # Rust test: toml_provider_rejects_invalid_environments.
    cases = [
        (EnvironmentToml(id="local", url="ws://127.0.0.1:8765"), "environment id `local` is reserved"),
        (
            EnvironmentToml(id=" devbox ", url="ws://127.0.0.1:8765"),
            "environment id ` devbox ` must not contain surrounding whitespace",
        ),
        (
            EnvironmentToml(id="dev box", url="ws://127.0.0.1:8765"),
            "environment id `dev box` must contain only ASCII letters, numbers, '-' or '_'",
        ),
        (
            EnvironmentToml(id="devbox", url="http://127.0.0.1:8765"),
            "environment url `http://127.0.0.1:8765` must use ws:// or wss://",
        ),
        (
            EnvironmentToml(id="devbox", url="ws://127.0.0.1:8765", program="codex"),
            "environment `devbox` must set exactly one of url or program",
        ),
        (EnvironmentToml(id="devbox", program=" "), "environment `devbox` program cannot be empty"),
        (
            EnvironmentToml(id="devbox", args=[]),
            "environment `devbox` args, env, and cwd require program",
        ),
        (
            EnvironmentToml(id="ssh-dev", program="ssh", connect_timeout_sec=1),
            "environment `ssh-dev` connect_timeout_sec requires url",
        ),
    ]

    for item, expected in cases:
        with pytest.raises(ExecServerError) as exc_info:
            TomlEnvironmentProvider.new(EnvironmentsToml(environments=[item]))
        assert str(exc_info.value) == f"exec-server protocol error: {expected}"


def test_toml_provider_resolves_relative_stdio_cwd_from_config_dir(tmp_path: Path) -> None:
    # Rust test: toml_provider_resolves_relative_stdio_cwd_from_config_dir.
    provider = TomlEnvironmentProvider.new_with_config_dir(
        EnvironmentsToml(environments=[EnvironmentToml(id="ssh-dev", program="ssh", cwd=Path("workspace"))]),
        tmp_path,
    )

    assert provider.environments[0][1] == ExecServerTransportParams.stdio_command(
        StdioExecServerCommand(program="ssh", args=[], env={}, cwd=tmp_path / "workspace"),
        initialize_timeout=DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
    )


def test_toml_provider_parses_configured_transport_timeouts() -> None:
    # Rust test: toml_provider_parses_configured_transport_timeouts.
    provider = TomlEnvironmentProvider.new(
        EnvironmentsToml(
            environments=[
                EnvironmentToml(
                    id="devbox",
                    url="ws://127.0.0.1:8765",
                    connect_timeout_sec=12,
                    initialize_timeout_sec=34,
                ),
                EnvironmentToml(id="ssh-dev", program="ssh", initialize_timeout_sec=56),
            ]
        )
    )

    assert provider.environments[0][1] == ExecServerTransportParams.from_websocket_url(
        "ws://127.0.0.1:8765",
        connect_timeout=12,
        initialize_timeout=34,
    )
    assert provider.environments[1][1] == ExecServerTransportParams.stdio_command(
        StdioExecServerCommand(program="ssh", args=[], env={}, cwd=None),
        initialize_timeout=56,
    )


def test_toml_provider_rejects_relative_stdio_cwd_without_config_dir() -> None:
    # Rust test: toml_provider_rejects_relative_stdio_cwd_without_config_dir.
    with pytest.raises(ExecServerError) as exc_info:
        TomlEnvironmentProvider.new(
            EnvironmentsToml(environments=[EnvironmentToml(id="ssh-dev", program="ssh", cwd=Path("workspace"))])
        )
    assert str(exc_info.value) == "exec-server protocol error: environment `ssh-dev` cwd must be absolute"


def test_toml_provider_rejects_duplicate_overlong_and_unknown_default() -> None:
    # Rust tests: duplicate ids, overlong id, and unknown default.
    with pytest.raises(ExecServerError, match="environment id `devbox` is duplicated"):
        TomlEnvironmentProvider.new(
            EnvironmentsToml(
                environments=[
                    EnvironmentToml(id="devbox", url="ws://127.0.0.1:8765"),
                    EnvironmentToml(id="devbox", program="codex"),
                ]
            )
        )

    overlong_id = "a" * 65
    with pytest.raises(ExecServerError, match=f"environment id `{overlong_id}` cannot be longer"):
        TomlEnvironmentProvider.new(EnvironmentsToml(environments=[EnvironmentToml(id=overlong_id, program="ssh")]))

    with pytest.raises(ExecServerError, match="default environment `missing` is not configured"):
        TomlEnvironmentProvider.new(EnvironmentsToml(default="missing"))


def test_load_environments_toml_reads_root_environment_list(tmp_path: Path) -> None:
    # Rust test: load_environments_toml_reads_root_environment_list.
    path = tmp_path / ENVIRONMENTS_TOML_FILE
    cwd = tmp_path.as_posix()
    path.write_text(
        f'''
default = "ssh-dev"
include_local = false

[[environments]]
id = "devbox"
url = "ws://127.0.0.1:4512"
connect_timeout_sec = 12.0
initialize_timeout_sec = 34.0

[[environments]]
id = "ssh-dev"
program = "ssh"
args = ["dev", "codex exec-server --listen stdio"]
cwd = "{cwd}"
[environments.env]
CODEX_LOG = "debug"
''',
        encoding="utf-8",
    )

    environments = load_environments_toml(path)

    assert environments.default == "ssh-dev"
    assert environments.include_local is False
    assert environments.environments[0] == EnvironmentToml(
        id="devbox",
        url="ws://127.0.0.1:4512",
        connect_timeout_sec=12.0,
        initialize_timeout_sec=34.0,
    )
    assert environments.environments[1] == EnvironmentToml(
        id="ssh-dev",
        program="ssh",
        args=["dev", "codex exec-server --listen stdio"],
        env={"CODEX_LOG": "debug"},
        cwd=Path(cwd),
    )


def test_load_environments_toml_rejects_unknown_fields(tmp_path: Path) -> None:
    # Rust test: load_environments_toml_rejects_unknown_fields.
    cases = [
        ("unknown = true\n", "unknown field `unknown`"),
        ('[[environments]]\nid = "devbox"\nurl = "ws://127.0.0.1:4512"\nunknown = true\n', "unknown field `unknown`"),
    ]
    for index, (contents, expected) in enumerate(cases):
        path = tmp_path / f"environments-{index}.toml"
        path.write_text(contents, encoding="utf-8")
        with pytest.raises(ExecServerError) as exc_info:
            load_environments_toml(path)
        assert expected in str(exc_info.value)


def test_toml_provider_rejects_malformed_websocket_url() -> None:
    # Rust test: toml_provider_rejects_malformed_websocket_url.
    with pytest.raises(ExecServerError) as exc_info:
        TomlEnvironmentProvider.new(EnvironmentsToml(environments=[EnvironmentToml(id="devbox", url="ws://")]))
    assert "environment url `ws://` is invalid" in str(exc_info.value)


def test_environment_provider_from_codex_home_uses_file_or_default(tmp_path: Path, monkeypatch) -> None:
    # Rust tests: environment_provider_from_codex_home_uses_present_environments_file
    # and environment_provider_from_codex_home_falls_back_when_file_is_missing.
    (tmp_path / ENVIRONMENTS_TOML_FILE).write_text(
        'default = "none"\ninclude_local = false\n',
        encoding="utf-8",
    )
    snapshot = environment_provider_from_codex_home(tmp_path).snapshot()
    assert snapshot.include_local is False
    assert snapshot.environments == []
    assert snapshot.default == EnvironmentDefault.disabled()

    fallback_home = tmp_path / "fallback"
    fallback_home.mkdir()
    monkeypatch.delenv("CODEX_EXEC_SERVER_URL", raising=False)
    fallback_snapshot = environment_provider_from_codex_home(fallback_home).snapshot()
    assert fallback_snapshot.include_local is True
    assert fallback_snapshot.environments == []
    assert fallback_snapshot.default == EnvironmentDefault.environment_id_value(LOCAL_ENVIRONMENT_ID)


def test_toml_provider_default_timeout_values() -> None:
    # Rust module contract: omitted transport timeouts use client_api defaults.
    provider = TomlEnvironmentProvider.new(
        EnvironmentsToml(environments=[EnvironmentToml(id="devbox", url="ws://127.0.0.1:8765")])
    )

    transport = provider.environments[0][1]
    assert transport.kind is ExecServerTransportKind.WEBSOCKET_URL
    assert transport.connect_timeout == DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT
    assert transport.initialize_timeout == DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT
