import asyncio

from pycodex.app_server.connection_rpc_gate import ConnectionRpcGate


def test_run_executes_while_open() -> None:
    # Rust: run_executes_while_open.
    async def scenario() -> None:
        gate = ConnectionRpcGate.new()
        ran = False

        async def handler() -> None:
            nonlocal ran
            ran = True

        assert await gate.run(handler())
        assert ran is True

    asyncio.run(scenario())


def test_run_drops_future_without_polling_after_shutdown() -> None:
    # Rust: run_drops_future_without_polling_after_shutdown.
    async def scenario() -> None:
        gate = ConnectionRpcGate.new()
        await gate.shutdown()
        polled = False

        async def handler() -> None:
            nonlocal polled
            polled = True

        assert not await gate.run(handler())
        assert polled is False
        assert not await gate.is_accepting()

    asyncio.run(scenario())


def test_shutdown_waits_for_started_run_to_finish() -> None:
    # Rust: shutdown_waits_for_started_run_to_finish.
    async def scenario() -> None:
        gate = ConnectionRpcGate.new()
        started = asyncio.Event()
        finish = asyncio.Event()

        async def handler() -> None:
            started.set()
            await finish.wait()

        run_task = asyncio.create_task(gate.run(handler()))
        await started.wait()
        assert gate.inflight_count() == 1

        shutdown_task = asyncio.create_task(gate.shutdown())
        try:
            await asyncio.wait_for(asyncio.shield(shutdown_task), timeout=0.05)
            raise AssertionError("shutdown should wait for the running handler")
        except TimeoutError:
            pass

        finish.set()
        assert await run_task
        await shutdown_task
        assert gate.inflight_count() == 0

    asyncio.run(scenario())


def test_shutdown_drops_late_runs_while_waiting_for_inflight_work() -> None:
    # Rust: shutdown_drops_late_runs_while_waiting_for_inflight_work.
    async def scenario() -> None:
        gate = ConnectionRpcGate.new()
        started = asyncio.Event()
        finish = asyncio.Event()

        async def handler() -> None:
            started.set()
            await finish.wait()

        run_task = asyncio.create_task(gate.run(handler()))
        await started.wait()
        shutdown_task = asyncio.create_task(gate.shutdown())
        await asyncio.sleep(0)

        late_polled = False

        async def late_handler() -> None:
            nonlocal late_polled
            late_polled = True

        assert not await gate.run(late_handler())
        assert late_polled is False

        finish.set()
        assert await run_task
        await shutdown_task
        assert gate.inflight_count() == 0

    asyncio.run(scenario())


def test_run_is_counted_before_handler_body_continues() -> None:
    # Rust: run_is_counted_before_handler_body_continues.
    async def scenario() -> None:
        gate = ConnectionRpcGate.new()
        entered = asyncio.Event()
        continue_run = asyncio.Event()

        async def handler() -> None:
            entered.set()
            await continue_run.wait()

        run_task = asyncio.create_task(gate.run(handler()))
        await entered.wait()
        assert gate.inflight_count() == 1

        continue_run.set()
        assert await run_task
        assert gate.inflight_count() == 0

    asyncio.run(scenario())
