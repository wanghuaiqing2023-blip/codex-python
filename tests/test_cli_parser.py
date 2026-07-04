import unittest
import io
import os
import json
import re
import shlex
import subprocess
import sys
import tempfile
import socket
import threading
import time
from dataclasses import replace
from email.message import Message
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from pathlib import Path

from pycodex.cli.features import (
    FeatureCliError,
    FeatureToggles,
    FeaturesSubcommand,
    format_features_list,
    parse_features_args,
    run_features_command,
    under_development_feature_warning,
)
from pycodex.cli.parser import (
    CliParseError,
    _collect_cloud_attempt_diffs,
    _parse_mcp_env_pair,
    _print_local_app_server_connect_hint,
    _build_tui_core_active_thread_runtime,
    _read_responses_api_auth_header,
    _resolve_exec_remote_endpoint,
    _remote_control_human_lines,
    _remote_control_start_human_message,
    _run_cloud_command,
    _run_stdio_to_uds,
    _select_cloud_attempt_diff,
    _validate_mcp_server_name,
    default_reachability_plan,
    main,
    parse_args,
    reject_remote_mode_for_subcommand,
)
from pycodex.cli import DoctorUpdateCheck, NpmRootCheck, UpdateAction
from pycodex.cli.login import AuthDotJson
from pycodex.exec.config_plan import build_exec_config_bootstrap_plan
from pycodex.core import Feature, Features, PersonalityMigrationStatus
from pycodex.rollout import (
    SessionMeta,
    materialize_session_rollout,
    read_event_msgs_from_rollout,
    read_response_items_from_rollout,
)
from pycodex.exec import app_server_control_socket_path
from pycodex.core.session.turn.runtime import UserTurnSamplingResult
from pycodex.protocol import AltScreenMode, AskForApproval, ContentItem, ProfileV2Name, ResponseItem, SandboxMode
from pycodex.tui.app.runtime import ExecFunctionActiveThreadRuntime, TuiAppRuntime


class TopLevelCliParserTests(unittest.TestCase):
    def setUp(self):
        self._previous_openai_api_key = os.environ.get("OPENAI_API_KEY")
        if self._testMethodName.startswith("test_main_doctor_") and "OPENAI_API_KEY" not in os.environ:
            os.environ["OPENAI_API_KEY"] = "sk-doctor-smoke"
        self._provider_reachability_patch = None
        if self._testMethodName.startswith("test_main_doctor_"):
            self._provider_reachability_patch = patch(
                "pycodex.cli.parser.doctor_provider_reachability_check",
                return_value=DoctorUpdateCheck(
                    status="warn",
                    summary="provider reachability checks are skipped in tests",
                    details=(f"reachability mode: {default_reachability_plan().description}",),
                ),
            ).start()

    def tearDown(self):
        if self._testMethodName.startswith("test_main_doctor_"):
            if self._previous_openai_api_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = self._previous_openai_api_key
            if self._provider_reachability_patch is not None:
                self._provider_reachability_patch.stop()

    def _main_with_local_http_exec_disabled(self, argv, **kwargs):
        with patch.dict(
            os.environ,
            {
                "PYCODEX_EXEC_LOCAL_HTTP": "0",
                "PYCODEX_EXEC_CORE": "0",
            },
        ):
            return main(argv, **kwargs)

    def test_no_args_defaults_to_interactive_mode(self):
        parsed = parse_args([])

        self.assertTrue(parsed.is_interactive)
        self.assertIsNone(parsed.command)
        self.assertIsNone(parsed.prompt)

    def test_single_positional_without_subcommand_is_prompt(self):
        parsed = parse_args(["fix the failing tests"])

        self.assertTrue(parsed.is_interactive)
        self.assertEqual(parsed.prompt, "fix the failing tests")

    def test_exec_command_and_visible_alias_map_to_canonical_name(self):
        parsed = parse_args(["exec", "hello"])
        alias = parse_args(["e", "hello"])

        self.assertEqual(parsed.command, "exec")
        self.assertEqual(alias.command, "exec")
        self.assertEqual(parsed.command_args, ("hello",))
        self.assertEqual(alias.command_args, ("hello",))
        self.assertEqual(parsed.exec_cli().prompt, "hello")

    def test_apply_alias_maps_to_canonical_name(self):
        parsed = parse_args(["a", "task-1"])

        self.assertEqual(parsed.command, "apply")
        self.assertEqual(parsed.command_args, ("task-1",))

    def test_hyphenated_commands_match_upstream_clap_names(self):
        for name in ("mcp-server", "app-server", "remote-control", "exec-server"):
            with self.subTest(name=name):
                self.assertEqual(parse_args([name]).command, name)

    def test_mcp_requires_subcommand(self):
        with self.assertRaisesRegex(CliParseError, "mcp requires a subcommand"):
            parse_args(["mcp"])

    def test_plugin_requires_subcommand(self):
        with self.assertRaisesRegex(CliParseError, "plugin requires a subcommand"):
            parse_args(["plugin"])

    def test_parse_mcp_list_json(self):
        parsed = parse_args(["mcp", "list", "--json"])

        self.assertEqual(parsed.command_args, ("list", "--json"))

    def test_parse_mcp_get_allows_json(self):
        self.assertEqual(
            parse_args(["mcp", "get", "acme", "--json"]).command_args,
            ("get", "acme", "--json"),
        )
        self.assertEqual(
            parse_args(["mcp", "get", "--json", "acme"]).command_args,
            ("get", "--json", "acme"),
        )

    def test_parse_mcp_add_supports_env_in_command_mode(self):
        parsed = parse_args(
            ["mcp", "add", "acme", "--env", "TOKEN=abc", "--", "npm", "start"]
        )

        self.assertEqual(parsed.command_args, ("add", "acme", "--env", "TOKEN=abc", "--", "npm", "start"))

    def test_mcp_add_rejects_scopes(self):
        with self.assertRaisesRegex(CliParseError, "Unknown argument for mcp add: --scopes"):
            parse_args(["mcp", "add", "acme", "--scopes", "foo", "--", "npm", "start"])

    def test_parse_mcp_add_url_and_command_modes(self):
        parsed_url = parse_args(["mcp", "add", "acme", "--url", "https://example.com/mcp"])
        parsed_command = parse_args(["mcp", "add", "acme", "--", "npm", "start"])

        self.assertEqual(parsed_url.command_args, ("add", "acme", "--url", "https://example.com/mcp"))
        self.assertEqual(parsed_command.command_args, ("add", "acme", "--", "npm", "start"))

    def test_mcp_add_requires_url_or_command(self):
        with self.assertRaisesRegex(CliParseError, "mcp add requires --url or command."):
            parse_args(["mcp", "add", "acme"])

    def test_mcp_env_pair_matches_rust(self):
        # Rust parity: codex-cli/src/mcp_cmd.rs parse_env_pair.
        self.assertEqual(_parse_mcp_env_pair(" TOKEN =abc"), ("TOKEN", "abc"))
        self.assertEqual(_parse_mcp_env_pair("TOKEN="), ("TOKEN", ""))
        with self.assertRaisesRegex(RuntimeError, "environment entries must be in KEY=VALUE form"):
            _parse_mcp_env_pair("TOKEN")
        with self.assertRaisesRegex(RuntimeError, "environment entries must be in KEY=VALUE form"):
            _parse_mcp_env_pair(" =abc")

    def test_mcp_server_name_validation_matches_rust(self):
        # Rust parity: codex-cli/src/mcp_cmd.rs validate_server_name.
        for name in ("acme", "acme_1", "acme-1", "A1"):
            _validate_mcp_server_name(name)
        for name in ("", "bad.name", "bad/name", "bad name", "é"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(RuntimeError, "invalid server name"):
                    _validate_mcp_server_name(name)

    def test_parse_plugin_marketplace_add_supports_sparse_and_ref(self):
        parsed = parse_args(
            ["plugin", "marketplace", "add", "acme", "--sparse", "pkg1", "pkg2", "--ref", "main"]
        )
        self.assertEqual(
            parsed.command_args,
            (
                "marketplace",
                "add",
                "acme",
                "--sparse",
                "pkg1",
                "pkg2",
                "--ref",
                "main",
            ),
        )

    def test_parse_plugin_marketplace_upgrade_rejects_extra_arguments(self):
        with self.assertRaisesRegex(
            CliParseError,
            "plugin marketplace upgrade accepts at most one marketplace name.",
        ):
            parse_args(["plugin", "marketplace", "upgrade", "primary", "secondary"])

    def test_parse_plugin_marketplace_remove_matches_rust(self):
        # Rust parity: codex-cli/src/marketplace_cmd.rs remove_subcommand_parses_marketplace_name.
        self.assertEqual(
            parse_args(["plugin", "marketplace", "remove", "debug"]).command_args,
            ("marketplace", "remove", "debug"),
        )

    def test_parse_plugin_add_accepts_marketplace_short_flag_and_explicit_marketplace_match(self):
        self.assertEqual(
            parse_args(["plugin", "add", "acme@debug", "-m", "debug"]).command_args,
            ("add", "acme@debug", "-m", "debug"),
        )
        self.assertEqual(
            parse_args(["plugin", "remove", "acme@debug", "--marketplace", "debug"]).command_args,
            ("remove", "acme@debug", "--marketplace", "debug"),
        )
        self.assertEqual(
            parse_args(["plugin", "list", "-m", "debug"]).command_args,
            ("list", "-m", "debug"),
        )

    def test_plugin_selector_requires_marketplace_like_rust(self):
        # Rust parity: codex-cli/src/plugin_cmd.rs parse_plugin_selection.
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["plugin", "remove", "sample"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn("plugin requires --marketplace unless passed as <plugin>@<marketplace>", stderr.getvalue())

    def test_plugin_selector_rejects_marketplace_mismatch_like_rust(self):
        # Rust parity: codex-cli/src/plugin_cmd.rs parse_plugin_selection.
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["plugin", "remove", "sample@debug", "--marketplace", "primary"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn(
            "plugin id `sample@debug` belongs to marketplace `debug`, but --marketplace specified `primary`",
            stderr.getvalue(),
        )

    def test_parse_remote_control_allows_json_with_start(self):
        self.assertEqual(
            parse_args(["remote-control", "--json", "start"]).command_args,
            ("--json", "start"),
        )

    def test_parse_remote_control_allows_json(self):
        self.assertEqual(
            parse_args(["remote-control", "--json"]).command_args,
            ("--json",),
        )

    def test_parse_mcp_server_rejects_positional_arguments(self):
        with self.assertRaisesRegex(
            CliParseError,
            "Unexpected argument for mcp-server: plugin",
        ):
            parse_args(["mcp-server", "plugin"])

    def test_parse_mcp_server_allows_strict_config(self):
        self.assertEqual(
            parse_args(["mcp-server", "--strict-config"]).command_args,
            ("--strict-config",),
        )

    def test_parse_mcp_server_rejects_unknown_flag(self):
        with self.assertRaisesRegex(
            CliParseError,
            "Unknown argument for mcp-server: --unknown",
        ):
            parse_args(["mcp-server", "--unknown"])

    def test_parse_remote_control_rejects_unknown_and_rejects_too_many_subcommands(self):
        with self.assertRaisesRegex(CliParseError, "Unknown argument for remote-control"):
            parse_args(["remote-control", "oops"])
        with self.assertRaisesRegex(CliParseError, "Too many arguments for `remote-control`."):
            parse_args(["remote-control", "start", "stop"])

    def test_parse_remote_control_accepts_json_with_stop(self):
        self.assertEqual(
            parse_args(["remote-control", "stop", "--json"]).command_args,
            ("stop", "--json"),
        )

    def test_remote_control_human_start_messages_match_rust(self):
        # Rust parity: codex-cli/src/remote_control_cmd.rs remote_control_human_start_messages_use_server_name.
        self.assertEqual(
            _remote_control_start_human_message("connected", "owen-mbp"),
            "This machine is available for remote control as owen-mbp.",
        )
        self.assertEqual(
            _remote_control_start_human_message("connecting", "owen-mbp"),
            "Remote control is enabled on owen-mbp and still connecting.",
        )
        self.assertEqual(
            _remote_control_start_human_message("errored", "owen-mbp"),
            "Remote control is enabled on owen-mbp but the connection is errored.",
        )
        self.assertEqual(
            _remote_control_start_human_message("disabled", "owen-mbp"),
            "Remote control is disabled on owen-mbp.",
        )

    def test_remote_control_human_lines_match_rust_foreground_hint(self):
        # Rust parity: codex-cli/src/remote_control_cmd.rs remote_control_human_lines_include_foreground_stop_hint_only.
        summary = {"status": "connected", "server_name": "owen-mbp"}

        self.assertEqual(
            _remote_control_human_lines(summary, "foreground"),
            [
                "This machine is available for remote control as owen-mbp.",
                "Press Ctrl-C to stop.",
            ],
        )
        self.assertEqual(
            _remote_control_human_lines(summary, "daemon"),
            ["This machine is available for remote control as owen-mbp."],
        )

    def test_parse_debug_models_allows_bundled_flag(self):
        self.assertEqual(
            parse_args(["debug", "models", "--bundled"]).command_args,
            ("models", "--bundled"),
        )

    def test_parse_debug_models_rejects_unknown_flag(self):
        with self.assertRaisesRegex(CliParseError, "Unknown argument for debug models"):
            parse_args(["debug", "models", "--helpful"])

    def test_parse_debug_app_server_send_message_requires_message(self):
        with self.assertRaisesRegex(CliParseError, "send-message-v2 requires USER_MESSAGE"):
            parse_args(["debug", "app-server"])
        with self.assertRaisesRegex(CliParseError, "send-message-v2 requires USER_MESSAGE"):
            parse_args(["debug", "app-server", "send-message-v2"])

    def test_parse_debug_app_server_send_message_accepts_payload(self):
        self.assertEqual(
            parse_args(["debug", "app-server", "send-message-v2", "hello"]).command_args,
            ("app-server", "send-message-v2", "hello"),
        )

    def test_parse_debug_prompt_input_supports_images(self):
        self.assertEqual(
            parse_args(
                ["debug", "prompt-input", "Summarize", "--image", "a.png", "-i", "b.png"]
            ).command_args,
            ("prompt-input", "Summarize", "--image", "a.png", "-i", "b.png"),
        )

    def test_parse_review_command_accepts_review_options(self):
        self.assertEqual(
            parse_args(["review", "--commit", "123456789", "--title", "Fix"]).command_args,
            ("--commit", "123456789", "--title", "Fix"),
        )

    def test_parse_review_command_accepts_help(self):
        self.assertEqual(parse_args(["review", "--help"]).command_args, ("--help",))

    def test_parse_completion_command_accepts_shell_option(self):
        self.assertEqual(
            parse_args(["completion", "--shell", "zsh"]).command_args,
            ("--shell", "zsh"),
        )

    def test_parse_completion_command_accepts_short_shell_option(self):
        self.assertEqual(
            parse_args(["completion", "-s", "fish"]).command_args,
            ("-s", "fish"),
        )

    def test_parse_completion_command_accepts_shell_option_with_equals(self):
        self.assertEqual(
            parse_args(["completion", "--shell=zsh"]).command_args,
            ("--shell=zsh",),
        )

    def test_parse_completion_command_requires_shell_value(self):
        with self.assertRaisesRegex(CliParseError, "Missing value for option --shell"):
            parse_args(["completion", "--shell"])
        with self.assertRaisesRegex(CliParseError, "Missing value for option --shell"):
            parse_args(["completion", "--shell="])

    def test_parse_completion_command_rejects_unknown_flag(self):
        with self.assertRaisesRegex(CliParseError, "Unknown argument for completion: --unknown"):
            parse_args(["completion", "--unknown"])

    def test_parse_stdio_to_uds_requires_socket_path(self):
        with self.assertRaisesRegex(CliParseError, "Expected exactly one argument: <socket-path>"):
            parse_args(["stdio-to-uds"])
        with self.assertRaisesRegex(CliParseError, "Expected exactly one argument: <socket-path>"):
            parse_args(["stdio-to-uds", "sock1", "sock2"])
        self.assertEqual(
            parse_args(["stdio-to-uds", "/tmp/codex.sock"]).command_args,
            ("/tmp/codex.sock",),
        )

    def test_parse_app_server_root_options(self):
        self.assertEqual(
            parse_args(
                [
                    "app-server",
                    "--listen",
                    "stdio://",
                    "--remote-control",
                    "--analytics-default-enabled",
                ]
            ).command_args,
            ("--listen", "stdio://", "--remote-control", "--analytics-default-enabled"),
        )

    def test_parse_app_server_root_rejects_unsupported_listen_url(self):
        with self.assertRaisesRegex(
            CliParseError, r"unsupported --listen URL `http://foo`; expected `stdio://`, `unix://`, `unix://PATH`, `ws://IP:PORT`, or `off`"
        ):
            parse_args(["app-server", "--listen", "http://foo"])

    def test_parse_app_server_root_rejects_ws_non_ip_listen_url(self):
        with self.assertRaisesRegex(
            CliParseError, r"invalid websocket --listen URL `ws://localhost:4500`; expected `ws://IP:PORT`"
        ):
            parse_args(["app-server", "--listen", "ws://localhost:4500"])

    def test_parse_app_server_root_requires_values_for_value_options(self):
        with self.assertRaisesRegex(CliParseError, "Missing value for --listen."):
            parse_args(["app-server", "--listen"])

    def test_parse_app_server_daemon(self):
        self.assertEqual(
            parse_args(["app-server", "daemon", "start"]).command_args,
            ("daemon", "start"),
        )
        self.assertEqual(
            parse_args(["app-server", "daemon", "bootstrap", "--remote-control"]).command_args,
            ("daemon", "bootstrap", "--remote-control"),
        )

    def test_parse_app_server_daemon_allows_all_subcommands(self):
        daemon_commands = (
            "start",
            "stop",
            "restart",
            "enable-remote-control",
            "disable-remote-control",
            "version",
            "pid-update-loop",
        )
        for daemon_command in daemon_commands:
            with self.subTest(daemon_command=daemon_command):
                self.assertEqual(
                    parse_args(["app-server", "daemon", daemon_command]).command_args,
                    ("daemon", daemon_command),
                )

    def test_parse_app_server_daemon_requires_subcommand(self):
        with self.assertRaisesRegex(CliParseError, "app-server daemon requires a subcommand."):
            parse_args(["app-server", "daemon"])

    def test_parse_app_server_daemon_rejects_too_many_positional_args(self):
        for daemon_command in (
            "start",
            "stop",
            "restart",
            "enable-remote-control",
            "disable-remote-control",
            "version",
            "pid-update-loop",
        ):
            with self.subTest(daemon_command=daemon_command):
                with self.assertRaisesRegex(
                    CliParseError, f"Too many arguments for `app-server daemon {daemon_command}`."
                ):
                    parse_args(["app-server", "daemon", daemon_command, "extra"])

    def test_parse_app_server_daemon_rejects_unknown_subcommand(self):
        with self.assertRaisesRegex(CliParseError, "Unknown app-server daemon subcommand"):
            parse_args(["app-server", "daemon", "unknown"])

    def test_parse_app_server_proxy_accepts_optional_socket(self):
        self.assertEqual(
            parse_args(["app-server", "proxy"]).command_args,
            ("proxy",),
        )
        self.assertEqual(
            parse_args(["app-server", "proxy", "--sock", "/tmp/codex.sock"]).command_args,
            ("proxy", "--sock", "/tmp/codex.sock"),
        )

    def test_parse_app_server_proxy_requires_socket_value_if_present(self):
        with self.assertRaisesRegex(CliParseError, "Missing value for --sock."):
            parse_args(["app-server", "proxy", "--sock"])

    def test_parse_app_server_generate_ts_requires_out(self):
        with self.assertRaisesRegex(CliParseError, "requires --out"):
            parse_args(["app-server", "generate-ts"])

    def test_parse_app_server_generate_ts_parse_known_flags(self):
        self.assertEqual(
            parse_args(
                [
                    "app-server",
                    "generate-ts",
                    "-o",
                    "build",
                    "--prettier",
                    "node_modules/.bin/prettier",
                    "--experimental",
                ]
            ).command_args,
            (
                "generate-ts",
                "-o",
                "build",
                "--prettier",
                "node_modules/.bin/prettier",
                "--experimental",
            ),
        )

    def test_parse_app_server_rejects_websocket_auth_flags_without_mode(self):
        with self.assertRaisesRegex(
            CliParseError, "websocket auth flags require `--ws-auth`"
        ):
            parse_args(["app-server", "--ws-token-file", "/tmp/token"])

    def test_parse_app_server_rejects_capability_token_missing_secret_source(self):
        with self.assertRaisesRegex(
            CliParseError, "is required when `--ws-auth capability-token` is set"
        ):
            parse_args(["app-server", "--ws-auth", "capability-token"])

    def test_parse_app_server_rejects_signed_bearer_token_without_shared_secret(self):
        with self.assertRaisesRegex(
            CliParseError, "is required when `--ws-auth signed-bearer-token` is set"
        ):
            parse_args(["app-server", "--ws-auth", "signed-bearer-token"])

    def test_parse_app_server_rejects_capability_mode_with_bearer_only_flags(self):
        with self.assertRaisesRegex(
            CliParseError,
            "`--ws-shared-secret-file`, `--ws-issuer`, `--ws-audience`, and "
            "`--ws-max-clock-skew-seconds` require `--ws-auth signed-bearer-token`",
        ):
            parse_args(["app-server", "--ws-auth", "capability-token", "--ws-issuer", "x"])

    def test_parse_app_server_rejects_signed_bearer_mode_with_capability_flags(self):
        with self.assertRaisesRegex(
            CliParseError,
            "`--ws-token-file` and `--ws-token-sha256` require "
            "`--ws-auth capability-token`, not `signed-bearer-token`",
        ):
            parse_args(["app-server", "--ws-auth", "signed-bearer-token", "--ws-token-file", "/tmp/token"])

    def test_parse_app_server_rejects_both_capability_token_sources(self):
        with self.assertRaisesRegex(
            CliParseError, "`--ws-token-file` and `--ws-token-sha256` are mutually exclusive"
        ):
            parse_args(
                ["app-server", "--ws-auth", "capability-token", "--ws-token-file", "/tmp/token", "--ws-token-sha256", "abc"],
            )
    def test_parse_app_server_rejects_unsupported_ws_auth_value(self):
        with self.assertRaisesRegex(CliParseError, "Invalid value for --ws-auth"):
            parse_args(["app-server", "--ws-auth", "invalid"])

    def test_parse_responses_api_proxy_allows_options(self):
        self.assertEqual(
            parse_args(
                [
                    "responses-api-proxy",
                    "--port",
                    "9001",
                    "--upstream-url",
                    "https://api.openai.com/v1/responses",
                    "--http-shutdown",
                    "--server-info",
                    "/tmp/server-info.json",
                    "--dump-dir",
                    "/tmp/dumps",
                ]
            ).command_args,
            (
                "--port",
                "9001",
                "--upstream-url",
                "https://api.openai.com/v1/responses",
                "--http-shutdown",
                "--server-info",
                "/tmp/server-info.json",
                "--dump-dir",
                "/tmp/dumps",
            ),
        )

    def test_parse_responses_api_proxy_rejects_unknown_arg(self):
        with self.assertRaisesRegex(
            CliParseError, "Unknown argument for responses-api-proxy: --unsupported"
        ):
            parse_args(["responses-api-proxy", "--unsupported"])

    def test_parse_responses_api_proxy_rejects_bad_port(self):
        with self.assertRaisesRegex(CliParseError, "Invalid value for --port"):
            parse_args(["responses-api-proxy", "--port", "not-an-int"])

    def test_main_responses_api_proxy_help(self):
        stdout = io.StringIO()
        code = main(["responses-api-proxy", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertEqual(
            stdout.getvalue().strip(),
            "Usage: codex responses-api-proxy [OPTIONS]",
        )

    def test_main_stdio_to_uds_help(self):
        stdout = io.StringIO()
        code = main(["stdio-to-uds", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertEqual(
            stdout.getvalue().strip(),
            "Usage: codex stdio-to-uds [OPTIONS]",
        )

    def test_read_responses_api_auth_header_requires_ascii_token(self):
        stderr = io.StringIO()
        with self.assertRaisesRegex(RuntimeError, "API key may only contain ASCII"):
            _read_responses_api_auth_header("bad key", stderr=stderr)

        self.assertEqual(
            _read_responses_api_auth_header("valid_key-123", stderr=stderr),
            "Bearer valid_key-123",
        )

    def test_read_responses_api_auth_header_rejects_too_long_key(self):
        stderr = io.StringIO()
        too_long = "a" * 1018

        with self.assertRaisesRegex(
            RuntimeError, "API key is too large to fit in the 1024-byte buffer"
        ):
            _read_responses_api_auth_header(too_long, stderr=stderr)

    def test_main_responses_api_proxy_forwards_success_and_dumps_pair(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            upstream_requests: list[tuple[dict[str, str], bytes]] = []
            downstream = []

            class _UpstreamHandler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:
                    headers = {
                        key.lower(): value for key, value in self.headers.items()
                    }
                    length = int(self.headers.get("Content-Length", "0") or 0)
                    body = self.rfile.read(length) if length else b""
                    upstream_requests.append((headers, body))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("X-Upstream", "yes")
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok","model":"tests"}')

                def log_message(self, fmt: str, *args: object) -> None:
                    del fmt
                    del args

            upstream_server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _UpstreamHandler,
            )

            upstream_thread = threading.Thread(
                target=upstream_server.serve_forever,
                kwargs={"poll_interval": 0.05},
                daemon=True,
            )
            upstream_thread.start()

            try:
                server_info_path = Path(tmpdir) / "server-info.json"
                dump_dir = Path(tmpdir) / "dumps"
                proxy_args = [
                    "responses-api-proxy",
                    "--upstream-url",
                    f"http://127.0.0.1:{upstream_server.server_port}/v1/responses",
                    "--http-shutdown",
                    "--server-info",
                    str(server_info_path),
                    "--dump-dir",
                    str(dump_dir),
                ]
                results: list[int] = []
                stderr = io.StringIO()
                proxy_thread = threading.Thread(
                    target=lambda: results.append(
                        main(proxy_args, stdin="sk-test-key-1", stderr=stderr)
                    ),
                    daemon=True,
                )
                proxy_thread.start()

                proxy_info = None
                for _ in range(200):
                    if server_info_path.exists():
                        text = server_info_path.read_text(encoding="utf-8").strip()
                        if text:
                            proxy_info = json.loads(text)
                            break
                    time.sleep(0.05)
                self.assertIsNotNone(proxy_info)

                proxy_port = proxy_info["port"]
                request = Request(
                    f"http://127.0.0.1:{proxy_port}/v1/responses",
                    method="POST",
                    data=b'{"model":"gpt-5"}',
                    headers={"Content-Type": "application/json"},
                )
                with urlopen(request) as response:
                    self.assertEqual(response.status, 200)
                    body = response.read()
                    self.assertEqual(body, b'{"status":"ok","model":"tests"}')
                    downstream.append(response.getheader("X-Upstream"))

                self.assertEqual(downstream, ["yes"])
                self.assertEqual(len(upstream_requests), 1)
                request_headers, request_body = upstream_requests[0]
                self.assertIn("content-type", request_headers)
                self.assertEqual(request_headers["content-type"], "application/json")
                self.assertEqual(request_body, b'{"model":"gpt-5"}')
                with urlopen(f"http://127.0.0.1:{proxy_port}/shutdown") as shutdown:
                    self.assertEqual(shutdown.status, 200)

                for _ in range(100):
                    proxy_thread.join(timeout=0.1)
                    if not proxy_thread.is_alive():
                        break
                self.assertFalse(proxy_thread.is_alive())
                self.assertEqual(len(results), 1)
                self.assertIn(results[0], (0,))
                self.assertEqual(len(list(dump_dir.glob("*-request.json"))), 1)
                self.assertEqual(len(list(dump_dir.glob("*-response.json"))), 1)
                dump_request = list(dump_dir.glob("*-request.json"))[0].read_text(encoding="utf-8")
                dump_response = list(dump_dir.glob("*-response.json"))[0].read_text(encoding="utf-8")
                parsed_request = json.loads(dump_request)
                parsed_response = json.loads(dump_response)
                self.assertEqual(parsed_request["method"], "POST")
                self.assertEqual(parsed_request["url"], "/v1/responses")
                self.assertEqual(parsed_request["body"], {"model": "gpt-5"})
                self.assertEqual(parsed_response["status"], 200)
                # Rust codex-responses-api-proxy/src/lib.rs only skips headers
                # managed by tiny_http, so upstream Server/Date headers may
                # remain before Content-Type in the dump.
                self.assertIn(
                    {"name": "Content-Type", "value": "application/json"},
                    parsed_response["headers"],
                )
                self.assertEqual(parsed_response["body"], {"status": "ok", "model": "tests"})
            finally:
                upstream_server.shutdown()
                upstream_thread.join()
                if "proxy_thread" in locals() and proxy_thread.is_alive():
                    proxy_thread.join(timeout=1)

    def test_main_responses_api_proxy_forwards_http_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            class _UpstreamHandler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:
                    self.send_response(418)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("X-Upstream-Error", "true")
                    self.end_headers()
                    self.wfile.write(b"upstream is unavailable")

                def log_message(self, fmt: str, *args: object) -> None:
                    del fmt
                    del args

            upstream_server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _UpstreamHandler,
            )
            upstream_thread = threading.Thread(
                target=upstream_server.serve_forever,
                kwargs={"poll_interval": 0.05},
                daemon=True,
            )
            upstream_thread.start()
            try:
                server_info_path = Path(tmpdir) / "server-info.json"
                proxy_args = [
                    "responses-api-proxy",
                    "--upstream-url",
                    f"http://127.0.0.1:{upstream_server.server_port}/v1/responses",
                    "--http-shutdown",
                    "--server-info",
                    str(server_info_path),
                ]
                results: list[int] = []
                proxy_thread = threading.Thread(
                    target=lambda: results.append(main(proxy_args, stdin="sk-test-key-2")),
                    daemon=True,
                )
                proxy_thread.start()

                proxy_info = None
                for _ in range(200):
                    if server_info_path.exists():
                        text = server_info_path.read_text(encoding="utf-8").strip()
                        if text:
                            proxy_info = json.loads(text)
                            break
                    time.sleep(0.05)
                self.assertIsNotNone(proxy_info)
                proxy_port = proxy_info["port"]

                with self.assertRaisesRegex(HTTPError, "HTTP Error 418") as ctx:
                    req = Request(
                        f"http://127.0.0.1:{proxy_port}/v1/responses",
                        method="POST",
                        data=b"",
                        headers={"Content-Type": "application/json"},
                    )
                    with urlopen(req):
                        pass
                self.assertEqual(ctx.exception.code, 418)
                self.assertEqual(ctx.exception.read(), b"upstream is unavailable")
                self.assertEqual(ctx.exception.headers.get("X-Upstream-Error"), "true")

                with urlopen(f"http://127.0.0.1:{proxy_port}/shutdown") as shutdown:
                    self.assertEqual(shutdown.status, 200)
                proxy_thread.join(timeout=2)
            finally:
                upstream_server.shutdown()
                upstream_thread.join()
                if "proxy_thread" in locals() and proxy_thread.is_alive():
                    proxy_thread.join(timeout=1)

    def test_main_responses_api_proxy_rejects_disallowed_path_with_403(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server_info_path = Path(tmpdir) / "server-info.json"
            proxy_args = [
                "responses-api-proxy",
                "--http-shutdown",
                "--upstream-url",
                "https://example.com/v1/responses",
                "--server-info",
                str(server_info_path),
            ]
            results: list[int] = []
            proxy_thread = threading.Thread(
                target=lambda: results.append(main(proxy_args, stdin="sk-test-key-3")),
                daemon=True,
            )
            proxy_thread.start()
            try:
                proxy_info = None
                for _ in range(200):
                    if server_info_path.exists():
                        text = server_info_path.read_text(encoding="utf-8").strip()
                        if text:
                            proxy_info = json.loads(text)
                            break
                    time.sleep(0.05)
                self.assertIsNotNone(proxy_info)
                proxy_port = proxy_info["port"]

                with self.assertRaisesRegex(HTTPError, "HTTP Error 403") as ctx:
                    with urlopen(f"http://127.0.0.1:{proxy_port}/not-allowed"):
                        pass
                self.assertEqual(ctx.exception.code, 403)
                self.assertEqual(ctx.exception.read(), b"")
                with urlopen(f"http://127.0.0.1:{proxy_port}/shutdown") as shutdown:
                    self.assertEqual(shutdown.status, 200)
                proxy_thread.join(timeout=2)
            finally:
                if proxy_thread.is_alive():
                    proxy_thread.join(timeout=1)

    def test_main_responses_api_proxy_rejects_shutdown_with_query_with_403(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server_info_path = Path(tmpdir) / "server-info.json"
            proxy_args = [
                "responses-api-proxy",
                "--http-shutdown",
                "--upstream-url",
                "https://example.com/v1/responses",
                "--server-info",
                str(server_info_path),
            ]
            results: list[int] = []
            proxy_thread = threading.Thread(
                target=lambda: results.append(main(proxy_args, stdin="sk-test-key-4")),
                daemon=True,
            )
            proxy_thread.start()
            try:
                proxy_info = None
                for _ in range(200):
                    if server_info_path.exists():
                        text = server_info_path.read_text(encoding="utf-8").strip()
                        if text:
                            proxy_info = json.loads(text)
                            break
                    time.sleep(0.05)
                self.assertIsNotNone(proxy_info)
                proxy_port = proxy_info["port"]

                with self.assertRaisesRegex(HTTPError, "HTTP Error 403") as ctx:
                    with urlopen(f"http://127.0.0.1:{proxy_port}/shutdown?x=1"):
                        pass
                self.assertEqual(ctx.exception.code, 403)
                self.assertEqual(ctx.exception.read(), b"")
                with urlopen(f"http://127.0.0.1:{proxy_port}/shutdown") as shutdown:
                    self.assertEqual(shutdown.status, 200)
                proxy_thread.join(timeout=2)
            finally:
                if proxy_thread.is_alive():
                    proxy_thread.join(timeout=1)

    def test_main_stdio_to_uds_relay_roundtrip(self):
        if not hasattr(socket, "AF_UNIX"):
            self.skipTest("AF_UNIX is unavailable on this platform")

        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = Path(tmpdir) / "codex.sock"
            response_payload = b"response-from-upstream"
            received_payloads: list[bytes] = []

            def _socket_server() -> None:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                    server.bind(str(socket_path))
                    server.listen(1)
                    conn, _ = server.accept()
                    with conn:
                        data = conn.recv(4096)
                        received_payloads.append(data)
                        conn.sendall(response_payload)

            server_thread = threading.Thread(target=_socket_server, daemon=True)
            server_thread.start()

            output = io.BytesIO()
            stderr = io.StringIO()
            with patch("pycodex.cli.parser.sys.stdout", output):
                code = _run_stdio_to_uds(
                    (str(socket_path),),
                    stdout=io.StringIO(),
                    stderr=stderr,
                    stdin=b"client-data",
                )
            server_thread.join(timeout=2)

            self.assertEqual(code, 0)
            self.assertEqual(received_payloads, [b"client-data"])
            self.assertEqual(output.getvalue(), response_payload)

    def test_parse_app_server_root_websocket_auth_combinations_are_valid(self):
        self.assertEqual(
            parse_args(
                [
                    "app-server",
                    "--ws-auth",
                    "capability-token",
                    "--ws-token-file",
                    "/tmp/token",
                    "proxy",
                ]
            ).command_args,
            ("--ws-auth", "capability-token", "--ws-token-file", "/tmp/token", "proxy"),
        )
        self.assertEqual(
            parse_args(
                [
                    "app-server",
                    "--ws-auth",
                    "signed-bearer-token",
                    "--ws-shared-secret-file",
                    "/tmp/secret",
                    "daemon",
                    "start",
                ]
            ).command_args,
            (
                "--ws-auth",
                "signed-bearer-token",
                "--ws-shared-secret-file",
                "/tmp/secret",
                "daemon",
                "start",
            ),
        )

    def test_main_remote_control_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["remote-control", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex remote-control [OPTIONS]", stdout.getvalue())

    def test_main_remote_control_start_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["remote-control", "start", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex remote-control start", stdout.getvalue())

    def test_main_remote_control_json_then_start_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["remote-control", "--json", "start", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex remote-control start", stdout.getvalue())

    def test_main_remote_control_stop_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["remote-control", "stop", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex remote-control stop", stdout.getvalue())

    def test_main_app_server_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["app-server", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app-server [OPTIONS] [COMMAND]", stdout.getvalue())

    def test_main_app_server_listen_then_daemon_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(
            [
                "app-server",
                "--listen",
                "stdio://",
                "daemon",
                "start",
                "--help",
            ],
            stdout=stdout,
        )

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app-server daemon start", stdout.getvalue())

    def test_main_app_server_help_with_listen_then_help_then_daemon_subcommand(self):
        stdout = io.StringIO()

        code = main(
            [
                "app-server",
                "--listen",
                "stdio://",
                "--help",
                "daemon",
                "start",
            ],
            stdout=stdout,
        )

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app-server daemon start", stdout.getvalue())

    def test_main_remote_auth_rejects_app_server_listen_then_daemon_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app-server",
                "--listen",
                "stdio://",
                "--help",
                "daemon",
                "start",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server daemon start`", stderr.getvalue())

    def test_main_remote_rejects_app_server_websocket_flags_then_proxy_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "app-server",
                "--ws-auth",
                "capability-token",
                "--help",
                "proxy",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server proxy`", stderr.getvalue())

    def test_main_app_server_daemon_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["app-server", "daemon", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app-server daemon <COMMAND>", stdout.getvalue())

    def test_main_app_server_daemon_subcommand_help_prints_usage(self):
        for daemon_subcommand in (
            "start",
            "stop",
            "bootstrap",
            "restart",
            "enable-remote-control",
            "disable-remote-control",
            "version",
            "pid-update-loop",
        ):
            stdout = io.StringIO()
            with self.subTest(daemon_subcommand=daemon_subcommand):
                code = main(
                    ["app-server", "daemon", daemon_subcommand, "--help"],
                    stdout=stdout,
                )

                self.assertEqual(code, 0)
                self.assertIn(f"Usage: codex app-server daemon {daemon_subcommand}", stdout.getvalue())

    def test_main_app_server_websocket_flags_then_proxy_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(
            [
                "app-server",
                "--ws-auth",
                "capability-token",
                "--ws-token-file",
                "/tmp/token",
                "proxy",
                "--help",
            ],
            stdout=stdout,
        )

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app-server proxy [OPTIONS]", stdout.getvalue())

    def test_main_app_server_websocket_flags_then_help_proxy_prints_usage(self):
        stdout = io.StringIO()

        code = main(
            [
                "app-server",
                "--ws-auth",
                "capability-token",
                "--ws-token-file",
                "/tmp/token",
                "--help",
                "proxy",
            ],
            stdout=stdout,
        )

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app-server proxy [OPTIONS]", stdout.getvalue())

    def test_main_app_server_proxy_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["app-server", "proxy", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app-server proxy [OPTIONS]", stdout.getvalue())

    def test_main_app_server_generate_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["app-server", "generate-ts", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app-server generate-ts [OPTIONS]", stdout.getvalue())

        stdout = io.StringIO()
        code = main(["app-server", "generate-json-schema", "--help"], stdout=stdout)
        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app-server generate-json-schema [OPTIONS]", stdout.getvalue())

        stdout = io.StringIO()
        code = main(["app-server", "generate-internal-json-schema", "--help"], stdout=stdout)
        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app-server generate-internal-json-schema [OPTIONS]", stdout.getvalue())

    def test_parse_update_accepts_no_args_and_rejects_unknown(self):
        self.assertEqual(parse_args(["update"]).command_args, ())
        with self.assertRaisesRegex(CliParseError, "Unknown argument for update"):
            parse_args(["update", "--force"])

    def test_parse_app_accepts_path_and_download_url(self):
        self.assertEqual(
            parse_args(
                ["app", "workspace", "--download-url", "https://example.com/codex"]
            ).command_args,
            ("workspace", "--download-url", "https://example.com/codex"),
        )

    def test_parse_exec_server_remote_requires_environment_id(self):
        with self.assertRaisesRegex(
            CliParseError, "--environment-id is required when --remote is set\\."
        ):
            parse_args(["exec-server", "--remote", "ws://127.0.0.1:4500"])

    def test_parse_exec_server_remote_accepts_environment_id(self):
        self.assertEqual(
            parse_args(
                ["exec-server", "--remote", "ws://127.0.0.1:4500", "--environment-id", "env-1"]
            ).command_args,
            ("--remote", "ws://127.0.0.1:4500", "--environment-id", "env-1"),
        )

    def test_parse_exec_server_listen_requires_value(self):
        with self.assertRaisesRegex(CliParseError, "Missing value for --listen\\."):
            parse_args(["exec-server", "--listen"])

    def test_parse_exec_server_listen_conflicts_with_remote(self):
        with self.assertRaisesRegex(
            CliParseError, "--listen cannot be used with --remote\\."
        ):
            parse_args(
                [
                    "exec-server",
                    "--listen",
                    "127.0.0.1:8080",
                    "--remote",
                    "ws://127.0.0.1:4500",
                    "--environment-id",
                    "env-1",
                ]
            )

    def test_parse_exec_server_accepts_stdio_listen(self):
        self.assertEqual(
            parse_args(["exec-server", "--listen", "stdio://"]).command_args,
            ("--listen", "stdio://"),
        )

    def test_parse_exec_server_agent_identity_auth_allows_remote_after_flag(self):
        self.assertEqual(
            parse_args(
                [
                    "exec-server",
                    "--use-agent-identity-auth",
                    "--remote",
                    "ws://127.0.0.1:4500",
                    "--environment-id",
                    "env-1",
                ]
            ).command_args,
            (
                "--use-agent-identity-auth",
                "--remote",
                "ws://127.0.0.1:4500",
                "--environment-id",
                "env-1",
            ),
        )

    def test_parse_app_rejects_extra_positional_or_unknown(self):
        with self.assertRaisesRegex(CliParseError, "Too many arguments for `app`"):
            parse_args(["app", "workspace", "another"])
        with self.assertRaisesRegex(CliParseError, "Unknown argument for app: --bad"):
            parse_args(["app", "--bad"])
        with self.assertRaisesRegex(CliParseError, "Missing value for --download-url\\."):
            parse_args(["app", "--download-url"])

    def test_main_app_noop_on_linux(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("pycodex.cli.parser.sys.platform", "linux"):
            code = main(["app", "/tmp/my-workspace"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_parse_resume_allows_session_id_with_options(self):
        self.assertEqual(
            parse_args(
                [
                    "resume",
                    "abc",
                    "--all",
                    "--include-non-interactive",
                    "--remote",
                    "ws://localhost:4500",
                    "--remote-auth-token-env",
                    "TOKEN_ENV",
                ]
            ).command_args,
            (
                "abc",
                "--all",
                "--include-non-interactive",
                "--remote",
                "ws://localhost:4500",
                "--remote-auth-token-env",
                "TOKEN_ENV",
            ),
        )

    def test_parse_fork_rejects_last_with_session_id(self):
        with self.assertRaisesRegex(CliParseError, "fork does not support --last with session-id"):
            parse_args(["fork", "abc", "--last"])

    def test_parse_fork_allows_id_without_last(self):
        self.assertEqual(parse_args(["fork", "abc"]).command_args, ("abc",))

    def test_parse_fork_allows_all_flag(self):
        self.assertEqual(parse_args(["fork", "--all"]).command_args, ("--all",))

    def test_parse_apply_requires_task_id(self):
        with self.assertRaisesRegex(CliParseError, "apply requires TASK_ID"):
            parse_args(["apply"])
        with self.assertRaisesRegex(CliParseError, "Too many arguments for `apply`"):
            parse_args(["apply", "task-1", "extra"])

    def test_parse_apply_rejects_unknown_flag(self):
        with self.assertRaisesRegex(CliParseError, "Unknown argument for apply"):
            parse_args(["apply", "--bad"])

    def test_parse_apply_accepts_dash_prefixed_task_id_via_end_marker(self):
        self.assertEqual(
            parse_args(["apply", "--", "-task-1"]).command_args,
            ("--", "-task-1"),
        )

    def test_parse_apply_rejects_extra_after_end_marker(self):
        with self.assertRaisesRegex(CliParseError, "Too many arguments for `apply`"):
            parse_args(["apply", "--", "-task-1", "extra"])

    def test_parse_cloud_exec_without_subcommand_runs_default_ui(self):
        self.assertEqual(parse_args(["cloud"]).command_args, ())

    def test_parse_cloud_exec_with_query_and_options(self):
        self.assertEqual(
            parse_args(["cloud", "exec", "fix a bug", "--env", "env-1", "--attempts", "2", "--branch", "main"]).command_args,
            ("exec", "fix a bug", "--env", "env-1", "--attempts", "2", "--branch", "main"),
        )

    def test_parse_cloud_status_requires_task_id(self):
        with self.assertRaisesRegex(CliParseError, "cloud status requires TASK_ID"):
            parse_args(["cloud", "status"])
        self.assertEqual(parse_args(["cloud", "status", "task-1"]).command_args, ("status", "task-1"))

    def test_parse_cloud_status_accepts_task_id_from_url_forms(self):
        parsed = parse_args([
            "cloud",
            "status",
            "https://chatgpt.com/backend-api/wham/tasks/task-99?source=cli#fragment",
        ])
        self.assertEqual(parsed.command_args, ("status", "https://chatgpt.com/backend-api/wham/tasks/task-99?source=cli#fragment"))

    def test_main_cloud_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["cloud", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex cloud", stdout.getvalue())

    def test_main_cloud_subcommand_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["cloud", "status", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex cloud", stdout.getvalue())

    def test_main_cloud_exec_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["cloud", "exec", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex cloud", stdout.getvalue())

    def test_main_cloud_subcommand_help_shows_subcommand_usage(self):
        for subcommand in ("exec", "status", "apply", "diff", "list"):
            with self.subTest(subcommand=subcommand):
                stdout = io.StringIO()

                code = main(["cloud", subcommand, "--help"], stdout=stdout)

                self.assertEqual(code, 0)
                self.assertIn(f"Usage: codex cloud {subcommand}", stdout.getvalue())

    def test_main_cloud_help_shows_root_subcommand_usage(self):
        stdout = io.StringIO()

        code = main(["cloud", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex cloud [OPTIONS] <COMMAND>", stdout.getvalue())

    def test_parse_cloud_apply_accepts_task_id_from_url_forms(self):
        parsed = parse_args([
            "cloud",
            "apply",
            "https://chatgpt.com/backend-api/wham/tasks/task-99?source=cli#fragment",
        ])
        self.assertEqual(
            parsed.command_args,
            (
                "apply",
                "https://chatgpt.com/backend-api/wham/tasks/task-99?source=cli#fragment",
            ),
        )

    def test_parse_cloud_unknown_subcommand(self):
        with self.assertRaisesRegex(CliParseError, "Unknown cloud subcommand"):
            parse_args(["cloud", "unknown"])

    def test_main_cloud_unknown_subcommand_reports_helpful_error(self):
        stderr = io.StringIO()

        code = main(["cloud", "unknown"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Unknown cloud subcommand: unknown", stderr.getvalue())

    def test_run_cloud_command_unknown_subcommand_with_fallback_returns_nonfatal(self):
        previous_fallback = os.environ.get("PYCODEX_CLOUD_FALLBACK")
        os.environ["PYCODEX_CLOUD_FALLBACK"] = "1"
        stderr = io.StringIO()
        stdout = io.StringIO()

        try:
            with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"):
                code = _run_cloud_command(
                    ("unknown",),
                    stdout=stdout,
                    stderr=stderr,
                )
        finally:
            if previous_fallback is None:
                os.environ.pop("PYCODEX_CLOUD_FALLBACK", None)
            else:
                os.environ["PYCODEX_CLOUD_FALLBACK"] = previous_fallback

        self.assertEqual(code, 0)
        self.assertIn("pycodex: command 'cloud unknown' is currently not implemented yet.", stderr.getvalue())

    def test_run_cloud_command_unknown_subcommand_without_fallback_returns_unsupported(self):
        previous_fallback = os.environ.get("PYCODEX_CLOUD_FALLBACK")
        if previous_fallback is not None:
            os.environ.pop("PYCODEX_CLOUD_FALLBACK", None)
        stderr = io.StringIO()
        stdout = io.StringIO()

        try:
            with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"):
                code = _run_cloud_command(
                    ("unknown",),
                    stdout=stdout,
                    stderr=stderr,
                )
        finally:
            if previous_fallback is None:
                os.environ.pop("PYCODEX_CLOUD_FALLBACK", None)
            else:
                os.environ["PYCODEX_CLOUD_FALLBACK"] = previous_fallback

        self.assertEqual(code, 64)
        self.assertIn("pycodex: command 'cloud unknown' is currently not implemented yet.", stderr.getvalue())

    def test_main_cloud_no_subcommand_with_fallback_runs_list(self):
        previous_fallback = os.environ.get("PYCODEX_CLOUD_FALLBACK")
        os.environ["PYCODEX_CLOUD_FALLBACK"] = "1"
        stderr = io.StringIO()
        stdout = io.StringIO()

        try:
            with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
                "pycodex.cli.parser._list_cloud_tasks",
                return_value=([
                    {
                        "id": "task-1",
                        "status": "ready",
                        "title": "Demo",
                        "url": "https://chatgpt.com/tasks/task-1",
                    },
                ], None),
            ):
                code = main(["cloud"], stdout=stdout, stderr=stderr)
        finally:
            if previous_fallback is None:
                os.environ.pop("PYCODEX_CLOUD_FALLBACK", None)
            else:
                os.environ["PYCODEX_CLOUD_FALLBACK"] = previous_fallback

        self.assertEqual(code, 0)
        self.assertIn("No cloud subcommand provided. Falling back to `cloud list`.", stderr.getvalue())
        self.assertIn("task-1", stdout.getvalue())

    def test_main_cloud_no_subcommand_without_fallback_returns_interactive_message(self):
        previous_fallback = os.environ.get("PYCODEX_CLOUD_FALLBACK")
        if previous_fallback is not None:
            os.environ.pop("PYCODEX_CLOUD_FALLBACK", None)
        stderr = io.StringIO()
        stdout = io.StringIO()

        try:
            code = main(["cloud"], stdout=stdout, stderr=stderr)
        finally:
            if previous_fallback is None:
                os.environ.pop("PYCODEX_CLOUD_FALLBACK", None)
            else:
                os.environ["PYCODEX_CLOUD_FALLBACK"] = previous_fallback

        self.assertEqual(code, 64)
        self.assertIn(
            "pycodex: command 'cloud' is currently parsed but the interactive browser is not implemented yet.",
            stderr.getvalue(),
        )

    def test_main_cloud_apply_normalizes_task_id_from_url(self):
        captured: dict[str, object] = {}

        def fake_request_json(url, method, token):
            captured["url"] = url
            return {"task": {"id": "task-99"}, "turn_history": []}

        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            side_effect=fake_request_json,
        ), patch("pycodex.cli.parser._collect_cloud_attempt_diffs", return_value=[{"diff": "diff-1"}]), patch(
            "pycodex.cli.parser._apply_task_diff_with_git",
            return_value=0,
        ):
            code = main([
                "cloud",
                "apply",
                "https://chatgpt.com/backend-api/wham/tasks/task-99?source=cli#fragment",
            ])

        self.assertEqual(code, 0)
        self.assertIn("/wham/tasks/task-99", str(captured.get("url", "")))

    def test_main_cloud_diff_normalizes_task_id_from_url(self):
        stdout = io.StringIO()

        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            return_value={"task": {"id": "task-99"}},
        ), patch(
            "pycodex.cli.parser._collect_cloud_attempt_diffs",
            return_value=[{"diff": "diff-from-url"}],
        ):
            code = main(
                [
                    "cloud",
                    "diff",
                    "https://chatgpt.com/backend-api/wham/tasks/task-99?source=cli#fragment",
                ],
                stdout=stdout,
            )

        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "diff-from-url\n")

    def test_parse_cloud_apply_and_diff_require_task_id(self):
        with self.assertRaisesRegex(CliParseError, "cloud apply requires TASK_ID"):
            parse_args(["cloud", "apply"])
        with self.assertRaisesRegex(CliParseError, "cloud diff requires TASK_ID"):
            parse_args(["cloud", "diff"])

    def test_parse_cloud_list_parses_options(self):
        self.assertEqual(
            parse_args(["cloud", "list", "--env", "env-1", "--limit", "5", "--cursor", "c", "--json"]).command_args,
            ("list", "--env", "env-1", "--limit", "5", "--cursor", "c", "--json"),
        )

    def test_parse_cloud_attempt_range_is_enforced(self):
        with self.assertRaisesRegex(CliParseError, "Invalid value for --attempts"):
            parse_args(["cloud", "exec", "--attempts", "9", "hello"])
        with self.assertRaisesRegex(CliParseError, "Invalid value for --attempt"):
            parse_args(["cloud", "apply", "task-1", "--attempt", "0"])
        with self.assertRaisesRegex(CliParseError, "Missing value for --attempt"):
            parse_args(["cloud", "apply", "--attempt"])
        self.assertEqual(
            parse_args(["cloud", "apply", "--attempt", "2", "task-1"]).command_args,
            ("apply", "--attempt", "2", "task-1"),
        )

    def test_parse_cloud_exec_allows_options_around_query(self):
        self.assertEqual(
            parse_args(["cloud", "exec", "--env", "env-1", "fix a bug", "--attempts", "2"]).command_args,
            ("exec", "--env", "env-1", "fix a bug", "--attempts", "2"),
        )
        self.assertEqual(
            parse_args(["cloud", "exec", "--", "--leading-hyphen-query"]).command_args,
            ("exec", "--", "--leading-hyphen-query"),
        )

    def test_main_cloud_exec_fails_without_env(self):
        stderr = io.StringIO()
        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"):
            code = main(["cloud", "exec", "write tests"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("cloud exec requires --env.", stderr.getvalue())

    def test_main_cloud_without_subcommand_without_fallback_prints_not_implemented(self):
        stderr = io.StringIO()

        code = main(["cloud"], stderr=stderr)

        self.assertEqual(code, 64)
        self.assertIn("command 'cloud' is currently parsed but the interactive browser is not implemented yet.", stderr.getvalue())

    def test_main_cloud_without_subcommand_with_fallback_prints_warning(self):
        previous_fallback = os.environ.get("PYCODEX_CLOUD_FALLBACK")
        os.environ["PYCODEX_CLOUD_FALLBACK"] = "1"
        stderr = io.StringIO()

        try:
            with patch("pycodex.cli.parser._cloud_auth_token", side_effect=RuntimeError("Not logged in.")):
                code = main(["cloud"], stderr=stderr)
        finally:
            if previous_fallback is None:
                os.environ.pop("PYCODEX_CLOUD_FALLBACK", None)
            else:
                os.environ["PYCODEX_CLOUD_FALLBACK"] = previous_fallback

        self.assertEqual(code, 2)
        self.assertIn("No cloud subcommand provided. Falling back to `cloud list`.", stderr.getvalue())
        self.assertIn("pycodex: Not logged in.", stderr.getvalue())

    def test_main_cloud_status_requires_auth(self):
        stderr = io.StringIO()
        with patch("pycodex.cli.parser._cloud_auth_token", side_effect=RuntimeError("Not logged in.")):
            code = main(["cloud", "status", "task-1"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("pycodex: Not logged in.", stderr.getvalue())

    def test_main_cloud_exec_posts_task_payload(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        observed: dict[str, object] = {}

        def fake_request_json(url, method, token, payload=None):
            observed["url"] = url
            observed["method"] = method
            observed["token"] = token
            observed["payload"] = payload
            return {"task": {"id": "task-123"}}

        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            side_effect=fake_request_json,
        ):
            code = main(
                [
                    "cloud",
                    "exec",
                    "write tests",
                    "--env",
                    "env-1",
                    "--branch",
                    "feature-branch",
                    "--attempts",
                    "2",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(code, 0)
        self.assertIn("/wham/tasks", str(observed.get("url")))
        self.assertEqual(observed.get("method"), "POST")
        self.assertEqual(observed.get("token"), "access-token")
        payload = observed.get("payload")
        self.assertIsInstance(payload, dict)
        if isinstance(payload, dict):
            new_task = payload.get("new_task")
            self.assertIsInstance(new_task, dict)
            if isinstance(new_task, dict):
                self.assertEqual(new_task.get("environment_id"), "env-1")
                self.assertEqual(new_task.get("branch"), "feature-branch")
                self.assertFalse(new_task.get("run_environment_in_qa_mode"))
                self.assertEqual(payload.get("metadata"), {"best_of_n": 2})
            input_items = payload.get("input_items")
            self.assertIsInstance(input_items, list)
            if isinstance(input_items, list):
                item = input_items[0]
                self.assertEqual(item["content"][0]["text"], "write tests")
        self.assertEqual(stdout.getvalue(), "https://chatgpt.com/codex/tasks/task-123\n")

    def test_main_cloud_status_bad_payload(self):
        stderr = io.StringIO()
        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            return_value="not-a-dict",
        ):
            code = main(["cloud", "status", "task-1"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("unexpected response format from cloud task endpoint.", stderr.getvalue())

    def test_main_cloud_status_normalizes_task_id_from_url(self):
        observed = {}

        def fake_request_json(url, method, token):
            observed["url"] = url
            return {
                "id": "task-99",
                "task_status_display": {"status": "READY"},
            }

        stderr = io.StringIO()
        stdout = io.StringIO()
        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            side_effect=fake_request_json,
        ):
            code = main(
                ["cloud", "status", "https://chatgpt.com/backend-api/wham/tasks/task-99?src=cli#frag"],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(code, 0)
        self.assertIn("/wham/tasks/task-99", observed.get("url", ""))
        self.assertIn("status: READY", stdout.getvalue())

    def test_main_cloud_apply_respects_attempt(self):
        captured: dict[str, object] = {}

        def fake_collect_cloud_attempt_diffs(payload: object, *, token: str, task_id: str) -> list[dict[str, object]]:
            captured["token"] = token
            captured["task_id"] = task_id
            return [
                {"diff": "diff-1"},
                {"diff": "diff-2"},
            ]

        def fake_apply_task_diff_with_git(diff: str, **kwargs):
            captured["applied_diff"] = diff
            return 0

        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            return_value={"task": {"id": "task-1"}},
        ), patch(
            "pycodex.cli.parser._collect_cloud_attempt_diffs",
            side_effect=fake_collect_cloud_attempt_diffs,
        ), patch(
            "pycodex.cli.parser._apply_task_diff_with_git",
            side_effect=fake_apply_task_diff_with_git,
        ):
            code = main(["cloud", "apply", "--attempt", "2", "task-1"])

        self.assertEqual(code, 0)
        self.assertEqual(captured.get("task_id"), "task-1")
        self.assertEqual(captured.get("token"), "access-token")
        self.assertEqual(captured.get("applied_diff"), "diff-2")

    def test_main_cloud_apply_out_of_range_attempt_prints_hint(self):
        stderr = io.StringIO()
        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            return_value={"task": {"id": "task-1"}},
        ), patch(
            "pycodex.cli.parser._collect_cloud_attempt_diffs",
            return_value=[
                {"diff": "diff-1"},
                {"diff": "diff-2"},
            ],
        ):
            code = main(["cloud", "apply", "task-1", "--attempt", "3"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Attempt 3 not available for task task-1; only 2 attempt(s) found.", stderr.getvalue())

    def test_main_cloud_apply_collect_diff_failure_returns_error(self):
        stderr = io.StringIO()
        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            return_value={"task": {"id": "task-1"}},
        ), patch(
            "pycodex.cli.parser._collect_cloud_attempt_diffs",
            side_effect=RuntimeError("collect failed"),
        ):
            code = main(["cloud", "apply", "task-1"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("pycodex: collect failed", stderr.getvalue())

    def test_main_cloud_apply_bad_payload_format(self):
        stderr = io.StringIO()
        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            return_value="not-a-dict",
        ):
            code = main(["cloud", "apply", "task-1"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("unexpected response format from cloud task endpoint.", stderr.getvalue())

    def test_main_cloud_diff_respects_attempt(self):
        stdout = io.StringIO()
        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            return_value={"task": {"id": "task-1"}},
        ), patch(
            "pycodex.cli.parser._collect_cloud_attempt_diffs",
            return_value=[
                {"diff": "diff-1"},
                {"diff": "diff-2"},
            ],
        ):
            code = main(["cloud", "diff", "task-1", "--attempt", "1"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "diff-1\n")

    def test_main_cloud_diff_collect_failure_returns_error(self):
        stderr = io.StringIO()
        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            return_value={"task": {"id": "task-1"}},
        ), patch(
            "pycodex.cli.parser._collect_cloud_attempt_diffs",
            side_effect=RuntimeError("collect failed"),
        ):
            code = main(["cloud", "diff", "task-1"], stdout=io.StringIO(), stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("pycodex: collect failed", stderr.getvalue())

    def test_main_cloud_diff_no_diffs_returns_exit_1(self):
        stderr = io.StringIO()
        with patch("pycodex.cli.parser._cloud_auth_token", return_value="access-token"), patch(
            "pycodex.cli.parser._cloud_request_json",
            return_value={"task": {"id": "task-1"}},
        ), patch(
            "pycodex.cli.parser._collect_cloud_attempt_diffs",
            return_value=[],
        ):
            code = main(["cloud", "diff", "task-1"], stdout=io.StringIO(), stderr=stderr)

        self.assertEqual(code, 1)
        self.assertIn("No diff available for task task-1.", stderr.getvalue())

    def test_collect_cloud_attempt_diffs_orders_by_placement_then_created_at(self):
        payload = {
            "task": {
                "current_assistant_turn": {
                    "id": "current",
                    "attempt_placement": "2",
                    "created_at": "2026-01-01T00:00:00Z",
                    "output_items": [{"type": "output_diff", "diff": "current"}],
                }
            }
        }

        siblings = [
            {
                "id": "earliest-no-date",
                "created_at": "not-a-date",
                "output_items": [{"type": "output_diff", "diff": "no-date"}],
            },
            {
                "id": "placement-one",
                "attempt_placement": 1,
                "created_at": "2024-01-01T00:00:00Z",
                "output_items": [{"type": "output_diff", "diff": "priority"}],
            },
            {
                "id": "created-at-middle",
                "created_at": "2025-01-01T00:00:00Z",
                "output_items": [{"type": "output_diff", "diff": "created-middle"}],
            },
        ]

        def fake_request_json(url, method, token, payload=None):
            del method, token, payload
            if "sibling_turns" in url:
                return {"sibling_turns": siblings}
            raise AssertionError("unexpected request to _cloud_request_json")

        with patch("pycodex.cli.parser._cloud_request_json", side_effect=fake_request_json):
            attempts = _collect_cloud_attempt_diffs(payload, token="access-token", task_id="task-1")

        self.assertEqual(len(attempts), 4)
        self.assertEqual(attempts[0]["diff"], "priority")
        self.assertEqual(attempts[1]["diff"], "current")
        self.assertEqual(attempts[2]["diff"], "created-middle")
        self.assertEqual(attempts[3]["diff"], "no-date")
        self.assertEqual(_select_cloud_attempt_diff(attempts, 1), "priority")
        self.assertEqual(_select_cloud_attempt_diff(attempts, 2), "current")
        self.assertEqual(_select_cloud_attempt_diff(attempts, 3), "created-middle")
        self.assertEqual(_select_cloud_attempt_diff(attempts, 4), "no-date")
        self.assertIsNone(_select_cloud_attempt_diff(attempts, 5))

    def test_collect_cloud_attempt_diffs_deduplicates_turn_id(self):
        payload = {
            "task": {
                "current_assistant_turn": {
                    "id": "shared",
                    "output_items": [{"type": "output_diff", "diff": "current"}],
                }
            }
        }

        siblings = [
            {
                "id": "shared",
                "output_items": [{"type": "output_diff", "diff": "duplicate"}],
            },
            {
                "id": "unique",
                "output_items": [{"type": "output_diff", "diff": "unique"}],
            },
        ]

        def fake_request_json(url, method, token, payload=None):
            del method, token, payload
            if "sibling_turns" in url:
                return {"sibling_turns": siblings}
            raise AssertionError("unexpected request")

        with patch("pycodex.cli.parser._cloud_request_json", side_effect=fake_request_json):
            attempts = _collect_cloud_attempt_diffs(payload, token="access-token", task_id="task-1")

        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["diff"], "current")
        self.assertEqual(attempts[1]["diff"], "unique")

    def test_parse_cloud_limit_range_is_enforced(self):
        with self.assertRaisesRegex(CliParseError, "Invalid value for --limit"):
            parse_args(["cloud", "list", "--limit", "99"])

    def test_parse_execpolicy_requires_check(self):
        with self.assertRaisesRegex(CliParseError, "execpolicy requires a subcommand: check"):
            parse_args(["execpolicy"])

    def test_parse_execpolicy_check_requires_rules_and_command(self):
        with self.assertRaisesRegex(CliParseError, "execpolicy check requires --rules."):
            parse_args(["execpolicy", "check", "echo", "ls"])
        with self.assertRaisesRegex(CliParseError, "execpolicy check requires COMMAND."):
            parse_args(["execpolicy", "check", "--rules", "policy.json"])
        with self.assertRaisesRegex(CliParseError, "execpolicy check requires COMMAND."):
            parse_args(["execpolicy", "check", "--rules", "policy.json", "--"])

    def test_parse_execpolicy_check_parses_known_flags_and_command(self):
        self.assertEqual(
            parse_args(
                [
                    "execpolicy",
                    "check",
                    "--rules",
                    "policy1",
                    "--rules",
                    "policy2",
                    "--pretty",
                    "--resolve-host-executables",
                    "echo",
                    "hello",
                ]
            ).command_args,
            (
                "check",
                "--rules",
                "policy1",
                "--rules",
                "policy2",
                "--pretty",
                "--resolve-host-executables",
                "echo",
                "hello",
            ),
        )

    def test_parse_execpolicy_check_accepts_dashdash_command_without_special_treatment(self):
        self.assertEqual(
            parse_args(
                ["execpolicy", "check", "--rules", "policy.json", "--", "-h"]
            ).command_args,
            ("check", "--rules", "policy.json", "--", "-h"),
        )

    def test_main_execpolicy_check_matches_rule(self):
        fd, policy_path = tempfile.mkstemp()
        try:
            os.close(fd)
            Path(policy_path).write_text(
                "prefix_rule(pattern=[\"echo\", \"hello\"], decision=\"allow\")\n"
            )

            stdout = io.StringIO()
            code = main(["execpolicy", "check", "--rules", policy_path, "echo", "hello"], stdout=stdout)
            self.assertEqual(code, 0)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["decision"], "allow")
            self.assertEqual(
                payload["matchedRules"],
                [
                    {
                        "prefixRuleMatch": {
                            "matchedPrefix": ["echo", "hello"],
                            "decision": "allow",
                        }
                    }
                ],
            )
        finally:
            os.remove(policy_path)

    def test_main_execpolicy_check_includes_justification_when_present(self):
        fd, policy_path = tempfile.mkstemp()
        try:
            os.close(fd)
            Path(policy_path).write_text(
                "prefix_rule("
                "pattern=[\"git\", \"push\"], "
                "decision=\"forbidden\", "
                "justification=\"pushing is blocked in this repo\""
                ")\n"
            )

            stdout = io.StringIO()
            code = main(
                ["execpolicy", "check", "--rules", policy_path, "git", "push", "origin", "main"],
                stdout=stdout,
            )
            self.assertEqual(code, 0)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(
                payload,
                {
                    "matchedRules": [
                        {
                            "prefixRuleMatch": {
                                "matchedPrefix": ["git", "push"],
                                "decision": "forbidden",
                                "justification": "pushing is blocked in this repo",
                            }
                        }
                    ],
                    "decision": "forbidden",
                },
            )
        finally:
            os.remove(policy_path)

    def test_main_execpolicy_check_no_match_reports_empty_rules(self):
        fd, policy_path = tempfile.mkstemp()
        try:
            os.close(fd)
            Path(policy_path).write_text(
                "prefix_rule(pattern=[\"echo\", \"hello\"], decision=\"allow\")\n"
            )

            stdout = io.StringIO()
            code = main(["execpolicy", "check", "--rules", policy_path, "echo", "world"], stdout=stdout)
            self.assertEqual(code, 0)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload, {"matchedRules": []})
        finally:
            os.remove(policy_path)

    def test_main_execpolicy_check_help(self):
        stdout = io.StringIO()
        code = main(["execpolicy", "check", "--help"], stdout=stdout)
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout.getvalue().strip(),
            "Usage: codex execpolicy [OPTIONS]",
        )

    def test_main_execpolicy_check_with_pretty_output(self):
        fd, policy_path = tempfile.mkstemp()
        try:
            os.close(fd)
            Path(policy_path).write_text(
                "prefix_rule(pattern=[\"echo\", \"hello\"], decision=\"prompt\")\n"
            )

            stdout = io.StringIO()
            code = main(
                ["execpolicy", "check", "--rules", policy_path, "--pretty", "echo", "hello"],
                stdout=stdout,
            )
            self.assertEqual(code, 0)

            text = stdout.getvalue()
            payload = json.loads(text)
            self.assertEqual(payload["decision"], "prompt")
            self.assertIn("\n", text)
        finally:
            os.remove(policy_path)

    def test_main_execpolicy_check_resolve_host_executables(self):
        fd, policy_path = tempfile.mkstemp()
        command_path = Path(policy_path).with_name("host_cmd")
        try:
            os.close(fd)
            Path(policy_path).write_text(
                "host_executable(name=\"host_cmd\", paths=[\"%s\"])\n"
                "prefix_rule(pattern=[\"host_cmd\", \"--help\"], decision=\"allow\")\n"
                % (str(command_path),)
            )

            stdout = io.StringIO()
            code = main(
                [
                    "execpolicy",
                    "check",
                    "--rules",
                    policy_path,
                    "--resolve-host-executables",
                    str(command_path),
                    "--help",
                ],
                stdout=stdout,
            )
            self.assertEqual(code, 0)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["decision"], "allow")
            self.assertEqual(
                payload["matchedRules"][0]["prefixRuleMatch"]["resolvedProgram"],
                str(command_path),
            )
        finally:
            os.remove(policy_path)

    def test_main_execpolicy_check_reports_missing_rules_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = os.path.join(temp_dir, "missing_policy.json")
            stderr = io.StringIO()
            code = main(
                ["execpolicy", "check", "--rules", missing_path, "echo", "hello"],
                stderr=stderr,
            )
            self.assertEqual(code, 2)
            self.assertIn("failed to read policy at", stderr.getvalue())

    def test_main_execpolicy_check_reports_parse_error(self):
        fd, policy_path = tempfile.mkstemp()
        try:
            os.close(fd)
            Path(policy_path).write_text("prefix_rule(pattern=[\"echo\", \"hello\", decision=\"allow\")\n")

            stderr = io.StringIO()
            code = main(
                ["execpolicy", "check", "--rules", policy_path, "echo", "hello"],
                stderr=stderr,
            )
            self.assertEqual(code, 2)
            self.assertIn("failed to parse policy at", stderr.getvalue())
        finally:
            os.remove(policy_path)

    def test_main_execpolicy_check_reports_example_validation_error(self):
        fd, policy_path = tempfile.mkstemp()
        try:
            os.close(fd)
            Path(policy_path).write_text(
                "prefix_rule("
                'pattern=["echo", "hello"],'
                'decision="allow",'
                'match=[["echo", "bad"]],'
                ")\n"
            )

            stderr = io.StringIO()
            code = main(
                ["execpolicy", "check", "--rules", policy_path, "echo", "hello"],
                stderr=stderr,
            )
            self.assertEqual(code, 2)
            self.assertIn("invalid match example in", stderr.getvalue())

            self.assertIn("did not match any rule", stderr.getvalue())
        finally:
            os.remove(policy_path)

    def test_main_execpolicy_check_reports_network_rule_validation(self):
        fd, policy_path = tempfile.mkstemp()
        try:
            os.close(fd)
            Path(policy_path).write_text(
                'network_rule(host="https://example.com", protocol="tcp", decision="allow")\n'
            )

            stderr = io.StringIO()
            code = main(
                ["execpolicy", "check", "--rules", policy_path, "echo", "hello"],
                stderr=stderr,
            )
            self.assertEqual(code, 2)
            self.assertIn("network_rule host must be a hostname or IP literal", stderr.getvalue())
        finally:
            os.remove(policy_path)

    def test_parse_sandbox_accepts_profile_flags_and_dependencies(self):
        parsed = parse_args(
            [
                "sandbox",
                "--permissions-profile",
                "ci",
                "--profile",
                "work",
                "-C",
                "dir",
                "--include-managed-config",
                "--allow-unix-socket",
                "/tmp/codex.sock",
                "--log-denials",
            ]
        )

        self.assertEqual(
            parsed.command_args,
            (
                "--permissions-profile",
                "ci",
                "--profile",
                "work",
                "-C",
                "dir",
                "--include-managed-config",
                "--allow-unix-socket",
                "/tmp/codex.sock",
                "--log-denials",
            ),
        )

    def test_sandbox_requires_permissions_profile_with_cd_or_managed_config(self):
        with self.assertRaisesRegex(
            CliParseError, "the following required argument was not provided: --permissions-profile"
        ):
            parse_args(["sandbox", "--cd", "dir"])
        with self.assertRaisesRegex(
            CliParseError, "the following required argument was not provided: --permissions-profile"
        ):
            parse_args(["sandbox", "--include-managed-config"])

    def test_cloud_tasks_alias_matches_cloud_command(self):
        parsed = parse_args(["cloud-tasks", "list"])

        self.assertEqual(parsed.command, "cloud")
        self.assertEqual(parsed.command_args, ("list",))

    def test_root_options_are_collected_before_subcommand(self):
        parsed = parse_args(
            [
                "-c",
                "model=gpt-5",
                "--enable",
                "unified_exec",
                "--disable=old_flow",
                "--remote",
                "ws://127.0.0.1:1234",
                "--strict-config",
                "exec",
                "prompt",
            ]
        )

        self.assertEqual(parsed.command, "exec")
        self.assertEqual(parsed.config_overrides, ("model=gpt-5",))
        self.assertEqual(parsed.enable, ("unified_exec",))
        self.assertEqual(parsed.disable, ("old_flow",))
        self.assertEqual(parsed.remote, "ws://127.0.0.1:1234")
        self.assertTrue(parsed.strict_config)
        self.assertEqual(parsed.command_args, ("prompt",))

    def test_exec_cli_rejects_root_remote_like_upstream_noninteractive_dispatch(self):
        parsed = parse_args(["--remote", "ws://127.0.0.1:1234", "exec", "prompt"])

        with self.assertRaisesRegex(CliParseError, "only supported for interactive TUI commands"):
            parsed.exec_cli()

    def test_main_rejects_remote_auth_token_env_for_noninteractive_subcommand(self):
        stderr = io.StringIO()

        code = main(["--remote-auth-token-env", "CODEX_REMOTE_AUTH_TOKEN", "exec", "prompt"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex exec`", stderr.getvalue())

    def test_main_remote_rejects_remote_control_start(self):
        stderr = io.StringIO()

        code = main(["--remote", "ws://127.0.0.1:4500", "remote-control", "start"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex remote-control start`", stderr.getvalue())

    def test_main_remote_rejects_remote_control_start_with_json(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "remote-control",
                "--json",
                "start",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex remote-control start`", stderr.getvalue())

    def test_main_remote_rejects_remote_control_no_subcommand_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(["--remote", "ws://127.0.0.1:4500", "remote-control"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex remote-control`", stderr.getvalue())

    def test_main_remote_rejects_remote_control_stop(self):
        stderr = io.StringIO()

        code = main(["--remote", "ws://127.0.0.1:4500", "remote-control", "stop"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex remote-control stop`", stderr.getvalue())

    def test_main_remote_auth_rejects_remote_control_start(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "remote-control",
                "start",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex remote-control start`", stderr.getvalue())

    def test_main_remote_auth_rejects_remote_control_start_with_json(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "remote-control",
                "--json",
                "start",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex remote-control start`", stderr.getvalue())

    def test_main_remote_auth_rejects_remote_control_stop(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "remote-control",
                "stop",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex remote-control stop`", stderr.getvalue())

    def test_main_remote_rejects_debug_models_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(["--remote", "ws://127.0.0.1:4500", "debug", "models"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug models`", stderr.getvalue())

    def test_main_debug_models_returns_supported_default_models(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(["debug", "models"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["source"], "online")
        self.assertIn("gpt-5.3-codex", payload["models"])

    def test_main_remote_rejects_debug_models_with_preceding_help_flag(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "debug",
                "--help",
                "models",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug models`", stderr.getvalue())

    def test_main_remote_auth_rejects_debug_models_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "debug",
                "models",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug models`", stderr.getvalue())

    def test_main_remote_rejects_debug_app_server_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "debug",
                "app-server",
                "send-message-v2",
                "hello",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug app-server`", stderr.getvalue())

    def test_main_remote_rejects_debug_trace_reduce_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "debug",
                "trace-reduce",
                "trace.bundle",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug trace-reduce`", stderr.getvalue())

    def test_main_remote_rejects_debug_clear_memories_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "debug",
                "clear-memories",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug clear-memories`", stderr.getvalue())

    def test_main_remote_rejects_debug_prompt_input_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "debug",
                "prompt-input",
                "Summarize",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug prompt-input`", stderr.getvalue())

    def test_main_remote_auth_rejects_debug_app_server_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "debug",
                "app-server",
                "send-message-v2",
                "hello",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug app-server`", stderr.getvalue())

    def test_main_remote_auth_rejects_debug_trace_reduce_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "debug",
                "trace-reduce",
                "trace.bundle",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug trace-reduce`", stderr.getvalue())

    def test_main_remote_auth_rejects_debug_clear_memories_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "debug",
                "clear-memories",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug clear-memories`", stderr.getvalue())

    def test_main_remote_auth_rejects_debug_prompt_input_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "debug",
                "prompt-input",
                "Summarize",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug prompt-input`", stderr.getvalue())

    def test_main_remote_rejects_debug_app_server_with_preceding_help_flag(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "debug",
                "--help",
                "app-server",
                "send-message-v2",
                "hello",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug app-server`", stderr.getvalue())

    def test_main_remote_auth_rejects_debug_app_server_with_preceding_help_flag(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "debug",
                "--help",
                "app-server",
                "send-message-v2",
                "hello",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex debug app-server`", stderr.getvalue())

    def test_main_remote_auth_rejects_features_list_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(["--remote-auth-token-env", "CODEX_REMOTE_AUTH_TOKEN", "features", "list"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex features list`", stderr.getvalue())

    def test_main_remote_rejects_features_list_with_preceding_help_flag(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "features",
                "--help",
                "list",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex features list`", stderr.getvalue())

    def test_main_remote_rejects_features_enable_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "features",
                "enable",
                "shell_tool",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex features enable`", stderr.getvalue())

    def test_main_remote_rejects_features_list_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(["--remote", "ws://127.0.0.1:4500", "features", "list"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex features list`", stderr.getvalue())

    def test_main_remote_rejects_features_disable_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "features",
                "disable",
                "network_proxy",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex features disable`", stderr.getvalue())

    def test_main_remote_rejects_features_list_with_preceding_flag(self):
        stderr = io.StringIO()

        code = main(["--remote", "ws://127.0.0.1:4500", "features", "--json", "list"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex features list`", stderr.getvalue())

    def test_main_remote_auth_rejects_features_list_with_preceding_flag(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "features",
                "--json",
                "list",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex features list`", stderr.getvalue())

    def test_main_remote_auth_rejects_features_list_with_preceding_help_flag(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "features",
                "--help",
                "list",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex features list`", stderr.getvalue())

    def test_main_remote_auth_rejects_features_enable_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "features",
                "enable",
                "shell_tool",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex features enable`", stderr.getvalue())

    def test_main_remote_auth_rejects_features_disable_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "features",
                "disable",
                "network_proxy",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex features disable`", stderr.getvalue())

    def test_main_remote_auth_rejects_app_server_generate_json_schema_with_remote(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app-server",
                "generate-json-schema",
                "--out",
                "out",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server generate-json-schema`", stderr.getvalue())

    def test_main_remote_rejects_app_server_generate_ts_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "app-server",
                "generate-ts",
                "--out",
                "out",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server generate-ts`", stderr.getvalue())

    def test_main_remote_rejects_app_server_generate_json_schema_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "app-server",
                "generate-json-schema",
                "--out",
                "out",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server generate-json-schema`", stderr.getvalue())

    def test_main_remote_rejects_app_server_generate_internal_json_schema_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "app-server",
                "generate-internal-json-schema",
                "--out",
                "out",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn(
            "not `codex app-server generate-internal-json-schema`", stderr.getvalue()
        )

    def test_main_remote_rejects_app_server_proxy_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "app-server",
                "proxy",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server proxy`", stderr.getvalue())

    def test_main_remote_rejects_app_server_daemon_start_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "app-server",
                "daemon",
                "start",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server daemon start`", stderr.getvalue())

    def test_main_remote_rejects_app_server_daemon_bootstrap_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "app-server",
                "daemon",
                "bootstrap",
                "--remote-control",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server daemon bootstrap`", stderr.getvalue())

    def test_main_remote_rejects_app_server_daemon_subcommands_with_context(self):
        for daemon_subcommand in (
            "restart",
            "enable-remote-control",
            "disable-remote-control",
            "stop",
            "version",
            "pid-update-loop",
        ):
            stderr = io.StringIO()

            code = main(
                [
                    "--remote",
                    "ws://127.0.0.1:4500",
                    "app-server",
                    "daemon",
                    daemon_subcommand,
                ],
                stderr=stderr,
            )

            self.assertEqual(code, 2)
            self.assertIn(f"not `codex app-server daemon {daemon_subcommand}`", stderr.getvalue())

    def test_main_remote_auth_rejects_app_server_generate_json_schema(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app-server",
                "generate-json-schema",
                "--out",
                "out",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server generate-json-schema`", stderr.getvalue())

    def test_main_remote_auth_rejects_app_server_with_root_flags_and_daemon(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app-server",
                "--analytics-default-enabled",
                "daemon",
                "start",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server daemon start`", stderr.getvalue())

    def test_main_remote_auth_rejects_app_server_daemon_start_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app-server",
                "daemon",
                "start",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server daemon start`", stderr.getvalue())

    def test_main_remote_auth_rejects_app_server_daemon_bootstrap_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app-server",
                "daemon",
                "bootstrap",
                "--remote-control",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server daemon bootstrap`", stderr.getvalue())

    def test_main_remote_auth_rejects_app_server_daemon_subcommands_with_context(self):
        for daemon_subcommand in (
            "restart",
            "enable-remote-control",
            "disable-remote-control",
            "stop",
            "version",
            "pid-update-loop",
        ):
            stderr = io.StringIO()

            code = main(
                [
                    "--remote-auth-token-env",
                    "CODEX_REMOTE_AUTH_TOKEN",
                    "app-server",
                    "daemon",
                    daemon_subcommand,
                ],
                stderr=stderr,
            )

            self.assertEqual(code, 2)
            self.assertIn(f"not `codex app-server daemon {daemon_subcommand}`", stderr.getvalue())

    def test_main_remote_auth_rejects_app_server_proxy_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app-server",
                "proxy",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server proxy`", stderr.getvalue())

    def test_main_remote_auth_rejects_app_server_generate_ts_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app-server",
                "generate-ts",
                "--out",
                "out",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server generate-ts`", stderr.getvalue())

    def test_main_remote_auth_rejects_app_server_generate_internal_json_schema_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app-server",
                "generate-internal-json-schema",
                "--out",
                "out",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn(
            "not `codex app-server generate-internal-json-schema`", stderr.getvalue()
        )

    def test_main_remote_auth_rejects_app_server_with_root_flags_and_generate_ts(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app-server",
                "--strict-config",
                "generate-ts",
                "--out",
                "out",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app-server generate-ts`", stderr.getvalue())

    def test_main_remote_rejects_responses_api_proxy_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "responses-api-proxy",
                "--port",
                "9000",
                "--upstream-url",
                "https://example.com",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex responses-api-proxy`", stderr.getvalue())

    def test_main_remote_auth_rejects_responses_api_proxy_with_remote_auth_token_env_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "responses-api-proxy",
                "--port",
                "9000",
                "--upstream-url",
                "https://example.com",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex responses-api-proxy`", stderr.getvalue())

    def test_main_remote_auth_rejects_execpolicy_check_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "execpolicy",
                "check",
                "--rules",
                "policy.json",
                "--",
                "echo",
                "ok",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex execpolicy check`", stderr.getvalue())

    def test_main_remote_auth_rejects_execpolicy_check_with_preceding_help_flag(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "execpolicy",
                "--help",
                "check",
                "--rules",
                "policy.json",
                "--",
                "echo",
                "ok",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex execpolicy check`", stderr.getvalue())

    def test_main_remote_rejects_execpolicy_check_with_subcommand_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "execpolicy",
                "check",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex execpolicy check`", stderr.getvalue())

    def test_main_remote_rejects_execpolicy_check_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "execpolicy",
                "check",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex execpolicy check`", stderr.getvalue())

    def test_main_remote_auth_rejects_execpolicy_check_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "execpolicy",
                "check",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex execpolicy check`", stderr.getvalue())

    def test_main_remote_rejects_execpolicy_check_with_preceding_help_flag(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "execpolicy",
                "--help",
                "check",
                "--rules",
                "policy.json",
                "--",
                "echo",
                "ok",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex execpolicy check`", stderr.getvalue())

    def test_main_remote_rejects_cloud_with_help_before_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "cloud",
                "--help",
                "status",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex cloud`", stderr.getvalue())

    def test_main_remote_auth_rejects_cloud_with_help_before_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "cloud",
                "--help",
                "status",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex cloud`", stderr.getvalue())

    def test_main_remote_auth_rejects_stdio_to_uds(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "stdio-to-uds",
                "/tmp/codex.sock",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex stdio-to-uds`", stderr.getvalue())

    def test_main_remote_rejects_stdio_to_uds_with_path(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "stdio-to-uds",
                "/tmp/codex.sock",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex stdio-to-uds`", stderr.getvalue())

    def test_main_remote_rejects_exec_server(self):
        stderr = io.StringIO()

        code = main(["--remote", "ws://127.0.0.1:4500", "exec-server"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex exec-server`", stderr.getvalue())

    def test_main_remote_auth_rejects_exec_server(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "exec-server",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex exec-server`", stderr.getvalue())

    def test_main_remote_rejects_features_root_without_subcommand(self):
        stderr = io.StringIO()

        code = main(["--remote", "ws://127.0.0.1:4500", "features"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("not `codex features`", stderr.getvalue())

    def test_main_remote_rejects_review_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "review",
                "prompt",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex review`", stderr.getvalue())

    def test_main_remote_auth_rejects_review_with_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "review",
                "prompt",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex review`", stderr.getvalue())

    def test_main_remote_auth_rejects_remote_supported_root_commands(self):
        for command, expected_command in (
            ("doctor", "doctor"),
            ("login", "login"),
            ("logout", "logout"),
            ("mcp-server", "mcp-server"),
            ("cloud", "cloud"),
            ("sandbox", "sandbox"),
            ("app-server", "app-server"),
            ("update", "update"),
            ("completion", "completion"),
            ("responses-api-proxy", "responses-api-proxy"),
            ("app", "app"),
        ):
            with self.subTest(command=command):
                stderr = io.StringIO()

                code = main(["--remote", "ws://127.0.0.1:4500", command], stderr=stderr)

                self.assertEqual(code, 2)
                self.assertIn(f"not `codex {expected_command}`", stderr.getvalue())

    def test_main_remote_auth_rejects_remote_supported_root_commands_with_auth_token_env(self):
        for command, expected_command in (
            ("completion", "completion"),
            ("doctor", "doctor"),
            ("login", "login"),
            ("logout", "logout"),
            ("mcp-server", "mcp-server"),
            ("cloud", "cloud"),
            ("sandbox", "sandbox"),
            ("update", "update"),
            ("app-server", "app-server"),
            ("responses-api-proxy", "responses-api-proxy"),
            ("app", "app"),
        ):
            with self.subTest(command=command):
                stderr = io.StringIO()

                code = main(
                    [
                        "--remote-auth-token-env",
                        "CODEX_REMOTE_AUTH_TOKEN",
                        command,
                    ],
                    stderr=stderr,
                )

                self.assertEqual(code, 2)
                self.assertIn(f"not `codex {expected_command}`", stderr.getvalue())

    def test_main_remote_rejects_completion_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "completion",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex completion`", stderr.getvalue())

    def test_main_remote_auth_rejects_completion_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "completion",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex completion`", stderr.getvalue())

    def test_main_remote_rejects_remote_supported_root_commands_with_help(self):
        for command, expected_command in (
            ("doctor", "doctor"),
            ("login", "login"),
            ("logout", "logout"),
            ("cloud", "cloud"),
            ("sandbox", "sandbox"),
            ("app-server", "app-server"),
            ("update", "update"),
            ("responses-api-proxy", "responses-api-proxy"),
            ("completion", "completion"),
            ("mcp", "mcp"),
            ("plugin", "plugin"),
            ("app", "app"),
        ):
            with self.subTest(command=command):
                stderr = io.StringIO()

                code = main(
                    [
                        "--remote",
                        "ws://127.0.0.1:4500",
                        command,
                        "--help",
                    ],
                    stderr=stderr,
                )

                self.assertEqual(code, 2)
                self.assertIn(f"not `codex {expected_command}`", stderr.getvalue())

    def test_main_remote_auth_rejects_remote_supported_root_commands_with_help(self):
        for command, expected_command in (
            ("completion", "completion"),
            ("doctor", "doctor"),
            ("login", "login"),
            ("logout", "logout"),
            ("cloud", "cloud"),
            ("sandbox", "sandbox"),
            ("app-server", "app-server"),
            ("update", "update"),
            ("responses-api-proxy", "responses-api-proxy"),
            ("mcp-server", "mcp-server"),
            ("plugin", "plugin"),
            ("app", "app"),
        ):
            with self.subTest(command=command):
                stderr = io.StringIO()

                code = main(
                    [
                        "--remote-auth-token-env",
                        "CODEX_REMOTE_AUTH_TOKEN",
                        command,
                        "--help",
                    ],
                    stderr=stderr,
                )

                self.assertEqual(code, 2)
                self.assertIn(f"not `codex {expected_command}`", stderr.getvalue())

    def test_main_remote_rejects_update_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "update",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("`--remote ws://127.0.0.1:4500`", stderr.getvalue())

    def test_main_remote_auth_rejects_update_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "update",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("`--remote-auth-token-env`", stderr.getvalue())

    def test_main_remote_rejects_mcp_server_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp-server",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp-server`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_server_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp-server",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp-server`", stderr.getvalue())

    def test_main_remote_rejects_mcp_server_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp-server",
                "--help",
                "register",
                "--json",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp-server`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_server_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp-server",
                "--help",
                "register",
                "--json",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp-server`", stderr.getvalue())

    def test_main_remote_rejects_mcp_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_plugin_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_app_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "app",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app`", stderr.getvalue())

    def test_main_remote_auth_rejects_app_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "app",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex app`", stderr.getvalue())

    def test_main_remote_rejects_apply_with_task(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "apply",
                "task-123",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex apply`", stderr.getvalue())

    def test_main_remote_auth_rejects_apply_with_task(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "apply",
                "task-123",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex apply`", stderr.getvalue())

    def test_main_remote_rejects_apply_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "apply",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex apply`", stderr.getvalue())

    def test_main_remote_auth_rejects_apply_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "apply",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex apply`", stderr.getvalue())

    def test_main_remote_rejects_exec_with_prompt(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "exec",
                "hello",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex exec`", stderr.getvalue())

    def test_main_remote_rejects_responses_api_proxy_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "responses-api-proxy",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex responses-api-proxy`", stderr.getvalue())

    def test_main_remote_auth_rejects_responses_api_proxy_with_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "responses-api-proxy",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex responses-api-proxy`", stderr.getvalue())

    def test_main_remote_rejects_mcp_list_with_root_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "list",
                "--json",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_list_with_root_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "list",
                "--json",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_list_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "--help",
                "list",
                "--json",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_list_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "--help",
                "list",
                "--json",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_list_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "list",
                "--help",
                "--json",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_list_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "list",
                "--help",
                "--json",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_get_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "get",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_get_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "get",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_add_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "add",
                "demo",
                "--url",
                "https://example.com/mcp",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_add_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "add",
                "demo",
                "--url",
                "https://example.com/mcp",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_remove_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "remove",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_remove_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "remove",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_login_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "login",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_login_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "login",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_logout_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "logout",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_logout_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "logout",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_add_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "--help",
                "add",
                "demo",
                "--url",
                "https://example.com/mcp",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_add_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "--help",
                "add",
                "demo",
                "--url",
                "https://example.com/mcp",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_remove_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "--help",
                "remove",
                "demo",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_remove_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "--help",
                "remove",
                "demo",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_login_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "--help",
                "login",
                "demo",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_login_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "--help",
                "login",
                "demo",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_mcp_logout_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "mcp",
                "--help",
                "logout",
                "demo",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_auth_rejects_mcp_logout_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "mcp",
                "--help",
                "logout",
                "demo",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex mcp`", stderr.getvalue())

    def test_main_remote_rejects_plugin_marketplace_add_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "--help",
                "marketplace",
                "add",
                "owner/source",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_marketplace_add_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "--help",
                "marketplace",
                "add",
                "owner/source",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_marketplace_remove_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "--help",
                "marketplace",
                "remove",
                "market-1",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_marketplace_remove_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "--help",
                "marketplace",
                "remove",
                "market-1",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_marketplace_upgrade_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "--help",
                "marketplace",
                "upgrade",
                "market-1",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_marketplace_upgrade_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "--help",
                "marketplace",
                "upgrade",
                "market-1",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_marketplace_list_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "--help",
                "marketplace",
                "list",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_marketplace_list_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "--help",
                "marketplace",
                "list",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_add_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "add",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_add_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "add",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_marketplace_add_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "marketplace",
                "add",
                "owner/source",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_marketplace_add_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "marketplace",
                "add",
                "owner/source",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_remove_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "remove",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_remove_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "remove",
                "demo",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_marketplace_remove_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "marketplace",
                "remove",
                "market-1",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_marketplace_remove_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "marketplace",
                "remove",
                "market-1",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_marketplace_upgrade_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "marketplace",
                "upgrade",
                "market-1",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_marketplace_list_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "marketplace",
                "list",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_marketplace_list_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "marketplace",
                "list",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_marketplace_upgrade_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "marketplace",
                "upgrade",
                "market-1",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_list_with_root_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "list",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_list_with_root_context(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "list",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_list_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "--help",
                "list",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_list_with_preceding_help(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "--help",
                "list",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_rejects_plugin_list_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote",
                "ws://127.0.0.1:4500",
                "plugin",
                "list",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_main_remote_auth_rejects_plugin_list_with_help_after_subcommand(self):
        stderr = io.StringIO()

        code = main(
            [
                "--remote-auth-token-env",
                "CODEX_REMOTE_AUTH_TOKEN",
                "plugin",
                "list",
                "--help",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not `codex plugin`", stderr.getvalue())

    def test_remote_mode_rejection_messages_match_upstream(self):
        with self.assertRaisesRegex(CliParseError, "`--remote ws://localhost:4500`"):
            reject_remote_mode_for_subcommand("ws://localhost:4500", None, "remote-control")
        with self.assertRaisesRegex(CliParseError, "`--remote-auth-token-env`"):
            reject_remote_mode_for_subcommand(None, "CODEX_REMOTE_AUTH_TOKEN", "exec")

    def test_feature_toggles_known_features_generate_overrides(self):
        toggles = FeatureToggles(
            enable=("web_search_request",),
            disable=("unified_exec",),
        )

        self.assertEqual(
            toggles.to_overrides(),
            [
                "features.web_search_request=true",
                "features.unified_exec=false",
            ],
        )

    def test_feature_toggles_accept_removed_and_legacy_flags(self):
        self.assertEqual(
            FeatureToggles(enable=("use_linux_sandbox_bwrap",)).to_overrides(),
            ["features.use_linux_sandbox_bwrap=true"],
        )
        self.assertEqual(
            FeatureToggles(enable=("image_detail_original",)).to_overrides(),
            ["features.image_detail_original=true"],
        )

    def test_feature_toggles_unknown_feature_errors(self):
        with self.assertRaisesRegex(FeatureCliError, "Unknown feature flag: does_not_exist"):
            FeatureToggles(enable=("does_not_exist",)).to_overrides()

    def test_root_feature_toggles_are_folded_after_config_overrides(self):
        parsed = parse_args(
            [
                "-c",
                "features.unified_exec=true",
                "--disable",
                "unified_exec",
                "--enable",
                "web_search_request",
            ]
        )

        self.assertEqual(
            parsed.config_overrides_with_feature_toggles(),
            (
                "features.unified_exec=true",
                "features.web_search_request=true",
                "features.unified_exec=false",
            ),
        )
        parsed_overrides = parsed.parsed_config_overrides()
        self.assertEqual(parsed_overrides[-2].path, "features.web_search_request")
        self.assertIs(parsed_overrides[-2].value, True)
        self.assertEqual(parsed_overrides[-1].path, "features.unified_exec")
        self.assertIs(parsed_overrides[-1].value, False)

    def test_exec_inherits_feature_toggle_overrides(self):
        parsed = parse_args(["--enable", "web_search_request", "exec", "prompt"])

        self.assertEqual(parsed.exec_cli().config_overrides, ("features.web_search_request=true",))

    def test_exec_inherits_root_shared_options_like_upstream_main(self):
        parsed = parse_args(
            [
                "--image",
                "root.png",
                "--model",
                "gpt-5.2",
                "--sandbox",
                "workspace-write",
                "--add-dir",
                "root-extra",
                "exec",
                "--image",
                "exec.png",
                "--add-dir",
                "exec-extra",
                "summarize",
            ]
        )
        exec_cli = parsed.exec_cli()

        self.assertEqual(exec_cli.images, ("root.png", "exec.png"))
        self.assertEqual(exec_cli.model, "gpt-5.2")
        self.assertIs(exec_cli.sandbox, SandboxMode.WORKSPACE_WRITE)
        self.assertEqual(exec_cli.add_dir, ("root-extra", "exec-extra"))

    def test_main_review_alias_runs_exec_plan_preparation(self):
        stderr = io.StringIO()

        with patch.dict(os.environ, {"PYCODEX_EXEC_LOCAL_HTTP": "0"}):
            code = main(["review", "--commit", "123456789", "--title", "Fix"], stderr=stderr)

        self.assertEqual(code, 0)
        self.assertIn("prepared non-interactive review plan", stderr.getvalue())

    def test_main_review_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["review", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex review", stdout.getvalue())

    def test_main_exec_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["exec", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex exec", stdout.getvalue())

    def test_main_review_requires_review_target(self):
        stderr = io.StringIO()

        code = main(["review"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Specify --uncommitted", stderr.getvalue())

    def test_main_review_inherits_root_exec_shared_options(self):
        stderr = io.StringIO()

        with patch.dict(os.environ, {"PYCODEX_EXEC_LOCAL_HTTP": "0"}):
            code = main(
                [
                    "--model",
                    "gpt-5.2",
                    "--sandbox",
                    "workspace-write",
                    "review",
                    "--commit",
                    "123456789",
                    "--title",
                    "Fix",
                ],
                stderr=stderr,
            )

        self.assertEqual(code, 0)
        self.assertIn("prepared non-interactive review plan", stderr.getvalue())

    def test_main_completion_defaults_to_bash(self):
        stdout = io.StringIO()

        code = main(["completion"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("pycodex completion (bash)", stdout.getvalue())

    def test_main_completion_accepts_shell_option(self):
        stdout = io.StringIO()

        code = main(["completion", "--shell", "zsh"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("pycodex completion (zsh)", stdout.getvalue())

    def test_main_completion_accepts_short_shell_option(self):
        stdout = io.StringIO()

        code = main(["completion", "-s", "fish"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("# pycodex completion (fish)", stdout.getvalue())

    def test_main_completion_accepts_shell_option_with_equals(self):
        stdout = io.StringIO()

        code = main(["completion", "--shell=zsh"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("# pycodex completion (zsh)", stdout.getvalue())

    def test_main_completion_rejects_unsupported_shell(self):
        stderr = io.StringIO()

        code = main(["completion", "--shell", "unsupported-shell"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Unsupported shell 'unsupported-shell'", stderr.getvalue())

    def test_main_completion_unknown_argument(self):
        stderr = io.StringIO()

        code = main(["completion", "--mystery"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Unknown argument for completion: --mystery", stderr.getvalue())

    def test_main_completion_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["completion", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex completion", stdout.getvalue())

    def test_main_login_status_not_logged_in(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["login", "status"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 1)
        self.assertIn("Not logged in", stderr.getvalue())

    def test_main_login_status_api_key(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            auth_json = {
                "auth_mode": "apiKey",
                "OPENAI_API_KEY": "sk-test-key-12345",
            }
            (Path(tmpdir) / "auth.json").write_text(
                json.dumps(auth_json, indent=2),
                encoding="utf-8",
            )

            try:
                code = main(["login", "status"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("Logged in using an API key - sk-test-***12345", stderr.getvalue())

    def test_main_login_status_default_to_chatgpt_for_legacy_missing_auth_mode(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            auth_json = {
                "OPENAI_API_KEY": "",
                "tokens": {
                    "access_token": "x",
                    "refresh_token": "y",
                    "account_id": "acct",
                },
                "last_refresh": "2025-01-01T00:00:00Z",
            }
            (Path(tmpdir) / "auth.json").write_text(
                json.dumps(auth_json, indent=2),
                encoding="utf-8",
            )

            try:
                code = main(["login", "status"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("Logged in using ChatGPT", stderr.getvalue())

    def test_main_login_status_rejects_unknown_auth_mode(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            auth_json = {
                "auth_mode": "mystery-mode",
                "OPENAI_API_KEY": "sk-test",
            }
            (Path(tmpdir) / "auth.json").write_text(
                json.dumps(auth_json, indent=2),
                encoding="utf-8",
            )

            try:
                code = main(["login", "status"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn("Unknown auth_mode value", stderr.getvalue())

    def test_main_login_status_rejects_invalid_auth_json(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            (Path(tmpdir) / "auth.json").write_text("{{", encoding="utf-8")
            try:
                code = main(["login", "status"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn("Invalid auth file format.", stderr.getvalue())

    def test_main_login_status_agent_identity(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            auth_json = {
                "auth_mode": "agentIdentity",
                "agent_identity": "access-token-value",
            }
            (Path(tmpdir) / "auth.json").write_text(
                json.dumps(auth_json, indent=2),
                encoding="utf-8",
            )

            try:
                code = main(["login", "status"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("Logged in using access token", stderr.getvalue())

    def test_main_login_status_rejects_extra_positionals(self):
        stderr = io.StringIO()

        code = main(["login", "status", "unexpected"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("`status` does not accept extra login arguments.", stderr.getvalue())

    def test_main_login_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["login", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex login", stdout.getvalue())

    def test_main_login_status_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["login", "status", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex login status", stdout.getvalue())

    def test_main_login_prints_guidance_for_deprecated_api_key_flag(self):
        stderr = io.StringIO()

        code = main(["login", "--api-key", "abc"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("The --api-key flag is no longer supported.", stderr.getvalue())

    def test_main_login_defaults_to_chatgpt_login_flow(self):
        stderr = io.StringIO()

        with patch("pycodex.cli.parser.run_chatgpt_login", return_value=0) as chatgpt_login:
            code = main(["login"], stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(chatgpt_login.call_count, 1)
        self.assertIsNone(chatgpt_login.call_args.kwargs["issuer"])
        self.assertIsNone(chatgpt_login.call_args.kwargs["client_id"])

    def test_main_login_defaults_to_chatgpt_login_flow_with_experimental_overrides(self):
        stderr = io.StringIO()

        with patch("pycodex.cli.parser.run_chatgpt_login", return_value=0) as chatgpt_login:
            code = main(
                [
                    "login",
                    "--experimental_issuer",
                    "https://auth.example.com",
                    "--experimental_client-id",
                    "custom-client-id",
                ],
                stderr=stderr,
            )

        self.assertEqual(code, 0)
        self.assertEqual(chatgpt_login.call_count, 1)
        self.assertEqual(
            chatgpt_login.call_args.kwargs["issuer"],
            "https://auth.example.com",
        )
        self.assertEqual(
            chatgpt_login.call_args.kwargs["client_id"],
            "custom-client-id",
        )

    def test_main_login_defaults_to_not_implemented_chatgpt_flow(self):
        stderr = io.StringIO()

        with patch("pycodex.cli.login._CHATGPT_LOGIN_WAIT_SECONDS", 0), patch(
            "pycodex.cli.login.webbrowser.open", return_value=False
        ):
            code = main(["login"], stderr=stderr)

        self.assertEqual(code, 64)
        self.assertIn("Starting local login server on http://localhost:", stderr.getvalue())
        self.assertIn("login callback was not completed in time", stderr.getvalue())

    def test_main_login_rejects_double_credentials(self):
        stderr = io.StringIO()

        code = main(["login", "--with-api-key", "--with-access-token"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Choose one login credential source", stderr.getvalue())

    def test_main_login_device_auth(self):
        stderr = io.StringIO()

        with patch("pycodex.cli.parser._run_device_auth_login", return_value=0) as device_auth_call:
            code = main(["login", "--device-auth"], stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(device_auth_call.call_count, 1)
        self.assertEqual(stderr.getvalue(), "")

    def test_main_login_device_auth_with_experimental_overrides(self):
        stderr = io.StringIO()

        with patch("pycodex.cli.parser._run_device_auth_login", return_value=0) as device_auth_call:
            code = main(
                [
                    "login",
                    "--device-auth",
                    "--experimental_issuer",
                    "https://auth.example.local",
                    "--experimental_client-id",
                    "device-client-id",
                ],
                stderr=stderr,
            )

        self.assertEqual(code, 0)
        self.assertEqual(device_auth_call.call_count, 1)
        kwargs = device_auth_call.call_args.kwargs
        self.assertEqual(kwargs["issuer"], "https://auth.example.local")
        self.assertEqual(kwargs["client_id"], "device-client-id")

    def test_main_login_status_rejects_device_auth_flag(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["login", "status", "--device-auth"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn("`status` does not accept extra login arguments.", stderr.getvalue())

    def test_main_login_status_rejects_api_key_flags(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["login", "status", "--with-api-key"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn("`status` does not accept extra login arguments.", stderr.getvalue())

    def test_main_login_status_rejects_access_token_flags(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["login", "status", "--with-access-token"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn("`status` does not accept extra login arguments.", stderr.getvalue())

    def test_main_login_status_rejects_experimental_flags(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(
                    [
                        "login",
                        "status",
                        "--experimental_issuer",
                        "https://auth.example.com",
                        "--experimental_client-id",
                        "client-id",
                    ],
                    stderr=stderr,
                )
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn("`status` does not accept extra login arguments.", stderr.getvalue())

    def test_main_login_status_rejects_double_credentials(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(
                    ["login", "status", "--with-api-key", "--with-access-token"],
                    stderr=stderr,
                )
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn("`status` does not accept extra login arguments.", stderr.getvalue())

    def test_main_login_status_accepts_double_credentials_with_status_after(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(
                    ["login", "--with-api-key", "--with-access-token", "status"],
                    stderr=stderr,
                )
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 1)
        self.assertIn("Not logged in", stderr.getvalue())

    def test_main_login_status_accepts_with_api_key_before_status(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["login", "--with-api-key", "status"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 1)
        self.assertIn("Not logged in", stderr.getvalue())

    def test_main_login_status_help_with_preceding_flag(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["login", "--with-api-key", "status", "--help"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex login status", stdout.getvalue())

    def test_main_login_deprecated_api_key_with_status_value_rejected(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["login", "--api-key", "status"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn("The --api-key flag is no longer supported.", stderr.getvalue())

    def test_main_login_status_rejects_deprecated_api_key_flag(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["login", "status", "--api-key", "abc"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 2)
        self.assertIn("`status` does not accept extra login arguments.", stderr.getvalue())

    def test_main_login_rejects_device_auth_with_access_token_mode(self):
        stderr = io.StringIO()

        code = main(["login", "--device-auth", "--with-access-token"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Choose one login credential source", stderr.getvalue())

    def test_main_login_rejects_device_auth_with_api_key_mode(self):
        stderr = io.StringIO()

        code = main(["login", "--device-auth", "--with-api-key"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Choose one login credential source", stderr.getvalue())

    def test_oauth_callback_error_message_for_missing_codex_entitlement(self):
        from pycodex.cli.login import _oauth_callback_error_message

        self.assertEqual(
            _oauth_callback_error_message("access_denied", "workspace does not have missing_codex_entitlement feature"),
            "Codex is not enabled for your workspace. Contact your workspace administrator to request access to Codex.",
        )

    def test_oauth_callback_error_message_preserves_error_description(self):
        from pycodex.cli.login import _oauth_callback_error_message

        self.assertEqual(
            _oauth_callback_error_message("access_denied", "user canceled"),
            "Sign-in failed: user canceled",
        )

    def test_extract_auth_claims_from_jwt(self):
        import base64

        from pycodex.cli.login import _extract_auth_claims_from_jwt

        claims = {
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "acct-123",
                "plan": "plus",
            },
        }
        payload = json.dumps(claims).encode()
        encoded_payload = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        token = f"header.{encoded_payload}.sig"
        self.assertEqual(
            _extract_auth_claims_from_jwt(token),
            {
                "chatgpt_account_id": "acct-123",
                "plan": "plus",
            },
        )

    def test_extract_auth_claims_from_jwt_returns_empty_on_bad_token(self):
        from pycodex.cli.login import _extract_auth_claims_from_jwt

        self.assertEqual(_extract_auth_claims_from_jwt("bad.token"), {})

    def test_main_login_requires_stdin_for_api_key_flag(self):
        stderr = io.StringIO()

        code = main(["login", "--with-api-key"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("--with-api-key requires value from stdin.", stderr.getvalue())

    def test_main_login_with_api_key_terminal_stdin_fails(self):
        stderr = io.StringIO()

        code = main(
            ["login", "--with-api-key"],
            stdin="sk-xyz\n",
            stdin_is_terminal=True,
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn(
            "expects the API key on stdin. Try piping it, e.g. `printenv OPENAI_API_KEY | codex login --with-api-key`.",
            stderr.getvalue(),
        )

    def test_main_login_with_access_token_terminal_stdin_fails(self):
        stderr = io.StringIO()

        code = main(
            ["login", "--with-access-token"],
            stdin="access-token\n",
            stdin_is_terminal=True,
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn(
            "expects the access token on stdin. Try piping it, e.g. `printenv CODEX_ACCESS_TOKEN | codex login --with-access-token`.",
            stderr.getvalue(),
        )

    def test_main_login_with_api_key_reads_stdin(self):
        stderr = io.StringIO()
        auth_payload: dict[str, object] = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir

            try:
                code = main(["login", "--with-api-key"], stdin="sk-xyz\n", stderr=stderr)
                auth_payload = json.loads(
                    (Path(tmpdir) / "auth.json").read_text(encoding="utf-8")
                )
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("Successfully logged in", stderr.getvalue())
        self.assertEqual(auth_payload.get("OPENAI_API_KEY"), "sk-xyz")

    def test_main_login_with_api_key_empty_stdin_rejected(self):
        stderr = io.StringIO()

        code = main(["login", "--with-api-key"], stdin="\n", stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("No API key provided via stdin.", stderr.getvalue())

    def test_main_login_with_access_token_reads_stdin(self):
        stderr = io.StringIO()
        auth_payload: dict[str, object] = {}
        valid_access_token = "eyJhbGciOiAibm9uZSJ9.eyJzdWIiOiAiYWNjZXNzLXRva2VuIn0.c2lnbmF0dXJl"
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir

            try:
                code = main(
                    ["login", "--with-access-token"],
                    stdin=f"{valid_access_token}\n",
                    stderr=stderr,
                )
                auth_payload = json.loads(
                    (Path(tmpdir) / "auth.json").read_text(encoding="utf-8")
                )
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("Successfully logged in", stderr.getvalue())
        self.assertEqual(auth_payload.get("agent_identity"), valid_access_token)

    def test_main_login_with_access_token_empty_stdin_rejected(self):
        stderr = io.StringIO()

        code = main(["login", "--with-access-token"], stdin="\n", stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("No access token provided via stdin.", stderr.getvalue())

    def test_main_login_with_invalid_access_token_rejected(self):
        stderr = io.StringIO()

        code = main(["login", "--with-access-token"], stdin="not-a-jwt-token", stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn(
            "Error logging in with access token: invalid access token format.",
            stderr.getvalue(),
        )

    def test_main_logout_no_args(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["logout"], stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("Not logged in", stderr.getvalue())

    def test_parse_logout_disallows_args(self):
        with self.assertRaisesRegex(CliParseError, "unexpected argument 'unexpected' for `codex logout`"):
            parse_args(["logout", "unexpected"])

    def test_main_logout_removes_auth_file(self):
        stderr = io.StringIO()
        removed = False
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            auth_path = Path(tmpdir) / "auth.json"
            auth_path.write_text(json.dumps({"auth_mode": "apiKey", "OPENAI_API_KEY": "sk-test"}), encoding="utf-8")
            try:
                code = main(["logout"], stderr=stderr)
                removed = not auth_path.exists()
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("Successfully logged out", stderr.getvalue())
        self.assertTrue(removed)

    def test_main_logout_rejects_unknown_arg(self):
        stderr = io.StringIO()

        code = main(["logout", "unexpected"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("unexpected argument 'unexpected' for `codex logout`", stderr.getvalue())

    def test_main_logout_help_does_not_logout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        logout_retained = False

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            Path(tmpdir, "auth.json").write_text(json.dumps({"auth_mode": "apiKey"}), encoding="utf-8")
            try:
                code = main(["logout", "--help"], stdout=stdout, stderr=stderr)
                logout_retained = Path(tmpdir, "auth.json").exists()
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex logout", stdout.getvalue())
        self.assertTrue(logout_retained)

    def test_main_update_no_args(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(["update"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertIn(
            "update command is not implemented in this Python port yet.",
            stdout.getvalue(),
        )

    def test_main_update_help(self):
        stdout = io.StringIO()

        code = main(["update", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex update [OPTIONS]", stdout.getvalue())

    def test_main_update_rejects_unknown_arg(self):
        stderr = io.StringIO()

        code = main(["update", "now"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Unknown argument for update", stderr.getvalue())

    def test_main_doctor_reports_status(self):
        stdout = io.StringIO()

        with patch("pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"), patch(
            "pycodex.cli.parser.doctor_terminal_check",
            return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
        ):
            code = main(["doctor"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("doctor:", stdout.getvalue())

    def test_main_doctor_json_includes_version_cache_details(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            version_file = Path(tmpdir) / "version.json"
            version_file.write_text(
                json.dumps({"latest_version": "1.2.3", "dismissed_version": "1.2.0"}),
                encoding="utf-8",
            )
            (Path(tmpdir) / "config.toml").write_text("check_for_update_on_startup = false\n", encoding="utf-8")
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=None), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.2.4"
                ), patch(
                    "pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False
                ), patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
                ):
                    code = main(["doctor", "--json"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        updates = payload["checks"]["updates.status"]
        self.assertIsInstance(updates["durationMs"], int)
        self.assertEqual(updates["details"]["check for update on startup"], "false")
        self.assertEqual(updates["details"]["update action"], "manual or unknown")
        self.assertEqual(updates["details"]["version cache"], str(version_file))
        self.assertEqual(updates["details"]["cached latest version"], "1.2.3")
        self.assertEqual(updates["details"]["dismissed version"], "1.2.0")
        self.assertEqual(updates["details"]["latest version"], "1.2.4")
        self.assertEqual(updates["details"]["latest version status"], "newer version is available")

    def test_main_doctor_json_warns_on_latest_version_probe_error(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=None), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", side_effect=RuntimeError("offline")
                ), patch(
                    "pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False
                ), patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
                ):
                    code = main(["doctor", "--json"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["checks"]["updates.status"]["status"], "warning")
        self.assertEqual(payload["checks"]["updates.status"]["details"]["latest version probe"], "offline")

    def test_main_doctor_json_includes_npm_root_mismatch_remediation(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=UpdateAction.NPM_GLOBAL_LATEST), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"
                ), patch(
                    "pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=True
                ), patch(
                    "pycodex.cli.doctor_updates.npm_global_root_check",
                    return_value=NpmRootCheck.mismatch(Path("running-pkg"), Path("npm-root") / "@openai" / "codex"),
                ) as npm_root_check:
                    code = main(["doctor", "--json"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        payload = json.loads(stdout.getvalue())
        updates = payload["checks"]["updates.status"]
        self.assertEqual(code, 1)
        self.assertEqual(payload["overallStatus"], "fail")
        self.assertEqual(npm_root_check.call_count, 2)
        self.assertNotIn("summary", payload)
        self.assertNotIn("codex_home", payload["checks"])
        self.assertNotIn("environment", payload["checks"])
        self.assertNotIn("runtime.python", payload["checks"])
        self.assertEqual(updates["status"], "fail")
        self.assertEqual(updates["summary"], "update would target a different npm install")
        self.assertEqual(updates["details"]["update action"], "npm install -g @openai/codex")
        self.assertEqual(updates["details"]["running package root"], str(Path("running-pkg")))
        self.assertEqual(updates["details"]["npm package root"], str(Path("npm-root") / "@openai" / "codex"))
        self.assertIn("Fix PATH or npm prefix", updates["remediation"])
        installation = payload["checks"]["installation"]
        self.assertEqual(installation["status"], "fail")
        self.assertEqual(installation["summary"], "npm install -g @openai/codex would update a different install")
        self.assertEqual(installation["details"]["running package root"], str(Path("running-pkg")))
        self.assertEqual(installation["details"]["npm package root"], str(Path("npm-root") / "@openai" / "codex"))
        self.assertIn("Fix PATH or npm prefix", installation["remediation"])

    def test_main_doctor_json_routes_latest_probe_by_detected_update_action(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            seen: list[UpdateAction | None] = []

            def fake_fetch(action):
                seen.append(action)
                return "1.0.0"

            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=UpdateAction.BREW_UPGRADE), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", side_effect=fake_fetch
                ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False), patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
                ):
                    code = main(["doctor", "--json"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(seen, [UpdateAction.BREW_UPGRADE])
        self.assertEqual(payload["checks"]["updates.status"]["details"]["update action"], "brew upgrade --cask codex")

    def test_main_doctor_json_includes_installation_check(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=None), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"
                ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False), patch(
                    "pycodex.cli.parser.doctor_installation_check",
                    return_value=DoctorUpdateCheck(
                        status="ok",
                        summary="installation looks consistent",
                        details=("install context: other", "managed by npm: false"),
                    ),
                ), patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
                ):
                    code = main(["doctor", "--json"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["checks"]["installation"]["summary"], "installation looks consistent")
        self.assertEqual(payload["checks"]["installation"]["details"]["install context"], "other")

    def test_main_doctor_json_includes_system_check(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=None), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"
                ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False), patch(
                    "pycodex.cli.parser.doctor_system_check",
                    return_value=DoctorUpdateCheck(
                        status="ok",
                        summary="OS language en-US",
                        details=("os: TestOS", "os language: en-US"),
                    ),
                ), patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
                ):
                    code = main(["doctor", "--json"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["checks"]["system.environment"]["summary"], "OS language en-US")
        self.assertEqual(payload["checks"]["system.environment"]["details"]["os"], "TestOS")

    def test_main_doctor_json_includes_terminal_check(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=None), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"
                ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False), patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(
                        status="ok",
                        summary="terminal metadata was detected",
                        details=("terminal: unknown", "color output: enabled"),
                    ),
                ) as terminal_check:
                    code = main(["doctor", "--json", "--no-color"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(terminal_check.call_args.kwargs["no_color_flag"])
        self.assertEqual(payload["checks"]["terminal.env"]["summary"], "terminal metadata was detected")
        self.assertEqual(payload["checks"]["terminal.env"]["details"]["terminal"], "unknown")

    def test_main_doctor_json_includes_runtime_check(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=None), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"
                ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False), patch(
                    "pycodex.cli.parser.doctor_runtime_check",
                    return_value=DoctorUpdateCheck(
                        status="ok",
                        summary="running local build on test-arch",
                        details=("version: test", "platform: test-arch"),
                    ),
                ), patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
                ):
                    code = main(["doctor", "--json"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["checks"]["runtime.provenance"]["summary"], "running local build on test-arch")
        self.assertEqual(payload["checks"]["runtime.provenance"]["details"]["platform"], "test-arch")
        self.assertIsInstance(payload["checks"]["runtime.provenance"]["durationMs"], int)

    def test_main_doctor_json_includes_search_check(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=None), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"
                ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False), patch(
                    "pycodex.cli.parser.doctor_search_check",
                    return_value=DoctorUpdateCheck(
                        status="ok",
                        summary="search is OK (system)",
                        details=("search command: rg", "search provider: system"),
                    ),
                ), patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
                ):
                    code = main(["doctor", "--json"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["checks"]["runtime.search"]["summary"], "search is OK (system)")
        self.assertEqual(payload["checks"]["runtime.search"]["details"]["search provider"], "system")

    def test_main_doctor_json_includes_background_server_check_with_rust_id(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=None), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"
                ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False), patch(
                    "pycodex.cli.parser.doctor_background_server_check",
                    return_value=DoctorUpdateCheck(
                        status="ok",
                        summary="background server is not running",
                        details=("status: not running",),
                    ),
                ), patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
                ):
                    code = main(["doctor", "--json"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["checks"]["app_server.status"]["summary"], "background server is not running")
        self.assertNotIn("app-server.status", payload["checks"])

    def test_main_doctor_json_config_failure_uses_rust_fallback_check_set(self):
        stdout = io.StringIO()
        with patch("pycodex.cli.parser.find_codex_home", side_effect=RuntimeError("home missing")), patch(
            "pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False
        ):
            code = main(["doctor", "--json"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        checks = payload["checks"]
        self.assertEqual(code, 1)
        self.assertEqual(payload["overallStatus"], "fail")
        self.assertEqual(checks["config.load"]["status"], "fail")
        self.assertIsInstance(checks["config.load"]["durationMs"], int)
        self.assertEqual(checks["config.load"]["summary"], "config could not be loaded")
        self.assertEqual(
            checks["config.load"]["remediation"],
            "Fix the reported config error, then rerun codex doctor.",
        )
        self.assertEqual(checks["config.load"]["notes"], ["home missing"])
        self.assertEqual(checks["state.paths"]["status"], "warning")
        self.assertEqual(
            checks["network.provider_reachability"]["details"]["reachability mode"],
            "ChatGPT auth",
        )
        self.assertIn("network.env", checks)
        self.assertIn("terminal.env", checks)
        self.assertIn("git.environment", checks)
        self.assertIn("network.provider_reachability", checks)
        self.assertNotIn("auth.credentials", checks)
        self.assertNotIn("sandbox.helpers", checks)
        self.assertNotIn("terminal.title", checks)
        self.assertNotIn("updates.status", checks)
        self.assertNotIn("mcp.config", checks)
        self.assertNotIn("network.websocket_reachability", checks)
        self.assertNotIn("app_server.status", checks)
        self.assertNotIn("state.rollout_db_parity", checks)

    def test_main_doctor_json_config_failure_keeps_resolved_state_ok(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            with patch("pycodex.cli.parser.find_codex_home", return_value=codex_home), patch(
                "pycodex.cli.parser.read_toml_mapping", side_effect=RuntimeError("broken config")
            ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False):
                code = main(["doctor", "--json"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        checks = payload["checks"]
        self.assertEqual(code, 1)
        self.assertEqual(checks["config.load"]["status"], "fail")
        self.assertEqual(checks["config.load"]["notes"], ["broken config"])
        self.assertEqual(
            checks["config.load"]["remediation"],
            "Fix the reported config error, then rerun codex doctor.",
        )
        self.assertEqual(checks["state.paths"]["status"], "ok")
        self.assertEqual(checks["state.paths"]["summary"], "CODEX_HOME was resolved without config")
        self.assertEqual(checks["state.paths"]["details"]["CODEX_HOME"], str(codex_home))

    def test_main_doctor_summary_returns_nonzero_on_fail(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=UpdateAction.NPM_GLOBAL_LATEST), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"
                ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=True), patch(
                    "pycodex.cli.doctor_updates.npm_global_root_check",
                    return_value=NpmRootCheck.mismatch(Path("running-pkg"), Path("npm-root") / "@openai" / "codex"),
                ):
                    code = main(["doctor", "--summary"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 1)
        self.assertIn("doctor: fail", stdout.getvalue())

    def test_main_doctor_summary_counts_warning_status_as_warning(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=None), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"
                ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False), patch(
                    "pycodex.cli.parser.doctor_search_check",
                    return_value=DoctorUpdateCheck(status="warning", summary="search warning", details=()),
                ), patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
                ):
                    code = main(["doctor", "--summary"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("doctor: warn", stdout.getvalue())

    def test_main_doctor_all_requests_installation_path_details(self):
        previous = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                with patch("pycodex.cli.doctor_updates.detect_update_action", return_value=None), patch(
                    "pycodex.cli.doctor_updates.fetch_latest_version", return_value="1.0.0"
                ), patch("pycodex.cli.doctor_updates.doctor_managed_by_npm", return_value=False), patch(
                    "pycodex.cli.parser.doctor_installation_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="installation looks consistent", details=()),
                ) as installation_check, patch(
                    "pycodex.cli.parser.doctor_terminal_check",
                    return_value=DoctorUpdateCheck(status="ok", summary="terminal metadata was detected", details=()),
                ):
                    code = main(["doctor", "--all"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertTrue(installation_check.call_args.kwargs["show_details"])

    def test_main_sandbox_requires_command(self):
        stderr = io.StringIO()

        code = main(["sandbox", "--permissions-profile", "default", "--cd", "."], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("sandbox command not provided", stderr.getvalue())

    def test_main_exec_server_prints_config(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(["exec-server", "--listen", "127.0.0.1:8080"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertIn("pycodex: exec-server config:", stdout.getvalue())
        self.assertIn("exec-server is not fully implemented", stderr.getvalue())

    def test_main_exec_server_allows_stdio_listen(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(["exec-server", "--listen", "stdio://"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertIn('"listen": "stdio://"', stdout.getvalue())

    def test_main_app_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["app", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex app [OPTIONS] [PATH]", stdout.getvalue())

    def test_main_exec_server_rejects_listen_with_remote(self):
        stderr = io.StringIO()

        code = main(
            [
                "exec-server",
                "--listen",
                "127.0.0.1:8080",
                "--remote",
                "ws://127.0.0.1:4500",
                "--environment-id",
                "env-1",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn(
            "--listen cannot be used with --remote.",
            stderr.getvalue(),
        )

    def test_main_exec_server_requires_access_token_for_agent_identity_auth(self):
        previous_token = os.environ.get("CODEX_ACCESS_TOKEN")
        if previous_token is not None:
            os.environ.pop("CODEX_ACCESS_TOKEN")

        stderr = io.StringIO()
        try:
            code = main(
                [
                    "exec-server",
                    "--remote",
                    "ws://127.0.0.1:4500",
                    "--environment-id",
                    "env-1",
                    "--use-agent-identity-auth",
                ],
                stderr=stderr,
            )
        finally:
            if previous_token is None:
                os.environ.pop("CODEX_ACCESS_TOKEN", None)
            else:
                os.environ["CODEX_ACCESS_TOKEN"] = previous_token

        self.assertEqual(code, 2)
        self.assertIn(
            "CODEX_ACCESS_TOKEN is required when --use-agent-identity-auth is set.",
            stderr.getvalue(),
        )

    def test_main_exec_allows_strict_config(self):
        stderr = io.StringIO()

        class SuccessResult:
            ok = True
            exit_code = 0
            error_message = None

        with patch("pycodex.cli.parser.local_http_exec_enabled", return_value=False), patch(
            "pycodex.cli.parser.core_exec_enabled", return_value=False
        ), patch("pycodex.cli.parser.remote_exec_session_connect_and_run", return_value=SuccessResult()):
            code = main(["--strict-config", "exec", "--full-auto", "prompt"], stderr=stderr, stdin="")

        self.assertEqual(code, 0)
        self.assertIn("prepared non-interactive exec plan", stderr.getvalue())

    def test_main_rejects_strict_config_for_unsupported_subcommand(self):
        stderr = io.StringIO()

        code = main(["--strict-config", "login", "status"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("`--strict-config` is not supported for `codex login`", stderr.getvalue())

    def test_main_allows_strict_config_for_app_server_root(self):
        stderr = io.StringIO()

        code = main(["--strict-config", "app-server"], stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")

    def test_main_rejects_strict_config_for_app_server_proxy(self):
        stderr = io.StringIO()

        code = main(["--strict-config", "app-server", "proxy"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn(
            "`--strict-config` is not supported for `codex app-server proxy`",
            stderr.getvalue(),
        )

    def test_main_rejects_strict_config_for_app_server_subcommand(self):
        stderr = io.StringIO()

        code = main(["--strict-config", "app-server", "daemon", "start"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn(
            "`--strict-config` is not supported for `codex app-server daemon start`",
            stderr.getvalue(),
        )

    def test_main_rejects_strict_config_for_remote_control_subcommands(self):
        stderr = io.StringIO()
        for command_args, expected in (
            (["remote-control"], "codex remote-control"),
            (["remote-control", "--json"], "codex remote-control"),
            (["remote-control", "--json", "start"], "codex remote-control start"),
            (["remote-control", "start", "--json"], "codex remote-control start"),
            (["remote-control", "start"], "codex remote-control start"),
            (["remote-control", "stop"], "codex remote-control stop"),
        ):
            with self.subTest(command_args=command_args):
                stderr = io.StringIO()
                code = main(["--strict-config", *command_args], stderr=stderr)
                self.assertEqual(code, 2)
                self.assertIn(
                    f"`--strict-config` is not supported for `{expected}`",
                    stderr.getvalue(),
                )

    def test_main_rejects_strict_config_for_app_server_all_daemon_subcommands(self):
        for daemon_subcommand in (
            "start",
            "restart",
            "stop",
            "enable-remote-control",
            "disable-remote-control",
            "version",
            "pid-update-loop",
            "bootstrap",
        ):
            with self.subTest(daemon_subcommand=daemon_subcommand):
                stderr = io.StringIO()
                code = main(
                    ["--strict-config", "app-server", "daemon", daemon_subcommand],
                    stderr=stderr,
                )
                self.assertEqual(code, 2)
                self.assertIn(
                    f"`--strict-config` is not supported for `codex app-server daemon {daemon_subcommand}`",
                    stderr.getvalue(),
                )

    def test_main_rejects_strict_config_for_app_server_allows_root_flags_for_daemon(self):
        stderr = io.StringIO()

        code = main(
            [
                "--strict-config",
                "app-server",
                "--listen",
                "stdio://",
                "--remote-control",
                "daemon",
                "start",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("`--strict-config` is not supported for `codex app-server daemon start`", stderr.getvalue())

    def test_main_rejects_strict_config_for_app_server_generate_ts_with_root_options(self):
        stderr = io.StringIO()

        code = main(
            [
                "--strict-config",
                "app-server",
                "--listen",
                "stdio://",
                "--ws-auth",
                "capability-token",
                "--ws-token-file",
                "/tmp/token",
                "generate-ts",
                "--out",
                "out",
            ],
            stderr=stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn(
            "`--strict-config` is not supported for `codex app-server generate-ts`",
            stderr.getvalue(),
        )

    def test_main_exec_reads_stdin_prompt_when_no_prompt_argument(self):
        stderr = io.StringIO()

        class SuccessResult:
            ok = True
            exit_code = 0
            error_message = None

        with patch("pycodex.cli.parser.local_http_exec_enabled", return_value=False), patch(
            "pycodex.cli.parser.core_exec_enabled", return_value=False
        ), patch(
            "pycodex.cli.parser.remote_exec_session_connect_and_run",
            return_value=SuccessResult(),
        ):
            code = main(["exec"], stdin="Summarize this\n", stderr=stderr)

        self.assertEqual(code, 0)
        self.assertIn("prepared non-interactive exec plan", stderr.getvalue())

    def test_main_exec_dash_reads_forced_stdin_prompt(self):
        stderr = io.StringIO()

        class SuccessResult:
            ok = True
            exit_code = 0
            error_message = None

        with patch("pycodex.cli.parser.local_http_exec_enabled", return_value=False), patch(
            "pycodex.cli.parser.core_exec_enabled", return_value=False
        ), patch(
            "pycodex.cli.parser.remote_exec_session_connect_and_run",
            return_value=SuccessResult(),
        ):
            code = main(["exec", "-"], stdin="Summarize this\n", stderr=stderr)

        self.assertEqual(code, 0)
        self.assertIn("prepared non-interactive exec plan", stderr.getvalue())

    def test_main_exec_enforces_trusted_directory_gate_before_runtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "not-a-repo"
            project.mkdir()
            with patch.dict(os.environ, {"PYCODEX_EXEC_LOCAL_HTTP": "0"}):
                with patch("pycodex.exec.config_plan.get_git_repo_root", return_value=None):
                    with patch(
                        "pycodex.cli.parser.remote_exec_session_connect_and_run",
                        side_effect=AssertionError("runtime should not start for untrusted cwd"),
                    ):
                        stderr = io.StringIO()
                        code = main(["exec", "--cd", str(project), "prompt"], stderr=stderr, stdin="")

        self.assertEqual(code, 2)
        self.assertIn(
            "Not inside a trusted directory and --skip-git-repo-check was not specified.",
            stderr.getvalue(),
        )

    def test_main_exec_prepares_noninteractive_plan(self):
        stderr = io.StringIO()

        class SuccessResult:
            ok = True
            exit_code = 0
            error_message = None

        with patch("pycodex.cli.parser.local_http_exec_enabled", return_value=False), patch(
            "pycodex.cli.parser.core_exec_enabled", return_value=False
        ), patch(
            "pycodex.cli.parser.remote_exec_session_connect_and_run",
            return_value=SuccessResult(),
        ):
            code = main(["exec", "--full-auto", "prompt"], stderr=stderr, stdin="")

        self.assertEqual(code, 0)
        self.assertIn("prepared non-interactive exec plan", stderr.getvalue())

    def test_main_exec_with_profile_triggers_personality_migration_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            read_call_count = 0
            bootstrap_configs = []

            class SuccessResult:
                ok = True
                exit_code = 0
                error_message = None

            def fake_read_toml_mapping(_path: Path) -> dict[str, object]:
                nonlocal read_call_count
                read_call_count += 1
                if read_call_count == 1:
                    return {}
                return {"personality": "pragmatic"}

            def fake_build_bootstrap_plan(
                _exec_cli: object,
                *,
                config_toml: dict[str, object],
            ) -> object:
                bootstrap_configs.append(dict(config_toml))
                return SimpleNamespace(config_cwd=codex_home)

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "PYCODEX_EXEC_CORE": "0",
                },
            ):
                with patch("pycodex.cli.parser.read_toml_mapping", side_effect=fake_read_toml_mapping) as read_toml, patch(
                    "pycodex.cli.parser.maybe_migrate_personality",
                    return_value=PersonalityMigrationStatus.APPLIED,
                ) as migrate, patch(
                    "pycodex.cli.parser.build_exec_config_bootstrap_plan",
                    side_effect=fake_build_bootstrap_plan,
                ), patch(
                    "pycodex.cli.parser.prepare_exec_run_plan",
                    return_value=SimpleNamespace(prompt_summary=()),
                ), patch(
                    "pycodex.cli.parser.ensure_exec_trusted_directory"
                ), patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("local", object(), codex_home),
                ), patch(
                    "pycodex.cli.parser._build_exec_session_config",
                    return_value=SimpleNamespace(),
                ), patch(
                    "pycodex.cli.parser._build_noninteractive_exec_event_processor",
                    return_value=SimpleNamespace(),
                ), patch(
                    "pycodex.cli.parser.remote_exec_session_connect_and_run",
                    return_value=SuccessResult(),
                ):
                    code = main(["exec", "--profile", "work", "hello"], stderr=io.StringIO(), stdin="")

        self.assertEqual(code, 0)
        self.assertEqual(read_toml.call_count, 2)
        self.assertEqual(len(bootstrap_configs), 1)
        self.assertEqual(bootstrap_configs[0].get("personality"), "pragmatic")
        migrate.assert_called_once_with(codex_home, {}, override_profile="work")
        self.assertEqual(migrate.call_args[0][1], {})

    def test_main_exec_without_migration_applied_uses_original_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            bootstrap_configs = []

            class SuccessResult:
                ok = True
                exit_code = 0
                error_message = None

            def fake_read_toml_mapping(_path: Path) -> dict[str, object]:
                return {"personality": "existing"}

            def fake_build_bootstrap_plan(
                _exec_cli: object,
                *,
                config_toml: dict[str, object],
            ) -> object:
                bootstrap_configs.append(dict(config_toml))
                return SimpleNamespace(config_cwd=codex_home)

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "PYCODEX_EXEC_CORE": "0",
                },
            ):
                with patch(
                    "pycodex.cli.parser.read_toml_mapping",
                    side_effect=fake_read_toml_mapping,
                ) as read_toml, patch(
                    "pycodex.cli.parser.maybe_migrate_personality",
                    return_value=PersonalityMigrationStatus.SKIPPED_NO_SESSIONS,
                ) as migrate, patch(
                    "pycodex.cli.parser.build_exec_config_bootstrap_plan",
                    side_effect=fake_build_bootstrap_plan,
                ), patch(
                    "pycodex.cli.parser.prepare_exec_run_plan",
                    return_value=SimpleNamespace(prompt_summary=()),
                ), patch(
                    "pycodex.cli.parser.ensure_exec_trusted_directory"
                ), patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("local", object(), codex_home),
                ), patch(
                    "pycodex.cli.parser._build_exec_session_config",
                    return_value=SimpleNamespace(),
                ), patch(
                    "pycodex.cli.parser._build_noninteractive_exec_event_processor",
                    return_value=SimpleNamespace(),
                ), patch(
                    "pycodex.cli.parser.remote_exec_session_connect_and_run",
                    return_value=SuccessResult(),
                ):
                    code = main(["exec", "hello"], stderr=io.StringIO(), stdin="")

        self.assertEqual(code, 0)
        self.assertEqual(read_toml.call_count, 1)
        self.assertEqual(len(bootstrap_configs), 1)
        self.assertEqual(bootstrap_configs[0].get("personality"), "existing")
        migrate.assert_called_once_with(codex_home, {"personality": "existing"}, override_profile=None)

    def test_main_review_with_profile_triggers_personality_migration_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            read_call_count = 0
            bootstrap_configs = []

            class SuccessResult:
                ok = True
                exit_code = 0
                error_message = None

            def fake_read_toml_mapping(_path: Path) -> dict[str, object]:
                nonlocal read_call_count
                read_call_count += 1
                if read_call_count == 1:
                    return {}
                return {"personality": "pragmatic"}

            def fake_build_bootstrap_plan(
                _exec_cli: object,
                *,
                config_toml: dict[str, object],
            ) -> object:
                bootstrap_configs.append(dict(config_toml))
                return SimpleNamespace(config_cwd=codex_home)

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "PYCODEX_EXEC_CORE": "0",
                },
            ):
                with patch(
                    "pycodex.cli.parser.read_toml_mapping",
                    side_effect=fake_read_toml_mapping,
                ) as read_toml, patch(
                    "pycodex.cli.parser.maybe_migrate_personality",
                    return_value=PersonalityMigrationStatus.APPLIED,
                ) as migrate, patch(
                    "pycodex.cli.parser.build_exec_config_bootstrap_plan",
                    side_effect=fake_build_bootstrap_plan,
                ), patch(
                    "pycodex.cli.parser.prepare_exec_run_plan",
                    return_value=SimpleNamespace(prompt_summary=()),
                ), patch(
                    "pycodex.cli.parser.ensure_exec_trusted_directory"
                ), patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("local", object(), codex_home),
                ), patch(
                    "pycodex.cli.parser._build_exec_session_config",
                    return_value=SimpleNamespace(),
                ), patch(
                    "pycodex.cli.parser._build_noninteractive_exec_event_processor",
                    return_value=SimpleNamespace(),
                ), patch(
                    "pycodex.cli.parser.remote_exec_session_connect_and_run",
                    return_value=SuccessResult(),
                ):
                    code = main(["--profile", "work", "review", "hello"], stderr=io.StringIO(), stdin="")

        self.assertEqual(code, 0)
        self.assertEqual(read_toml.call_count, 2)
        self.assertEqual(len(bootstrap_configs), 1)
        self.assertEqual(bootstrap_configs[0].get("personality"), "pragmatic")
        migrate.assert_called_once_with(codex_home, {}, override_profile="work")

    def test_main_review_without_migration_applied_uses_original_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            bootstrap_configs = []

            class SuccessResult:
                ok = True
                exit_code = 0
                error_message = None

            def fake_read_toml_mapping(_path: Path) -> dict[str, object]:
                return {"personality": "existing"}

            def fake_build_bootstrap_plan(
                _exec_cli: object,
                *,
                config_toml: dict[str, object],
            ) -> object:
                bootstrap_configs.append(dict(config_toml))
                return SimpleNamespace(config_cwd=codex_home)

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "PYCODEX_EXEC_CORE": "0",
                },
            ):
                with patch(
                    "pycodex.cli.parser.read_toml_mapping",
                    side_effect=fake_read_toml_mapping,
                ) as read_toml, patch(
                    "pycodex.cli.parser.maybe_migrate_personality",
                    return_value=PersonalityMigrationStatus.SKIPPED_NO_SESSIONS,
                ) as migrate, patch(
                    "pycodex.cli.parser.build_exec_config_bootstrap_plan",
                    side_effect=fake_build_bootstrap_plan,
                ), patch(
                    "pycodex.cli.parser.prepare_exec_run_plan",
                    return_value=SimpleNamespace(prompt_summary=()),
                ), patch(
                    "pycodex.cli.parser.ensure_exec_trusted_directory"
                ), patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("local", object(), codex_home),
                ), patch(
                    "pycodex.cli.parser._build_exec_session_config",
                    return_value=SimpleNamespace(),
                ), patch(
                    "pycodex.cli.parser._build_noninteractive_exec_event_processor",
                    return_value=SimpleNamespace(),
                ), patch(
                    "pycodex.cli.parser.remote_exec_session_connect_and_run",
                    return_value=SuccessResult(),
                ):
                    code = main(["--profile", "work", "review", "hello"], stderr=io.StringIO(), stdin="")

        self.assertEqual(code, 0)
        self.assertEqual(read_toml.call_count, 1)
        self.assertEqual(len(bootstrap_configs), 1)
        self.assertEqual(bootstrap_configs[0].get("personality"), "existing")
        migrate.assert_called_once_with(codex_home, {"personality": "existing"}, override_profile="work")

    def test_main_exec_local_http_runtime_prints_summary_and_final_message(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_shell_tools = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS")
        previous_key = os.environ.get("OPENAI_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = "0"
        os.environ["OPENAI_API_KEY"] = "sk-test"

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(*_args, **_kwargs):
            return FakeResult()

        try:
            with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_shell_tools is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = previous_shell_tools
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key

        self.assertEqual(code, 0)
        self.assertIn("OpenAI Codex v", stderr.getvalue())
        self.assertIn("provider: openai", stderr.getvalue())
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "done\n")

    def test_main_exec_local_http_loads_default_execpolicy_rules(self):
        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ),
            )
            raw_result = None

        captured = {}

        async def fake_run(session_config, *_args, **_kwargs):
            captured["rules"] = session_config.exec_policy_rules
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir) / "home"
            project = Path(tmpdir) / "project"
            (codex_home / "rules").mkdir(parents=True)
            (project / ".codex" / "rules").mkdir(parents=True)
            (project / ".git").mkdir()
            (codex_home / "rules" / "user.rules").write_text(
                'prefix_rule(pattern=["pwd"], decision="prompt", justification="inspect cwd")\n'
            )
            (project / ".codex" / "rules" / "project.rules").write_text(
                'prefix_rule(pattern=["git", "push"], decision="forbidden")\n'
            )
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-test",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "--cd", str(project), "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(
            tuple(rule.pattern for rule in captured["rules"]),
            (("pwd",), ("git", "push")),
        )
        self.assertEqual(captured["rules"][0].decision, "prompt")
        self.assertEqual(captured["rules"][0].justification, "inspect cwd")
        self.assertEqual(captured["rules"][1].decision, "forbidden")

    def test_main_exec_local_http_ignore_rules_skips_default_execpolicy_rules(self):
        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ),
            )
            raw_result = None

        captured = {}

        async def fake_run(session_config, *_args, **_kwargs):
            captured["rules"] = session_config.exec_policy_rules
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir) / "home"
            (codex_home / "rules").mkdir(parents=True)
            (codex_home / "rules" / "user.rules").write_text(
                'prefix_rule(pattern=["pwd"], decision="prompt", justification="inspect cwd")\n'
            )
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-test",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "--ignore-rules", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(captured["rules"], ())

    def test_main_review_local_http_runtime_prints_summary_and_final_message(self):
        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "review done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(*_args, **_kwargs):
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-test",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_review_http_sampling", side_effect=fake_run) as run_review:
                        with patch("pycodex.cli.parser.persist_local_http_exec_rollout") as persist_rollout:
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["review", "--uncommitted"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertTrue(run_review.called)
        self.assertTrue(persist_rollout.called)
        persisted_input = persist_rollout.call_args.kwargs["input_items"]
        self.assertEqual(len(persisted_input), 1)
        self.assertIn("full review output from reviewer model", persisted_input[0].text)
        self.assertIn("<action>review</action>", persisted_input[0].text)
        self.assertIn("review done", persisted_input[0].text)
        self.assertIn("current changes", stderr.getvalue())
        self.assertIn("completed local HTTP non-interactive review execution", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "review done\n")

    def test_main_review_core_env_uses_core_review_runner(self):
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "core review done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(command, *_args, **kwargs):
            seen["command"] = command
            seen["auth"] = kwargs.get("auth")
            seen["cli_version"] = kwargs.get("cli_version")
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_CORE": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "OPENAI_API_KEY": "sk-test",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_core_exec_command", side_effect=fake_run) as run_review:
                        with patch(
                            "pycodex.cli.parser.run_exec_review_http_sampling",
                            side_effect=AssertionError("local HTTP review runner should not run when core exec is enabled"),
                        ):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["review", "--uncommitted"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertTrue(run_review.called)
        self.assertEqual(seen["command"], "review")
        self.assertEqual(seen["auth"], "sk-test")
        self.assertIsInstance(seen["cli_version"], str)
        self.assertTrue(seen["cli_version"])
        self.assertIn("completed core non-interactive review execution", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "core review done\n")

    def test_main_review_api_key_defaults_to_core_review_runner(self):
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "default core review done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(command, *_args, **kwargs):
            seen["command"] = command
            seen["auth"] = kwargs.get("auth")
            seen["cli_version"] = kwargs.get("cli_version")
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "OPENAI_API_KEY": "sk-default-review",
                },
                clear=True,
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_core_exec_command", side_effect=fake_run) as run_review:
                        with patch(
                            "pycodex.cli.parser.run_exec_review_http_sampling",
                            side_effect=AssertionError("local HTTP review runner should not be the API-key default"),
                        ):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["review", "--uncommitted"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(run_review.call_count, 1)
        self.assertEqual(seen["command"], "review")
        self.assertEqual(seen["auth"], "sk-default-review")
        self.assertIsInstance(seen["cli_version"], str)
        self.assertEqual(stdout.getvalue(), "default core review done\n")
        self.assertIn("completed core non-interactive review execution", stderr.getvalue())

    def test_main_exec_local_http_configures_human_reasoning_visibility(self):
        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ),
            )
            raw_result = {
                "output": [
                    {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "public summary"}],
                        "content": [{"type": "reasoning_text", "text": "raw local thought"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    },
                ]
            }

        async def fake_run(*_args, **_kwargs):
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-test",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            ["exec", "--oss", "--local-provider", "lmstudio", "prompt"],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0)
        self.assertIn("raw local thought", stderr.getvalue())
        self.assertNotIn("public summary", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "done\n")

    def test_main_exec_local_http_smoke_posts_expected_request(self) -> None:
        seen = {}

        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "smoke"}],
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            seen["url"] = request.full_url
            seen["headers"] = dict(request.header_items())
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(seen["url"], "https://api.openai.com/v1/responses")
        headers = {key.lower(): value for key, value in seen["headers"].items()}
        self.assertEqual(headers["authorization"], "Bearer sk-smoke")
        self.assertEqual(headers["x-codex-installation-id"], "pycodex-local-exec")
        self.assertIn("x-codex-window-id", headers)
        self.assertEqual(headers.get("content-type"), "application/json")
        self.assertIn("input", seen["body"])
        self.assertEqual(seen["body"]["model"], "gpt-5.3-codex")
        self.assertIn("client_metadata", seen["body"])
        self.assertEqual(
            seen["body"]["client_metadata"]["x-codex-installation-id"],
            "pycodex-local-exec",
        )
        self.assertEqual(stdout.getvalue(), "smoke\n")

    def test_main_prompt_without_subcommand_uses_local_http_exec_when_available(self) -> None:
        seen = {}

        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "bare prompt done"}],
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["bare prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "bare prompt done\n")
        self.assertIn("prepared non-interactive exec plan", stderr.getvalue())
        user_items = [
            item
            for item in seen["body"]["input"]
            if item.get("type") == "message" and item.get("role") == "user"
        ]
        user_texts = [
            content.get("text")
            for item in user_items
            for content in item.get("content", ())
            if isinstance(content, dict)
        ]
        self.assertIn("bare prompt", user_texts)

    def test_main_prompt_without_subcommand_normalizes_crlf_for_local_http_exec(self) -> None:
        seen = {}

        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "ok"}],
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["line1\r\nline2\rline3"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        user_items = [
            item
            for item in seen["body"]["input"]
            if item.get("type") == "message" and item.get("role") == "user"
        ]
        user_texts = [
            content.get("text")
            for item in user_items
            for content in item.get("content", ())
            if isinstance(content, dict)
        ]
        self.assertIn("line1\nline2\nline3", user_texts)

    def test_main_exec_command_normalizes_crlf_prompt_for_core(self) -> None:
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "core exec crlf done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(command, _codex_home, _config, plan, _model_client, _provider, _model_info, **kwargs):
            seen["command"] = command
            seen["prompt"] = plan.prompt_summary
            seen["auth"] = kwargs.get("auth")
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_CORE": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "OPENAI_API_KEY": "sk-core",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_core_exec_command", side_effect=fake_run) as run_core:
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "line1\r\nline2\rline3"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(run_core.call_count, 1)
        self.assertIsNone(seen["command"])
        self.assertEqual(seen["prompt"], "line1\nline2\nline3")
        self.assertEqual(seen["auth"], "sk-core")
        self.assertEqual(stdout.getvalue(), "core exec crlf done\n")

    def test_main_prompt_without_subcommand_normalizes_crlf_for_core_exec_when_core_only(self) -> None:
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "core crlf prompt done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(command, _codex_home, _config, plan, _model_client, _provider, _model_info, **kwargs):
            seen["command"] = command
            seen["prompt"] = plan.prompt_summary
            seen["auth"] = kwargs.get("auth")
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_CORE": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "OPENAI_API_KEY": "sk-core",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_core_exec_command", side_effect=fake_run) as run_core:
                        with patch(
                            "pycodex.cli.parser._run_tui",
                            side_effect=AssertionError("prompt should run through core exec"),
                        ):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["line1\r\nline2\rline3"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(run_core.call_count, 1)
        self.assertIsNone(seen["command"])
        self.assertEqual(seen["prompt"], "line1\nline2\nline3")
        self.assertEqual(seen["auth"], "sk-core")
        self.assertEqual(stdout.getvalue(), "core crlf prompt done\n")

    def test_main_prompt_without_subcommand_uses_core_exec_when_core_only(self) -> None:
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "core bare prompt done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(command, _codex_home, _config, plan, _model_client, _provider, _model_info, **kwargs):
            seen["command"] = command
            seen["prompt"] = plan.prompt_summary
            seen["auth"] = kwargs.get("auth")
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_CORE": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "OPENAI_API_KEY": "sk-core",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_core_exec_command", side_effect=fake_run) as run_core:
                        with patch("pycodex.cli.parser._run_tui", side_effect=AssertionError("prompt should run through core exec")):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["bare prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(run_core.call_count, 1)
        self.assertIsNone(seen["command"])
        self.assertEqual(seen["prompt"], "bare prompt")
        self.assertEqual(seen["auth"], "sk-core")
        self.assertEqual(stdout.getvalue(), "core bare prompt done\n")
        self.assertIn("completed core non-interactive exec execution", stderr.getvalue())

    def test_main_exec_defaults_to_core_without_python_env_flag(self) -> None:
        # Rust crates/modules:
        # - codex-cli/src/main.rs dispatches Subcommand::Exec directly to
        #   codex_exec::run_main.
        # - codex-exec/src/lib.rs builds InProcessClientStartArgs and runs the
        #   exec session in-process.
        # Python must not require PYCODEX_EXEC_CORE=1 or fall through to the
        # app-server socket path for ordinary exec.
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "default core done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(command, *_args, **kwargs):
            seen["command"] = command
            seen["auth"] = kwargs.get("auth")
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            auth = SimpleNamespace(
                auth_mode="chatgpt",
                tokens={"access_token": "access-token", "account_id": "workspace-123"},
            )
            with patch.dict(os.environ, {"CODEX_HOME": tmpdir}, clear=True):
                with patch("pycodex.cli.parser.read_auth_json", return_value=auth):
                    with patch("pycodex.cli.parser.run_core_exec_command", side_effect=fake_run) as run_core:
                        with patch(
                            "pycodex.cli.parser._resolve_exec_remote_endpoint",
                            side_effect=AssertionError("default exec should not resolve app-server endpoint"),
                        ):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["exec", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(run_core.call_count, 1)
        self.assertIsNone(seen["command"])
        self.assertEqual(
            seen["auth"].to_auth_headers(),
            {
                "Authorization": "Bearer access-token",
                "ChatGPT-Account-ID": "workspace-123",
            },
        )
        self.assertEqual(stdout.getvalue(), "default core done\n")
        self.assertIn("completed core non-interactive exec execution", stderr.getvalue())

    def test_main_prompt_without_subcommand_with_profile_triggers_noninteractive_migration_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            read_call_count = 0
            bootstrap_configs = []

            class SuccessResult:
                response_items = ()
                raw_result = None

            def fake_read_toml_mapping(_path: Path) -> dict[str, object]:
                nonlocal read_call_count
                read_call_count += 1
                if read_call_count == 1:
                    return {}
                return {"personality": "pragmatic"}

            def fake_build_bootstrap_plan(
                _exec_cli: object,
                *,
                config_toml: dict[str, object],
            ) -> object:
                bootstrap_configs.append(dict(config_toml))
                return SimpleNamespace(config_cwd=codex_home)

            async def fake_core_run(*_args, **_kwargs) -> SuccessResult:
                return SuccessResult()

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "PYCODEX_EXEC_CORE": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                },
            ):
                with patch(
                    "pycodex.cli.parser.read_toml_mapping",
                    side_effect=fake_read_toml_mapping,
                ) as read_toml, patch(
                    "pycodex.cli.parser.maybe_migrate_personality",
                    return_value=PersonalityMigrationStatus.APPLIED,
                ) as migrate, patch(
                    "pycodex.cli.parser.build_exec_config_bootstrap_plan",
                    side_effect=fake_build_bootstrap_plan,
                ), patch(
                    "pycodex.cli.parser.prepare_exec_run_plan",
                    return_value=SimpleNamespace(prompt_summary="hello"),
                ), patch(
                    "pycodex.cli.parser.ensure_exec_trusted_directory"
                ), patch(
                    "pycodex.cli.parser.build_default_core_exec_runtime",
                    return_value=(
                        SimpleNamespace(state=SimpleNamespace(session_id="s", thread_id="t")),
                        SimpleNamespace(),
                        SimpleNamespace(slug="codex-test"),
                        None,
                    ),
                ), patch(
                    "pycodex.cli.parser.run_core_exec_command",
                    side_effect=fake_core_run,
                ) as run_core, patch(
                    "pycodex.cli.parser.emit_core_exec_result",
                ), patch(
                    "pycodex.cli.parser.emit_core_exec_config_summary",
                ), patch(
                    "pycodex.cli.parser._build_exec_session_config",
                    return_value=SimpleNamespace(),
                ), patch(
                    "pycodex.cli.parser._build_noninteractive_exec_event_processor",
                    return_value=SimpleNamespace(),
                ):
                    code = main(["--profile", "work", "hello"], stdout=io.StringIO(), stderr=io.StringIO())

        self.assertEqual(code, 0)
        self.assertEqual(read_toml.call_count, 2)
        self.assertEqual(len(bootstrap_configs), 1)
        self.assertEqual(bootstrap_configs[0].get("personality"), "pragmatic")
        self.assertEqual(run_core.call_count, 1)
        migrate.assert_called_once_with(codex_home, {}, override_profile="work")

    def test_main_prompt_without_subcommand_with_profile_without_migration_uses_original_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            bootstrap_configs = []

            class SuccessResult:
                response_items = ()
                raw_result = None

            async def fake_core_run(*_args, **_kwargs) -> SuccessResult:
                return SuccessResult()

            def fake_read_toml_mapping(_path: Path) -> dict[str, object]:
                return {"personality": "existing"}

            def fake_build_bootstrap_plan(
                _exec_cli: object,
                *,
                config_toml: dict[str, object],
            ) -> object:
                bootstrap_configs.append(dict(config_toml))
                return SimpleNamespace(config_cwd=codex_home)

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "PYCODEX_EXEC_CORE": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                },
            ):
                with patch(
                    "pycodex.cli.parser.read_toml_mapping",
                    side_effect=fake_read_toml_mapping,
                ) as read_toml, patch(
                    "pycodex.cli.parser.maybe_migrate_personality",
                    return_value=PersonalityMigrationStatus.SKIPPED_EXPLICIT_PERSONALITY,
                ) as migrate, patch(
                    "pycodex.cli.parser.build_exec_config_bootstrap_plan",
                    side_effect=fake_build_bootstrap_plan,
                ), patch(
                    "pycodex.cli.parser.prepare_exec_run_plan",
                    return_value=SimpleNamespace(prompt_summary="hello"),
                ), patch(
                    "pycodex.cli.parser.ensure_exec_trusted_directory"
                ), patch(
                    "pycodex.cli.parser.build_default_core_exec_runtime",
                    return_value=(
                        SimpleNamespace(state=SimpleNamespace(session_id="s", thread_id="t")),
                        SimpleNamespace(),
                        SimpleNamespace(slug="codex-test"),
                        None,
                    ),
                ), patch(
                    "pycodex.cli.parser.run_core_exec_command",
                    side_effect=fake_core_run,
                ) as run_core, patch(
                    "pycodex.cli.parser.emit_core_exec_result",
                ), patch(
                    "pycodex.cli.parser.emit_core_exec_config_summary",
                ), patch(
                    "pycodex.cli.parser._build_exec_session_config",
                    return_value=SimpleNamespace(),
                ), patch(
                    "pycodex.cli.parser._build_noninteractive_exec_event_processor",
                    return_value=SimpleNamespace(),
                ):
                    code = main(["--profile", "work", "hello"], stdout=io.StringIO(), stderr=io.StringIO())

        self.assertEqual(code, 0)
        self.assertEqual(read_toml.call_count, 1)
        self.assertEqual(len(bootstrap_configs), 1)
        self.assertEqual(bootstrap_configs[0].get("personality"), "existing")
        self.assertEqual(run_core.call_count, 1)
        migrate.assert_called_once_with(codex_home, {"personality": "existing"}, override_profile="work")

    def test_main_prompt_without_subcommand_forwards_root_image_to_local_http_exec(self) -> None:
        seen = {}

        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "image prompt done"}],
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "image.png"
            image_path.write_bytes(png_bytes)
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            ["--image", str(image_path), "inspect the provided image"],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "image prompt done\n")
        user_content = [
            content
            for item in seen["body"]["input"]
            if item.get("type") == "message" and item.get("role") == "user"
            for content in item.get("content", ())
            if isinstance(content, dict)
        ]
        self.assertTrue(
            any(
                content.get("type") == "input_image"
                and str(content.get("image_url", "")).startswith("data:image/png;base64,")
                for content in user_content
            )
        )
        self.assertTrue(any(content.get("text") == "inspect the provided image" for content in user_content))

    def test_main_prompt_without_subcommand_forwards_root_cd_to_local_http_exec(self) -> None:
        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "local_shell_call",
                                "call_id": "cwd-1",
                                "status": "completed",
                                "action": {
                                    "type": "exec",
                                    "command": ["pwd"],
                                },
                            },
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "cwd done"}],
                            },
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", return_value=FakeResponse()):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "--cd",
                                str(project),
                                "inspect cwd",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "cwd done\n")
        self.assertIn(f"workdir: {project}", stderr.getvalue())

    def test_main_prompt_without_subcommand_forwards_root_model_to_local_http_exec(self) -> None:
        seen = {}

        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "model done"}],
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            ["--model", "gpt-test-root", "inspect model"],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "model done\n")
        self.assertEqual(seen["body"]["model"], "gpt-test-root")
        self.assertIn("model: gpt-test-root", stderr.getvalue())

    def test_main_prompt_without_subcommand_forwards_root_approval_to_local_http_exec(self) -> None:
        request_bodies = []
        command = subprocess.list2cmdline(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('blocked-bare.txt').write_text('ran', encoding='utf-8')",
            ]
        )

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "bare-shell-blocked",
                        "arguments": json.dumps({"cmd": command}),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "bare approval needed"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "--ask-for-approval",
                                "on-request",
                                "--cd",
                                str(project),
                                "run a shell command",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )
            created = project / "blocked-bare.txt"
            created_exists = created.exists()

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertFalse(created_exists)
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(stdout.getvalue(), "bare approval needed\n")
        tool_outputs = [
            item for item in request_bodies[1]["input"] if item.get("type") == "function_call_output"
        ]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "bare-shell-blocked")
        self.assertIs(tool_outputs[0]["success"], False)
        self.assertIn("exit_code: approval_required", tool_outputs[0]["output"])
        self.assertIn("approval_policy: on-request", tool_outputs[0]["output"])
        self.assertIn("blocked-bare.txt", tool_outputs[0]["output"])

    def test_main_prompt_without_subcommand_forwards_root_dangerous_bypass_to_local_http_exec(self) -> None:
        request_bodies = []
        command = subprocess.list2cmdline(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('created-bare.txt').write_text('ran', encoding='utf-8')",
            ]
        )

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "bare-shell-created",
                        "arguments": json.dumps({"cmd": command}),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "bare shell ran"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "--dangerously-bypass-approvals-and-sandbox",
                                "--cd",
                                str(project),
                                "run a shell command",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )
            created = project / "created-bare.txt"
            created_text = created.read_text(encoding="utf-8") if created.exists() else None

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(created_text, "ran")
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(stdout.getvalue(), "bare shell ran\n")
        tool_outputs = [
            item for item in request_bodies[1]["input"] if item.get("type") == "function_call_output"
        ]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "bare-shell-created")
        self.assertIs(tool_outputs[0]["success"], True)
        self.assertIn("Process exited with code 0", tool_outputs[0]["output"])

    def test_main_exec_local_http_sse_smoke_outputs_final_message(self) -> None:
        seen = {}

        class FakeSseResponse:
            headers = {"content-type": "text/event-stream"}

            def read(self) -> bytes:
                return (
                    "event: response.output_item.done\n"
                    "data: {\"type\":\"response.output_item.done\",\"item\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"sse smoke\"}]}}\n"
                    "\n"
                    "event: response.completed\n"
                    "data: {\"type\":\"response.completed\",\"response\":{\"id\":\"resp-cli-sse\",\"usage\":{\"input_tokens\":3,\"output_tokens\":2,\"total_tokens\":5}}}\n"
                    "\n"
                    "data: [DONE]\n"
                    "\n"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            seen["url"] = request.full_url
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeSseResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(seen["url"], "https://api.openai.com/v1/responses")
        self.assertIs(seen["body"]["stream"], True)
        self.assertEqual(stdout.getvalue(), "sse smoke\n")

    def test_main_exec_local_http_sse_streamed_exec_command_runs_tool_and_followup(self) -> None:
        request_bodies = []
        command = subprocess.list2cmdline([sys.executable, "-c", "print('streamed-tool-smoke')"])
        arguments = json.dumps({"cmd": command})
        split_at = max(1, len(arguments) // 2)

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        class FakeSseToolCallResponse:
            headers = {"content-type": "text/event-stream"}

            def read(self) -> bytes:
                frames = [
                    (
                        "response.output_item.added",
                        {
                            "type": "response.output_item.added",
                            "item": {
                                "id": "fc-stream-1",
                                "type": "function_call",
                                "call_id": "stream-call-1",
                                "name": "exec_command",
                                "arguments": "",
                            },
                        },
                    ),
                    (
                        "response.function_call_arguments.delta",
                        {
                            "type": "response.function_call_arguments.delta",
                            "item_id": "fc-stream-1",
                            "delta": arguments[:split_at],
                        },
                    ),
                    (
                        "response.function_call_arguments.delta",
                        {
                            "type": "response.function_call_arguments.delta",
                            "item_id": "fc-stream-1",
                            "delta": arguments[split_at:],
                        },
                    ),
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp-streamed-tool",
                                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
                            },
                        },
                    ),
                ]
                body = "".join(
                    f"event: {event}\n"
                    f"data: {json.dumps(payload, separators=(',', ':'))}\n"
                    "\n"
                    for event, payload in frames
                )
                return (body + "data: [DONE]\n\n").encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            FakeSseToolCallResponse(),
            FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "streamed tool done"}],
                        }
                    ]
                }
            ),
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            ["exec", "--dangerously-bypass-approvals-and-sandbox", "prompt"],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(len(request_bodies), 2)
        self.assertIs(request_bodies[0]["stream"], True)
        self.assertEqual(stdout.getvalue(), "streamed tool done\n")
        followup_input = request_bodies[1]["input"]
        tool_outputs = [item for item in followup_input if item.get("type") == "function_call_output"]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "stream-call-1")
        self.assertIn("streamed-tool-smoke", tool_outputs[0]["output"])

    def test_main_exec_local_http_sse_streamed_apply_patch_runs_tool_and_followup(self) -> None:
        request_bodies = []
        patch_text = "*** Begin Patch\n*** Add File: streamed-patch.txt\n+from streamed patch\n*** End Patch\n"
        split_at = max(1, len(patch_text) // 2)

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        class FakeSseApplyPatchResponse:
            headers = {"content-type": "text/event-stream"}

            def read(self) -> bytes:
                frames = [
                    (
                        "response.output_item.added",
                        {
                            "type": "response.output_item.added",
                            "item": {
                                "id": "custom-stream-1",
                                "type": "custom_tool_call",
                                "call_id": "patch-stream-1",
                                "name": "apply_patch",
                                "input": "",
                            },
                        },
                    ),
                    (
                        "response.custom_tool_call_input.delta",
                        {
                            "type": "response.custom_tool_call_input.delta",
                            "item_id": "custom-stream-1",
                            "call_id": "patch-stream-1",
                            "delta": patch_text[:split_at],
                        },
                    ),
                    (
                        "response.custom_tool_call_input.delta",
                        {
                            "type": "response.custom_tool_call_input.delta",
                            "item_id": "custom-stream-1",
                            "call_id": "patch-stream-1",
                            "delta": patch_text[split_at:],
                        },
                    ),
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp-streamed-patch",
                                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
                            },
                        },
                    ),
                ]
                body = "".join(
                    f"event: {event}\n"
                    f"data: {json.dumps(payload, separators=(',', ':'))}\n"
                    "\n"
                    for event, payload in frames
                )
                return (body + "data: [DONE]\n\n").encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            FakeSseApplyPatchResponse(),
            FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "streamed patch done"}],
                        }
                    ]
                }
            ),
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return responses.pop(0)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "exec",
                                "--cd",
                                tmpdir,
                                "--dangerously-bypass-approvals-and-sandbox",
                                "create a file with streamed apply_patch",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )
            created = Path(tmpdir) / "streamed-patch.txt"
            created_text = created.read_text(encoding="utf-8")

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(created_text, "from streamed patch\n")
        self.assertEqual(len(request_bodies), 2)
        self.assertIs(request_bodies[0]["stream"], True)
        self.assertEqual(stdout.getvalue(), "streamed patch done\n")
        followup_input = request_bodies[1]["input"]
        patch_outputs = [item for item in followup_input if item.get("type") == "custom_tool_call_output"]
        self.assertEqual(len(patch_outputs), 1)
        self.assertEqual(patch_outputs[0]["call_id"], "patch-stream-1")
        self.assertNotIn("name", patch_outputs[0])
        self.assertIs(patch_outputs[0]["success"], True)
        self.assertIn("Success. Updated the following files:", patch_outputs[0]["output"])
        self.assertIn("streamed-patch.txt", patch_outputs[0]["output"])

    def test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup(self) -> None:
        request_bodies = []
        command = subprocess.list2cmdline([sys.executable, "-c", "print('tool-smoke')"])

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "call-1",
                        "arguments": json.dumps({"cmd": command}),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "tool done"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            ["exec", "--dangerously-bypass-approvals-and-sandbox", "prompt"],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0)
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(stdout.getvalue(), "tool done\n")
        first_tools = request_bodies[0].get("tools")
        self.assertTrue(any(tool.get("name") == "exec_command" for tool in first_tools))
        followup_input = request_bodies[1]["input"]
        tool_outputs = [item for item in followup_input if item.get("type") == "function_call_output"]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "call-1")
        self.assertIn("tool-smoke", tool_outputs[0]["output"])

    def test_main_exec_local_http_view_image_smoke_returns_image_content(self) -> None:
        request_bodies = []

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "view_image",
                        "call_id": "image-1",
                        "arguments": json.dumps({"path": "image.png", "detail": "high"}),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "image done"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "image.png").write_bytes(png_bytes)
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "exec",
                                "--cd",
                                tmpdir,
                                "--dangerously-bypass-approvals-and-sandbox",
                                "inspect image",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(stdout.getvalue(), "image done\n")
        first_tools = request_bodies[0].get("tools")
        self.assertTrue(any(tool.get("name") == "view_image" for tool in first_tools))
        view_image_tool = next(tool for tool in first_tools if tool.get("name") == "view_image")
        self.assertNotIn("output_schema", view_image_tool)
        followup_input = request_bodies[1]["input"]
        tool_outputs = [item for item in followup_input if item.get("type") == "function_call_output"]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "image-1")
        self.assertIs(tool_outputs[0]["success"], True)
        image_content = tool_outputs[0]["output"]
        self.assertEqual(len(image_content), 1)
        self.assertEqual(image_content[0]["type"], "input_image")
        self.assertEqual(image_content[0]["detail"], "high")
        self.assertTrue(image_content[0]["image_url"].startswith("data:image/png;base64,"))

    def test_main_exec_local_http_output_schema_smoke_reaches_followup_request(self) -> None:
        request_bodies = []
        command = subprocess.list2cmdline([sys.executable, "-c", "print('schema-tool-smoke')"])

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "schema-call-1",
                        "arguments": json.dumps({"cmd": command}),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "{\"summary\":\"schema done\"}"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        output_schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            schema_path = Path(tmpdir) / "schema.json"
            schema_path.write_text(json.dumps(output_schema), encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "exec",
                                "--output-schema",
                                str(schema_path),
                                "--dangerously-bypass-approvals-and-sandbox",
                                "prompt",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(stdout.getvalue(), "{\"summary\":\"schema done\"}\n")
        for body in request_bodies:
            text_format = body["text"]["format"]
            self.assertEqual(text_format["type"], "json_schema")
            self.assertEqual(text_format["name"], "codex_output_schema")
            self.assertIs(text_format["strict"], True)
            self.assertEqual(text_format["schema"], output_schema)
        followup_input = request_bodies[1]["input"]
        tool_outputs = [item for item in followup_input if item.get("type") == "function_call_output"]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "schema-call-1")
        self.assertIn("schema-tool-smoke", tool_outputs[0]["output"])

    def test_main_exec_local_http_write_stdin_smoke_continues_session_and_followup(self) -> None:
        request_bodies = []

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "stdin_child.py"
            script.write_text(
                "import sys\n"
                "print('ready', flush=True)\n"
                "line = sys.stdin.readline()\n"
                "print('got:' + line.strip(), flush=True)\n",
                encoding="utf-8",
            )
            command = subprocess.list2cmdline([sys.executable, "-u", str(script)])
            responses_seen = {"count": 0}

            def opener(request):
                body = json.loads(request.data.decode("utf-8"))
                request_bodies.append(body)
                responses_seen["count"] += 1
                if responses_seen["count"] == 1:
                    return FakeResponse(
                        {
                            "output": [
                                {
                                    "type": "function_call",
                                    "name": "exec_command",
                                    "call_id": "session-call-1",
                                    "arguments": json.dumps({"cmd": command, "yield_time_ms": 100}),
                                }
                            ]
                        }
                    )
                if responses_seen["count"] == 2:
                    tool_output = next(
                        item
                        for item in body["input"]
                        if item.get("type") == "function_call_output"
                        and item.get("call_id") == "session-call-1"
                    )
                    session_match = re.search(r"Process running with session ID (\d+)", tool_output["output"])
                    self.assertIsNotNone(session_match)
                    assert session_match is not None
                    return FakeResponse(
                        {
                            "output": [
                                {
                                    "type": "function_call",
                                    "name": "write_stdin",
                                    "call_id": "stdin-call-1",
                                    "arguments": json.dumps(
                                        {
                                            "session_id": int(session_match.group(1)),
                                            "chars": "hello\n",
                                            "yield_time_ms": 500,
                                        }
                                    ),
                                }
                            ]
                        }
                    )
                return FakeResponse(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "stdin done"}],
                            }
                        ]
                    }
                )

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "3",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            ["exec", "--dangerously-bypass-approvals-and-sandbox", "prompt"],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(len(request_bodies), 3)
        self.assertEqual(stdout.getvalue(), "stdin done\n")
        first_tools = request_bodies[0].get("tools")
        self.assertTrue(any(tool.get("name") == "exec_command" for tool in first_tools))
        self.assertTrue(any(tool.get("name") == "write_stdin" for tool in first_tools))
        exec_outputs = [
            item
            for item in request_bodies[1]["input"]
            if item.get("type") == "function_call_output" and item.get("call_id") == "session-call-1"
        ]
        self.assertEqual(len(exec_outputs), 1)
        self.assertIn("ready", exec_outputs[0]["output"])
        stdin_outputs = [
            item
            for item in request_bodies[2]["input"]
            if item.get("type") == "function_call_output" and item.get("call_id") == "stdin-call-1"
        ]
        self.assertEqual(len(stdin_outputs), 1)
        self.assertIs(stdin_outputs[0]["success"], True)
        self.assertIn("got:hello", stdin_outputs[0]["output"])

    def test_main_exec_local_http_shell_tool_on_request_requires_approval(self) -> None:
        request_bodies = []
        command = subprocess.list2cmdline(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('blocked-shell.txt').write_text('ran', encoding='utf-8')",
            ]
        )

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "shell-blocked",
                        "arguments": json.dumps({"cmd": command}),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "approval needed"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "--ask-for-approval",
                                "on-request",
                                "exec",
                                "--cd",
                                tmpdir,
                                "--skip-git-repo-check",
                                "run a shell command",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )
            created = Path(tmpdir) / "blocked-shell.txt"
            created_exists = created.exists()

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertFalse(created_exists)
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(stdout.getvalue(), "approval needed\n")
        followup_input = request_bodies[1]["input"]
        tool_outputs = [item for item in followup_input if item.get("type") == "function_call_output"]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "shell-blocked")
        self.assertIs(tool_outputs[0]["success"], False)
        self.assertIn("exit_code: approval_required", tool_outputs[0]["output"])
        self.assertIn("approval_policy: on-request", tool_outputs[0]["output"])
        self.assertIn("blocked-shell.txt", tool_outputs[0]["output"])

    def test_main_exec_local_http_shell_tool_forbidden_by_policy(self) -> None:
        request_bodies = []

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "shell-forbidden",
                        "arguments": json.dumps(
                            {
                                "cmd": "rm -rf /important/data",
                            }
                        ),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "blocked"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "exec",
                                "--ask-for-approval",
                                "never",
                                "--cd",
                                tmpdir,
                                "--skip-git-repo-check",
                                "rm -rf /important/data",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(len(request_bodies), 2)
        followup_input = request_bodies[1]["input"]
        tool_outputs = [item for item in followup_input if item.get("type") == "function_call_output"]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "shell-forbidden")
        self.assertIs(tool_outputs[0]["success"], False)
        self.assertIn("exit_code: forbidden", tool_outputs[0]["output"])
        self.assertIn("approval_policy", tool_outputs[0]["output"])
        self.assertIn("command:", tool_outputs[0]["output"])
        self.assertEqual(stdout.getvalue(), "blocked\n")

    def test_main_exec_local_http_request_permissions_on_request_returns_cancel_output(self) -> None:
        request_bodies = []

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "request_permissions",
                        "call_id": "permissions-1",
                        "arguments": json.dumps(
                            {
                                "reason": "Need network for smoke test",
                                "permissions": {"network": {"enabled": True}},
                            }
                        ),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "permission handled"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir) / "codex-home"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                "\n".join(
                    [
                        "[features]",
                        "request_permissions_tool = true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            project = Path(tmpdir) / "project"
            project.mkdir()
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "--ask-for-approval",
                                "on-request",
                                "exec",
                                "--cd",
                                str(project),
                                "--skip-git-repo-check",
                                "request network permission",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(stdout.getvalue(), "permission handled\n")
        first_tools = request_bodies[0].get("tools")
        self.assertTrue(any(tool.get("name") == "request_permissions" for tool in first_tools))
        followup_input = request_bodies[1]["input"]
        permission_outputs = [
            item
            for item in followup_input
            if item.get("type") == "function_call_output"
            and item.get("call_id") == "permissions-1"
        ]
        self.assertEqual(len(permission_outputs), 1)
        self.assertNotIn("name", permission_outputs[0])
        self.assertIs(permission_outputs[0]["success"], False)
        self.assertEqual(
            permission_outputs[0]["output"],
            "request_permissions was cancelled before receiving a response",
        )

    def test_main_exec_local_http_apply_patch_smoke_writes_file_and_followup(self) -> None:
        request_bodies = []
        patch_text = "*** Begin Patch\n*** Add File: created.txt\n+hello\n*** End Patch\n"

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "custom_tool_call",
                        "name": "apply_patch",
                        "input": patch_text,
                        "call_id": "patch-1",
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "patch done"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "exec",
                                "--cd",
                                tmpdir,
                                "--dangerously-bypass-approvals-and-sandbox",
                                "create a file",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )
            created = Path(tmpdir) / "created.txt"
            created_text = created.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertEqual(created_text, "hello\n")
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(stdout.getvalue(), "patch done\n")
        self.assertTrue(any(tool.get("name") == "apply_patch" for tool in request_bodies[0].get("tools", ())))
        followup_input = request_bodies[1]["input"]
        patch_outputs = [item for item in followup_input if item.get("type") == "custom_tool_call_output"]
        self.assertEqual(len(patch_outputs), 1)
        self.assertEqual(patch_outputs[0]["call_id"], "patch-1")
        self.assertNotIn("name", patch_outputs[0])
        self.assertIs(patch_outputs[0]["success"], True)
        self.assertIn("Success. Updated the following files:", patch_outputs[0]["output"])
        self.assertIn("created.txt", patch_outputs[0]["output"])

    def test_main_exec_local_http_apply_patch_on_request_requires_approval(self) -> None:
        request_bodies = []
        patch_text = "*** Begin Patch\n*** Add File: blocked.txt\n+no write\n*** End Patch\n"

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "custom_tool_call",
                        "name": "apply_patch",
                        "input": patch_text,
                        "call_id": "patch-blocked",
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "approval needed"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "--ask-for-approval",
                                "on-request",
                                "exec",
                                "--cd",
                                tmpdir,
                                "--skip-git-repo-check",
                                "create a file",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )
            created = Path(tmpdir) / "blocked.txt"
            created_exists = created.exists()

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertFalse(created_exists)
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(stdout.getvalue(), "approval needed\n")
        followup_input = request_bodies[1]["input"]
        patch_outputs = [item for item in followup_input if item.get("type") == "custom_tool_call_output"]
        self.assertEqual(len(patch_outputs), 1)
        self.assertEqual(patch_outputs[0]["call_id"], "patch-blocked")
        self.assertNotIn("name", patch_outputs[0])
        self.assertIs(patch_outputs[0]["success"], False)
        self.assertIn("apply_patch: approval_required", patch_outputs[0]["output"])
        self.assertIn("approval_policy: on-request", patch_outputs[0]["output"])

    def test_main_exec_local_http_exec_command_apply_patch_heredoc_smoke(self) -> None:
        request_bodies = []
        patch_command = (
            "apply_patch <<'PATCH'\n"
            "*** Begin Patch\n"
            "*** Add File: heredoc.txt\n"
            "+from heredoc\n"
            "*** End Patch\n"
            "PATCH\n"
        )

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "call-patch",
                        "arguments": json.dumps({"cmd": patch_command}),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "heredoc done"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "exec",
                                "--cd",
                                tmpdir,
                                "--dangerously-bypass-approvals-and-sandbox",
                                "create a file with apply_patch",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )
            created = Path(tmpdir) / "heredoc.txt"
            created_text = created.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertEqual(created_text, "from heredoc\n")
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(stdout.getvalue(), "heredoc done\n")
        followup_input = request_bodies[1]["input"]
        patch_outputs = [item for item in followup_input if item.get("type") == "function_call_output"]
        self.assertEqual(len(patch_outputs), 1)
        self.assertEqual(patch_outputs[0]["call_id"], "call-patch")
        self.assertIs(patch_outputs[0]["success"], True)
        self.assertIn("Success. Updated the following files:", patch_outputs[0]["output"])
        self.assertIn("heredoc.txt", patch_outputs[0]["output"])

    def test_main_exec_local_http_json_local_shell_call_smoke_outputs_command_execution(self) -> None:
        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "local_shell_call",
                                "call_id": "shell-smoke",
                                "status": "completed",
                                "action": {
                                    "type": "exec",
                                    "command": ["pwd"],
                                    "working_directory": "C:/work/project",
                                },
                            },
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done"}],
                            },
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", return_value=FakeResponse()):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        command_events = [
            event["item"]
            for event in events
            if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
        ]
        self.assertEqual(
            [(item["id"], item["command"], item["cwd"], item["status"]) for item in command_events],
            [
                ("shell-smoke", "pwd", "C:/work/project", "in_progress"),
                ("shell-smoke", "pwd", "C:/work/project", "completed"),
            ],
        )
        self.assertEqual(command_events[-1]["aggregated_output"], "aborted")
        agent_messages = [
            event["item"]["text"]
            for event in events
            if event["type"] == "item.completed" and event["item"]["type"] == "agent_message"
        ]
        self.assertEqual(agent_messages, ["done"])

    def test_main_exec_local_http_json_core_exec_command_smoke_outputs_command_execution(self) -> None:
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def read(self) -> bytes:
                return json.dumps(self.payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        command = (
            subprocess.list2cmdline([sys.executable, "-c", "print('cli core exec output')"])
            if os.name == "nt"
            else shlex.join([sys.executable, "-c", "print('cli core exec output')"])
        )
        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": json.dumps({"cmd": command, "yield_time_ms": 1_000}),
                        "call_id": "core-exec-smoke",
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ]
            },
        ]
        request_bodies = []

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(len(request_bodies), 2)
        tool_outputs = [item for item in request_bodies[1]["input"] if item["type"] == "function_call_output"]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "core-exec-smoke")
        self.assertIn("cli core exec output", tool_outputs[0]["output"])
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        command_events = [
            event["item"]
            for event in events
            if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
        ]
        self.assertEqual(
            [(item["id"], item["command"], item["status"]) for item in command_events],
            [
                ("core-exec-smoke", command, "in_progress"),
                ("core-exec-smoke", command, "completed"),
            ],
        )
        self.assertIn("cli core exec output", command_events[-1]["aggregated_output"])
        agent_messages = [
            event["item"]["text"]
            for event in events
            if event["type"] == "item.completed" and event["item"]["type"] == "agent_message"
        ]
        self.assertEqual(agent_messages, ["done"])

    def test_main_exec_local_http_json_orphan_tool_outputs_are_hidden(self) -> None:
        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "function_call_output",
                                "call_id": "orphan-function",
                                "output": "drop",
                            },
                            {
                                "type": "custom_tool_call_output",
                                "call_id": "orphan-custom",
                                "output": "drop",
                            },
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done"}],
                            },
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", return_value=FakeResponse()):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        completed_items = [
            event["item"]
            for event in events
            if event["type"] == "item.completed"
        ]
        self.assertEqual(
            [(item["type"], item.get("text")) for item in completed_items],
            [("agent_message", "done")],
        )
        self.assertNotIn("drop", stdout.getvalue())

    def test_main_exec_local_http_shell_tool_followup_interrupted_persists_tool_and_marker(self) -> None:
        request_bodies = []
        command = subprocess.list2cmdline([sys.executable, "-c", "print('before-interrupt')"])

        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "exec_command",
                                "call_id": "interrupt-call-1",
                                "arguments": json.dumps({"cmd": command}),
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse()

        async def fake_followup(*_args, **_kwargs):
            return UserTurnSamplingResult(
                request_plan=None,
                response_items=(ResponseItem.message("assistant", (ContentItem.output_text("partial after tool"),)),),
                turn_status="interrupted",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.exec.local_runtime.run_exec_tool_output_http_sampling", side_effect=fake_followup):
                        with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(
                                [
                                    "exec",
                                    "--cd",
                                    tmpdir,
                                    "--dangerously-bypass-approvals-and-sandbox",
                                    "run then interrupt",
                                ],
                                stdout=stdout,
                                stderr=stderr,
                            )
            rollout_paths = list((Path(tmpdir) / "sessions").rglob("rollout-*.jsonl"))
            self.assertEqual(len(rollout_paths), 1)
            persisted_items = read_response_items_from_rollout(rollout_paths[0])
            persisted_events = read_event_msgs_from_rollout(rollout_paths[0])

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("turn interrupted", stderr.getvalue())
        self.assertNotIn("partial after tool", stderr.getvalue())
        self.assertEqual(len(request_bodies), 1)
        persisted_types = [item.type for item in persisted_items]
        self.assertIn("function_call", persisted_types)
        self.assertIn("function_call_output", persisted_types)
        self.assertIn("before-interrupt", persisted_items[-2].output.to_json())
        self.assertIn("<turn_aborted>", persisted_items[-1].content[0].text)
        self.assertEqual(persisted_events[-1].type, "turn_aborted")
        self.assertEqual(persisted_events[-1].payload.reason, "interrupted")

    def test_main_exec_local_http_smoke_uses_openai_base_url(self) -> None:
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_key = os.environ.get("OPENAI_API_KEY")
        previous_base_url = os.environ.get("OPENAI_BASE_URL")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["OPENAI_API_KEY"] = "sk-smoke"
        os.environ["OPENAI_BASE_URL"] = "https://proxy.example/v1"

        seen = {}

        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps({"output": []}).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            seen["url"] = request.full_url
            return FakeResponse()

        try:
            with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key
            if previous_base_url is None:
                os.environ.pop("OPENAI_BASE_URL", None)
            else:
                os.environ["OPENAI_BASE_URL"] = previous_base_url

        self.assertEqual(code, 0)
        self.assertEqual(seen["url"], "https://proxy.example/v1/responses")

    def test_main_exec_resume_local_http_smoke_posts_expected_request(self) -> None:
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_key = os.environ.get("OPENAI_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["OPENAI_API_KEY"] = "sk-smoke"
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "aaaaaaaa-1111-2222-3333-444444444444"
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd="C:/work/resume",
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            self.assertIsNotNone(rollout_path)
            assert rollout_path is not None
            with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T03:04:05Z",
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": "before smoke"}],
                            },
                        }
                    )
                    + "\n"
                )

            seen = {}

            class FakeResponse:
                def read(self) -> bytes:
                    return json.dumps({"output": []}).encode("utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, _exc_type, _exc, _tb) -> None:
                    return None

            def opener(request):
                seen["url"] = request.full_url
                seen["headers"] = dict(request.header_items())
                seen["body"] = json.loads(request.data.decode("utf-8"))
                return FakeResponse()

            try:
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch.dict(os.environ, {"CODEX_HOME": tmpdir}):
                        with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["exec", "resume", thread_id, "hello"], stdout=stdout, stderr=stderr)
            finally:
                if previous_enabled is None:
                    os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
                else:
                    os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
                if previous_key is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = previous_key

            self.assertEqual(code, 0)
            self.assertEqual(seen["url"], "https://api.openai.com/v1/responses")
            headers = {key.lower(): value for key, value in seen["headers"].items()}
            self.assertEqual(headers["authorization"], "Bearer sk-smoke")
            self.assertEqual(headers["x-codex-installation-id"], "pycodex-local-exec")
            self.assertIn("x-codex-window-id", headers)
            self.assertIn("client_metadata", seen["body"])
            self.assertEqual(
                seen["body"]["client_metadata"]["x-codex-installation-id"],
                "pycodex-local-exec",
            )
            self.assertEqual(seen["body"]["input"][-1]["content"][0]["text"], "hello")
            self.assertIn("input", seen["body"])

    def test_main_exec_resume_local_http_smoke_reads_history_and_appends_rollout(self) -> None:
        request_bodies = []
        request_headers = []

        class FakeResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "resume cli done"}],
                            }
                        ]
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            request_headers.append({key.lower(): value for key, value in request.header_items()})
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "bbbbbbbb-1111-2222-3333-444444444444"
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd="C:/work/resume",
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            self.assertIsNotNone(rollout_path)
            assert rollout_path is not None
            with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
                for payload in (
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "previous user"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "previous assistant"}],
                    },
                ):
                    file.write(
                        json.dumps(
                            {
                                "timestamp": "2025-01-02T03:04:05Z",
                                "type": "response_item",
                                "payload": payload,
                            }
                        )
                        + "\n"
                    )

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            ["exec", "resume", thread_id, "current prompt"],
                            stdout=stdout,
                            stderr=stderr,
                        )
            persisted_items = read_response_items_from_rollout(rollout_path)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "resume cli done\n")
        self.assertEqual(len(request_bodies), 1)
        message_texts = [
            item["content"][0]["text"]
            for item in request_bodies[0]["input"]
            if item.get("type") == "message" and item.get("content")
        ]
        visible_turn_texts = [
            text
            for text in message_texts
            if text in {"previous user", "previous assistant", "current prompt"}
        ]
        self.assertEqual(visible_turn_texts, ["previous user", "previous assistant", "current prompt"])
        self.assertEqual(message_texts[-1], "current prompt")
        self.assertEqual(request_headers[0]["session-id"], thread_id)
        self.assertEqual(request_headers[0]["thread-id"], thread_id)
        self.assertEqual(persisted_items[-1].content[0].text, "resume cli done")

    def test_main_exec_resume_local_http_interrupted_appends_marker_and_suppresses_partial(self) -> None:
        async def fake_run(*_args, **_kwargs):
            return UserTurnSamplingResult(
                request_plan=None,
                response_items=(ResponseItem.message("assistant", (ContentItem.output_text("partial resume"),)),),
                turn_status="interrupted",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "dddddddd-1111-2222-3333-444444444444"
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd=str(codex_home),
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            self.assertIsNotNone(rollout_path)
            assert rollout_path is not None
            with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T03:04:05Z",
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": "previous resume"}],
                            },
                        }
                    )
                    + "\n"
                )

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.exec.local_runtime.run_exec_user_turn_http_sampling", side_effect=fake_run):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "resume", thread_id, "resume interrupted"], stdout=stdout, stderr=stderr)
            persisted_items = read_response_items_from_rollout(rollout_path)
            persisted_events = read_event_msgs_from_rollout(rollout_path)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("turn interrupted", stderr.getvalue())
        self.assertNotIn("partial resume", stderr.getvalue())
        self.assertIn("<turn_aborted>", persisted_items[-1].content[0].text)
        self.assertIn("interrupted the previous turn", persisted_items[-1].content[0].text)
        self.assertEqual(persisted_events[-1].type, "turn_aborted")
        self.assertEqual(persisted_events[-1].payload.reason, "interrupted")

    def test_main_exec_resume_local_http_shell_tools_smoke_runs_command_and_appends_rollout(self) -> None:
        request_bodies = []
        command = subprocess.list2cmdline([sys.executable, "-c", "print('resume-tool-smoke')"])

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "resume-call-1",
                        "arguments": json.dumps({"cmd": command}),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "resume tool done"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "cccccccc-1111-2222-3333-444444444444"
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd=str(codex_home),
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            self.assertIsNotNone(rollout_path)
            assert rollout_path is not None
            with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(
                    json.dumps(
                        {
                            "timestamp": "2025-01-02T03:04:05Z",
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": "previous tool turn"}],
                            },
                        }
                    )
                    + "\n"
                )

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "exec",
                                "resume",
                                thread_id,
                                "--dangerously-bypass-approvals-and-sandbox",
                                "resume with a tool",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )
            persisted_items = read_response_items_from_rollout(rollout_path)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "resume tool done\n")
        self.assertEqual(len(request_bodies), 2)
        first_message_texts = [
            item["content"][0]["text"]
            for item in request_bodies[0]["input"]
            if item.get("type") == "message" and item.get("content")
        ]
        self.assertIn("previous tool turn", first_message_texts)
        self.assertEqual(first_message_texts[-1], "resume with a tool")
        tool_outputs = [item for item in request_bodies[1]["input"] if item.get("type") == "function_call_output"]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "resume-call-1")
        self.assertIn("resume-tool-smoke", tool_outputs[0]["output"])
        self.assertEqual(persisted_items[-1].content[0].text, "resume tool done")
        persisted_types = [item.type for item in persisted_items]
        self.assertIn("function_call_output", persisted_types)

    def test_main_exec_resume_local_http_output_schema_smoke_reaches_followup_request(self) -> None:
        request_bodies = []
        command = subprocess.list2cmdline([sys.executable, "-c", "print('resume-schema-tool-smoke')"])

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "resume-schema-call-1",
                        "arguments": json.dumps({"cmd": command}),
                    }
                ]
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "{\"summary\":\"resume schema done\"}"}],
                    }
                ]
            },
        ]

        def opener(request):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        output_schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            thread_id = "eeeeeeee-1111-2222-3333-444444444444"
            schema_path = codex_home / "schema.json"
            schema_path.write_text(json.dumps(output_schema), encoding="utf-8")
            rollout_path = materialize_session_rollout(
                codex_home,
                SessionMeta(
                    id=thread_id,
                    timestamp="2025-01-02T03:04:05Z",
                    cwd=str(codex_home),
                    originator="codex_exec",
                    cli_version="test-version",
                    source="cli",
                    model_provider="openai",
                ),
            )
            self.assertIsNotNone(rollout_path)
            assert rollout_path is not None
            with rollout_path.open("a", encoding="utf-8", newline="\n") as file:
                for payload in (
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "previous schema user"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "previous schema assistant"}],
                    },
                ):
                    file.write(
                        json.dumps(
                            {
                                "timestamp": "2025-01-02T03:04:05Z",
                                "type": "response_item",
                                "payload": payload,
                            }
                        )
                        + "\n"
                    )

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-smoke",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            [
                                "exec",
                                "resume",
                                thread_id,
                                "--output-schema",
                                str(schema_path),
                                "--dangerously-bypass-approvals-and-sandbox",
                                "resume with schema",
                            ],
                            stdout=stdout,
                            stderr=stderr,
                        )
            persisted_items = read_response_items_from_rollout(rollout_path)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "{\"summary\":\"resume schema done\"}\n")
        self.assertEqual(len(request_bodies), 2)
        for body in request_bodies:
            text_format = body["text"]["format"]
            self.assertEqual(text_format["type"], "json_schema")
            self.assertEqual(text_format["name"], "codex_output_schema")
            self.assertIs(text_format["strict"], True)
            self.assertEqual(text_format["schema"], output_schema)
        first_message_texts = [
            item["content"][0]["text"]
            for item in request_bodies[0]["input"]
            if item.get("type") == "message" and item.get("content")
        ]
        self.assertEqual(
            [
                text
                for text in first_message_texts
                if text in {"previous schema user", "previous schema assistant", "resume with schema"}
            ],
            ["previous schema user", "previous schema assistant", "resume with schema"],
        )
        followup_input = request_bodies[1]["input"]
        tool_outputs = [item for item in followup_input if item.get("type") == "function_call_output"]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(tool_outputs[0]["call_id"], "resume-schema-call-1")
        self.assertIn("resume-schema-tool-smoke", tool_outputs[0]["output"])
        self.assertEqual(persisted_items[-1].content[0].text, "{\"summary\":\"resume schema done\"}")

    def test_main_exec_local_http_json_outputs_thread_and_turn_events(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_shell_tools = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS")
        previous_key = os.environ.get("OPENAI_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = "0"
        os.environ["OPENAI_API_KEY"] = "sk-test"

        class FakeRaw:
            raw_result = {
                "usage": {
                    "input_tokens": 4,
                    "output_tokens": 2,
                }
            }

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ),
            )
            raw_result = FakeRaw()

        async def fake_run(*_args, **_kwargs):
            return FakeResult()

        try:
            with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_shell_tools is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = previous_shell_tools
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key

        self.assertEqual(code, 0)
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(
            [event["type"] for event in events],
            ["thread.started", "turn.started", "item.completed", "turn.completed"],
        )
        self.assertEqual(events[2]["item"]["type"], "agent_message")
        self.assertEqual(events[2]["item"]["text"], "done")
        self.assertEqual(events[3]["usage"]["input_tokens"], 4)
        self.assertEqual(events[3]["usage"]["output_tokens"], 2)
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_missing_api_key_prints_human_error(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_key = os.environ.get("OPENAI_API_KEY")
        previous_codex_key = os.environ.get("CODEX_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("CODEX_API_KEY", None)

        try:
            with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                stdout = io.StringIO()
                stderr = io.StringIO()
                code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key
            if previous_codex_key is None:
                os.environ.pop("CODEX_API_KEY", None)
            else:
                os.environ["CODEX_API_KEY"] = previous_codex_key

        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(
            "ERROR: OPENAI_API_KEY or CODEX_API_KEY is required for PYCODEX_EXEC_LOCAL_HTTP=1",
            stderr.getvalue(),
        )

    def test_main_exec_core_missing_api_key_prints_core_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_CORE": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                },
                clear=True,
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(
            "ERROR: OPENAI_API_KEY or CODEX_API_KEY is required for core exec runtime",
            stderr.getvalue(),
        )
        self.assertNotIn("PYCODEX_EXEC_LOCAL_HTTP=1", stderr.getvalue())

    def test_main_exec_local_http_context_window_error_prints_human_error(self):
        class ContextWindowResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "status": "failed",
                        "error": {
                            "code": "context_length_exceeded",
                            "message": "too much context",
                        },
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-context",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", return_value=ContextWindowResponse()):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("ERROR:", stderr.getvalue())
        self.assertIn("context window", stderr.getvalue())
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_missing_api_key_prints_json_turn_failed(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_key = os.environ.get("OPENAI_API_KEY")
        previous_codex_key = os.environ.get("CODEX_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("CODEX_API_KEY", None)

        try:
            with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                stdout = io.StringIO()
                stderr = io.StringIO()
                code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key
            if previous_codex_key is None:
                os.environ.pop("CODEX_API_KEY", None)
            else:
                os.environ["CODEX_API_KEY"] = previous_codex_key

        self.assertEqual(code, 2)
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["turn.started", "turn.failed"])
        self.assertEqual(
            events[1]["error"]["message"],
            "OPENAI_API_KEY or CODEX_API_KEY is required for PYCODEX_EXEC_LOCAL_HTTP=1",
        )

    def test_main_exec_local_http_context_window_error_prints_json_error_event(self):
        class ContextWindowResponse:
            def read(self) -> bytes:
                return json.dumps(
                    {
                        "status": "failed",
                        "error": {
                            "code": "context_length_exceeded",
                            "message": "too much context",
                        },
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-context",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", return_value=ContextWindowResponse()):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["thread.started", "turn.started", "error", "turn.completed"])
        self.assertIn("context window", events[2]["message"])
        self.assertIn("usage", events[3])
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_interrupted_prints_human_without_partial_and_persists_marker(self):
        async def fake_run(*_args, **_kwargs):
            return UserTurnSamplingResult(
                request_plan=None,
                response_items=(ResponseItem.message("assistant", (ContentItem.output_text("partial answer"),)),),
                turn_status="interrupted",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-interrupted",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)
            rollout_paths = list((Path(tmpdir) / "sessions").rglob("rollout-*.jsonl"))
            self.assertEqual(len(rollout_paths), 1)
            persisted_items = read_response_items_from_rollout(rollout_paths[0])
            persisted_events = read_event_msgs_from_rollout(rollout_paths[0])

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("turn interrupted", stderr.getvalue())
        self.assertNotIn("partial answer", stderr.getvalue())
        self.assertIn("<turn_aborted>", persisted_items[-1].content[0].text)
        self.assertIn("interrupted the previous turn", persisted_items[-1].content[0].text)
        self.assertEqual(persisted_events[-1].type, "turn_aborted")
        self.assertEqual(persisted_events[-1].payload.reason, "interrupted")

    def test_main_exec_local_http_interrupted_prints_json_without_partial_and_persists_marker(self):
        async def fake_run(*_args, **_kwargs):
            return UserTurnSamplingResult(
                request_plan=None,
                response_items=(ResponseItem.message("assistant", (ContentItem.output_text("partial answer"),)),),
                turn_status="interrupted",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-interrupted",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)
            rollout_paths = list((Path(tmpdir) / "sessions").rglob("rollout-*.jsonl"))
            self.assertEqual(len(rollout_paths), 1)
            persisted_items = read_response_items_from_rollout(rollout_paths[0])
            persisted_events = read_event_msgs_from_rollout(rollout_paths[0])

        self.assertEqual(code, 0, stderr.getvalue())
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["thread.started", "turn.started"])
        self.assertNotIn("partial answer", stdout.getvalue())
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())
        self.assertIn("<turn_aborted>", persisted_items[-1].content[0].text)
        self.assertEqual(persisted_events[-1].type, "turn_aborted")
        self.assertEqual(persisted_events[-1].payload.reason, "interrupted")

    def test_main_exec_local_http_provider_error_prints_human_error(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_shell_tools = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS")
        previous_key = os.environ.get("OPENAI_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = "0"
        os.environ["OPENAI_API_KEY"] = "sk-test"

        async def fake_run(*_args, **_kwargs):
            raise RuntimeError("Responses API request failed with HTTP 400: bad schema")

        try:
            with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_shell_tools is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = previous_shell_tools
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key

        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("ERROR: Responses API request failed with HTTP 400: bad schema", stderr.getvalue())

    def test_main_exec_local_http_provider_error_prints_json_turn_failed(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_shell_tools = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS")
        previous_key = os.environ.get("OPENAI_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = "0"
        os.environ["OPENAI_API_KEY"] = "sk-test"

        async def fake_run(*_args, **_kwargs):
            raise RuntimeError("Responses API request failed with HTTP 400: bad schema")

        try:
            with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_shell_tools is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = previous_shell_tools
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key

        self.assertEqual(code, 1)
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["thread.started", "turn.started", "turn.failed"])
        self.assertEqual(events[2]["error"]["message"], "Responses API request failed with HTTP 400: bad schema")

    def test_main_exec_local_http_provider_http_error_prints_human_error_event(self):
        def opener(_request, *_args, **_kwargs):
            raise HTTPError(
                "https://api.example.test/v1/responses",
                400,
                "Bad Request",
                {},
                io.BytesIO(b'{"error":{"message":"bad schema"}}'),
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-provider",
                    "OPENAI_BASE_URL": "https://api.example.test/v1",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn('ERROR: {"error":{"message":"bad schema"}}', stderr.getvalue())
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_provider_http_error_prints_json_error_event(self):
        def opener(_request, *_args, **_kwargs):
            raise HTTPError(
                "https://api.example.test/v1/responses",
                400,
                "Bad Request",
                {},
                io.BytesIO(b'{"error":{"message":"bad schema"}}'),
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-provider",
                    "OPENAI_BASE_URL": "https://api.example.test/v1",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["thread.started", "turn.started", "error", "turn.completed"])
        self.assertEqual(events[2]["message"], '{"error":{"message":"bad schema"}}')
        self.assertIn("usage", events[3])
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_provider_rate_limit_prints_json_error_event(self):
        def opener(_request, *_args, **_kwargs):
            raise HTTPError(
                "https://api.example.test/v1/responses",
                429,
                "Too Many Requests",
                {},
                io.BytesIO(b'{"error":{"message":"too fast"}}'),
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-provider",
                    "OPENAI_BASE_URL": "https://api.example.test/v1",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        with patch("pycodex.core.http_transport.http_sampling_stream_max_retries", return_value=0):
                            with patch("pycodex.core.session.turn.runtime._provider_stream_max_retries", return_value=0):
                                stdout = io.StringIO()
                                stderr = io.StringIO()
                                code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["thread.started", "turn.started", "error", "turn.completed"])
        self.assertEqual(events[2]["message"], "exceeded retry limit, last status: 429 Too Many Requests")
        self.assertIn("usage", events[3])
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_retryable_stream_error_retries_and_succeeds(self):
        request_bodies = []

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb) -> None:
                return None

        responses = [
            {
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "temporary stream error, try again in 0s",
                }
            },
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "retry succeeded"}],
                    }
                ]
            },
        ]

        def opener(request, *_args, **_kwargs):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(responses.pop(0))

        async def no_retry_sleep(_sess, _seconds):
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-provider",
                    "OPENAI_BASE_URL": "https://api.example.test/v1",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        with patch("pycodex.core.session.turn.runtime._provider_stream_max_retries", return_value=1):
                            with patch("pycodex.core.session.turn.runtime._sleep_for_sampling_retry", side_effect=no_retry_sleep):
                                stdout = io.StringIO()
                                stderr = io.StringIO()
                                code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(len(request_bodies), 2)
        self.assertEqual(request_bodies[0]["input"], request_bodies[1]["input"])
        self.assertEqual(stdout.getvalue(), "retry succeeded\n")
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_provider_usage_limit_prints_human_error_event(self):
        headers = Message()
        headers["x-codex-active-limit"] = "codex_other"
        headers["x-codex-other-limit-name"] = "codex_other"
        headers["x-codex-other-primary-used-percent"] = "100"
        headers["x-codex-other-primary-window-minutes"] = "60"
        headers["x-codex-promo-message"] = "Upgrade for more usage"
        headers["x-codex-rate-limit-reached-type"] = "workspace_owner_usage_limit_reached"

        def opener(_request, *_args, **_kwargs):
            raise HTTPError(
                "https://api.example.test/v1/responses",
                429,
                "Too Many Requests",
                headers,
                io.BytesIO(b'{"error":{"type":"usage_limit_reached","plan_type":"pro","resets_at":1704069000}}'),
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-provider",
                    "OPENAI_BASE_URL": "https://api.example.test/v1",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        with patch("pycodex.core.http_transport.http_sampling_stream_max_retries", return_value=0):
                            with patch("pycodex.core.session.turn.runtime._provider_stream_max_retries", return_value=0):
                                stdout = io.StringIO()
                                stderr = io.StringIO()
                                code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("ERROR: You've hit your usage limit for codex_other.", stderr.getvalue())
        self.assertIn("Switch to another model now", stderr.getvalue())
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_provider_usage_limit_prints_json_error_event(self):
        headers = Message()
        headers["x-codex-active-limit"] = "codex_other"
        headers["x-codex-other-limit-name"] = "codex_other"
        headers["x-codex-other-primary-used-percent"] = "100"
        headers["x-codex-other-primary-window-minutes"] = "60"
        headers["x-codex-promo-message"] = "Upgrade for more usage"
        headers["x-codex-rate-limit-reached-type"] = "workspace_owner_usage_limit_reached"

        def opener(_request, *_args, **_kwargs):
            raise HTTPError(
                "https://api.example.test/v1/responses",
                429,
                "Too Many Requests",
                headers,
                io.BytesIO(b'{"error":{"type":"usage_limit_reached","plan_type":"pro","resets_at":1704069000}}'),
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-provider",
                    "OPENAI_BASE_URL": "https://api.example.test/v1",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        with patch("pycodex.core.http_transport.http_sampling_stream_max_retries", return_value=0):
                            with patch("pycodex.core.session.turn.runtime._provider_stream_max_retries", return_value=0):
                                stdout = io.StringIO()
                                stderr = io.StringIO()
                                code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["thread.started", "turn.started", "error", "turn.completed"])
        self.assertIn("usage limit for codex_other", events[2]["message"])
        self.assertIn("Switch to another model now", events[2]["message"])
        self.assertIn("usage", events[3])
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_provider_connection_error_prints_human_error_event(self):
        def opener(_request, *_args, **_kwargs):
            raise URLError("temporary dns failure")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-provider",
                    "OPENAI_BASE_URL": "https://api.example.test/v1",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        with patch("pycodex.core.http_transport.http_sampling_stream_max_retries", return_value=0):
                            with patch("pycodex.core.session.turn.runtime._provider_stream_max_retries", return_value=0):
                                stdout = io.StringIO()
                                stderr = io.StringIO()
                                code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("ERROR: Connection failed: temporary dns failure", stderr.getvalue())
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_provider_timeout_prints_json_error_event(self):
        def opener(_request, *_args, **_kwargs):
            raise TimeoutError("timed out")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "sk-provider",
                    "OPENAI_BASE_URL": "https://api.example.test/v1",
                    "PYCODEX_EXEC_MODEL": "",
                    "OPENAI_MODEL": "",
                },
            ):
                with patch("pycodex.core.http_transport.urlopen", side_effect=opener):
                    with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                        with patch("pycodex.core.http_transport.http_sampling_stream_max_retries", return_value=0):
                            with patch("pycodex.core.session.turn.runtime._provider_stream_max_retries", return_value=0):
                                stdout = io.StringIO()
                                stderr = io.StringIO()
                                code = main(["exec", "--json", "prompt"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0, stderr.getvalue())
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["thread.started", "turn.started", "error", "turn.completed"])
        self.assertEqual(events[2]["message"], "request timed out")
        self.assertIn("usage", events[3])
        self.assertIn("completed local HTTP non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_writes_last_message_file(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_shell_tools = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS")
        previous_key = os.environ.get("OPENAI_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = "0"
        os.environ["OPENAI_API_KEY"] = "sk-test"

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(*_args, **_kwargs):
            return FakeResult()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                last_message_path = Path(tmpdir) / "last-message.txt"
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            ["exec", "--output-last-message", str(last_message_path), "prompt"],
                            stdout=stdout,
                            stderr=stderr,
                        )
                written = last_message_path.read_text(encoding="utf-8")
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_shell_tools is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = previous_shell_tools
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key

        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "done\n")
        self.assertEqual(written, "done")

    def test_main_exec_local_http_json_writes_last_message_file(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_shell_tools = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS")
        previous_key = os.environ.get("OPENAI_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = "0"
        os.environ["OPENAI_API_KEY"] = "sk-test"

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(*_args, **_kwargs):
            return FakeResult()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                last_message_path = Path(tmpdir) / "last-message.txt"
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            ["exec", "--json", "--output-last-message", str(last_message_path), "prompt"],
                            stdout=stdout,
                            stderr=stderr,
                        )
                written = last_message_path.read_text(encoding="utf-8")
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_shell_tools is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = previous_shell_tools
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key

        self.assertEqual(code, 0)
        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(
            [event["type"] for event in events],
            ["thread.started", "turn.started", "item.completed", "turn.completed"],
        )
        self.assertEqual(events[2]["item"]["text"], "done")
        self.assertEqual(written, "done")

    def test_main_exec_local_http_uses_auth_json_api_key(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_shell_tools = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS")
        previous_key = os.environ.get("OPENAI_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = "0"
        os.environ.pop("OPENAI_API_KEY", None)
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(*_args, **kwargs):
            seen["auth"] = kwargs["auth"]
            return FakeResult()

        try:
            with patch(
                "pycodex.cli.parser.read_auth_json",
                return_value=AuthDotJson(openai_api_key="sk-auth-json"),
            ):
                with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_shell_tools is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = previous_shell_tools
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key

        self.assertEqual(code, 0)
        self.assertEqual(seen["auth"].openai_api_key, "sk-auth-json")
        self.assertEqual(stdout.getvalue(), "done\n")

    def test_main_exec_reads_config_toml_for_local_http_session_config(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_shell_tools = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS")
        previous_key = os.environ.get("OPENAI_API_KEY")
        previous_home = os.environ.get("CODEX_HOME")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = "0"
        os.environ["OPENAI_API_KEY"] = "sk-test"
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(config, *_args, **_kwargs):
            seen["user_instructions"] = config.user_instructions
            seen["allow_login_shell"] = config.allow_login_shell
            seen["exec_permission_approvals_enabled"] = config.exec_permission_approvals_enabled
            seen["request_permissions_tool_enabled"] = config.request_permissions_tool_enabled
            return FakeResult()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["CODEX_HOME"] = tmpdir
                (Path(tmpdir) / "config.toml").write_text(
                    "\n".join(
                        [
                            'user_instructions = "from config"',
                            "allow_login_shell = false",
                            "[features]",
                            "exec_permission_approvals = true",
                            "request_permissions_tool = true",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_shell_tools is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = previous_shell_tools
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key
            if previous_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 0)
        self.assertTrue(seen["user_instructions"].startswith("from config"))
        self.assertFalse(seen["allow_login_shell"])
        self.assertTrue(seen["exec_permission_approvals_enabled"])
        self.assertTrue(seen["request_permissions_tool_enabled"])
        self.assertEqual(stdout.getvalue(), "done\n")

    def test_main_exec_local_http_prefers_env_api_key_over_auth_json(self):
        previous_enabled = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP")
        previous_shell_tools = os.environ.get("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS")
        previous_key = os.environ.get("OPENAI_API_KEY")
        os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = "1"
        os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = "0"
        os.environ["OPENAI_API_KEY"] = "sk-env"
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ),
            )
            raw_result = None

        async def fake_run(*_args, **kwargs):
            seen["auth"] = kwargs["auth"]
            return FakeResult()

        try:
            with patch(
                "pycodex.cli.parser.read_auth_json",
                return_value=AuthDotJson(openai_api_key="sk-auth-json"),
            ):
                with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(["exec", "prompt"], stdout=stdout, stderr=stderr)
        finally:
            if previous_enabled is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP"] = previous_enabled
            if previous_shell_tools is None:
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS", None)
            else:
                os.environ["PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"] = previous_shell_tools
            if previous_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_key

        self.assertEqual(code, 0)
        self.assertEqual(seen["auth"], "sk-env")
        self.assertEqual(stdout.getvalue(), "done\n")

    def test_main_exec_when_local_app_server_missing_prints_start_hint(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            endpoint_path = Path(tmpdir) / "app-server-control" / "app-server-control.sock"
            fake_endpoint = type("FakeEndpoint", (), {"kind": "unix_socket", "socket_path": endpoint_path})()

            class FailedResult:
                ok = False
                exit_code = 17
                error_message = "connection failed (stubbed)"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("unix://%s" % endpoint_path, fake_endpoint, Path(tmpdir)),
                ):
                    with patch("pycodex.cli.parser.remote_exec_session_connect_and_run", return_value=FailedResult()):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(["exec", "prompt"], stderr=stderr)
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 17)
        self.assertIn("local app-server socket not found", stderr.getvalue())
        self.assertIn("app-server state: state file missing", stderr.getvalue())
        self.assertIn("start the local app-server first, for example:", stderr.getvalue())
        self.assertIn("codex app-server daemon start", stderr.getvalue())
        self.assertIn("connection failed (stubbed)", stderr.getvalue())

    def test_main_exec_when_local_app_server_state_not_running_prints_state_hint(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            state_path = Path(tmpdir) / "app-server-state.json"
            state_path.write_text(json.dumps({"daemon": {"running": False}}), encoding="utf-8")
            endpoint_path = Path(tmpdir) / "app-server-control" / "app-server-control.sock"
            fake_endpoint = type("FakeEndpoint", (), {"kind": "unix_socket", "socket_path": endpoint_path})()

            endpoint_path.parent.mkdir(parents=True, exist_ok=True)
            endpoint_path.write_text("", encoding="utf-8")

            class FailedResult:
                ok = False
                exit_code = 19
                error_message = "connection failed (stubbed)"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("unix://%s" % endpoint_path, fake_endpoint, Path(tmpdir)),
                ):
                    with patch("pycodex.cli.parser.remote_exec_session_connect_and_run", return_value=FailedResult()):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(["exec", "prompt"], stderr=stderr)
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 19)
        self.assertIn("cannot connect to local app-server socket", stderr.getvalue())
        self.assertIn("state says not running", stderr.getvalue())
        self.assertIn("codex app-server daemon bootstrap", stderr.getvalue())

    def test_main_exec_when_no_remote_defaults_to_non_unix_remote_endpoint_prints_remote_hint(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir

            from pycodex.exec.session import RemoteAppServerEndpoint

            fake_endpoint = RemoteAppServerEndpoint.websocket("ws://127.0.0.1:4500")

            class FailedResult:
                ok = False
                exit_code = 31
                error_message = "[Errno 111] Connection refused"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("ws://127.0.0.1:4500", fake_endpoint, Path(tmpdir)),
                ):
                    with patch(
                        "pycodex.cli.parser.remote_exec_session_connect_and_run",
                        return_value=FailedResult(),
                    ):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(
                            ["exec", "prompt"], stderr=stderr
                        )
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 31)
        self.assertIn(
            "no --remote provided; attempting local app-server endpoint ws://127.0.0.1:4500.",
            stderr.getvalue(),
        )
        self.assertIn(
            "pycodex: failed to connect to remote execution endpoint `ws://127.0.0.1:4500`.",
            stderr.getvalue(),
        )
        self.assertIn("ensure the remote endpoint is reachable and running.", stderr.getvalue())
        self.assertIn("[Errno 111] Connection refused", stderr.getvalue())
        self.assertNotIn("local app-server socket not found", stderr.getvalue())

    def test_main_exec_when_remote_arg_set_does_not_print_local_app_server_hint(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir

            from pycodex.exec.session import RemoteAppServerEndpoint

            fake_endpoint = RemoteAppServerEndpoint.websocket("ws://127.0.0.1:4500")

            class FailedResult:
                ok = False
                exit_code = 31
                error_message = "[Errno 111] Connection refused"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("ws://127.0.0.1:4500", fake_endpoint, Path(tmpdir)),
                ):
                    with patch(
                        "pycodex.cli.parser.remote_exec_session_connect_and_run",
                        return_value=FailedResult(),
                    ):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(
                            ["--remote", "ws://127.0.0.1:4500", "exec", "prompt"],
                            stderr=stderr,
                        )
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 31)
        self.assertIn(
            "pycodex: failed to connect to remote execution endpoint `ws://127.0.0.1:4500`.",
            stderr.getvalue(),
        )
        self.assertIn("[Errno 111] Connection refused", stderr.getvalue())
        self.assertNotIn("attempting local app-server endpoint", stderr.getvalue())
        self.assertNotIn("start the local app-server first, for example:", stderr.getvalue())

    def test_main_exec_when_remote_arg_set_unix_socket_does_not_print_local_app_server_hint(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir

            from pycodex.exec.session import RemoteAppServerEndpoint

            endpoint_path = Path(tmpdir) / "explicit-unix.sock"
            fake_endpoint = RemoteAppServerEndpoint.unix_socket(endpoint_path)

            class FailedResult:
                ok = False
                exit_code = 31
                error_message = "[Errno 2] No such file or directory"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=(f"unix://{endpoint_path}", fake_endpoint, Path(tmpdir)),
                ):
                    with patch(
                        "pycodex.cli.parser.remote_exec_session_connect_and_run",
                        return_value=FailedResult(),
                    ):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(
                            ["--remote", f"unix://{endpoint_path}", "exec", "prompt"],
                            stderr=stderr,
                        )
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 31)
        self.assertIn(
            f"pycodex: failed to connect to remote execution endpoint `unix://{endpoint_path}`.",
            stderr.getvalue(),
        )
        self.assertIn("[Errno 2] No such file or directory", stderr.getvalue())
        self.assertNotIn("attempting local app-server endpoint", stderr.getvalue())
        self.assertNotIn("start the local app-server first, for example:", stderr.getvalue())

    def test_main_exec_when_remote_arg_is_invalid_remote_address(self) -> None:
        previous_home = os.environ.get("CODEX_HOME")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["CODEX_HOME"] = tmpdir
                stderr = io.StringIO()
                code = self._main_with_local_http_exec_disabled(
                    ["--remote", "not-a-remote", "exec", "prompt"],
                    stderr=stderr,
                )
        finally:
            if previous_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 1)
        self.assertIn("invalid remote address `not-a-remote`", stderr.getvalue())
        self.assertNotIn("attempting local app-server endpoint", stderr.getvalue())
        self.assertNotIn("start the local app-server first, for example:", stderr.getvalue())

    def test_main_exec_when_remote_auth_token_env_is_missing_does_not_print_local_app_server_hint(self) -> None:
        previous_home = os.environ.get("CODEX_HOME")
        previous_token = os.environ.get("PYCODEX_TEST_REMOTE_AUTH_TOKEN")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["CODEX_HOME"] = tmpdir
                stderr = io.StringIO()
                code = self._main_with_local_http_exec_disabled(
                    [
                        "--remote",
                        "ws://127.0.0.1:4500",
                        "--remote-auth-token-env",
                        "PYCODEX_TEST_REMOTE_AUTH_TOKEN",
                        "exec",
                        "prompt",
                    ],
                    stderr=stderr,
                )
        finally:
            if previous_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_home
            if previous_token is None:
                os.environ.pop("PYCODEX_TEST_REMOTE_AUTH_TOKEN", None)
            else:
                os.environ["PYCODEX_TEST_REMOTE_AUTH_TOKEN"] = previous_token

        self.assertEqual(code, 1)
        self.assertIn("environment variable `PYCODEX_TEST_REMOTE_AUTH_TOKEN` is not set", stderr.getvalue())
        self.assertNotIn("attempting local app-server endpoint", stderr.getvalue())
        self.assertNotIn("start the local app-server first, for example:", stderr.getvalue())

    def test_print_local_app_server_connect_hint_for_websocket_connect_error_variants(self) -> None:
        previous_home = os.environ.get("CODEX_HOME")
        try:
            for connect_error in (None, ""):
                with self.subTest(connect_error=connect_error):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        os.environ["CODEX_HOME"] = tmpdir
                        from pycodex.exec.session import RemoteAppServerEndpoint

                        endpoint = RemoteAppServerEndpoint.websocket("ws://127.0.0.1:4500")
                        stderr = io.StringIO()
                        _print_local_app_server_connect_hint(
                            endpoint,
                            Path(tmpdir),
                            connect_error=connect_error,
                            stderr=stderr,
                        )

                        self.assertIn(
                            "pycodex: failed to connect to remote execution endpoint `ws://127.0.0.1:4500`.",
                            stderr.getvalue(),
                        )
                        self.assertIn(
                            "pycodex: ensure the remote endpoint is reachable and running.",
                            stderr.getvalue(),
                        )
                        self.assertNotIn("local app-server socket", stderr.getvalue())
                        self.assertNotIn("state file", stderr.getvalue())
        finally:
            if previous_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_home

    def test_main_exec_when_local_app_server_state_is_invalid_prints_state_read_error(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            state_path = Path(tmpdir) / "app-server-state.json"
            state_path.write_text("[]", encoding="utf-8")
            endpoint_path = Path(tmpdir) / "app-server-control" / "app-server-control.sock"
            fake_endpoint = type("FakeEndpoint", (), {"kind": "unix_socket", "socket_path": endpoint_path})()

            endpoint_path.parent.mkdir(parents=True, exist_ok=True)
            endpoint_path.write_text("", encoding="utf-8")

            class FailedResult:
                ok = False
                exit_code = 23
                error_message = "[Errno 111] Connection refused"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("unix://%s" % endpoint_path, fake_endpoint, Path(tmpdir)),
                ):
                    with patch("pycodex.cli.parser.remote_exec_session_connect_and_run", return_value=FailedResult()):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(["exec", "prompt"], stderr=stderr)
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 23)
        self.assertIn("app-server state: failed to read state: invalid state format in", stderr.getvalue())
        self.assertIn("local app-server socket exists but the app-server is not accepting connections yet.", stderr.getvalue())

    def test_main_exec_when_local_app_server_state_is_unreadable_prints_state_read_error(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            state_path = Path(tmpdir) / "app-server-state.json"
            state_path.write_text("{\"daemon\":", encoding="utf-8")
            endpoint_path = Path(tmpdir) / "app-server-control" / "app-server-control.sock"
            fake_endpoint = type("FakeEndpoint", (), {"kind": "unix_socket", "socket_path": endpoint_path})()

            endpoint_path.parent.mkdir(parents=True, exist_ok=True)
            endpoint_path.write_text("", encoding="utf-8")

            class FailedResult:
                ok = False
                exit_code = 24
                error_message = "[Errno 111] Connection refused"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("unix://%s" % endpoint_path, fake_endpoint, Path(tmpdir)),
                ):
                    with patch("pycodex.cli.parser.remote_exec_session_connect_and_run", return_value=FailedResult()):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(["exec", "prompt"], stderr=stderr)
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 24)
        self.assertIn("app-server state: failed to read state: failed to read", stderr.getvalue())
        self.assertIn("app-server-state.json", stderr.getvalue())

    def test_main_exec_when_local_app_server_connection_is_refused_prints_refused_hint(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            endpoint_path = Path(tmpdir) / "app-server-control" / "app-server-control.sock"
            fake_endpoint = type("FakeEndpoint", (), {"kind": "unix_socket", "socket_path": endpoint_path})()

            endpoint_path.parent.mkdir(parents=True, exist_ok=True)
            endpoint_path.write_text("", encoding="utf-8")

            class FailedResult:
                ok = False
                exit_code = 19
                error_message = "[Errno 111] Connection refused"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("unix://%s" % endpoint_path, fake_endpoint, Path(tmpdir)),
                ):
                    with patch("pycodex.cli.parser.remote_exec_session_connect_and_run", return_value=FailedResult()):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(["exec", "prompt"], stderr=stderr)
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 19)
        self.assertIn("local app-server socket exists but the app-server is not accepting connections yet.", stderr.getvalue())
        self.assertIn("[Errno 111] Connection refused", stderr.getvalue())

    def test_main_exec_when_local_app_server_generic_connect_error_prints_generic_hint(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            endpoint_path = Path(tmpdir) / "app-server-control" / "app-server-control.sock"
            fake_endpoint = type("FakeEndpoint", (), {"kind": "unix_socket", "socket_path": endpoint_path})()

            endpoint_path.parent.mkdir(parents=True, exist_ok=True)
            endpoint_path.write_text("", encoding="utf-8")

            class FailedResult:
                ok = False
                exit_code = 25
                error_message = None

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("unix://%s" % endpoint_path, fake_endpoint, Path(tmpdir)),
                ):
                    with patch("pycodex.cli.parser.remote_exec_session_connect_and_run", return_value=FailedResult()):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(["exec", "prompt"], stderr=stderr)
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 25)
        self.assertIn("cannot connect to local app-server socket", stderr.getvalue())
        self.assertIn("state file missing", stderr.getvalue())

    def test_main_exec_when_local_app_server_permission_is_denied_prints_permission_hint(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            endpoint_path = Path(tmpdir) / "app-server-control" / "app-server-control.sock"
            fake_endpoint = type("FakeEndpoint", (), {"kind": "unix_socket", "socket_path": endpoint_path})()

            endpoint_path.parent.mkdir(parents=True, exist_ok=True)
            endpoint_path.write_text("", encoding="utf-8")

            class FailedResult:
                ok = False
                exit_code = 77
                error_message = "[Errno 13] Permission denied"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("unix://%s" % endpoint_path, fake_endpoint, Path(tmpdir)),
                ):
                    with patch("pycodex.cli.parser.remote_exec_session_connect_and_run", return_value=FailedResult()):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(["exec", "prompt"], stderr=stderr)
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 77)
        self.assertIn("cannot access local app-server socket due to permissions.", stderr.getvalue())
        self.assertIn("codex app-server daemon start", stderr.getvalue())
        self.assertIn("[Errno 13] Permission denied", stderr.getvalue())

    def test_main_exec_when_local_app_server_connection_timed_out_prints_timed_out_hint(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            endpoint_path = Path(tmpdir) / "app-server-control" / "app-server-control.sock"
            fake_endpoint = type("FakeEndpoint", (), {"kind": "unix_socket", "socket_path": endpoint_path})()

            endpoint_path.parent.mkdir(parents=True, exist_ok=True)
            endpoint_path.write_text("", encoding="utf-8")

            class FailedResult:
                ok = False
                exit_code = 28
                error_message = "[Errno 110] Connection timed out"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("unix://%s" % endpoint_path, fake_endpoint, Path(tmpdir)),
                ):
                    with patch("pycodex.cli.parser.remote_exec_session_connect_and_run", return_value=FailedResult()):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(["exec", "prompt"], stderr=stderr)
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 28)
        self.assertIn("connection timed out while waiting for startup", stderr.getvalue())
        self.assertIn("state file missing", stderr.getvalue())
        self.assertIn("[Errno 110] Connection timed out", stderr.getvalue())

    def test_main_exec_when_local_app_server_state_running_but_socket_missing_warns_stale_state(self):
        previous_home = os.environ.get("CODEX_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CODEX_HOME"] = tmpdir
            state_path = Path(tmpdir) / "app-server-state.json"
            state_path.write_text(json.dumps({"daemon": {"running": True}}), encoding="utf-8")
            endpoint_path = Path(tmpdir) / "app-server-control" / "app-server-control.sock"
            fake_endpoint = type("FakeEndpoint", (), {"kind": "unix_socket", "socket_path": endpoint_path})()

            class FailedResult:
                ok = False
                exit_code = 21
                error_message = "connection failed (stubbed)"

            try:
                with patch(
                    "pycodex.cli.parser._resolve_exec_remote_endpoint",
                    return_value=("unix://%s" % endpoint_path, fake_endpoint, Path(tmpdir)),
                ):
                    with patch("pycodex.cli.parser.remote_exec_session_connect_and_run", return_value=FailedResult()):
                        stderr = io.StringIO()
                        code = self._main_with_local_http_exec_disabled(["exec", "prompt"], stderr=stderr)
            finally:
                if previous_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_home

        self.assertEqual(code, 21)
        self.assertIn("state says running", stderr.getvalue())
        self.assertIn("app-server state still reports running; socket may be stale or permission-limited.", stderr.getvalue())
        self.assertIn("local app-server socket not found", stderr.getvalue())

    def test_resolve_exec_remote_endpoint_defaults_to_local_app_server_unix_socket(self):
        previous_home = os.environ.get("CODEX_HOME")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["CODEX_HOME"] = tmpdir
                parsed = parse_args(["exec", "prompt"])
                bootstrap_plan = build_exec_config_bootstrap_plan(
                    parsed.exec_cli(),
                    config_toml={},
                )
                remote_arg, endpoint, codex_home = _resolve_exec_remote_endpoint(parsed, bootstrap_plan)

                expected_path = app_server_control_socket_path(tmpdir)
                self.assertEqual(remote_arg, f"unix://{expected_path}")
                self.assertEqual(endpoint.kind, "unix_socket")
                self.assertEqual(endpoint.socket_path, expected_path)
                self.assertEqual(codex_home, Path(tmpdir))
        finally:
            if previous_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_home

    def test_resolve_exec_remote_endpoint_relative_unix_path_uses_exec_cwd(self):
        previous_home = os.environ.get("CODEX_HOME")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config_cwd = Path(tmpdir) / "workdir"
                config_cwd.mkdir()
                os.environ["CODEX_HOME"] = tmpdir
                parsed = parse_args(["-C", str(config_cwd), "exec", "prompt"])
                parsed.remote = "unix://session.sock"

                bootstrap_plan = build_exec_config_bootstrap_plan(
                    parsed.exec_cli(),
                    config_toml={},
                )
                remote_arg, endpoint, codex_home = _resolve_exec_remote_endpoint(parsed, bootstrap_plan)

                self.assertEqual(remote_arg, "unix://session.sock")
                self.assertEqual(endpoint.kind, "unix_socket")
                self.assertEqual(endpoint.socket_path, config_cwd / "session.sock")
                self.assertEqual(codex_home, Path(tmpdir))
        finally:
            if previous_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_home

    def test_resolve_exec_remote_endpoint_invalid_remote_address_raises_value_error(self):
        previous_home = os.environ.get("CODEX_HOME")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["CODEX_HOME"] = tmpdir
                parsed = parse_args(["exec", "prompt"])
                bootstrap_plan = build_exec_config_bootstrap_plan(
                    parsed.exec_cli(),
                    config_toml={},
                )
                parsed = replace(parsed, remote="not-a-remote")

                with self.assertRaisesRegex(ValueError, "invalid remote address `not-a-remote`"):
                    _resolve_exec_remote_endpoint(parsed, bootstrap_plan)
        finally:
            if previous_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_home

    def test_resolve_exec_remote_endpoint_requires_remote_auth_token_env(self):
        previous_home = os.environ.get("CODEX_HOME")
        previous_token = os.environ.get("PYCODEX_TEST_REMOTE_AUTH_TOKEN")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["CODEX_HOME"] = tmpdir
                parsed = parse_args(["exec", "prompt"])
                bootstrap_plan = build_exec_config_bootstrap_plan(
                    parsed.exec_cli(),
                    config_toml={},
                )
                parsed = replace(
                    parsed,
                    remote="ws://127.0.0.1:4500",
                    remote_auth_token_env="PYCODEX_TEST_REMOTE_AUTH_TOKEN",
                )

                with self.assertRaisesRegex(
                    ValueError,
                    "environment variable `PYCODEX_TEST_REMOTE_AUTH_TOKEN` is not set",
                ):
                    _resolve_exec_remote_endpoint(parsed, bootstrap_plan)
        finally:
            if previous_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_home
            if previous_token is None:
                os.environ.pop("PYCODEX_TEST_REMOTE_AUTH_TOKEN", None)
            else:
                os.environ["PYCODEX_TEST_REMOTE_AUTH_TOKEN"] = previous_token

    def legacy_main_without_subcommand_runs_terminal_tui_exec_loop(self):
        # Rust crates/modules:
        # - codex-cli/src/main.rs run_interactive_tui normalizes/dispatches
        #   the no-subcommand entry point into codex_tui::run_main.
        # - codex-tui/src/tui.rs owns terminal mode setup and alternate-screen
        #   entry; --no-alt-screen is the explicit inline escape hatch.
        # Contract: the default interactive entry point enters alternate-screen
        # terminal mode and forwards user prompts through the ported exec runtime.
        stdout = io.StringIO()
        stderr = io.StringIO()
        seen = []

        def fake_exec(prompt):
            seen.append(prompt)
            return 0, "terminal answer\n"

        with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=ExecFunctionActiveThreadRuntime(fake_exec)):
            code = main([], stdout=stdout, stderr=stderr, stdin=io.StringIO("hello\r\n/quit\n"))

        self.assertEqual(code, 0)
        self.assertEqual(seen, ["hello"])
        self.assertIn("\x1b[?1049h", stdout.getvalue())
        self.assertIn("\x1b[?1007h", stdout.getvalue())
        self.assertIn("Codex", stdout.getvalue())
        self.assertIn("terminal answer\n", stdout.getvalue())
        final_screen = stdout.getvalue().rsplit("\x1b[2J", 1)[-1]
        self.assertIn("terminal answer", final_screen)
        self.assertEqual(stdout.getvalue().count("\x1b[2J"), 1)
        self.assertIn("\x1b[?1007l", stdout.getvalue())
        self.assertIn("\x1b[?1049l", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def legacy_main_without_subcommand_hides_exec_stderr_when_reply_is_available(self):
        # Rust crates/modules:
        # - codex-cli/src/main.rs dispatches no-subcommand invocations into
        #   codex_tui::run_main.
        # - codex-tui/src/lib.rs::run_main owns the interactive TUI launch
        #   boundary; non-interactive exec diagnostics must not be rendered as
        #   transcript content for a successful user turn.
        stdout = io.StringIO()
        stderr = io.StringIO()

        def fake_exec(_prompt):
            return 0, "assistant reply\n"

        with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=ExecFunctionActiveThreadRuntime(fake_exec)):
            code = main([], stdout=stdout, stderr=stderr, stdin=io.StringIO("hello\n/quit\n"))

        self.assertEqual(code, 0)
        self.assertIn("assistant reply", stdout.getvalue())
        self.assertNotIn("prepared non-interactive exec plan", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def legacy_main_without_subcommand_shows_exec_stderr_when_turn_fails_without_reply(self):
        # Rust crates/modules:
        # - codex-tui/src/lib.rs::run_main keeps terminal output visible until
        #   exit.
        # - codex-tui/src/startup_error.rs and app error surfaces show failures
        #   inside the TUI instead of silently returning to an input prompt.
        stdout = io.StringIO()
        stderr = io.StringIO()

        def fake_exec(_prompt):
            return 7, "ERROR: live auth failed\nTry `codex login`.\n"

        with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=ExecFunctionActiveThreadRuntime(fake_exec)):
            code = main([], stdout=stdout, stderr=stderr, stdin=io.StringIO("hello\n"))

        self.assertEqual(code, 7)
        self.assertIn("ERROR: live auth failed", stdout.getvalue())
        self.assertIn("Try `codex login`.", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def legacy_main_without_subcommand_appends_long_tui_reply_to_history(self):
        # Rust crates/modules:
        # - codex-tui/src/insert_history.rs inserts finalized history rows into
        #   terminal scrollback instead of repainting and clipping the transcript.
        # - codex-tui/tests/suite/vt100_history.rs verifies inserted rows remain
        #   visible/preserved above the active viewport.
        # Contract: long completed replies are appended as history and are not
        # lost by a post-turn full-screen redraw.
        stdout = io.StringIO()
        stderr = io.StringIO()
        long_answer = "\n".join(f"visible history line {index:02d}" for index in range(1, 61))

        def fake_exec(_prompt):
            return 0, long_answer + "\n"

        with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=ExecFunctionActiveThreadRuntime(fake_exec)):
            code = main([], stdout=stdout, stderr=stderr, stdin=io.StringIO("long answer\n/quit\n"))

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertEqual(output.count("\x1b[2J"), 1)
        self.assertIn("visible history line 01", output)
        self.assertIn("visible history line 30", output)
        self.assertIn("visible history line 60", output)
        self.assertIn(f"  {long_answer.splitlines()[-1]}\n", output)
        self.assertEqual(stderr.getvalue(), "")

    def legacy_main_without_subcommand_auto_pages_long_tui_reply_for_tty(self):
        # Rust crates/modules:
        # - codex-tui/src/pager_overlay.rs owns TranscriptOverlay and PagerView.
        # - codex-tui/src/keymap.rs binds global.open_transcript and pager
        #   PageUp/PageDown/scroll actions.
        # Contract: in an interactive alternate-screen TUI, long transcript
        # content is readable through an in-TUI pager instead of depending on
        # terminal scrollback outside the alternate screen.
        class TtyInput(io.StringIO):
            def isatty(self):
                return True

        stdout = io.StringIO()
        stderr = io.StringIO()
        long_answer = "\n".join(f"pager visible line {index:02d}" for index in range(1, 25))

        def fake_exec(_prompt):
            return 0, long_answer + "\n"

        with patch("pycodex.tui.shutil.get_terminal_size", return_value=os.terminal_size((40, 10))):
            with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=ExecFunctionActiveThreadRuntime(fake_exec)):
                code = main([], stdout=stdout, stderr=stderr, stdin=TtyInput("long\n\n\n\nq\nquit\n"))

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("T R A N S C R I P T", output)
        self.assertIn("Enter/space next", output)
        self.assertIn("pager visible line 01", output)
        self.assertIn("pager visible line 18", output)
        self.assertIn("-- ", output)
        self.assertEqual(stderr.getvalue(), "")

    def legacy_main_without_subcommand_transcript_command_opens_history_pager(self):
        # Rust source: codex-tui/src/app/input.rs dispatches the
        # global.open_transcript keybinding into the transcript overlay.
        stdout = io.StringIO()
        stderr = io.StringIO()

        def fake_exec(_prompt):
            return 0, "short transcript answer\n"

        with patch("pycodex.tui.shutil.get_terminal_size", return_value=os.terminal_size((60, 12))):
            with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=ExecFunctionActiveThreadRuntime(fake_exec)):
                code = main([], stdout=stdout, stderr=stderr, stdin=io.StringIO("hello\n/transcript\nq\nquit\n"))

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("T R A N S C R I P T", output)
        self.assertIn("you", output)
        self.assertIn("hello", output)
        self.assertIn("short transcript answer", output)
        self.assertEqual(stderr.getvalue(), "")

    def legacy_main_without_subcommand_no_alt_screen_stays_inline(self):
        # Rust crate/module/test source:
        # - codex-tui/src/cli.rs exposes --no-alt-screen.
        # - codex-tui/src/lib.rs::determine_alt_screen_mode returns false when
        #   no_alt_screen is true.
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch(
            "pycodex.cli.parser._build_tui_core_active_thread_runtime",
            return_value=ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "")),
        ):
            code = main(["--no-alt-screen"], stdout=stdout, stderr=stderr, stdin=io.StringIO("/quit\n"))

        self.assertEqual(code, 0)
        self.assertNotIn("\x1b[?1049h", stdout.getvalue())
        self.assertNotIn("\x1b[?1049l", stdout.getvalue())
        self.assertIn("Codex", stdout.getvalue())

    def test_main_without_subcommand_tty_uses_textual_even_with_no_alt_screen(self):
        # Rust/Python product-path contract:
        # - codex-tui/src/tui.rs owns the real interactive terminal loop.
        # - pycodex.tui.textual_runtime.should_use_textual_tui is the Python
        #   product-entry guard for real TTY sessions.
        # Contract: --no-alt-screen does not revive the legacy inline renderer
        # for real TTY use; it only remains relevant to non-TTY compatibility
        # harnesses while they are migrated.
        class TtyInput(io.StringIO):
            def isatty(self):
                return True

        class TtyOutput(io.StringIO):
            def isatty(self):
                return True

        stdout = TtyOutput()
        stderr = io.StringIO()
        runtime = ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused"))

        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=runtime):
                with patch("pycodex.tui.textual_runtime.run_textual_tui", return_value=0) as run_textual:
                    code = main(
                        ["--no-alt-screen"],
                        stdout=stdout,
                        stderr=stderr,
                        stdin=TtyInput("/quit\n"),
                        stdin_is_terminal=True,
                    )

        self.assertEqual(code, 0)
        run_textual.assert_called_once_with(active_thread_runtime=runtime, stdout=stdout, use_alt_screen=False)
        self.assertEqual(stderr.getvalue(), "")

    def test_main_without_subcommand_tty_respects_tui_alternate_screen_config(self):
        # Rust source contract:
        # - codex-rs/tui/src/lib.rs::determine_alt_screen_mode disables the
        #   alternate screen when Config.tui.alternate_screen is Never, even
        #   without the CLI --no-alt-screen flag.
        class TtyInput(io.StringIO):
            def isatty(self):
                return True

        class TtyOutput(io.StringIO):
            def isatty(self):
                return True

        stdout = TtyOutput()
        stderr = io.StringIO()
        runtime = ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused"))
        runtime.session_config = SimpleNamespace(tui_alternate_screen=AltScreenMode.NEVER)

        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=runtime):
                with patch("pycodex.tui.textual_runtime.run_textual_tui", return_value=0) as run_textual:
                    code = main(
                        [],
                        stdout=stdout,
                        stderr=stderr,
                        stdin=TtyInput("/quit\n"),
                        stdin_is_terminal=True,
                    )

        self.assertEqual(code, 0)
        run_textual.assert_called_once_with(active_thread_runtime=runtime, stdout=stdout, use_alt_screen=False)
        self.assertEqual(stderr.getvalue(), "")

    def test_tui_core_runtime_reads_reasoning_summary_from_config_toml(self):
        # Rust source contract:
        # - codex-core/src/config/mod.rs loads Config.model_reasoning_summary
        #   from config.toml.
        # - codex-cli/src/main.rs::run_interactive_tui passes loaded Config
        #   into codex_tui::run_main.
        # Python's Textual TUI must receive the same value through the active
        # core runtime session config so reasoning summary visibility is
        # controlled by config.toml rather than a local UI default.
        parsed = parse_args([])
        codex_home = Path("C:/Users/test/.codex")

        with patch("pycodex.cli.parser.find_codex_home", return_value=str(codex_home)):
            with patch(
                "pycodex.cli.parser.read_toml_mapping",
                return_value={"model": "gpt-5.5", "model_reasoning_summary": "none"},
            ):
                with patch(
                    "pycodex.cli.parser.maybe_migrate_personality",
                    return_value=PersonalityMigrationStatus.SKIPPED_MARKER,
                ):
                    with patch("pycodex.cli.parser.ensure_exec_trusted_directory"):
                        with patch("pycodex.cli.parser._execpolicy_rules_for_local_http_exec", return_value=()):
                            with patch("pycodex.cli.parser.read_auth_json", return_value={}):
                                with patch(
                                    "pycodex.cli.parser.build_default_core_exec_runtime",
                                    return_value=(
                                        SimpleNamespace(thread_id=None, session_id=None),
                                        SimpleNamespace(),
                                        SimpleNamespace(slug="gpt-5.5"),
                                        None,
                                    ),
                                ):
                                    runtime = _build_tui_core_active_thread_runtime(parsed, stderr=io.StringIO())

        self.assertEqual(runtime.session_config.model_reasoning_summary, "none")

    def test_main_without_subcommand_non_tty_refuses_after_runtime_setup(self):
        # Rust source/native contract:
        # - codex-cli/src/main.rs::run_interactive_tui dispatches into
        #   codex_tui::run_main for ordinary non-TERM=dumb sessions.
        # - codex-tui/src/tui.rs::init then rejects non-terminal stdin with
        #   `stdin is not a terminal`.
        # Native evidence:
        #   `"/quit" | codex.exe --no-alt-screen -C <repo> -s read-only -a never`
        #   exits 1 and prints `Error: stdin is not a terminal`.
        stdout = io.StringIO()
        stderr = io.StringIO()
        runtime = ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused"))

        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=runtime) as build_runtime:
                code = main(
                    ["--no-alt-screen"],
                    stdout=stdout,
                    stderr=stderr,
                    stdin=io.StringIO("/quit\n"),
                    stdin_is_terminal=False,
                )

        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "Error: stdin is not a terminal\n")
        build_runtime.assert_called_once()

    def test_main_without_subcommand_term_dumb_non_tty_refuses_interactive_tui(self):
        # Rust source/native contract:
        # - codex-cli/src/main.rs::run_interactive_tui refuses TERM=dumb when
        #   stdin/stderr are not TTYs because the confirmation prompt cannot be
        #   shown safely.
        # - Native run:
        #   `"/quit" | codex.exe --no-alt-screen ...` returns 1 and prints the
        #   same ERROR line before codex-tui starts.
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch.dict(os.environ, {"TERM": "dumb"}):
            with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime") as build_runtime:
                code = main(
                    ["--no-alt-screen"],
                    stdout=stdout,
                    stderr=stderr,
                    stdin=io.StringIO("/quit\n"),
                    stdin_is_terminal=False,
                )

        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn('ERROR: TERM is set to "dumb". Refusing to start the interactive TUI', stderr.getvalue())
        build_runtime.assert_not_called()

    def test_native_and_python_term_dumb_non_tty_guard_match_when_enabled(self):
        # Rust crate/module contract:
        # - codex-cli/src/main.rs::run_interactive_tui owns the TERM=dumb
        #   startup guard before dispatching into codex-tui.
        # - codex-tui/src/cli.rs exposes --no-alt-screen so the same inline
        #   entry path can be compared without alternate-screen capture.
        # Native evidence command:
        #   `"/quit" | codex.exe --no-alt-screen -C <repo> -s read-only -a never`
        # Python parity:
        #   `"/quit" | python -m pycodex --no-alt-screen -C <repo> -s read-only -a never`
        # The opt-in gate keeps default CI independent from a locally built Rust
        # binary while preserving an executable native comparison harness.
        if os.environ.get("PYCODEX_RUN_NATIVE_TUI_COMPARISON") != "1":
            self.skipTest("set PYCODEX_RUN_NATIVE_TUI_COMPARISON=1 to compare against a local Rust codex.exe")

        repo_root = Path(__file__).resolve().parents[1]
        default_native = Path(
            r"C:\Users\27605\AppData\Local\codex-rust-target\codex-rs\debug\codex.exe"
        )
        native_exe = Path(os.environ.get("PYCODEX_NATIVE_CODEX_EXE", str(default_native)))
        if not native_exe.exists():
            self.skipTest(f"native codex executable not found: {native_exe}")

        env = os.environ.copy()
        env["TERM"] = "dumb"
        expected = (
            'ERROR: TERM is set to "dumb". Refusing to start the interactive TUI because '
            "no terminal is available for a confirmation prompt (stdin/stderr is not a TTY). "
            "Run in a supported terminal or unset TERM."
        )
        common_args = ["--no-alt-screen", "-C", str(repo_root), "-s", "read-only", "-a", "never"]
        native = subprocess.run(
            [str(native_exe), *common_args],
            input="/quit\n",
            text=True,
            capture_output=True,
            cwd=str(repo_root),
            env=env,
            timeout=10,
        )
        python = subprocess.run(
            [sys.executable, "-m", "pycodex", *common_args],
            input="/quit\n",
            text=True,
            capture_output=True,
            cwd=str(repo_root),
            env=env,
            timeout=15,
        )

        self.assertEqual(native.returncode, 1, native.stdout + native.stderr)
        self.assertEqual(python.returncode, 1, python.stdout + python.stderr)
        self.assertIn(expected, native.stdout + native.stderr)
        self.assertIn(expected, python.stdout + python.stderr)
        self.assertEqual(native.stdout.strip(), python.stdout.strip())
        self.assertEqual(native.stderr.strip(), python.stderr.strip())

    def test_main_mcp_server_not_implemented(self):
        stderr = io.StringIO()

        code = main(["mcp-server"], stderr=stderr)

        self.assertEqual(code, 64)
        self.assertIn("command 'mcp-server' is not implemented in this Python port.", stderr.getvalue())
        self.assertIn("launch the Rust `codex-mcp-server` binary", stderr.getvalue())

    def test_main_mcp_server_runtime_handles_initialize_and_tools_list(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "clientInfo": {
                                "name": "test-client",
                                "version": "0.0.1",
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/list",
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            code = main(
                ["mcp-server"],
                stdout=stdout,
                stderr=stderr,
                stdin=payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("starting mcp-server stdio runtime.", stderr.getvalue())
        lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)

        initialize = json.loads(lines[0])
        tools_list = json.loads(lines[1])
        self.assertEqual(initialize["id"], 1)
        self.assertIn("result", initialize)
        self.assertIn("capabilities", initialize["result"])
        self.assertEqual(tools_list["id"], 2)
        names = {tool["name"] for tool in tools_list["result"]["tools"]}
        self.assertIn("codex", names)
        self.assertIn("codex-reply", names)

    def test_main_mcp_server_runtime_notifications_initialized_is_acked(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "clientInfo": {
                                "name": "test-client",
                                "version": "0.0.1",
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                    }
                ),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/list",
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            code = main(
                ["mcp-server"],
                stdout=stdout,
                stderr=stderr,
                stdin=payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(code, 0)
        lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["id"], 1)
        self.assertEqual(json.loads(lines[1])["id"], 2)

    def test_main_mcp_server_runtime_initialize_twice_returns_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                    }
                ),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "initialize",
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            code = main(
                ["mcp-server"],
                stdout=stdout,
                stderr=stderr,
                stdin=payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(code, 0)
        lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        second = json.loads(lines[1])
        self.assertEqual(second["id"], 2)
        self.assertIn("error", second)
        self.assertEqual(second["error"]["code"], -32600)
        self.assertEqual(second["error"]["message"], "initialize called more than once")

    def test_main_mcp_server_runtime_codex_tool_rejects_missing_prompt(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "codex", "arguments": {}},
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            code = main(
                ["mcp-server"],
                stdout=stdout,
                stderr=stderr,
                stdin=payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("starting mcp-server stdio runtime.", stderr.getvalue())
        line = [line for line in stdout.getvalue().splitlines() if line.strip()][0]
        call = json.loads(line)
        self.assertEqual(call["id"], 1)
        self.assertTrue(call["result"].get("isError"))
        self.assertIn(
            "Missing arguments for codex tool-call; the `prompt` field is required.",
            call["result"]["content"][0]["text"],
        )

    def test_main_mcp_server_runtime_tools_call_requires_name(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"arguments": {"prompt": "hello"}},
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            code = main(
                ["mcp-server"],
                stdout=stdout,
                stderr=stderr,
                stdin=payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(code, 0)
        call = json.loads([line for line in stdout.getvalue().splitlines() if line.strip()][0])
        self.assertTrue(call["result"].get("isError"))
        self.assertIn("Unknown tool 'None'", call["result"]["content"][0]["text"])

    def test_main_mcp_server_runtime_rejects_unknown_codex_argument(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "codex",
                            "arguments": {
                                "prompt": "hello",
                                "unknown": "field",
                            },
                        },
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            code = main(
                ["mcp-server"],
                stdout=stdout,
                stderr=stderr,
                stdin=payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(code, 0)
        call = json.loads([line for line in stdout.getvalue().splitlines() if line.strip()][0])
        self.assertTrue(call["result"].get("isError"))
        self.assertIn("Failed to parse configuration for Codex tool: unknown field", call["result"]["content"][0]["text"])

    def test_main_mcp_server_runtime_notification_prefixed_methods_are_acknowledged_without_response(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "id": 1,
                    }
                ),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "notifications/something",
                    }
                ),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "initialized",
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            code = main(
                ["mcp-server"],
                stdout=stdout,
                stderr=stderr,
                stdin=payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(code, 0)
        lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(lines, [])

    def test_main_mcp_server_runtime_codex_tool_creates_thread(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "codex",
                            "arguments": {
                                "prompt": "hello world",
                                "model": "gpt-5",
                            },
                        },
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            code = main(
                ["mcp-server"],
                stdout=stdout,
                stderr=stderr,
                stdin=payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(code, 0)
        self.assertIn("starting mcp-server stdio runtime.", stderr.getvalue())
        lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)

        call = json.loads(lines[0])
        self.assertEqual(call["id"], 1)
        self.assertIn("result", call)
        self.assertIn("structuredContent", call["result"])
        self.assertEqual(call["result"]["structuredContent"].get("content"), "stub started")

    def test_main_mcp_server_runtime_codex_reply_missing_thread(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "codex-reply",
                            "arguments": {
                                "threadId": "missing-thread",
                                "prompt": "continue please",
                            },
                        },
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            code = main(
                ["mcp-server"],
                stdout=stdout,
                stderr=stderr,
                stdin=payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(code, 0)
        lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)

        call = json.loads(lines[0])
        self.assertEqual(call["id"], 1)
        self.assertTrue(call["result"].get("isError"))
        self.assertIn("Session not found", call["result"]["content"][0]["text"])

    def test_main_mcp_server_runtime_codex_reply_followed_by_success(self):
        stdout_create = io.StringIO()
        stdout_reply = io.StringIO()
        stderr = io.StringIO()

        create_payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "codex",
                            "arguments": {
                                "prompt": "first prompt",
                            },
                        },
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            create_code = main(
                ["mcp-server"],
                stdout=stdout_create,
                stderr=stderr,
                stdin=create_payload,
            )
            create_lines = [
                line
                for line in stdout_create.getvalue().splitlines()
                if line.strip()
            ]
            self.assertEqual(create_code, 0)
            self.assertEqual(len(create_lines), 1)
            create_call = json.loads(create_lines[0])
            thread_id = create_call["result"]["structuredContent"]["threadId"]

            reply_payload = "\n".join(
                [
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {
                                "name": "codex-reply",
                                "arguments": {
                                    "threadId": thread_id,
                                    "prompt": "second prompt",
                                },
                            },
                        }
                    ),
                    "",
                ]
            )

            reply_code = main(
                ["mcp-server"],
                stdout=stdout_reply,
                stderr=stderr,
                stdin=reply_payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(reply_code, 0)
        reply_lines = [line for line in stdout_reply.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(reply_lines), 1)

        reply_call = json.loads(reply_lines[0])
        self.assertEqual(reply_call["id"], 2)
        self.assertIn("result", reply_call)
        self.assertEqual(reply_call["result"].get("isError"), False)
        self.assertEqual(reply_call["result"]["structuredContent"].get("threadId"), thread_id)

    def test_main_mcp_server_runtime_tools_list_has_expected_schema_fields(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            code = main(
                ["mcp-server"],
                stdout=stdout,
                stderr=stderr,
                stdin=payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(code, 0)
        line = [line for line in stdout.getvalue().splitlines() if line.strip()][0]
        tools_list = json.loads(line)["result"]
        codex = next(item for item in tools_list["tools"] if item["name"] == "codex")
        codex_reply = next(
            item for item in tools_list["tools"] if item["name"] == "codex-reply"
        )
        self.assertEqual(codex["outputSchema"]["required"], ["threadId", "content"])
        self.assertIn("prompt", codex["inputSchema"]["required"])
        self.assertIn("threadId", codex_reply["inputSchema"]["properties"])
        self.assertIn("conversationId", codex_reply["inputSchema"]["properties"])
        self.assertEqual(codex_reply["inputSchema"]["required"], ["prompt"])

    def test_main_mcp_server_runtime_codex_reply_accepts_conversation_id_alias(self):
        stdout_create = io.StringIO()
        stderr = io.StringIO()
        payload = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "codex",
                            "arguments": {
                                "prompt": "first prompt",
                            },
                        },
                    }
                ),
                "",
            ]
        )

        previous = os.environ.get("PYCODEX_MCP_SERVER_RUNTIME")
        os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = "1"
        try:
            create_code = main(["mcp-server"], stdout=stdout_create, stderr=stderr, stdin=payload)
            tools_list = [
                line
                for line in stdout_create.getvalue().splitlines()
                if line.strip()
            ]
            self.assertEqual(create_code, 0)
            create_call = json.loads(tools_list[0])
            thread_id = create_call["result"]["structuredContent"]["threadId"]

            stdout_reply = io.StringIO()
            reply_payload = "\n".join(
                [
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {
                                "name": "codex-reply",
                                "arguments": {
                                    "conversationId": thread_id,
                                    "prompt": "continue",
                                },
                            },
                        }
                    ),
                    "",
                ]
            )
            reply_code = main(
                ["mcp-server"],
                stdout=stdout_reply,
                stderr=stderr,
                stdin=reply_payload,
            )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_MCP_SERVER_RUNTIME", None)
            else:
                os.environ["PYCODEX_MCP_SERVER_RUNTIME"] = previous

        self.assertEqual(reply_code, 0)
        reply_call = json.loads([line for line in stdout_reply.getvalue().splitlines() if line.strip()][0])
        self.assertEqual(reply_call["result"]["structuredContent"]["threadId"], thread_id)

    def test_main_resume_without_fallback_uses_textual_tui_path(self):
        class TtyInput(io.StringIO):
            def isatty(self):
                return True

        class TtyOutput(io.StringIO):
            def isatty(self):
                return True

        stdout = TtyOutput()
        stderr = io.StringIO()
        runtime = ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused"))

        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=runtime):
                with patch("pycodex.tui.textual_runtime.run_textual_tui", return_value=0) as run_textual:
                    code = main(
                        ["resume", "--last"],
                        stdout=stdout,
                        stderr=stderr,
                        stdin=TtyInput("continue\n/quit\n"),
                        stdin_is_terminal=True,
                    )

        self.assertEqual(code, 0)
        self.assertIn("resume request parsed with session_id=None, last=True, all=False, include_non_interactive=False.", stderr.getvalue())
        called_runtime = run_textual.call_args.kwargs["active_thread_runtime"]
        self.assertIsInstance(called_runtime, TuiAppRuntime)
        self.assertIs(called_runtime.active_thread_runtime, runtime)
        self.assertEqual(called_runtime.startup_session_action, "resume")
        self.assertTrue(called_runtime.startup_session_last)
        self.assertTrue(run_textual.call_args.kwargs["use_alt_screen"])
        self.assertIs(run_textual.call_args.kwargs["stdout"], stdout)

    def test_main_resume_with_exec_fallback_uses_noninteractive_resume_exec(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        previous = os.environ.get("PYCODEX_RESUME_EXEC_FALLBACK")
        os.environ["PYCODEX_RESUME_EXEC_FALLBACK"] = "1"
        try:
            with patch("pycodex.cli.parser._run_noninteractive_exec", return_value=7) as run_noninteractive:
                code = main(
                    ["resume", "abc", "--include-non-interactive", "--all"],
                    stdout=stdout,
                    stdin="continue from stdin\n",
                    stdin_is_terminal=False,
                    stderr=stderr,
                )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_RESUME_EXEC_FALLBACK", None)
            else:
                os.environ["PYCODEX_RESUME_EXEC_FALLBACK"] = previous

        self.assertEqual(code, 7)
        resumed_parsed = run_noninteractive.call_args.args[0]
        self.assertEqual(resumed_parsed.command_args, ("abc", "--all"))
        self.assertIs(run_noninteractive.call_args.kwargs["stdout"], stdout)
        self.assertEqual(run_noninteractive.call_args.kwargs["stdin"], "continue from stdin\n")
        self.assertFalse(run_noninteractive.call_args.kwargs["stdin_is_terminal"])

    def test_main_fork_routes_to_textual_tui_startup(self):
        stderr = io.StringIO()
        with patch("pycodex.cli.parser._run_tui", return_value=13) as run_tui:
            code = main(["fork", "abc"], stderr=stderr)

        self.assertEqual(code, 13)
        run_tui.assert_called_once()
        self.assertIn("fork request parsed with session_id='abc'", stderr.getvalue())
        self.assertNotIn("non-interactive fallback mode", stderr.getvalue())

    def test_main_fork_without_id_enters_textual_fork_picker_startup(self):
        # Rust source/test contract:
        # - codex-rs/cli/src/main.rs::finalize_fork_interactive sets
        #   fork_picker when `codex fork` has no session id and no --last.
        # - Rust test: fork_picker_logic_none_and_not_last.
        class TtyInput(io.StringIO):
            def isatty(self):
                return True

        class TtyOutput(io.StringIO):
            def isatty(self):
                return True

        stdout = TtyOutput()
        stderr = io.StringIO()
        runtime = ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused"))

        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            with patch("pycodex.cli.parser._build_tui_core_active_thread_runtime", return_value=runtime):
                with patch("pycodex.tui.textual_runtime.run_textual_tui", return_value=0) as run_textual:
                    code = main(
                        ["fork"],
                        stdout=stdout,
                        stderr=stderr,
                        stdin=TtyInput("/quit\n"),
                        stdin_is_terminal=True,
                    )

        self.assertEqual(code, 0)
        called_runtime = run_textual.call_args.kwargs["active_thread_runtime"]
        self.assertTrue(run_textual.call_args.kwargs["use_alt_screen"])
        self.assertIsInstance(called_runtime, TuiAppRuntime)
        self.assertIs(called_runtime.active_thread_runtime, runtime)
        self.assertEqual(called_runtime.startup_session_action, "fork")
        self.assertIsNone(called_runtime.startup_session_id)
        self.assertFalse(called_runtime.startup_session_last)
        self.assertFalse(called_runtime.startup_session_show_all)
        self.assertIn("fork request parsed with session_id=None, last=False, all=False.", stderr.getvalue())

    def test_main_fork_with_exec_fallback_uses_noninteractive_fork_exec(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        previous = os.environ.get("PYCODEX_FORK_EXEC_FALLBACK")
        os.environ["PYCODEX_FORK_EXEC_FALLBACK"] = "1"
        try:
            with patch("pycodex.cli.parser._run_noninteractive_exec", return_value=11) as run_noninteractive:
                code = main(
                    ["fork", "abc", "--all"],
                    stdout=stdout,
                    stdin="fork from stdin\n",
                    stdin_is_terminal=False,
                    stderr=stderr,
                )
        finally:
            if previous is None:
                os.environ.pop("PYCODEX_FORK_EXEC_FALLBACK", None)
            else:
                os.environ["PYCODEX_FORK_EXEC_FALLBACK"] = previous

        self.assertEqual(code, 11)
        forked_parsed = run_noninteractive.call_args.args[0]
        self.assertEqual(forked_parsed.command, "resume")
        self.assertEqual(forked_parsed.command_args, ("abc", "--all"))
        self.assertIs(run_noninteractive.call_args.kwargs["stdout"], stdout)
        self.assertEqual(run_noninteractive.call_args.kwargs["stdin"], "fork from stdin\n")
        self.assertFalse(run_noninteractive.call_args.kwargs["stdin_is_terminal"])

    def test_main_remote_control_start_is_implemented(self):
        stderr = io.StringIO()
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["remote-control", "start"], stdout=stdout, stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Starting app-server daemon with remote control enabled", stdout.getvalue())

    def test_main_remote_control_start_and_stop_json(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                start_code = main(["remote-control", "start", "--json"], stdout=stdout, stderr=stderr)
                self.assertEqual(start_code, 0)
                self.assertEqual(stderr.getvalue(), "")
                start_payload = json.loads(stdout.getvalue().strip().split("\n")[-1])
                self.assertEqual(start_payload.get("mode"), "daemon")
                self.assertEqual(start_payload.get("status"), "connected")
                self.assertIsInstance(start_payload.get("daemon"), dict)
                self.assertIn("pid", start_payload["daemon"])
                self.assertEqual(start_payload["daemon"].get("backend"), "pid")
                self.assertIn("managedCodexPath", start_payload["daemon"])
                self.assertIn("socketPath", start_payload["daemon"])

                stop_stdout = io.StringIO()
                stop_stderr = io.StringIO()
                stop_code = main(["remote-control", "stop", "--json"], stdout=stop_stdout, stderr=stop_stderr)
                self.assertEqual(stop_code, 0)
                stop_payload = json.loads(stop_stdout.getvalue().strip())
                self.assertEqual(stop_payload.get("status"), "stopped")
                self.assertIsInstance(stop_payload.get("daemon"), dict)
                self.assertIn("status", stop_payload["daemon"])
                self.assertEqual(stop_payload["daemon"].get("status"), "stopped")
                self.assertIn("pid", stop_payload["daemon"])
                self.assertIn("backend", stop_payload["daemon"])
                self.assertIn("managedCodexVersion", stop_payload["daemon"])
                self.assertEqual(stop_stderr.getvalue(), "")

                final_state = json.loads((Path(tmpdir) / "app-server-state.json").read_text(encoding="utf-8"))
                self.assertEqual(final_state.get("daemon", {}).get("running"), False)
                self.assertEqual(final_state.get("remote_control", {}).get("status"), "disabled")
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

    def test_main_remote_control_stop_when_not_running(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["remote-control", "stop"], stdout=stdout, stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().strip(), "Remote control is not running.")

    def test_main_remote_control_stop_not_running_json(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(["remote-control", "stop", "--json"], stdout=stdout, stderr=stderr)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue().strip())
        self.assertEqual(payload.get("status"), "notRunning")
        self.assertIsInstance(payload.get("daemon"), dict)
        self.assertEqual(payload["daemon"].get("status"), "notRunning")
        self.assertIn("managedCodexPath", payload["daemon"])
        self.assertIn("cliVersion", payload["daemon"])
        self.assertNotIn("backend", payload["daemon"])
        self.assertNotIn("pid", payload["daemon"])

    def test_main_app_server_daemon_bootstrap_json(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                code = main(
                    ["app-server", "daemon", "bootstrap", "--remote-control"],
                    stdout=stdout,
                    stderr=stderr,
                )
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue().strip())
        self.assertEqual(payload.get("status"), "bootstrapped")
        self.assertEqual(payload.get("backend"), "pid")
        self.assertTrue(payload.get("autoUpdateEnabled"))
        self.assertTrue(payload.get("remoteControlEnabled"))
        self.assertIsInstance(payload.get("managedCodexPath"), str)
        self.assertIsInstance(payload.get("cliVersion"), str)
        self.assertIn("socketPath", payload)

    def test_main_app_server_daemon_start_and_restart_json(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                start_code = main(["app-server", "daemon", "start"], stdout=stdout, stderr=stderr)
                self.assertEqual(start_code, 0)
                self.assertEqual(stderr.getvalue(), "")
                start_payload = json.loads(stdout.getvalue().strip())
                self.assertEqual(start_payload.get("status"), "started")
                self.assertIn("pid", start_payload)
                self.assertIn("backend", start_payload)
                self.assertIn("managedCodexPath", start_payload)

                start_again_stdout = io.StringIO()
                start_again_stderr = io.StringIO()
                start_again_code = main(
                    ["app-server", "daemon", "start"],
                    stdout=start_again_stdout,
                    stderr=start_again_stderr,
                )
                self.assertEqual(start_again_code, 0)
                self.assertEqual(start_again_stderr.getvalue(), "")
                already_running_payload = json.loads(start_again_stdout.getvalue().strip())
                self.assertEqual(already_running_payload.get("status"), "alreadyRunning")
                self.assertNotIn("pid", already_running_payload)
                self.assertIn("backend", already_running_payload)

                restart_stdout = io.StringIO()
                restart_stderr = io.StringIO()
                restart_code = main(
                    ["app-server", "daemon", "restart"],
                    stdout=restart_stdout,
                    stderr=restart_stderr,
                )
                self.assertEqual(restart_code, 0)
                self.assertEqual(restart_stderr.getvalue(), "")
                restart_payload = json.loads(restart_stdout.getvalue().strip())
                self.assertEqual(restart_payload.get("status"), "restarted")
                self.assertIn("pid", restart_payload)
                self.assertIn("backend", restart_payload)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

    def test_main_app_server_daemon_stop_and_not_running_json(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                start_code = main(["app-server", "daemon", "start"], stdout=stdout, stderr=stderr)
                self.assertEqual(start_code, 0)

                stdout.seek(0)
                stdout.truncate(0)
                stderr.seek(0)
                stderr.truncate(0)

                stop_code = main(["app-server", "daemon", "stop"], stdout=stdout, stderr=stderr)
                self.assertEqual(stop_code, 0)
                self.assertEqual(stderr.getvalue(), "")
                stop_payload = json.loads(stdout.getvalue().strip())
                self.assertEqual(stop_payload.get("status"), "stopped")
                self.assertIn("backend", stop_payload)
                self.assertNotIn("pid", stop_payload)

                stdout.seek(0)
                stdout.truncate(0)
                stderr.seek(0)
                stderr.truncate(0)

                not_running_code = main(["app-server", "daemon", "stop"], stdout=stdout, stderr=stderr)
                self.assertEqual(not_running_code, 0)
                payload = json.loads(stdout.getvalue().strip())
                self.assertEqual(payload.get("status"), "notRunning")
                self.assertNotIn("backend", payload)
                self.assertNotIn("pid", payload)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

    def test_main_app_server_daemon_version_and_remote_control_toggle_json(self):
        start_stdout = io.StringIO()
        start_stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            try:
                start_code = main(
                    ["app-server", "daemon", "start"],
                    stdout=start_stdout,
                    stderr=start_stderr,
                )
                self.assertEqual(start_code, 0)
                self.assertEqual(start_stderr.getvalue(), "")

                version_stdout = io.StringIO()
                version_stderr = io.StringIO()
                version_code = main(
                    ["app-server", "daemon", "version"],
                    stdout=version_stdout,
                    stderr=version_stderr,
                )
                self.assertEqual(version_code, 0)
                version_payload = json.loads(version_stdout.getvalue().strip())
                self.assertEqual(version_payload.get("status"), "running")
                self.assertNotIn("pid", version_payload)

                stop_code = main(
                    ["app-server", "daemon", "stop"],
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
                self.assertEqual(stop_code, 0)

                failed_version_stderr = io.StringIO()
                failed_version_code = main(
                    ["app-server", "daemon", "version"],
                    stdout=io.StringIO(),
                    stderr=failed_version_stderr,
                )
                self.assertEqual(failed_version_code, 2)
                self.assertIn("not running", failed_version_stderr.getvalue())

                enable_again_stdout = io.StringIO()
                enable_code = main(
                    ["app-server", "daemon", "enable-remote-control"],
                    stdout=enable_again_stdout,
                    stderr=io.StringIO(),
                )
                self.assertEqual(enable_code, 0)
                enable_payload = json.loads(enable_again_stdout.getvalue().strip())
                self.assertEqual(enable_payload.get("status"), "enabled")
                self.assertTrue(enable_payload.get("remoteControlEnabled"))

                enable_stdout = io.StringIO()
                already_enabled_code = main(
                    ["app-server", "daemon", "enable-remote-control"],
                    stdout=enable_stdout,
                    stderr=io.StringIO(),
                )
                self.assertEqual(already_enabled_code, 0)
                already_enabled_payload = json.loads(enable_stdout.getvalue().strip())
                self.assertEqual(already_enabled_payload.get("status"), "alreadyEnabled")

                disable_stdout = io.StringIO()
                disable_code = main(
                    ["app-server", "daemon", "disable-remote-control"],
                    stdout=disable_stdout,
                    stderr=io.StringIO(),
                )
                self.assertEqual(disable_code, 0)
                disable_payload = json.loads(disable_stdout.getvalue().strip())
                self.assertEqual(disable_payload.get("status"), "disabled")
                self.assertFalse(disable_payload.get("remoteControlEnabled"))

                disable_again_stdout = io.StringIO()
                disable_again_code = main(
                    ["app-server", "daemon", "disable-remote-control"],
                    stdout=disable_again_stdout,
                    stderr=io.StringIO(),
                )
                self.assertEqual(disable_again_code, 0)
                already_disabled_payload = json.loads(disable_again_stdout.getvalue().strip())
                self.assertEqual(already_disabled_payload.get("status"), "alreadyDisabled")
                self.assertFalse(already_disabled_payload.get("remoteControlEnabled"))

            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

    def test_main_command_help_placeholder(self):
        stdout = io.StringIO()

        code = main(["plugin", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex plugin <COMMAND>", stdout.getvalue())

        stdout_marketplace = io.StringIO()
        code = main(["plugin", "marketplace", "--help"], stdout=stdout_marketplace)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex plugin marketplace <COMMAND>", stdout_marketplace.getvalue())

        stdout_marketplace_add = io.StringIO()
        code = main(["plugin", "marketplace", "add", "--help"], stdout=stdout_marketplace_add)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex plugin marketplace add <SOURCE>", stdout_marketplace_add.getvalue())

        stdout_add = io.StringIO()
        code = main(["plugin", "add", "--help"], stdout=stdout_add)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex plugin add <PLUGIN>[@<MARKETPLACE>]", stdout_add.getvalue())

        stdout_list = io.StringIO()
        code = main(["plugin", "list", "--help"], stdout=stdout_list)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex plugin list [--marketplace MARKETPLACE]", stdout_list.getvalue())

    def test_main_features_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["features", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex features", stdout.getvalue())

    def test_main_features_subcommand_help_prints_usage(self):
        stdout = io.StringIO()

        code = main(["features", "list", "--help"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex features", stdout.getvalue())

    def test_main_features_list_with_search_sets_web_search_override(self):
        with patch("pycodex.cli.parser.run_features_command", return_value=0) as run_features:
            code = main(["--search", "features", "list"])

        self.assertEqual(code, 0)
        self.assertIn("web_search=live", run_features.call_args.kwargs["raw_config_overrides"])

    def test_features_enable_and_disable_parse_feature_name(self):
        enabled = parse_args(["features", "enable", "unified_exec"]).features_cli()
        disabled = parse_args(["features", "disable", "shell_tool"]).features_cli()

        self.assertIs(enabled.subcommand, FeaturesSubcommand.ENABLE)
        self.assertEqual(enabled.args.feature, "unified_exec")
        self.assertIs(disabled.subcommand, FeaturesSubcommand.DISABLE)
        self.assertEqual(disabled.args.feature, "shell_tool")

    def test_features_list_parses_without_extra_args(self):
        listed = parse_features_args(["list"])

        self.assertIs(listed.subcommand, FeaturesSubcommand.LIST)
        self.assertIsNone(listed.args)

    def test_features_subcommands_reject_bad_shape(self):
        for args, pattern in (
            (["features"], "features requires a subcommand"),
            (["features", "list", "extra"], "does not accept extra"),
            (["features", "enable"], "requires exactly one feature"),
            (["features", "enable", "does_not_exist"], "Unknown feature flag"),
        ):
            with self.subTest(args=args):
                with self.assertRaisesRegex(CliParseError, pattern):
                    parse_args(args).features_cli()

    def test_main_validates_unknown_feature_toggles_before_dispatch(self):
        stderr = io.StringIO()

        code = main(["--strict-config", "--enable", "does_not_exist"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("Unknown feature flag: does_not_exist", stderr.getvalue())

    def test_features_list_command_reads_config_and_root_overrides(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / "config.toml").write_text("[features]\nshell_tool = false\n", encoding="utf-8")
            stdout = io.StringIO()

            code = run_features_command(
                parse_features_args(["list"]),
                raw_config_overrides=("features.network_proxy=true",),
                codex_home=home,
                stdout=stdout,
            )

            self.assertEqual(code, 0)
            output = stdout.getvalue()
            self.assertTrue(any(line.startswith("network_proxy") and line.endswith("true") for line in output.splitlines()))
            self.assertTrue(any(line.startswith("shell_tool") and line.endswith("false") for line in output.splitlines()))

    def test_features_enable_command_writes_config_and_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            stdout = io.StringIO()
            stderr = io.StringIO()

            code = run_features_command(
                parse_features_args(["enable", "code_mode"]),
                codex_home=home,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 0)
            self.assertIn("Enabled feature `code_mode` in config.toml.", stdout.getvalue())
            self.assertIn("Under-development features enabled: code_mode", stderr.getvalue())
            self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), "[features]\ncode_mode = true\n")

    def test_features_disable_command_clears_default_false_and_sets_default_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / "config.toml").write_text("[features]\nnetwork_proxy = true\n", encoding="utf-8")
            stdout = io.StringIO()

            code = run_features_command(
                parse_features_args(["disable", "network_proxy"]),
                codex_home=home,
                stdout=stdout,
            )

            self.assertEqual(code, 0)
            self.assertIn("Disabled feature `network_proxy` in config.toml.", stdout.getvalue())
            self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), "[features]\n")

            run_features_command(parse_features_args(["disable", "shell_tool"]), codex_home=home, stdout=io.StringIO())
            self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), "[features]\nshell_tool = false\n")

    def test_main_features_enable_uses_codex_home(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmpdir
            stdout = io.StringIO()
            try:
                code = main(["features", "enable", "network_proxy"], stdout=stdout)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

            self.assertEqual(code, 0)
            self.assertIn("Enabled feature `network_proxy` in config.toml.", stdout.getvalue())
            self.assertEqual(
                (Path(tmpdir) / "config.toml").read_text(encoding="utf-8"),
                "[features]\nnetwork_proxy = true\n",
            )

    def test_format_features_list_matches_upstream_columns(self):
        features = Features.with_defaults()
        features.enable(Feature.CODE_MODE)

        output = format_features_list(features)
        lines = output.splitlines()

        self.assertEqual(lines, sorted(lines))
        self.assertTrue(any(line.startswith("code_mode") and line.endswith("true") for line in lines))
        self.assertTrue(any("under development" in line for line in lines))

    def test_under_development_feature_warning_matches_cli_text(self):
        warning = under_development_feature_warning("C:/tmp/codex-home", "code_mode")

        self.assertIsNotNone(warning)
        self.assertIn("Under-development features enabled: code_mode", warning)
        self.assertIn("config.toml", warning)
        self.assertIsNone(under_development_feature_warning("C:/tmp/codex-home", "personality"))

    def test_root_config_overrides_parse_with_shared_config_logic(self):
        parsed = parse_args(["-c", "use_legacy_landlock=true", "-c", "model=gpt-5"])
        overrides = parsed.parsed_config_overrides()

        self.assertEqual(overrides[0].path, "features.use_legacy_landlock")
        self.assertIs(overrides[0].value, True)
        self.assertEqual(overrides[1].path, "model")
        self.assertEqual(overrides[1].value, "gpt-5")

    def test_config_option_preserves_empty_raw_value_for_later_parse_error(self):
        parsed = parse_args(["--config="])

        self.assertEqual(parsed.config_overrides, ("",))

    def test_shared_interactive_options_are_collected(self):
        parsed = parse_args(
            [
                "--image",
                "a.png,b.png",
                "-m",
                "gpt-5",
                "--oss",
                "--sandbox",
                "workspace-write",
                "--ask-for-approval",
                "untrusted",
                "--profile",
                "work",
                "-C",
                "work",
                "--add-dir",
                "extra",
                "hello",
            ]
        )

        self.assertEqual(parsed.prompt, "hello")
        self.assertEqual(parsed.root_options["images"], ("a.png", "b.png"))
        self.assertEqual(parsed.root_options["model"], "gpt-5")
        self.assertTrue(parsed.root_options["oss"])
        self.assertIs(parsed.root_options["sandbox"], SandboxMode.WORKSPACE_WRITE)
        self.assertIs(parsed.root_options["approval_policy"], AskForApproval.UNLESS_TRUSTED)
        self.assertEqual(parsed.root_options["profile"], ProfileV2Name("work"))
        self.assertEqual(parsed.root_options["cwd"], "work")
        self.assertEqual(parsed.root_options["add_dir"], ("extra",))

    def test_invalid_typed_shared_options_error(self):
        for args, pattern in (
            (["--sandbox", "workspace_write"], "invalid SandboxMode"),
            (["--ask-for-approval", "sometimes"], "invalid AskForApproval"),
            (["--profile", "../work"], "invalid --profile"),
        ):
            with self.subTest(args=args):
                with self.assertRaisesRegex(CliParseError, pattern):
                    parse_args(args)

    def test_main_rejects_profile_for_config_management_subcommand(self):
        stderr = io.StringIO()

        code = main(["--profile", "work", "features", "list"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("--profile only applies to runtime commands and `codex mcp`", stderr.getvalue())

    def test_main_allows_profile_for_mcp(self):
        stderr = io.StringIO()

        code = main(["--profile", "work", "mcp", "list"], stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")

    def test_main_allows_profile_for_debug_prompt_input(self):
        stderr = io.StringIO()
        stdout = io.StringIO()

        code = main(["--profile", "work", "debug", "prompt-input"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn('"prompt": ""', stdout.getvalue())

    def test_main_rejects_profile_for_debug_other_subcommand(self):
        stderr = io.StringIO()

        code = main(["--profile", "work", "debug", "models"], stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("--profile only applies to runtime commands and `codex mcp`", stderr.getvalue())

    def test_extra_interactive_positionals_error_like_optional_prompt(self):
        with self.assertRaisesRegex(CliParseError, "Unexpected extra argument"):
            parse_args(["first", "second"])

    def test_unknown_root_option_errors(self):
        with self.assertRaisesRegex(CliParseError, "Unknown option"):
            parse_args(["--definitely-not-a-codex-option"])

    def test_help_text_hides_hidden_commands(self):
        with self.assertRaises(CliParseError) as ctx:
            parse_args(["--help"])

        help_text = str(ctx.exception)
        self.assertIn("exec", help_text)
        self.assertIn("app-server", help_text)
        self.assertNotIn("responses-api-proxy", help_text)
        self.assertNotIn("stdio-to-uds", help_text)

    def test_parse_top_level_version_flag(self):
        parsed = parse_args(["--version"])
        self.assertTrue(parsed.version_requested)
        self.assertIsNone(parsed.command)

    def test_parse_top_level_version_short_flag(self):
        parsed = parse_args(["-V"])
        self.assertTrue(parsed.version_requested)
        self.assertIsNone(parsed.command)

    def test_main_top_level_version(self):
        stdout = io.StringIO()
        code = main(["--version"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("codex 0.1.0", stdout.getvalue())

    def test_main_top_level_version_short_flag(self):
        stdout = io.StringIO()
        code = main(["-V"], stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("codex 0.1.0", stdout.getvalue())

    def test_main_exec_local_http_uses_config_provider_env_key(self):
        seen = {}

        async def fake_run(config, _plan, _model_client, provider, _model_info, **kwargs):
            seen["auth"] = kwargs["auth"]
            seen["provider_base_url"] = provider.base_url
            seen["model_provider_id"] = config.model_provider_id
            text_part = type("TextPart", (), {"text": "done"})()
            response_item = type("ResponseItem", (), {"content": [text_part]})()
            return type(
                "Result",
                (),
                {
                    "response_items": (response_item,),
                    "raw_result": {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done"}],
                            }
                        ]
                    },
                },
            )()

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    (
                        'model_provider = "local-openai"',
                        "",
                        "[model_providers.local-openai]",
                        'base_url = "https://local.example.test/v1"',
                        'env_key = "LOCAL_OPENAI_KEY"',
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "0",
                    "OPENAI_API_KEY": "",
                    "LOCAL_OPENAI_KEY": "sk-local",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(seen["auth"], "sk-local")
        self.assertEqual(seen["provider_base_url"], "https://local.example.test/v1")
        self.assertEqual(seen["model_provider_id"], "local-openai")
        self.assertIn("done", stdout.getvalue())

    def test_main_exec_local_http_shell_tools_flag_uses_tool_loop(self):
        seen = {}

        async def fake_run(config, _plan, _model_client, _provider, _model_info, **kwargs):
            seen["auth"] = kwargs["auth"]
            seen["max_tool_rounds"] = kwargs["max_tool_rounds"]
            seen["tool_output_max_chars"] = kwargs["tool_output_max_chars"]
            seen["cwd"] = str(config.cwd)
            text_part = type("TextPart", (), {"text": "done"})()
            response_item = type("ResponseItem", (), {"content": [text_part]})()
            return type(
                "Result",
                (),
                {
                    "response_items": (response_item,),
                    "raw_result": {
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done"}],
                            }
                        ]
                    },
                },
            )()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS": "50",
                    "OPENAI_API_KEY": "sk-env",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch(
                        "pycodex.cli.parser.run_exec_user_turn_with_shell_tools_http_sampling",
                        side_effect=fake_run,
                    ) as run_tool_loop:
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(run_tool_loop.call_count, 1)
        self.assertEqual(seen["auth"], "sk-env")
        self.assertEqual(seen["max_tool_rounds"], 2)
        self.assertEqual(seen["tool_output_max_chars"], 50)
        self.assertIn("done", stdout.getvalue())

    def test_main_exec_local_http_default_uses_core_http_sampling(self):
        seen = {}

        async def fake_run(_config, _plan, _model_client, _provider, _model_info, **kwargs):
            seen["auth"] = kwargs["auth"]
            return type(
                "Result",
                (),
                {
                    "response_items": (
                        ResponseItem.from_mapping(
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done"}],
                            }
                        ),
                    ),
                    "raw_result": None,
                },
            )()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "",
                    "OPENAI_API_KEY": "sk-env",
                },
                clear=False,
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_exec_user_turn_http_sampling", side_effect=fake_run) as run_core:
                        with patch(
                            "pycodex.cli.parser.run_exec_user_turn_with_shell_tools_http_sampling",
                            side_effect=AssertionError("legacy shell loop should not run by default"),
                        ):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["exec", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(run_core.call_count, 1)
        self.assertEqual(seen["auth"], "sk-env")
        self.assertEqual(stdout.getvalue(), "done\n")

    def test_main_exec_core_env_uses_in_memory_core_http_sampling(self):
        seen = {}

        async def fake_run(command, *_args, **kwargs):
            seen["command"] = command
            seen["auth"] = kwargs["auth"]
            seen["max_tool_followups"] = kwargs["max_tool_followups"]
            seen["cli_version"] = kwargs["cli_version"]
            return type(
                "Result",
                (),
                {
                    "response_items": (
                        ResponseItem.from_mapping(
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done"}],
                            }
                        ),
                    ),
                    "raw_result": None,
                },
            )()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_CORE": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "OPENAI_API_KEY": "sk-env",
                },
                clear=False,
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_core_exec_command", side_effect=fake_run) as run_core:
                        with patch(
                            "pycodex.cli.parser.run_exec_user_turn_http_sampling",
                            side_effect=AssertionError("local HTTP wrapper should not run when core exec is enabled"),
                        ):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["exec", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(run_core.call_count, 1)
        self.assertIsNone(seen["command"])
        self.assertEqual(seen["auth"], "sk-env")
        self.assertEqual(seen["max_tool_followups"], 2)
        self.assertIsInstance(seen["cli_version"], str)
        self.assertEqual(stdout.getvalue(), "done\n")
        self.assertIn("completed core non-interactive exec execution", stderr.getvalue())

    def test_main_exec_api_key_defaults_to_core_runtime(self):
        seen = {}

        async def fake_run(command, *_args, **kwargs):
            seen["command"] = command
            seen["auth"] = kwargs["auth"]
            seen["max_tool_followups"] = kwargs["max_tool_followups"]
            return type(
                "Result",
                (),
                {
                    "response_items": (
                        ResponseItem.from_mapping(
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done"}],
                            }
                        ),
                    ),
                    "raw_result": None,
                },
            )()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "OPENAI_API_KEY": "sk-env",
                },
                clear=True,
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.run_core_exec_command", side_effect=fake_run) as run_core:
                        with patch(
                            "pycodex.cli.parser.run_exec_user_turn_http_sampling",
                            side_effect=AssertionError("legacy local HTTP runner should not be the API-key default"),
                        ):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["exec", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(run_core.call_count, 1)
        self.assertIsNone(seen["command"])
        self.assertEqual(seen["auth"], "sk-env")
        self.assertIsNone(seen["max_tool_followups"])
        self.assertEqual(stdout.getvalue(), "done\n")
        self.assertIn("completed core non-interactive exec execution", stderr.getvalue())

    def test_main_exec_local_http_shell_tools_explicit_tool_rounds_are_unbounded(self):
        seen = {}

        async def fake_run(_config, _plan, _model_client, _provider, _model_info, **kwargs):
            seen["max_tool_rounds"] = kwargs["max_tool_rounds"]
            return type(
                "Result",
                (),
                {
                    "response_items": (
                        ResponseItem.from_mapping(
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done"}],
                            }
                        ),
                    ),
                    "raw_result": None,
                },
            )()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "OPENAI_API_KEY": "sk-env",
                },
                clear=False,
            ):
                os.environ.pop("PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS", None)
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch(
                        "pycodex.cli.parser.run_exec_user_turn_with_shell_tools_http_sampling",
                        side_effect=fake_run,
                    ):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(["exec", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertIsNone(seen["max_tool_rounds"])
        self.assertEqual(stdout.getvalue(), "done\n")

    def test_main_exec_local_http_shell_tools_passes_output_schema_to_tool_loop(self):
        seen = {}

        async def fake_run(_config, plan, _model_client, _provider, _model_info, **kwargs):
            seen["output_schema"] = plan.initial_operation.output_schema
            seen["max_tool_rounds"] = kwargs["max_tool_rounds"]
            return type(
                "Result",
                (),
                {
                    "response_items": (
                        ResponseItem.from_mapping(
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "done"}],
                            }
                        ),
                    ),
                    "raw_result": None,
                },
            )()

        with tempfile.TemporaryDirectory() as tmpdir:
            schema_path = Path(tmpdir) / "schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                        "required": ["summary"],
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "OPENAI_API_KEY": "sk-env",
                },
                clear=False,
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch(
                        "pycodex.cli.parser.run_exec_user_turn_with_shell_tools_http_sampling",
                        side_effect=fake_run,
                    ):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        code = main(
                            ["exec", "--output-schema", str(schema_path), "hello"],
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertEqual(code, 0)
        self.assertEqual(seen["output_schema"]["properties"]["summary"]["type"], "string")
        self.assertIsNone(seen["max_tool_rounds"])
        self.assertEqual(stdout.getvalue(), "done\n")

    def test_main_exec_resume_local_http_last_uses_resume_runner(self):
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "resumed"}],
                    }
                ),
            )
            raw_result = None

        async def fake_resume_run(codex_home, config, plan, _model_client, _provider, _model_info, **kwargs):
            seen["codex_home"] = Path(codex_home)
            seen["cwd"] = config.cwd
            seen["prompt"] = plan.prompt_summary
            seen["thread_id"] = kwargs.get("thread_id")
            seen["resume_last"] = kwargs.get("resume_last")
            seen["include_all"] = kwargs.get("include_all")
            seen["resolved_rollout_path"] = kwargs.get("resolved_rollout_path")
            return FakeResult()

        def fake_align(_codex_home, _config, model_client, **_kwargs):
            model_client.state.session_id = "resumed-thread"
            model_client.state.thread_id = "resumed-thread"
            return Path("aligned-rollout.jsonl")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "OPENAI_API_KEY": "sk-env",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.align_local_http_exec_resume_model_client", side_effect=fake_align):
                        with patch(
                            "pycodex.cli.parser.run_exec_resume_user_turn_http_sampling",
                            side_effect=fake_resume_run,
                        ) as resume_runner:
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["exec", "resume", "--last", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(resume_runner.call_count, 1)
        self.assertEqual(seen["codex_home"], Path(tmpdir))
        self.assertEqual(seen["prompt"], "hello")
        self.assertIsNone(seen["thread_id"])
        self.assertTrue(seen["resume_last"])
        self.assertFalse(seen["include_all"])
        self.assertEqual(seen["resolved_rollout_path"], Path("aligned-rollout.jsonl"))
        self.assertIn("session id: resumed-thread", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "resumed\n")

    def test_main_exec_resume_core_env_uses_core_resume_runner(self):
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "core resumed"}],
                    }
                ),
            )
            raw_result = None

        async def fake_resume_run(command, codex_home, _config, plan, _model_client, _provider, _model_info, **kwargs):
            seen["command"] = command
            seen["codex_home"] = Path(codex_home)
            seen["prompt"] = plan.prompt_summary
            seen["resume_args"] = kwargs.get("resume_args")
            seen["resume_target"] = kwargs.get("resume_target")
            seen["resume_target_resolved"] = kwargs.get("resume_target_resolved")
            seen["auth"] = kwargs.get("auth")
            seen["cli_version"] = kwargs.get("cli_version")
            return FakeResult()

        def fake_align(_codex_home, _config, model_client, _resume_args):
            model_client.state.session_id = "core-resumed-thread"
            model_client.state.thread_id = "core-resumed-thread"
            return type(
                "Target",
                (),
                {
                    "thread_id": None,
                    "session_name": None,
                    "rollout_path": Path("core-aligned-rollout.jsonl"),
                },
            )()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_CORE": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "OPENAI_API_KEY": "sk-env",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.resolve_core_exec_resume_target", side_effect=fake_align):
                        with patch(
                            "pycodex.cli.parser.run_core_exec_command",
                            side_effect=fake_resume_run,
                        ) as resume_runner:
                            with patch(
                                "pycodex.cli.parser.run_exec_resume_user_turn_http_sampling",
                                side_effect=AssertionError("local HTTP resume runner should not run when core exec is enabled"),
                            ):
                                stdout = io.StringIO()
                                stderr = io.StringIO()
                                code = main(["exec", "resume", "--last", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(resume_runner.call_count, 1)
        self.assertEqual(seen["command"], "resume")
        self.assertEqual(seen["codex_home"], Path(tmpdir))
        self.assertEqual(seen["prompt"], "hello")
        self.assertTrue(seen["resume_args"].last)
        self.assertFalse(seen["resume_args"].all)
        self.assertIsNone(seen["resume_target"].thread_id)
        self.assertTrue(seen["resume_target_resolved"])
        self.assertEqual(seen["resume_target"].rollout_path, Path("core-aligned-rollout.jsonl"))
        self.assertEqual(seen["auth"], "sk-env")
        self.assertIsInstance(seen["cli_version"], str)
        self.assertIn("session id: core-resumed-thread", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "core resumed\n")

    def test_main_exec_resume_core_env_without_target_starts_new_core_turn(self):
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "new core turn"}],
                    }
                ),
            )
            raw_result = None

        async def fake_resume_run(command, _codex_home, _config, plan, _model_client, _provider, _model_info, **kwargs):
            seen["command"] = command
            seen["prompt"] = plan.prompt_summary
            seen["resume_args"] = kwargs.get("resume_args")
            seen["resume_target"] = kwargs.get("resume_target")
            seen["resume_target_resolved"] = kwargs.get("resume_target_resolved")
            return FakeResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_CORE": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP": "0",
                    "OPENAI_API_KEY": "sk-env",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.resolve_core_exec_resume_target", return_value=None):
                        with patch(
                            "pycodex.cli.parser.run_core_exec_command",
                            side_effect=fake_resume_run,
                        ) as resume_runner:
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["exec", "resume", "--last", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(resume_runner.call_count, 1)
        self.assertEqual(seen["command"], "resume")
        self.assertEqual(seen["prompt"], "hello")
        self.assertTrue(seen["resume_args"].last)
        self.assertIsNone(seen["resume_target"])
        self.assertTrue(seen["resume_target_resolved"])
        self.assertIn("session id:", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "new core turn\n")

    def test_main_exec_resume_local_http_named_session_uses_resume_runner(self):
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "named resumed"}],
                    }
                ),
            )
            raw_result = None

        async def fake_resume_run(_codex_home, _config, plan, _model_client, _provider, _model_info, **kwargs):
            seen["prompt"] = plan.prompt_summary
            seen["thread_id"] = kwargs.get("thread_id")
            seen["session_name"] = kwargs.get("session_name")
            seen["resume_last"] = kwargs.get("resume_last")
            return FakeResult()

        def fake_align(_codex_home, _config, model_client, **_kwargs):
            model_client.state.thread_id = "named-thread"
            return Path("rollout.jsonl")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "OPENAI_API_KEY": "sk-env",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.align_local_http_exec_resume_model_client", side_effect=fake_align):
                        with patch("pycodex.cli.parser.run_exec_resume_user_turn_http_sampling", side_effect=fake_resume_run):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["exec", "resume", "named-session", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertEqual(seen["prompt"], "hello")
        self.assertIsNone(seen["thread_id"])
        self.assertEqual(seen["session_name"], "named-session")
        self.assertFalse(seen["resume_last"])
        self.assertEqual(stdout.getvalue(), "named resumed\n")

    def test_main_exec_resume_local_http_shell_tools_passes_tool_loop_options(self):
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "shell resumed"}],
                    }
                ),
            )
            raw_result = None

        async def fake_resume_run(_codex_home, _config, _plan, _model_client, _provider, _model_info, **kwargs):
            seen["use_shell_tools"] = kwargs.get("use_shell_tools")
            seen["max_tool_rounds"] = kwargs.get("max_tool_rounds")
            seen["tool_output_max_chars"] = kwargs.get("tool_output_max_chars")
            seen["resume_last"] = kwargs.get("resume_last")
            return FakeResult()

        def fake_align(_codex_home, _config, model_client, **_kwargs):
            model_client.state.session_id = "shell-resumed-thread"
            model_client.state.thread_id = "shell-resumed-thread"
            return Path("rollout.jsonl")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "2",
                    "PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS": "50",
                    "OPENAI_API_KEY": "sk-env",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.align_local_http_exec_resume_model_client", side_effect=fake_align):
                        with patch("pycodex.cli.parser.run_exec_resume_user_turn_http_sampling", side_effect=fake_resume_run):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(["exec", "resume", "--last", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertTrue(seen["use_shell_tools"])
        self.assertEqual(seen["max_tool_rounds"], 2)
        self.assertEqual(seen["tool_output_max_chars"], 50)
        self.assertTrue(seen["resume_last"])
        self.assertEqual(stdout.getvalue(), "shell resumed\n")

    def test_main_exec_resume_local_http_shell_tools_passes_output_schema(self):
        seen = {}

        class FakeResult:
            response_items = (
                ResponseItem.from_mapping(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "schema resumed"}],
                    }
                ),
            )
            raw_result = None

        async def fake_resume_run(_codex_home, _config, plan, _model_client, _provider, _model_info, **kwargs):
            seen["output_schema"] = plan.initial_operation.output_schema
            seen["use_shell_tools"] = kwargs.get("use_shell_tools")
            seen["resume_last"] = kwargs.get("resume_last")
            return FakeResult()

        def fake_align(_codex_home, _config, model_client, **_kwargs):
            model_client.state.session_id = "schema-resumed-thread"
            model_client.state.thread_id = "schema-resumed-thread"
            return Path("rollout.jsonl")

        with tempfile.TemporaryDirectory() as tmpdir:
            schema_path = Path(tmpdir) / "schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                        "required": ["summary"],
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "OPENAI_API_KEY": "sk-env",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    with patch("pycodex.cli.parser.align_local_http_exec_resume_model_client", side_effect=fake_align):
                        with patch("pycodex.cli.parser.run_exec_resume_user_turn_http_sampling", side_effect=fake_resume_run):
                            stdout = io.StringIO()
                            stderr = io.StringIO()
                            code = main(
                                ["exec", "resume", "--last", "--output-schema", str(schema_path), "hello"],
                                stdout=stdout,
                                stderr=stderr,
                            )

        self.assertEqual(code, 0)
        self.assertTrue(seen["use_shell_tools"])
        self.assertTrue(seen["resume_last"])
        self.assertEqual(seen["output_schema"]["properties"]["summary"]["type"], "string")
        self.assertEqual(stdout.getvalue(), "schema resumed\n")

    def test_main_exec_local_http_shell_tools_rejects_invalid_max_rounds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS": "many",
                    "OPENAI_API_KEY": "sk-env",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(["exec", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS must be a non-negative integer", stderr.getvalue())

    def test_main_exec_local_http_shell_tools_rejects_invalid_output_max_chars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": tmpdir,
                    "PYCODEX_EXEC_LOCAL_HTTP": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS": "1",
                    "PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS": "0",
                    "OPENAI_API_KEY": "sk-env",
                },
            ):
                with patch("pycodex.cli.parser.read_auth_json", return_value=None):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    code = main(["exec", "hello"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 2)
        self.assertIn("PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS must be a positive integer", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()






