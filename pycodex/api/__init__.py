"""Python interface for Rust ``codex-api``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse, urlunparse


WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY = "ws_request_header_traceparent"
WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY = "ws_request_header_tracestate"


def build_session_headers(session_id: str | None = None, thread_id: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if session_id is not None:
        headers["session-id"] = session_id
    if thread_id is not None:
        headers["thread-id"] = thread_id
    return headers


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int
    base_delay: float
    retry_429: bool
    retry_5xx: bool
    retry_transport: bool

    def to_policy(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "base_delay": self.base_delay,
            "retry_on": {
                "retry_429": self.retry_429,
                "retry_5xx": self.retry_5xx,
                "retry_transport": self.retry_transport,
            },
        }


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    query_params: dict[str, str] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    retry: RetryConfig | None = None
    stream_idle_timeout: float | None = None

    def url_for_path(self, path: str) -> str:
        base = self.base_url.rstrip("/")
        clean_path = path.lstrip("/")
        url = base if not clean_path else f"{base}/{clean_path}"
        if self.query_params:
            query = "&".join(f"{key}={value}" for key, value in self.query_params.items())
            url += "?" + query
        return url

    def build_request(self, method: str, path: str) -> dict[str, Any]:
        return {
            "method": method,
            "url": self.url_for_path(path),
            "headers": dict(self.headers),
            "body": None,
            "compression": "none",
            "timeout": None,
        }

    def is_azure_responses_endpoint(self) -> bool:
        return is_azure_responses_provider(self.name, self.base_url)

    def websocket_url_for_path(self, path: str) -> str:
        parsed = urlparse(self.url_for_path(path))
        scheme = {"http": "ws", "https": "wss"}.get(parsed.scheme, parsed.scheme)
        return urlunparse(parsed._replace(scheme=scheme))


def is_azure_responses_provider(name: str, base_url: str | None = None) -> bool:
    if name.lower() == "azure":
        return True
    if base_url is None:
        return False
    lowered = base_url.lower()
    markers = (
        "openai.azure.",
        "cognitiveservices.azure.",
        "aoai.azure.",
        "azure-api.",
        "azurefd.",
        "windows.net/openai",
    )
    return any(marker in lowered for marker in markers)


class ApiError(Exception):
    pass


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class AuthHeaderTelemetry:
    has_auth_header: bool = False
    auth_kind: str | None = None


class AuthProvider:
    def add_auth_headers(self, headers: dict[str, str]) -> None:
        raise NotImplementedError


SharedAuthProvider = AuthProvider


def auth_header_telemetry(auth: AuthProvider) -> AuthHeaderTelemetry:
    headers: dict[str, str] = {}
    auth.add_auth_headers(headers)
    value = headers.get("Authorization")
    return AuthHeaderTelemetry(bool(value), value.split(" ", 1)[0].lower() if value else None)


@dataclass(frozen=True)
class Reasoning:
    effort: Any | None = None
    summary: Any | None = None


class OpenAiVerbosity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class TextFormat:
    schema: Any
    strict: bool
    name: str = "codex_output_schema"
    type: str = "json_schema"


@dataclass(frozen=True)
class TextControls:
    verbosity: OpenAiVerbosity | None = None
    format: TextFormat | None = None


def create_text_param_for_request(
    verbosity: str | OpenAiVerbosity | None,
    output_schema: Any | None,
    output_schema_strict: bool,
) -> TextControls | None:
    if verbosity is None and output_schema is None:
        return None
    parsed = OpenAiVerbosity(verbosity) if isinstance(verbosity, str) else verbosity
    fmt = TextFormat(schema=output_schema, strict=output_schema_strict) if output_schema is not None else None
    return TextControls(verbosity=parsed, format=fmt)


def response_create_client_metadata(
    client_metadata: dict[str, str] | None,
    trace: Any | None,
) -> dict[str, str] | None:
    metadata = dict(client_metadata or {})
    traceparent = getattr(trace, "traceparent", None) if trace is not None else None
    tracestate = getattr(trace, "tracestate", None) if trace is not None else None
    if traceparent:
        metadata[WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY] = traceparent
    if tracestate:
        metadata[WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY] = tracestate
    return metadata or None


@dataclass(frozen=True)
class CompactionInput:
    model: str
    input: Any
    instructions: str = ""
    tools: list[Any] = field(default_factory=list)
    parallel_tool_calls: bool = False
    reasoning: Reasoning | None = None
    service_tier: str | None = None
    prompt_cache_key: str | None = None
    text: TextControls | None = None


@dataclass(frozen=True)
class RawMemoryMetadata:
    source_path: str


@dataclass(frozen=True)
class RawMemory:
    id: str
    metadata: RawMemoryMetadata
    items: list[Any]


@dataclass(frozen=True)
class MemorySummarizeInput:
    model: str
    raw_memories: list[RawMemory]
    reasoning: Reasoning | None = None


@dataclass(frozen=True)
class MemorySummarizeOutput:
    raw_memory: str
    memory_summary: str


@dataclass(frozen=True)
class ResponsesApiRequest:
    model: str
    instructions: str
    input: list[Any]
    tools: list[Any]
    tool_choice: str
    parallel_tool_calls: bool
    reasoning: Reasoning | None
    store: bool
    stream: bool
    include: list[str]
    service_tier: str | None = None
    prompt_cache_key: str | None = None
    text: TextControls | None = None
    client_metadata: dict[str, str] | None = None


@dataclass(frozen=True)
class ResponseCreateWsRequest:
    model: str
    instructions: str
    previous_response_id: str | None
    input: list[Any]
    tools: list[Any]
    tool_choice: str
    parallel_tool_calls: bool
    reasoning: Reasoning | None
    store: bool
    stream: bool
    include: list[str]
    service_tier: str | None = None
    prompt_cache_key: str | None = None
    text: TextControls | None = None
    generate: bool | None = None
    client_metadata: dict[str, str] | None = None


@dataclass(frozen=True)
class ResponseProcessedWsRequest:
    response_id: str


@dataclass(frozen=True)
class ResponseStream:
    rx_event: Any
    upstream_request_id: str | None = None


class ResponseEvent:
    pass


class _EndpointClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs


CompactClient = ImagesClient = MemoriesClient = ModelsClient = RealtimeCallClient = SearchClient = ResponsesClient = _EndpointClient
RealtimeWebsocketClient = ResponsesWebsocketClient = _EndpointClient
RealtimeCallResponse = RealtimeEventParser = RealtimeOutputModality = RealtimeSessionConfig = RealtimeSessionMode = object
RealtimeWebsocketConnection = RealtimeWebsocketEvents = RealtimeWebsocketWriter = object
ResponsesOptions = ResponsesWebsocketClose = ResponsesWebsocketConnection = ResponsesWebsocketProbe = object
Compression = object
ImageBackground = ImageData = ImageEditRequest = ImageGenerationRequest = ImageQuality = ImageResponse = ImageUrl = object
AllowedCaller = ApproximateLocation = ClickOperation = FinanceAssetType = FinanceOperation = FindOperation = object
LocationType = OpenOperation = ScreenshotOperation = SearchCommands = SearchContextSize = SearchFilters = object
SearchImageSettings = SearchInput = SearchQuery = SearchRequest = SearchResponse = SearchResponseLength = object
SearchSettings = SportsFunction = SportsLeague = SportsOperation = SportsToolName = TimeOperation = WeatherOperation = object
SseTelemetry = WebsocketTelemetry = object


def map_api_error(error: Any) -> Any:
    return error


def session_update_session_json(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"args": args, "kwargs": kwargs}


def upload_local_file(*args: Any, **kwargs: Any) -> None:
    raise NotImplementedError("codex-api file upload is not ported")
