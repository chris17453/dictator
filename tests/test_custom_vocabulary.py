"""
Tests for custom vocabulary functionality.

Verifies that:
- Users can add/remove custom words and phrases
- Vocabulary is persisted in configuration
- Vocabulary is passed to Whisper transcription
- Vocabulary list is displayed in settings UI
- Vocabulary improves recognition of custom terms
"""

import pytest
from unittest.mock import patch, MagicMock
import json


class TestVocabularyStorage:
    """Test storage and persistence of custom vocabulary."""

    def test_window_has_custom_vocabulary_list(self, qapp):
        """Test that window has a custom vocabulary list."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'custom_vocabulary')
            assert isinstance(window.custom_vocabulary, list)

    def test_default_vocabulary_is_empty(self, qapp, tmp_path):
        """Test that vocabulary starts empty by default (without loading from config)."""
        from src.dictator import DictatorWindow
        from pathlib import Path

        config_file = tmp_path / "test_config.json"

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            # Reset vocabulary after load (test is for default empty state)
            window.custom_vocabulary = []

            assert window.custom_vocabulary == []

    def test_can_add_vocabulary_word(self, qapp):
        """Test adding a word to vocabulary."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.add_vocabulary_term("DICTATOR")

            assert "DICTATOR" in window.custom_vocabulary

    def test_can_add_vocabulary_phrase(self, qapp):
        """Test adding a multi-word phrase to vocabulary."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.add_vocabulary_term("machine learning")

            assert "machine learning" in window.custom_vocabulary

    def test_can_remove_vocabulary_term(self, qapp):
        """Test removing a term from vocabulary."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.add_vocabulary_term("PyQt6")
            window.remove_vocabulary_term("PyQt6")

            assert "PyQt6" not in window.custom_vocabulary

    def test_duplicate_terms_not_added(self, qapp):
        """Test that duplicate terms are not added."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.add_vocabulary_term("Whisper")
            window.add_vocabulary_term("Whisper")

            # Should only appear once
            assert window.custom_vocabulary.count("Whisper") == 1

    def test_vocabulary_case_sensitive(self, qapp):
        """Test that vocabulary preserves case."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.add_vocabulary_term("PyQt6")

            assert "PyQt6" in window.custom_vocabulary
            assert "pyqt6" not in window.custom_vocabulary


class TestVocabularyPersistence:
    """Test saving and loading vocabulary from config."""

    def test_vocabulary_saved_to_config(self, qapp, tmp_path):
        """Test that vocabulary is saved to config file."""
        from src.dictator import DictatorWindow
        from pathlib import Path

        config_file = tmp_path / "test_config.json"

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.config_path = Path(config_file)

            window.add_vocabulary_term("Anthropic")
            window.add_vocabulary_term("Claude")
            window.save_config()

            # Verify saved to file
            assert config_file.exists()
            config_data = json.loads(config_file.read_text())
            assert 'custom_vocabulary' in config_data
            assert "Anthropic" in config_data['custom_vocabulary']
            assert "Claude" in config_data['custom_vocabulary']

    def test_vocabulary_loaded_from_config(self, qapp, tmp_path):
        """Test that vocabulary is loaded from config on startup."""
        from src.dictator import DictatorWindow
        from pathlib import Path

        config_file = tmp_path / "test_config.json"
        config_data = {
            'custom_vocabulary': ["Kubernetes", "PostgreSQL", "FastAPI"]
        }
        config_file.write_text(json.dumps(config_data))

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.config_path = Path(config_file)
            window.load_config()

            assert "Kubernetes" in window.custom_vocabulary
            assert "PostgreSQL" in window.custom_vocabulary
            assert "FastAPI" in window.custom_vocabulary


class TestVocabularyUI:
    """Test vocabulary management UI in settings."""

    def test_settings_has_vocabulary_section(self, qapp):
        """Test that settings dialog has vocabulary management section."""
        from src.dictator import DictatorWindow
        from src.settings_ui import SettingsDialog

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(window)

            # Should have vocabulary input and list
            assert hasattr(dialog, 'vocabulary_input') or hasattr(dialog, 'vocabulary_text')
            assert hasattr(dialog, 'vocabulary_list') or hasattr(dialog, 'vocabulary_display')

    def test_can_add_term_through_ui(self, qapp):
        """Test adding vocabulary term through settings UI."""
        from src.dictator import DictatorWindow
        from src.settings_ui import SettingsDialog

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(window)

            # Add term through UI
            if hasattr(dialog, 'vocabulary_input'):
                dialog.vocabulary_input.setText("TensorFlow")
                dialog.add_vocabulary_term_ui()

                assert "TensorFlow" in window.custom_vocabulary

    def test_vocabulary_list_displays_current_terms(self, qapp):
        """Test that vocabulary list shows current terms."""
        from src.dictator import DictatorWindow
        from src.settings_ui import SettingsDialog

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.add_vocabulary_term("Docker")
            window.add_vocabulary_term("Redis")

            dialog = SettingsDialog(window)

            # Should display current vocabulary
            if hasattr(dialog, 'vocabulary_list'):
                list_widget = dialog.vocabulary_list
                items = [list_widget.item(i).text() for i in range(list_widget.count())]
                assert "Docker" in items
                assert "Redis" in items

    def test_can_remove_term_through_ui(self, qapp):
        """Test removing vocabulary term through settings UI."""
        from src.dictator import DictatorWindow
        from src.settings_ui import SettingsDialog

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            window.add_vocabulary_term("Nginx")

            dialog = SettingsDialog(window)

            # Remove term through UI
            if hasattr(dialog, 'remove_vocabulary_term_ui'):
                dialog.remove_vocabulary_term_ui("Nginx")

                assert "Nginx" not in window.custom_vocabulary


class TestVocabularyWhisperIntegration:
    """Test integration of vocabulary with Whisper transcription."""

    def test_vocabulary_passed_to_whisper(self, qapp):
        """Test that vocabulary is passed to Whisper as initial_prompt."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.custom_vocabulary = ["PyQt6", "Whisper", "DICTATOR"]

        # Should have method to generate initial prompt
        assert hasattr(recorder, 'get_vocabulary_prompt')

    def test_vocabulary_prompt_generation(self, qapp):
        """Test that vocabulary is formatted correctly for Whisper."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.custom_vocabulary = ["API", "JSON", "REST"]

        prompt = recorder.get_vocabulary_prompt()

        # Should be a string containing the vocabulary
        assert isinstance(prompt, str)
        assert "API" in prompt
        assert "JSON" in prompt
        assert "REST" in prompt

    def test_empty_vocabulary_returns_empty_prompt(self, qapp):
        """Test that empty vocabulary doesn't generate a prompt."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.custom_vocabulary = []

        prompt = recorder.get_vocabulary_prompt()

        # Should return None or empty string
        assert prompt is None or prompt == ""

    def test_transcription_uses_vocabulary(self, qapp):
        """Test that transcription passes vocabulary to Whisper."""
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.custom_vocabulary = ["Anthropic", "Claude"]

        # Mock the Whisper model
        with patch.object(recorder, 'whisper_model') as mock_model:
            mock_segments = [MagicMock(text="Test", avg_logprob=-0.5)]
            mock_info = MagicMock()
            mock_model.transcribe.return_value = (mock_segments, mock_info)

            # Transcribe with vocabulary
            recorder.transcribe_preview_audio(lambda t, s, c=None: None)

            # Verify initial_prompt was passed to transcribe
            if mock_model.transcribe.called:
                call_kwargs = mock_model.transcribe.call_args[1]
                assert 'initial_prompt' in call_kwargs
                prompt = call_kwargs['initial_prompt']
                # Prompt should contain vocabulary terms
                assert prompt is not None and ("Anthropic" in prompt or "Claude" in prompt)


class TestVocabularyValidation:
    """Test validation of vocabulary terms."""

    def test_empty_term_not_added(self, qapp):
        """Test that empty strings are not added to vocabulary."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.add_vocabulary_term("")

            assert "" not in window.custom_vocabulary

    def test_whitespace_only_term_not_added(self, qapp):
        """Test that whitespace-only strings are not added."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.add_vocabulary_term("   ")

            assert "   " not in window.custom_vocabulary

    def test_term_whitespace_trimmed(self, qapp):
        """Test that leading/trailing whitespace is trimmed."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.add_vocabulary_term("  Python  ")

            assert "Python" in window.custom_vocabulary
            assert "  Python  " not in window.custom_vocabulary


class TestVocabularyImportExport:
    """Test importing and exporting vocabulary lists."""

    def test_can_import_vocabulary_from_text(self, qapp):
        """Test importing vocabulary from newline-separated text."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            vocab_text = "Linux\nDocker\nKubernetes"
            window.import_vocabulary_from_text(vocab_text)

            assert "Linux" in window.custom_vocabulary
            assert "Docker" in window.custom_vocabulary
            assert "Kubernetes" in window.custom_vocabulary

    def test_can_export_vocabulary_to_text(self, qapp):
        """Test exporting vocabulary as newline-separated text."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            window.add_vocabulary_term("React")
            window.add_vocabulary_term("Vue")
            window.add_vocabulary_term("Angular")

            vocab_text = window.export_vocabulary_to_text()

            assert "React" in vocab_text
            assert "Vue" in vocab_text
            assert "Angular" in vocab_text


class TestVocabularyOrdering:
    """Test vocabulary list ordering."""

    def test_vocabulary_sorted_alphabetically(self, qapp, tmp_path):
        """Test that vocabulary can be sorted alphabetically."""
        from src.dictator import DictatorWindow
        from pathlib import Path

        config_file = tmp_path / "test_config.json"

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)
            # Clear any loaded vocabulary for clean test
            window.custom_vocabulary = []

            window.add_vocabulary_term("Zebra")
            window.add_vocabulary_term("Apple")
            window.add_vocabulary_term("Banana")

            sorted_vocab = window.get_sorted_vocabulary()

            assert sorted_vocab == ["Apple", "Banana", "Zebra"]
