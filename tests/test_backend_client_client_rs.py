from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import pycodex.backend_client as backend_client
from pycodex.app_server_protocol.account import CreditsSnapshot
from pycodex.app_server_protocol.account import RateLimitReachedType
from pycodex.app_server_protocol.account import RateLimitSnapshot
from pycodex.app_server_protocol.account import RateLimitWindow
from pycodex.backend_client import AddCreditsNudgeCreditType
from pycodex.backend_client import BackendRequest
from pycodex.backend_client import BackendResponse
from pycodex.backend_client import Client
from pycodex.backend_client import PathStyle
from pycodex.backend_client import RequestError
from pycodex.codex_client.chatgpt_cloudflare_cookies import ChatGptCloudflareCookieStore
from pycodex.codex_backend_openapi_models.models import AdditionalRateLimitDetails
from pycodex.codex_backend_openapi_models.models import CreditStatusDetails
from pycodex.codex_backend_openapi_models.models import PlanType as BackendPlanType
from pycodex.codex_backend_openapi_models.models import RateLimitReachedKind
from pycodex.codex_backend_openapi_models.models import RateLimitReachedType as BackendRateLimitReachedType
from pycodex.codex_backend_openapi_models.models import RateLimitStatusDetails
from pycodex.codex_backend_openapi_models.models import RateLimitStatusPayload
from pycodex.codex_backend_openapi_models.models import RateLimitWindowSnapshot
from pycodex.protocol.account import PlanType


def test_map_plan_type_supports_usage_based_business_variants_and_unknowns() -> None:
    # Rust: codex-backend-client src/client.rs tests::map_plan_type_supports_usage_based_business_variants.
    cases = [
        (BackendPlanType.SELF_SERVE_BUSINESS_USAGE_BASED, PlanType.SELF_SERVE_BUSINESS_USAGE_BASED),
        (BackendPlanType.ENTERPRISE_CBP_USAGE_BASED, PlanType.ENTERPRISE_CBP_USAGE_BASED),
        (BackendPlanType.EDUCATION, PlanType.EDU),
        (BackendPlanType.EDU, PlanType.EDU),
        (BackendPlanType.GUEST, PlanType.UNKNOWN),
        (BackendPlanType.FREE_WORKSPACE, PlanType.UNKNOWN),
        (BackendPlanType.QUORUM, PlanType.UNKNOWN),
        (BackendPlanType.K12, PlanType.UNKNOWN),
        (BackendPlanType.UNKNOWN, PlanType.UNKNOWN),
    ]
    for backend_plan, expected in cases:
        payload = RateLimitStatusPayload(plan_type=backend_plan)
        assert Client.rate_limit_snapshots_from_payload(payload)[0].plan_type == expected


def test_usage_payload_maps_primary_and_additional_rate_limits() -> None:
    # Rust: codex-backend-client src/client.rs tests::usage_payload_maps_primary_and_additional_rate_limits.
    payload = RateLimitStatusPayload(
        plan_type=BackendPlanType.PRO,
        rate_limit=RateLimitStatusDetails(
            primary_window=RateLimitWindowSnapshot(42, 300, 0, 123),
            secondary_window=RateLimitWindowSnapshot(84, 3600, 0, 456),
        ),
        additional_rate_limits=(
            AdditionalRateLimitDetails(
                limit_name="codex_other",
                metered_feature="codex_other",
                rate_limit=RateLimitStatusDetails(primary_window=RateLimitWindowSnapshot(70, 900, 0, 789)),
            ),
        ),
        credits=CreditStatusDetails(has_credits=True, unlimited=False, balance="9.99"),
        rate_limit_reached_type=BackendRateLimitReachedType(RateLimitReachedKind.WORKSPACE_MEMBER_CREDITS_DEPLETED),
    )

    snapshots = Client.rate_limit_snapshots_from_payload(payload)
    assert len(snapshots) == 2

    assert snapshots[0].limit_id == "codex"
    assert snapshots[0].limit_name is None
    assert snapshots[0].primary == RateLimitWindow(used_percent=42, window_duration_mins=5, resets_at=123)
    assert snapshots[0].secondary == RateLimitWindow(used_percent=84, window_duration_mins=60, resets_at=456)
    assert snapshots[0].credits == CreditsSnapshot(has_credits=True, unlimited=False, balance="9.99")
    assert snapshots[0].plan_type == PlanType.PRO
    assert snapshots[0].rate_limit_reached_type == RateLimitReachedType.WORKSPACE_MEMBER_CREDITS_DEPLETED

    assert snapshots[1].limit_id == "codex_other"
    assert snapshots[1].limit_name == "codex_other"
    assert snapshots[1].primary == RateLimitWindow(used_percent=70, window_duration_mins=15, resets_at=789)
    assert snapshots[1].secondary is None
    assert snapshots[1].credits is None
    assert snapshots[1].plan_type == PlanType.PRO
    assert snapshots[1].rate_limit_reached_type is None


def test_usage_payload_maps_zero_rate_limit_when_primary_absent() -> None:
    # Rust: codex-backend-client src/client.rs tests::usage_payload_maps_zero_rate_limit_when_primary_absent.
    payload = RateLimitStatusPayload(
        plan_type=BackendPlanType.PLUS,
        rate_limit=None,
        additional_rate_limits=(AdditionalRateLimitDetails("codex_other", "codex_other", None),),
        credits=None,
        rate_limit_reached_type=None,
    )

    snapshots = Client.rate_limit_snapshots_from_payload(payload)
    assert len(snapshots) == 2
    assert snapshots[0].limit_id == "codex"
    assert snapshots[0].limit_name is None
    assert snapshots[0].primary is None
    assert snapshots[1].limit_id == "codex_other"
    assert snapshots[1].limit_name == "codex_other"
    assert snapshots[1].primary is None


def test_preferred_snapshot_selection_matches_get_rate_limits_behavior() -> None:
    # Rust: codex-backend-client src/client.rs tests::preferred_snapshot_selection_matches_get_rate_limits_behavior.
    snapshots = [
        RateLimitSnapshot(
            limit_id="codex_other",
            limit_name="codex_other",
            primary=RateLimitWindow(used_percent=90, window_duration_mins=60, resets_at=1),
            plan_type=PlanType.PRO,
        ),
        RateLimitSnapshot(
            limit_id="codex",
            limit_name="codex",
            primary=RateLimitWindow(used_percent=10, window_duration_mins=60, resets_at=2),
            plan_type=PlanType.PRO,
        ),
    ]
    assert Client.preferred_rate_limit_snapshot(snapshots).limit_id == "codex"
    assert Client.preferred_rate_limit_snapshot(snapshots[:1]).limit_id == "codex_other"
    with pytest.raises(IndexError):
        Client.preferred_rate_limit_snapshot([])


def test_usage_payload_maps_every_rate_limit_reached_type() -> None:
    # Rust: codex-backend-client src/client.rs tests::usage_payload_maps_every_rate_limit_reached_type.
    cases = [
        (RateLimitReachedKind.RATE_LIMIT_REACHED, RateLimitReachedType.RATE_LIMIT_REACHED),
        (RateLimitReachedKind.WORKSPACE_OWNER_CREDITS_DEPLETED, RateLimitReachedType.WORKSPACE_OWNER_CREDITS_DEPLETED),
        (RateLimitReachedKind.WORKSPACE_MEMBER_CREDITS_DEPLETED, RateLimitReachedType.WORKSPACE_MEMBER_CREDITS_DEPLETED),
        (RateLimitReachedKind.WORKSPACE_OWNER_USAGE_LIMIT_REACHED, RateLimitReachedType.WORKSPACE_OWNER_USAGE_LIMIT_REACHED),
        (RateLimitReachedKind.WORKSPACE_MEMBER_USAGE_LIMIT_REACHED, RateLimitReachedType.WORKSPACE_MEMBER_USAGE_LIMIT_REACHED),
        (RateLimitReachedKind.UNKNOWN, None),
    ]
    for backend_kind, expected in cases:
        payload = RateLimitStatusPayload(
            plan_type=BackendPlanType.PLUS,
            rate_limit=None,
            credits=None,
            additional_rate_limits=None,
            rate_limit_reached_type=BackendRateLimitReachedType(backend_kind),
        )
        assert Client.rate_limit_snapshots_from_payload(payload)[0].rate_limit_reached_type == expected


def test_usage_payload_preserves_absent_rate_limit_reached_type() -> None:
    # Rust: codex-backend-client src/client.rs tests::usage_payload_preserves_absent_rate_limit_reached_type.
    payload = RateLimitStatusPayload(plan_type=BackendPlanType.PLUS)
    assert Client.rate_limit_snapshots_from_payload(payload)[0].rate_limit_reached_type is None


def test_add_credits_nudge_email_uses_expected_paths_and_bodies() -> None:
    # Rust: codex-backend-client src/client.rs tests::add_credits_nudge_email_uses_expected_paths_and_bodies.
    codex_client = Client("https://example.test", PathStyle.CODEX_API)
    assert (
        codex_client.send_add_credits_nudge_email_url()
        == "https://example.test/api/codex/accounts/send_add_credits_nudge_email"
    )

    chatgpt_client = Client("https://chatgpt.com/backend-api", PathStyle.CHATGPT_API)
    assert (
        chatgpt_client.send_add_credits_nudge_email_url()
        == "https://chatgpt.com/backend-api/wham/accounts/send_add_credits_nudge_email"
    )

    assert Client.send_add_credits_nudge_email_body(AddCreditsNudgeCreditType.CREDITS) == {"credit_type": "credits"}
    assert Client.send_add_credits_nudge_email_body(AddCreditsNudgeCreditType.USAGE_LIMIT) == {
        "credit_type": "usage_limit"
    }


def test_endpoint_url_helpers_match_client_path_style_contract() -> None:
    # Rust: codex-backend-client src/client.rs Client endpoint methods path-style match arms.
    codex_client = Client.new("https://example.test")
    chatgpt_client = Client.new("https://chatgpt.com")

    assert codex_client.rate_limits_url() == "https://example.test/api/codex/usage"
    assert chatgpt_client.rate_limits_url() == "https://chatgpt.com/backend-api/wham/usage"

    assert (
        codex_client.list_tasks_url(limit=20, task_filter="mine", environment_id="env 1", cursor="cur")
        == "https://example.test/api/codex/tasks/list?limit=20&task_filter=mine&cursor=cur&environment_id=env+1"
    )
    assert chatgpt_client.list_tasks_url() == "https://chatgpt.com/backend-api/wham/tasks/list"

    assert codex_client.task_details_url("task_123") == "https://example.test/api/codex/tasks/task_123"
    assert chatgpt_client.task_details_url("task_123") == "https://chatgpt.com/backend-api/wham/tasks/task_123"
    assert (
        codex_client.sibling_turns_url("task_123", "turn_456")
        == "https://example.test/api/codex/tasks/task_123/turns/turn_456/sibling_turns"
    )
    assert (
        chatgpt_client.sibling_turns_url("task_123", "turn_456")
        == "https://chatgpt.com/backend-api/wham/tasks/task_123/turns/turn_456/sibling_turns"
    )
    assert codex_client.config_requirements_file_url() == "https://example.test/api/codex/config/requirements"
    assert chatgpt_client.config_requirements_file_url() == "https://chatgpt.com/backend-api/wham/config/requirements"
    assert codex_client.create_task_url() == "https://example.test/api/codex/tasks"
    assert chatgpt_client.create_task_url() == "https://chatgpt.com/backend-api/wham/tasks"


def test_create_task_id_from_response_prefers_task_id_then_top_level_id() -> None:
    # Rust: codex-backend-client src/client.rs Client::create_task response id extraction.
    client = Client.new("https://example.test")
    assert client.create_task_id_from_response('{"task":{"id":"task_nested"},"id":"top"}') == "task_nested"
    assert client.create_task_id_from_response('{"id":"task_top"}') == "task_top"

    with pytest.raises(ValueError, match="no task id found"):
        client.create_task_id_from_response('{"task":{}}', content_type="application/json")
    with pytest.raises(ValueError, match="Decode error"):
        client.create_task_id_from_response("{", content_type="application/json")


def test_client_endpoint_methods_execute_through_injected_transport() -> None:
    # Rust: codex-backend-client src/client.rs public endpoint methods call exec_request/decode_json.
    seen: list[BackendRequest] = []

    def transport(request: BackendRequest) -> BackendResponse:
        seen.append(request)
        if request.url.endswith("/api/codex/usage"):
            return BackendResponse(
                200,
                '{"plan_type":"pro","rate_limit":{"primary_window":{"used_percent":11,"limit_window_seconds":60,"reset_at":7}}}',
                "application/json",
            )
        if "/tasks/list" in request.url:
            return BackendResponse(200, '{"items":[{"id":"task_1","title":"One"}],"cursor":"next"}', "application/json")
        if request.url.endswith("/tasks/task_1"):
            return BackendResponse(
                200,
                '{"current_assistant_turn":{"output_items":[{"type":"message","content":["done"]}]}}',
                "application/json",
            )
        if request.url.endswith("/sibling_turns"):
            return BackendResponse(200, '{"sibling_turns":[{"id":"turn_2"}]}', "application/json")
        if request.url.endswith("/config/requirements"):
            return BackendResponse(200, '{"contents":"x","sha256":"abc"}', "application/json")
        if request.url.endswith("/accounts/send_add_credits_nudge_email"):
            return BackendResponse(204, "", "")
        if request.url.endswith("/api/codex/tasks") and request.method == "POST":
            return BackendResponse(200, '{"task":{"id":"created"}}', "application/json")
        raise AssertionError(f"unexpected request: {request}")

    client = Client.new("https://example.test").with_transport(transport)
    assert client.get_rate_limits().primary == RateLimitWindow(11, 1, 7)
    assert client.list_tasks(limit=1).items[0].id == "task_1"
    details, body, content_type = client.get_task_details_with_body("task_1")
    assert details.assistant_text_messages() == ["done"]
    assert '"current_assistant_turn"' in body
    assert content_type == "application/json"
    assert client.list_sibling_turns("task_1", "turn_1").sibling_turns == ({"id": "turn_2"},)
    assert client.get_config_requirements_file().sha256 == "abc"
    client.send_add_credits_nudge_email(AddCreditsNudgeCreditType.USAGE_LIMIT)
    assert client.create_task({"prompt": "hello"}) == "created"

    assert [request.method for request in seen] == ["GET", "GET", "GET", "GET", "GET", "POST", "POST"]
    assert seen[1].url == "https://example.test/api/codex/tasks/list?limit=1"
    assert seen[-2].body == b'{"credit_type":"usage_limit"}'
    assert seen[-1].body == b'{"prompt":"hello"}'
    assert seen[-1].headers["content-type"] == "application/json"


def test_exec_request_error_and_decode_error_context_match_rust() -> None:
    # Rust: codex-backend-client src/client.rs exec_request, exec_request_detailed, decode_json.
    def failing_transport(request: BackendRequest) -> BackendResponse:
        if request.url.endswith("/config/requirements"):
            return BackendResponse(401, '{"error":"no"}', "application/json")
        return BackendResponse(200, "not json", "text/plain")

    client = Client.new("https://example.test").with_transport(failing_transport)
    with pytest.raises(RequestError) as detailed:
        client.get_config_requirements_file()
    assert str(detailed.value) == (
        'GET https://example.test/api/codex/config/requirements failed: 401; '
        'content-type=application/json; body={"error":"no"}'
    )
    assert detailed.value.is_unauthorized()

    with pytest.raises(ValueError, match="Decode error for https://example.test/api/codex/usage"):
        client.get_rate_limits_many()


def test_default_stdlib_transport_uses_real_local_http_and_preserves_error_body() -> None:
    # Rust: codex-backend-client src/client.rs exec_request_detailed preserves status/content-type/body.
    requests: list[tuple[str, str, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
            requests.append(("GET", self.path, None))
            if self.path == "/api/codex/usage":
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"plan_type":"plus"}')
            elif self.path == "/api/codex/config/requirements":
                self.send_response(401)
                self.send_header("content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"denied")
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
            body = self.rfile.read(int(self.headers.get("content-length", "0"))).decode("utf-8")
            requests.append(("POST", self.path, body))
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"id":"created"}')

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = Client.new(f"http://127.0.0.1:{server.server_port}")
        assert client.get_rate_limits().plan_type == PlanType.PLUS
        assert client.create_task({"x": 1}) == "created"
        with pytest.raises(RequestError) as exc:
            client.get_config_requirements_file()
        assert exc.value.status == 401
        assert exc.value.content_type == "text/plain"
        assert exc.value.body == "denied"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert requests == [
        ("GET", "/api/codex/usage", None),
        ("POST", "/api/codex/tasks", '{"x":1}'),
        ("GET", "/api/codex/config/requirements", None),
    ]


def test_auth_provider_headers_are_applied_before_explicit_account_overrides() -> None:
    # Rust: codex-backend-client src/client.rs Client::headers calls auth_provider.add_auth_headers before account overrides.
    class BearerLikeAuth:
        def add_auth_headers(self, headers: dict[str, str]) -> None:
            headers["Authorization"] = "Bearer access-token"
            headers["ChatGPT-Account-ID"] = "provider-account"
            headers["X-OpenAI-Fedramp"] = "true"

    client = (
        Client.new("https://example.test")
        .with_user_agent("custom")
        .with_auth_provider(BearerLikeAuth())
        .with_chatgpt_account_id("explicit-account")
        .with_fedramp_routing_header()
    )

    assert client.headers() == {
        "user-agent": "custom",
        "Authorization": "Bearer access-token",
        "ChatGPT-Account-Id": "explicit-account",
        "X-OpenAI-Fedramp": "true",
    }


def test_auth_provider_headers_are_visible_to_transport() -> None:
    # Rust: codex-backend-client src/client.rs endpoint requests call headers() before transport send.
    seen: list[BackendRequest] = []

    class CustomAuth:
        def add_auth_headers(self, headers: dict[str, str]) -> None:
            headers["authorization"] = "Bearer injected"
            headers["x-extra"] = "1"

    def transport(request: BackendRequest) -> BackendResponse:
        seen.append(request)
        return BackendResponse(200, '{"plan_type":"plus"}', "application/json")

    client = Client.new("https://example.test").with_auth_provider(CustomAuth()).with_transport(transport)
    assert client.get_rate_limits().plan_type == PlanType.PLUS
    assert seen[0].headers == {
        "user-agent": "codex-cli",
        "authorization": "Bearer injected",
        "x-extra": "1",
    }


def test_chatgpt_cloudflare_cookie_store_is_applied_to_transport_requests() -> None:
    # Rust: codex-backend-client Client::new wraps reqwest builder with with_chatgpt_cloudflare_cookie_store.
    store = ChatGptCloudflareCookieStore()
    seen: list[BackendRequest] = []

    def transport(request: BackendRequest) -> BackendResponse:
        seen.append(request)
        if len(seen) == 1:
            return BackendResponse(200, '{"plan_type":"plus"}', "application/json", ("_cfuvid=visitor; Path=/; Secure",))
        return BackendResponse(200, '{"plan_type":"plus"}', "application/json")

    client = Client.new("https://chatgpt.com").with_cookie_store(store).with_transport(transport)
    assert client.get_rate_limits().plan_type == PlanType.PLUS
    assert client.get_rate_limits().plan_type == PlanType.PLUS

    assert "Cookie" not in seen[0].headers
    assert seen[1].headers["Cookie"] == "_cfuvid=visitor"


def test_stdlib_transport_uses_custom_ca_bundle_for_https_ssl_context(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust: codex-backend-client Client::new wraps reqwest builder with build_reqwest_client_with_custom_ca.
    seen: dict[str, object] = {}

    class FakeBundle:
        path = Path("C:/tmp/codex-ca.pem")

    def fake_configured_ca_bundle(_env: object) -> FakeBundle:
        return FakeBundle()

    def fake_create_default_context(*, cafile: str | None = None):
        seen["cafile"] = cafile
        return "ssl-context"

    monkeypatch.setattr(backend_client, "configured_ca_bundle", fake_configured_ca_bundle)
    monkeypatch.setattr(backend_client.ssl, "create_default_context", fake_create_default_context)

    assert backend_client._ssl_context_for_request("https://chatgpt.com/backend-api/wham/usage") == "ssl-context"
    assert Path(str(seen["cafile"])) == Path("C:/tmp/codex-ca.pem")
    assert backend_client._ssl_context_for_request("http://chatgpt.com/backend-api/wham/usage") is None


def test_client_new_normalizes_chatgpt_urls_and_headers() -> None:
    # Rust: codex-backend-client src/client.rs Client::new, PathStyle::from_base_url, Client::headers.
    assert Client.new("https://example.test///").base_url == "https://example.test"
    chatgpt = Client.new("https://chatgpt.com")
    assert chatgpt.base_url == "https://chatgpt.com/backend-api"
    assert chatgpt.path_style is PathStyle.CHATGPT_API
    assert Client.new("https://chat.openai.com/").base_url == "https://chat.openai.com/backend-api"
    assert Client.new("https://chatgpt.com/backend-api").base_url == "https://chatgpt.com/backend-api"

    client = chatgpt.with_user_agent("custom").with_chatgpt_account_id("acc").with_fedramp_routing_header()
    assert client.headers() == {
        "user-agent": "custom",
        "ChatGPT-Account-Id": "acc",
        "X-OpenAI-Fedramp": "true",
    }
    assert Client.new("https://example.test").headers() == {"user-agent": "codex-cli"}


def test_request_error_display_and_unauthorized_match_rust() -> None:
    # Rust: codex-backend-client src/client.rs RequestError::{Display,is_unauthorized,status}.
    err = RequestError("POST", "https://example.test/path", 401, "application/json", '{"error":true}')
    assert str(err) == 'POST https://example.test/path failed: 401; content-type=application/json; body={"error":true}'
    assert err.is_unauthorized()
    assert not RequestError("GET", "https://example.test/path", 500).is_unauthorized()
