# pycodex.exec_server Test Alignment

Rust crate: `codex-exec-server`

Rust anchor: `codex/codex-rs/exec-server`

## Module-derived tests

| Python test | Rust source | Behavior contract |
| --- | --- | --- |
| `tests/test_exec_server_protocol_rs.py::test_bytechunk_is_transparent_base64_wire_value` | `src/protocol.rs::ByteChunk`, `base64_bytes` | Protocol byte chunks are transparent base64 strings on the wire and decode back to bytes. |
| `tests/test_exec_server_protocol_rs.py::test_exec_params_decode_camel_case_defaults_and_env_policy` | `src/protocol.rs::{ExecParams,ExecEnvPolicy}` | Exec params decode camelCase protocol fields, transparent process ids, env policy fields, and Rust defaults for omitted `envPolicy`, `pipeStdin`, and `arg0`. |
| `tests/test_exec_server_protocol_rs.py::test_process_request_response_wire_shapes_use_base64_and_camel_case` | `src/protocol.rs::{ReadParams,WriteParams,TerminateParams,ReadResponse,WriteResponse}` | Process params/responses use camelCase names, base64 chunks, transparent process ids, optional integer fields, and `WriteStatus` camelCase variants. |
| `tests/test_exec_server_protocol_rs.py::test_http_request_timeout_treats_omitted_and_null_as_no_timeout` | `src/protocol.rs` Rust test `http_request_timeout_treats_omitted_and_null_as_no_timeout` | Omitted and null `timeoutMs` decode to no timeout, while numeric timeout values are preserved. |
| `tests/test_exec_server_protocol_rs.py::test_http_request_and_response_wire_shapes` | `src/protocol.rs::{HttpRequestParams,HttpRequestResponse,HttpHeader}` | HTTP request/response envelopes preserve ordered headers, `bodyBase64`, request id, `streamResponse` defaulting, and response body base64 encoding. |
| `tests/test_exec_server_protocol_rs.py::test_notification_wire_shapes_use_rust_field_names` | `src/protocol.rs::{HttpRequestBodyDeltaNotification,ExecOutputDeltaNotification,ExecExitedNotification,ExecClosedNotification}` | Streamed HTTP and process notifications use Rust camelCase field names and base64 byte fields. |
| `tests/test_exec_server_client_rs.py::test_process_events_are_delivered_in_seq_order_when_notifications_are_reordered` | `src/client.rs`, Rust test `process_events_are_delivered_in_seq_order_when_notifications_are_reordered` | Connection-global process notifications are routed by process id and published to session subscribers only after all earlier sequence numbers are delivered. |
| `tests/test_exec_server_client_rs.py::test_transport_disconnect_fails_sessions_and_rejects_new_sessions` | `src/client.rs`, Rust test `transport_disconnect_fails_sessions_and_rejects_new_sessions` | Transport disconnect publishes a failed event, synthesizes a closed failed read response, clears active sessions, and rejects new session registration. |
| `tests/test_exec_server_client_rs.py::test_wake_notifications_do_not_block_other_sessions` | `src/client.rs`, Rust test `wake_notifications_do_not_block_other_sessions` | A noisy process notification stream does not prevent another session from receiving its own wake update. |
| `tests/test_exec_server_client_rs.py::test_register_session_rejects_duplicate_process_id` | `src/client.rs::Inner::insert_session` | Duplicate client-side process session registration is rejected with a Rust-shaped protocol error. |
| `tests/test_exec_server_client_rs.py::test_client_read_write_terminate_forward_jsonrpc_calls` | `src/client.rs::ExecServerClient::{read,write,terminate}` | Public process-control helpers forward through the shared JSON-RPC call boundary using Rust method names, camelCase/base64 params, and typed response decoding. |
| `tests/test_exec_server_client_rs.py::test_client_call_maps_server_error_and_disconnect_like_rust` | `src/client.rs::ExecServerClient::call`, `From<RpcCallError> for ExecServerError` | JSON-RPC server errors map to the Rust `ExecServerError::Server` display shape and transport disconnects fail pending calls with the canonical disconnected message. |
| `tests/test_exec_server_client_rs.py::test_lazy_remote_exec_server_client_caches_and_reconnects_like_rust` | `src/client.rs::LazyRemoteExecServerClient::get` | Lazy remote clients reuse connected cached clients, serialize concurrent first connection attempts, reconnect disconnected WebSocket clients, and return disconnected non-WebSocket clients without reconnecting. |
| `tests/test_exec_server_client_rs.py::test_lazy_remote_exec_server_client_http_methods_forward_after_get` | `src/client.rs::impl HttpClient for LazyRemoteExecServerClient` | Buffered and streamed HTTP helper calls lazily obtain the remote exec-server client and delegate to the connected client. |
| `tests/test_exec_server_http_response_body_stream_rs.py::test_remote_http_response_body_stream_yields_chunk_then_eof` | `src/client/http_response_body_stream.rs::HttpResponseBodyStream::recv` | A terminal body delta with bytes returns the bytes first and EOF on the following recv while releasing the request route. |
| `tests/test_exec_server_http_response_body_stream_rs.py::test_remote_http_response_body_stream_empty_done_is_immediate_eof` | `src/client/http_response_body_stream.rs::HttpResponseBodyStream::recv` | An empty terminal body delta returns EOF immediately. |
| `tests/test_exec_server_http_response_body_stream_rs.py::test_remote_http_response_body_stream_rejects_sequence_gap` | `src/client/http_response_body_stream.rs::HttpResponseBodyStream::recv` | Remote body streams reject non-contiguous sequence numbers with a protocol error naming the request id and expected seq. |
| `tests/test_exec_server_http_response_body_stream_rs.py::test_remote_http_response_body_stream_error_delta_fails` | `src/client/http_response_body_stream.rs::HttpResponseBodyStream::recv` | Stream-side body delta errors become protocol errors with the request id and original error message. |
| `tests/test_exec_server_http_response_body_stream_rs.py::test_unknown_http_body_delta_request_id_is_ignored` | `src/client/http_response_body_stream.rs::Inner::handle_http_body_delta_notification` | Body deltas for unknown request ids are ignored because streams may have already released their route. |
| `tests/test_exec_server_http_response_body_stream_rs.py::test_stream_drop_schedules_route_removal` | `src/client/http_response_body_stream.rs::Drop for HttpResponseBodyStream` | Dropping a remote stream before EOF schedules route removal from the synchronous drop path. |
| `tests/test_exec_server_http_response_body_stream_rs.py::test_fail_all_http_body_streams_delivers_terminal_error` | `src/client/http_response_body_stream.rs::Inner::fail_all_http_body_streams` | Active streamed HTTP bodies receive terminal errors when the transport fails so readers do not wait forever. |
| `tests/test_exec_server_http_response_body_stream_rs.py::test_reader_loop_routes_http_body_delta_notifications` | `src/client/http_response_body_stream.rs::Inner::handle_http_body_delta_notification`, `src/client.rs` notification loop | Shared-connection `http/request/bodyDelta` notifications route into the matching request-local stream. |
| `tests/test_exec_server_reqwest_http_client_rs.py::test_runner_buffers_response_body_and_sends_request_shape` | `src/client/reqwest_http_client.rs::ReqwestHttpRequestRunner::run`, Rust integration test `exec_server_http_request_buffers_response_body` | A buffered local HTTP request sends the requested method/url/header/body and returns status, response headers, and the complete body. |
| `tests/test_exec_server_reqwest_http_client_rs.py::test_runner_treats_http_error_status_as_response` | `src/client/reqwest_http_client.rs::ReqwestHttpRequestRunner::run` | HTTP error statuses are caller-visible responses rather than transport failures. |
| `tests/test_exec_server_reqwest_http_client_rs.py::test_client_stream_returns_empty_header_body_and_local_stream` | `src/client/reqwest_http_client.rs::ReqwestHttpClient::http_request_stream`, Rust integration test `exec_server_http_request_streams_response_body_notifications` | Streamed local requests return status/headers with an empty buffered body and expose bytes through `HttpResponseBodyStream`. |
| `tests/test_exec_server_reqwest_http_client_rs.py::test_stream_body_sends_ordered_deltas_and_terminal_frame` | `src/client/reqwest_http_client.rs::ReqwestHttpRequestRunner::stream_body` | Pending local body chunks are forwarded as ordered `http/request/bodyDelta` notifications followed by an empty terminal frame. |
| `tests/test_exec_server_reqwest_http_client_rs.py::test_runner_maps_invalid_method_url_and_headers_to_invalid_params` | `src/client/reqwest_http_client.rs::ReqwestHttpRequestRunner::run/build_headers` | Invalid methods, unsupported URL schemes, and invalid headers become JSON-RPC `invalid_params` errors with Rust-shaped messages. |
| `tests/test_exec_server_rpc_http_client_rs.py::test_http_request_forces_buffered_response` | `src/client/rpc_http_client.rs::ExecServerClient::http_request` | Buffered HTTP requests force `streamResponse=false` and forward through the `http/request` JSON-RPC method. |
| `tests/test_exec_server_rpc_http_client_rs.py::test_http_request_stream_allocates_request_id_and_registers_stream` | `src/client/rpc_http_client.rs::ExecServerClient::http_request_stream` | Streamed HTTP requests allocate a connection-local request id, replace caller ids, register a body route before the header request, and return a remote body stream. |
| `tests/test_exec_server_rpc_http_client_rs.py::test_http_request_stream_cleans_registration_on_call_error` | `src/client/rpc_http_client.rs::ExecServerClient::http_request_stream` | If the header `http/request` call fails after registration, the body route is removed before returning the error. |
| `tests/test_exec_server_rpc_http_client_rs.py::test_http_request_stream_request_ids_are_connection_local` | `src/client/rpc_http_client.rs::ExecServerClient::http_request_stream` | Streamed HTTP request ids are allocated with the `http-N` prefix per connection. |
| `tests/test_exec_server_rpc_http_client_rs.py::test_http_body_delta_channel_capacity_matches_rust_constant` | `src/client/rpc_http_client.rs::HTTP_BODY_DELTA_CHANNEL_CAPACITY` | HTTP body delta channels use the Rust capacity of 256 queued frames. |
| `tests/test_exec_server_client_api_rs.py::test_remote_timeout_constants_match_rust_durations` | `src/client_api.rs` | Remote exec-server connect and initialize timeout constants mirror `Duration::from_secs(10)`. |
| `tests/test_exec_server_client_api_rs.py::test_client_connect_options_default_matches_client_impl` | `src/client.rs` default impl for `ExecServerClientConnectOptions` | Default client name is `codex-core`, initialize timeout is 10 seconds, and resume session id is absent. |
| `tests/test_exec_server_client_api_rs.py::test_remote_connect_args_new_and_into_options` | `src/client_api.rs`, `src/client.rs` | `RemoteExecServerConnectArgs::new` fills default timeouts and conversion to client options preserves shared fields. |
| `tests/test_exec_server_client_api_rs.py::test_stdio_connect_args_into_options_and_command_normalization` | `src/client_api.rs`, `src/client.rs`, `src/client_transport.rs` | Stdio command args/env/cwd are structured and conversion to client options preserves shared fields. |
| `tests/test_exec_server_client_api_rs.py::test_transport_params_websocket_constructor_matches_rust_helper` | `src/client_api.rs` | `ExecServerTransportParams::websocket_url` fills WebSocketUrl variant defaults. |
| `tests/test_exec_server_client_api_rs.py::test_transport_params_reject_wrong_variant_fields` | `src/client_api.rs` | WebSocketUrl and StdioCommand variants remain disjoint. |
| `tests/test_exec_server_client_api_rs.py::test_http_client_trait_boundary_is_explicitly_unported` | `src/client_api.rs` | `HttpClient` exposes buffered and streamed request methods without implementing concrete transport. |
| `tests/test_exec_server_client_transport_rs.py::test_connect_for_transport_projects_websocket_params_to_environment_client` | `src/client_transport.rs::ExecServerClient::connect_for_transport` | WebSocket transport params are projected to remote connect args with the `codex-environment` client name and no resume session. |
| `tests/test_exec_server_client_transport_rs.py::test_is_rendezvous_harness_url_matches_rust_query_scan` | `src/client_transport.rs::is_rendezvous_harness_url` | Only a literal query pair `role=harness` selects the rendezvous harness relay transport; parsing is split-based and not URL-decoded. |
| `tests/test_exec_server_client_transport_rs.py::test_connect_websocket_selects_harness_or_plain_connection_from_url_role` | `src/client_transport.rs::ExecServerClient::connect_websocket` | Injected websocket streams with `role=harness` are wrapped with the relay harness connection, while ordinary websocket URLs use the plain JSON-RPC websocket connection. |
| `tests/test_exec_server_client_transport_rs.py::test_connect_websocket_maps_connect_timeout_like_rust` | `src/client_transport.rs::ExecServerClient::connect_websocket`, `src/client.rs::ExecServerError::WebSocketConnectTimeout` | Websocket connect is bounded by `connect_timeout`, cancels the dial future, and displays the Rust timeout error shape with URL and duration. |
| `tests/test_exec_server_client_transport_rs.py::test_connect_websocket_maps_connector_error_like_rust` | `src/client_transport.rs::ExecServerClient::connect_websocket`, `src/client.rs::ExecServerError::WebSocketConnect` | Websocket dial errors preserve the URL and source display in the Rust `failed to connect to exec-server websocket` message shape. |
| `tests/test_exec_server_client_transport_rs.py::test_connect_websocket_without_injected_connector_uses_stdlib_handshake` | `src/client_transport.rs::ExecServerClient::connect_websocket` | Without an injected connector, the dependency-light websocket runtime performs the HTTP upgrade, validates the 101 `Upgrade`/`Connection`/`Sec-WebSocket-Accept` headers, sends masked client frames, reads server frames, and routes initialize/initialized through the ordinary websocket connection path. |
| `tests/test_exec_server_client_transport_rs.py::test_stdlib_websocket_upgrade_response_requires_tungstenite_protocol_headers` | `src/client_transport.rs::ExecServerClient::connect_websocket`, `tokio_tungstenite::connect_async` | The Python stdlib handshake mirrors tungstenite's successful 101 boundary by rejecting responses without WebSocket `Upgrade` and `Connection` protocol tokens before returning a websocket stream. |
| `tests/test_exec_server_client_transport_rs.py::test_connect_for_transport_projects_stdio_command_to_environment_client` | `src/client_transport.rs::ExecServerClient::connect_for_transport` | Stdio command transport params are projected to stdio connect args with the `codex-environment` client name and no resume session. |
| `tests/test_exec_server_client_transport_rs.py::test_connect_stdio_command_uses_options_conversion` | `src/client_transport.rs::ExecServerClient::connect_stdio_command`, `src/client.rs` | Stdio connect args convert into client options before initialize handoff while preserving command metadata at the connector boundary. |
| `tests/test_exec_server_client_transport_rs.py::test_connect_stdio_command_spawns_real_json_rpc_client` | `src/client_transport.rs::ExecServerClient::connect_stdio_command`, Rust tests `connect_stdio_command_initializes_json_rpc_client_on_windows` and non-Windows companion | Without an injected connector, stdio connect spawns the configured command with piped stdio, env, cwd, stderr draining, child supervision, and initialize/initialized handshake. |
| `tests/test_exec_server_client_transport_rs.py::test_connect_stdio_command_spawn_error_matches_rust_prefix` | `src/client.rs::ExecServerError::Spawn`, `src/client_transport.rs::connect_stdio_command` | Missing stdio command programs map to the Rust `failed to spawn exec-server:` error prefix. |
| `tests/test_exec_server_client_transport_rs.py::test_initialize_connection_sends_initialize_then_initialized` | `src/client.rs::ExecServerClient::connect`, `src/client_transport.rs` | Connection initialization sends an `initialize` request, records the returned sessionId, then sends the `initialized` notification. |
| `tests/test_exec_server_client_transport_rs.py::test_stdio_command_process_spec_matches_rust_command_builder` | `src/client_transport.rs::stdio_command_process` | Stdio command process planning preserves program, args, env, cwd, piped stdio, and Unix process-group intent. |
| `tests/test_exec_server_environment_rs.py::test_create_local_environment_does_not_connect` | `src/environment.rs`, Rust test `create_local_environment_does_not_connect` | Local environment construction records no exec-server URL and does not create a remote transport. |
| `tests/test_exec_server_environment_rs.py::test_environment_manager_normalizes_empty_url` | `src/environment.rs`, Rust test `environment_manager_normalizes_empty_url` | Empty legacy exec-server URL selects the local default and caches the same local environment for default/local lookup. |
| `tests/test_exec_server_environment_rs.py::test_disabled_environment_manager_has_no_default_or_local_environment` | `src/environment.rs`, Rust test `disabled_environment_manager_has_no_default_or_local_environment` | Explicit no-environment manager exposes no default, local, or remote environment. |
| `tests/test_exec_server_environment_rs.py::test_environment_manager_reports_remote_url` | `src/environment.rs`, Rust test `environment_manager_reports_remote_url` | Websocket legacy URL creates the remote default environment, reports its URL, and omits local lookup. |
| `tests/test_exec_server_environment_rs.py::test_environment_manager_builds_from_snapshot_and_orders_default_first` | `src/environment.rs`, Rust tests `environment_manager_builds_from_snapshot` and `environment_manager_uses_explicit_provider_default` | Provider snapshots create named environments, include local when requested, and order default environment ids with default first. |
| `tests/test_exec_server_environment_rs.py::test_environment_manager_disables_provider_default` | `src/environment.rs`, Rust test `environment_manager_disables_provider_default` | Disabled provider defaults leave default lookup unset while preserving included local environments. |
| `tests/test_exec_server_environment_rs.py::test_environment_manager_rejects_invalid_snapshot_defaults_and_ids` | `src/environment.rs` snapshot rejection tests | Empty ids, reserved `local`, duplicate ids, and unknown defaults raise Rust-shaped protocol errors. |
| `tests/test_exec_server_environment_rs.py::test_environment_manager_omits_default_provider_local_lookup_when_default_disabled` | `src/environment.rs`, Rust test `environment_manager_omits_default_provider_local_lookup_when_default_disabled` | Legacy URL `none` disables both default and local lookup. |
| `tests/test_exec_server_environment_rs.py::test_environment_manager_carries_local_runtime_paths` | `src/environment.rs`, Rust test `environment_manager_carries_local_runtime_paths` | Local environments retain runtime paths and construct sandbox-capable local filesystem helpers. |
| `tests/test_exec_server_environment_rs.py::test_environment_manager_upserts_named_remote_environment` | `src/environment.rs`, Rust test `environment_manager_upserts_named_remote_environment` | Named remote upsert adds/replaces environments without changing default selection. |
| `tests/test_exec_server_environment_rs.py::test_environment_manager_rejects_invalid_upsert_environment` | `src/environment.rs::EnvironmentManager::upsert_environment` | Empty ids, empty URLs, and disabled remote URLs are rejected with Rust-shaped protocol errors. |
| `tests/test_exec_server_environment_provider_rs.py::test_default_provider_requests_local_environment_when_url_is_missing` | `src/environment_provider.rs` | Missing `CODEX_EXEC_SERVER_URL` requests local environment as default. |
| `tests/test_exec_server_environment_provider_rs.py::test_default_provider_requests_local_environment_when_url_is_empty` | `src/environment_provider.rs` | Empty URL requests local environment as default. |
| `tests/test_exec_server_environment_provider_rs.py::test_default_provider_omits_local_environment_for_none_value` | `src/environment_provider.rs` | `none` disables the default and omits local/remote environments. |
| `tests/test_exec_server_environment_provider_rs.py::test_default_provider_adds_remote_environment_for_websocket_url` | `src/environment_provider.rs` | Configured remote websocket URL creates the remote environment and selects it as default. |
| `tests/test_exec_server_environment_provider_rs.py::test_default_provider_normalizes_exec_server_url` | `src/environment_provider.rs` | Remote URL values are trimmed before snapshot construction. |
| `tests/test_exec_server_environment_provider_rs.py::test_normalize_exec_server_url_matches_rust_helper` | `src/environment_provider.rs` | URL normalization returns `(url, disabled)` exactly like the Rust helper. |
| `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_includes_local_and_adds_configured_environments` | `src/environment_toml.rs` | TOML provider includes local by default, adds configured environments in order, trims URLs/programs, and selects configured default. |
| `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_default_selection_cases` | `src/environment_toml.rs` | Default omitted/none/include_local combinations match Rust snapshot behavior. |
| `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_rejects_invalid_environments` | `src/environment_toml.rs` | Reserved ids, whitespace, invalid id chars, invalid URL scheme, url+program conflict, empty program, orphan args/env/cwd, and stdio connect timeout errors match Rust text. |
| `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_resolves_relative_stdio_cwd_from_config_dir` | `src/environment_toml.rs` | Relative stdio cwd resolves against the config directory. |
| `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_parses_configured_transport_timeouts` | `src/environment_toml.rs` | Configured connect/initialize timeouts project into transport params. |
| `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_rejects_relative_stdio_cwd_without_config_dir` | `src/environment_toml.rs` | Relative stdio cwd without a config dir is rejected. |
| `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_rejects_duplicate_overlong_and_unknown_default` | `src/environment_toml.rs` | Duplicate ids, overlong ids, and unknown defaults are rejected. |
| `tests/test_exec_server_environment_toml_rs.py::test_load_environments_toml_reads_root_environment_list` | `src/environment_toml.rs` | Root `environments.toml` list deserializes into Rust-shaped config objects. |
| `tests/test_exec_server_environment_toml_rs.py::test_load_environments_toml_rejects_unknown_fields` | `src/environment_toml.rs` | Unknown root and environment fields are rejected. |
| `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_rejects_malformed_websocket_url` | `src/environment_toml.rs` | Malformed websocket URLs are rejected with the Rust error prefix. |
| `tests/test_exec_server_environment_toml_rs.py::test_environment_provider_from_codex_home_uses_file_or_default` | `src/environment_toml.rs` | `environment_provider_from_codex_home` uses present config files and falls back to the default env provider when absent. |
| `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_default_timeout_values` | `src/environment_toml.rs` | Omitted transport timeouts use `client_api` defaults. |
| `tests/test_exec_server_remote_rs.py::test_register_environment_posts_with_auth_provider_headers` | `src/remote.rs::EnvironmentRegistryClient::register_environment`, Rust test `register_environment_posts_with_auth_provider_headers` | Remote environment registration POSTs to the normalized registry endpoint with auth-provider headers and decodes the typed rendezvous response. |
| `tests/test_exec_server_remote_rs.py::test_register_environment_does_not_follow_redirects_with_auth_headers` | `src/remote.rs::EnvironmentRegistryClient`, Rust test `register_environment_does_not_follow_redirects_with_auth_headers` | Registry HTTP client disables redirect following so auth headers are not forwarded to redirect targets. |
| `tests/test_exec_server_remote_rs.py::test_debug_output_redacts_auth_provider` | `src/remote.rs::{RemoteEnvironmentConfig,EnvironmentRegistryClient}` | Debug output redacts auth-provider details while preserving visible registry/config fields. |
| `tests/test_exec_server_remote_rs.py::test_remote_environment_config_normalizes_environment_id_and_defaults_name` | `src/remote.rs::RemoteEnvironmentConfig::new` | Remote environment config trims environment ids, rejects empty ids, and fills the default exec-server name. |
| `tests/test_exec_server_remote_rs.py::test_base_url_endpoint_and_error_helpers_match_rust_shapes` | `src/remote.rs::{normalize_base_url,endpoint_url,registry_error_message,environment_registry_auth_error,environment_registry_http_error}` | Registry base URLs and endpoint paths normalize like Rust; registry error helpers prefer nested error messages and fall back to trimmed body previews. |
| `tests/test_exec_server_remote_rs.py::test_run_remote_environment_registers_connects_serves_and_resets_backoff` | `src/remote.rs::run_remote_environment` | The remote environment loop registers the configured environment id, prints the registered id, connects to the returned rendezvous URL, serves successful websocket connections with a connection processor, and resets sleep backoff to one second after connect success. |
| `tests/test_exec_server_remote_rs.py::test_run_remote_environment_connect_failure_uses_exponential_backoff` | `src/remote.rs::run_remote_environment` | Websocket connect failures are swallowed for the next registration attempt while sleep backoff doubles and caps at 30 seconds. |
| `tests/test_exec_server_remote_rs.py::test_run_remote_environment_propagates_registration_errors` | `src/remote.rs::run_remote_environment` | Registration errors propagate immediately before websocket connect or backoff sleep. |
| `tests/test_exec_server_remote_rs.py::test_run_remote_environment_default_connector_uses_stdlib_websocket` | `src/remote.rs::run_remote_environment` source contract for `connect_async(response.url.as_str())` | Without an injected connector, the remote loop uses the registry rendezvous URL, performs the dependency-light websocket HTTP upgrade through the shared stdlib connector, and passes the resulting websocket stream to the multiplexed environment serve boundary. |
| `tests/test_exec_server_connection_rs.py::test_stdio_connection_reads_messages_skips_blanks_and_reports_eof` | `src/connection.rs::JsonRpcConnection::from_stdio` | Stdio reader consumes newline-framed lite JSON-RPC messages, skips blank lines, and reports disconnected on EOF. |
| `tests/test_exec_server_connection_rs.py::test_stdio_connection_reports_malformed_jsonrpc_message` | `src/connection.rs::JsonRpcConnection::from_stdio`, `send_malformed_message` | Malformed stdio JSON-RPC frames emit `JsonRpcConnectionEvent::MalformedMessage` with the connection-label parse prefix. |
| `tests/test_exec_server_connection_rs.py::test_stdio_connection_writes_compact_jsonrpc_lines` | `src/connection.rs::write_jsonrpc_line_message`, `serialize_jsonrpc_message` | Outbound stdio messages serialize as compact JSON and append a newline. |
| `tests/test_exec_server_connection_rs.py::test_stdio_connection_reports_write_errors_as_disconnected` | `src/connection.rs::JsonRpcConnection::from_stdio`, `send_disconnected` | Stdio writer failures emit `JsonRpcConnectionEvent::Disconnected` with the Rust write-error prefix. |
| `tests/test_exec_server_connection_rs.py::test_websocket_connection_sends_configured_ping` | `src/connection.rs::JsonRpcConnection::from_websocket_stream`, Rust test `websocket_connection_sends_configured_ping` | Websocket connections with configured keepalive intervals send ping frames. |
| `tests/test_exec_server_connection_rs.py::test_websocket_connection_ignores_server_pong` | `src/connection.rs::JsonRpcWebSocketMessage::parse_jsonrpc_frame`, Rust test `websocket_connection_ignores_server_pong` | Incoming websocket pong frames are ignored and produce no connection event. |
| `tests/test_exec_server_connection_rs.py::test_websocket_connection_reports_server_close` | `src/connection.rs::JsonRpcConnection::from_websocket`, Rust test `websocket_connection_reports_server_close` | Incoming websocket close frames report a disconnected event with no reason. |
| `tests/test_exec_server_connection_rs.py::test_websocket_connection_accepts_binary_jsonrpc_message` | `src/connection.rs::JsonRpcWebSocketMessage::parse_jsonrpc_frame`, Rust test `websocket_connection_accepts_binary_jsonrpc_message` | Binary websocket frames containing JSON-RPC payloads are decoded as connection message events. |
| `tests/test_exec_server_connection_rs.py::test_websocket_connection_keeps_outbound_message_while_send_is_backpressured` | `src/connection.rs::JsonRpcConnection::from_websocket_stream`, Rust test `websocket_connection_keeps_outbound_message_while_send_is_backpressured` | The single websocket transport loop preserves outbound send ordering while a write is backpressured and does not process ignored inbound frames until the write completes. |
| `tests/test_exec_server_connection_rs.py::test_stdio_transport_terminate_is_idempotent_and_requests_child_termination` | `src/connection.rs::StdioTransportHandle::terminate`, `spawn_stdio_child_supervisor` | Stdio child terminate requests are idempotent and notify the supervisor only once. |
| `tests/test_exec_server_connection_rs.py::test_stdio_transport_kills_child_after_termination_grace_timeout` | `src/connection.rs::terminate_stdio_child` | Terminating a stdio child first requests graceful termination and then kills after the grace period. |
| `tests/test_exec_server_connection_rs.py::test_stdio_child_supervisor_kills_process_tree_after_child_exit` | `src/connection.rs::spawn_stdio_child_supervisor` | If the child exits before a terminate request, the supervisor performs process-tree cleanup. |
| `tests/test_exec_server_connection_rs.py::test_jsonrpc_connection_with_child_process_installs_stdio_transport` | `src/connection.rs::JsonRpcConnection::with_child_process`, `JsonRpcTransport::from_child_process` | Attaching a child process wraps the connection transport in the stdio transport variant. |
| `tests/test_exec_server_fs_helper_rs.py::test_helper_requests_use_fs_method_names` | `src/fs_helper.rs`, Rust test `helper_requests_use_fs_method_names` | Helper requests serialize the protocol fs method name as the `operation` discriminator. |
| `tests/test_exec_server_fs_helper_rs.py::test_helper_payload_and_response_wire_shape_round_trip` | `src/fs_helper.rs` | Helper payload and response envelopes use Rust's serde `operation`/`response` and `status`/`payload` shape. |
| `tests/test_exec_server_fs_helper_rs.py::test_helper_payload_expect_methods_reject_wrong_operation` | `src/fs_helper.rs` | Payload `expect_*` helpers return typed responses for matching operations and Rust-shaped internal errors for mismatches. |
| `tests/test_exec_server_fs_helper_rs.py::test_run_direct_request_reads_and_writes_base64` | `src/fs_helper.rs::run_direct_request` | Direct readFile/writeFile requests round-trip file bytes through base64 dataBase64. |
| `tests/test_exec_server_fs_helper_rs.py::test_run_direct_request_uses_rust_default_options` | `src/fs_helper.rs::run_direct_request` | createDirectory defaults recursive to true and readDirectory returns fileName/isDirectory/isFile entries. |
| `tests/test_exec_server_fs_helper_rs.py::test_run_direct_request_invalid_base64_maps_to_invalid_request` | `src/fs_helper.rs::run_direct_request` | Invalid writeFile base64 maps to invalid_request with the Rust method/field message prefix. |
| `tests/test_exec_server_fs_helper_rs.py::test_map_fs_error_matches_fs_helper_error_kinds` | `src/fs_helper.rs::map_fs_error`, `src/rpc.rs` | Fs-helper IO errors map NotFound to -32004, invalid input/permission to invalid_request, and other errors to internal_error. |
| `tests/test_exec_server_fs_helper_rs.py::test_run_fs_helper_once_wraps_payload_as_json_line` | `src/fs_helper_main.rs::run_main` | Helper entrypoint reads a complete request, dispatches direct filesystem work, wraps Ok payloads, and writes compact JSON plus newline. |
| `tests/test_exec_server_fs_helper_rs.py::test_run_fs_helper_once_wraps_direct_request_errors` | `src/fs_helper_main.rs::run_main` | Direct request JSON-RPC errors are serialized as FsHelperResponse::Error without failing the helper process. |
| `tests/test_exec_server_fs_helper_rs.py::test_run_fs_helper_main_reports_invalid_input_to_stderr` | `src/fs_helper_main.rs::main` | Malformed helper input reports the Rust stderr prefix and exits with code 1. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_helper_permissions_enable_minimal_reads_for_restricted_profiles` | `src/fs_sandbox.rs` | Restricted helper policies receive minimal read permissions without losing writes. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_helper_permissions_preserve_writes_and_add_helper_read_roots` | `src/fs_sandbox.rs` | Helper runtime read roots are added while existing writable roots remain writable. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_helper_env_preserves_allowlist_without_leaking_secrets` | `src/fs_sandbox.rs` | Helper env keeps PATH/TMPDIR/TMP/TEMP and excludes secrets/proxy values. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_sandbox_cwd_uses_context_cwd` | `src/fs_sandbox.rs` | Sandbox cwd prefers the context cwd when present. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_sandbox_cwd_rejects_dynamic_profile_without_context_cwd` | `src/fs_sandbox.rs` | Cwd-dependent dynamic filesystem permissions require an explicit cwd. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_helper_permissions_include_helper_read_root_without_additional_permissions` | `src/fs_sandbox.rs` | Codex helper parent is added as a readable root when needed. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_helper_permissions_include_linux_sandbox_alias_parent` | `src/fs_sandbox.rs` | Linux sandbox alias parent is included as a helper read root. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_sandbox_exec_request_carries_helper_env` | `src/fs_sandbox.rs` | Fs-helper command planning carries the filtered helper environment. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_runner_run_encodes_request_and_decodes_ok_response` | `src/fs_sandbox.rs::FileSystemSandboxRunner::run`, `run_command` | Runner prepares the helper command, writes JSON FsHelperRequest bytes, and decodes FsHelperResponse::Ok stdout. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_runner_run_returns_helper_error_response` | `src/fs_sandbox.rs::run_command` | FsHelperResponse::Error is returned as the helper JSON-RPC error rather than wrapped as a transport failure. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_runner_run_maps_nonzero_status_and_invalid_json` | `src/fs_sandbox.rs::run_command`, `json_error` | Non-zero helper status and invalid stdout JSON become internal JSON-RPC errors with Rust message prefixes. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_runner_run_rejects_empty_sandbox_command` | `src/fs_sandbox.rs::spawn_command` | Empty transformed sandbox commands return invalid_request with the Rust message. |
| `tests/test_exec_server_fs_sandbox_rs.py::test_run_command_spawns_helper_subprocess_and_decodes_stdout` | `src/fs_sandbox.rs::run_command`, `spawn_command` | Default runner execution spawns the helper subprocess with piped stdin/stdout/stderr and decodes FsHelperResponse::Ok stdout. |
| `tests/test_exec_server_sandboxed_file_system_rs.py::test_sandboxed_file_system_rejects_missing_or_non_platform_sandbox` | `src/sandboxed_file_system.rs::require_platform_sandbox` | Sandboxed filesystem operations require a context that should run in the platform sandbox. |
| `tests/test_exec_server_sandboxed_file_system_rs.py::test_sandboxed_file_system_read_file_decodes_helper_base64` | `src/sandboxed_file_system.rs::SandboxedFileSystem::read_file` | readFile sends a helper request without nested sandbox context and decodes returned dataBase64. |
| `tests/test_exec_server_sandboxed_file_system_rs.py::test_sandboxed_file_system_write_create_remove_and_copy_requests` | `src/sandboxed_file_system.rs` ExecutorFileSystem impl | Mutating operations encode Rust helper request params and map matching payloads to unit results. |
| `tests/test_exec_server_sandboxed_file_system_rs.py::test_sandboxed_file_system_metadata_and_directory_projection` | `src/sandboxed_file_system.rs::{get_metadata,read_directory}` | Helper metadata and directory entries project into filesystem-domain values. |
| `tests/test_exec_server_sandboxed_file_system_rs.py::test_sandboxed_file_system_maps_helper_errors_and_unexpected_payloads` | `src/sandboxed_file_system.rs::map_sandbox_error`, `FsHelperPayload::expect_*` | Helper JSON-RPC errors and unexpected payload variants become filesystem errors. |
| `tests/test_exec_server_sandboxed_file_system_rs.py::test_sandboxed_file_system_invalid_read_base64_is_invalid_data` | `src/sandboxed_file_system.rs::SandboxedFileSystem::read_file` | Invalid helper dataBase64 becomes an invalid-data filesystem error with the Rust method/field prefix. |
| `tests/test_exec_server_sandboxed_file_system_rs.py::test_map_sandbox_error_matches_rust_jsonrpc_codes` | `src/sandboxed_file_system.rs::map_sandbox_error` | not_found maps to NotFound, invalid_request maps to InvalidInput, and other helper errors map to generic IO error. |
| `tests/test_exec_server_sandboxed_file_system_rs.py::test_local_file_system_with_runtime_paths_configures_sandboxed_backend` | `src/local_file_system.rs::LocalFileSystem::new`, `src/sandboxed_file_system.rs::SandboxedFileSystem::new` | Configured runtime paths install a SandboxedFileSystem backend for platform sandbox contexts. |
| `tests/test_exec_server_local_file_system_rs.py::test_resolve_existing_path_handles_missing_suffix` | `src/local_file_system.rs::resolve_existing_path` | Path resolution canonicalizes the deepest existing parent and appends unresolved suffixes. |
| `tests/test_exec_server_local_file_system_rs.py::test_resolve_existing_path_handles_symlink_parent_dotdot_escape` | `src/local_file_system.rs`, Rust test `resolve_existing_path_handles_symlink_parent_dotdot_escape` | Symlink parents are canonicalized before appending unresolved suffixes. |
| `tests/test_exec_server_local_file_system_rs.py::test_direct_file_system_read_write_metadata_and_directory` | `src/local_file_system.rs::DirectFileSystem` | Direct filesystem read/write/metadata/readDirectory behavior matches local filesystem semantics. |
| `tests/test_exec_server_local_file_system_rs.py::test_direct_file_system_create_directory_recursive_matches_rust` | `src/local_file_system.rs::DirectFileSystem::create_directory` | Recursive directory creation uses create_dir_all semantics and non-recursive creation errors when parents are missing. |
| `tests/test_exec_server_local_file_system_rs.py::test_direct_file_system_remove_defaults_are_caller_owned` | `src/local_file_system.rs::DirectFileSystem::remove` | Remove honors caller-supplied recursive and force options. |
| `tests/test_exec_server_local_file_system_rs.py::test_direct_file_system_copy_rejects_directory_without_recursive` | `src/local_file_system.rs::DirectFileSystem::copy` | Directory copy requires recursive true. |
| `tests/test_exec_server_local_file_system_rs.py::test_direct_file_system_copy_rejects_descendant_destination` | `src/local_file_system.rs::destination_is_same_or_descendant_of_source` | Directory copy rejects copying into itself or one of its descendants. |
| `tests/test_exec_server_local_file_system_rs.py::test_unsandboxed_file_system_rejects_platform_sandbox_context` | `src/local_file_system.rs::reject_platform_sandbox_context` | Unsandboxed fallback rejects contexts that should run in a configured platform sandbox. |
| `tests/test_exec_server_local_file_system_rs.py::test_local_file_system_delegates_to_unsandboxed_without_sandbox` | `src/local_file_system.rs::LocalFileSystem::file_system_for` | Local filesystem delegates to unsandboxed filesystem when no sandbox context is provided. |
| `tests/test_exec_server_local_file_system_rs.py::test_current_sandbox_cwd_resolves_existing_cwd` | `src/local_file_system.rs::current_sandbox_cwd` | Current sandbox cwd is resolved through `resolve_existing_path`. |
| `tests/test_exec_server_local_process_rs.py::test_child_env_defaults_to_exact_env` | `src/local_process.rs`, Rust test `child_env_defaults_to_exact_env` | Without env_policy, child_env returns exactly params.env. |
| `tests/test_exec_server_local_process_rs.py::test_child_env_applies_policy_then_overlay` | `src/local_process.rs`, Rust test `child_env_applies_policy_then_overlay` | Shell environment policy is applied first, then request env overlays policy-set values. |
| `tests/test_exec_server_local_process_rs.py::test_shell_environment_policy_projection_matches_rust_fields` | `src/local_process.rs::shell_environment_policy` | ExecEnvPolicy projects to ShellEnvironmentPolicy fields with use_profile=false. |
| `tests/test_exec_server_local_process_rs.py::test_start_process_rejects_empty_argv_before_tracking_process` | `src/local_process.rs::LocalProcess::start_process` | Empty argv returns invalid_params and does not insert a process entry. |
| `tests/test_exec_server_local_process_rs.py::test_start_process_rejects_duplicate_process_ids` | `src/local_process.rs::LocalProcess::start_process`, Rust test `duplicate_process_ids_allow_only_one_successful_start` | Existing process ids return invalid_request with the Rust message shape. |
| `tests/test_exec_server_local_process_rs.py::test_start_process_spawn_failure_removes_starting_entry` | `src/local_process.rs::LocalProcess::start_process` | Spawn failure removes the temporary Starting entry and maps the error to internal_error. |
| `tests/test_exec_server_local_process_rs.py::test_start_process_success_inserts_running_process_with_env_overlay` | `src/local_process.rs::LocalProcess::start_process` | Successful spawn receives child_env output, installs a running process configured from tty/pipe_stdin, and returns ExecResponse. |
| `tests/test_exec_server_local_process_rs.py::test_start_process_spawns_real_pipe_process_and_collects_output` | `src/local_process.rs::LocalProcess::start_process`, `stream_output`, `watch_exit`, `maybe_emit_closed` | Non-TTY real subprocess execution captures stdout/stderr chunks, reports exit code, waits for changes, and closes after both output streams finish. |
| `tests/test_exec_server_local_process_rs.py::test_start_process_tty_process_uses_pty_stream_and_accepts_stdin` | `src/local_process.rs::LocalProcess::start_process`, `codex_utils_pty::spawn_pty_process`, `stream_output` | TTY subprocesses use the PTY spawn branch, accept stdin through the session writer, and classify process output as `ExecOutputStream::Pty`; Windows keeps the explicit unsupported boundary. |
| `tests/test_exec_server_local_process_rs.py::test_exec_write_writes_to_real_pipe_process_stdin` | `src/local_process.rs::LocalProcess::exec_write` | `pipe_stdin` real subprocesses receive stdin bytes through the session writer and return `WriteStatus::Accepted`. |
| `tests/test_exec_server_local_process_rs.py::test_local_process_start_returns_exec_process_facade_with_events` | `src/local_process.rs` impls for `ExecBackend` and `ExecProcess`, `src/process.rs` trait contract | `LocalProcess.start` returns a process facade whose read/write/terminate methods delegate to the backend and whose event/wake subscriptions report output, exit, and closed sequence changes. |
| `tests/test_exec_server_local_process_rs.py::test_exec_read_reports_unknown_and_starting_processes` | `src/local_process.rs::LocalProcess::exec_read` | Unknown process ids and starting entries return invalid_request errors with Rust message shape. |
| `tests/test_exec_server_local_process_rs.py::test_exec_read_filters_after_seq_and_respects_max_bytes` | `src/local_process.rs::LocalProcess::exec_read` | Retained chunks with seq greater than after_seq are returned in order and maxBytes never omits the first available chunk. |
| `tests/test_exec_server_local_process_rs.py::test_exec_read_reports_exit_terminal_event_without_chunks` | `src/local_process.rs::LocalProcess::exec_read` | Exit increments next_seq, sets exited/exit_code, and produces a terminal response even without output chunks. |
| `tests/test_exec_server_local_process_rs.py::test_exec_read_reports_closed_state_and_retains_late_output_shape` | `src/local_process.rs`, Rust test `exited_process_retains_late_output_past_retention` | Late retained output after exit remains readable with its sequence number and exit code, while closed is reported separately. |
| `tests/test_exec_server_local_process_rs.py::test_closed_process_is_evicted_after_retention` | `src/local_process.rs`, Rust test `closed_process_is_evicted_after_retention` | Closed process entries remain briefly readable, then are evicted after the retention delay without deleting replacement entries. |
| `tests/test_exec_server_local_process_rs.py::test_exec_write_reports_unknown_starting_and_closed_stdin_states` | `src/local_process.rs::LocalProcess::exec_write` | Unknown, starting, and non-stdin-capable running processes return Rust WriteStatus values. |
| `tests/test_exec_server_local_process_rs.py::test_exec_write_accepts_tty_or_pipe_stdin_and_records_chunk` | `src/local_process.rs::LocalProcess::exec_write` | TTY or piped-stdin running processes accept stdin bytes and return WriteStatus::Accepted. |
| `tests/test_exec_server_local_process_rs.py::test_exec_write_maps_writer_failure_to_internal_error` | `src/local_process.rs::LocalProcess::exec_write` | Writer send failure maps to internal_error with the Rust message. |
| `tests/test_exec_server_local_process_rs.py::test_terminate_process_reports_running_state_and_marks_termination` | `src/local_process.rs::LocalProcess::terminate_process` | Unknown, starting, and exited processes report running=false; running processes are terminated and report running=true. |
| `tests/test_exec_server_local_process_rs.py::test_local_pipe_child_process_terminates_process_group_on_posix` | `src/local_process.rs::terminate_process`, `codex_utils_pty::ProcessHandle::terminate`, `codex-utils-pty/src/pipe.rs::PipeChildTerminator`, `codex-utils-pty/src/process_group.rs::kill_process_group` | Local pipe-backed process termination targets the child process group on POSIX and falls back to the direct child process on non-POSIX. |
| `tests/test_exec_server_process_rs.py::test_process_event_seq_matches_rust_variants` | `src/process.rs::ExecProcessEvent::seq` | Output/Exited/Closed events expose sequence numbers and Failed is unsequenced. |
| `tests/test_exec_server_process_rs.py::test_process_event_retained_len_matches_rust_variants` | `src/process.rs::ExecProcessEvent::retained_len` | Output counts chunk bytes, Failed counts message bytes, and lifecycle events retain zero bytes. |
| `tests/test_exec_server_process_rs.py::test_event_history_replay_is_bounded_by_retained_bytes` | `src/process.rs`, Rust test `event_history_replay_is_bounded_by_retained_bytes` | Replay history evicts oversized output while retaining zero-byte lifecycle events. |
| `tests/test_exec_server_process_rs.py::test_event_history_replay_is_bounded_by_event_count` | `src/process.rs::ExecProcessEventLog::publish` | Replay history is also bounded by event count. |
| `tests/test_exec_server_process_rs.py::test_subscriber_drains_replay_then_receives_live_events` | `src/process.rs::ExecProcessEventLog::subscribe`, `ExecProcessEventReceiver::recv` | Subscribers drain replayed history before receiving live events. |
| `tests/test_exec_server_process_rs.py::test_empty_receiver_has_no_replay` | `src/process.rs::ExecProcessEventReceiver::empty` | Empty receivers have no replayed events. |
| `tests/test_exec_server_process_rs.py::test_process_trait_boundaries_are_explicitly_unported` | `src/process.rs::ExecProcess`, `ExecBackend`, `StartedExecProcess` | Python exposes the process trait surfaces without claiming concrete runtime execution. |
| `tests/test_exec_server_process_id_runtime_paths_rs.py::test_process_id_string_newtype_contract` | `src/process_id.rs` | `ProcessId` mirrors Rust's transparent `String` newtype: construction, string accessors, display, equality, hashing, and ordering. |
| `tests/test_exec_server_process_id_runtime_paths_rs.py::test_process_id_protocol_fields_keep_transparent_value` | `src/process_id.rs`, protocol process-id fields | Protocol dataclasses carry the `ProcessId` string identity without a nested object shape. |
| `tests/test_exec_server_process_id_runtime_paths_rs.py::test_runtime_paths_from_optional_paths_requires_codex_self_exe` | `src/runtime_paths.rs` | `from_optional_paths` rejects missing `codex_self_exe` with the Rust user-facing error text. |
| `tests/test_exec_server_process_id_runtime_paths_rs.py::test_runtime_paths_new_absolutizes_configured_paths` | `src/runtime_paths.rs`, `codex-utils-absolute-path` | `new` converts configured paths through `AbsolutePathBuf::from_absolute_path`, including relative-path absolutization. |
| `tests/test_exec_server_process_id_runtime_paths_rs.py::test_runtime_paths_accepts_missing_linux_sandbox_path` | `src/runtime_paths.rs` | `codex_linux_sandbox_exe` remains optional once `codex_self_exe` is configured. |
| `tests/test_exec_server_rpc_rs.py::test_rpc_error_helpers_match_rust_codes` | `src/rpc.rs` | RPC error helpers emit Rust JSON-RPC codes and no data payload. |
| `tests/test_exec_server_rpc_rs.py::test_encode_server_message_matches_jsonrpc_envelopes` | `src/rpc.rs::encode_server_message` | Outbound response/error/notification messages encode to lite JSON-RPC envelopes. |
| `tests/test_exec_server_rpc_rs.py::test_decode_params_falls_back_empty_object_to_null` | `src/rpc.rs::decode_params` | Failed `{}` param decoding retries with null and request errors map to invalid_params. |
| `tests/test_exec_server_rpc_rs.py::test_rpc_router_request_and_request_with_id_routes` | `src/rpc.rs::RpcRouter::request`, `request_with_id` | Request routes decode params, invoke handlers, return encoded responses, and request-with-id success emits no response. |
| `tests/test_exec_server_rpc_rs.py::test_rpc_router_request_decode_error_returns_error_message` | `src/rpc.rs::RpcRouter::request` | Request param decode errors become outbound JSON-RPC errors. |
| `tests/test_exec_server_rpc_rs.py::test_rpc_router_notification_route_reports_decode_errors` | `src/rpc.rs::RpcRouter::notification` | Notification param decode errors return plain error strings. |
| `tests/test_exec_server_rpc_rs.py::test_handle_server_message_routes_responses_errors_and_notifications` | `src/rpc.rs::handle_server_message` | Responses/errors resolve pending requests and notifications become client events. |
| `tests/test_exec_server_rpc_rs.py::test_rpc_client_matches_out_of_order_responses_by_request_id` | `src/rpc.rs`, Rust test `rpc_client_matches_out_of_order_responses_by_request_id` | Concurrent calls are matched by JSON-RPC request id, independent of response order. |
| `tests/test_exec_server_rpc_rs.py::test_drain_pending_fails_unresolved_calls_as_closed` | `src/rpc.rs::drain_pending` | Pending calls fail as closed when the transport drains unresolved requests. |
| `tests/test_exec_server_relay_rs.py::test_relay_resume_frame_uses_rust_prost_wire_shape` | `src/relay.rs::RelayMessageFrame::resume`, `src/relay_proto.rs`, `src/proto/codex.exec_server.relay.v1.proto` | Relay resume frames encode with Rust prost field numbers: version 1, stream id, and an empty resume oneof body. |
| `tests/test_exec_server_relay_rs.py::test_relay_data_frame_encodes_and_decodes_jsonrpc_payload` | `src/relay.rs::{RelayMessageFrame::data,jsonrpc_payload,into_jsonrpc_message}` | Data frames carry compact JSON-RPC payload bytes in a single-segment `RelayData` body and decode back to `JSONRPCMessage`. |
| `tests/test_exec_server_relay_rs.py::test_relay_frame_validation_errors_match_rust` | `src/relay.rs::RelayMessageFrame::validate` | Relay frame validation rejects unsupported versions, empty stream ids, incomplete data/reset frames, and missing bodies with Rust-shaped protocol errors. |
| `tests/test_exec_server_relay_rs.py::test_relay_non_data_frame_is_not_jsonrpc_payload` | `src/relay.rs::RelayMessageFrame::into_jsonrpc_message` | Non-data relay frames cannot be converted into JSON-RPC messages. |
| `tests/test_exec_server_relay_rs.py::test_relay_reset_reason_only_returns_nonempty_reset_reason` | `src/relay.rs::RelayMessageFrame::into_reset_reason` | Reset reasons are extracted only from non-empty reset bodies. |
| `tests/test_exec_server_relay_rs.py::test_decode_relay_message_frame_maps_malformed_protobuf_to_protocol_error` | `src/relay.rs::decode_relay_message_frame` | Malformed protobuf payloads are reported as relay protocol errors. |
| `tests/test_exec_server_relay_rs.py::test_harness_connection_receives_relay_data` | `src/relay.rs::harness_connection_from_websocket`, Rust test `harness_connection_receives_relay_data` | Harness relay connections emit an initial resume frame and route matching relay data frames into JSON-RPC connection message events. |
| `tests/test_exec_server_relay_rs.py::test_harness_connection_reports_text_frames_as_malformed` | `src/relay.rs::harness_connection_from_websocket`, Rust test `harness_connection_reports_text_frames_as_malformed` | Text websocket frames on the relay transport report the Rust malformed-message string. |
| `tests/test_exec_server_relay_rs.py::test_harness_connection_reports_server_close` | `src/relay.rs::harness_connection_from_websocket`, Rust test `harness_connection_reports_server_close` | Relay websocket close frames become disconnected events with no reason. |
| `tests/test_exec_server_relay_rs.py::test_harness_connection_keeps_outbound_frame_while_send_is_backpressured` | `src/relay.rs::harness_connection_from_websocket`, Rust test `harness_connection_keeps_outbound_frame_while_send_is_backpressured` | The single relay transport loop preserves an outbound data frame while its write is backpressured and does not process ignored inbound frames first. |
| `tests/test_exec_server_relay_rs.py::test_run_multiplexed_environment_spawns_virtual_stream_and_frames_processor_response` | `src/relay.rs::run_multiplexed_environment` and `src/relay.rs::spawn_virtual_stream` | A relay data frame creates a virtual JSON-RPC connection, delivers the decoded message to the processor, and frames the processor's outbound response onto the physical websocket using the same stream id. |
| `tests/test_exec_server_relay_rs.py::test_run_multiplexed_environment_reset_disconnects_matching_virtual_stream` | `src/relay.rs::run_multiplexed_environment`, reset branch, and `VirtualStream::disconnect` | Reset frames disconnect only the matching active virtual stream and preserve the reset reason. |
| `tests/test_exec_server_relay_rs.py::test_run_multiplexed_environment_close_disconnects_active_virtual_streams` | `src/relay.rs::run_multiplexed_environment` loop exit cleanup | Physical websocket close disconnects all active virtual streams with no reason. |
| `tests/test_exec_server_relay_rs.py::test_run_multiplexed_environment_drops_malformed_non_data_and_nonbinary_frames` | `src/relay.rs::run_multiplexed_environment` frame filtering | Non-binary, malformed protobuf, and non-data relay frames are dropped before any virtual stream is created. |
| `tests/test_exec_server_file_system_handler_rs.py::test_no_platform_sandbox_policies_do_not_require_configured_sandbox_helper` | `src/server/file_system_handler.rs`, Rust test `no_platform_sandbox_policies_do_not_require_configured_sandbox_helper` | Disabled/danger-full-access and external sandbox contexts use the unsandboxed LocalFileSystem path without requiring configured helper runtime. |
| `tests/test_exec_server_file_system_handler_rs.py::test_file_system_handler_projects_read_write_metadata_and_directory` | `src/server/file_system_handler.rs::FileSystemHandler` | Read/write/metadata/readDirectory methods translate protocol params/responses and forward sandbox context. |
| `tests/test_exec_server_file_system_handler_rs.py::test_file_system_handler_uses_rust_default_options_for_create_and_remove` | `src/server/file_system_handler.rs::FileSystemHandler::{create_directory,remove}` | Omitted create-directory recursive and remove recursive/force options default to true. |
| `tests/test_exec_server_file_system_handler_rs.py::test_file_system_handler_copy_forwards_recursive_option` | `src/server/file_system_handler.rs::FileSystemHandler::copy` | Copy forwards params.recursive through CopyOptions and returns the empty protocol response on success. |
| `tests/test_exec_server_file_system_handler_rs.py::test_file_system_handler_invalid_base64_maps_to_invalid_request` | `src/server/file_system_handler.rs::FileSystemHandler::write_file` | Invalid dataBase64 maps to invalid_request with the fs/writeFile method name in the message. |
| `tests/test_exec_server_file_system_handler_rs.py::test_file_system_handler_maps_filesystem_errors` | `src/server/file_system_handler.rs::map_fs_error` | Filesystem errors map to not_found, invalid_request, or internal_error by IO error kind. |
| `tests/test_exec_server_remote_file_system_rs.py::test_remote_sandbox_context_drops_unused_cwd` | `src/remote_file_system.rs::remote_sandbox_context`, Rust test `remote_sandbox_context_drops_unused_cwd` | Remote filesystem sandbox contexts drop cwd when permissions do not contain cwd-dependent project-root entries. |
| `tests/test_exec_server_remote_file_system_rs.py::test_remote_sandbox_context_preserves_required_cwd` | `src/remote_file_system.rs::remote_sandbox_context`, Rust test `remote_sandbox_context_preserves_required_cwd` | Remote filesystem sandbox contexts preserve cwd when project-root permissions require remote dynamic path resolution. |
| `tests/test_exec_server_remote_file_system_rs.py::test_transport_errors_map_to_broken_pipe` | `src/remote_file_system.rs::map_remote_error`, Rust test `transport_errors_map_to_broken_pipe` | Closed and disconnected remote transports map to BrokenPipe-style filesystem errors with the Rust message. |
| `tests/test_exec_server_remote_file_system_rs.py::test_remote_errors_map_by_jsonrpc_code` | `src/remote_file_system.rs::map_remote_error` | Remote JSON-RPC not-found and invalid-request server errors map to filesystem not-found and invalid-input errors; other server errors remain generic IO errors. |
| `tests/test_exec_server_remote_file_system_rs.py::test_remote_file_system_projects_rpc_params_and_responses` | `src/remote_file_system.rs::RemoteFileSystem` | Remote filesystem operations project to `fs/*` protocol params, preserve options and sandbox contexts, base64 encode writes, and decode metadata/directory responses. |
| `tests/test_exec_server_remote_file_system_rs.py::test_read_file_rejects_invalid_remote_base64` | `src/remote_file_system.rs::RemoteFileSystem::read_file` | Invalid `dataBase64` from a remote read response maps to a method/field-specific invalid-data filesystem error. |
| `tests/test_exec_server_remote_process_rs.py::test_remote_process_start_registers_session_then_execs` | `src/remote_process.rs::RemoteProcess::start` | Remote process start obtains the lazy client, registers a session for the process id, calls `exec` with the original params, and returns a process facade. |
| `tests/test_exec_server_remote_process_rs.py::test_remote_process_start_unregisters_session_when_exec_fails` | `src/remote_process.rs::RemoteProcess::start` | If remote `exec` fails after session registration, the session is unregistered before the error is returned. |
| `tests/test_exec_server_remote_process_rs.py::test_remote_exec_process_delegates_session_methods` | `src/remote_process.rs::RemoteExecProcess` | Remote process handles delegate process id, wake/event subscriptions, read, write, terminate, and unregister cleanup to the client session. |
| `tests/test_exec_server_handler_rs.py::test_handler_initialize_and_initialized_state_machine` | `src/server/handler.rs::ExecServerHandler::{initialize,initialized}` | Initialized before initialize returns the Rust protocol string error, initialize attaches a session, duplicate initialize is rejected, and initialized marks the connection initialized. |
| `tests/test_exec_server_handler_rs.py::test_handler_active_session_resume_is_rejected` | `src/server/handler/tests.rs`, Rust test `active_session_resume_is_rejected` | A second handler cannot initialize against a session id still attached to another connection. |
| `tests/test_exec_server_handler_rs.py::test_handler_filesystem_methods_require_initialize_and_initialized` | `src/server/handler.rs::require_initialized_for`, fs methods | Filesystem methods require initialize and then initialized before delegating to FileSystemHandler. |
| `tests/test_exec_server_handler_rs.py::test_handler_shutdown_detaches_session` | `src/server/handler.rs::ExecServerHandler::shutdown` | Shutdown detaches the active session and clears the process notification sender. |
| `tests/test_exec_server_process_handler_rs.py::test_process_handler_new_wraps_local_process_boundary` | `src/server/process_handler.rs::ProcessHandler::new` | ProcessHandler constructs a LocalProcess boundary with the notification sender while concrete LocalProcess execution remains separate. |
| `tests/test_exec_server_process_handler_rs.py::test_process_handler_delegates_lifecycle_and_notification_sender` | `src/server/process_handler.rs::ProcessHandler::{shutdown,set_notification_sender}` | Lifecycle and notification sender updates delegate to the wrapped process. |
| `tests/test_exec_server_process_handler_rs.py::test_process_handler_delegates_exec_read_write_and_terminate` | `src/server/process_handler.rs::ProcessHandler::{exec,exec_read,exec_write,terminate}` | Process requests are delegated unchanged, and terminate calls LocalProcess::terminate_process. |
| `tests/test_exec_server_server_registry_rs.py::test_build_router_registers_rust_methods` | `src/server/registry.rs::build_router` | Every protocol method in the Rust registry is registered as a request or notification route. |
| `tests/test_exec_server_server_registry_rs.py::test_build_router_dispatches_initialized_notification` | `src/server/registry.rs::build_router` | The initialized notification ignores params, calls `handler.initialized`, and preserves Rust-style `Result<(), String>` error strings. |
| `tests/test_exec_server_server_registry_rs.py::test_build_router_dispatches_http_request_with_request_id` | `src/server/registry.rs::build_router`, `src/protocol.rs::HttpRequestParams` | `http/request` is registered with request id forwarding, decodes typed HTTP protocol params, and emits no JSON-RPC response on success. |
| `tests/test_exec_server_server_registry_rs.py::test_build_router_dispatches_requests_to_matching_handler_methods` | `src/server/registry.rs::build_router`, `src/protocol.rs::{InitializeParams,ExecParams,ReadParams,WriteParams,TerminateParams}` | Process and filesystem requests forward params to the exact handler methods registered in Rust source; initialize and process routes decode camelCase wire params into typed protocol values and encode Rust response shapes back to JSON. |
| `tests/test_exec_server_processor_rs.py::test_transport_disconnect_detaches_session_during_in_flight_read` | `src/server/processor.rs::run_connection` | Transport disconnect cancels an in-flight long-poll process/read route, detaches the first session connection, and lets a second connection resume without waiting for the old read timeout. |
| `tests/test_exec_server_session_registry_rs.py::test_session_registry_attach_creates_new_session` | `src/server/session_registry.rs::SessionRegistry::attach` | Missing resume session id creates a new active session with a process notification sender. |
| `tests/test_exec_server_session_registry_rs.py::test_session_registry_rejects_unknown_resume_session_id` | `src/server/session_registry.rs::SessionRegistry::attach` | Unknown resume ids return Rust-shaped invalid_request errors. |
| `tests/test_exec_server_session_registry_rs.py::test_session_registry_rejects_already_attached_resume` | `src/server/session_registry.rs::SessionRegistry::attach` | Active sessions reject a second connection. |
| `tests/test_exec_server_session_registry_rs.py::test_session_handle_detach_marks_session_detached_and_clears_notifications` | `src/server/session_registry.rs::SessionHandle::detach` | Detach clears current attachment and notification sender while preserving resumability. |
| `tests/test_exec_server_session_registry_rs.py::test_session_registry_resume_detached_session_reattaches_and_reuses_process` | `src/server/session_registry.rs::SessionRegistry::attach` | Non-expired detached sessions resume with the existing process and new notification sender. |
| `tests/test_exec_server_session_registry_rs.py::test_session_registry_expired_resume_shuts_down_process_and_removes_session` | `src/server/session_registry.rs::SessionRegistry::attach` | Expired detached sessions are removed, shut down, and reported as unknown. |
| `tests/test_exec_server_session_registry_rs.py::test_session_registry_expire_if_detached_removes_only_matching_expired_connection` | `src/server/session_registry.rs::SessionRegistry::expire_if_detached` | TTL expiry removes only matching detached connections. |
| `tests/test_exec_server_session_registry_rs.py::test_session_entry_attach_detach_helpers_match_rust_state_transitions` | `src/server/session_registry.rs::SessionEntry` | Entry attach/detach helpers preserve Rust attachment state transitions. |
| `tests/test_exec_server_transport_rs.py::test_parse_listen_url_accepts_default_websocket_url` | `src/server/transport_tests.rs` | `DEFAULT_LISTEN_URL` parses as a WebSocket socket address on `127.0.0.1:0`. |
| `tests/test_exec_server_transport_rs.py::test_parse_listen_url_accepts_stdio_forms` | `src/server/transport_tests.rs` | `stdio` and `stdio://` both select the stdio listen transport. |
| `tests/test_exec_server_transport_rs.py::test_parse_listen_url_accepts_websocket_url` | `src/server/transport_tests.rs` | `ws://IP:PORT` parses as a WebSocket listen transport. |
| `tests/test_exec_server_transport_rs.py::test_parse_listen_url_rejects_invalid_websocket_url` | `src/server/transport_tests.rs` | Hostname websocket bind addresses fail with the Rust invalid-websocket display text. |
| `tests/test_exec_server_transport_rs.py::test_parse_listen_url_rejects_unsupported_url` | `src/server/transport_tests.rs` | Unsupported listen schemes fail with the Rust unsupported-listen display text. |
| `tests/test_exec_server_transport_rs.py::test_parse_listen_url_rejects_bad_ports_and_missing_ports` | `src/server/transport.rs` | WebSocket listen URLs must parse as `std::net::SocketAddr`. |
| `tests/test_exec_server_transport_rs.py::test_stdio_listen_transport_serves_initialize` | `src/server/transport_tests.rs::stdio_listen_transport_serves_initialize`, `src/server/processor.rs` | Newline-framed stdio transport routes initialize through ConnectionProcessor/build_router, returns a camelCase sessionId response, accepts initialized, and exits after client disconnect. |
| `tests/test_exec_server_transport_rs.py::test_websocket_http_handler_serves_readyz_and_initialize` | `src/server/transport.rs::{run_websocket_listener,readiness_handler,websocket_upgrade_handler}` | The websocket listen path serves `GET /readyz` with 200, upgrades `GET /`, decodes masked client websocket frames, writes server websocket frames, and routes initialize through `JsonRpcConnection::from_axum_websocket`/`ConnectionProcessor`. |
| `tests/test_exec_server_server_rs.py::test_server_reexports_transport_public_surface` | `src/server.rs` | Server facade publicly re-exports the listen URL default and listen URL parse error from the transport module. |
| `tests/test_exec_server_server_rs.py::test_run_main_forwards_to_transport` | `src/server.rs::run_main` | `run_main` is an async thin wrapper that forwards listen URL and runtime paths to `transport::run_transport` unchanged. |
| `tests/test_exec_server_lib_rs.py` | `src/lib.rs` | Crate-root `pub use` facade exposes the Rust public surface through package-root `__all__`, preserves key constants, and points exported names at canonical package-root objects. |

## Focused validation

- `python -m pytest tests/test_exec_server_client_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_connection_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_processor_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_server_registry_rs.py tests/test_exec_server_processor_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_client_api_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_fs_sandbox_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_rpc_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_session_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_server_registry_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_handler_rs.py tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_process_handler_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_local_process_rs.py tests/test_exec_server_process_handler_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_server_rs.py tests/test_exec_server_transport_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_remote_process_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_environment_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_remote_rs.py tests/test_exec_server_remote_process_rs.py tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_environment_toml_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_server_remote_rs.py tests/test_exec_server_environment_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_rpc_http_client_rs.py tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_server_remote_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_reqwest_http_client_rs.py tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_rpc_http_client_rs.py -q --tb=short`
- `python -m pytest tests/test_exec_server_relay_rs.py tests/test_exec_server_connection_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_client_transport_rs.py -q --tb=short`

Protocol/registry module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_protocol_rs.py tests/test_exec_server_server_registry_rs.py -q --tb=short`
  passed with `10 passed`.
- `python -m pytest tests/test_exec_server_protocol_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short`
  passed with `29 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_protocol_rs.py tests\test_exec_server_server_registry_rs.py`
  passed.

Handler/session registry module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_handler_rs.py tests/test_exec_server_session_registry_rs.py -q --tb=short`
  passed with `12 passed`.
- `python -m pytest tests/test_exec_server_handler_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_processor_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_process_handler_rs.py -q --tb=short`
  passed with `20 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_handler_rs.py tests\test_exec_server_session_registry_rs.py`
  passed.

Process-handler/processor module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_process_handler_rs.py tests/test_exec_server_processor_rs.py -q --tb=short`
  passed with `4 passed`.
- `python -m pytest tests/test_exec_server_process_handler_rs.py tests/test_exec_server_processor_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_server_registry_rs.py -q --tb=short`
  passed with `20 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_process_handler_rs.py tests\test_exec_server_processor_rs.py`
  passed.

Server facade/transport module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_server_rs.py tests/test_exec_server_transport_rs.py -q --tb=short`
  passed with `9 passed`.
- `python -m pytest tests/test_exec_server_server_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_processor_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_process_handler_rs.py -q --tb=short`
  passed with `17 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_server_rs.py tests\test_exec_server_transport_rs.py`
  passed.

File-system handler module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_file_system_handler_rs.py -q --tb=short`
  passed with `6 passed`.
- `python -m pytest tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_protocol_rs.py -q --tb=short`
  passed with `20 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_file_system_handler_rs.py`
  passed.

Local filesystem module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_local_file_system_rs.py -q --tb=short`
  passed with `9 passed, 1 skipped`.
- `python -m pytest tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_fs_sandbox_rs.py -q --tb=short`
  passed with `36 passed, 1 skipped`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_local_file_system_rs.py`
  passed.

Sandboxed filesystem module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_sandboxed_file_system_rs.py -q --tb=short`
  passed with `8 passed`.
- `python -m pytest tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_fs_sandbox_rs.py -q --tb=short`
  passed with `36 passed, 1 skipped`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_sandboxed_file_system_rs.py`
  passed.

FS sandbox module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_fs_sandbox_rs.py -q --tb=short`
  passed with `13 passed`.
- `python -m pytest tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short`
  passed with `36 passed, 1 skipped`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_fs_sandbox_rs.py`
  passed.

FS helper module group focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_fs_helper_rs.py -q --tb=short`
  passed with `10 passed`.
- `python -m pytest tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short`
  passed with `46 passed, 1 skipped`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_fs_helper_rs.py`
  passed.

Remote filesystem module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_remote_file_system_rs.py -q --tb=short`
  passed with `6 passed`.
- `python -m pytest tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short`
  passed with `42 passed, 1 skipped`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_remote_file_system_rs.py`
  passed.

Remote process module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_remote_process_rs.py -q --tb=short`
  passed with `3 passed`.
- `python -m pytest tests/test_exec_server_remote_process_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_environment_rs.py -q --tb=short`
  passed with `31 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_remote_process_rs.py`
  passed.

Local process module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_local_process_rs.py -q --tb=short`
  passed with `21 passed`.
- `python -m pytest tests/test_exec_server_local_process_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_process_handler_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_handler_rs.py -q --tb=short`
  passed with `43 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_local_process_rs.py`
  passed.

Remote module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_remote_rs.py -q --tb=short`
  passed with `8 passed`.
- `python -m pytest tests/test_exec_server_remote_rs.py tests/test_exec_server_remote_process_rs.py tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_client_transport_rs.py -q --tb=short`
  passed with `55 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_remote_rs.py`
  passed.

Process module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_process_rs.py -q --tb=short`
  passed with `7 passed`.
- `python -m pytest tests/test_exec_server_process_rs.py tests/test_exec_server_local_process_rs.py tests/test_exec_server_remote_process_rs.py tests/test_exec_server_process_handler_rs.py tests/test_exec_server_client_rs.py -q --tb=short`
  passed with `37 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_process_rs.py`
  passed.

Client module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_client_rs.py -q --tb=short`
  passed with `4 passed`.
- `python -m pytest tests/test_exec_server_client_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_protocol_rs.py -q --tb=short`
  passed with `26 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_client_rs.py`
  passed.

Client transport module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_client_transport_rs.py -q --tb=short`
  passed with `9 passed`.
- `python -m pytest tests/test_exec_server_client_transport_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_connection_rs.py tests/test_exec_server_relay_rs.py tests/test_exec_server_protocol_rs.py -q --tb=short`
  passed with `50 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_client_transport_rs.py`
  passed.

Client API module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_client_api_rs.py -q --tb=short`
  passed with `7 passed`.
- `python -m pytest tests/test_exec_server_client_api_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short`
  passed with `25 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_client_api_rs.py`
  passed.

HTTP response body stream module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_http_response_body_stream_rs.py -q --tb=short`
  passed with `8 passed`.
- `python -m pytest tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_server_remote_rs.py tests/test_exec_server_environment_rs.py -q --tb=short`
  passed with `37 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_http_response_body_stream_rs.py`
  passed.

RPC HTTP client module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_rpc_http_client_rs.py -q --tb=short`
  passed with `5 passed`.
- `python -m pytest tests/test_exec_server_rpc_http_client_rs.py tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_server_remote_rs.py -q --tb=short`
  passed with `31 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_rpc_http_client_rs.py`
  passed.

Reqwest HTTP client module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_reqwest_http_client_rs.py -q --tb=short`
  passed with `8 passed`.
- `python -m pytest tests/test_exec_server_reqwest_http_client_rs.py tests/test_exec_server_http_response_body_stream_rs.py tests/test_exec_server_rpc_http_client_rs.py -q --tb=short`
  passed with `21 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_reqwest_http_client_rs.py`
  passed.

Environment module group focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_environment_toml_rs.py -q --tb=short`
  passed with `29 passed`.
- `python -m pytest tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short`
  passed with `41 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_environment_rs.py tests\test_exec_server_environment_provider_rs.py tests\test_exec_server_environment_toml_rs.py`
  passed.

Connection/RPC module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_connection_rs.py tests/test_exec_server_rpc_rs.py -q --tb=short`
  passed with `22 passed`.
- `python -m pytest tests/test_exec_server_connection_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_transport_rs.py -q --tb=short`
  passed with `38 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_connection_rs.py tests\test_exec_server_rpc_rs.py`
  passed.

Process id/runtime paths module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short`
  passed with `5 passed`.
- `python -m pytest tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
  passed with `149 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_process_id_runtime_paths_rs.py`
  passed.

Relay module focused result on 2026-06-21:

- `python -m pytest tests/test_exec_server_relay_rs.py -q --tb=short`
  passed with `18 passed`.
- `python -m pytest tests/test_exec_server_connection_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_client_transport_rs.py -q --tb=short`
  passed with `31 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_relay_rs.py`
  passed.

Crate-focused validation on 2026-06-21:

- `$files = Get-ChildItem tests -Filter 'test_exec_server_*.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q --tb=short`
  passed with `250 passed, 1 skipped`.

Latest crate-focused validation after `src/server/transport.rs` websocket
handler slice on 2026-06-21:

- `$files = Get-ChildItem tests -Filter 'test_exec_server_*_rs.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q --tb=short`
  passed with `251 passed, 1 skipped`.

Latest crate-focused validation after `src/client_transport.rs` stdlib
websocket connect slice on 2026-06-21:

- `$files = Get-ChildItem tests -Filter 'test_exec_server_*_rs.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q --tb=short`
  passed with `252 passed, 1 skipped`.

Latest crate-focused validation after `src/remote.rs` default websocket
connector slice on 2026-06-21:

- `$files = Get-ChildItem tests -Filter 'test_exec_server_*_rs.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q --tb=short`
  passed with `253 passed, 1 skipped`.

Latest crate-focused validation after `src/client_transport.rs` websocket
101 protocol-header validation on 2026-06-21:

- `$files = Get-ChildItem tests -Filter 'test_exec_server_*.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q --tb=short`
  passed with `254 passed, 1 skipped`.

Crate-root facade validation on 2026-06-21:

- `python -m pytest tests/test_exec_server_lib_rs.py -q --tb=short`
  passed with `3 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_lib_rs.py`
  passed.

## Non-blocking runtime notes

The crate is complete for the dependency-light Python port. Exact Windows
ConPTY/job-object process-tree behavior, concrete Axum/tungstenite websocket
runtime identity, live `wss://` rendezvous service integration, exact reqwest
custom-CA/TLS and immediate header-before-body streaming timing, and unbounded
live remote/runtime orchestration remain optional operational checks. They do
not block crate completion because the registered module-scoped behavior
contracts have Rust-derived Python coverage and the crate-focused suite passes.
