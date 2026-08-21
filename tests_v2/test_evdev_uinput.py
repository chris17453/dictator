"""The prompt-free backends: key mapping and chord matching.

The mapping logic is pure and testable without hardware. The parts that need a
real device are marked and skipped where none is available.
"""
import os

import pytest

evdev = pytest.importorskip("evdev")

from dictatord.errors import Fault
from dictatord.platform import evdev_shortcuts as ev
from dictatord.platform import uinput_injection as ui
from dictatord.platform.chords import Chord


# -- key mapping -----------------------------------------------------------


@pytest.mark.parametrize("key,expected", [
    ("d", "KEY_D"),
    ("a", "KEY_A"),
    ("Escape", "KEY_ESC"),
    ("space", "KEY_SPACE"),
    ("Return", "KEY_ENTER"),
    ("F5", "KEY_F5"),
    ("comma", "KEY_COMMA"),
    ("period", "KEY_DOT"),
    ("Prior", "KEY_PAGEUP"),
])
def test_chord_keys_map_to_kernel_codes(key, expected):
    assert ev._code_for(evdev, key) == int(getattr(evdev.ecodes, expected))


def test_an_unmappable_key_is_a_fault_with_a_remedy():
    with pytest.raises(Fault) as excinfo:
        ev._code_for(evdev, "NoSuchKey")
    assert "dictator keys set" in excinfo.value.remedy


def test_every_chord_modifier_has_left_and_right_variants():
    for name, keys in ev._MODIFIER_KEYS.items():
        assert len(keys) == 2, f"{name} should accept either side of the keyboard"
        for key in keys:
            assert hasattr(evdev.ecodes, key)


# -- chord matching --------------------------------------------------------


class FakeBackend(ev.EvdevShortcuts):
    """Drives _handle() directly, with no devices open."""

    def __init__(self):
        super().__init__()
        self.emitted = []

    def _emit(self, shortcut_id, which):
        self.emitted.append((shortcut_id, which.value))


def _event(code, value):
    return evdev.InputEvent(0, 0, evdev.ecodes.EV_KEY, int(code), int(value))


@pytest.fixture
def backend():
    instance = FakeBackend()
    instance._targets = {
        "dictate": (
            int(evdev.ecodes.KEY_D),
            [(int(evdev.ecodes.KEY_LEFTMETA), int(evdev.ecodes.KEY_RIGHTMETA))],
        )
    }
    return instance


def test_the_chord_fires_only_with_its_modifier(backend):
    backend._handle(_event(evdev.ecodes.KEY_D, 1))
    assert backend.emitted == [], "the bare key must not fire"

    backend._handle(_event(evdev.ecodes.KEY_LEFTMETA, 1))
    backend._handle(_event(evdev.ecodes.KEY_D, 1))
    assert backend.emitted == [("dictate", "pressed")]


def test_release_is_reported(backend):
    backend._handle(_event(evdev.ecodes.KEY_LEFTMETA, 1))
    backend._handle(_event(evdev.ecodes.KEY_D, 1))
    backend._handle(_event(evdev.ecodes.KEY_D, 0))
    assert backend.emitted == [("dictate", "pressed"), ("dictate", "released")]


def test_either_side_of_the_modifier_works(backend):
    backend._handle(_event(evdev.ecodes.KEY_RIGHTMETA, 1))
    backend._handle(_event(evdev.ecodes.KEY_D, 1))
    assert backend.emitted == [("dictate", "pressed")]


def test_autorepeat_does_not_refire(backend):
    """A held chord must not restart the session over and over."""
    backend._handle(_event(evdev.ecodes.KEY_LEFTMETA, 1))
    backend._handle(_event(evdev.ecodes.KEY_D, 1))
    for _ in range(20):
        backend._handle(_event(evdev.ecodes.KEY_D, 2))
    assert backend.emitted.count(("dictate", "pressed")) == 1


def test_unrelated_keys_are_ignored(backend):
    for code in (evdev.ecodes.KEY_A, evdev.ecodes.KEY_ENTER, evdev.ecodes.KEY_F1):
        backend._handle(_event(code, 1))
        backend._handle(_event(code, 0))
    assert backend.emitted == []


def test_modifier_released_first_still_ends_cleanly(backend):
    backend._handle(_event(evdev.ecodes.KEY_LEFTMETA, 1))
    backend._handle(_event(evdev.ecodes.KEY_D, 1))
    backend._handle(_event(evdev.ecodes.KEY_LEFTMETA, 0))
    backend._handle(_event(evdev.ecodes.KEY_D, 0))
    assert backend.emitted[-1] == ("dictate", "released")


# -- uinput mapping --------------------------------------------------------


def test_printable_ascii_is_typeable():
    for char in "abcXYZ019 .,/;'[]-=":
        assert char in ui._CHARS, f"{char!r} should be typeable"


def test_shifted_symbols_carry_the_shift_flag():
    assert ui._CHARS["A"] == ("KEY_A", True)
    assert ui._CHARS["a"] == ("KEY_A", False)
    assert ui._CHARS["!"] == ("KEY_1", True)
    assert ui._CHARS["?"] == ("KEY_SLASH", True)


def test_every_mapped_key_exists_in_the_kernel():
    for name, _shift in ui._CHARS.values():
        assert hasattr(evdev.ecodes, name), f"{name} is not a kernel key"


def test_characters_off_the_layout_are_simply_absent():
    """They cannot be typed; paste delivery has no such limit."""
    for char in "€漢🙂":
        assert char not in ui._CHARS


# -- probes ----------------------------------------------------------------


async def test_probe_reports_a_reason_when_unavailable(monkeypatch):
    monkeypatch.setattr(ev, "keyboards", lambda _evdev: [])
    capability = await ev.EvdevShortcuts.probe()
    assert not capability.available
    assert "permission" in capability.reason


async def test_probes_state_their_trust_model():
    """doctor reports this; it must never be silently omitted."""
    for probe in (ev.EvdevShortcuts.probe, ui.UinputInjection.probe):
        capability = await probe()
        if capability.available:
            assert capability.trust
            assert capability.requires_consent is False


@pytest.mark.skipif(not os.access("/dev/uinput", os.W_OK),
                    reason="needs write access to /dev/uinput")
async def test_uinput_opens_and_closes():
    injection = ui.UinputInjection()
    await injection.start()
    try:
        await injection.send_chord(Chord.parse("Ctrl+v"))
    finally:
        await injection.stop()
