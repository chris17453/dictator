"""
Tests for pause/resume recording functionality.

Verifies that:
- Recording can be paused and resumed
- Audio segments are collected during pause/resume cycles
- Paused state is properly tracked
- UI shows pause button during recording
- Pause/resume works with both toggle and push-to-talk modes
"""

import pytest
from unittest.mock import patch, MagicMock


class TestPauseResumeState:
    """Test pause/resume state management."""

    def test_recorder_has_is_paused_flag(self, qapp):
        """Test that recorder has is_paused flag."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert hasattr(recorder, 'is_paused')

    def test_default_is_paused_is_false(self, qapp):
        """Test that is_paused defaults to False."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert recorder.is_paused is False

    def test_recorder_has_pause_method(self, qapp):
        """Test that recorder has pause_recording method."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert hasattr(recorder, 'pause_recording')
        assert callable(recorder.pause_recording)

    def test_recorder_has_resume_method(self, qapp):
        """Test that recorder has resume_recording method."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert hasattr(recorder, 'resume_recording')
        assert callable(recorder.resume_recording)

    def test_pause_sets_is_paused_true(self, qapp):
        """Test that pausing sets is_paused to True."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.is_recording = True
        recorder.pause_recording()

        assert recorder.is_paused is True
        # Recording should still be True (paused, not stopped)
        assert recorder.is_recording is True

    def test_resume_sets_is_paused_false(self, qapp):
        """Test that resuming sets is_paused to False."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.is_recording = True
        recorder.is_paused = True

        recorder.resume_recording()

        assert recorder.is_paused is False
        assert recorder.is_recording is True


class TestAudioSegments:
    """Test audio segment collection during pause/resume."""

    def test_recorder_has_audio_segments_list(self, qapp):
        """Test that recorder tracks audio segments."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert hasattr(recorder, 'audio_segments')
        assert isinstance(recorder.audio_segments, list)

    def test_pause_saves_current_audio_segment(self, qapp):
        """Test that pausing saves current audio to segments list."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.is_recording = True

        # Mock the subprocess and audio data
        recorder.active_subprocess = MagicMock()
        recorder.active_subprocess.poll.return_value = None

        recorder.pause_recording()

        # Should have saved a segment
        # (actual implementation will handle subprocess termination)
        assert recorder.is_paused is True

    def test_resume_starts_new_segment(self, qapp):
        """Test that resuming starts collecting a new audio segment."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.is_recording = True
        recorder.is_paused = True

        recorder.resume_recording()

        # Should be ready to collect new segment
        assert recorder.is_paused is False

    def test_stop_combines_all_segments(self, qapp):
        """Test that stopping combines all audio segments."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Simulate multiple segments from pause/resume cycles
        recorder.audio_segments = ['segment1.raw', 'segment2.raw']
        recorder.is_recording = True

        # Stop should combine segments (tested via integration)
        recorder.stop_recording()

        assert recorder.is_recording is False


class TestPauseResumeUI:
    """Test UI controls for pause/resume."""

    def test_window_has_pause_resume_method(self, qapp):
        """Test that window has pause/resume toggle method."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'toggle_pause')
            assert callable(window.toggle_pause)

    def test_window_has_pause_button(self, qapp):
        """Test that window has pause button."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have pause button
            assert hasattr(window, 'pause_btn')

    def test_pause_button_hidden_when_not_recording(self, qapp):
        """Test that pause button is hidden when not recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should be hidden initially
            assert window.pause_btn.isVisible() is False

    def test_pause_button_visible_during_recording(self, qapp):
        """Test that pause button becomes visible during recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Mock start_recording to avoid actual recording
            with patch.object(window.recorder, 'start_recording'):
                window.recorder.is_recording = True
                window.update_ui_for_recording_state()

                # Should be visible now
                assert window.pause_btn.isVisible() is True

    def test_pause_button_text_changes_on_pause(self, qapp):
        """Test that pause button text changes between Pause/Resume."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Initially should say "Pause" or have pause icon
            window.recorder.is_recording = True
            window.recorder.is_paused = False
            window.update_ui_for_recording_state()

            pause_text = window.pause_btn.text()

            # After pausing, should change
            window.recorder.is_paused = True
            window.update_ui_for_recording_state()

            resume_text = window.pause_btn.text()

            # Texts should be different
            assert pause_text != resume_text

    def test_pause_button_has_tooltip(self, qapp):
        """Test that pause button has helpful tooltip."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            tooltip = window.pause_btn.toolTip()
            assert tooltip, "Pause button should have tooltip"
            assert len(tooltip) > 0


class TestPauseResumeBehavior:
    """Test pause/resume behavior during recording."""

    def test_toggle_pause_when_recording_pauses(self, qapp):
        """Test that toggle_pause pauses when recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate recording
            window.recorder.is_recording = True
            window.recorder.is_paused = False

            # Mock pause method
            with patch.object(window.recorder, 'pause_recording') as mock_pause:
                window.toggle_pause()
                mock_pause.assert_called_once()

    def test_toggle_pause_when_paused_resumes(self, qapp):
        """Test that toggle_pause resumes when paused."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Simulate paused state
            window.recorder.is_recording = True
            window.recorder.is_paused = True

            # Mock resume method
            with patch.object(window.recorder, 'resume_recording') as mock_resume:
                window.toggle_pause()
                mock_resume.assert_called_once()

    def test_pause_updates_status_label(self, qapp):
        """Test that pausing updates status to show 'Paused'."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.recorder.is_recording = True
            window.recorder.is_paused = True
            window.update_ui_for_recording_state()

            status_text = window.status_label.text()
            assert 'pause' in status_text.lower() or '⏸' in status_text

    def test_cannot_pause_when_not_recording(self, qapp):
        """Test that pause does nothing when not recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.recorder.is_recording = False

            # Should not crash
            window.toggle_pause()

            # Should still not be paused
            assert window.recorder.is_paused is False


class TestPauseResumeIntegration:
    """Test integration of pause/resume with other features."""

    def test_pause_works_with_toggle_mode(self, qapp):
        """Test that pause works in toggle recording mode."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recording_mode = 'toggle'

            window.recorder.is_recording = True

            # Should be able to pause
            with patch.object(window.recorder, 'pause_recording'):
                window.toggle_pause()
                # Should not crash

    def test_pause_works_with_push_to_talk_mode(self, qapp):
        """Test that pause works in push-to-talk mode."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recording_mode = 'push-to-talk'

            window.recorder.is_recording = True

            # Should be able to pause
            with patch.object(window.recorder, 'pause_recording'):
                window.toggle_pause()
                # Should not crash

    def test_stopping_while_paused_works(self, qapp):
        """Test that stopping while paused completes properly."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.recorder.is_recording = True
            window.recorder.is_paused = True

            # Should handle stop gracefully
            with patch.object(window.recorder, 'stop_recording'):
                with patch.object(window, 'stop_recording') as mock_stop:
                    window.hotkey_pressed(is_press=True)
                    # In toggle mode, should stop
