"""Whether audio capture can actually work — not merely whether a device entry exists.

PortAudio advertises aggregate "pipewire" and "default" entries on a PipeWire
host whether or not any microphone exists behind them. Reporting those as a
working microphone is the silent-failure behaviour this rewrite exists to
remove (G-08).
"""
import pytest

from dictatord.audio import devices as dev
from dictatord.audio.devices import Device


def _device(name, index=0, default=False):
    return Device(name=name, description=name, index=index, channels=1,
                  sample_rate=48000.0, is_default=default)


@pytest.mark.parametrize("name", ["pipewire", "pulse", "default", "sysdefault"])
def test_routing_entries_are_recognised_as_aggregates(name):
    assert dev.is_aggregate(_device(name))


def test_real_devices_are_not_aggregates():
    assert not dev.is_aggregate(_device("keychron-q6"))
    assert not dev.is_aggregate(_device("blue-yeti"))


def test_real_sources_mean_capture_works(monkeypatch):
    monkeypatch.setattr(dev, "_pipewire_sources", lambda: [("mic", "Blue Yeti")])
    monkeypatch.setattr(dev, "_session_is_remote", lambda: False)
    diagnosis = dev.diagnose()
    assert diagnosis.ok and diagnosis.real_sources == 1


def test_aggregates_alone_are_not_a_microphone(monkeypatch):
    """The exact false green this check exists to prevent."""
    monkeypatch.setattr(dev, "_pipewire_sources", lambda: [])
    monkeypatch.setattr(dev, "_session_is_remote", lambda: False)
    monkeypatch.setattr(dev, "enumerate_devices",
                        lambda: [_device("pipewire"), _device("default", 1, True)])
    diagnosis = dev.diagnose()
    assert not diagnosis.ok
    assert "connect a microphone" in diagnosis.remedy.lower()


def test_hardware_without_a_sound_server_still_counts(monkeypatch):
    monkeypatch.setattr(dev, "_pipewire_sources", lambda: [])
    monkeypatch.setattr(dev, "_session_is_remote", lambda: False)
    monkeypatch.setattr(dev, "enumerate_devices", lambda: [_device("hw-card-0")])
    assert dev.diagnose().ok


def test_a_remote_session_explains_redirection(monkeypatch):
    monkeypatch.setattr(dev, "_pipewire_sources", lambda: [])
    monkeypatch.setattr(dev, "_session_is_remote", lambda: True)
    monkeypatch.setattr(dev, "enumerate_devices",
                        lambda: [_device("pipewire"), _device("default", 1, True)])
    diagnosis = dev.diagnose()
    assert not diagnosis.ok
    assert diagnosis.remote_session
    # A setup gap, not a broken install: doctor shows it as a warning.
    assert diagnosis.is_warning
    assert "redirection" in diagnosis.remedy
    assert "/microphone" in diagnosis.remedy


def test_a_local_session_is_not_told_about_redirection(monkeypatch):
    monkeypatch.setattr(dev, "_pipewire_sources", lambda: [])
    monkeypatch.setattr(dev, "_session_is_remote", lambda: False)
    monkeypatch.setattr(dev, "enumerate_devices", lambda: [])
    diagnosis = dev.diagnose()
    assert not diagnosis.is_warning, "a local machine with no mic is a real failure"
    assert "redirection" not in diagnosis.remedy


def test_monitors_are_never_offered_as_microphones(monkeypatch):
    """A monitor is a loopback of output, not anything a user means by mic."""
    import shutil
    import subprocess

    class Result:
        returncode = 0
        stdout = (
            "1\talsa_output.pci.analog.monitor\tmodule\ts16le\tRUNNING\n"
            "2\talsa_input.usb-Blue_Yeti\tmodule\ts16le\tSUSPENDED\n"
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/pactl")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Result())
    names = [name for name, _ in dev._pipewire_sources()]
    assert names == ["alsa_input.usb-Blue_Yeti"]


def test_diagnosis_never_raises_when_enumeration_fails(monkeypatch):
    from dictatord.errors import Fault, FaultCode

    def boom():
        raise Fault(code=FaultCode.NO_DEVICE, message="x", remedy="y")

    monkeypatch.setattr(dev, "_pipewire_sources", lambda: [])
    monkeypatch.setattr(dev, "_session_is_remote", lambda: False)
    monkeypatch.setattr(dev, "enumerate_devices", boom)
    assert dev.diagnose().ok is False


# -- phantom devices -------------------------------------------------------


def test_a_source_portaudio_already_exposes_is_not_duplicated(monkeypatch):
    """The duplicate resolved to the aggregate index and captured silence.

    PipeWire names a source "remote_mic" while PortAudio shows its description,
    "Remote-Microphone". Adding the PipeWire name as a second device produced
    two entries for one microphone, one of which quietly recorded nothing.
    """
    monkeypatch.setattr(dev, "_pipewire_sources", lambda: [("remote_mic", "remote_mic")])

    class FakeSoundDevice:
        @staticmethod
        def query_devices():
            return [
                {"name": "pipewire", "max_input_channels": 64, "default_samplerate": 44100},
                {"name": "Remote-Microphone", "max_input_channels": 1,
                 "default_samplerate": 48000},
            ]

        class default:
            device = (0, 0)

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", FakeSoundDevice)
    names = [d.name for d in dev.enumerate_devices()]
    assert names.count("remote-microphone") == 1
    assert "remote-mic" not in names, "the PipeWire spelling must not become a second device"


def test_a_source_portaudio_cannot_see_is_added_and_flagged_for_routing(monkeypatch):
    monkeypatch.setattr(dev, "_pipewire_sources", lambda: [("usb_yeti", "Blue Yeti")])

    class FakeSoundDevice:
        @staticmethod
        def query_devices():
            return [{"name": "pipewire", "max_input_channels": 64,
                     "default_samplerate": 44100}]

        class default:
            device = (0, 0)

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", FakeSoundDevice)
    extra = [d for d in dev.enumerate_devices() if d.name == "usb-yeti"]
    assert len(extra) == 1
    # It has no PortAudio index of its own, so capture must be routed by name.
    assert extra[0].needs_routing
    assert extra[0].server_source == "usb_yeti"


@pytest.mark.parametrize("candidate,existing,same", [
    ("blue-yeti", "blue-yeti-usb", True),
    # PipeWire spells it alsa_input.usb-Blue_Yeti, PortAudio just "Blue Yeti".
    # Recognising those as one device is the whole point.
    ("alsa-input-usb-blue-yeti", "blue-yeti", True),
    ("remote-mic", "remote-microphone", True),
    ("blue-yeti", "logitech-webcam", False),
    ("", "blue-yeti", False),
])
def test_device_name_similarity(candidate, existing, same):
    assert dev._looks_like(candidate, existing) is same
