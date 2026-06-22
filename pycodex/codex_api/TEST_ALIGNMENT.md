# codex-api test alignment

Rust crate: `codex-api`

Python package: `pycodex/codex_api`

Status: `complete`

Module mapping:

- `codex/codex-rs/codex-api/src/lib.rs` ->
  `pycodex/codex_api/__init__.py` (`complete`; crate-root facade)
- `codex/codex-rs/codex-api/src/api_bridge.rs` ->
  `pycodex/codex_api/api_bridge.py` (`complete`)
- `codex/codex-rs/codex-api/src/auth.rs` ->
  `pycodex/codex_api/auth.py` (`complete`)
- `codex/codex-rs/codex-api/src/common.rs` ->
  `pycodex/codex_api/common.py` (`complete`)
- `codex/codex-rs/codex-api/src/error.rs` ->
  `pycodex/codex_api/error.py` (`complete`)
- `codex/codex-rs/codex-api/src/endpoint/compact.rs` ->
  `pycodex/codex_api/endpoint/compact.py` (`complete`)
- `codex/codex-rs/codex-api/src/endpoint/images.rs` ->
  `pycodex/codex_api/endpoint/images.py` (`complete`)
- `codex/codex-rs/codex-api/src/endpoint/memories.rs` ->
  `pycodex/codex_api/endpoint/memories.py` (`complete`)
- `codex/codex-rs/codex-api/src/endpoint/models.rs` ->
  `pycodex/codex_api/endpoint/models.py` (`complete`)
- `codex/codex-rs/codex-api/src/endpoint/realtime_call.rs` ->
  `pycodex/codex_api/endpoint/realtime_call.py` (`complete`)
- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/{protocol,methods_common,methods_v1,methods_v2}.rs` ->
  `pycodex/codex_api/endpoint/realtime_websocket/` (`complete`
  for pure outbound-message/session helper slice)
- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/{protocol,protocol_common,protocol_v1,protocol_v2}.rs` ->
  `pycodex/codex_api/endpoint/realtime_websocket/` (`complete` for pure
  event parser slice)
- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/methods.rs` ->
  `pycodex/codex_api/endpoint/realtime_websocket/methods.py`
  (`complete` for websocket URL/config and active-transcript helper
  slices, dependency-light read/write facade, and standard-library
  connect/session projection including dependency-light custom-CA SSL context
  selection for `wss`)
- `codex/codex-rs/codex-api/src/endpoint/responses.rs` ->
  `pycodex/codex_api/endpoint/responses.py` (`complete`)
- `codex/codex-rs/codex-api/src/endpoint/responses_websocket.rs` ->
  `pycodex/codex_api/endpoint/responses_websocket.py` (`complete`;
  helper, dependency-light stream/send, and standard-library connect/probe
  projection slices covered, including dependency-light custom-CA SSL context
  selection for `wss`)
- `codex/codex-rs/codex-api/src/endpoint/search.rs` ->
  `pycodex/codex_api/endpoint/search.py` (`complete`)
- `codex/codex-rs/codex-api/src/endpoint/session.rs` ->
  `pycodex/codex_api/endpoint/session.py` (`complete`)
- `codex/codex-rs/codex-api/src/files.rs` ->
  `pycodex/codex_api/files.py` (`complete`)
- `codex/codex-rs/codex-api/src/images.rs` ->
  `pycodex/codex_api/images.py` (`complete`)
- `codex/codex-rs/codex-api/src/provider.rs` ->
  `pycodex/codex_api/provider.py` (`complete`)
- `codex/codex-rs/codex-api/src/rate_limits.rs` ->
  `pycodex/codex_api/rate_limits.py` (`complete`)
- `codex/codex-rs/codex-api/src/requests/headers.rs` ->
  `pycodex/codex_api/requests/headers.py` (`complete`)
- `codex/codex-rs/codex-api/src/requests/responses.rs` ->
  `pycodex/codex_api/requests/responses.py` (`complete`)
- `codex/codex-rs/codex-api/src/search.rs` ->
  `pycodex/codex_api/search.py` (`complete`)
- `codex/codex-rs/codex-api/src/sse/responses.rs` ->
  `pycodex/codex_api/sse/responses.py` (`complete`)
- `codex/codex-rs/codex-api/src/telemetry.rs` ->
  `pycodex/codex_api/telemetry.py` (`complete`)

Rust-derived behavior covered in `tests/test_codex_api_lib_rs.py`:

- Source-defined crate-root `pub use` facade from `src/lib.rs`, including
  module API exports, `codex-client` transport/telemetry aliases, and
  realtime protocol facade names.
- Re-export identity checks for cross-crate anchors
  `RequestTelemetry`, `ReqwestTransport`, `TransportError`,
  `RealtimeAudioFrame`, `RealtimeOutputModality`, realtime websocket facade
  classes, responses websocket facade classes, and shared common/request
  helpers.

Rust-derived behavior covered in `tests/test_codex_api_api_bridge_rs.py`:

- Rust tests from `src/api_bridge_tests.rs` for direct server-overloaded
  mapping, 503 overloaded body classification, 400 cyber-policy body handling,
  websocket-wrapped cyber-policy bodies, fallback cyber-policy messages,
  unknown 400 invalid-request preservation, usage-limit active-limit header
  handling, absence of limit-name fallback to limit id, unparseable
  rate-limit-reached-type headers, and identity authorization header
  extraction from unexpected responses.
- Source contract for direct `ApiError` variants, stream/retryable errors,
  invalid-image 400 bodies, usage-not-included 429 bodies, and retry-limit
  request tracking id fallback.
- Source contract for direct API status errors, rate-limit-as-stream,
  `slow_down` overloaded bodies, retry-limit transport fallback,
  timeout/network/build transport variants, 500 internal-server mapping,
  request-id precedence, invalid `x-error-json` ignoring, and usage-limit
  plan/reset timestamp projection.

Rust-derived behavior covered in `tests/test_codex_api_auth_rs.py`:


- `AuthError` display strings and conversion to `TransportError`.
- `AuthProvider::to_auth_headers` fresh header-map construction.
- Default `AuthProvider::apply_auth` header-only request mutation semantics.
- Rust `HeaderMap`-style case-insensitive auth header replacement in
  `to_auth_headers` and default `apply_auth`.
- `auth_header_telemetry` authorization-header detection and absent-header
  fallback.

Rust-derived behavior covered in `tests/test_codex_api_common_rs.py`:

- `response_create_client_metadata` traceparent/tracestate merge behavior and
  empty-result fallback.
- `create_text_param_for_request` no-op, verbosity, JSON-schema, strict, and
  `codex_output_schema` branches.
- `ResponsesApiRequest` to `ResponseCreateWsRequest` conversion.
- Serde skip/rename/alias behavior for compaction and memory summarize payloads.
- Required-field rejection when memory summarize output omits both
  `trace_summary` and `raw_memory`.
- Preservation of empty `client_metadata` through websocket request conversion.
- Tagged `ResponsesWsRequest` wire names and lightweight `ResponseStream`
  event/upstream-request-id boundary.

Rust-derived behavior covered in `tests/test_codex_api_error_rs.py`:

- `ApiError` display strings for all variants in `src/error.rs`.
- Transparent transport error display.
- `Retryable` optional delay retention while display only includes the message.
- Transparent display coverage for multiple `TransportError` variants.
- `From<RateLimitError> for ApiError` behavior via
  `ApiError.from_rate_limit_error(...)`.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_compact_rs.py`:

- Rust test `path_is_responses_compact` from `src/endpoint/compact.rs`.
- Source contract for `compact`: POST path, arbitrary `serde_json::Value`
  request-body preservation, request timeout mutation, and `output` decoding
  into protocol `ResponseItem` values.
- Source contract for `with_telemetry`: a new client is returned with request
  telemetry configured while transport/provider/auth boundaries are preserved.
- Source contract for `compact_input`: `CompactionInput` serialization before
  delegating to `compact`.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_images_rs.py`:

- Rust tests `generate_posts_typed_request_and_parses_image_response`,
  `edit_posts_typed_request_and_parses_image_response`, and
  `image_response_requires_image_data` from `src/endpoint/images.rs`.
- Generation and edit POST paths, JSON body construction through the typed
  image request objects, typed `ImageResponse` decoding, and image
  response-decode failures mapped to `ApiError::Stream`-style messages.
- Source contract for `generate`/`edit`: extra headers/auth are applied through
  the shared session-shaped request boundary.
- Source contract for `with_telemetry`: a new client is returned with request
  telemetry configured while transport/provider/auth boundaries are preserved.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_memories_rs.py`:

- Rust tests `path_is_memories_trace_summarize_for_wire_compatibility` and
  `summarize_input_posts_expected_payload_and_parses_output` from
  `src/endpoint/memories.rs`.
- Memory summarize POST path, typed `MemorySummarizeInput` serialization,
  raw JSON body preservation, auth/extra-header application, `output`
  decoding, and `trace_summary`/`raw_memory` alias handling.
- Source contract for `summarize`: arbitrary `serde_json::Value` request-body
  preservation.
- Source contract for `with_telemetry`: a new client is returned with request
  telemetry configured while transport/provider/auth boundaries are preserved.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_models_rs.py`:

- Rust tests `appends_client_version_query`, `parses_models_response`, and
  `list_models_includes_etag` from `src/endpoint/models.rs`.
- Integration-test path/method behavior from
  `tests/models_integration.rs::models_client_hits_models_endpoint`.
- Provider query-param preservation when appending `client_version`, extra
  header and auth-header application, and decode failures mapped to
  `ApiError::Stream`-style messages.
- Source contract for `with_telemetry`: a new client is returned with request
  telemetry configured while transport/provider/auth boundaries are preserved.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_realtime_call_rs.py`:

- Rust tests `sends_sdp_offer_as_raw_body`,
  `extracts_call_id_from_forwarded_backend_location`,
  `sends_api_session_call_as_multipart_body`,
  `sends_backend_session_call_as_json_body`,
  `errors_when_location_is_missing`, and `rejects_location_without_call_id`
  from `src/endpoint/realtime_call.rs`.
- SDP-only call creation, API multipart session call creation, backend JSON
  session call creation, auth/header application, response SDP decoding,
  Location call-id parsing, and missing/invalid Location error strings.
- Source contract for `create_with_headers`: extra headers are forwarded
  through the shared session-shaped request boundary alongside auth and
  content-type mutation.
- Source contract for `with_telemetry`: a new client is returned with request
  telemetry configured while transport/provider/auth boundaries are preserved.
- Lightweight `RealtimeSessionConfig` and `session_update_session_json`
  interface constraints used by realtime call creation. The implementation now
  delegates to the realtime websocket helper package. Full websocket runtime
  behavior remains owned by the realtime websocket modules.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_realtime_websocket_methods_rs.py`:

- `normalized_session_mode` and `websocket_intent` behavior from
  `src/endpoint/realtime_websocket/methods_common.rs`.
- V1 `conversation.item.create`, `conversation.handoff.append`, quicksilver
  session JSON, audio format, voice, id, and model behavior from
  `methods_v1.rs` plus `methods.rs::e2e_connect_and_exchange_events_against_mock_ws_server`.
- V2 realtime session JSON for output modalities, input/output audio,
  transcription model, server VAD, background-agent/remain-silent tool schema,
  tool choice, id, and model behavior from `methods_v2.rs` plus
  `methods.rs::realtime_v2_session_update_includes_background_agent_tool_and_handoff_output_item`.
- V2 `function_call_output` item JSON from
  `methods.rs::realtime_v2_session_update_includes_background_agent_tool_and_handoff_output_item`.
- V2 transcription session omission of instructions, output audio, tools, and
  tool choice from
  `methods.rs::transcription_mode_session_update_omits_output_audio_and_instructions`.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_realtime_websocket_url_rs.py`:

- `websocket_url_from_api_url` scheme conversion, default `/v1/realtime`
  path, `/v1` path append behavior, existing realtime path preservation,
  intent/model append order, extra query filtering, V1 transcription-mode
  intent behavior, and Realtime V2 intent omission from
  `src/endpoint/realtime_websocket/methods.rs` URL tests.
- `websocket_url_from_api_url_for_call` sideband `call_id` behavior from
  `methods.rs::websocket_url_for_call_id_joins_existing_realtime_session`.
- Unsupported scheme errors and `websocket_config` default facade from
  `methods.rs` source contracts.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_realtime_websocket_active_transcript_rs.py`:

- `RealtimeWebsocketEvents::update_active_transcript` behavior from
  `src/endpoint/realtime_websocket/methods.rs`: input/output transcript deltas,
  input/output transcript done replacement, handoff active-transcript injection,
  last-handoff entry accounting, speech-started input boundaries, and
  response-created output boundaries.
- Low-level `append_transcript_delta`, `apply_transcript_done`,
  `append_handoff_input`, and `contains_transcript_entry` contracts including
  empty text handling, same-role merge/replace, trimmed handoff input, and
  duplicate suppression.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py`:

- `RealtimeWebsocketWriter`, `RealtimeWebsocketEvents`, and
  `RealtimeWebsocketConnection` behavior from
  `src/endpoint/realtime_websocket/methods.rs`: audio-frame send JSON,
  conversation item/function-call output send JSON, response/session update
  send JSON, idempotent close, closed-send errors, send/close/read error
  mapping, ignored unsupported text/ping/pong/frame messages, binary frame
  error events, close frame termination, shared closed state, and active
  transcript mutation while parsing event messages.
- `RealtimeWebsocketClient::connect`, `connect_webrtc_sideband`,
  `connect_realtime_websocket_url`, `merge_request_headers`, and
  `with_session_id_header` behavior from `methods.rs`: provider
  base/query/model URL construction, case-insensitive header precedence,
  `x-session-id` insertion/replacement and invalid value rejection, WebRTC
  sideband `call_id` joins, connector error mapping, stream adaptation,
  immediate `session.update` send after connect, closed stream termination,
  and custom-CA TLS configuration/error projection for secure websocket
  connections.
- `methods.rs::e2e_connect_and_exchange_events_against_mock_ws_server` concrete
  websocket runtime contract: local `ws://` handshake, client-masked text frame
  sends, server text frame events, `session.update` ordering, V1 audio and
  transcript parsing, active-transcript handoff projection, and graceful close.
- `connect_webrtc_sideband` retry behavior from `methods.rs`: attempts cover
  `0..=max_attempts` and failed joins sleep with
  `codex_client::retry::backoff(base_delay, attempt + 1)`.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py`:

- Shared `parse_realtime_event` dispatch, `session.updated`, transcript
  delta/done, error fallback, invalid JSON/missing type, unsupported events,
  and required-field fallthrough from
  `src/endpoint/realtime_websocket/{protocol,protocol_common}.rs`.
- V1 audio delta, item added/done, explicit handoff requested, input
  transcript aliases, and output transcript aliases from
  `protocol_v1.rs` and corresponding `methods.rs` parser tests, including
  Rust `as_u64` plus `u32`/`u16` conversion rejection for invalid audio
  numeric fields.
- V2 background-agent handoff tool calls, remain-silent noop tool calls,
  transcript aliases, item created/done, defaulted audio delta shape,
  speech-started, response cancelled/done/created lifecycle events, and
  response id extraction behavior from `protocol_v2.rs` and corresponding
  `methods.rs` parser tests, including default fallback for invalid audio
  numeric fields.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_responses_rs.py`:

- `ResponsesClient.new`, `with_telemetry`, and `ResponsesOptions` storage from
  `src/endpoint/responses.rs`.
- `stream_request` JSON body shaping, session/thread/client-request-id headers,
  subagent header projection, Azure stored-request item-id attachment, and
  delegation to `stream`.
- `stream` fixed POST path, `accept: text/event-stream` insertion, compression
  projection to `codex-client`, and `EndpointSession.stream_with` delegation.
- `spawn_response_stream` handoff boundary, upstream request id projection,
  turn-state header side effect, and delegation to the `codex-api/src/sse`
  Responses stream parser.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_responses_websocket_rs.py`:

- Rust tests from `src/endpoint/responses_websocket.rs` for permessage-deflate
  config projection, wrapped websocket error parsing, non-error payload
  ignoring, HTTP transport projection for websocket error frames,
  connection-limit retryable mapping, absent-status no-op mapping, and
  provider/extra/default header precedence including case-insensitive
  `HeaderMap` name matching.
- Source contract for wrapped websocket error status handling: `status` /
  `status_code` deserialize through `Option<u16>`, and mapping applies
  `StatusCode::from_u16(...).ok()?` before constructing HTTP transport errors.
- Source contract for `status_code` alias parsing and JSON scalar header value
  conversion for strings, numbers, and booleans, including invalid header
  name/value skip behavior from `HeaderName::from_bytes` and
  `HeaderValue::from_str`.
- Source contract from `send_websocket_request`,
  `run_websocket_response_stream`, and `ResponsesWebsocketConnection` for
  compact request JSON, send idle-timeout boundary mapping including the
  concrete stdlib stream timeout/restore projection,
  send/read/close/EOF/idle-timeout errors, request/event telemetry callback
  shape, invalid text ignoring, wrapped-error priority,
  rate-limit event mapping, server-model de-duplication, model-verification
  events, completed termination, metadata prelude events,
  `response.processed` sends, and terminal-error connection closure.
- Source contract from `ResponsesWebsocketClient::new/connect/probe_handshake`,
  `connect_websocket`, and `immediate_close_from_message` for websocket URL
  construction, provider/extra/default header and auth application, turn-state
  capture, metadata projection, non-101 HTTP transport-error mapping,
  strict UTF-8 body projection for non-101 HTTP errors including valid-body
  preservation, invalid-body clearing, and Content-Length body reads across
  the header/body boundary, websocket upgrade/connection/accept validation,
  successful 101 metadata and turn-state extraction from case-insensitive
  `x-codex-turn-state`, `x-reasoning-included`, `x-models-etag`, and
  `openai-model` headers,
  immediate close-frame probe reporting, timeout-without-close no-op behavior,
  request-target path/query projection, bracketed IPv6 Host authority
  formatting, dependency-light custom-CA SSL context selection/error mapping
  for `wss`, dependency-light text send timeout, socket-timeout restore,
  binary/close/ping/pong frame behavior, and
  the `WsStream` pump contract that replies to server Ping frames with Pong,
  filters Ping/Pong frames from callers, and forwards text/binary/close/frame
  messages.

Optional live Rust-boundary smoke check in
`tests/test_codex_api_endpoint_responses_websocket_live_rs.py`:

- Source contract from `connect_websocket`: a real non-local `wss://` endpoint
  performs TLS, HTTP 101/Sec-WebSocket-Accept validation, and successful
  response metadata projection through the Python standard-library websocket
  connector. The test rejects local endpoints and is skipped unless
  `PYCODEX_LIVE_RESPONSES_WS_URL` is set with real headers supplied through
  `PYCODEX_LIVE_RESPONSES_WS_HEADERS_JSON` or `OPENAI_API_KEY`.
- Cross-crate caller contract from `codex-cli/src/doctor.rs`:
  `doctor_websocket_check` now calls
  `ResponsesWebsocketClient.probe_handshake(...)` with the Rust beta websocket
  header, so doctor diagnostics exercise this module's real probe boundary.
  The Rust-derived coverage lives in
  `tests/test_cli_doctor_updates.py` under the websocket doctor tests,
  including endpoint query preservation through the temporary `Provider`
  boundary.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_search_rs.py`:

- Rust test `search_posts_typed_request_and_parses_encrypted_output` from
  `src/endpoint/search.rs`.
- Search POST path, typed `SearchRequest` JSON body construction, encrypted
  output response decoding, and missing encrypted-output failures mapped to
  `ApiError::Stream`-style messages.
- Source contract for `search`: extra headers/auth are applied through the
  shared session-shaped request boundary.
- Source contract for `with_telemetry`: a new client is returned with request
  telemetry configured while transport/provider/auth boundaries are preserved.

Rust-derived behavior covered in `tests/test_codex_api_endpoint_session_rs.py`:

- `EndpointSession.new`, `with_request_telemetry`, and `provider` storage
  behavior from `src/endpoint/session.rs`.
- Provider request construction, extra-header extension, optional JSON body
  attachment, and configure-before-auth ordering.
- Auth application before `transport.execute` / `transport.stream`.
- Request telemetry retry wrapping with request rebuilding between attempts.
- Terminal `TransportError` mapping to `ApiError::Transport`.

Rust-derived behavior covered in `tests/test_codex_api_files_rs.py`:

- `openai_file_uri` sediment URI construction.
- `upload_local_file` preflight behavior for missing paths, non-files, and
  over-limit files.
- Create/upload/finalize request shape, auth headers, timeout constants,
  canonical returned URI, retry-finalize sleep, and success payload mapping.
- Non-success status, invalid JSON decode, finalize timeout, missing
  `download_url`, and failed finalize error mapping.
- `DownloadLinkResponse` optional string field decoding for present non-string
  values, and successful finalize fallback to the local file name when
  `file_name` is absent.

Rust-derived behavior covered in `tests/test_codex_api_images_rs.py`:

- `ImageGenerationRequest` serialization from
  `endpoint/images.rs::generate_posts_typed_request_and_parses_image_response`.
- `ImageEditRequest` serialization from
  `endpoint/images.rs::edit_posts_typed_request_and_parses_image_response`.
- Lowercase image background/quality enum wire values.
- `ImageResponse` decoding with optional `background`, `quality`, and `size`
  defaults.
- Required `data` behavior from
  `endpoint/images.rs::image_response_requires_image_data`.
- Rust `u64`-style non-negative `created` deserialization.
- Required `ImageData.b64_json` behavior.
- Full lowercase wire-value coverage for all image background/quality enum
  variants.
- `ImageUrl` `image_url` wire field round trip.

Rust-derived behavior covered in `tests/test_codex_api_provider_rs.py`:

- `RetryConfig::to_policy` conversion.
- `Provider::url_for_path`, `build_request`, `is_azure_responses_endpoint`,
  and `websocket_url_for_path` behavior.
- Rust test `detects_azure_responses_base_urls`.
- Source contract for `websocket_url_for_path` preserving unknown schemes
  unchanged through the `_ => return Ok(url)` branch.

Rust-derived behavior covered in `tests/test_codex_api_requests_headers_rs.py`:

- `build_session_headers` optional session/thread header construction.
- `subagent_header` mappings for review, compact, memory consolidation, thread
  spawn, caller-provided labels, and non-subagent sources.
- `insert_header` invalid name/value skip behavior.
- `HeaderValue::from_str` value validation: visible ASCII and HTAB are
  accepted; other controls, DEL, and non-ASCII values are skipped.

Rust-derived behavior covered in `tests/test_codex_api_requests_responses_rs.py`:

- `Compression` public `None`/`Zstd` request-surface variants.
- `attach_item_ids` early-return behavior for absent or non-array `input`.
- `attach_item_ids` zip truncation with original `ResponseItem` entries.
- Non-empty id insertion for reasoning, message, web search, function call,
  tool search, local shell, and custom tool call response items.
- Empty, absent, non-object, and non-matching item skip behavior.
- Existing serialized `id` replacement through Rust's `obj.insert(...)`
  branch.

Rust-derived behavior covered in `tests/test_codex_api_telemetry_rs.py`:

- Public `SseTelemetry` and `WebsocketTelemetry` structural trait surface.
- `WithStatus` response-status extraction and `http_status` HTTP-only mapping.
- `run_with_request_telemetry` success callback shape.
- `run_with_request_telemetry` HTTP-error callback status, retry handoff, and
  subsequent success callback ordering.
- `run_with_request_telemetry` non-HTTP transport error callback without
  status and propagation when retry policy declines it.
- `run_with_request_telemetry` absent telemetry branch preserves retry/send
  behavior without callbacks.

Rust-derived behavior covered in `tests/test_codex_api_rate_limits_rs.py`:

- Rust tests `parse_rate_limit_for_limit_defaults_to_codex_headers`,
  `parse_rate_limit_for_limit_reads_secondary_headers`,
  `parse_rate_limit_for_limit_prefers_limit_name_header`,
  `parse_all_rate_limits_reads_all_limit_families`, and
  `parse_all_rate_limits_includes_default_codex_snapshot`.
- `parse_rate_limit_event` JSON event mapping for windows, credits, strict
  JSON bool credit fields, plan type, and normalized metered/legacy limit
  names.
- Promo message, protocol-enum reached-type filtering, credits, non-finite
  numeric, zero-only window, and invalid-event helper branches from
  `src/rate_limits.rs`.
- `RateLimitError` message-only display behavior.

Rust-derived behavior covered in `tests/test_codex_api_search_rs.py`:

- `SearchRequest` serialization from
  `endpoint/search.rs::search_posts_typed_request_and_parses_encrypted_output`.
- `SearchInput` untagged text and response-item-list serialization.
- `SearchCommands` operation field names and lowercase enum values for query,
  image query, open, click, find, screenshot, finance, weather, sports, time,
  and response length commands.
- `SearchSettings` user location, context size, filters, image settings,
  allowed caller, and external web access skip/rename behavior.
- `SearchResponse` encrypted-output decoding and required field behavior.
- Rust `u64`-style non-negative integer validation for search operation and
  request limit fields.
- Full enum wire-value coverage for finance, sports, response length, and
  allowed caller variants.

Rust-derived behavior covered in `tests/test_codex_api_sse_responses_rs.py`:

- `ResponsesStreamEvent::response_model` header precedence, case-insensitive
  OpenAI model header names, and top-level/response-header fallback behavior
  from `src/sse/responses.rs`.
- `ResponsesStreamEvent::model_verifications` metadata-only
  `trusted_access_for_cyber` decoding and unknown/non-array skip behavior.
- `process_responses_event` mapping for created, text delta, completed usage,
  output items, reasoning deltas, tool-call input deltas, and reasoning summary
  part events.
- `response.completed` invalid response-shape parse errors mapped to
  `ApiError::Stream`-style messages.
- `response.failed` classification for context-window, quota, usage-not-
  included, cyber-policy, invalid-prompt, overloaded/slow-down, and retryable
  rate-limit errors.
- `response.incomplete` stream-error message construction and
  `try_parse_retry_after` seconds/milliseconds parsing.
- `process_sse` stream behavior for parsing SSE `data:` frames, ignoring
  invalid JSON, emitting response-header server model changes, metadata model
  verifications, terminal completed events, stored failed-response errors on
  stream close, missing-completed stream errors, transport errors, and idle
  timeout errors.
- `spawn_response_stream` response-header prelude behavior for upstream request
  id, server model, rate-limit snapshots, models ETag, reasoning-included
  marker, and turn-state capture.
- Rust tests for ignoring bare `response.model` payload fields and ignoring
  model-verification response headers.

Validation:

- `python -m pytest tests/test_codex_api_requests_responses_rs.py -q --tb=short`
  passed on 2026-06-21 with `6 passed, 3 subtests passed`.
- `python -m py_compile pycodex\codex_api\requests\responses.py tests\test_codex_api_requests_responses_rs.py`
  passed on 2026-06-21.
- `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `207 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_requests_headers_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed, 4 subtests passed`.
- `python -m py_compile pycodex\codex_api\requests\headers.py tests\test_codex_api_requests_headers_rs.py`
  passed on 2026-06-21.
- `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `206 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_provider_rs.py -q --tb=short`
  passed on 2026-06-21 with `6 passed, 9 subtests passed`.
- `python -m py_compile pycodex\codex_api\provider.py tests\test_codex_api_provider_rs.py`
  passed on 2026-06-21.
- `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `205 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `32 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `63 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `205 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `31 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `62 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `204 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `30 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `61 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `203 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `19 passed, 3 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\realtime_websocket\methods.py tests\test_codex_api_endpoint_realtime_websocket_runtime_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_runtime_rs tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-21 with `52 tests`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `202 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `29 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `200 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `27 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `198 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `26 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `197 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_compact_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- `python -m py_compile pycodex/codex_api/endpoint/compact.py tests/test_codex_api_endpoint_compact_rs.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `215 passed, 47 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_memories_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- `python -m py_compile pycodex/codex_api/endpoint/memories.py tests/test_codex_api_endpoint_memories_rs.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `217 passed, 47 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_images_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- `python -m py_compile tests/test_codex_api_endpoint_images_rs.py pycodex/codex_api/endpoint/images.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `219 passed, 47 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_search_rs.py -q --tb=short`
  passed on 2026-06-21 with `4 passed`.
- `python -m py_compile tests/test_codex_api_endpoint_search_rs.py pycodex/codex_api/endpoint/search.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `221 passed, 47 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_models_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- `python -m py_compile tests/test_codex_api_endpoint_models_rs.py pycodex/codex_api/endpoint/models.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `222 passed, 47 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_call_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- `python -m py_compile tests/test_codex_api_endpoint_realtime_call_rs.py pycodex/codex_api/endpoint/realtime_call.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `224 passed, 47 subtests passed`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_api_auth_rs tests.test_codex_api_error_rs tests.test_codex_api_rate_limits_rs tests.test_codex_api_common_rs tests.test_codex_api_provider_rs tests.test_codex_api_requests_headers_rs tests.test_codex_api_requests_responses_rs tests.test_codex_api_telemetry_rs tests.test_codex_api_files_rs tests.test_codex_api_images_rs tests.test_codex_api_search_rs tests.test_codex_api_endpoint_models_rs tests.test_codex_api_endpoint_images_rs tests.test_codex_api_endpoint_search_rs tests.test_codex_api_endpoint_compact_rs tests.test_codex_api_endpoint_memories_rs tests.test_codex_api_endpoint_realtime_call_rs -v`
  passed on 2026-06-20 with `78 tests`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `16 passed, 3 subtests passed`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_runtime_rs tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-21 with `49 tests`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `192 passed, 45 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/realtime_websocket/methods.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py`
  passed on 2026-06-21.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_api_auth_rs tests.test_codex_api_error_rs tests.test_codex_api_rate_limits_rs tests.test_codex_api_common_rs tests.test_codex_api_provider_rs tests.test_codex_api_requests_headers_rs tests.test_codex_api_requests_responses_rs tests.test_codex_api_telemetry_rs tests.test_codex_api_files_rs tests.test_codex_api_images_rs tests.test_codex_api_search_rs tests.test_codex_api_endpoint_models_rs tests.test_codex_api_endpoint_images_rs tests.test_codex_api_endpoint_search_rs tests.test_codex_api_endpoint_compact_rs tests.test_codex_api_endpoint_memories_rs tests.test_codex_api_endpoint_realtime_call_rs -v`
  passed on 2026-06-20 with `78 tests`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `15 passed`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_runtime_rs tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-21 with `48 tests`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `191 passed, 42 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/realtime_websocket/methods.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py`
  passed on 2026-06-21.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_api_auth_rs tests.test_codex_api_error_rs tests.test_codex_api_rate_limits_rs tests.test_codex_api_common_rs tests.test_codex_api_provider_rs tests.test_codex_api_requests_headers_rs tests.test_codex_api_requests_responses_rs tests.test_codex_api_telemetry_rs tests.test_codex_api_files_rs tests.test_codex_api_images_rs tests.test_codex_api_search_rs tests.test_codex_api_endpoint_models_rs tests.test_codex_api_endpoint_images_rs tests.test_codex_api_endpoint_search_rs tests.test_codex_api_endpoint_compact_rs tests.test_codex_api_endpoint_memories_rs tests.test_codex_api_endpoint_realtime_call_rs -v`
  passed on 2026-06-20 with `78 tests`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `25 passed, 5 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/responses_websocket.py tests/test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `196 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `55 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `194 passed, 45 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `22 passed, 5 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `53 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `189 passed, 42 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/responses_websocket.py tests/test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_api_auth_rs tests.test_codex_api_error_rs tests.test_codex_api_rate_limits_rs tests.test_codex_api_common_rs tests.test_codex_api_provider_rs tests.test_codex_api_requests_headers_rs tests.test_codex_api_requests_responses_rs tests.test_codex_api_telemetry_rs tests.test_codex_api_files_rs tests.test_codex_api_images_rs tests.test_codex_api_search_rs tests.test_codex_api_endpoint_models_rs tests.test_codex_api_endpoint_images_rs tests.test_codex_api_endpoint_search_rs tests.test_codex_api_endpoint_compact_rs tests.test_codex_api_endpoint_memories_rs tests.test_codex_api_endpoint_realtime_call_rs -v`
  passed on 2026-06-20 with `78 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/codex_api/__init__.py pycodex/codex_api/auth.py pycodex/codex_api/common.py pycodex/codex_api/error.py pycodex/codex_api/files.py pycodex/codex_api/images.py pycodex/codex_api/provider.py pycodex/codex_api/rate_limits.py pycodex/codex_api/search.py pycodex/codex_api/telemetry.py pycodex/codex_api/endpoint/__init__.py pycodex/codex_api/endpoint/compact.py pycodex/codex_api/endpoint/images.py pycodex/codex_api/endpoint/memories.py pycodex/codex_api/endpoint/models.py pycodex/codex_api/endpoint/realtime_call.py pycodex/codex_api/endpoint/search.py pycodex/codex_api/requests/__init__.py pycodex/codex_api/requests/headers.py pycodex/codex_api/requests/responses.py tests/test_codex_api_auth_rs.py tests/test_codex_api_common_rs.py tests/test_codex_api_endpoint_compact_rs.py tests/test_codex_api_endpoint_images_rs.py tests/test_codex_api_endpoint_memories_rs.py tests/test_codex_api_endpoint_models_rs.py tests/test_codex_api_endpoint_realtime_call_rs.py tests/test_codex_api_endpoint_search_rs.py tests/test_codex_api_error_rs.py tests/test_codex_api_files_rs.py tests/test_codex_api_images_rs.py tests/test_codex_api_provider_rs.py tests/test_codex_api_rate_limits_rs.py tests/test_codex_api_requests_headers_rs.py tests/test_codex_api_requests_responses_rs.py tests/test_codex_api_search_rs.py tests/test_codex_api_telemetry_rs.py`
  passed on 2026-06-20.
- `python -m pytest tests/test_codex_api_endpoint_session_rs.py -q --tb=short`
  passed on 2026-06-20 with `5 passed`.
- `python -m py_compile pycodex/codex_api/endpoint/session.py tests/test_codex_api_endpoint_session_rs.py`
  passed on 2026-06-20.
- `python -m pytest tests/test_codex_api_endpoint_responses_rs.py -q --tb=short`
  passed on 2026-06-20 with `4 passed`.
- `python -m py_compile pycodex/codex_api/endpoint/responses.py tests/test_codex_api_endpoint_responses_rs.py pycodex/codex_api/endpoint/__init__.py pycodex/codex_api/__init__.py`
  passed on 2026-06-20.
- `python -m pytest tests/test_codex_api_sse_responses_rs.py -q --tb=short`
  passed on 2026-06-20 with `20 passed, 5 subtests passed`.
- `python -m py_compile pycodex/codex_api/sse/__init__.py pycodex/codex_api/sse/responses.py pycodex/codex_api/endpoint/responses.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py`
  passed on 2026-06-20.
- `python -m pytest tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_endpoint_session_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-20 with `36 passed, 5 subtests passed`.
- `python -m pytest tests/test_codex_api_sse_responses_rs.py -q --tb=short`
  passed on 2026-06-21 with `22 passed, 7 subtests passed`.
- `python -m py_compile pycodex/codex_api/sse/responses.py tests/test_codex_api_sse_responses_rs.py`
  passed on 2026-06-21.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `240 passed, 71 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py -q --tb=short`
  passed on 2026-06-21 with `15 passed, 5 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/realtime_websocket/protocol.py pycodex/codex_api/endpoint/realtime_websocket/protocol_common.py pycodex/codex_api/endpoint/realtime_websocket/protocol_v1.py pycodex/codex_api/endpoint/realtime_websocket/protocol_v2.py tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py tests/test_codex_api_endpoint_realtime_websocket_methods_rs.py tests/test_codex_api_endpoint_realtime_websocket_url_rs.py tests/test_codex_api_endpoint_realtime_websocket_active_transcript_rs.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `54 passed, 8 subtests passed`.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `242 passed, 76 subtests passed`.
- `python -m pytest tests/test_codex_api_api_bridge_rs.py -q --tb=short`
  passed on 2026-06-21 with `21 passed, 8 subtests passed`.
- `python -m py_compile pycodex/codex_api/api_bridge.py pycodex/codex_api/__init__.py tests/test_codex_api_api_bridge_rs.py`
  passed on 2026-06-21.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `231 passed, 49 subtests passed`.
- `python -m pytest tests/test_codex_api_images_rs.py -q --tb=short` passed
  on 2026-06-21 with `8 passed`.
- `python -m py_compile pycodex/codex_api/images.py tests/test_codex_api_images_rs.py`
  passed on 2026-06-21.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `234 passed, 49 subtests passed`.
- `python -m pytest tests/test_codex_api_search_rs.py -q --tb=short` passed
  on 2026-06-21 with `7 passed, 16 subtests passed`.
- `python -m py_compile pycodex/codex_api/search.py tests/test_codex_api_search_rs.py`
  passed on 2026-06-21.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `236 passed, 65 subtests passed`.
- `python -m pytest tests/test_codex_api_files_rs.py -q --tb=short` passed on
  2026-06-21 with `6 passed, 4 subtests passed`.
- `python -m py_compile pycodex/codex_api/files.py tests/test_codex_api_files_rs.py`
  passed on 2026-06-21.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `238 passed, 69 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-20 with `21 passed, 5 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/responses_websocket.py pycodex/codex_api/endpoint/__init__.py tests/test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-20.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-20 with `52 passed, 10 subtests passed`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_methods_rs tests.test_codex_api_endpoint_realtime_call_rs -v`
  passed on 2026-06-20 with `13 tests`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-20 with `15 tests`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-20 with `28 tests`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-20 with `33 tests`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_runtime_rs tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-20 with `35 tests`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `20 passed, 3 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_methods_rs.py tests/test_codex_api_endpoint_realtime_websocket_url_rs.py tests/test_codex_api_endpoint_realtime_websocket_active_transcript_rs.py tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `56 passed, 8 subtests passed`.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `247 passed, 79 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/realtime_websocket/methods.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-20 with `13 passed`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_runtime_rs tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-20 with `46 tests`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-20 with
  `188 passed, 42 subtests passed`.
- `python -m py_compile` over PowerShell-expanded `pycodex/codex_api/**/*.py`
  package modules and `tests/test_codex_api_*_rs.py` passed on 2026-06-20.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `36 passed, 8 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `70 passed, 15 subtests passed`.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `250 passed, 79 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m py_compile tests\test_codex_api_endpoint_responses_websocket_live_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_live_rs.py -q --tb=short -rs`
  skipped on 2026-06-21 because `PYCODEX_LIVE_RESPONSES_WS_URL` was not set.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `250 passed, 1 skipped, 79 subtests passed`; the skip is
  the optional live-only responses websocket smoke check without a configured
  real endpoint.

Completion note:

- `codex-api` completion is based on Rust-derived module contracts and focused
  local validation. The live-only responses websocket smoke check remains
  available as optional real-endpoint coverage, but it is not part of the
  completion requirement and must not be used by itself to reopen this crate as
  partial.
