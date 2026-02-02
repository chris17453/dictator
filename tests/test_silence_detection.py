"""
Tests for silence detection settings.

Verifies that:
- Silence detection can be enabled/disabled
- Silence threshold is configurable
- Silence duration is configurable
- Auto-stop on silence can be triggered
- Settings persist in config
- UI has silence detection controls
"""

import pytest
from unittest.mock import patch, MagicMock
import time


class TestSilenceDetectionConfig:
    """Test silence detection configuration."""

    def test_window_has_silence_detection_enabled_flag(self, qapp):
        """Test that window has silence detection enabled flag."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'silence_detection_enabled')

    def test_default_silence_detection_disabled(self, qapp, tmp_path):
        """Test that silence detection is disabled by default."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('pathlib.Path.home', return_value=tmp_path):
                window = DictatorWindow(no_tray=True)

                # Should be disabled by default
                assert window.silence_detection_enabled is False

    def test_window_has_silence_threshold(self, qapp):
        """Test that window has configurable silence threshold."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'silence_threshold')

    def test_default_silence_threshold_reasonable(self, qapp):
        """Test that default silence threshold is reasonable."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should be around 5% (very quiet)
            assert 3 <= window.silence_threshold <= 10

    def test_window_has_silence_duration(self, qapp):
        """Test that window has configurable silence duration."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'silence_duration')

    def test_default_silence_duration_reasonable(self, qapp):
        """Test that default silence duration is reasonable (2-3 seconds)."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should be 2-3 seconds
            assert 2.0 <= window.silence_duration <= 3.0

    def test_silence_settings_saved_to_config(self, qapp, tmp_path):
        """Test that silence settings are saved to config."""
        from src.dictator import DictatorWindow
        from pathlib import Path
        import json

        config_file = tmp_path / "config.json"

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.config_path = Path(config_file)

            # Configure silence detection
            window.silence_detection_enabled = True
            window.silence_threshold = 8
            window.silence_duration = 3.0
            window.save_config()

            # Verify in config file
            with open(config_file) as f:
                config = json.load(f)
                assert config.get('silence_detection_enabled') is True
                assert config.get('silence_threshold') == 8
                assert config.get('silence_duration') == 3.0

    def test_silence_settings_loaded_from_config(self, qapp, tmp_path):
        """Test that silence settings are loaded from config."""
        from src.dictator import DictatorWindow
        from pathlib import Path
        import json

        config_file = tmp_path / "config.json"

        # Create config with custom settings
        config = {
            'silence_detection_enabled': True,
            'silence_threshold': 7,
            'silence_duration': 2.5
        }
        with open(config_file, 'w') as f:
            json.dump(config, f)

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.config_path = Path(config_file)
            window.load_config()

            # Should load settings
            assert window.silence_detection_enabled is True
            assert window.silence_threshold == 7
            assert window.silence_duration == 2.5


class TestSilenceDetectionUI:
    """Test UI controls for silence detection."""

    def test_settings_has_silence_detection_checkbox(self, qapp):
        """Test that settings has silence detection enable checkbox."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Should have silence detection checkbox
            assert hasattr(dialog, 'silence_detection_checkbox')

    def test_settings_has_silence_threshold_control(self, qapp):
        """Test that settings has silence threshold control."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Should have threshold control
            assert hasattr(dialog, 'silence_threshold_spin') or hasattr(dialog, 'silence_threshold_slider')

    def test_settings_has_silence_duration_control(self, qapp):
        """Test that settings has silence duration control."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Should have duration control
            assert hasattr(dialog, 'silence_duration_spin') or hasattr(dialog, 'silence_duration_combo')

    def test_silence_checkbox_reflects_current_state(self, qapp):
        """Test that checkbox reflects current enabled state."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.silence_detection_enabled = True
            dialog = SettingsDialog(parent)

            # Should be checked
            assert dialog.silence_detection_checkbox.isChecked() is True

    def test_changing_settings_updates_window(self, qapp):
        """Test that changing settings updates main window."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.silence_detection_enabled = False
            dialog = SettingsDialog(parent)

            # Enable silence detection
            dialog.silence_detection_checkbox.setChecked(True)
            dialog.apply_settings()

            # Should update window
            assert parent.silence_detection_enabled is True

    def test_silence_controls_have_tooltips(self, qapp):
        """Test that silence controls have helpful tooltips."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Checkbox should have tooltip
            tooltip = dialog.silence_detection_checkbox.toolTip()
            assert tooltip and len(tooltip) > 0


class TestSilenceDetectionBehavior:
    """Test silence detection behavior during recording."""

    def test_silence_tracking_during_recording(self, qapp):
        """Test that silence is tracked during recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.silence_detection_enabled = True

            # Should track silence start time
            assert hasattr(window, 'silence_start_time')

    def test_silence_detected_when_below_threshold(self, qapp):
        """Test that silence is detected when audio is below threshold."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.silence_detection_enabled = True
            window.silence_threshold = 5
            window.recorder.is_recording = True

            # Simulate quiet audio
            window.recorder.current_audio_level = 3
            window.check_silence()

            # Should detect silence
            assert window.silence_start_time is not None

    def test_silence_reset_when_audio_detected(self, qapp):
        """Test that silence is reset when audio is detected."""
        from src.dictator import DictatorWindow
        import time

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.silence_detection_enabled = True
            window.silence_threshold = 5
            window.recorder.is_recording = True

            # Start silence
            window.recorder.current_audio_level = 3
            window.check_silence()
            assert window.silence_start_time is not None

            # Audio detected
            window.recorder.current_audio_level = 30
            window.check_silence()

            # Should reset silence
            assert window.silence_start_time is None

    def test_auto_stop_after_silence_duration(self, qapp):
        """Test that recording auto-stops after silence duration."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.silence_detection_enabled = True
            window.silence_threshold = 5
            window.silence_duration = 1.0  # 1 second for testing
            window.recorder.is_recording = True

            # Simulate silence start
            import time
            window.silence_start_time = time.time() - 1.5  # 1.5 seconds ago

            # Simulate continuing silence
            window.recorder.current_audio_level = 3

            with patch.object(window, 'stop_recording') as mock_stop:
                window.check_silence()

                # Should trigger auto-stop
                mock_stop.assert_called_once()

    def test_no_auto_stop_when_disabled(self, qapp):
        """Test that auto-stop doesn't happen when disabled."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.silence_detection_enabled = False  # Disabled
            window.silence_threshold = 5
            window.silence_duration = 1.0
            window.recorder.is_recording = True

            # Simulate long silence
            import time
            window.silence_start_time = time.time() - 5.0

            with patch.object(window, 'stop_recording') as mock_stop:
                window.check_silence()

                # Should NOT trigger auto-stop
                mock_stop.assert_not_called()


class TestSilenceDetectionIntegration:
    """Test integration of silence detection with recording."""

    def test_silence_checked_during_recording(self, qapp):
        """Test that silence is checked while recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have check_silence method
            assert hasattr(window, 'check_silence')
            assert callable(window.check_silence)

    def test_silence_state_resets_on_stop(self, qapp):
        """Test that silence state resets when recording stops."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.silence_detection_enabled = True

            # Set silence state
            import time
            window.silence_start_time = time.time()

            # Stop recording
            window.recorder.is_recording = False
            with patch.object(window.recorder, 'stop_recording'):
                window.stop_recording()

            # Should reset
            assert window.silence_start_time is None

    def test_silence_detection_persists_across_restarts(self, qapp, tmp_path):
        """Test that silence detection settings persist."""
        from src.dictator import DictatorWindow
        from pathlib import Path

        config_dir = tmp_path / ".config" / "dictator"
        config_dir.mkdir(parents=True)

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('pathlib.Path.home', return_value=tmp_path):
                # First instance
                window1 = DictatorWindow(no_tray=True)
                window1.silence_detection_enabled = True
                window1.silence_threshold = 6
                window1.save_config()

                # Second instance
                window2 = DictatorWindow(no_tray=True)
                assert window2.silence_detection_enabled is True
                assert window2.silence_threshold == 6
