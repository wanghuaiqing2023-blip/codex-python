from __future__ import annotations

from pycodex.ext.memories.metrics import scope_from_optional_path
from pycodex.ext.memories.metrics import scope_from_path
from pycodex.ext.memories.metrics import status_tag
from pycodex.ext.memories.metrics import truncated_tag


def test_memory_scope_classification_matches_rust() -> None:
    assert scope_from_path("") == "root"
    assert scope_from_path("./MEMORY.md") == "memory_md"
    assert scope_from_path("/memory_summary.md/") == "memory_summary"
    assert scope_from_path("rollout_summaries/one.jsonl") == "rollout_summaries"
    assert scope_from_path("skills/example/SKILL.md") == "skills"
    assert scope_from_path("extensions/ad_hoc/notes/note.md") == "ad_hoc_notes"
    assert scope_from_path("elsewhere") == "other"
    assert scope_from_optional_path(None, "default") == "default"


def test_metric_status_tags_match_rust() -> None:
    assert truncated_tag(True) == "true"
    assert truncated_tag(False) == "false"
    assert truncated_tag(None) == "unknown"
    assert status_tag(True) == "succeeded"
    assert status_tag(False) == "failed"
