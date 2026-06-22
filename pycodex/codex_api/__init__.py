"""Python surface for selected Rust ``codex-api`` module contracts."""

from __future__ import annotations

from .api_bridge import map_api_error
from .auth import AuthError
from .auth import AuthHeaderTelemetry
from .auth import AuthProvider
from .auth import SharedAuthProvider
from .auth import auth_header_telemetry
from .common import CompactionInput
from .common import MemorySummarizeInput
from .common import MemorySummarizeOutput
from .common import OpenAiVerbosity
from .common import RawMemory
from .common import RawMemoryMetadata
from .common import Reasoning
from .common import ResponseCreateWsRequest
from .common import ResponseEvent
from .common import ResponseProcessedWsRequest
from .common import ResponseStream
from .common import ResponsesApiRequest
from .common import ResponsesWsRequest
from .common import TextControls
from .common import TextFormat
from .common import TextFormatType
from .common import WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY
from .common import WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY
from .common import create_text_param_for_request
from .common import response_create_client_metadata
from pycodex.codex_client import RequestTelemetry
from pycodex.codex_client import ReqwestTransport
from pycodex.codex_client import TransportError
from .error import ApiError
from .endpoint import CompactClient
from .endpoint import ImagesClient
from .endpoint import MemoriesClient
from .endpoint import ModelsClient
from .endpoint import RealtimeCallClient
from .endpoint import RealtimeCallResponse
from .endpoint import RealtimeEventParser
from .endpoint import RealtimeOutputModality
from .endpoint import RealtimeSessionConfig
from .endpoint import RealtimeSessionMode
from .endpoint import RealtimeWebsocketClient
from .endpoint import RealtimeWebsocketConnection
from .endpoint import RealtimeWebsocketEvents
from .endpoint import RealtimeWebsocketWriter
from .endpoint import ResponsesClient
from .endpoint import ResponsesOptions
from .endpoint import ResponsesWebsocketClient
from .endpoint import ResponsesWebsocketClose
from .endpoint import ResponsesWebsocketConnection
from .endpoint import ResponsesWebsocketProbe
from .endpoint import SearchClient
from .endpoint import session_update_session_json
from .endpoint import spawn_response_stream
from .endpoint.realtime_websocket import RealtimeEvent
from .files import OPENAI_FILE_FINALIZE_RETRY_DELAY
from .files import OPENAI_FILE_FINALIZE_TIMEOUT
from .files import OPENAI_FILE_REQUEST_TIMEOUT
from .files import OPENAI_FILE_UPLOAD_LIMIT_BYTES
from .files import OPENAI_FILE_URI_PREFIX
from .files import OPENAI_FILE_USE_CASE
from .files import OpenAiFileError
from .files import OpenAiFileResponse
from .files import OpenAiFileTransport
from .files import UploadedOpenAiFile
from .files import openai_file_uri
from .files import upload_local_file
from .images import ImageBackground
from .images import ImageData
from .images import ImageEditRequest
from .images import ImageGenerationRequest
from .images import ImageQuality
from .images import ImageResponse
from .images import ImageUrl
from .provider import Provider
from .provider import RetryConfig
from .provider import is_azure_responses_provider
from .requests import Compression
from .requests import SessionSource
from .requests import SubAgentSource
from .requests import attach_item_ids
from .requests import build_session_headers
from .requests import insert_header
from .requests import subagent_header
from .rate_limits import CreditsSnapshot
from .rate_limits import RateLimitError
from .rate_limits import RateLimitSnapshot
from .rate_limits import RateLimitWindow
from .rate_limits import parse_all_rate_limits
from .rate_limits import parse_default_rate_limit
from .rate_limits import parse_promo_message
from .rate_limits import parse_rate_limit_event
from .rate_limits import parse_rate_limit_for_limit
from .rate_limits import parse_rate_limit_reached_type
from .search import AllowedCaller
from .search import ApproximateLocation
from .search import ClickOperation
from .search import FinanceAssetType
from .search import FinanceOperation
from .search import FindOperation
from .search import LocationType
from .search import OpenOperation
from .search import ScreenshotOperation
from .search import SearchCommands
from .search import SearchContextSize
from .search import SearchFilters
from .search import SearchImageSettings
from .search import SearchInput
from .search import SearchQuery
from .search import SearchRequest
from .search import SearchResponse
from .search import SearchResponseLength
from .search import SearchSettings
from .search import SportsFunction
from .search import SportsLeague
from .search import SportsOperation
from .search import SportsToolName
from .search import TimeOperation
from .search import WeatherOperation
from .telemetry import SseTelemetry
from .telemetry import WebsocketTelemetry
from .telemetry import http_status
from .telemetry import response_status
from .telemetry import run_with_request_telemetry
from pycodex.protocol import RealtimeAudioFrame

__all__ = [
    "ApiError",
    "AuthError",
    "AuthHeaderTelemetry",
    "AuthProvider",
    "AllowedCaller",
    "ApproximateLocation",
    "ClickOperation",
    "Compression",
    "CompactionInput",
    "CompactClient",
    "CreditsSnapshot",
    "FinanceAssetType",
    "FinanceOperation",
    "FindOperation",
    "MemoriesClient",
    "MemorySummarizeInput",
    "MemorySummarizeOutput",
    "ModelsClient",
    "LocationType",
    "OPENAI_FILE_FINALIZE_RETRY_DELAY",
    "OPENAI_FILE_FINALIZE_TIMEOUT",
    "OPENAI_FILE_REQUEST_TIMEOUT",
    "OPENAI_FILE_UPLOAD_LIMIT_BYTES",
    "OPENAI_FILE_URI_PREFIX",
    "OPENAI_FILE_USE_CASE",
    "OpenAiVerbosity",
    "OpenAiFileError",
    "OpenAiFileResponse",
    "OpenAiFileTransport",
    "ImageBackground",
    "ImageData",
    "ImageEditRequest",
    "ImageGenerationRequest",
    "ImageQuality",
    "ImageResponse",
    "ImageUrl",
    "ImagesClient",
    "OpenOperation",
    "Provider",
    "RealtimeAudioFrame",
    "RealtimeCallClient",
    "RealtimeCallResponse",
    "RealtimeEvent",
    "RealtimeEventParser",
    "RealtimeOutputModality",
    "RealtimeSessionConfig",
    "RealtimeSessionMode",
    "RealtimeWebsocketClient",
    "RealtimeWebsocketConnection",
    "RealtimeWebsocketEvents",
    "RealtimeWebsocketWriter",
    "RawMemory",
    "RawMemoryMetadata",
    "RateLimitError",
    "RateLimitSnapshot",
    "RateLimitWindow",
    "Reasoning",
    "ResponseCreateWsRequest",
    "ResponseEvent",
    "ResponseProcessedWsRequest",
    "ResponseStream",
    "ResponsesApiRequest",
    "ResponsesClient",
    "ResponsesOptions",
    "ResponsesWebsocketClient",
    "ResponsesWebsocketClose",
    "ResponsesWebsocketConnection",
    "ResponsesWebsocketProbe",
    "ResponsesWsRequest",
    "RequestTelemetry",
    "ReqwestTransport",
    "RetryConfig",
    "ScreenshotOperation",
    "SearchCommands",
    "SearchContextSize",
    "SearchClient",
    "SearchFilters",
    "SearchImageSettings",
    "SearchInput",
    "SearchQuery",
    "SearchRequest",
    "SearchResponse",
    "SearchResponseLength",
    "SearchSettings",
    "SessionSource",
    "SharedAuthProvider",
    "SportsFunction",
    "SportsLeague",
    "SportsOperation",
    "SportsToolName",
    "SseTelemetry",
    "SubAgentSource",
    "TextControls",
    "TextFormat",
    "TextFormatType",
    "TimeOperation",
    "TransportError",
    "UploadedOpenAiFile",
    "WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY",
    "WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY",
    "WeatherOperation",
    "WebsocketTelemetry",
    "attach_item_ids",
    "auth_header_telemetry",
    "build_session_headers",
    "create_text_param_for_request",
    "http_status",
    "insert_header",
    "is_azure_responses_provider",
    "map_api_error",
    "parse_all_rate_limits",
    "parse_default_rate_limit",
    "parse_promo_message",
    "parse_rate_limit_event",
    "parse_rate_limit_for_limit",
    "parse_rate_limit_reached_type",
    "openai_file_uri",
    "response_create_client_metadata",
    "response_status",
    "run_with_request_telemetry",
    "session_update_session_json",
    "spawn_response_stream",
    "subagent_header",
    "upload_local_file",
]
