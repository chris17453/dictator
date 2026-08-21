"""The daemon's contract, exercised with no display server at all.

This is what CI runs on every commit: Tier 3 in the support matrix. The whole
pipeline works headlessly, which is exactly why the null backends exist
(v2.md 5.5).
"""
import numpy as np
import pytest

from dictatord import config as cfg
from dictatord.daemon import Daemon
from dictatord.errors import Fault
from dictatord.platform.base import ShortcutEvent
from dictatord.session import State


class StubEngine:
    """Stands in for Whisper so the contract can be tested without a GPU."""

    def __init__(self, text="hello world"):
        self.text = text
        self.calls = []
        self.model_name = "stub"

    def describe(self):
        return {"model": "stub", "device": "cpu", "compute_type": "int8",
                "loaded": "true", "integrity": "n/a"}

    async def ensure_loaded(self): ...
    async def unload(self): ...

    async def transcribe(self, audio, sample_rate, prompt="", partial=False):
        from dictatord.asr.engine import Transcript

        self.calls.append({"samples": int(audio.size), "prompt": prompt, "partial": partial})
        return Transcript(text=self.text, language="en", confidence=0.9,
                          duration_s=audio.size / sample_rate)


@pytest.fixture
async def daemon(monkeypatch):
    """A daemon with no display server and no microphone."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)

    config = cfg.load(
        overrides={
            "memory.enabled": True,
            "streaming.enabled": False,
            "model.keep_resident": False,
            "lexicon.enabled": True,
        },
        use_site=False, use_user=False,
    )
    instance = Daemon(config)
    instance.engine = StubEngine()
    await instance.start()
    yield instance
    await instance.shutdown()


async def test_headless_selects_null_backends(daemon):
    assert daemon.platform.session.is_headless
    assert daemon.platform.shortcuts.name == "none"
    assert daemon.platform.injection.name == "none"


async def test_toggle_starts_and_stops(daemon):
    session_id = await daemon.toggle({})
    assert session_id > 0
    assert daemon.session_manager.state is State.LISTENING

    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    assert await daemon.toggle({}) == session_id
    assert daemon.session_manager.state is State.IDLE


async def test_a_full_utterance_is_transcribed_and_stored(daemon):
    await daemon.toggle({})
    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    await daemon.toggle({})

    assert daemon.engine.calls, "the engine must be asked to transcribe"
    assert daemon.store.count() == 1
    assert daemon.store.last().text == "hello world"


async def test_transcript_reaches_the_clipboard(daemon):
    await daemon.toggle({})
    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    await daemon.toggle({})
    assert await daemon.platform.injection.get_clipboard() == "hello world"


async def test_silence_is_not_stored(daemon):
    daemon.engine.text = "   "
    await daemon.toggle({})
    daemon.session_manager.feed(np.zeros(16000, dtype=np.float32))
    await daemon.toggle({})
    assert daemon.store.count() == 0


async def test_cancel_delivers_nothing(daemon):
    await daemon.toggle({})
    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    assert await daemon.cancel() is True
    assert daemon.store.count() == 0
    assert not daemon.engine.calls


async def test_push_to_talk_via_the_api(daemon):
    session_id = await daemon.push_begin({})
    assert session_id > 0
    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    assert await daemon.push_end() == session_id
    assert daemon.store.count() == 1


async def test_shortcut_events_drive_the_session(daemon):
    """A null backend still delivers events, so the FSM is testable in CI.

    It cannot report key release, so a press must mean toggle outright — with
    hold semantics the session could never be stopped from the chord.
    """
    assert daemon.session_manager.supports_release is False
    await daemon._handle_shortcut("dictate", ShortcutEvent.PRESSED)
    assert daemon.session_manager.state is State.LISTENING
    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    await daemon._handle_shortcut("dictate", ShortcutEvent.PRESSED)
    assert daemon.store.count() == 1


async def test_cancel_shortcut_discards(daemon):
    await daemon._handle_shortcut("dictate", ShortcutEvent.PRESSED)
    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    await daemon._handle_shortcut("cancel", ShortcutEvent.PRESSED)
    assert daemon.session_manager.state is State.IDLE
    assert daemon.store.count() == 0


async def test_state_snapshot_reports_the_real_backends(daemon):
    state = daemon.state_snapshot()
    assert state["shortcut_backend"] == "none"
    assert state["injection_backend"] == "none"
    assert state["session"] == "headless"
    # The model's compute device must not overwrite the audio device.
    assert "model_device" in state and "device" in state


async def test_list_models_marks_the_catalogue(daemon):
    rows = daemon.list_models()
    assert rows and len(rows[0]) == 5
    assert {r[0] for r in rows} >= {"tiny", "base", "large-v3-turbo"}


async def test_list_shortcuts_reports_configuration(daemon):
    rows = {r[0]: r[1] for r in daemon.list_shortcuts()}
    assert rows["dictate"] == "Super+d"
    assert rows["dictate_terminal"] == "(unbound)"


async def test_search_finds_a_stored_transcript(daemon):
    await daemon.toggle({})
    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    await daemon.toggle({})
    assert daemon.search("hello", 10)
    assert daemon.search("absent", 10) == []


async def test_redeliver_replays_without_re_speaking(daemon):
    await daemon.toggle({})
    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    await daemon.toggle({})
    await daemon.platform.injection.set_clipboard("something else")
    assert await daemon.redeliver(0, {}) is True
    assert await daemon.platform.injection.get_clipboard() == "hello world"


async def test_redeliver_of_a_missing_entry_explains_itself(daemon):
    with pytest.raises(Fault) as excinfo:
        await daemon.redeliver(999, {})
    assert excinfo.value.remedy


async def test_lexicon_prompt_reaches_the_engine(daemon):
    daemon.lexicon.add_term("ctranslate2")
    await daemon.toggle({})
    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    await daemon.toggle({})
    assert "ctranslate2" in daemon.engine.calls[-1]["prompt"]


async def test_lexicon_substitution_is_applied_to_output(daemon):
    daemon.engine.text = "deploy to cubernetes"
    daemon.lexicon.add_substitution("cubernetes", "Kubernetes")
    await daemon.toggle({})
    daemon.session_manager.feed(np.full(16000, 0.2, dtype=np.float32))
    await daemon.toggle({})
    assert daemon.store.last().text == "deploy to Kubernetes"


async def test_setting_an_unknown_shortcut_is_refused(daemon):
    with pytest.raises(Fault):
        await daemon.set_shortcut("nonsense", "Super+z")


async def test_setting_an_unusable_chord_is_refused(daemon):
    from dictatord.platform.chords import ChordError

    with pytest.raises((Fault, ChordError)):
        await daemon.set_shortcut("dictate", "a")


async def test_reload_re_reads_configuration(daemon):
    result = await daemon.reload()
    assert result["reloaded"] == "true"
