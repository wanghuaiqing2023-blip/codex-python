"""Search command schema from Rust ``web-search/src/schema.rs``."""

from __future__ import annotations

from typing import Any


def commands_schema() -> dict[str, Any]:
    search_query = _object(
        {
            "q": _string("Search query."),
            "recency": _u64("Whether to filter by recency, as a number of recent days."),
            "domains": _string_array(
                "Whether to filter by a specific list of domains."
            ),
        },
        required=("q",),
    )
    properties = {
        "search_query": _array(
            search_query,
            "Query the internet search engine for a given list of queries.",
        ),
        "image_query": _array(
            search_query,
            "Query the image search engine for a given list of queries.",
        ),
        "open": _array(
            _object(
                {
                    "ref_id": _string("Reference id or URL to open."),
                    "lineno": _u64("Line number to position the page at."),
                },
                required=("ref_id",),
            ),
            "Open pages by reference id or URL.",
        ),
        "click": _array(
            _object(
                {
                    "ref_id": _string("Reference id containing the numbered link."),
                    "id": _u64("Numbered link id to open."),
                },
                required=("ref_id", "id"),
            ),
            "Open links from previously opened pages.",
        ),
        "find": _array(
            _object(
                {
                    "ref_id": _string("Reference id or URL to search within."),
                    "pattern": _string("Text pattern to find."),
                },
                required=("ref_id", "pattern"),
            ),
            "Find text patterns in pages.",
        ),
        "screenshot": _array(
            _object(
                {
                    "ref_id": _string("Reference id or URL to screenshot."),
                    "pageno": _u64("Zero-indexed PDF page number."),
                },
                required=("ref_id", "pageno"),
            ),
            "Take screenshots of PDF pages.",
        ),
        "finance": _array(
            _object(
                {
                    "ticker": _string("Ticker symbol to look up."),
                    "type": _enum(
                        ("equity", "fund", "crypto", "index"),
                        "Asset type to look up.",
                    ),
                    "market": _string(
                        'ISO 3166-1 alpha-3 country code, "OTC", or "" for '
                        "cryptocurrency."
                    ),
                },
                required=("ticker", "type"),
            ),
            "Look up prices for the given stock symbols.",
        ),
        "weather": _array(
            _object(
                {
                    "location": _string('Location in "Country, Area, City" format.'),
                    "start": _string(
                        "Start date in YYYY-MM-DD format. Defaults to today."
                    ),
                    "duration": _u64("Number of days to return. Defaults to 7."),
                },
                required=("location",),
            ),
            "Look up weather forecasts.",
        ),
        "sports": _array(
            _object(
                {
                    "tool": _enum(("sports",), "Tool name for sports requests."),
                    "fn": _enum(
                        ("schedule", "standings"),
                        "Sports function to call.",
                    ),
                    "league": _enum(
                        (
                            "nba",
                            "wnba",
                            "nfl",
                            "nhl",
                            "mlb",
                            "epl",
                            "ncaamb",
                            "ncaawb",
                            "ipl",
                        ),
                        "League to look up.",
                    ),
                    "team": _string(
                        "Team to look up, using the common 3 or 4 letter alias "
                        "used in broadcasts."
                    ),
                    "opponent": _string(
                        "Opponent to use with `team` when narrowing the lookup."
                    ),
                    "date_from": _string("Start date in YYYY-MM-DD format."),
                    "date_to": _string("End date in YYYY-MM-DD format."),
                    "num_games": _u64("Number of games to return."),
                    "locale": _string("Locale for the lookup."),
                },
                required=("fn", "league"),
            ),
            "Look up sports schedules and standings.",
        ),
        "time": _array(
            _object(
                {"utc_offset": _string('UTC offset formatted like "+03:00".')},
                required=("utc_offset",),
            ),
            "Get time for the given UTC offsets.",
        ),
    }
    properties["response_length"] = {
        "type": "string",
        "enum": ["short", "medium", "long"],
        "description": "Set the length of the response to be returned.",
    }
    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }


def _object(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _array(items: dict[str, Any], description: str) -> dict[str, Any]:
    return {"type": "array", "items": items, "description": description}


def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _u64(description: str) -> dict[str, Any]:
    return {
        "type": "integer",
        "format": "uint64",
        "minimum": 0,
        "description": description,
    }


def _string_array(description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string"},
        "description": description,
    }


def _enum(values: tuple[str, ...], description: str) -> dict[str, Any]:
    return {
        "type": "string",
        "enum": list(values),
        "description": description,
    }


__all__ = ["commands_schema"]
