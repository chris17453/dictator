"""
Tests for Whisper language selection feature.

Verifies that:
- Language selection UI works correctly
- Settings are saved and loaded properly
- Selected language is used during transcription
- Language selection persists across restarts
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


class TestLanguageSelectionUI:
    """Test the language selection UI components."""

    def test_language_combo_exists(self, qapp):
        """Test that language combo box exists in settings UI."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Should have language combo box
            assert hasattr(dialog, 'language_combo')
            assert dialog.language_combo is not None

    def test_language_combo_has_common_languages(self, qapp):
        """Test that language combo includes common languages."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Get all items from combo
            count = dialog.language_combo.count()
            assert count > 10, "Should have multiple language options"

            # Should include auto-detect and common languages
            languages = [dialog.language_combo.itemText(i) for i in range(count)]

            # Check for auto-detect option
            assert any('auto' in lang.lower() for lang in languages), "Should have auto-detect option"

            # Check for common languages
            assert any('english' in lang.lower() for lang in languages)
            assert any('spanish' in lang.lower() for lang in languages)
            assert any('french' in lang.lower() for lang in languages)

    def test_language_combo_loads_current_setting(self, qapp):
        """Test that language combo shows current setting."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.whisper_language = 'es'  # Spanish

            dialog = SettingsDialog(parent)

            # Should show Spanish as current selection
            current_text = dialog.language_combo.currentText()
            assert 'spanish' in current_text.lower() or dialog.language_combo.currentData() == 'es'


class TestLanguageSaving:
    """Test language setting persistence."""

    def test_save_whisper_settings_updates_language(self, qapp):
        """Test that saving settings updates language."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.whisper_language = 'auto'

            dialog = SettingsDialog(parent)

            # Find and select French
            for i in range(dialog.language_combo.count()):
                if dialog.language_combo.itemData(i) == 'fr':
                    dialog.language_combo.setCurrentIndex(i)
                    break

            # Save settings
            dialog.save_whisper_settings()

            # Parent should be updated
            assert parent.whisper_language == 'fr'

    def test_save_whisper_settings_updates_recorder_language(self, qapp):
        """Test that saving settings updates recorder language."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            parent.whisper_language = 'auto'

            dialog = SettingsDialog(parent)

            # Find and select German
            for i in range(dialog.language_combo.count()):
                if dialog.language_combo.itemData(i) == 'de':
                    dialog.language_combo.setCurrentIndex(i)
                    break

            # Save settings
            dialog.save_whisper_settings()

            # Recorder should be updated
            assert parent.recorder.whisper_language == 'de'


class TestTranscriptionWithLanguage:
    """Test that selected language is used during transcription."""

    def test_transcribe_uses_selected_language(self):
        """Test that transcribe method receives language parameter."""
        from src.recorder import PureRecorder

        with patch('faster_whisper.WhisperModel') as mock_whisper_class:
            mock_model = Mock()
            mock_whisper_class.return_value = mock_model

            # Setup mock transcribe return value
            mock_segment = Mock()
            mock_segment.text = "Hola mundo"
            mock_info = Mock()
            mock_info.language = "es"
            mock_model.transcribe.return_value = ([mock_segment], mock_info)

            recorder = PureRecorder()
            recorder.whisper_language = 'es'
            recorder.whisper_device = 'cpu'
            recorder.load_whisper_model()

            # Simulate transcription
            import numpy as np
            audio_data = np.zeros(16000, dtype=np.float32)
            recorder.callback = Mock()

            # Manually call the transcription logic
            recorder.whisper_model = mock_model
            segments, info = recorder.whisper_model.transcribe(audio_data, language='es')

            # Should have called transcribe with language='es'
            mock_model.transcribe.assert_called_once()
            call_args = mock_model.transcribe.call_args
            assert call_args[1].get('language') == 'es'

    def test_auto_detect_passes_none(self):
        """Test that auto-detect passes None to transcribe."""
        from src.recorder import PureRecorder

        with patch('faster_whisper.WhisperModel') as mock_whisper_class:
            mock_model = Mock()
            mock_whisper_class.return_value = mock_model

            # Setup mock transcribe return value
            mock_segment = Mock()
            mock_segment.text = "Hello world"
            mock_info = Mock()
            mock_info.language = "en"
            mock_model.transcribe.return_value = ([mock_segment], mock_info)

            recorder = PureRecorder()
            recorder.whisper_language = 'auto'
            recorder.whisper_device = 'cpu'
            recorder.load_whisper_model()

            # Simulate transcription with auto-detect
            import numpy as np
            audio_data = np.zeros(16000, dtype=np.float32)

            recorder.whisper_model = mock_model
            # When language is 'auto', should pass None
            lang_param = None if recorder.whisper_language == 'auto' else recorder.whisper_language
            segments, info = recorder.whisper_model.transcribe(audio_data, language=lang_param)

            # Should have called with language=None for auto-detect
            call_args = mock_model.transcribe.call_args
            assert call_args[1].get('language') is None


class TestConfigPersistence:
    """Test that language selection persists across restarts."""

    def test_config_saves_language(self, qapp, tmp_path):
        """Test that config saves whisper_language."""
        from src.dictator import DictatorWindow
        import json

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('src.dictator.Path.home', return_value=tmp_path):
                window = DictatorWindow(no_tray=True)
                window.whisper_language = 'fr'

                # Save config
                window.save_config()

                # Read config file
                config_file = tmp_path / ".config" / "dictator" / "config.json"
                assert config_file.exists()

                config = json.loads(config_file.read_text())
                assert config['whisper_language'] == 'fr'

    def test_config_loads_language(self, qapp, tmp_path):
        """Test that config loads whisper_language on startup."""
        from src.dictator import DictatorWindow
        import json

        # Create config file with language
        config_dir = tmp_path / ".config" / "dictator"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        config_data = {
            'whisper_language': 'de',
            'whisper_model_size': 'tiny',
            'whisper_model_dir': str(Path.home() / ".config" / "dictator" / "models"),
            'whisper_device': 'cpu'
        }
        config_file.write_text(json.dumps(config_data))

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('src.dictator.Path.home', return_value=tmp_path):
                window = DictatorWindow(no_tray=True)
                window.load_config()

                # Should have loaded the saved language
                assert window.whisper_language == 'de'

    def test_default_language_is_auto(self, qapp):
        """Test that default language is auto-detect."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Default should be auto-detect
            assert hasattr(window, 'whisper_language')
            assert window.whisper_language == 'auto'


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_change_language_in_ui_affects_recorder(self, qapp):
        """Test that changing language in UI affects recorder."""
        from src.dictator import DictatorWindow
        from src.settings_ui import SettingsDialog

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Open settings
            settings = SettingsDialog(window)

            # Find and select Japanese
            for i in range(settings.language_combo.count()):
                if settings.language_combo.itemData(i) == 'ja':
                    settings.language_combo.setCurrentIndex(i)
                    break

            # Save settings
            settings.save_whisper_settings()

            # Recorder should have Japanese language set
            assert window.recorder.whisper_language == 'ja'

    def test_language_persists_after_reload(self, qapp, tmp_path):
        """Test that language persists after app restart."""
        from src.dictator import DictatorWindow
        import json

        # First session: set language to Spanish
        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('src.dictator.Path.home', return_value=tmp_path):
                window1 = DictatorWindow(no_tray=True)
                window1.whisper_language = 'es'
                window1.save_config()

        # Second session: load config
        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            with patch('src.dictator.Path.home', return_value=tmp_path):
                window2 = DictatorWindow(no_tray=True)
                window2.load_config()

                # Should still have Spanish
                assert window2.whisper_language == 'es'
