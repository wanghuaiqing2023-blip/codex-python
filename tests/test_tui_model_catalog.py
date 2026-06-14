# Parity source: codex-rs/tui/src/model_catalog.rs

from pycodex.tui.model_catalog import ModelCatalog


def test_model_catalog_new_stores_models_and_lists_clone():
    models = [
        {"id": "gpt-5", "name": "GPT-5"},
        {"id": "gpt-5-mini", "name": "GPT-5 mini"},
    ]

    catalog = ModelCatalog.new(models)
    listed = catalog.try_list_models()

    assert listed == models
    assert listed is not models


def test_model_catalog_is_snapshot_of_constructor_input():
    models = [{"id": "first"}]
    catalog = ModelCatalog.new(models)

    models.append({"id": "later"})

    assert catalog.try_list_models() == [{"id": "first"}]


def test_try_list_models_returns_fresh_deepcopy_each_time():
    catalog = ModelCatalog.new([{"id": "first", "metadata": {"rank": 1}}])

    first = catalog.try_list_models()
    first[0]["metadata"]["rank"] = 99

    assert catalog.try_list_models() == [{"id": "first", "metadata": {"rank": 1}}]


def test_empty_catalog_lists_empty_vec_like_rust():
    assert ModelCatalog.new([]).try_list_models() == []
