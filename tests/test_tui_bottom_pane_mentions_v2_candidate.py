from pycodex.tui.bottom_pane.mentions_v2.candidate import (
    TAG_WIDTH,
    Candidate,
    MentionType,
    Selection,
    SemanticSpan,
)


def test_tag_width_matches_plugin_label_width():
    assert TAG_WIDTH == len("Plugin")


def test_mention_type_is_filesystem_matches_rust():
    assert not MentionType.PLUGIN.is_filesystem()
    assert not MentionType.SKILL.is_filesystem()
    assert MentionType.FILE.is_filesystem()
    assert MentionType.DIRECTORY.is_filesystem()


def test_mention_type_labels_and_padded_spans_match_rust_visible_tags():
    assert MentionType.PLUGIN.label() == "Plugin"
    assert MentionType.SKILL.label() == "Skill"
    assert MentionType.FILE.label() == "File"
    assert MentionType.DIRECTORY.label() == "Dir"

    assert MentionType.PLUGIN.span().content == "Plugin"
    assert MentionType.SKILL.span().content == "Skill "
    assert MentionType.FILE.span().content == "File  "
    assert MentionType.DIRECTORY.span().content == "Dir   "


def test_mention_type_span_applies_semantic_styles():
    assert MentionType.PLUGIN.span(("base",)).style == ("base", "magenta")
    assert MentionType.SKILL.span().style == ("dim",)
    assert MentionType.FILE.span().style == ("cyan",)
    assert MentionType.DIRECTORY.span("base").style == ("base",)
    assert isinstance(MentionType.FILE.span(), SemanticSpan)


def test_selection_file_and_tool_variants_preserve_fields():
    file_selection = Selection.File("src/main.rs")
    assert file_selection.kind == "File"
    assert str(file_selection.file).endswith("src/main.rs")

    tool_selection = Selection.Tool("@skill", path="skills/demo")
    assert tool_selection.kind == "Tool"
    assert tool_selection.insert_text == "@skill"
    assert tool_selection.path == "skills/demo"


def test_candidate_to_result_clones_candidate_fields_and_match_indices():
    candidate = Candidate(
        display_name="demo.py",
        description="Python file",
        search_terms=["demo", "python"],
        mention_type=MentionType.FILE,
        selection=Selection.File("demo.py"),
    )
    match_indices = [0, 1, 4]

    result = candidate.to_result(match_indices, 42)
    match_indices.append(99)

    assert result.display_name == "demo.py"
    assert result.description == "Python file"
    assert result.mention_type is MentionType.FILE
    assert result.selection == Selection.File("demo.py")
    assert result.match_indices == [0, 1, 4]
    assert result.score == 42
