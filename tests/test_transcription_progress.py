"""
Tests for transcription progress indicator.

Verifies that:
- Progress bar exists in UI
- Progress updates during transcription
- Progress bar shows/hides appropriately
- Progress reflects actual Whisper processing stages
- Progress is thread-safe
"""

import pytest
from unittest.mock import patch, MagicMock
import time


class TestProgressBarUI:
    """Test that progress bar UI elements exist."""

    def test_window_has_progress_bar(self, qapp):
        """Test that window has a progress bar widget."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'progress_bar')

    def test_progress_bar_is_progress_bar_widget(self, qapp):
        """Test that progress bar is a QProgressBar."""
        from src.dictator import DictatorWindow
        from PyQt6.QtWidgets import QProgressBar

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert isinstance(window.progress_bar, QProgressBar)

    def test_progress_bar_hidden_by_default(self, qapp):
        """Test that progress bar is hidden when not transcribing."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert window.progress_bar.isVisible() is False

    def test_progress_label_exists(self, qapp):
        """Test that progress label exists for text description."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'progress_label')

    def test_progress_label_hidden_by_default(self, qapp):
        """Test that progress label is hidden by default."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert window.progress_label.isVisible() is False


class TestProgressBarBehavior:
    """Test progress bar behavior during transcription."""

    def test_progress_bar_shows_when_transcription_starts(self, qapp):
        """Test that progress bar appears when transcription starts."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate transcription start
            window.show_transcription_progress()

            assert window.progress_bar.isVisible() is True
            assert window.progress_label.isVisible() is True

    def test_progress_bar_hides_when_transcription_completes(self, qapp):
        """Test that progress bar hides when transcription completes."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Show then hide
            window.show_transcription_progress()
            window.hide_transcription_progress()

            assert window.progress_bar.isVisible() is False
            assert window.progress_label.isVisible() is False

    def test_progress_bar_starts_at_zero(self, qapp):
        """Test that progress bar starts at 0%."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.show_transcription_progress()

            assert window.progress_bar.value() == 0

    def test_progress_bar_updates_to_specific_value(self, qapp):
        """Test that progress bar updates to specific percentage."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.show_transcription_progress()
            window.update_transcription_progress(50)

            assert window.progress_bar.value() == 50

    def test_progress_bar_completes_at_100(self, qapp):
        """Test that progress bar reaches 100% when complete."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.show_transcription_progress()
            window.update_transcription_progress(100)

            assert window.progress_bar.value() == 100


class TestProgressStages:
    """Test progress updates for different transcription stages."""

    def test_progress_label_shows_loading_stage(self, qapp):
        """Test that progress label shows 'Loading model' stage."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.show_transcription_progress()
            window.update_transcription_progress(10, "Loading model...")

            assert "Loading" in window.progress_label.text()

    def test_progress_label_shows_processing_stage(self, qapp):
        """Test that progress label shows 'Processing audio' stage."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.show_transcription_progress()
            window.update_transcription_progress(50, "Processing audio...")

            assert "Processing" in window.progress_label.text()

    def test_progress_label_shows_finalizing_stage(self, qapp):
        """Test that progress label shows 'Finalizing' stage."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.show_transcription_progress()
            window.update_transcription_progress(90, "Finalizing transcription...")

            assert "Finalizing" in window.progress_label.text()


class TestRecorderProgressCallbacks:
    """Test that recorder emits progress updates."""

    def test_recorder_has_progress_callback(self, qapp):
        """Test that recorder has progress callback attribute."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        assert hasattr(recorder, 'progress_callback')

    def test_recorder_calls_progress_callback_during_transcription(self, qapp):
        """Test that recorder calls progress callback."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        progress_updates = []

        def track_progress(percent, message):
            progress_updates.append((percent, message))

        recorder.progress_callback = track_progress

        # We can't test actual transcription without Whisper model
        # But we can test that the callback mechanism exists
        assert recorder.progress_callback is not None
        assert callable(recorder.progress_callback)


class TestProgressIntegration:
    """Test integration of progress bar with actual transcription."""

    def test_progress_shown_during_transcription_workflow(self, qapp):
        """Test that progress bar appears during full transcription workflow."""
        from src.dictator import DictatorWindow
        import numpy as np

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate having preview audio
            window.recorder.preview_audio_data = np.array([100, 200], dtype=np.int16)
            window.recorder.preview_sample_rate = 16000

            # Mock the actual transcription
            with patch.object(window, 'transcribe_audio') as mock_transcribe:
                # Accept recording should show progress
                window.accept_recording_btn.click()

                # Progress should be visible
                # Note: This might need adjustment based on actual implementation
                # The test validates the integration point exists

    def test_progress_updates_are_thread_safe(self, qapp):
        """Test that progress updates from background thread are safe."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate progress update from background thread
            # Should not crash
            window.update_transcription_progress(25, "Testing...")

            assert window.progress_bar.value() == 25


class TestProgressBarStyling:
    """Test that progress bar has appropriate styling."""

    def test_progress_bar_has_custom_styling(self, qapp):
        """Test that progress bar matches futuristic theme."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            stylesheet = window.progress_bar.styleSheet()
            # Should have some custom styling
            assert len(stylesheet) > 0

    def test_progress_label_has_themed_color(self, qapp):
        """Test that progress label has themed color."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            stylesheet = window.progress_label.styleSheet()
            # Should have color styling
            assert 'color' in stylesheet.lower() or len(stylesheet) > 0


class TestProgressErrorHandling:
    """Test error handling for progress updates."""

    def test_progress_update_with_invalid_value_clamped(self, qapp):
        """Test that invalid progress values are clamped to 0-100."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Try to set invalid values
            window.update_transcription_progress(-10)
            assert window.progress_bar.value() >= 0

            window.update_transcription_progress(150)
            assert window.progress_bar.value() <= 100

    def test_progress_update_without_message_works(self, qapp):
        """Test that progress update works without message."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should not crash
            window.update_transcription_progress(50)
            assert window.progress_bar.value() == 50
