"""Deferred tool-search handler ported from Codex core.

The Rust implementation uses the ``bm25`` crate. This Python port keeps the
runtime dependency-free by implementing the small Okapi BM25 slice needed for
``core/src/tools/handlers/tool_search.rs``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from pycodex.core.tool_context import ToolPayload, ToolSearchOutput
from pycodex.core.tool_search_entry import (
    ToolSearchEntry,
    ToolSearchInfo,
    ToolSearchSourceInfo,
    coalesce_loadable_tool_specs,
)
from pycodex.protocol import ToolName

JsonValue = Any

TOOL_SEARCH_TOOL_NAME = "tool_search"
TOOL_SEARCH_DEFAULT_LIMIT = 8


def create_tool_search_tool(
    searchable_sources: tuple[ToolSearchSourceInfo, ...] | list[ToolSearchSourceInfo],
    default_limit: int = TOOL_SEARCH_DEFAULT_LIMIT,
) -> dict[str, JsonValue]:
    source_descriptions = _render_source_descriptions(searchable_sources)
    description = (
        "# Tool discovery\n\n"
        "Searches over deferred tool metadata with BM25 and exposes matching tools for the next model call.\n\n"
        "You have access to tools from the following sources:\n"
        f"{source_descriptions}\n"
        "Some of the tools may not have been provided to you upfront, and you should use this tool "
        f"(`{TOOL_SEARCH_TOOL_NAME}`) to search for the required tools. For MCP tool discovery, always use "
        f"`{TOOL_SEARCH_TOOL_NAME}` instead of `list_mcp_resources` or `list_mcp_resource_templates`."
    )
    return {
        "type": "tool_search",
        "execution": "client",
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "number",
                    "description": f"Maximum number of tools to return (defaults to {default_limit}).",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for deferred tools.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }


@dataclass(frozen=True)
class _IndexedDocument:
    index: int
    tokens: tuple[str, ...]
    counts: Counter[str]


class _Bm25Index:
    def __init__(self, documents: tuple[str, ...]) -> None:
        indexed = []
        document_frequency: Counter[str] = Counter()
        for index, text in enumerate(documents):
            tokens = tuple(_tokenize(text))
            counts = Counter(tokens)
            indexed.append(_IndexedDocument(index, tokens, counts))
            document_frequency.update(counts.keys())

        self._documents = tuple(indexed)
        self._document_frequency = document_frequency
        self._average_length = (
            sum(len(document.tokens) for document in self._documents) / len(self._documents)
            if self._documents
            else 0.0
        )

    def search(self, query: str, limit: int) -> tuple[int, ...]:
        query_terms = tuple(dict.fromkeys(_tokenize(query)))
        if not query_terms or limit <= 0:
            return ()

        scored: list[tuple[float, int]] = []
        for document in self._documents:
            score = self._score_document(query_terms, document)
            if score > 0:
                scored.append((score, document.index))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(index for _, index in scored[:limit])

    def _score_document(self, query_terms: tuple[str, ...], document: _IndexedDocument) -> float:
        if not document.tokens:
            return 0.0

        total_documents = len(self._documents)
        k1 = 1.5
        b = 0.75
        score = 0.0
        for term in query_terms:
            frequency = document.counts.get(term, 0)
            if frequency == 0:
                continue
            document_frequency = self._document_frequency[term]
            idf = math.log(1.0 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5))
            denominator = frequency + k1 * (
                1.0 - b + b * (len(document.tokens) / (self._average_length or 1.0))
            )
            score += idf * (frequency * (k1 + 1.0)) / denominator
        return score


class ToolSearchHandler:
    def __init__(self, search_infos: tuple[ToolSearchInfo, ...] | list[ToolSearchInfo]) -> None:
        self.entries = tuple(search_info.entry for search_info in search_infos)
        self.search_source_infos = tuple(
            search_info.source_info
            for search_info in search_infos
            if search_info.source_info is not None
        )
        self._search_index = _Bm25Index(tuple(entry.search_text for entry in self.entries))

    def tool_name(self) -> ToolName:
        return ToolName.plain(TOOL_SEARCH_TOOL_NAME)

    def spec(self) -> dict[str, JsonValue]:
        return create_tool_search_tool(self.search_source_infos, TOOL_SEARCH_DEFAULT_LIMIT)

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def matches_kind(self, payload: ToolPayload) -> bool:
        return payload.type == "tool_search"

    def handle(self, invocation_or_payload: Any) -> ToolSearchOutput:
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        if not isinstance(payload, ToolPayload) or payload.type != "tool_search":
            raise RuntimeError(f"{TOOL_SEARCH_TOOL_NAME} handler received unsupported payload")

        arguments = payload.search_arguments
        if arguments is None:
            raise RuntimeError(f"{TOOL_SEARCH_TOOL_NAME} handler received unsupported payload")

        query = arguments.query.strip()
        if query == "":
            raise ValueError("query must not be empty")

        limit = TOOL_SEARCH_DEFAULT_LIMIT if arguments.limit is None else arguments.limit
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        if not self.entries:
            return ToolSearchOutput(())

        return ToolSearchOutput(self.search(query, limit))

    def search(self, query: str, limit: int = TOOL_SEARCH_DEFAULT_LIMIT) -> tuple[JsonValue, ...]:
        indexes = self._search_index.search(query, limit)
        return self.search_output_tools(tuple(self.entries[index] for index in indexes))

    def search_output_tools(self, results: tuple[ToolSearchEntry, ...] | list[ToolSearchEntry]) -> tuple[JsonValue, ...]:
        return coalesce_loadable_tool_specs(entry.output for entry in results)


def _render_source_descriptions(sources: tuple[ToolSearchSourceInfo, ...] | list[ToolSearchSourceInfo]) -> str:
    descriptions: dict[str, str | None] = {}
    for source in sources:
        if source.name in descriptions:
            if descriptions[source.name] is None:
                descriptions[source.name] = source.description
        else:
            descriptions[source.name] = source.description

    if not descriptions:
        return "None currently enabled."

    lines = []
    for name in sorted(descriptions):
        description = descriptions[name]
        lines.append(f"- {name}: {description}" if description is not None else f"- {name}")
    return "\n".join(lines)


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in re.findall(r"[A-Za-z0-9_]+", text))


__all__ = [
    "TOOL_SEARCH_DEFAULT_LIMIT",
    "TOOL_SEARCH_TOOL_NAME",
    "ToolSearchHandler",
    "create_tool_search_tool",
]
