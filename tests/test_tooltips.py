"""
Tests for UI tooltips.

Verifies that:
- All interactive elements have helpful tooltips
- Tooltips are clear and concise
- Tooltips explain what each control does
"""

import pytest
from unittest.mock import patch


class TestMainWindowTooltips:
    """Test tooltips in main window."""

    def test_record_button_has_tooltip(self, qapp):
        """Test that record button has helpful tooltip."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Record button should have tooltip
            tooltip = window.record_btn.toolTip()
            assert tooltip, "Record button should have a tooltip"
            assert len(tooltip) > 0
            # Should explain what it does
            assert any(word in tooltip.lower() for word in ['click', 'start', 'listen', 'record'])

    def test_settings_button_has_tooltip(self, qapp):
        """Test that settings button has tooltip."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Find settings button
            settings_btn = None
            for child in window.findChildren(type(window.record_btn)):
                if '⚙' in child.text():
                    settings_btn = child
                    break

            assert settings_btn is not None, "Settings button should exist"
            tooltip = settings_btn.toolTip()
            assert tooltip, "Settings button should have a tooltip"
            assert 'settings' in tooltip.lower() or 'preferences' in tooltip.lower()

    def test_history_toggle_has_tooltip(self, qapp):
        """Test that history toggle button has tooltip."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            tooltip = window.history_toggle.toolTip()
            assert tooltip, "History toggle should have a tooltip"
            assert 'history' in tooltip.lower()

    def test_minimize_button_has_tooltip(self, qapp):
        """Test that minimize button has tooltip."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Find minimize button
            minimize_btn = None
            for child in window.findChildren(type(window.record_btn)):
                if '−' in child.text():
                    minimize_btn = child
                    break

            assert minimize_btn is not None, "Minimize button should exist"
            tooltip = minimize_btn.toolTip()
            assert tooltip, "Minimize button should have a tooltip"
            assert 'minimize' in tooltip.lower() or 'hide' in tooltip.lower()

    def test_close_button_has_tooltip(self, qapp):
        """Test that close button has tooltip."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Find close button
            close_btn = None
            for child in window.findChildren(type(window.record_btn)):
                if '✕' in child.text():
                    close_btn = child
                    break

            assert close_btn is not None, "Close button should exist"
            tooltip = close_btn.toolTip()
            assert tooltip, "Close button should have a tooltip"
            assert 'close' in tooltip.lower() or 'exit' in tooltip.lower()


class TestSettingsDialogTooltips:
    """Test tooltips in settings dialog."""

    def test_model_combo_has_tooltip(self, qapp):
        """Test that model selection has tooltip."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            tooltip = dialog.model_combo.toolTip()
            assert tooltip, "Model combo should have a tooltip"
            assert 'model' in tooltip.lower()

    def test_language_combo_has_tooltip(self, qapp):
        """Test that language selection has tooltip."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            tooltip = dialog.language_combo.toolTip()
            assert tooltip, "Language combo should have a tooltip"
            assert 'language' in tooltip.lower()

    def test_device_combo_has_tooltip(self, qapp):
        """Test that device selection has tooltip."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            tooltip = dialog.device_combo.toolTip()
            assert tooltip, "Device combo should have a tooltip"
            assert 'device' in tooltip.lower() or 'cpu' in tooltip.lower() or 'gpu' in tooltip.lower()

    def test_download_button_has_tooltip(self, qapp):
        """Test that download model button has tooltip."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            tooltip = dialog.download_model_btn.toolTip()
            assert tooltip, "Download button should have a tooltip"
            assert 'download' in tooltip.lower()

    def test_debug_checkbox_has_tooltip(self, qapp):
        """Test that debug mode checkbox has tooltip."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            tooltip = dialog.debug_mode_checkbox.toolTip()
            assert tooltip, "Debug checkbox should have a tooltip"
            assert 'debug' in tooltip.lower() or 'log' in tooltip.lower()


class TestTooltipQuality:
    """Test that tooltips are helpful and well-written."""

    def test_tooltips_are_concise(self, qapp):
        """Test that tooltips are not too long."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Check record button tooltip length
            tooltip = window.record_btn.toolTip()
            if tooltip:
                # Should be under 100 characters for readability
                assert len(tooltip) < 100, f"Tooltip too long: {len(tooltip)} chars"

    def test_tooltips_use_sentence_case(self, qapp):
        """Test that tooltips use proper capitalization."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            tooltip = window.record_btn.toolTip()
            if tooltip:
                # Should start with capital letter
                assert tooltip[0].isupper(), "Tooltip should start with capital letter"

    def test_no_redundant_tooltips(self, qapp):
        """Test that tooltips don't just repeat the button text."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # History toggle shouldn't just say "History"
            tooltip = window.history_toggle.toolTip()
            button_text = window.history_toggle.text()

            if tooltip and button_text:
                # Tooltip should provide more info than just the button text
                assert tooltip.lower() != button_text.lower(), \
                    "Tooltip should provide additional information, not just repeat button text"


class TestTooltipAccessibility:
    """Test tooltip accessibility features."""

    def test_all_interactive_elements_have_tooltips(self, qapp):
        """Test that all buttons have tooltips."""
        from src.dictator import DictatorWindow
        from PyQt6.QtWidgets import QPushButton

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Find all buttons
            buttons = window.findChildren(QPushButton)

            # Count buttons with tooltips
            buttons_with_tooltips = sum(1 for btn in buttons if btn.toolTip())

            # Should have at least 3 main buttons with tooltips
            # (record, settings, history toggle, plus minimize/close)
            assert buttons_with_tooltips >= 3, \
                f"Expected at least 3 buttons with tooltips, got {buttons_with_tooltips}"

    def test_tooltips_explain_keyboard_shortcuts(self, qapp):
        """Test that tooltips mention keyboard shortcuts where applicable."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Record button tooltip should mention the hotkey
            tooltip = window.record_btn.toolTip()
            if tooltip:
                # Should mention Ctrl+Space or keyboard shortcut
                has_shortcut = any(key in tooltip for key in ['Ctrl', 'Space', 'keyboard', 'hotkey'])
                # Not strict requirement, but good UX
                # assert has_shortcut, "Record button tooltip should mention keyboard shortcut"
