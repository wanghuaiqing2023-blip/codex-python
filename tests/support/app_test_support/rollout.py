from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Iterable, Mapping
import uuid


def rollout_path(codex_home: Path, filename_ts: str, thread_id: str) -> Path:
    return (
        codex_home
        / "sessions"
        / filename_ts[0:4]
        / filename_ts[5:7]
        / filename_ts[8:10]
        / f"rollout-{filename_ts}-{thread_id}.jsonl"
    )


def create_fake_rollout(
    codex_home: Path,
    filename_ts: str,
    meta_rfc3339: str,
    preview: str,
    model_provider: str | None = None,
    git_info: Mapping[str, object] | None = None,
) -> str:
    return create_fake_rollout_with_source(
        codex_home,
        filename_ts,
        meta_rfc3339,
        preview,
        model_provider,
        git_info,
        "cli",
    )


def create_fake_rollout_with_source(
    codex_home: Path,
    filename_ts: str,
    meta_rfc3339: str,
    preview: str,
    model_provider: str | None,
    git_info: Mapping[str, object] | None,
    source: str,
) -> str:
    thread_id = str(uuid.uuid4())
    path = rollout_path(codex_home, filename_ts, thread_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": thread_id,
        "forked_from_id": None,
        "timestamp": meta_rfc3339,
        "cwd": "/",
        "originator": "codex",
        "cli_version": "0.0.0",
        "source": source,
        "model_provider": model_provider,
    }
    lines = [
        {"timestamp": meta_rfc3339, "type": "session_meta", "payload": {"meta": meta, "git": git_info}},
        {
            "timestamp": meta_rfc3339,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": preview}],
            },
        },
        {
            "timestamp": meta_rfc3339,
            "type": "event_msg",
            "payload": {"type": "user_message", "message": preview, "kind": "plain"},
        },
    ]
    _write_jsonl(path, lines)
    timestamp = datetime.fromisoformat(meta_rfc3339.replace("Z", "+00:00")).timestamp()
    path.touch()
    import os

    os.utime(path, (timestamp, timestamp))
    return thread_id


def create_fake_rollout_with_token_usage(
    codex_home: Path,
    filename_ts: str,
    meta_rfc3339: str,
    preview: str,
    model_provider: str | None = None,
) -> str:
    thread_id = create_fake_rollout(
        codex_home,
        filename_ts,
        meta_rfc3339,
        preview,
        model_provider,
    )
    path = rollout_path(codex_home, filename_ts, thread_id)
    event = {
        "timestamp": meta_rfc3339,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": 120,
                    "cached_input_tokens": 20,
                    "output_tokens": 30,
                    "reasoning_output_tokens": 10,
                    "total_tokens": 150,
                },
                "last_token_usage": {
                    "input_tokens": 70,
                    "cached_input_tokens": 10,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 5,
                    "total_tokens": 90,
                },
                "model_context_window": 200000,
            },
            "rate_limits": None,
        },
    }
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(event, separators=(",", ":")) + "\n")
    return thread_id


def create_fake_rollout_with_text_elements(
    codex_home: Path,
    filename_ts: str,
    meta_rfc3339: str,
    preview: str,
    text_elements: Iterable[Mapping[str, object]],
    model_provider: str | None = None,
    git_info: Mapping[str, object] | None = None,
) -> str:
    thread_id = create_fake_rollout(
        codex_home,
        filename_ts,
        meta_rfc3339,
        preview,
        model_provider,
        git_info,
    )
    path = rollout_path(codex_home, filename_ts, thread_id)
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records[-1]["payload"]["text_elements"] = list(text_elements)
    records[-1]["payload"]["local_images"] = []
    _write_jsonl(path, records)
    return thread_id


def _write_jsonl(path: Path, records: Iterable[Mapping[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
        newline="\n",
    )
