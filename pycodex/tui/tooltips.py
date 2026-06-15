"""Behavior port for Rust ``codex-tui::tooltips``."""

from __future__ import annotations

import platform
import random
import re
import threading
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ._porting import RustTuiModule
from .version import CODEX_CLI_VERSION

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None

RUST_MODULE = RustTuiModule(crate="codex-tui", module="tooltips", source="codex/codex-rs/tui/src/tooltips.rs", status="complete")

ANNOUNCEMENT_TIP_URL = "https://raw.githubusercontent.com/openai/codex/main/announcement_tip.toml"
SOURCE_TOOLTIPS_PATH = Path(__file__).resolve().parents[2] / "codex" / "codex-rs" / "tui" / "tooltips.txt"

IS_MACOS = platform.system().lower() == "darwin"
IS_WINDOWS = platform.system().lower() == "windows"

APP_TOOLTIP = "Try the **Codex App**. Run 'codex app' or visit https://chatgpt.com/codex?app-landing-page=true"
FAST_TOOLTIP = "*New* Use **/fast** to enable our fastest inference with increased plan usage."
OTHER_TOOLTIP = "*New* Build faster with the **Codex App**. Run 'codex app' or visit https://chatgpt.com/codex?app-landing-page=true"
OTHER_TOOLTIP_NON_MAC = "*New* Build faster with Codex."
FREE_GO_TOOLTIP = "*New* For a limited time, Codex is included in your plan for free 鈥?let鈥檚 build together."

_RAW_TOOLTIPS_SNAPSHOT = """Use /compact when the conversation gets long to summarize history and free up context.
Start a fresh idea with /new; the previous session stays in history.
Use /feedback to send logs to the maintainers when something looks off.
Switch models or reasoning effort quickly with /model.
Use /permissions to control when Codex asks for confirmation.
Run /review to get a code review of your current changes.
Use /skills to list available skills or ask Codex to use one.
Use /status to see the current model, approvals, and token usage.
Use /statusline to configure which items appear in the status line.
Use /fork to branch the current chat into a new thread.
Use /side to start a side conversation in a temporary fork without polluting the main thread.
Use /init to create an AGENTS.md with project-specific guidance.
Use /mcp to list configured MCP tools.
Run `codex app` to open Codex Desktop (it installs on macOS if needed).
Use /personality to customize how Codex communicates.
Use /rename to rename your threads for easier thread resuming.
Use the OpenAI docs MCP for API questions; enable it with `codex mcp add openaiDeveloperDocs --url https://developers.openai.com/mcp`.
Join the OpenAI community Discord: http://discord.gg/openai
Visit the Codex community forum: https://community.openai.com/c/codex/37
You can run any shell command from Codex using `!` (e.g. `!ls`)
Type / to open the command popup; Tab autocompletes slash commands.
When the composer is empty, press Esc to step back and edit your last message; Enter confirms.
Press Tab to queue a message when a task is running; otherwise it sends immediately (except `!`).
[tui.keymap] in ~/.codex/config.toml lets you rebind supported shortcuts.
See the Codex keymap documentation for supported actions and examples.
Paste an image with Ctrl+V to attach it to your next message.
You can resume a previous conversation by running `codex resume`
Use /copy or press Ctrl+O to copy the latest agent response as Markdown.
"""


def load_raw_tooltips(path: Path = SOURCE_TOOLTIPS_PATH) -> str:
    """Load the same tooltip catalog Rust includes with ``include_str!``."""

    if path.exists():
        return path.read_text(encoding="utf-8")
    return _RAW_TOOLTIPS_SNAPSHOT


RAW_TOOLTIPS = load_raw_tooltips()


class TargetOs(Enum):
    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"
    UNKNOWN = "unknown"

    @classmethod
    def current(cls) -> "TargetOs":
        if IS_MACOS:
            return cls.MACOS
        if IS_WINDOWS:
            return cls.WINDOWS
        return cls.LINUX


CURRENT_OS = TargetOs.current()
ANNOUNCEMENT_TIP: Optional[str] = None


@dataclass(frozen=True)
class AnnouncementTipRaw:
    content: str
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    version_regex: Optional[str] = None
    target_app: Optional[str] = None
    target_plan_types: Optional[List[str]] = None
    target_oses: Optional[List[Any]] = None

    @classmethod
    def from_mapping(cls, mapping: Dict[str, Any]) -> "AnnouncementTipRaw":
        content = mapping.get("content")
        if not isinstance(content, str):
            raise TypeError("content must be a string")
        return cls(
            content=content,
            from_date=_optional_str(mapping.get("from_date")),
            to_date=_optional_str(mapping.get("to_date")),
            version_regex=_optional_str(mapping.get("version_regex")),
            target_app=_optional_str(mapping.get("target_app")),
            target_plan_types=_optional_str_list(mapping.get("target_plan_types")),
            target_oses=_optional_os_list(mapping.get("target_oses")),
        )


@dataclass(frozen=True)
class AnnouncementTipDocument:
    announcements: List[AnnouncementTipRaw]


@dataclass(frozen=True)
class AnnouncementTip:
    content: str
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    version_regex: Optional[Any] = None
    target_app: str = "cli"
    target_plan_types: Optional[List[str]] = None
    target_oses: Optional[List[TargetOs]] = None

    @classmethod
    def from_raw(cls, raw: Any) -> Optional["AnnouncementTip"]:
        if isinstance(raw, dict):
            raw = AnnouncementTipRaw.from_mapping(raw)
        content = raw.content.strip()
        if not content:
            return None
        try:
            from_date = _parse_date(raw.from_date)
            to_date = _parse_date(raw.to_date)
            version_regex = re.compile(raw.version_regex) if raw.version_regex is not None else None
        except Exception:
            return None

        plans = [_normalize_plan(plan) for plan in raw.target_plan_types] if raw.target_plan_types is not None else None
        if plans is not None and any(plan == "unknown" for plan in plans):
            return None
        oses = [_normalize_os(os_name) for os_name in raw.target_oses] if raw.target_oses is not None else None
        if oses is not None and any(os_name is TargetOs.UNKNOWN for os_name in oses):
            return None
        return cls(
            content=content,
            from_date=from_date,
            to_date=to_date,
            version_regex=version_regex,
            target_app=(raw.target_app or "cli").lower(),
            target_plan_types=plans,
            target_oses=oses,
        )

    def version_matches(self, version: str) -> bool:
        return self.version_regex is None or self.version_regex.search(version) is not None

    def date_matches(self, today: date) -> bool:
        if self.from_date is not None and today < self.from_date:
            return False
        if self.to_date is not None and today >= self.to_date:
            return False
        return True


def experimental_tooltips(features: Optional[Iterable[Any]] = None) -> List[str]:
    if features is None:
        return []
    result: List[str] = []
    for spec in features:
        stage = getattr(spec, "stage", None)
        announcement = getattr(stage, "experimental_announcement", None)
        if callable(announcement):
            value = announcement()
        else:
            value = getattr(spec, "experimental_announcement", None)
        if value:
            result.append(str(value))
    return result


def get_tooltip(plan: Any = None, fast_mode_enabled: bool = False, *, rng: Any = None, announcement_text: Optional[str] = None) -> Optional[str]:
    rng = rng or random.Random()
    if announcement_text is None:
        announcement_text = fetch_announcement_tip(plan)
    if announcement_text is not None:
        return announcement_text

    if _random_ratio(rng, 8, 10):
        if _is_paid_plan(plan):
            tooltip = pick_paid_tooltip(rng, fast_mode_enabled)
            if tooltip is not None:
                return tooltip
        if _normalize_plan(plan) in {"go", "free"}:
            return FREE_GO_TOOLTIP
        return OTHER_TOOLTIP if IS_MACOS else OTHER_TOOLTIP_NON_MAC
    return pick_tooltip(rng)


def paid_app_tooltip() -> Optional[str]:
    return APP_TOOLTIP if IS_MACOS or IS_WINDOWS else None


def pick_paid_tooltip(rng: Any, fast_mode_enabled: bool) -> Optional[str]:
    if fast_mode_enabled or _random_bool(rng, 0.5):
        return paid_app_tooltip()
    return FAST_TOOLTIP


def pick_tooltip(rng: Any) -> Optional[str]:
    tooltips = all_tooltips()
    if not tooltips:
        return None
    return tooltips[_random_range(rng, 0, len(tooltips))]


def tooltips() -> List[str]:
    tips = []
    for raw in RAW_TOOLTIPS.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not IS_MACOS and not IS_WINDOWS and "codex app" in line:
            continue
        tips.append(line)
    return tips


def all_tooltips(features: Optional[Iterable[Any]] = None) -> List[str]:
    return [*tooltips(), *experimental_tooltips(features)]


def prewarm(fetcher: Any = None) -> None:
    def worker() -> None:
        global ANNOUNCEMENT_TIP
        ANNOUNCEMENT_TIP = init_announcement_tip_in_thread(fetcher)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

def fetch_announcement_tip(plan: Any = None) -> Optional[str]:
    if ANNOUNCEMENT_TIP is None:
        return None
    return parse_announcement_tip_toml(ANNOUNCEMENT_TIP, plan)


def init_announcement_tip_in_thread(fetcher: Any = None) -> Optional[str]:
    return blocking_init_announcement_tip(fetcher)


def blocking_init_announcement_tip(fetcher: Any = None) -> Optional[str]:
    try:
        if fetcher is not None:
            return fetcher(ANNOUNCEMENT_TIP_URL)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(ANNOUNCEMENT_TIP_URL, headers={"User-Agent": "pycodex-tui"})
        with opener.open(request, timeout=2.0) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset)
    except Exception:
        return None

def parse_announcement_tip_toml(
    text: str,
    plan: Any = None,
    *,
    today: Optional[date] = None,
    version: str = CODEX_CLI_VERSION,
    current_os: TargetOs = CURRENT_OS,
) -> Optional[str]:
    try:
        decoded = _loads_announcement_toml(text)
        raw_entries = decoded.get("announcements") if isinstance(decoded, dict) else None
        if raw_entries is None:
            raw_entries = _loads_announcement_toml(f"announcements = {text}").get("announcements")
    except Exception:
        return None
    if not isinstance(raw_entries, list):
        return None

    latest_match = None
    today = today or datetime.now(timezone.utc).date()
    normalized_plan = _normalize_plan(plan)
    for raw in raw_entries:
        if not isinstance(raw, dict):
            return None
        try:
            tip = AnnouncementTip.from_raw(raw)
        except Exception:
            return None
        if tip is None:
            continue
        plan_matches = tip.target_plan_types is None or (normalized_plan is not None and normalized_plan in tip.target_plan_types)
        os_matches = tip.target_oses is None or current_os in tip.target_oses
        if tip.version_matches(version) and tip.date_matches(today) and tip.target_app == "cli" and plan_matches and os_matches:
            latest_match = tip.content
    return latest_match


def random_tooltip_returns_some_tip_when_available() -> None:
    assert pick_tooltip(random.Random(42)) is not None


def random_tooltip_is_reproducible_with_seed() -> None:
    assert pick_tooltip(random.Random(7)) == pick_tooltip(random.Random(7))


def paid_tooltip_pool_rotates_between_promos() -> None:
    seen = {pick_paid_tooltip(random.Random(seed), False) for seed in range(32)}
    assert seen == {paid_app_tooltip(), FAST_TOOLTIP}


def paid_tooltip_pool_skips_fast_when_fast_mode_is_enabled() -> None:
    seen = {pick_paid_tooltip(random.Random(seed), True) for seed in range(8)}
    assert seen == {paid_app_tooltip()}
    assert FAST_TOOLTIP not in seen


def announcement_tip_toml_picks_last_matching() -> None:
    toml = """
[[announcements]]
content = "first"
from_date = "2000-01-01"

[[announcements]]
content = "latest match"
version_regex = ".*"
target_app = "cli"

[[announcements]]
content = "should not match"
to_date = "2000-01-01"
"""
    assert parse_announcement_tip_toml(toml) == "latest match"


def announcement_tip_toml_picks_no_match() -> None:
    toml = """
[[announcements]]
content = "first"
from_date = "2000-01-01"
to_date = "2000-01-05"

[[announcements]]
content = "latest match"
version_regex = "invalid_version_name"

[[announcements]]
content = "should not match either "
target_app = "vsce"
"""
    assert parse_announcement_tip_toml(toml) is None


def announcement_tip_toml_bad_deserialization() -> None:
    assert parse_announcement_tip_toml('[[announcements]]\ncontent = 123\nfrom_date = "2000-01-01"') is None


def announcement_tip_toml_parse_comments() -> None:
    toml = """
# Example announcement tips for Codex TUI.
[[announcements]]
content = "Welcome to Codex! Check out the new onboarding flow."
from_date = "2024-10-01"
to_date = "2024-10-15"
target_app = "cli"
version_regex = "^0\\.0\\.0$"

[[announcements]]
content = "This is a test announcement"
"""
    assert parse_announcement_tip_toml(toml) == "This is a test announcement"


def announcement_tip_toml_matches_target_plan_type() -> None:
    toml = """
[[announcements]]
content = "all plans"

[[announcements]]
content = "pro announcement"
target_plan_types = ["pro", "enterprise"]

[[announcements]]
content = "free announcement"
target_plan_types = ["free"]
"""
    assert parse_announcement_tip_toml(toml, "pro") == "pro announcement"
    assert parse_announcement_tip_toml(toml, "free") == "free announcement"
    assert parse_announcement_tip_toml(toml, "plus") == "all plans"
    assert parse_announcement_tip_toml(toml, None) == "all plans"


def announcement_tip_toml_rejects_unknown_target_plan_type() -> None:
    toml = """
[[announcements]]
content = "all plans"

[[announcements]]
content = "typo announcement"
target_plan_types = ["prp"]
"""
    assert parse_announcement_tip_toml(toml, "unknown") == "all plans"


def announcement_tip_toml_matches_target_os() -> None:
    toml = """
[[announcements]]
content = "linux announcement"
target_oses = ["linux"]

[[announcements]]
content = "macos announcement"
target_oses = ["macos"]

[[announcements]]
content = "windows announcement"
target_oses = ["windows"]
"""
    expected = {
        TargetOs.MACOS: "macos announcement",
        TargetOs.WINDOWS: "windows announcement",
    }.get(CURRENT_OS, "linux announcement")
    assert parse_announcement_tip_toml(toml) == expected


def announcement_tip_toml_rejects_unknown_target_os() -> None:
    toml = """
[[announcements]]
content = "all operating systems"

[[announcements]]
content = "typo announcement"
target_oses = ["amiga"]
"""
    assert parse_announcement_tip_toml(toml) == "all operating systems"


def _loads_announcement_toml(text: str) -> Dict[str, Any]:
    if tomllib is not None:
        return tomllib.loads(text)
    return _loads_announcement_toml_fallback(text)


def _loads_announcement_toml_fallback(text: str) -> Dict[str, Any]:
    announcements: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[[announcements]]":
            current = {}
            announcements.append(current)
            continue
        if line.startswith("announcements = [") and line.endswith("]"):
            inner = line[len("announcements = [") : -1].strip()
            if not inner:
                return {"announcements": []}
            entries = re.findall(r"\{([^}]*)\}", inner)
            return {"announcements": [_parse_inline_toml_table(entry) for entry in entries]}
        if current is None or "=" not in line:
            raise ValueError("unsupported announcement TOML shape")
        key, value = [part.strip() for part in line.split("=", 1)]
        current[key] = _parse_toml_scalar_or_list(value)
    return {"announcements": announcements}


def _parse_inline_toml_table(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for item in text.split(","):
        if "=" not in item:
            continue
        key, value = [part.strip() for part in item.split("=", 1)]
        result[key] = _parse_toml_scalar_or_list(value)
    return result


def _parse_toml_scalar_or_list(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_toml_scalar_or_list(part.strip()) for part in inner.split(",")]
    if value.startswith('"') and value.endswith('"'):
        return bytes(value[1:-1], "utf-8").decode("unicode_escape")
    raise ValueError("unsupported announcement TOML scalar")


def _parse_date(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value) if value is not None else None


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("expected string")
    return value


def _optional_str_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if not isinstance(value, list):
        raise TypeError("expected list")
    return [str(item) for item in value]


def _optional_os_list(value: Any) -> Optional[List[TargetOs]]:
    if value is None:
        return None
    if not isinstance(value, list):
        raise TypeError("expected list")
    return [_normalize_os(item) for item in value]


def _normalize_os(value: Any) -> TargetOs:
    if isinstance(value, TargetOs):
        return value
    mapping = {"linux": TargetOs.LINUX, "macos": TargetOs.MACOS, "windows": TargetOs.WINDOWS}
    return mapping.get(str(value).lower(), TargetOs.UNKNOWN)


def _normalize_plan(value: Any) -> Optional[str]:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    raw = getattr(raw, "name", raw)
    text = str(raw).lower()
    valid = {"plus", "enterprise", "pro", "prolite", "pro_lite", "team", "business", "go", "free"}
    if text in {"prolite", "pro_lite"}:
        return "prolite"
    return text if text in valid else "unknown"


def _is_paid_plan(value: Any) -> bool:
    plan = _normalize_plan(value)
    return plan in {"plus", "enterprise", "pro", "prolite", "team", "business"}


def _random_ratio(rng: Any, numerator: int, denominator: int) -> bool:
    if hasattr(rng, "random_ratio"):
        return bool(rng.random_ratio(numerator, denominator))
    return _random_range(rng, 0, denominator) < numerator


def _random_bool(rng: Any, probability: float) -> bool:
    if hasattr(rng, "random_bool"):
        return bool(rng.random_bool(probability))
    return float(rng.random()) < probability


def _random_range(rng: Any, start: int, stop: int) -> int:
    if hasattr(rng, "random_range"):
        return int(rng.random_range(start, stop))
    return int(rng.randrange(start, stop))


__all__ = [
    "ANNOUNCEMENT_TIP",
    "ANNOUNCEMENT_TIP_URL",
    "APP_TOOLTIP",
    "AnnouncementTip",
    "AnnouncementTipDocument",
    "AnnouncementTipRaw",
    "CURRENT_OS",
    "FAST_TOOLTIP",
    "FREE_GO_TOOLTIP",
    "IS_MACOS",
    "IS_WINDOWS",
    "OTHER_TOOLTIP",
    "OTHER_TOOLTIP_NON_MAC",
    "RAW_TOOLTIPS",
    "RUST_MODULE",
    "TargetOs",
    "all_tooltips",
    "announcement_tip_toml_bad_deserialization",
    "announcement_tip_toml_matches_target_os",
    "announcement_tip_toml_matches_target_plan_type",
    "announcement_tip_toml_parse_comments",
    "announcement_tip_toml_picks_last_matching",
    "announcement_tip_toml_picks_no_match",
    "announcement_tip_toml_rejects_unknown_target_os",
    "announcement_tip_toml_rejects_unknown_target_plan_type",
    "blocking_init_announcement_tip",
    "experimental_tooltips",
    "fetch_announcement_tip",
    "get_tooltip",
    "init_announcement_tip_in_thread",
    "paid_app_tooltip",
    "paid_tooltip_pool_rotates_between_promos",
    "paid_tooltip_pool_skips_fast_when_fast_mode_is_enabled",
    "parse_announcement_tip_toml",
    "pick_paid_tooltip",
    "pick_tooltip",
    "prewarm",
    "random_tooltip_is_reproducible_with_seed",
    "random_tooltip_returns_some_tip_when_available",
    "tooltips",
]

