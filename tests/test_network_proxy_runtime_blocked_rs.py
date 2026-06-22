import asyncio
import json

from pycodex.network_proxy import (
    BlockedRequest,
    BlockedRequestArgs,
    ConfigState,
    MAX_BLOCKED_EVENTS,
    NETWORK_POLICY_VIOLATION_PREFIX,
    NetworkMode,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyState,
    StaticNetworkProxyReloader,
    blocked_request_violation_log_line,
)


def state_for_blocked() -> NetworkProxyState:
    state = ConfigState(NetworkProxyConfig(), NetworkProxyConstraints())
    return NetworkProxyState(state, StaticNetworkProxyReloader(state))


def blocked_request(host: str = "google.com", *, timestamp: int | None = None) -> BlockedRequest:
    request = BlockedRequest.new(
        BlockedRequestArgs(
            host=host,
            reason="not_allowed",
            client=None,
            method="GET",
            mode=None,
            protocol="http",
            decision="ask",
            source="decider",
            port=80,
        )
    )
    if timestamp is None:
        return request
    return BlockedRequest(
        host=request.host,
        reason=request.reason,
        client=request.client,
        method=request.method,
        mode=request.mode,
        protocol=request.protocol,
        decision=request.decision,
        source=request.source,
        port=request.port,
        timestamp=timestamp,
    )


def test_blocked_snapshot_does_not_consume_entries() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: blocked_snapshot_does_not_consume_entries
    # Contract: blocked_snapshot returns a clone of buffered entries without draining them.
    state = state_for_blocked()

    asyncio.run(state.record_blocked(blocked_request()))

    snapshot = asyncio.run(state.blocked_snapshot())
    assert len(snapshot) == 1
    assert snapshot[0].host == "google.com"
    assert snapshot[0].decision == "ask"

    drained = asyncio.run(state.drain_blocked())
    assert len(drained) == 1
    assert drained[0].host == snapshot[0].host
    assert drained[0].reason == snapshot[0].reason
    assert drained[0].decision == snapshot[0].decision
    assert drained[0].source == snapshot[0].source
    assert drained[0].port == snapshot[0].port


def test_drain_blocked_returns_buffered_window() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: drain_blocked_returns_buffered_window
    # Contract: record_blocked keeps only MAX_BLOCKED_EVENTS newest entries and drain preserves FIFO order.
    state = state_for_blocked()

    for idx in range(MAX_BLOCKED_EVENTS + 5):
        asyncio.run(state.record_blocked(blocked_request(f"example{idx}.com")))

    blocked = asyncio.run(state.drain_blocked())
    assert len(blocked) == MAX_BLOCKED_EVENTS
    assert blocked[0].host == "example5.com"
    assert blocked[-1].host == f"example{MAX_BLOCKED_EVENTS + 4}.com"
    assert asyncio.run(state.drain_blocked()) == []


def test_blocked_request_violation_log_line_serializes_payload() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: blocked_request_violation_log_line_serializes_payload
    # Contract: violation log line is the fixed prefix plus compact serde_json payload with None decision/source/port omitted only.
    entry = BlockedRequest(
        host="google.com",
        reason="not_allowed",
        client="127.0.0.1",
        method="GET",
        mode=NetworkMode.FULL,
        protocol="http",
        decision="ask",
        source="decider",
        port=80,
        timestamp=1_735_689_600,
    )

    assert blocked_request_violation_log_line(entry) == (
        f'{NETWORK_POLICY_VIOLATION_PREFIX} '
        '{"host":"google.com","reason":"not_allowed","client":"127.0.0.1",'
        '"method":"GET","mode":"full","protocol":"http","decision":"ask",'
        '"source":"decider","port":80,"timestamp":1735689600}'
    )


def test_blocked_request_to_mapping_skips_only_rust_skip_serializing_fields() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust item: BlockedRequest serde shape
    # Contract: decision/source/port are skipped when absent, while client/method/mode remain null.
    entry = BlockedRequest(
        host="google.com",
        reason="not_allowed",
        client=None,
        method=None,
        mode=None,
        protocol="http",
        decision=None,
        source=None,
        port=None,
        timestamp=1,
    )

    assert entry.to_mapping() == {
        "host": "google.com",
        "reason": "not_allowed",
        "client": None,
        "method": None,
        "mode": None,
        "protocol": "http",
        "timestamp": 1,
    }
    assert json.loads(blocked_request_violation_log_line(entry).split(" ", 1)[1]) == entry.to_mapping()


def test_record_blocked_notifies_observer_with_original_entry() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust items: BlockedRequestObserver, NetworkProxyState::record_blocked
    # Contract: record_blocked calls the configured observer with the blocked request after buffering it.
    state = state_for_blocked()
    seen: list[BlockedRequest] = []

    async def observer(request: BlockedRequest) -> None:
        seen.append(request)

    asyncio.run(state.set_blocked_request_observer(observer))
    entry = blocked_request()
    asyncio.run(state.record_blocked(entry))

    assert seen == [entry]
