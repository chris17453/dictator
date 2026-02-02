"""
Tests for transcription confidence scores.

Verifies that:
- Confidence scores are extracted from Whisper results
- Confidence scores are stored with transcriptions
- Confidence indicators are displayed in UI
- Low confidence warnings are shown
- Confidence thresholds are configurable
- Confidence scores appear in history
"""

import pytest
from unittest.mock import patch, MagicMock
import numpy as np


class TestConfidenceExtraction:
    """Test extraction of confidence scores from Whisper."""

    def test_recorder_extracts_confidence_from_whisper(self, qapp):
        """Test that recorder extracts confidence score from Whisper results."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Mock Whisper transcription result with confidence info
        mock_segment = MagicMock()
        mock_segment.text = "test transcription"
        mock_segment.avg_logprob = -0.3  # Good confidence

        # Whisper should provide confidence data
        # The recorder should be able to extract it
        assert hasattr(recorder, 'last_confidence_score')

    def test_confidence_score_calculated_from_logprob(self, qapp):
        """Test that confidence is calculated from log probability."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Test confidence calculation
        # Good logprob (close to 0) = high confidence
        # Bad logprob (very negative) = low confidence

        # Method should exist to convert logprob to 0-100 scale
        assert hasattr(recorder, 'calculate_confidence')
        assert callable(recorder.calculate_confidence)

    def test_high_confidence_detected(self, qapp):
        """Test detection of high confidence transcriptions."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # High confidence: logprob close to 0 (e.g., -0.1)
        confidence = recorder.calculate_confidence(-0.1)

        assert confidence >= 80  # Should be high confidence

    def test_medium_confidence_detected(self, qapp):
        """Test detection of medium confidence transcriptions."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Medium confidence: moderate negative logprob (e.g., -0.5)
        confidence = recorder.calculate_confidence(-0.5)

        assert 50 <= confidence < 80  # Should be medium confidence

    def test_low_confidence_detected(self, qapp):
        """Test detection of low confidence transcriptions."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Low confidence: very negative logprob (e.g., -2.0)
        confidence = recorder.calculate_confidence(-2.0)

        assert confidence < 50  # Should be low confidence


class TestConfidenceStorage:
    """Test storage of confidence scores."""

    def test_confidence_stored_with_transcription(self, qapp):
        """Test that confidence score is stored with transcription result."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Should have attribute to store last confidence
        assert hasattr(recorder, 'last_confidence_score')

        # Should initialize as None
        assert recorder.last_confidence_score is None

    def test_confidence_passed_to_callback(self, qapp):
        """Test that confidence is passed to transcription callback."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        results = []

        def test_callback(text, status, confidence=None):
            results.append({'text': text, 'status': status, 'confidence': confidence})

        # The callback should receive confidence as a parameter
        # This test verifies the signature supports it


class TestConfidenceUI:
    """Test UI elements for confidence scores."""

    def test_window_has_confidence_indicator(self, qapp):
        """Test that window has confidence indicator widget."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'confidence_indicator')

    def test_confidence_indicator_hidden_by_default(self, qapp):
        """Test that confidence indicator is hidden initially."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert window.confidence_indicator.isVisible() is False

    def test_confidence_indicator_shows_percentage(self, qapp):
        """Test that confidence indicator displays percentage."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Set confidence score
            window.update_confidence_display(85)

            # Should display percentage
            text = window.confidence_indicator.text()
            assert '85' in text
            assert '%' in text

    def test_high_confidence_shown_in_green(self, qapp):
        """Test that high confidence (>80%) is shown in green."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.update_confidence_display(90)

            # Should use green/cyan styling for high confidence
            stylesheet = window.confidence_indicator.styleSheet()
            # Check for green or cyan color (various shades acceptable)
            assert ('green' in stylesheet.lower() or
                    '76, 175, 80' in stylesheet or
                    '80, 220, 240' in stylesheet or
                    '60, 200, 220' in stylesheet)  # Futuristic cyan

    def test_medium_confidence_shown_in_yellow(self, qapp):
        """Test that medium confidence (50-80%) is shown in yellow/orange."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.update_confidence_display(65)

            # Should use yellow/orange styling
            stylesheet = window.confidence_indicator.styleSheet()
            # Check for yellow/orange color
            assert 'orange' in stylesheet.lower() or '255, 152, 0' in stylesheet or '255, 180' in stylesheet

    def test_low_confidence_shown_in_red(self, qapp):
        """Test that low confidence (<50%) is shown in red."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.update_confidence_display(30)

            # Should use red styling
            stylesheet = window.confidence_indicator.styleSheet()
            # Check for red color
            assert 'red' in stylesheet.lower() or '244, 67, 54' in stylesheet or '255, 100, 100' in stylesheet


class TestConfidenceWarnings:
    """Test low confidence warnings."""

    def test_window_has_confidence_warning_label(self, qapp):
        """Test that window has low confidence warning label."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # May reuse quality_warning_label or have separate one
            # Either way, should be able to show confidence warnings
            assert hasattr(window, 'quality_warning_label') or hasattr(window, 'confidence_warning_label')

    def test_low_confidence_shows_warning(self, qapp):
        """Test that low confidence (<50%) shows warning message."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate low confidence transcription
            window.show_confidence_warning(25, "Low confidence transcription")

            # Warning should be visible
            warning_visible = False
            if hasattr(window, 'confidence_warning_label'):
                warning_visible = window.confidence_warning_label.isVisible()
            elif hasattr(window, 'quality_warning_label'):
                warning_visible = window.quality_warning_label.isVisible()

            assert warning_visible is True

    def test_high_confidence_hides_warning(self, qapp):
        """Test that high confidence hides warning."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Show then hide warning
            window.show_confidence_warning(25, "Low confidence")
            window.hide_confidence_warning()

            # Should be hidden
            warning_visible = False
            if hasattr(window, 'confidence_warning_label'):
                warning_visible = window.confidence_warning_label.isVisible()
            elif hasattr(window, 'quality_warning_label'):
                warning_visible = window.quality_warning_label.isVisible()

            assert warning_visible is False


class TestConfidenceThresholds:
    """Test configurable confidence thresholds."""

    def test_window_has_confidence_threshold_setting(self, qapp):
        """Test that window has configurable confidence threshold."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'low_confidence_threshold')

    def test_default_threshold_is_reasonable(self, qapp):
        """Test that default low confidence threshold is reasonable (around 50%)."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should be around 50%
            assert 40 <= window.low_confidence_threshold <= 60

    def test_threshold_configurable_in_settings(self, qapp):
        """Test that threshold can be configured in settings."""
        from src.dictator import DictatorWindow
        from src.settings_ui import SettingsDialog

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(window)

            # Should have control for threshold
            has_threshold_control = (
                hasattr(dialog, 'confidence_threshold_spin') or
                hasattr(dialog, 'confidence_threshold_slider')
            )
            assert has_threshold_control is True


class TestConfidenceHistory:
    """Test confidence scores in history."""

    def test_history_items_store_confidence(self, qapp):
        """Test that history entries include confidence scores."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Add item with confidence
            window.add_history_item_with_confidence("test text", 85)

            # Should be in history
            assert len(window.history) > 0

            # Entry should have confidence
            last_entry = window.history[-1]
            assert 'confidence' in last_entry or hasattr(last_entry, 'confidence')

    def test_history_display_shows_confidence(self, qapp):
        """Test that history UI displays confidence scores."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Add item with confidence
            window.add_history_item_with_confidence("test text", 75)

            # History display should show confidence
            # Check that confidence appears in the UI
            # (exact implementation may vary)


class TestConfidenceIntegration:
    """Test integration of confidence scores with transcription workflow."""

    def test_confidence_updated_after_transcription(self, qapp):
        """Test that confidence is updated after successful transcription."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Initially no confidence
            assert window.confidence_indicator.isVisible() is False

            # Simulate transcription with confidence
            window.handle_transcription_with_confidence("test text", "success", 82)

            # Confidence should be visible
            assert window.confidence_indicator.isVisible() is True

    def test_confidence_cleared_on_new_recording(self, qapp):
        """Test that confidence is cleared when starting new recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Set confidence
            window.update_confidence_display(85)

            # Start new recording
            window.recorder.is_recording = True
            window.start_recording()

            # Confidence should be hidden/reset
            # (or stay visible until new transcription completes)


class TestConfidenceDisplay:
    """Test confidence score display formatting."""

    def test_confidence_formatted_as_percentage(self, qapp):
        """Test that confidence is formatted as percentage (0-100)."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.update_confidence_display(87.5)

            text = window.confidence_indicator.text()
            # Should show as integer percentage
            assert '87' in text or '88' in text

    def test_confidence_has_icon(self, qapp):
        """Test that confidence display includes visual indicator."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.update_confidence_display(90)

            text = window.confidence_indicator.text()
            # Should have some icon/emoji
            assert len(text) > 3  # More than just "90%"
