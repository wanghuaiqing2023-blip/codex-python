import io
import unittest
from pathlib import Path
from unittest.mock import patch

from pycodex import responses_api_proxy


class ResponsesApiProxyMainRsTests(unittest.TestCase):
    def test_run_main_parses_raw_args_and_calls_package_runtime(self):
        # Rust crate/module: codex-responses-api-proxy/src/main.rs
        # Contract: binary entrypoint parses Args and calls crate run_main.
        calls = []

        def fake_serve(args, *, auth_header, stdout, stderr):
            calls.append((args, auth_header, stdout, stderr))
            return 7

        stdin = io.StringIO("sk-test\n")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("pycodex.responses_api_proxy._serve_proxy", fake_serve):
            result = responses_api_proxy.main(
                ["--port", "0", "--http-shutdown"],
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(result, 7)
        parsed, auth_header, captured_stdout, captured_stderr = calls[0]
        self.assertEqual(parsed.port, 0)
        self.assertTrue(parsed.http_shutdown)
        self.assertEqual(auth_header, "Bearer sk-test")
        self.assertIs(captured_stdout, stdout)
        self.assertIs(captured_stderr, stderr)

    def test_run_main_passes_args_dataclass_to_package_runtime(self):
        # Rust crate/module: codex-responses-api-proxy/src/main.rs
        # Contract: Args values are handed to the crate runtime.
        calls = []

        def fake_serve(args, *, auth_header, stdout, stderr):
            calls.append((args, auth_header))
            return 0

        args = responses_api_proxy.ResponsesApiProxyArgs(
            port=8080,
            server_info=Path("server-info.json"),
            http_shutdown=True,
            upstream_url="http://127.0.0.1:9000/v1/responses",
            dump_dir=Path("dumps"),
        )

        with patch("pycodex.responses_api_proxy._serve_proxy", fake_serve):
            self.assertEqual(responses_api_proxy.run_main(args, stdin="sk-test\n"), 0)

        self.assertEqual(calls, [(args, "Bearer sk-test")])

    def test_parse_main_args_preserves_default_upstream_url(self):
        # Rust crate/module: codex-responses-api-proxy/src/main.rs
        # Contract: default Args use the Rust default upstream URL.
        parsed = responses_api_proxy.parse_main_args([])
        self.assertEqual(parsed.upstream_url, responses_api_proxy.DEFAULT_UPSTREAM_URL)

    def test_help_does_not_read_stdin_or_start_server(self):
        # Rust crate/module: codex-responses-api-proxy/src/main.rs
        # Contract: clap help exits before runtime work.
        stdout = io.StringIO()
        with patch("pycodex.responses_api_proxy._serve_proxy") as serve:
            code = responses_api_proxy.main(["--help"], stdin="", stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Usage: codex responses-api-proxy [OPTIONS]", stdout.getvalue())
        serve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
