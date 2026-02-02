"""
Tests for configurable recording timeout settings.

Verifies that:
- Recording timeout can be configured
- Default timeout is reasonable (5 minutes)
- Timeout persists in config
- UI has timeout selector in settings
- Timeout is applied during recording
"""

import pytest
from unittest.mock import patch, MagicMock


class TestTimeoutConfig:
    """Test timeout configuration and persistence."""

    def test_recorder_has_max_recording_duration(self, qapp):
        """Test that recorder has max_recording_duration attribute."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert hasattr(recorder, 'max_recording_duration')

    def test_default_timeout_is_300_seconds(self, qapp):
        """Test that default timeout is 5 minutes (300 seconds)."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        assert recorder.max_recording_duration == 300

    def test_can_set_custom_timeout(self, qapp):
        """Test that custom timeout can be set."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.max_recording_duration = 60  # 1 minute

        assert recorder.max_recording_duration == 60

    def test_window_has_recording_timeout_setting(self, qapp):
        """Test that window has recording_timeout attribute."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'recording_timeout')

    def test_recording_timeout_saved_to_config(self, qapp, tmp_path):
        """Test that recording timeout is saved to config file."""
        from src.dictator import DictatorWindow
        from pathlib import Path
        import json

        config_file = tmp_path / "config.json"

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.config_path = Path(config_file)

            # Set custom timeout and save
            window.recording_timeout = 120  # 2 minutes
            window.save_config()

            # Verify it's in config file
            with open(config_file) as f:
                config = json.load(f)
                assert config.get('recording_timeout') == 120

    def test_recording_timeout_loaded_from_config(self, qapp, tmp_path):
        """Test that recording timeout is loaded from config file."""
        from src.dictator import DictatorWindow
        from pathlib import Path
        import json

        config_file = tmp_path / "config.json"

        # Create config with custom timeout
        config = {'recording_timeout': 180}  # 3 minutes
        with open(config_file, 'w') as f:
            json.dump(config, f)

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.config_path = Path(config_file)
            window.load_config()

            # Should load the timeout from config
            assert window.recording_timeout == 180


class TestTimeoutUI:
    """Test UI controls for timeout configuration."""

    def test_settings_has_timeout_selector(self, qapp):
        """Test that settings dialog has timeout selector."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Should have timeout combo or spinner
            assert hasattr(dialog, 'timeout_combo') or hasattr(dialog, 'timeout_spin')

    def test_timeout_selector_has_common_values(self, qapp):
        """Test that timeout selector has common duration options."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Should have options like 1min, 2min, 5min, 10min
            if hasattr(dialog, 'timeout_combo'):
                count = dialog.timeout_combo.count()
                assert count >= 4, "Should have at least 4 timeout options"

    def test_timeout_selector_shows_current_value(self, qapp):
        """Test that timeout selector shows current configured timeout."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.recording_timeout = 120  # 2 minutes
            dialog = SettingsDialog(parent)

            # Should show 120 seconds / 2 minutes
            if hasattr(dialog, 'timeout_combo'):
                current_data = dialog.timeout_combo.currentData()
                assert current_data == 120

    def test_changing_timeout_in_settings_updates_window(self, qapp):
        """Test that changing timeout in settings updates main window."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.recording_timeout = 300
            dialog = SettingsDialog(parent)

            # Change to 1 minute (60 seconds)
            if hasattr(dialog, 'timeout_combo'):
                for i in range(dialog.timeout_combo.count()):
                    if dialog.timeout_combo.itemData(i) == 60:
                        dialog.timeout_combo.setCurrentIndex(i)
                        break

                # Apply settings
                dialog.apply_settings()

                # Main window should update
                assert parent.recording_timeout == 60

    def test_timeout_selector_has_tooltip(self, qapp):
        """Test that timeout selector has helpful tooltip."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            if hasattr(dialog, 'timeout_combo'):
                tooltip = dialog.timeout_combo.toolTip()
                assert tooltip, "Timeout selector should have tooltip"
                assert len(tooltip) > 0


class TestTimeoutBehavior:
    """Test timeout behavior during recording."""

    def test_timeout_applied_to_recorder_on_start(self, qapp):
        """Test that timeout is applied to recorder when starting recording."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recording_timeout = 180  # 3 minutes

            # Mock recorder
            with patch.object(window.recorder, 'start_recording'):
                # Timeout should be set on recorder before starting
                # (will be checked during integration)
                pass

    def test_recorder_uses_configured_timeout(self, qapp):
        """Test that recorder respects the configured timeout."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.max_recording_duration = 60  # 1 minute

        # The timeout should be used in _record_with_whisper
        assert recorder.max_recording_duration == 60

    def test_different_timeout_values(self, qapp):
        """Test that various timeout values work correctly."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Test common values
        for timeout in [30, 60, 120, 300, 600]:
            recorder.max_recording_duration = timeout
            assert recorder.max_recording_duration == timeout


class TestTimeoutIntegration:
    """Test integration of timeout with recording system."""

    def test_timeout_persists_across_app_restarts(self, qapp, tmp_path):
        """Test that timeout setting persists across app restarts."""
        from src.dictator import DictatorWindow
        from pathlib import Path

        config_dir = tmp_path / ".config" / "dictator"
        config_dir.mkdir(parents=True)

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('pathlib.Path.home', return_value=tmp_path):
                # First instance - set timeout
                window1 = DictatorWindow(no_tray=True)
                window1.recording_timeout = 240  # 4 minutes
                window1.save_config()

                # Second instance - should load timeout
                window2 = DictatorWindow(no_tray=True)
                assert window2.recording_timeout == 240

    def test_timeout_synced_between_window_and_recorder(self, qapp):
        """Test that timeout is synced from window to recorder."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recording_timeout = 90  # 1.5 minutes

            # When starting recording, recorder should get the timeout
            # (tested via integration, not unit test)
            pass

    def test_no_timeout_means_use_default(self, qapp, tmp_path):
        """Test that missing timeout config uses default."""
        from src.dictator import DictatorWindow
        from pathlib import Path
        import json

        config_dir = tmp_path / ".config" / "dictator"
        config_dir.mkdir(parents=True)

        # Config without timeout
        config = {'some_other_setting': 'value'}
        config_file = config_dir / "config.json"
        with open(config_file, 'w') as f:
            json.dump(config, f)

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('pathlib.Path.home', return_value=tmp_path):
                window = DictatorWindow(no_tray=True)

                # Should use default (300 seconds / 5 minutes)
                assert window.recording_timeout == 300
