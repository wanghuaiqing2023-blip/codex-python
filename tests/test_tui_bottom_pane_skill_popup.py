from pycodex.tui.bottom_pane.popup_consts import MAX_POPUP_ROWS
from pycodex.tui.bottom_pane.skill_popup import MentionItem
from pycodex.tui.bottom_pane.skill_popup import SkillPopup
from pycodex.tui.bottom_pane.skill_popup import mention_item
from pycodex.tui.bottom_pane.skill_popup import named_mention_item
from pycodex.tui.bottom_pane.skill_popup import plugin_mention_item
from pycodex.tui.bottom_pane.skill_popup import skill_popup_hint_line


def test_filtered_mentions_preserve_results_beyond_popup_height():
    popup = SkillPopup.new(mention_item(idx) for idx in range(MAX_POPUP_ROWS + 2))

    filtered_names = [popup.mentions[idx].display_name for idx in popup.filtered_items()]

    assert filtered_names == [f"Mention {idx:02}" for idx in range(MAX_POPUP_ROWS + 2)]
    assert popup.calculate_required_height(72) == MAX_POPUP_ROWS + 2


def test_scrolling_mentions_shifts_rendered_window_and_selection():
    popup = SkillPopup.new(mention_item(idx) for idx in range(MAX_POPUP_ROWS + 2))

    for _ in range(MAX_POPUP_ROWS + 1):
        popup.move_down()

    assert popup.selected_idx == MAX_POPUP_ROWS + 1
    assert popup.scroll_top == 2
    assert popup.selected_mention().display_name == f"Mention {MAX_POPUP_ROWS + 1:02}"
    rendered = popup.render_ref((0, 0, 72, popup.calculate_required_height(72)))
    assert rendered[0].text.startswith("  Mention 02")


def test_display_name_match_sorting_beats_worse_secondary_search_term_matches():
    popup = SkillPopup.new(
        [
            named_mention_item("pr-review-triage", ["pr-review-triage"]),
            named_mention_item("prd", ["prd"]),
            named_mention_item("PR Babysitter", ["babysit-pr", "PR Babysitter"]),
            named_mention_item("Plugin Creator", ["plugin-creator", "Plugin Creator"]),
            named_mention_item("Logging Best Practices", ["logging-best-practices", "Logging Best Practices"]),
        ]
    )
    popup.set_query("pr")

    filtered_names = [popup.mentions[idx].display_name for idx in popup.filtered_items()]

    assert filtered_names == [
        "PR Babysitter",
        "pr-review-triage",
        "prd",
        "Plugin Creator",
        "Logging Best Practices",
    ]


def test_query_match_score_sorts_before_plugin_rank_bias():
    popup = SkillPopup.new(
        [
            plugin_mention_item("GitHub", ["github", "pull requests", "pr"]),
            named_mention_item("pr-review-triage", ["pr-review-triage"]),
            named_mention_item("prd", ["prd"]),
            named_mention_item("Plugin Creator", ["plugin-creator", "Plugin Creator"]),
            named_mention_item("Logging Best Practices", ["logging-best-practices", "Logging Best Practices"]),
            named_mention_item("PR Babysitter", ["babysit-pr", "PR Babysitter"]),
        ]
    )
    popup.set_query("pr")

    filtered = [(popup.mentions[idx].display_name, popup.mentions[idx].category_tag) for idx in popup.filtered_items()]

    assert filtered == [
        ("PR Babysitter", "[Skill]"),
        ("pr-review-triage", "[Skill]"),
        ("prd", "[Skill]"),
        ("Plugin Creator", "[Skill]"),
        ("Logging Best Practices", "[Skill]"),
        ("GitHub", "[Plugin]"),
    ]


def test_rows_description_composition_and_truncation():
    popup = SkillPopup.new(
        [
            MentionItem(
                display_name="A Very Long Skill Mention Name That Should Truncate",
                description="Useful skill",
                insert_text="$skill",
                search_terms=[],
                category_tag="[Skill]",
                sort_rank=1,
            )
        ]
    )

    row = popup.rows_from_matches(popup.filtered())[0]

    assert row.name.endswith("…")
    assert row.description == "[Skill] Useful skill"
    assert row.selected is True


def test_set_mentions_query_clamp_empty_and_hint_line():
    popup = SkillPopup.new([])

    assert popup.selected_mention() is None
    assert popup.calculate_required_height(72) == 3
    assert popup.render_ref((0, 0, 40, 3))[0].text == "no matches"

    popup.set_mentions([mention_item(0)])
    assert popup.selected_mention().display_name == "Mention 00"
    popup.set_query("zzz")
    assert popup.selected_mention() is None
    assert skill_popup_hint_line() == "Press Enter to insert or Esc to close"
