"""
Tests for audio quality indicator.

Verifies that:
- Audio quality is assessed during recording
- Too quiet audio triggers warning
- Too loud audio (clipping risk) triggers warning
- Good quality audio shows no warnings
- Visual indicators appear in UI
- Quality thresholds are configurable
"""

import pytest
from unittest.mock import patch, MagicMock


class TestQualityDetection:
    """Test audio quality detection logic."""

    def test_window_has_audio_quality_state(self, qapp):
        """Test that window tracks audio quality state."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have audio quality tracking
            assert hasattr(window, 'audio_quality_state')

    def test_default_quality_state_is_good(self, qapp):
        """Test that default audio quality state is 'good'."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Default should be good (no warnings)
            assert window.audio_quality_state == 'good'

    def test_quiet_audio_detected(self, qapp):
        """Test that too-quiet audio is detected."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate recording with quiet audio level
            window.recorder.is_recording = True
            window.recorder.current_audio_level = 5  # 5% is too quiet

            window.check_audio_quality()

            # Should be in quiet state
            assert window.audio_quality_state == 'too_quiet'

    def test_loud_audio_detected(self, qapp):
        """Test that too-loud audio (clipping risk) is detected."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate recording with loud audio level (risk of clipping)
            window.recorder.is_recording = True
            window.recorder.current_audio_level = 95  # 95% is too loud

            window.check_audio_quality()

            # Should be in loud state
            assert window.audio_quality_state == 'too_loud'

    def test_good_audio_quality(self, qapp):
        """Test that normal audio levels show as good quality."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate recording with normal audio levels
            window.recorder.is_recording = True
            for level in [20, 40, 60, 80]:
                window.recorder.current_audio_level = level
                window.check_audio_quality()

                # Should be good quality
                assert window.audio_quality_state == 'good'


class TestQualityThresholds:
    """Test configurable quality thresholds."""

    def test_window_has_quiet_threshold(self, qapp):
        """Test that window has configurable quiet threshold."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'audio_too_quiet_threshold')

    def test_window_has_loud_threshold(self, qapp):
        """Test that window has configurable loud threshold."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'audio_too_loud_threshold')

    def test_default_quiet_threshold_is_reasonable(self, qapp):
        """Test that default quiet threshold is reasonable (around 10)."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should be around 10% for too quiet
            assert 5 <= window.audio_too_quiet_threshold <= 15

    def test_default_loud_threshold_is_reasonable(self, qapp):
        """Test that default loud threshold is reasonable (around 90)."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should be around 90% for too loud
            assert 85 <= window.audio_too_loud_threshold <= 95

    def test_can_customize_thresholds(self, qapp):
        """Test that thresholds can be customized."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Customize thresholds
            window.audio_too_quiet_threshold = 15
            window.audio_too_loud_threshold = 85

            assert window.audio_too_quiet_threshold == 15
            assert window.audio_too_loud_threshold == 85


class TestQualityUI:
    """Test UI indicators for audio quality."""

    def test_window_has_quality_warning_label(self, qapp):
        """Test that window has quality warning label."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have quality warning label
            assert hasattr(window, 'quality_warning_label')

    def test_quality_warning_hidden_by_default(self, qapp):
        """Test that quality warning is hidden when not recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should be hidden initially
            assert window.quality_warning_label.isVisible() is False

    def test_quiet_warning_shows_message(self, qapp):
        """Test that too-quiet warning shows appropriate message."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.is_recording = True

            # Simulate quiet audio
            window.audio_quality_state = 'too_quiet'
            window.update_quality_warning()

            # Should show warning and be visible
            assert window.quality_warning_label.isVisible() is True
            text = window.quality_warning_label.text().lower()
            assert 'quiet' in text or 'low' in text or 'speak' in text

    def test_loud_warning_shows_message(self, qapp):
        """Test that too-loud warning shows appropriate message."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.is_recording = True

            # Simulate loud audio
            window.audio_quality_state = 'too_loud'
            window.update_quality_warning()

            # Should show warning and be visible
            assert window.quality_warning_label.isVisible() is True
            text = window.quality_warning_label.text().lower()
            assert 'loud' in text or 'clip' in text or 'lower' in text

    def test_good_quality_hides_warning(self, qapp):
        """Test that good quality hides warning label."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.is_recording = True

            # Show warning first
            window.audio_quality_state = 'too_quiet'
            window.update_quality_warning()
            assert window.quality_warning_label.isVisible() is True

            # Then good quality
            window.audio_quality_state = 'good'
            window.update_quality_warning()

            # Should hide warning
            assert window.quality_warning_label.isVisible() is False

    def test_warning_label_has_distinctive_styling(self, qapp):
        """Test that warning label has eye-catching styling."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Check that styling exists
            style = window.quality_warning_label.styleSheet()
            # Should have some styling (color, background, etc)
            assert len(style) > 0


class TestQualityIntegration:
    """Test integration of quality indicator with recording."""

    def test_quality_checked_during_recording(self, qapp):
        """Test that quality is checked while recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Quality check should be part of volume update
            # (integration tested via volume_timer)
            assert hasattr(window, 'check_audio_quality')

    def test_quality_not_checked_when_not_recording(self, qapp):
        """Test that quality warnings don't appear when not recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.is_recording = False

            # Even with bad levels, no warning when not recording
            window.recorder.current_audio_level = 5
            window.update_volume_bars()

            # Warning should be hidden
            assert window.quality_warning_label.isVisible() is False

    def test_quality_state_resets_on_stop(self, qapp):
        """Test that quality state resets when recording stops."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Set bad quality
            window.audio_quality_state = 'too_quiet'
            window.recorder.is_recording = True
            window.update_quality_warning()

            # Stop recording
            window.recorder.is_recording = False
            with patch.object(window.recorder, 'stop_recording'):
                window.stop_recording()

            # Should reset to good and hide warning
            assert window.audio_quality_state == 'good'
            assert window.quality_warning_label.isVisible() is False


class TestQualityWarningText:
    """Test quality warning text content."""

    def test_quiet_warning_is_helpful(self, qapp):
        """Test that quiet warning provides helpful guidance."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.audio_quality_state = 'too_quiet'
            window.recorder.is_recording = True
            window.update_quality_warning()

            text = window.quality_warning_label.text()
            # Should give actionable advice
            assert len(text) > 10
            # Should mention what to do
            assert any(word in text.lower() for word in ['speak', 'closer', 'louder', 'volume'])

    def test_loud_warning_is_helpful(self, qapp):
        """Test that loud warning provides helpful guidance."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.audio_quality_state = 'too_loud'
            window.recorder.is_recording = True
            window.update_quality_warning()

            text = window.quality_warning_label.text()
            # Should give actionable advice
            assert len(text) > 10
            # Should mention what to do
            assert any(word in text.lower() for word in ['lower', 'away', 'quieter', 'clip'])

    def test_warning_includes_icon(self, qapp):
        """Test that warnings include visual icon/emoji."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.is_recording = True

            # Check quiet warning
            window.audio_quality_state = 'too_quiet'
            window.update_quality_warning()
            text_quiet = window.quality_warning_label.text()

            # Check loud warning
            window.audio_quality_state = 'too_loud'
            window.update_quality_warning()
            text_loud = window.quality_warning_label.text()

            # Should have some visual indicator (emoji or symbol)
            assert any(char in text_quiet for char in ['⚠', '!', '⬇', '🔇'])
            assert any(char in text_loud for char in ['⚠', '!', '⬆', '🔊'])
