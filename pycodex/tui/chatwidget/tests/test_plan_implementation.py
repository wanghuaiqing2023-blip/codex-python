from pycodex.tui.chatwidget.plan_implementation import (
    PLAN_IMPLEMENTATION_CLEAR_CONTEXT,
    PLAN_IMPLEMENTATION_CLEAR_CONTEXT_PREFIX,
    PLAN_IMPLEMENTATION_CODING_MESSAGE,
    PLAN_IMPLEMENTATION_DEFAULT_UNAVAILABLE,
    PLAN_IMPLEMENTATION_NO,
    PLAN_IMPLEMENTATION_NO_APPROVED_PLAN,
    PLAN_IMPLEMENTATION_TITLE,
    PLAN_IMPLEMENTATION_YES,
    selection_view_params,
)


def test_selection_view_params_builds_enabled_actions_with_plan() -> None:
    params = selection_view_params("default-mask", "- step one", "89% used")

    assert params.title == PLAN_IMPLEMENTATION_TITLE
    assert params.subtitle is None
    assert [item.name for item in params.items] == [
        PLAN_IMPLEMENTATION_YES,
        PLAN_IMPLEMENTATION_CLEAR_CONTEXT,
        PLAN_IMPLEMENTATION_NO,
    ]

    implement = params.items[0]
    assert implement.description == "Switch to Default and start coding."
    assert implement.disabled_reason is None
    assert implement.actions[0].event == "SubmitUserMessageWithMode"
    assert implement.actions[0].payload == {
        "text": PLAN_IMPLEMENTATION_CODING_MESSAGE,
        "collaboration_mode": "default-mask",
    }

    clear = params.items[1]
    assert clear.description == "Fresh thread. Context: 89% used."
    assert clear.disabled_reason is None
    assert clear.actions[0].event == "ClearUiAndSubmitUserMessage"
    assert clear.actions[0].payload["text"] == f"{PLAN_IMPLEMENTATION_CLEAR_CONTEXT_PREFIX}\n\n- step one"

    stay = params.items[2]
    assert stay.description == "Continue planning with the model."
    assert stay.actions == ()


def test_default_mask_absent_disables_implementation_choices() -> None:
    params = selection_view_params(None, "plan", None)

    assert params.items[0].disabled_reason == PLAN_IMPLEMENTATION_DEFAULT_UNAVAILABLE
    assert params.items[0].actions == ()
    assert params.items[1].disabled_reason == PLAN_IMPLEMENTATION_DEFAULT_UNAVAILABLE
    assert params.items[1].description == "Fresh thread with this plan."
    assert params.items[1].actions == ()


def test_clear_context_requires_non_empty_approved_plan() -> None:
    for plan in (None, "", "   \n"):
        params = selection_view_params("default-mask", plan, None)
        assert params.items[1].disabled_reason == PLAN_IMPLEMENTATION_NO_APPROVED_PLAN
        assert params.items[1].actions == ()
