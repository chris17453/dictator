"""
Tests for recording preview functionality.

Verifies that:
- Recorded audio can be previewed before transcription
- Preview UI appears after recording stops
- Audio playback works correctly
- User can accept or re-record
- Audio data is preserved for preview
- Transcription only happens after accepting
"""

import pytest
from unittest.mock import patch, MagicMock, call
import numpy as np


class TestPreviewDataStorage:
    """Test that recorded audio data is stored for preview."""

    def test_recorder_has_preview_audio_data_attribute(self, qapp):
        """Test that recorder can store preview audio data."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert hasattr(recorder, 'preview_audio_data')

    def test_recorder_has_preview_sample_rate_attribute(self, qapp):
        """Test that recorder stores sample rate for preview."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert hasattr(recorder, 'preview_sample_rate')

    def test_preview_data_initially_none(self, qapp):
        """Test that preview data is None initially."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert recorder.preview_audio_data is None
        assert recorder.preview_sample_rate is None

    def test_audio_data_preserved_after_recording(self, qapp):
        """Test that audio data is preserved after recording stops."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Simulate recorded audio
        mock_audio = np.array([100, 200, 300], dtype=np.int16)
        recorder.preview_audio_data = mock_audio
        recorder.preview_sample_rate = 44100

        # Data should be preserved
        assert recorder.preview_audio_data is not None
        assert len(recorder.preview_audio_data) == 3
        assert recorder.preview_sample_rate == 44100


class TestPreviewPlayback:
    """Test audio preview playback functionality."""

    def test_recorder_has_preview_audio_method(self, qapp):
        """Test that recorder has preview_audio method."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert hasattr(recorder, 'preview_audio')
        assert callable(recorder.preview_audio)

    def test_preview_audio_requires_stored_data(self, qapp):
        """Test that preview_audio requires preview data to be available."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.preview_audio_data = None

        # Should return False if no data
        result = recorder.preview_audio()
        assert result is False

    def test_preview_audio_uses_sounddevice(self, qapp):
        """Test that preview_audio uses sounddevice to play audio."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        mock_audio = np.array([100, 200, 300], dtype=np.int16)
        recorder.preview_audio_data = mock_audio
        recorder.preview_sample_rate = 44100

        with patch('sounddevice.play') as mock_play:
            with patch('sounddevice.wait') as mock_wait:
                result = recorder.preview_audio()

                # Should call sounddevice.play with audio data
                mock_play.assert_called_once()
                call_args = mock_play.call_args[0]
                assert len(call_args[0]) == 3  # Audio array
                assert mock_play.call_args[1]['samplerate'] == 44100

                # Should wait for playback to finish
                mock_wait.assert_called_once()
                assert result is True

    def test_preview_converts_audio_format(self, qapp):
        """Test that preview converts int16 to float32 for playback."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        # Create int16 audio data
        mock_audio = np.array([16384, -16384, 0], dtype=np.int16)
        recorder.preview_audio_data = mock_audio
        recorder.preview_sample_rate = 44100

        with patch('sounddevice.play') as mock_play:
            with patch('sounddevice.wait'):
                recorder.preview_audio()

                # Get the audio data passed to play()
                call_args = mock_play.call_args[0][0]

                # Should be float32
                assert call_args.dtype == np.float32
                # Should be normalized (-1.0 to 1.0)
                assert np.max(call_args) <= 1.0
                assert np.min(call_args) >= -1.0


class TestPreviewUI:
    """Test UI elements for preview functionality."""

    def test_window_has_preview_controls_container(self, qapp):
        """Test that window has preview controls container."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'preview_controls')

    def test_preview_controls_hidden_initially(self, qapp):
        """Test that preview controls are hidden by default."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert window.preview_controls.isVisible() is False

    def test_window_has_preview_button(self, qapp):
        """Test that window has preview button."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'preview_btn')

    def test_window_has_accept_button(self, qapp):
        """Test that window has accept recording button."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'accept_recording_btn')

    def test_window_has_rerecord_button(self, qapp):
        """Test that window has re-record button."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'rerecord_btn')

    def test_preview_controls_appear_after_recording(self, qapp):
        """Test that preview controls appear after recording stops."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate preview data available
            window.recorder.preview_audio_data = np.array([100, 200], dtype=np.int16)
            window.recorder.preview_sample_rate = 44100

            # Show preview controls
            window.show_preview_controls()

            assert window.preview_controls.isVisible() is True

    def test_preview_button_triggers_playback(self, qapp):
        """Test that clicking preview button plays audio."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.preview_audio_data = np.array([100, 200], dtype=np.int16)
            window.recorder.preview_sample_rate = 44100

            with patch.object(window.recorder, 'preview_audio') as mock_preview:
                window.preview_btn.click()

                mock_preview.assert_called_once()

    def test_accept_button_triggers_transcription(self, qapp):
        """Test that accepting triggers transcription."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.preview_audio_data = np.array([100, 200], dtype=np.int16)
            window.recorder.preview_sample_rate = 44100

            with patch.object(window, 'process_preview_audio_internal') as mock_process:
                window.accept_recording_btn.click()

                # Should process the audio
                mock_process.assert_called_once()
                # Verify it was called with the audio data
                call_args = mock_process.call_args[0]
                assert len(call_args[0]) == 2  # Audio array
                assert call_args[1] == 44100  # Sample rate

    def test_rerecord_button_clears_preview(self, qapp):
        """Test that re-record clears preview and starts new recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.preview_audio_data = np.array([100, 200], dtype=np.int16)
            window.show_preview_controls()

            with patch.object(window, 'start_recording') as mock_start:
                window.rerecord_btn.click()

                # Should clear preview data
                assert window.recorder.preview_audio_data is None

                # Should hide preview controls
                assert window.preview_controls.isVisible() is False

                # Should start new recording
                mock_start.assert_called_once()


class TestPreviewWorkflow:
    """Test complete preview workflow integration."""

    def test_recording_stops_shows_preview_controls(self, qapp):
        """Test that stopping recording shows preview controls."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Set up preview data
            window.recorder.preview_audio_data = np.array([100, 200], dtype=np.int16)
            window.recorder.preview_sample_rate = 44100
            window.recorder.is_recording = True

            # Simulate the preview_ready callback (which is what shows preview controls)
            with patch.object(window.recorder, 'stop_recording'):
                window._safe_handle_transcription("", "preview_ready")

            # Should show preview controls
            assert window.preview_controls.isVisible() is True

    def test_transcription_delayed_until_accept(self, qapp):
        """Test that transcription doesn't happen until user accepts."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate recording complete with preview data
            window.recorder.preview_audio_data = np.array([100, 200], dtype=np.int16)
            window.recorder.is_recording = True

            # Recording callback should NOT be called immediately
            callback_called = False

            def test_callback(text, status):
                nonlocal callback_called
                callback_called = True

            window.recorder.callback = test_callback

            # Stop recording
            with patch.object(window.recorder, 'stop_recording'):
                window.stop_recording()

            # Callback should not have been called yet
            assert callback_called is False

    def test_preview_data_cleared_after_accept(self, qapp):
        """Test that preview data is cleared after accepting."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.preview_audio_data = np.array([100, 200], dtype=np.int16)

            with patch.object(window, 'process_preview_audio'):
                window.accept_recording_btn.click()

            # Preview data should be cleared
            assert window.recorder.preview_audio_data is None

    def test_preview_controls_hidden_after_accept(self, qapp):
        """Test that preview controls hide after accepting."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.preview_audio_data = np.array([100, 200], dtype=np.int16)
            window.show_preview_controls()

            with patch.object(window, 'process_preview_audio'):
                window.accept_recording_btn.click()

            assert window.preview_controls.isVisible() is False


class TestPreviewProcessing:
    """Test audio processing after preview acceptance."""

    def test_window_has_process_preview_audio_method(self, qapp):
        """Test that window has method to process accepted preview."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'process_preview_audio')
            assert callable(window.process_preview_audio)

    def test_process_preview_uses_stored_audio_data(self, qapp):
        """Test that processing uses the stored preview audio."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            mock_audio = np.array([100, 200, 300], dtype=np.int16)
            window.recorder.preview_audio_data = mock_audio
            window.recorder.preview_sample_rate = 44100

            # Process should use the preview data
            with patch.object(window, 'transcribe_audio') as mock_transcribe:
                window.process_preview_audio()

                # Should call transcribe with preview data
                mock_transcribe.assert_called_once()
                call_args = mock_transcribe.call_args[0]
                assert len(call_args[0]) == 3  # Audio array
                assert call_args[1] == 44100  # Sample rate


class TestPreviewErrorHandling:
    """Test error handling in preview functionality."""

    def test_preview_handles_no_audio_data(self, qapp):
        """Test that preview handles missing audio data gracefully."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.preview_audio_data = None

        # Should not crash
        result = recorder.preview_audio()
        assert result is False

    def test_preview_handles_playback_error(self, qapp):
        """Test that preview handles sounddevice errors."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.preview_audio_data = np.array([100, 200], dtype=np.int16)
        recorder.preview_sample_rate = 44100

        with patch('sounddevice.play', side_effect=Exception("Playback error")):
            # Should not crash
            result = recorder.preview_audio()
            assert result is False

    def test_accept_with_no_preview_data_ignored(self, qapp):
        """Test that accepting with no preview data is ignored."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.preview_audio_data = None

            with patch.object(window, 'transcribe_audio') as mock_transcribe:
                window.process_preview_audio()

                # Should not attempt transcription
                mock_transcribe.assert_not_called()
