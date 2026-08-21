"""Application identity, which GNOME requires before it will bind shortcuts."""
import pytest

from dictatord.platform import appid


@pytest.mark.parametrize("unit,expected", [
    ("app-com.watkinslabs.Dictator.service", "com.watkinslabs.Dictator"),
    ("app-com.watkinslabs.Dictator-1234.scope", "com.watkinslabs.Dictator"),
    ("app-gnome-org.gnome.Nautilus-4567.scope", "org.gnome.Nautilus"),
    ("app-com.example.Thing@1.service", "com.example.Thing"),
])
def test_recognised_unit_shapes(monkeypatch, unit, expected):
    monkeypatch.setattr(appid, "_cgroup_unit", lambda pid=None: unit)
    appid.app_id.cache_clear()
    assert appid.app_id() == expected


@pytest.mark.parametrize("unit", [
    "",
    "user@1000.service",
    "session-2.scope",
    "app-nodots-1234.scope",   # no dot: not a desktop id
])
def test_unidentifiable_units(monkeypatch, unit):
    monkeypatch.setattr(appid, "_cgroup_unit", lambda pid=None: unit)
    appid.app_id.cache_clear()
    assert appid.app_id() == ""


def test_systemd_escaping_is_reversed(monkeypatch):
    monkeypatch.setattr(
        appid, "_cgroup_unit", lambda pid=None: r"app-com.example\x2dApp.service"
    )
    appid.app_id.cache_clear()
    assert appid.app_id() == "com.example-App"


def test_explain_is_actionable(monkeypatch):
    monkeypatch.setattr(appid, "_cgroup_unit", lambda pid=None: "")
    appid.app_id.cache_clear()
    assert "GNOME" in appid.explain()
    assert not appid.is_identified()
