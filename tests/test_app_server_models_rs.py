import asyncio

from pycodex.app_server.models import (
    REFRESH_STRATEGY_ONLINE_IF_UNCACHED,
    model_from_preset,
    reasoning_efforts_from_preset,
    supported_models,
    supported_models_from_presets,
)
from pycodex.protocol import InputModality, ReasoningEffort
from pycodex.protocol.openai_models import (
    ModelAvailabilityNux,
    ModelPreset,
    ModelServiceTier,
    ModelUpgrade,
    ReasoningEffortPreset,
)


def _preset(*, show_in_picker: bool = True, id: str = "codex-model") -> ModelPreset:
    return ModelPreset(
        id=id,
        model="gpt-codex",
        display_name="Codex Model",
        description="For agentic coding",
        default_reasoning_effort=ReasoningEffort.MEDIUM,
        supported_reasoning_efforts=(
            ReasoningEffortPreset(ReasoningEffort.LOW, "Low effort"),
            ReasoningEffortPreset(ReasoningEffort.HIGH, "High effort"),
        ),
        is_default=True,
        upgrade=ModelUpgrade(
            id="codex-model-next",
            migration_config_key="codex-model",
            upgrade_copy="Try the next model",
            model_link="https://example.test/model",
            migration_markdown="## Migration",
        ),
        show_in_picker=show_in_picker,
        availability_nux=ModelAvailabilityNux("Available now"),
        supported_in_api=True,
        supports_personality=True,
        additional_speed_tiers=("fast",),
        service_tiers=(ModelServiceTier("priority", "Priority", "Faster responses"),),
        default_service_tier="priority",
        input_modalities=(InputModality.TEXT,),
    )


def test_reasoning_efforts_from_preset_preserves_effort_and_description() -> None:
    # Rust: codex-app-server/src/models.rs reasoning_efforts_from_preset maps effort + description.
    efforts = reasoning_efforts_from_preset(
        (
            ReasoningEffortPreset(ReasoningEffort.LOW, "Low effort"),
            ReasoningEffortPreset(ReasoningEffort.HIGH, "High effort"),
        )
    )

    assert [item.to_camel_mapping() for item in efforts] == [
        {"reasoningEffort": "low", "description": "Low effort"},
        {"reasoningEffort": "high", "description": "High effort"},
    ]


def test_model_from_preset_projects_all_app_server_fields() -> None:
    # Rust: model_from_preset copies ModelPreset fields into app-server protocol Model.
    model = model_from_preset(_preset())

    assert model.to_camel_mapping() == {
        "id": "codex-model",
        "model": "gpt-codex",
        "upgrade": "codex-model-next",
        "upgradeInfo": {
            "model": "codex-model-next",
            "upgradeCopy": "Try the next model",
            "modelLink": "https://example.test/model",
            "migrationMarkdown": "## Migration",
        },
        "availabilityNux": {"message": "Available now"},
        "displayName": "Codex Model",
        "description": "For agentic coding",
        "hidden": False,
        "supportedReasoningEfforts": [
            {"reasoningEffort": "low", "description": "Low effort"},
            {"reasoningEffort": "high", "description": "High effort"},
        ],
        "defaultReasoningEffort": "medium",
        "inputModalities": ["text"],
        "supportsPersonality": True,
        "additionalSpeedTiers": ["fast"],
        "serviceTiers": [{"id": "priority", "name": "Priority", "description": "Faster responses"}],
        "defaultServiceTier": "priority",
        "isDefault": True,
    }


def test_model_from_preset_marks_hidden_without_upgrade_or_nux() -> None:
    # Rust: hidden is the inverse of show_in_picker and optional upgrade/nux fields stay absent.
    preset = _preset(show_in_picker=False, id="hidden")
    preset.upgrade = None
    preset.availability_nux = None

    model = model_from_preset(preset)

    assert model.hidden is True
    assert model.upgrade is None
    assert model.upgrade_info is None
    assert model.availability_nux is None


def test_supported_models_from_presets_filters_hidden_unless_requested() -> None:
    # Rust: supported_models filters by show_in_picker unless include_hidden is true.
    visible = _preset(show_in_picker=True, id="visible")
    hidden = _preset(show_in_picker=False, id="hidden")

    assert [model.id for model in supported_models_from_presets((hidden, visible), include_hidden=False)] == ["visible"]
    assert [model.id for model in supported_models_from_presets((hidden, visible), include_hidden=True)] == [
        "hidden",
        "visible",
    ]


def test_supported_models_requests_online_if_uncached_strategy() -> None:
    # Rust: supported_models calls ThreadManager::list_models(RefreshStrategy::OnlineIfUncached).
    class FakeThreadManager:
        def __init__(self) -> None:
            self.strategy = None

        async def list_models(self, strategy: str):
            self.strategy = strategy
            return [_preset()]

    manager = FakeThreadManager()
    models = asyncio.run(supported_models(manager, include_hidden=False))

    assert manager.strategy == REFRESH_STRATEGY_ONLINE_IF_UNCACHED
    assert [model.id for model in models] == ["codex-model"]
