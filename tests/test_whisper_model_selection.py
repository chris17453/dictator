"""
Tests for Whisper model selection feature.

Verifies that:
- Model selection UI works correctly
- Settings are saved and loaded properly
- Model is reloaded when settings change
- Model selection persists across restarts
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path


class TestWhisperModelUI:
    """Test the model selection UI components."""

    def test_model_combo_exists(self, qapp):
        """Test that model combo box exists in settings UI."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.whisper_model_size = 'tiny'
            parent.whisper_model_dir = str(Path.home() / ".config" / "dictator" / "models")
            parent.whisper_device = 'auto'

            dialog = SettingsDialog(parent)

            # Should have model combo box
            assert hasattr(dialog, 'model_combo')
            assert dialog.model_combo is not None

    def test_model_combo_has_all_models(self, qapp):
        """Test that model combo includes all available models."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.whisper_model_size = 'tiny'
            parent.whisper_model_dir = str(Path.home() / ".config" / "dictator" / "models")
            parent.whisper_device = 'auto'

            dialog = SettingsDialog(parent)

            # Get all items from combo
            models = [dialog.model_combo.itemText(i) for i in range(dialog.model_combo.count())]

            # Should include standard model sizes
            assert 'tiny' in models
            assert 'base' in models
            assert 'small' in models
            assert 'medium' in models
            assert 'large-v2' in models or 'large-v3' in models

    def test_model_combo_loads_current_setting(self, qapp):
        """Test that model combo shows current setting."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.whisper_model_size = 'small'
            parent.whisper_model_dir = str(Path.home() / ".config" / "dictator" / "models")
            parent.whisper_device = 'auto'

            dialog = SettingsDialog(parent)

            # Should show 'small' as current selection
            assert dialog.model_combo.currentText() == 'small'


class TestModelSaving:
    """Test model setting persistence."""

    def test_save_whisper_settings_updates_parent(self, qapp):
        """Test that saving settings updates parent window."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.whisper_model_size = 'tiny'
            parent.whisper_model_dir = str(Path.home() / ".config" / "dictator" / "models")
            parent.whisper_device = 'auto'

            dialog = SettingsDialog(parent)

            # Change model selection
            dialog.model_combo.setCurrentText('base')

            # Save settings
            dialog.save_whisper_settings()

            # Parent should be updated
            assert parent.whisper_model_size == 'base'

    def test_save_whisper_settings_updates_recorder(self, qapp):
        """Test that saving settings updates recorder."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.whisper_model_size = 'tiny'
            parent.whisper_model_dir = str(Path.home() / ".config" / "dictator" / "models")
            parent.whisper_device = 'auto'

            dialog = SettingsDialog(parent)

            # Change model selection
            dialog.model_combo.setCurrentText('medium')

            # Save settings
            dialog.save_whisper_settings()

            # Recorder should be updated
            assert parent.recorder.whisper_model_size == 'medium'

    def test_save_whisper_settings_reloads_model(self, qapp):
        """Test that saving settings triggers model reload."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.whisper_model_size = 'tiny'
            parent.whisper_model_dir = str(Path.home() / ".config" / "dictator" / "models")
            parent.whisper_device = 'auto'

            # Patch the instance method
            with patch.object(parent.recorder, 'load_whisper_model') as mock_load:
                dialog = SettingsDialog(parent)

                # Change model selection
                dialog.model_combo.setCurrentText('base')

                # Save settings
                dialog.save_whisper_settings()

                # Should have triggered model reload
                mock_load.assert_called_once()


class TestModelLoading:
    """Test model loading and reloading."""

    def test_load_whisper_model_uses_model_size(self):
        """Test that load_whisper_model uses the whisper_model_size attribute."""
        from src.recorder import PureRecorder

        with patch('faster_whisper.WhisperModel') as mock_whisper:
            mock_whisper.return_value = Mock()

            recorder = PureRecorder()
            recorder.whisper_model_size = 'small'
            recorder.whisper_device = 'cpu'

            recorder.load_whisper_model()

            # Should have loaded 'small' model
            mock_whisper.assert_called()
            # Find call with 'small' as first arg
            calls = [c for c in mock_whisper.call_args_list if c[0][0] == 'small']
            assert len(calls) > 0, "Expected WhisperModel to be called with 'small'"

    def test_model_reload_changes_model_size(self):
        """Test that reloading model with different size works."""
        from src.recorder import PureRecorder

        with patch('faster_whisper.WhisperModel') as mock_whisper:
            mock_whisper.return_value = Mock()

            recorder = PureRecorder()
            recorder.whisper_model_size = 'tiny'
            recorder.whisper_device = 'cpu'
            recorder.load_whisper_model()

            # Change size and reload
            recorder.whisper_model_size = 'base'
            recorder.load_whisper_model()

            # Should have been called with both sizes
            assert mock_whisper.call_count >= 2
            # Verify we called with both tiny and base
            all_calls = [c[0][0] for c in mock_whisper.call_args_list]
            assert 'tiny' in all_calls
            assert 'base' in all_calls


class TestConfigPersistence:
    """Test that model selection persists across restarts."""

    def test_config_saves_model_size(self, qapp):
        """Test that config saves whisper_model_size."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('builtins.open', create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file

                window = DictatorWindow(no_tray=True)
                window.whisper_model_size = 'medium'

                # Save config
                window.save_config()

                # Should have saved model size
                # Check that 'whisper_model_size' was written
                written_content = ''.join(str(call) for call in mock_file.write.call_args_list)
                assert 'whisper_model_size' in written_content

    def test_config_loads_model_size(self, qapp, tmp_path):
        """Test that config loads whisper_model_size on startup."""
        from src.dictator import DictatorWindow
        import json

        # Create config file with model size
        config_dir = tmp_path / ".config" / "dictator"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        config_data = {
            'whisper_model_size': 'large-v2',
            'whisper_model_dir': str(Path.home() / ".config" / "dictator" / "models"),
            'whisper_device': 'cpu'
        }
        config_file.write_text(json.dumps(config_data))

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('src.dictator.Path.home', return_value=tmp_path):
                window = DictatorWindow(no_tray=True)
                window.load_config()

                # Should have loaded the saved model size
                assert window.whisper_model_size == 'large-v2'


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_change_model_in_ui_affects_transcription(self, qapp):
        """Test that changing model in UI affects actual transcription."""
        from src.dictator import DictatorWindow
        from src.settings_ui import SettingsDialog

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.recorder.whisper_device = 'cpu'

            # Mock the load_whisper_model method to track calls
            with patch.object(window.recorder, 'load_whisper_model') as mock_load:
                # Open settings
                settings = SettingsDialog(window)

                # Change model
                settings.model_combo.setCurrentText('medium')
                settings.save_whisper_settings()

                # Close settings
                qapp.processEvents()

                # Recorder should have medium model loaded
                assert window.recorder.whisper_model_size == 'medium'
                # Model should have been reloaded
                mock_load.assert_called_once()
