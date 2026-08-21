"""Layered configuration: validation, precedence, and persistence."""
import pytest

from dictatord import config as cfg
from dictatord.errors import Fault


def test_defaults_cover_every_schema_field():
    config = cfg.defaults()
    assert len(config.values) == len(cfg.SCHEMA)
    for field in cfg.SCHEMA:
        assert config[field.path] == field.default


def test_chosen_defaults_are_the_documented_ones():
    """The open decisions from v2.md, settled."""
    config = cfg.defaults()
    assert config["shortcuts.dictate"] == "Super+d"
    assert config["model.name"] == "auto"
    assert config["memory.store_audio"] is False          # audio retention off
    assert config["delivery.default_profile"] == "standard"
    assert config["delivery.mode"] == "paste"
    assert config["shortcuts.hold_threshold_ms"] == 250


def test_unknown_setting_is_rejected():
    with pytest.raises(cfg.ValidationError):
        cfg.parse_value("model.nonsense", "x")


def test_type_and_choice_validation():
    with pytest.raises(cfg.ValidationError):
        cfg.parse_value("model.device", "gpu")
    with pytest.raises(cfg.ValidationError):
        cfg.parse_value("shortcuts.hold_threshold_ms", "not-a-number")
    assert cfg.parse_value("model.device", "cpu") == "cpu"


def test_range_validation():
    with pytest.raises(cfg.ValidationError):
        cfg.parse_value("model.beam_size", "99")
    assert cfg.parse_value("model.beam_size", "3") == 3


@pytest.mark.parametrize("raw,expected", [
    ("true", True), ("yes", True), ("1", True), ("on", True),
    ("false", False), ("no", False), ("0", False), ("off", False),
])
def test_boolean_parsing(raw, expected):
    assert cfg.parse_value("memory.enabled", raw) is expected


def test_list_parsing():
    assert cfg.parse_value("delivery.clipboard_only_apps", "keepassxc, bitwarden") == [
        "keepassxc", "bitwarden"
    ]


def test_environment_overrides_defaults():
    config = cfg.load(environ={"DICTATOR_MODEL_NAME": "small"},
                      use_site=False, use_user=False)
    assert config["model.name"] == "small"
    assert config.source("model.name") == "env"


def test_cli_overrides_environment():
    config = cfg.load(
        environ={"DICTATOR_MODEL_NAME": "small"},
        overrides={"model.name": "medium"},
        use_site=False, use_user=False,
    )
    assert config["model.name"] == "medium"
    assert config.source("model.name") == "cli"


def test_file_layer_is_read_and_recorded(tmp_path):
    path = tmp_path / "extra.toml"
    path.write_text('[model]\nname = "small"\n[audio]\nsample_rate = 48000\n')
    config = cfg.load(extra_files=[path], use_site=False, use_user=False)
    assert config["model.name"] == "small"
    assert config["audio.sample_rate"] == 48000
    assert path in config.loaded_files


def test_invalid_file_reports_a_fault_with_a_remedy(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("this is not toml [[[")
    with pytest.raises(Fault) as excinfo:
        cfg.load(extra_files=[path], use_site=False, use_user=False)
    assert excinfo.value.remedy


def test_unknown_key_in_file_is_reported(tmp_path):
    path = tmp_path / "unknown.toml"
    path.write_text('[model]\nnonsense = 1\n')
    with pytest.raises(Fault, match="unknown setting"):
        cfg.load(extra_files=[path], use_site=False, use_user=False)


def test_save_user_round_trips(tmp_path):
    target = tmp_path / "config.toml"
    cfg.save_user({"model.name": "small"}, path=target)
    config = cfg.load(extra_files=[target], use_site=False, use_user=False)
    assert config["model.name"] == "small"


def test_save_user_omits_defaults(tmp_path):
    """The file records deliberate choices, not a snapshot of everything."""
    target = tmp_path / "config.toml"
    cfg.save_user({"model.name": "small"}, path=target)
    cfg.save_user({"model.name": "auto"}, path=target)
    assert "small" not in target.read_text()


def test_save_user_is_private(tmp_path):
    target = tmp_path / "config.toml"
    cfg.save_user({"model.name": "small"}, path=target)
    assert oct(target.stat().st_mode)[-3:] == "600"


def test_sample_toml_is_valid_and_complete():
    text = cfg.sample_toml()
    for field in cfg.SCHEMA:
        assert field.path.rsplit(".", 1)[-1] in text
    for section in cfg.SECTIONS:
        assert f"[{section}]" in text


def test_section_accessor():
    config = cfg.defaults()
    section = config.section("model")
    assert "name" in section and "device" in section
