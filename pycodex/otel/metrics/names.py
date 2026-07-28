"""Rust-aligned owner for ``codex-otel::metrics.names``."""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import http.client
import contextvars
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

TOOL_CALL_COUNT_METRIC = "codex.tool.call"

TOOL_CALL_DURATION_METRIC = "codex.tool.call.duration_ms"

TOOL_CALL_UNIFIED_EXEC_METRIC = "codex.tool.unified_exec"

PROCESS_START_METRIC = "codex.process.start"

API_CALL_COUNT_METRIC = "codex.api_request"

API_CALL_DURATION_METRIC = "codex.api_request.duration_ms"

SSE_EVENT_COUNT_METRIC = "codex.sse_event"

SSE_EVENT_DURATION_METRIC = "codex.sse_event.duration_ms"

WEBSOCKET_REQUEST_COUNT_METRIC = "codex.websocket.request"

WEBSOCKET_REQUEST_DURATION_METRIC = "codex.websocket.request.duration_ms"

WEBSOCKET_EVENT_COUNT_METRIC = "codex.websocket.event"

WEBSOCKET_EVENT_DURATION_METRIC = "codex.websocket.event.duration_ms"

RESPONSES_API_OVERHEAD_DURATION_METRIC = "codex.responses_api_overhead.duration_ms"

RESPONSES_API_INFERENCE_TIME_DURATION_METRIC = "codex.responses_api_inference_time.duration_ms"

RESPONSES_API_ENGINE_IAPI_TTFT_DURATION_METRIC = "codex.responses_api_engine_iapi_ttft.duration_ms"

RESPONSES_API_ENGINE_SERVICE_TTFT_DURATION_METRIC = "codex.responses_api_engine_service_ttft.duration_ms"

RESPONSES_API_ENGINE_IAPI_TBT_DURATION_METRIC = "codex.responses_api_engine_iapi_tbt.duration_ms"

RESPONSES_API_ENGINE_SERVICE_TBT_DURATION_METRIC = "codex.responses_api_engine_service_tbt.duration_ms"

TURN_E2E_DURATION_METRIC = "codex.turn.e2e_duration_ms"

TURN_TTFT_DURATION_METRIC = "codex.turn.ttft.duration_ms"

TURN_TTFM_DURATION_METRIC = "codex.turn.ttfm.duration_ms"

TURN_NETWORK_PROXY_METRIC = "codex.turn.network_proxy"

TURN_MEMORY_METRIC = "codex.turn.memory"

TURN_TOOL_CALL_METRIC = "codex.turn.tool.call"

TURN_TOKEN_USAGE_METRIC = "codex.turn.token_usage"

GUARDIAN_REVIEW_COUNT_METRIC = "codex.guardian.review"

GUARDIAN_REVIEW_DURATION_METRIC = "codex.guardian.review.duration_ms"

GUARDIAN_REVIEW_TTFT_DURATION_METRIC = "codex.guardian.review.ttft.duration_ms"

GUARDIAN_REVIEW_TOKEN_USAGE_METRIC = "codex.guardian.review.token_usage"

GOAL_CREATED_METRIC = "codex.goal.created"

GOAL_RESUMED_METRIC = "codex.goal.resumed"

GOAL_COMPLETED_METRIC = "codex.goal.completed"

GOAL_BUDGET_LIMITED_METRIC = "codex.goal.budget_limited"

GOAL_USAGE_LIMITED_METRIC = "codex.goal.usage_limited"

GOAL_BLOCKED_METRIC = "codex.goal.blocked"

GOAL_TOKEN_COUNT_METRIC = "codex.goal.token_count"

GOAL_DURATION_SECONDS_METRIC = "codex.goal.duration_s"

PLUGIN_INSTALL_ELICITATION_SENT_METRIC = "codex.plugins.install_elicitation.sent"

PLUGIN_INSTALL_SUGGESTION_METRIC = "codex.plugins.install_suggestion"

CURATED_PLUGINS_STARTUP_SYNC_METRIC = "codex.plugins.startup_sync"

CURATED_PLUGINS_STARTUP_SYNC_FINAL_METRIC = "codex.plugins.startup_sync.final"

HOOK_RUN_METRIC = "codex.hooks.run"

HOOK_RUN_DURATION_METRIC = "codex.hooks.run.duration_ms"

STARTUP_PHASE_DURATION_METRIC = "codex.startup.phase.duration_ms"

STARTUP_PREWARM_DURATION_METRIC = "codex.startup_prewarm.duration_ms"

STARTUP_PREWARM_AGE_AT_FIRST_TURN_METRIC = "codex.startup_prewarm.age_at_first_turn_ms"

THREAD_STARTED_METRIC = "codex.thread.started"

THREAD_SKILLS_ENABLED_TOTAL_METRIC = "codex.thread.skills.enabled_total"

THREAD_SKILLS_KEPT_TOTAL_METRIC = "codex.thread.skills.kept_total"

THREAD_SKILLS_DESCRIPTION_TRUNCATED_CHARS_METRIC = "codex.thread.skills.description_truncated_chars"

THREAD_SKILLS_TRUNCATED_METRIC = "codex.thread.skills.truncated"


__all__ = [name for name in globals() if not name.startswith("_")]
