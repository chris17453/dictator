"""Settings that were renamed or retired must not break an upgrade."""
from dictatord import config as cfg


def test_retired_settings_are_dropped_with_an_explanation():
    flat, notes = cfg.migrate({"ui.theme": "dark", "model.name": "base"})
    assert "ui.theme" not in flat
    assert flat["model.name"] == "base"
    assert any("ui.theme" in note for note in notes)


def test_v1_whisper_settings_are_explained():
    _flat, notes = cfg.migrate({"whisper.model_size": "small"})
    assert any("model.name" in note for note in notes)


def test_unknown_but_current_settings_pass_through():
    flat, notes = cfg.migrate({"model.name": "small"})
    assert flat == {"model.name": "small"}
    assert notes == []


def test_a_stale_config_file_still_loads(tmp_path):
    """An upgrade must produce a working daemon, not a refusal to start."""
    path = tmp_path / "old.toml"
    path.write_text('[ui]\ntheme = "dark"\n[model]\nname = "small"\n')
    config = cfg.load(extra_files=[path], use_site=False, use_user=False)
    assert config["model.name"] == "small"
    assert config.migrations, "the user should be told what was dropped"


def test_schema_version_is_declared():
    assert isinstance(cfg.SCHEMA_VERSION, int) and cfg.SCHEMA_VERSION >= 1
