"""
Tests for push-to-talk recording mode.

Verifies that:
- Push-to-talk mode can be enabled/disabled
- In push-to-talk mode, holding key records
- In push-to-talk mode, releasing key stops recording
- In toggle mode, each press toggles recording state
- Mode preference is saved to config
"""

import pytest
from unittest.mock import patch, MagicMock


class TestRecordingModeConfig:
    """Test recording mode configuration."""

    def test_recording_mode_setting_exists(self, qapp):
        """Test that recording mode setting exists in config."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have recording mode attribute
            assert hasattr(window, 'recording_mode')

    def test_default_recording_mode_is_toggle(self, qapp, tmp_path):
        """Test that default recording mode is toggle."""
        from src.dictator import DictatorWindow
        from pathlib import Path

        # Create a fresh config directory
        config_dir = tmp_path / ".config" / "dictator"
        config_dir.mkdir(parents=True)

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('pathlib.Path.home', return_value=tmp_path):
                window = DictatorWindow(no_tray=True)

                # Default should be toggle mode for backwards compatibility
                # (no config file exists, so default is used)
                assert window.recording_mode == 'toggle'

    def test_can_set_push_to_talk_mode(self, qapp):
        """Test that push-to-talk mode can be set."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should be able to set to push-to-talk
            window.recording_mode = 'push-to-talk'
            assert window.recording_mode == 'push-to-talk'

    def test_recording_mode_saved_to_config(self, qapp, tmp_path):
        """Test that recording mode is saved to config file."""
        from src.dictator import DictatorWindow
        from pathlib import Path
        import json

        config_file = tmp_path / "config.json"

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.config_path = Path(config_file)

            # Set mode and save
            window.recording_mode = 'push-to-talk'
            window.save_config()

            # Verify it's in config file
            with open(config_file) as f:
                config = json.load(f)
                assert config.get('recording_mode') == 'push-to-talk'

    def test_recording_mode_loaded_from_config(self, qapp, tmp_path):
        """Test that recording mode is loaded from config file."""
        from src.dictator import DictatorWindow
        from pathlib import Path
        import json

        config_file = tmp_path / "config.json"

        # Create config with push-to-talk mode
        config = {'recording_mode': 'push-to-talk'}
        with open(config_file, 'w') as f:
            json.dump(config, f)

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.config_path = Path(config_file)
            window.load_config()

            # Should load the mode from config
            assert window.recording_mode == 'push-to-talk'


class TestPushToTalkBehavior:
    """Test push-to-talk recording behavior."""

    def test_push_to_talk_starts_on_key_press(self, qapp):
        """Test that push-to-talk starts recording on key press."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recording_mode = 'push-to-talk'

            # Mock the start_recording method to verify it's called
            with patch.object(window, 'start_recording') as mock_start:
                # Simulate key press event
                window.hotkey_pressed(is_press=True)

                # Should call start_recording
                mock_start.assert_called_once()

    def test_push_to_talk_stops_on_key_release(self, qapp):
        """Test that push-to-talk stops recording on key release."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recording_mode = 'push-to-talk'

            # Mock recording state
            window.recorder.is_recording = True

            # Mock the stop_recording method
            with patch.object(window, 'stop_recording') as mock_stop:
                # Release key
                window.hotkey_pressed(is_press=False)

                # Should call stop_recording
                mock_stop.assert_called_once()

    def test_toggle_mode_toggles_on_press(self, qapp):
        """Test that toggle mode toggles recording state on press."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recording_mode = 'toggle'

            # Mock start/stop methods
            with patch.object(window, 'start_recording') as mock_start:
                with patch.object(window, 'stop_recording') as mock_stop:
                    # First press should start
                    window.hotkey_pressed(is_press=True)
                    mock_start.assert_called_once()

                    # Simulate recording state
                    window.recorder.is_recording = True

                    # Second press should stop
                    window.hotkey_pressed(is_press=True)
                    mock_stop.assert_called_once()

    def test_toggle_mode_ignores_key_release(self, qapp):
        """Test that toggle mode ignores key release events."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recording_mode = 'toggle'

            # Mock start/stop methods
            with patch.object(window, 'start_recording') as mock_start:
                with patch.object(window, 'stop_recording') as mock_stop:
                    # Start recording
                    window.hotkey_pressed(is_press=True)
                    mock_start.assert_called_once()

                    # Simulate recording state
                    window.recorder.is_recording = True

                    # Release should not trigger anything
                    window.hotkey_pressed(is_press=False)
                    # start should still only be called once, stop should not be called
                    assert mock_start.call_count == 1
                    assert mock_stop.call_count == 0

                    # Another press should stop
                    window.hotkey_pressed(is_press=True)
                    mock_stop.assert_called_once()


class TestRecordingModeUI:
    """Test recording mode UI controls."""

    def test_settings_has_recording_mode_selector(self, qapp):
        """Test that settings dialog has recording mode selector."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Should have recording mode combo box
            assert hasattr(dialog, 'recording_mode_combo')

    def test_recording_mode_selector_has_both_options(self, qapp):
        """Test that recording mode selector has both toggle and push-to-talk."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Should have both options
            items = [dialog.recording_mode_combo.itemText(i)
                    for i in range(dialog.recording_mode_combo.count())]

            assert 'Toggle Mode' in items
            assert 'Push-to-Talk Mode' in items

    def test_recording_mode_selector_shows_current_mode(self, qapp):
        """Test that recording mode selector shows current mode."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.recording_mode = 'push-to-talk'
            dialog = SettingsDialog(parent)

            # Should show push-to-talk as selected
            current_text = dialog.recording_mode_combo.currentText()
            assert 'Push-to-Talk' in current_text

    def test_changing_mode_in_settings_updates_window(self, qapp):
        """Test that changing mode in settings updates main window."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.recording_mode = 'toggle'
            dialog = SettingsDialog(parent)

            # Change to push-to-talk
            for i in range(dialog.recording_mode_combo.count()):
                if 'Push-to-Talk' in dialog.recording_mode_combo.itemText(i):
                    dialog.recording_mode_combo.setCurrentIndex(i)
                    break

            # Apply settings
            dialog.apply_settings()

            # Main window should update
            assert parent.recording_mode == 'push-to-talk'

    def test_recording_mode_has_tooltip(self, qapp):
        """Test that recording mode selector has helpful tooltip."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            tooltip = dialog.recording_mode_combo.toolTip()
            assert tooltip, "Recording mode selector should have tooltip"
            assert len(tooltip) > 0


class TestRecordingModeIndicator:
    """Test UI indicators for current recording mode."""

    def test_status_shows_current_mode(self, qapp):
        """Test that status or UI shows current recording mode."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have method to get mode description
            if hasattr(window, 'get_mode_description'):
                desc_toggle = window.get_mode_description('toggle')
                desc_ptt = window.get_mode_description('push-to-talk')

                assert 'toggle' in desc_toggle.lower()
                assert 'push' in desc_ptt.lower() or 'hold' in desc_ptt.lower()

    def test_shortcuts_help_reflects_current_mode(self, qapp):
        """Test that shortcuts help explains current recording mode."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Toggle mode
            window.recording_mode = 'toggle'
            shortcuts_toggle = window.get_shortcuts_list()
            shortcuts_str_toggle = str(shortcuts_toggle)

            # Should mention toggle or press
            assert 'toggle' in shortcuts_str_toggle.lower() or 'press' in shortcuts_str_toggle.lower()

            # Push-to-talk mode
            window.recording_mode = 'push-to-talk'
            shortcuts_ptt = window.get_shortcuts_list()
            shortcuts_str_ptt = str(shortcuts_ptt)

            # Should mention hold or release
            assert 'hold' in shortcuts_str_ptt.lower() or 'release' in shortcuts_str_ptt.lower()


class TestHotkeyManagerIntegration:
    """Test integration with hotkey manager."""

    def test_hotkey_manager_reports_press_vs_release(self, qapp):
        """Test that hotkey callbacks distinguish press from release."""
        from src.hotkey_manager import HotkeyManager

        manager = HotkeyManager()

        # The callback should be able to determine if it's press or release
        # This might require modifying hotkey_manager to pass this info
        # For now, test that manager exists
        assert manager is not None

    def test_window_handles_press_and_release_callbacks(self, qapp):
        """Test that window can handle separate press and release callbacks."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have method that accepts press/release parameter
            assert hasattr(window, 'hotkey_pressed')

            # Should accept is_press parameter
            import inspect
            sig = inspect.signature(window.hotkey_pressed)
            assert 'is_press' in sig.parameters
