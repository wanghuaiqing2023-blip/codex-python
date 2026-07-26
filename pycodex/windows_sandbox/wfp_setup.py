"""Best-effort WFP installation with setup telemetry.

Rust owner: ``codex-windows-sandbox::wfp_setup``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .setup_error import sanitize_setup_metric_tag_value
from .wfp import install_wfp_filters_for_account


WFP_SETUP_SERVICE_NAME = "codex-windows-sandbox-setup"
WFP_SETUP_SUCCESS_METRIC = "codex.windows_sandbox.wfp_setup_success"
WFP_SETUP_FAILURE_METRIC = "codex.windows_sandbox.wfp_setup_failure"


class WfpSetupMetricOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class WfpSetupMetric:
    outcome: WfpSetupMetricOutcome
    target_account: str
    installed_filter_count: int
    error: str | None = None


def _metrics_recorder(otel: object | None) -> object | None:
    if otel is None:
        return None
    if callable(getattr(otel, "counter", None)):
        return otel
    metrics = getattr(otel, "metrics", None)
    if callable(metrics):
        return metrics()
    return metrics


def _emit_wfp_setup_metric(
    codex_home: Path,
    otel: object | None,
    metric: WfpSetupMetric,
) -> None:
    del codex_home
    metrics = _metrics_recorder(otel)
    counter = getattr(metrics, "counter", None)
    if not callable(counter):
        return
    target_account = sanitize_setup_metric_tag_value(metric.target_account)
    if metric.outcome is WfpSetupMetricOutcome.SUCCESS:
        counter(
            WFP_SETUP_SUCCESS_METRIC,
            1,
            (
                ("target_account", target_account),
                (
                    "installed_filter_count",
                    str(metric.installed_filter_count),
                ),
            ),
        )
        return
    tags: list[tuple[str, str]] = [("target_account", target_account)]
    if metric.error is not None:
        tags.append(
            ("message", sanitize_setup_metric_tag_value(metric.error))
        )
    counter(WFP_SETUP_FAILURE_METRIC, 1, tuple(tags))


def install_wfp_filters(
    codex_home: str | Path,
    offline_username: str,
    otel: object | None,
    log: Callable[[str], Any],
) -> None:
    """Install account filters without allowing WFP or metrics failure to abort setup."""

    try:
        installed_filter_count = install_wfp_filters_for_account(
            offline_username
        )
    except BaseException as exc:
        error = str(exc) or type(exc).__name__
        log(
            f"WFP setup failed for {offline_username}: {error}; "
            "continuing elevated setup"
        )
        metric = WfpSetupMetric(
            WfpSetupMetricOutcome.FAILURE,
            offline_username,
            0,
            error,
        )
    else:
        log(
            f"WFP setup succeeded for {offline_username} with "
            f"{installed_filter_count} installed filters"
        )
        metric = WfpSetupMetric(
            WfpSetupMetricOutcome.SUCCESS,
            offline_username,
            installed_filter_count,
        )

    try:
        _emit_wfp_setup_metric(Path(codex_home), otel, metric)
    except BaseException as exc:
        error = str(exc) or type(exc).__name__
        log(
            f"failed to emit WFP setup metric for "
            f"{offline_username}: {error}"
        )


__all__ = [
    "WFP_SETUP_FAILURE_METRIC",
    "WFP_SETUP_SERVICE_NAME",
    "WFP_SETUP_SUCCESS_METRIC",
    "WfpSetupMetric",
    "WfpSetupMetricOutcome",
    "install_wfp_filters",
]
