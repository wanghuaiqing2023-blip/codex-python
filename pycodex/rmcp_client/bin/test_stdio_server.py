"""Full stdio MCP integration fixture matching the Rust test binary."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

MEMO_URI = "memo://codex/example-note"
MEMO_CONTENT = "This is a sample MCP resource served by the rmcp test server."
SANDBOX_STATE_META_CAPABILITY = "codex/sandbox-state-meta"
SMALL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
    "iZk9HQAAAABJRU5ErkJggg=="
)
DEFAULT_SYNC_TIMEOUT_MS = 1_000
TOOLS_LIST_DELAY_ENV = "PYCODEX_TEST_MCP_TOOLS_LIST_DELAY_SECONDS"
TOOLS_LIST_RELEASE_FILE_ENV = "PYCODEX_TEST_MCP_TOOLS_LIST_RELEASE_FILE"
TOOLS_LIST_BLOCK_FILE_ENV = "PYCODEX_TEST_MCP_TOOLS_LIST_BLOCK_FILE"
TOOLS_PROFILE_ENV = "PYCODEX_TEST_MCP_PROFILE"
TOOLS_CALL_LOG_ENV = "PYCODEX_TEST_MCP_CALL_LOG"
TOOLS_LIST_RELEASE_TIMEOUT_SECONDS = 60.0
_SYNC_BARRIERS: dict[str, tuple[int, threading.Barrier]] = {}
_SYNC_LOCK = threading.Lock()


def stdio() -> tuple[Any, Any]:
    return sys.stdin, sys.stdout


def parse_data_url(url: str) -> tuple[str, str] | None:
    if not url.startswith("data:") or "," not in url:
        return None
    mime_and_options, data = url[5:].split(",", 1)
    mime = mime_and_options.split(";", 1)[0]
    return mime, data


def wait_on_sync_barrier(arguments: dict[str, Any]) -> None:
    barrier_id = str(arguments.get("id", ""))
    participants = int(arguments.get("participants", 0))
    timeout_ms = int(arguments.get("timeout_ms", DEFAULT_SYNC_TIMEOUT_MS))
    if participants <= 0:
        raise ValueError("barrier participants must be greater than zero")
    if timeout_ms <= 0:
        raise ValueError("barrier timeout must be greater than zero")
    with _SYNC_LOCK:
        state = _SYNC_BARRIERS.get(barrier_id)
        if state is None:
            barrier = threading.Barrier(participants)
            _SYNC_BARRIERS[barrier_id] = (participants, barrier)
        else:
            existing, barrier = state
            if existing != participants:
                raise ValueError(
                    f"barrier {barrier_id} already registered with "
                    f"{existing} participants"
                )
    try:
        leader = barrier.wait(timeout=timeout_ms / 1_000) == 0
    except threading.BrokenBarrierError as exc:
        with _SYNC_LOCK:
            if _SYNC_BARRIERS.get(barrier_id, (None, None))[1] is barrier:
                _SYNC_BARRIERS.pop(barrier_id, None)
        raise ValueError("sync barrier wait timed out") from exc
    if leader:
        with _SYNC_LOCK:
            if _SYNC_BARRIERS.get(barrier_id, (None, None))[1] is barrier:
                _SYNC_BARRIERS.pop(barrier_id, None)


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
    *,
    read_only: bool = False,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties or {},
            "additionalProperties": False,
        },
    }
    if required:
        value["inputSchema"]["required"] = required
    if read_only:
        value["annotations"] = {"readOnlyHint": True}
    return value


class TestToolServer:
    def __init__(self) -> None:
        echo_properties = {
            "message": {"type": "string"},
            "env_var": {"type": "string"},
        }
        sync_properties = {
            "sleep_before_ms": {"type": "number"},
            "sleep_after_ms": {"type": "number"},
            "barrier": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "participants": {"type": "number"},
                    "timeout_ms": {"type": "number"},
                },
                "required": ["id", "participants"],
                "additionalProperties": False,
            },
        }
        self.tools = [
            _tool(
                "echo",
                "Echo back the provided message and include environment data.",
                echo_properties,
                ["message"],
                read_only=True,
            ),
            _tool(
                "echo-tool",
                "Echo back the provided message via a non-JS tool name.",
                echo_properties,
                ["message"],
                read_only=True,
            ),
            _tool(
                "cwd",
                "Return the current working directory of this test server process.",
                read_only=True,
            ),
            _tool("sync", "Synchronize concurrent test calls.", sync_properties),
            _tool(
                "sync_readonly",
                "Synchronize concurrent read-only test calls.",
                sync_properties,
                read_only=True,
            ),
            _tool("image", "Return a single image content block.", read_only=True),
            _tool(
                "image_scenario",
                "Return content blocks for MCP image rendering scenarios.",
                {
                    "scenario": {"type": "string"},
                    "caption": {"type": "string"},
                    "data_url": {"type": "string"},
                },
                ["scenario"],
                read_only=True,
            ),
            _tool(
                "sandbox_meta",
                "Return the MCP request metadata received by this test server.",
                read_only=True,
            ),
        ]
        if os.environ.get(TOOLS_PROFILE_ENV) == "openai_docs":
            self.tools = [
                _tool(
                    "search_openai_docs",
                    "Search the official OpenAI developer documentation.",
                    {"query": {"type": "string"}},
                    ["query"],
                    read_only=True,
                ),
                _tool(
                    "fetch_openai_doc",
                    "Fetch an official OpenAI developer documentation page.",
                    {"url": {"type": "string"}},
                    ["url"],
                    read_only=True,
                ),
            ]
        self.resources = [
            {
                "uri": MEMO_URI,
                "name": "example-note",
                "title": "Example Note",
                "description": "A sample MCP resource exposed for integration tests.",
                "mimeType": "text/plain",
            }
        ]
        self.resource_templates = [
            {
                "uriTemplate": "memo://codex/{slug}",
                "name": "codex-memo",
                "title": "Codex Memo",
                "description": "Template for memo resources used in tests.",
                "mimeType": "text/plain",
            }
        ]

    def handle(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": "2025-06-18",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {},
                    "experimental": {SANDBOX_STATE_META_CAPABILITY: {}},
                },
                "serverInfo": {"name": "test-stdio-server", "version": "0.1.0"},
                "instructions": "Use these tools to exercise the rmcp test server.",
            }
        if method == "tools/list":
            release_file = os.environ.get(TOOLS_LIST_RELEASE_FILE_ENV)
            block_file = os.environ.get(TOOLS_LIST_BLOCK_FILE_ENV)
            should_block = not block_file or Path(block_file).exists()
            if release_file and should_block:
                deadline = time.monotonic() + TOOLS_LIST_RELEASE_TIMEOUT_SECONDS
                release_path = Path(release_file)
                while not release_path.exists():
                    if time.monotonic() >= deadline:
                        raise TimeoutError("tools/list release file was not created")
                    time.sleep(0.05)
            else:
                delay_seconds = float(os.environ.get(TOOLS_LIST_DELAY_ENV, "0") or 0)
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
            return {"tools": self.tools}
        if method == "resources/list":
            return {"resources": self.resources}
        if method == "resources/templates/list":
            return {"resourceTemplates": self.resource_templates}
        if method == "resources/read":
            uri = str(params.get("uri", ""))
            if uri != MEMO_URI:
                raise LookupError("resource_not_found")
            return {
                "contents": [
                    {"uri": uri, "mimeType": "text/plain", "text": MEMO_CONTENT}
                ]
            }
        if method == "tools/call":
            return self.call_tool(params)
        return {}

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", ""))
        arguments = params.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        call_log = os.environ.get(TOOLS_CALL_LOG_ENV)
        if call_log:
            with Path(call_log).open("a", encoding="utf-8") as sink:
                sink.write(
                    json.dumps(
                        {"name": name, "arguments": arguments},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        if name == "search_openai_docs":
            query = str(arguments.get("query", ""))
            if not query:
                raise ValueError("missing arguments for search_openai_docs tool")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "OPENAI_DOCS_E2E_RESULT: Responses API documentation "
                            "https://platform.openai.com/docs/api-reference/responses"
                        ),
                    }
                ],
                "isError": False,
            }
        if name == "fetch_openai_doc":
            url = str(arguments.get("url", ""))
            if not url:
                raise ValueError("missing arguments for fetch_openai_doc tool")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"OPENAI_DOCS_E2E_FETCHED: {url}",
                    }
                ],
                "isError": False,
            }
        if name == "sandbox_meta":
            return self.structured_result(dict(params.get("_meta") or {}))
        if name == "cwd":
            return self.structured_result({"cwd": str(Path.cwd())})
        if name in {"echo", "echo-tool"}:
            if "message" not in arguments:
                raise ValueError(f"missing arguments for {name} tool")
            env_name = str(arguments.get("env_var") or "MCP_TEST_VALUE")
            return self.structured_result(
                {
                    "echo": f"ECHOING: {arguments['message']}",
                    "env": os.environ.get(env_name),
                }
            )
        if name == "image":
            value = os.environ.get("MCP_TEST_IMAGE_DATA_URL")
            parsed = parse_data_url(value or "")
            if parsed is None:
                raise ValueError("missing or invalid MCP_TEST_IMAGE_DATA_URL")
            mime_type, data = parsed
            return {"content": [self.image_content(data, mime_type)], "isError": False}
        if name == "image_scenario":
            return self.image_scenario_result(arguments)
        if name in {"sync", "sync_readonly"}:
            before = int(arguments.get("sleep_before_ms") or 0)
            after = int(arguments.get("sleep_after_ms") or 0)
            if before > 0:
                time.sleep(before / 1_000)
            barrier = arguments.get("barrier")
            if isinstance(barrier, dict):
                wait_on_sync_barrier(barrier)
            if after > 0:
                time.sleep(after / 1_000)
            return self.structured_result({"result": "ok"})
        raise ValueError(f"unknown tool: {name}")

    @staticmethod
    def structured_result(value: Any) -> dict[str, Any]:
        return {"content": [], "structuredContent": value, "isError": False}

    @staticmethod
    def image_content(
        data: str,
        mime_type: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        value: dict[str, Any] = {
            "type": "image",
            "data": data,
            "mimeType": mime_type,
        }
        if meta is not None:
            value["_meta"] = meta
        return value

    def image_scenario_result(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        parsed = (
            parse_data_url(str(arguments["data_url"]))
            if arguments.get("data_url")
            else ("image/png", SMALL_PNG_BASE64)
        )
        if parsed is None:
            raise ValueError("invalid data_url for image_scenario tool")
        mime_type, data = parsed
        caption = str(arguments.get("caption") or "Here is the image:")
        image = self.image_content(data, mime_type)
        scenario = str(arguments.get("scenario", ""))
        content: list[dict[str, Any]]
        if scenario == "image_only":
            content = [image]
        elif scenario == "image_only_original_detail":
            content = [
                self.image_content(
                    data,
                    mime_type,
                    {"codex/imageDetail": "original"},
                )
            ]
        elif scenario == "text_then_image":
            content = [{"type": "text", "text": caption}, image]
        elif scenario == "invalid_base64_then_image":
            content = [self.image_content("not-base64", "image/png"), image]
        elif scenario == "invalid_image_bytes_then_image":
            content = [self.image_content("bm90IGFuIGltYWdl", "image/png"), image]
        elif scenario == "multiple_valid_images":
            content = [image, dict(image)]
        elif scenario == "image_then_text":
            content = [image, {"type": "text", "text": caption}]
        elif scenario == "text_only":
            content = [{"type": "text", "text": caption}]
        else:
            raise ValueError(f"unknown image scenario: {scenario}")
        return {"content": content, "isError": False}


def main() -> int:
    print("starting rmcp test server", file=sys.stderr, flush=True)
    pid_file = os.environ.get("MCP_TEST_PID_FILE")
    if pid_file:
        Path(pid_file).write_text(str(os.getpid()), encoding="utf-8")
    source, sink = stdio()
    server = TestToolServer()
    write_lock = threading.Lock()
    workers: list[threading.Thread] = []

    def respond(message: dict[str, Any]) -> None:
        try:
            result = server.handle(
                str(message.get("method", "")),
                message.get("params") or {},
            )
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": result,
            }
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32602, "message": str(exc)},
            }
        with write_lock:
            sink.write(json.dumps(response, separators=(",", ":")) + "\n")
            sink.flush()

    for line in source:
        message = json.loads(line)
        if message.get("id") is None:
            continue
        worker = threading.Thread(target=respond, args=(message,), daemon=True)
        workers.append(worker)
        worker.start()
    for worker in workers:
        worker.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
