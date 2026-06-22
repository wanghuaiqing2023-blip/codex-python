"""Common request/response contracts for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/common.rs``
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any


WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY = "ws_request_header_traceparent"
WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY = "ws_request_header_tracestate"


class OpenAiVerbosity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def from_config(cls, value: str | "OpenAiVerbosity") -> "OpenAiVerbosity":
        if isinstance(value, OpenAiVerbosity):
            return value
        return cls(str(value).lower())


class TextFormatType(str, Enum):
    JSON_SCHEMA = "json_schema"


@dataclass(frozen=True)
class Reasoning:
    effort: str | None = None
    summary: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return _skip_none({"effort": self.effort, "summary": self.summary})


@dataclass(frozen=True)
class TextFormat:
    schema: Any
    strict: bool = False
    name: str = "codex_output_schema"
    type: TextFormatType = TextFormatType.JSON_SCHEMA

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "strict": self.strict,
            "schema": self.schema,
            "name": self.name,
        }


@dataclass(frozen=True)
class TextControls:
    verbosity: OpenAiVerbosity | None = None
    format: TextFormat | None = None

    def to_json_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {}
        if self.verbosity is not None:
            value["verbosity"] = self.verbosity.value
        if self.format is not None:
            value["format"] = self.format.to_json_dict()
        return value


@dataclass(frozen=True)
class CompactionInput:
    model: str
    input: list[Any]
    instructions: str = ""
    tools: list[Any] | None = None
    parallel_tool_calls: bool = False
    reasoning: Reasoning | None = None
    service_tier: str | None = None
    prompt_cache_key: str | None = None
    text: TextControls | None = None

    def to_json_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "model": self.model,
            "input": self.input,
            "tools": list(self.tools or []),
            "parallel_tool_calls": self.parallel_tool_calls,
        }
        if self.instructions:
            value["instructions"] = self.instructions
        _put_optional(value, "reasoning", self.reasoning)
        _put_optional(value, "service_tier", self.service_tier)
        _put_optional(value, "prompt_cache_key", self.prompt_cache_key)
        _put_optional(value, "text", self.text)
        return value


@dataclass(frozen=True)
class RawMemoryMetadata:
    source_path: str

    def to_json_dict(self) -> dict[str, Any]:
        return {"source_path": self.source_path}


@dataclass(frozen=True)
class RawMemory:
    id: str
    metadata: RawMemoryMetadata
    items: list[Any]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "metadata": self.metadata.to_json_dict(),
            "items": self.items,
        }


@dataclass(frozen=True)
class MemorySummarizeInput:
    model: str
    raw_memories: list[RawMemory]
    reasoning: Reasoning | None = None

    def to_json_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "model": self.model,
            "traces": [memory.to_json_dict() for memory in self.raw_memories],
        }
        _put_optional(value, "reasoning", self.reasoning)
        return value


@dataclass(frozen=True)
class MemorySummarizeOutput:
    raw_memory: str
    memory_summary: str

    @classmethod
    def from_json_dict(cls, value: dict[str, Any]) -> "MemorySummarizeOutput":
        raw_memory = value.get("trace_summary", value.get("raw_memory"))
        if raw_memory is None:
            raise KeyError("trace_summary")
        return cls(
            raw_memory=str(raw_memory),
            memory_summary=str(value["memory_summary"]),
        )


@dataclass(frozen=True)
class ResponsesApiRequest:
    model: str
    instructions: str = ""
    input: list[Any] | None = None
    tools: list[Any] | None = None
    tool_choice: str = "auto"
    parallel_tool_calls: bool = False
    reasoning: Reasoning | None = None
    store: bool = False
    stream: bool = True
    include: list[str] | None = None
    service_tier: str | None = None
    prompt_cache_key: str | None = None
    text: TextControls | None = None
    client_metadata: dict[str, str] | None = None

    def to_ws_request(self) -> "ResponseCreateWsRequest":
        return ResponseCreateWsRequest(
            model=self.model,
            instructions=self.instructions,
            previous_response_id=None,
            input=list(self.input or []),
            tools=list(self.tools or []),
            tool_choice=self.tool_choice,
            parallel_tool_calls=self.parallel_tool_calls,
            reasoning=self.reasoning,
            store=self.store,
            stream=self.stream,
            include=list(self.include or []),
            service_tier=self.service_tier,
            prompt_cache_key=self.prompt_cache_key,
            text=self.text,
            generate=None,
            client_metadata=(
                dict(self.client_metadata) if self.client_metadata is not None else None
            ),
        )

    def to_json_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "model": self.model,
            "input": list(self.input or []),
            "tools": list(self.tools or []),
            "tool_choice": self.tool_choice,
            "parallel_tool_calls": self.parallel_tool_calls,
            "store": self.store,
            "stream": self.stream,
            "include": list(self.include or []),
        }
        if self.instructions:
            value["instructions"] = self.instructions
        _put_optional(value, "reasoning", self.reasoning)
        _put_optional(value, "service_tier", self.service_tier)
        _put_optional(value, "prompt_cache_key", self.prompt_cache_key)
        _put_optional(value, "text", self.text)
        _put_optional(value, "client_metadata", self.client_metadata)
        return value


@dataclass(frozen=True)
class ResponseCreateWsRequest:
    model: str
    instructions: str = ""
    previous_response_id: str | None = None
    input: list[Any] | None = None
    tools: list[Any] | None = None
    tool_choice: str = "auto"
    parallel_tool_calls: bool = False
    reasoning: Reasoning | None = None
    store: bool = False
    stream: bool = True
    include: list[str] | None = None
    service_tier: str | None = None
    prompt_cache_key: str | None = None
    text: TextControls | None = None
    generate: bool | None = None
    client_metadata: dict[str, str] | None = None

    @classmethod
    def from_api_request(cls, request: ResponsesApiRequest) -> "ResponseCreateWsRequest":
        return request.to_ws_request()

    def to_json_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "model": self.model,
            "input": list(self.input or []),
            "tools": list(self.tools or []),
            "tool_choice": self.tool_choice,
            "parallel_tool_calls": self.parallel_tool_calls,
            "store": self.store,
            "stream": self.stream,
            "include": list(self.include or []),
        }
        if self.instructions:
            value["instructions"] = self.instructions
        _put_optional(value, "previous_response_id", self.previous_response_id)
        _put_optional(value, "reasoning", self.reasoning)
        _put_optional(value, "service_tier", self.service_tier)
        _put_optional(value, "prompt_cache_key", self.prompt_cache_key)
        _put_optional(value, "text", self.text)
        _put_optional(value, "generate", self.generate)
        _put_optional(value, "client_metadata", self.client_metadata)
        return value


@dataclass(frozen=True)
class ResponseProcessedWsRequest:
    response_id: str

    def to_json_dict(self) -> dict[str, Any]:
        return {"response_id": self.response_id}


@dataclass(frozen=True)
class ResponsesWsRequest:
    kind: str
    payload: ResponseCreateWsRequest | ResponseProcessedWsRequest

    @classmethod
    def response_create(cls, request: ResponseCreateWsRequest) -> "ResponsesWsRequest":
        return cls("response.create", request)

    @classmethod
    def response_processed(
        cls,
        request: ResponseProcessedWsRequest,
    ) -> "ResponsesWsRequest":
        return cls("response.processed", request)

    def to_json_dict(self) -> dict[str, Any]:
        value = self.payload.to_json_dict()
        value["type"] = self.kind
        return value


@dataclass(frozen=True)
class ResponseEvent:
    kind: str
    value: Any = None


@dataclass
class ResponseStream:
    events: deque[Any]
    upstream_request_id: str | None = None

    @classmethod
    def from_iterable(
        cls,
        events: Iterable[Any],
        upstream_request_id: str | None = None,
    ) -> "ResponseStream":
        return cls(deque(events), upstream_request_id)

    def __iter__(self) -> "ResponseStream":
        return self

    def __next__(self) -> Any:
        if not self.events:
            raise StopIteration
        return self.events.popleft()


def response_create_client_metadata(
    client_metadata: dict[str, str] | None,
    trace: object | None,
) -> dict[str, str] | None:
    metadata = dict(client_metadata or {})
    traceparent = _trace_value(trace, "traceparent")
    if traceparent is not None:
        metadata[WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY] = traceparent
    tracestate = _trace_value(trace, "tracestate")
    if tracestate is not None:
        metadata[WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY] = tracestate
    return metadata or None


def create_text_param_for_request(
    verbosity: str | OpenAiVerbosity | None,
    output_schema: Any | None,
    output_schema_strict: bool,
) -> TextControls | None:
    if verbosity is None and output_schema is None:
        return None
    return TextControls(
        verbosity=OpenAiVerbosity.from_config(verbosity) if verbosity is not None else None,
        format=(
            TextFormat(
                schema=output_schema,
                strict=output_schema_strict,
                name="codex_output_schema",
            )
            if output_schema is not None
            else None
        ),
    )


def _put_optional(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if hasattr(value, "to_json_dict"):
        target[key] = value.to_json_dict()
    else:
        target[key] = value


def _skip_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _trace_value(trace: object | None, name: str) -> str | None:
    if trace is None:
        return None
    if isinstance(trace, dict):
        value = trace.get(name)
    else:
        value = getattr(trace, name, None)
    return str(value) if value is not None else None
