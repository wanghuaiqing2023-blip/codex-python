"""History cell for hook execution.

Upstream source: ``codex/codex-rs/tui/src/history_cell/hook_cell.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Any, Iterable

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from .base import plain_lines

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::hook_cell",
    source="codex/codex-rs/tui/src/history_cell/hook_cell.rs",
)

HOOK_RUN_REVEAL_DELAY = 0.300
QUIET_HOOK_MIN_VISIBLE = 0.600


class HookEventName(Enum):
    PreToolUse = "PreToolUse"
    PermissionRequest = "PermissionRequest"
    PostToolUse = "PostToolUse"
    PreCompact = "PreCompact"
    PostCompact = "PostCompact"
    SessionStart = "SessionStart"
    UserPromptSubmit = "UserPromptSubmit"
    SubagentStart = "SubagentStart"
    SubagentStop = "SubagentStop"
    Stop = "Stop"

    @classmethod
    def coerce(cls, value: "HookEventName | str | Any") -> "HookEventName":
        if isinstance(value, cls):
            return value
        name = str(getattr(value, "name", value))
        for item in cls:
            if item.name.lower() == name.lower() or item.value.lower() == name.lower():
                return item
        raise ValueError(f"unknown hook event name: {value!r}")


class HookRunStatus(Enum):
    Running = "Running"
    Completed = "Completed"
    Blocked = "Blocked"
    Failed = "Failed"
    Stopped = "Stopped"

    @classmethod
    def coerce(cls, value: "HookRunStatus | str | Any") -> "HookRunStatus":
        if isinstance(value, cls):
            return value
        name = str(getattr(value, "name", value))
        for item in cls:
            if item.name.lower() == name.lower() or item.value.lower() == name.lower():
                return item
        raise ValueError(f"unknown hook run status: {value!r}")


class HookOutputEntryKind(Enum):
    Warning = "Warning"
    Stop = "Stop"
    Feedback = "Feedback"
    Context = "Context"
    Error = "Error"

    @classmethod
    def coerce(cls, value: "HookOutputEntryKind | str | Any") -> "HookOutputEntryKind":
        if isinstance(value, cls):
            return value
        name = str(getattr(value, "name", value))
        for item in cls:
            if item.name.lower() == name.lower() or item.value.lower() == name.lower():
                return item
        raise ValueError(f"unknown hook output entry kind: {value!r}")


@dataclass(frozen=True)
class HookOutputEntry:
    kind: HookOutputEntryKind
    text: str

    @classmethod
    def coerce(cls, value: "HookOutputEntry | dict[str, Any] | Any") -> "HookOutputEntry":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(HookOutputEntryKind.coerce(value.get("kind", "Feedback")), str(value.get("text", "")))
        return cls(HookOutputEntryKind.coerce(getattr(value, "kind")), str(getattr(value, "text", "")))


@dataclass(frozen=True)
class HookRunSummary:
    id: str
    event_name: HookEventName
    status: HookRunStatus = HookRunStatus.Running
    status_message: str | None = None
    entries: tuple[HookOutputEntry, ...] = ()

    @classmethod
    def coerce(cls, value: "HookRunSummary | dict[str, Any] | Any") -> "HookRunSummary":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(
                str(value.get("id", "")),
                HookEventName.coerce(value.get("event_name", "PostToolUse")),
                HookRunStatus.coerce(value.get("status", "Running")),
                None if value.get("status_message") is None else str(value.get("status_message")),
                tuple(HookOutputEntry.coerce(entry) for entry in value.get("entries", ())),
            )
        return cls(
            str(getattr(value, "id")),
            HookEventName.coerce(getattr(value, "event_name")),
            HookRunStatus.coerce(getattr(value, "status", "Running")),
            getattr(value, "status_message", None),
            tuple(HookOutputEntry.coerce(entry) for entry in getattr(value, "entries", ())),
        )


class HookRunStateKind(Enum):
    PendingReveal = "pending_reveal"
    VisibleRunning = "visible_running"
    QuietLinger = "quiet_linger"
    Completed = "completed"


@dataclass
class HookRunState:
    kind: HookRunStateKind
    start_time: float | None = None
    reveal_deadline: float | None = None
    visible_since: float | None = None
    removal_deadline: float | None = None
    status: HookRunStatus | None = None
    entries: list[HookOutputEntry] = field(default_factory=list)

    @classmethod
    def pending(cls, start_time: float) -> "HookRunState":
        return cls(
            HookRunStateKind.PendingReveal,
            start_time=start_time,
            reveal_deadline=start_time + HOOK_RUN_REVEAL_DELAY,
        )

    @classmethod
    def completed(
        cls, status: HookRunStatus, entries: Iterable[HookOutputEntry]
    ) -> "HookRunState":
        return cls(HookRunStateKind.Completed, status=status, entries=list(entries))

    def is_active(self) -> bool:
        return self.kind in {
            HookRunStateKind.PendingReveal,
            HookRunStateKind.VisibleRunning,
            HookRunStateKind.QuietLinger,
        }

    def should_render(self) -> bool:
        return self.kind in {
            HookRunStateKind.VisibleRunning,
            HookRunStateKind.QuietLinger,
            HookRunStateKind.Completed,
        }

    def has_persistent_output(self) -> bool:
        return self.kind is HookRunStateKind.Completed and (
            self.status is not HookRunStatus.Completed or bool(self.entries)
        )

    def is_running_visible(self) -> bool:
        return self.kind in {HookRunStateKind.VisibleRunning, HookRunStateKind.QuietLinger}

    def reveal_if_due(self, now: float) -> bool:
        if self.kind is not HookRunStateKind.PendingReveal:
            return False
        if now < (self.reveal_deadline or 0):
            return False
        self.kind = HookRunStateKind.VisibleRunning
        self.visible_since = now
        return True

    def next_timer_deadline(self) -> float | None:
        if self.kind is HookRunStateKind.PendingReveal:
            return self.reveal_deadline
        if self.kind is HookRunStateKind.QuietLinger:
            return self.removal_deadline
        return None

    def quiet_linger_expired(self, now: float) -> bool:
        return self.kind is HookRunStateKind.QuietLinger and now >= (self.removal_deadline or 0)

    def complete_quiet_success(self, now: float) -> bool:
        if self.kind is not HookRunStateKind.VisibleRunning or self.visible_since is None:
            return False
        deadline = self.visible_since + QUIET_HOOK_MIN_VISIBLE
        if now >= deadline:
            return False
        self.kind = HookRunStateKind.QuietLinger
        self.removal_deadline = deadline
        return True


@dataclass(frozen=True)
class RunningHookGroupKey:
    event_name: HookEventName
    status_message: str | None = None


@dataclass
class RunningHookGroup:
    key: RunningHookGroupKey
    start_time: float | None = None
    count: int = 1

    @classmethod
    def new(
        cls, key: RunningHookGroupKey, start_time: float | None
    ) -> "RunningHookGroup":
        return cls(key, start_time, 1)


@dataclass
class HookRunCell:
    id: str
    event_name: HookEventName
    status_message: str | None
    state: HookRunState

    def running_group_key(self) -> RunningHookGroupKey | None:
        if not self.state.is_running_visible():
            return None
        return RunningHookGroupKey(self.event_name, self.status_message)

    def push_display_lines(self, lines: list[Line], animations_enabled: bool) -> None:
        label = hook_event_label(self.event_name)
        if self.state.kind in {HookRunStateKind.VisibleRunning, HookRunStateKind.QuietLinger}:
            push_running_hook_header(
                lines,
                f"Running {label} hook",
                self.state.start_time,
                self.status_message,
                animations_enabled,
            )
            return
        if self.state.kind is HookRunStateKind.Completed:
            status = self.state.status or HookRunStatus.Completed
            status_text = status.value.lower()
            bullet = hook_completed_bullet(status, self.state.entries)
            lines.append(Line.from_text(f"{bullet.content} {label} hook ({status_text})"))
            for entry in self.state.entries:
                lines.append(Line.from_text(f"  {hook_output_prefix(entry.kind)}{entry.text}"))

    def expire_quiet_linger_now_for_test(self) -> None:
        if self.state.kind is HookRunStateKind.QuietLinger:
            self.state.removal_deadline = monotonic()

    def reveal_running_now_for_test(self, now: float | None = None) -> None:
        if self.state.kind is HookRunStateKind.PendingReveal:
            self.state.reveal_deadline = monotonic() if now is None else now

    def reveal_running_after_delayed_redraw_for_test(self, now: float | None = None) -> None:
        now = monotonic() if now is None else now
        if self.state.kind is HookRunStateKind.PendingReveal:
            self.state.reveal_deadline = now - QUIET_HOOK_MIN_VISIBLE - 0.100


@dataclass(frozen=True)
class Bullet:
    content: str
    style: str = ""


def hook_run_is_quiet_success(run: HookRunSummary | dict[str, Any] | Any) -> bool:
    run = HookRunSummary.coerce(run)
    return run.status is HookRunStatus.Completed and not run.entries


def hook_completed_bullet(
    status: HookRunStatus | str | Any, entries: Iterable[HookOutputEntry | dict[str, Any] | Any]
) -> Bullet:
    status = HookRunStatus.coerce(status)
    coerced_entries = [HookOutputEntry.coerce(entry) for entry in entries]
    if status is HookRunStatus.Completed:
        if any(entry.kind is HookOutputEntryKind.Warning for entry in coerced_entries):
            return Bullet("*", "bold")
        return Bullet("*", "green bold")
    if status in {HookRunStatus.Blocked, HookRunStatus.Failed, HookRunStatus.Stopped}:
        return Bullet("*", "red bold")
    return Bullet("*")


def hook_output_prefix(kind: HookOutputEntryKind | str | Any) -> str:
    kind = HookOutputEntryKind.coerce(kind)
    return {
        HookOutputEntryKind.Warning: "warning: ",
        HookOutputEntryKind.Stop: "stop: ",
        HookOutputEntryKind.Feedback: "feedback: ",
        HookOutputEntryKind.Context: "hook context: ",
        HookOutputEntryKind.Error: "error: ",
    }[kind]


def hook_event_label(event_name: HookEventName | str | Any) -> str:
    return HookEventName.coerce(event_name).value


def earliest_instant(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def push_hook_line_separator(lines: list[Line]) -> None:
    if lines:
        lines.append(Line.from_text(""))


def push_running_hook_header(
    lines: list[Line],
    hook_text: str,
    start_time: float | None,
    status_message: str | None,
    animations_enabled: bool,
) -> None:
    del start_time
    text = hook_text
    if animations_enabled:
        text = f"* {text}"
    if status_message:
        text = f"{text}: {status_message}"
    lines.append(Line.from_text(text))


def push_running_hook_group(
    lines: list[Line], group: RunningHookGroup, animations_enabled: bool
) -> None:
    push_hook_line_separator(lines)
    label = hook_event_label(group.key.event_name)
    hook_text = (
        f"Running {label} hook"
        if group.count == 1
        else f"Running {group.count} {label} hooks"
    )
    push_running_hook_header(
        lines, hook_text, group.start_time, group.key.status_message, animations_enabled
    )


@dataclass
class HookCell:
    runs: list[HookRunCell] = field(default_factory=list)
    animations_enabled: bool = False

    @classmethod
    def new_active(
        cls, run: HookRunSummary | dict[str, Any] | Any, animations_enabled: bool
    ) -> "HookCell":
        cell = cls([], bool(animations_enabled))
        cell.start_run(run)
        return cell

    @classmethod
    def new_completed(
        cls, run: HookRunSummary | dict[str, Any] | Any, animations_enabled: bool
    ) -> "HookCell":
        cell = cls([], bool(animations_enabled))
        cell.add_completed_run(run)
        return cell

    def is_empty(self) -> bool:
        return not self.runs

    def is_active(self) -> bool:
        return any(run.state.is_active() for run in self.runs)

    def should_flush(self) -> bool:
        return not self.is_active() and not self.is_empty()

    def should_render(self) -> bool:
        return any(run.state.should_render() for run in self.runs)

    def take_completed_persistent_runs(self) -> "HookCell | None":
        completed: list[HookRunCell] = []
        remaining: list[HookRunCell] = []
        for run in self.runs:
            if run.state.has_persistent_output():
                completed.append(run)
            else:
                remaining.append(run)
        self.runs = remaining
        return HookCell(completed, self.animations_enabled) if completed else None

    def has_visible_running_run(self) -> bool:
        return any(run.state.is_running_visible() for run in self.runs)

    def advance_time(self, now: float | None = None) -> bool:
        now = monotonic() if now is None else now
        old_len = len(self.runs)
        changed = False
        for run in self.runs:
            changed |= run.state.reveal_if_due(now)
        self.runs = [run for run in self.runs if not run.state.quiet_linger_expired(now)]
        return changed or len(self.runs) != old_len

    def start_run(self, run: HookRunSummary | dict[str, Any] | Any) -> None:
        run = HookRunSummary.coerce(run)
        now = monotonic()
        for existing in self.runs:
            if existing.id == run.id:
                existing.event_name = run.event_name
                existing.status_message = run.status_message
                existing.state = HookRunState.pending(now)
                return
        self.runs.append(
            HookRunCell(
                run.id,
                run.event_name,
                run.status_message,
                HookRunState.pending(now),
            )
        )

    def complete_run(self, run: HookRunSummary | dict[str, Any] | Any) -> bool:
        run = HookRunSummary.coerce(run)
        for index, existing in enumerate(self.runs):
            if existing.id != run.id:
                continue
            if hook_run_is_quiet_success(run):
                if not existing.state.complete_quiet_success(monotonic()):
                    self.runs.pop(index)
                return True
            existing.event_name = run.event_name
            existing.status_message = run.status_message
            existing.state = HookRunState.completed(run.status, run.entries)
            return True
        return False

    def add_completed_run(self, run: HookRunSummary | dict[str, Any] | Any) -> None:
        run = HookRunSummary.coerce(run)
        if hook_run_is_quiet_success(run):
            return
        self.runs.append(
            HookRunCell(
                run.id,
                run.event_name,
                run.status_message,
                HookRunState.completed(run.status, run.entries),
            )
        )

    def next_timer_deadline(self) -> float | None:
        deadlines = [run.state.next_timer_deadline() for run in self.runs]
        deadlines = [deadline for deadline in deadlines if deadline is not None]
        return min(deadlines) if deadlines else None

    def expire_quiet_runs_now_for_test(self) -> None:
        for run in self.runs:
            run.expire_quiet_linger_now_for_test()

    def reveal_running_runs_now_for_test(self) -> None:
        now = monotonic()
        for run in self.runs:
            run.reveal_running_now_for_test(now)

    def reveal_running_runs_after_delayed_redraw_for_test(self) -> None:
        now = monotonic()
        for run in self.runs:
            run.reveal_running_after_delayed_redraw_for_test(now)

    def display_lines(self, _width: int) -> list[Line]:
        lines: list[Line] = []
        running_group: RunningHookGroup | None = None
        for run in self.runs:
            if not run.state.should_render():
                continue
            key = run.running_group_key()
            if key is None:
                if running_group is not None:
                    push_running_hook_group(lines, running_group, self.animations_enabled)
                    running_group = None
                push_hook_line_separator(lines)
                run.push_display_lines(lines, self.animations_enabled)
                continue
            if running_group is not None and running_group.key == key:
                running_group.count += 1
                running_group.start_time = earliest_instant(running_group.start_time, run.state.start_time)
                continue
            if running_group is not None:
                push_running_hook_group(lines, running_group, self.animations_enabled)
            running_group = RunningHookGroup.new(key, run.state.start_time)
        if running_group is not None:
            push_running_hook_group(lines, running_group, self.animations_enabled)
        return lines

    def transcript_lines(self, width: int) -> list[Line]:
        return self.display_lines(width)

    def raw_lines(self) -> list[Line]:
        return plain_lines(self.display_lines(65535))

    def transcript_animation_tick(self) -> int | None:
        if not self.animations_enabled:
            return None
        starts = [run.state.start_time for run in self.runs if run.state.is_running_visible()]
        starts = [start for start in starts if start is not None]
        if not starts:
            return None
        elapsed = monotonic() - min(starts)
        return int((elapsed * 1000) // 600)

    def desired_height(self, width: int) -> int:
        return len(self.display_lines(width))


def new_active_hook_cell(
    run: HookRunSummary | dict[str, Any] | Any, animations_enabled: bool
) -> HookCell:
    return HookCell.new_active(run, animations_enabled)


def new_completed_hook_cell(
    run: HookRunSummary | dict[str, Any] | Any, animations_enabled: bool
) -> HookCell:
    return HookCell.new_completed(run, animations_enabled)


def display_lines(cell: HookCell, width: int) -> list[Line]:
    return cell.display_lines(width)


def transcript_lines(cell: HookCell, width: int) -> list[Line]:
    return cell.transcript_lines(width)


def raw_lines(cell: HookCell) -> list[Line]:
    return cell.raw_lines()


def transcript_animation_tick(cell: HookCell) -> int | None:
    return cell.transcript_animation_tick()


def desired_height(cell: HookCell, width: int) -> int:
    return cell.desired_height(width)


def render(cell: HookCell, area: Any = None, buf: Any = None) -> list[Line]:
    width = getattr(area, "width", 65535) if area is not None else 65535
    lines = cell.display_lines(width)
    if buf is not None and hasattr(buf, "draw"):
        buf.draw(lines, area)
    return lines


__all__ = [
    "HOOK_RUN_REVEAL_DELAY",
    "QUIET_HOOK_MIN_VISIBLE",
    "Bullet",
    "HookCell",
    "HookEventName",
    "HookOutputEntry",
    "HookOutputEntryKind",
    "HookRunCell",
    "HookRunState",
    "HookRunStateKind",
    "HookRunStatus",
    "HookRunSummary",
    "RUST_MODULE",
    "RunningHookGroup",
    "RunningHookGroupKey",
    "desired_height",
    "display_lines",
    "earliest_instant",
    "hook_completed_bullet",
    "hook_event_label",
    "hook_output_prefix",
    "hook_run_is_quiet_success",
    "new_active_hook_cell",
    "new_completed_hook_cell",
    "push_hook_line_separator",
    "push_running_hook_group",
    "push_running_hook_header",
    "raw_lines",
    "render",
    "transcript_animation_tick",
    "transcript_lines",
]
