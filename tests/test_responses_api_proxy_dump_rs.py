import io
import json
import tempfile
import unittest
from pathlib import Path

from pycodex.responses_api_proxy import ExchangeDumper


def _single_dump_file(dump_dir: Path, suffix: str) -> Path:
    matches = sorted(path for path in dump_dir.iterdir() if str(path).endswith(suffix))
    assert len(matches) == 1
    return matches[0]


class ResponsesApiProxyDumpRsTests(unittest.TestCase):
    # Rust crate/module: codex-responses-api-proxy::dump.
    # Rust test: dump_request_writes_redacted_headers_and_json_body.
    def test_dump_request_writes_redacted_headers_and_json_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dump_dir = Path(tmpdir)
            dumper = ExchangeDumper(dump_dir)
            headers = [
                ("Authorization", "Bearer secret"),
                ("Cookie", "user-session=secret"),
                ("Content-Type", "application/json"),
                ("x-codex-window-id", "thread-1:0"),
                ("x-codex-parent-thread-id", "parent-thread-1"),
                ("x-openai-subagent", "collab_spawn"),
            ]

            exchange_dump = dumper.dump_request(
                "POST",
                "/v1/responses",
                headers,
                b'{"model":"gpt-5.4"}',
            )

            request_dump = json.loads(_single_dump_file(dump_dir, "-request.json").read_text(encoding="utf-8"))
            self.assertEqual(
                request_dump,
                {
                    "method": "POST",
                    "url": "/v1/responses",
                    "headers": [
                        {"name": "Authorization", "value": "[REDACTED]"},
                        {"name": "Cookie", "value": "[REDACTED]"},
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "x-codex-window-id", "value": "thread-1:0"},
                        {"name": "x-codex-parent-thread-id", "value": "parent-thread-1"},
                        {"name": "x-openai-subagent", "value": "collab_spawn"},
                    ],
                    "body": {"model": "gpt-5.4"},
                },
            )
            self.assertTrue(exchange_dump.response_path.name.endswith("-response.json"))

    # Rust crate/module: codex-responses-api-proxy::dump.
    # Rust test: response_body_dump_streams_body_and_writes_response_file.
    def test_response_body_dump_streams_body_and_writes_response_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dump_dir = Path(tmpdir)
            dumper = ExchangeDumper(dump_dir)
            exchange_dump = dumper.dump_request("POST", "/v1/responses", [], b"{}")
            headers = [
                ("content-type", "text/event-stream"),
                ("authorization", "Bearer secret"),
                ("set-cookie", "user-session=secret"),
            ]

            response_body = exchange_dump.tee_response_body(
                200,
                headers,
                io.BytesIO(b"data: hello\n\n"),
            )
            streamed = response_body.read()
            streamed += response_body.read()

            response_dump = json.loads(_single_dump_file(dump_dir, "-response.json").read_text(encoding="utf-8"))
            self.assertEqual(streamed, b"data: hello\n\n")
            self.assertEqual(
                response_dump,
                {
                    "status": 200,
                    "headers": [
                        {"name": "content-type", "value": "text/event-stream"},
                        {"name": "authorization", "value": "[REDACTED]"},
                        {"name": "set-cookie", "value": "[REDACTED]"},
                    ],
                    "body": "data: hello\n\n",
                },
            )


if __name__ == "__main__":
    unittest.main()
