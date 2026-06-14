from pycodex.tui.chatwidget.mcp_startup import (
    MCP_STARTUP_MULTI_HEADER_PREFIX,
    MCP_STARTUP_SINGLE_HEADER_PREFIX,
    McpServerStatusUpdatedNotification,
    McpStartupModel,
    McpStartupStatus,
)


def test_single_and_multi_startup_headers_match_rust_shape() -> None:
    model = McpStartupModel()
    model.update_mcp_startup_status("alpha", McpStartupStatus.starting(), complete_when_settled=False)
    assert model.status_header == f"{MCP_STARTUP_SINGLE_HEADER_PREFIX} alpha"

    model.update_mcp_startup_status("beta", McpStartupStatus.starting(), complete_when_settled=False)
    assert model.status_header == f"{MCP_STARTUP_MULTI_HEADER_PREFIX} (0/2): alpha, beta"

    model.update_mcp_startup_status("alpha", McpStartupStatus.ready(), complete_when_settled=False)
    assert model.status_header == f"{MCP_STARTUP_MULTI_HEADER_PREFIX} (1/2): beta"


def test_settled_expected_round_finishes_and_reports_failed_cancelled() -> None:
    model = McpStartupModel(task_running=True)
    model.set_status_header(f"{MCP_STARTUP_SINGLE_HEADER_PREFIX} alpha")
    model.set_mcp_startup_expected_servers(["alpha", "beta", "gamma"])

    model.update_mcp_startup_status("alpha", McpStartupStatus.ready(), complete_when_settled=True)
    model.update_mcp_startup_status("beta", McpStartupStatus.failed("beta exploded"), complete_when_settled=True)
    model.update_mcp_startup_status("gamma", McpStartupStatus.cancelled(), complete_when_settled=True)

    assert model.startup_status is None
    assert model.ignore_updates_until_next_start is True
    assert model.warnings == [
        "beta exploded",
        "MCP startup interrupted. The following servers were not initialized: gamma",
        "MCP startup incomplete (failed: beta)",
    ]
    assert model.reasoning_restores == 1
    assert model.queued_input_releases == 1


def test_finish_after_lag_marks_missing_or_starting_servers_cancelled() -> None:
    model = McpStartupModel()
    model.set_mcp_startup_expected_servers(["alpha", "beta", "gamma"])
    model.update_mcp_startup_status("alpha", McpStartupStatus.ready(), complete_when_settled=False)
    model.update_mcp_startup_status("beta", McpStartupStatus.starting(), complete_when_settled=False)

    model.finish_mcp_startup_after_lag()

    assert model.warnings == [
        "MCP startup interrupted. The following servers were not initialized: beta, gamma"
    ]
    assert model.startup_status is None


def test_ignore_mode_buffers_next_round_until_coherent() -> None:
    model = McpStartupModel(ignore_updates_until_next_start=True)
    model.set_mcp_startup_expected_servers(["alpha", "beta"])

    model.update_mcp_startup_status("alpha", McpStartupStatus.ready(), complete_when_settled=False)
    assert model.startup_status is None
    assert model.ignore_updates_until_next_start is True

    model.update_mcp_startup_status("beta", McpStartupStatus.starting(), complete_when_settled=False)
    assert model.ignore_updates_until_next_start is False
    assert model.startup_status == {
        "alpha": McpStartupStatus.ready(),
        "beta": McpStartupStatus.starting(),
    }
    assert model.status_header == f"{MCP_STARTUP_MULTI_HEADER_PREFIX} (1/2): beta"


def test_notification_conversion_uses_default_failed_error() -> None:
    model = McpStartupModel()
    model.set_mcp_startup_expected_servers(["alpha"])

    model.on_mcp_server_status_updated(McpServerStatusUpdatedNotification("alpha", "failed"))

    assert model.warnings == [
        "MCP client for `alpha` failed to start",
        "MCP startup incomplete (failed: alpha)",
    ]
    assert model.startup_status is None
