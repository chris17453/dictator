"""Delivery policy: clipboard first, paste second, type last."""
import pytest

from dictatord.delivery import profiles
from dictatord.delivery.deliver import Deliverer
from dictatord.errors import Fault, FaultCode
from dictatord.platform.base import Capability, InjectionBackend
from dictatord.platform.chords import Chord


class FakeInjection(InjectionBackend):
    name = "fake"

    def __init__(self, app_id=None, fail_chord=False, fail_clipboard=False):
        self.clipboard = None
        self.typed = []
        self.chords = []
        self._app_id = app_id
        self.fail_chord = fail_chord
        self.fail_clipboard = fail_clipboard

    @classmethod
    async def probe(cls):
        return Capability(name=cls.name, available=True)

    async def start(self): ...
    async def stop(self): ...

    async def set_clipboard(self, text):
        if self.fail_clipboard:
            raise RuntimeError("no clipboard")
        self.clipboard = text

    async def get_clipboard(self):
        return self.clipboard

    async def send_chord(self, chord):
        if self.fail_chord:
            raise Fault(code=FaultCode.INJECTION_FAILED, message="refused", remedy="x")
        self.chords.append(chord)

    async def type_text(self, text):
        self.typed.append(text)

    async def focused_app_id(self):
        return self._app_id


# -- profile selection -----------------------------------------------------


def test_terminal_apps_get_the_shift_paste():
    assert profiles.for_app("org.gnome.Console").name == "terminal"
    assert profiles.for_app("alacritty").name == "terminal"
    assert profiles.for_app("kitty").paste == Chord.parse("Ctrl+Shift+v")


def test_ordinary_apps_get_the_standard_paste():
    assert profiles.for_app("firefox").name == "standard"
    assert profiles.for_app("firefox").paste == Chord.parse("Ctrl+v")


def test_unknown_app_falls_back_to_the_configured_default():
    """None is the expected answer on Wayland, not a failure (v2.md 5.4)."""
    assert profiles.for_app(None).name == "standard"
    assert profiles.for_app(None, default="terminal").name == "terminal"


def test_clipboard_only_apps_never_get_synthesised_input():
    profile = profiles.for_app("keepassxc", clipboard_only_apps=("keepassxc",))
    assert profile.name == "clipboard-only"
    assert profile.synthesises_input is False


# -- delivery --------------------------------------------------------------


async def test_paste_sets_clipboard_and_sends_the_chord():
    backend = FakeInjection(app_id="firefox")
    result = await Deliverer(backend).deliver("hello world")
    assert result.ok and result.method == "paste"
    assert backend.clipboard == "hello world"
    assert backend.chords == [Chord.parse("Ctrl+v")]


async def test_both_clipboard_and_field_are_satisfied():
    """The requirement is both, always — not the either/or of G-05."""
    backend = FakeInjection(app_id="firefox")
    await Deliverer(backend).deliver("text")
    assert backend.clipboard == "text"
    assert backend.chords


async def test_terminal_gets_the_terminal_chord():
    backend = FakeInjection(app_id="org.gnome.Console")
    await Deliverer(backend).deliver("ls")
    assert backend.chords == [Chord.parse("Ctrl+Shift+v")]


async def test_profile_override_wins_over_detection():
    backend = FakeInjection(app_id="firefox")
    await Deliverer(backend).deliver("ls", profile_override="terminal")
    assert backend.chords == [Chord.parse("Ctrl+Shift+v")]


async def test_clipboard_mode_never_synthesises():
    backend = FakeInjection(app_id="firefox")
    result = await Deliverer(backend, mode="clipboard").deliver("secret")
    assert result.method == "clipboard"
    assert backend.clipboard == "secret"
    assert not backend.chords and not backend.typed


async def test_type_mode_types():
    backend = FakeInjection(app_id="firefox")
    result = await Deliverer(backend, mode="type").deliver("hello")
    assert result.method == "type"
    assert backend.typed == ["hello"]


async def test_failed_paste_still_leaves_text_on_the_clipboard():
    backend = FakeInjection(app_id="firefox", fail_chord=True)
    result = await Deliverer(backend).deliver("important")
    assert backend.clipboard == "important"
    assert result.method == "clipboard"
    assert result.ok


async def test_missing_clipboard_falls_back_to_typing():
    backend = FakeInjection(app_id="firefox", fail_clipboard=True)
    result = await Deliverer(backend).deliver("hello")
    assert result.method == "type"
    assert backend.typed == ["hello"]


async def test_empty_text_is_not_delivered():
    backend = FakeInjection()
    result = await Deliverer(backend).deliver("   ")
    assert not result.ok
    assert backend.clipboard is None


async def test_trailing_space_is_optional():
    backend = FakeInjection(app_id="firefox")
    await Deliverer(backend, trailing_space=True).deliver("word")
    assert backend.clipboard == "word "


async def test_clipboard_only_app_is_respected_end_to_end():
    backend = FakeInjection(app_id="keepassxc")
    deliverer = Deliverer(backend, clipboard_only_apps=("keepassxc",))
    result = await deliverer.deliver("hunter2")
    assert result.method == "clipboard"
    assert not backend.chords and not backend.typed
