from enum import Enum

from pycodex.tui.bottom_pane.mentions_v2.search_mode import SearchMode
from pycodex.tui.bottom_pane.mentions_v2.search_mode import accepts
from pycodex.tui.bottom_pane.mentions_v2.search_mode import label
from pycodex.tui.bottom_pane.mentions_v2.search_mode import next
from pycodex.tui.bottom_pane.mentions_v2.search_mode import previous


class MentionType(Enum):
    PLUGIN = "Plugin"
    SKILL = "Skill"
    FILE = "File"
    DIRECTORY = "Directory"


def test_previous_cycles_results_filesystem_tools_like_rust():
    assert SearchMode.RESULTS.previous() is SearchMode.TOOLS
    assert SearchMode.FILESYSTEM_ONLY.previous() is SearchMode.RESULTS
    assert SearchMode.TOOLS.previous() is SearchMode.FILESYSTEM_ONLY
    assert previous(SearchMode.RESULTS) is SearchMode.TOOLS


def test_next_cycles_results_filesystem_tools_like_rust():
    assert SearchMode.RESULTS.next() is SearchMode.FILESYSTEM_ONLY
    assert SearchMode.FILESYSTEM_ONLY.next() is SearchMode.TOOLS
    assert SearchMode.TOOLS.next() is SearchMode.RESULTS
    assert next(SearchMode.TOOLS) is SearchMode.RESULTS


def test_accepts_all_results_mode():
    for mention_type in MentionType:
        assert SearchMode.RESULTS.accepts(mention_type)


def test_filesystem_only_accepts_files_and_directories_only():
    assert SearchMode.FILESYSTEM_ONLY.accepts(MentionType.FILE)
    assert SearchMode.FILESYSTEM_ONLY.accepts(MentionType.DIRECTORY)
    assert not SearchMode.FILESYSTEM_ONLY.accepts(MentionType.PLUGIN)
    assert not SearchMode.FILESYSTEM_ONLY.accepts(MentionType.SKILL)
    assert accepts(SearchMode.FILESYSTEM_ONLY, "dir")


def test_tools_accepts_plugins_and_skills_only():
    assert SearchMode.TOOLS.accepts(MentionType.PLUGIN)
    assert SearchMode.TOOLS.accepts(MentionType.SKILL)
    assert not SearchMode.TOOLS.accepts(MentionType.FILE)
    assert not SearchMode.TOOLS.accepts(MentionType.DIRECTORY)


def test_labels_match_rust_visible_copy():
    assert SearchMode.RESULTS.label() == "All Results"
    assert SearchMode.FILESYSTEM_ONLY.label() == "Filesystem Only"
    assert SearchMode.TOOLS.label() == "Plugins"
    assert label(SearchMode.TOOLS) == "Plugins"
