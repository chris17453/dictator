"""Chord parsing, normalisation, and per-backend rendering."""
import pytest

from dictatord.platform.chords import Chord, ChordError, parse_optional, validate_usable


@pytest.mark.parametrize("text,expected", [
    ("Super+d", "Super+d"),
    ("<Super>d", "Super+d"),
    ("super+D", "Super+d"),
    ("ctrl+shift+v", "Ctrl+Shift+v"),
    ("CTRL+ALT+SHIFT+SUPER+k", "Ctrl+Alt+Shift+Super+k"),
    ("Super+Escape", "Super+Escape"),
    ("Super+esc", "Super+Escape"),
    ("Ctrl+enter", "Ctrl+Return"),
    ("Super+f5", "Super+F5"),
    ("Alt+pageup", "Alt+Prior"),
])
def test_parse_normalises(text, expected):
    assert str(Chord.parse(text)) == expected


def test_modifier_order_is_canonical_regardless_of_input():
    assert str(Chord.parse("Super+Shift+Ctrl+a")) == str(Chord.parse("Ctrl+Shift+Super+a"))


def test_renderings():
    chord = Chord.parse("Super+Shift+d")
    assert chord.to_portal() == "SHIFT+SUPER+d"
    assert chord.to_gsettings() == "<Shift><Super>d"


def test_aliases_are_equivalent():
    assert Chord.parse("win+d") == Chord.parse("Super+d")
    assert Chord.parse("control+c") == Chord.parse("Ctrl+c")


@pytest.mark.parametrize("bad", ["", "   ", "Super", "Ctrl+Shift", "Super+a+b", "Super+f99"])
def test_rejects_unusable_chords(bad):
    with pytest.raises(ChordError):
        Chord.parse(bad)


@pytest.mark.parametrize("bad,reason", [("d", "modifier"), ("Shift+a", "Shift")])
def test_validate_usable_rejects_typing_stealers(bad, reason):
    with pytest.raises(ChordError, match=reason):
        validate_usable(Chord.parse(bad))


def test_validate_accepts_real_chords():
    for good in ("Super+d", "Ctrl+Shift+v", "Alt+space"):
        validate_usable(Chord.parse(good))


def test_parse_optional_treats_empty_as_unbound():
    assert parse_optional("") is None
    assert parse_optional(None) is None
    assert parse_optional("  ") is None
    assert str(parse_optional("Super+d")) == "Super+d"


def test_chords_are_hashable_and_comparable():
    assert Chord.parse("Super+d") == Chord.parse("super+D")
    assert len({Chord.parse("Super+d"), Chord.parse("<Super>d")}) == 1
