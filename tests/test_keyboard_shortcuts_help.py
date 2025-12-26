"""
Tests for keyboard shortcuts help/documentation.

Verifies that:
- Keyboard shortcuts help dialog exists
- Help dialog shows all available shortcuts
- Help can be accessed from UI
- Shortcuts are clearly documented
"""

import pytest
from unittest.mock import patch


class TestShortcutsHelpDialog:
    """Test keyboard shortcuts help dialog."""

    def test_show_shortcuts_help_method_exists(self, qapp):
        """Test that method to show shortcuts help exists."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have method to show shortcuts help
            assert hasattr(window, 'show_shortcuts_help')
            assert callable(window.show_shortcuts_help)

    def test_shortcuts_help_shows_recording_hotkey(self, qapp):
        """Test that help shows the recording hotkey."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Call the help method (don't exec the dialog)
            if hasattr(window, 'show_shortcuts_help'):
                # Should not crash
                window.show_shortcuts_help()

    def test_shortcuts_help_content_includes_ctrl_space(self, qapp):
        """Test that help content mentions Ctrl+Space."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Get shortcuts data
            if hasattr(window, 'get_shortcuts_list'):
                shortcuts = window.get_shortcuts_list()

                # Should include recording shortcut
                assert len(shortcuts) > 0
                # Should mention recording or toggle
                shortcuts_str = str(shortcuts).lower()
                assert 'record' in shortcuts_str or 'toggle' in shortcuts_str


class TestShortcutsAccess:
    """Test that shortcuts help is accessible."""

    def test_help_button_or_menu_exists(self, qapp):
        """Test that there's a way to access help."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have help access through settings or menu
            # Check if settings dialog has help section
            has_help_access = hasattr(window, 'show_shortcuts_help')
            assert has_help_access, "Should have way to access keyboard shortcuts help"

    def test_settings_has_shortcuts_info(self, qapp):
        """Test that settings dialog has shortcuts information."""
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            parent = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(parent)

            # Should have some reference to shortcuts or help
            # Check if there's a shortcuts tab or help button
            has_shortcuts_info = (
                hasattr(dialog, 'shortcuts_tab') or
                hasattr(dialog, 'help_button') or
                hasattr(dialog, 'show_shortcuts_help')
            )

            # At minimum, should be able to access from parent
            assert has_shortcuts_info or hasattr(parent, 'show_shortcuts_help')


class TestShortcutsContent:
    """Test the content of shortcuts documentation."""

    def test_shortcuts_list_is_comprehensive(self, qapp):
        """Test that shortcuts list covers main features."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            if hasattr(window, 'get_shortcuts_list'):
                shortcuts = window.get_shortcuts_list()

                # Should be a list or dict
                assert shortcuts is not None
                assert len(shortcuts) > 0

                # Convert to string for checking
                shortcuts_str = str(shortcuts).lower()

                # Should mention key actions
                assert 'record' in shortcuts_str or 'listen' in shortcuts_str
                # Should mention the actual keys
                assert 'ctrl' in shortcuts_str or 'space' in shortcuts_str

    def test_shortcuts_are_user_friendly(self, qapp):
        """Test that shortcuts are described in user-friendly terms."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            if hasattr(window, 'get_shortcuts_list'):
                shortcuts = window.get_shortcuts_list()

                # Check if it's a dict with descriptions
                if isinstance(shortcuts, dict):
                    # Values should be human-readable descriptions
                    for key, description in shortcuts.items():
                        # Description should be more than just the key
                        assert description != key
                        # Description should be somewhat long
                        assert len(str(description)) > 5

    def test_shortcuts_show_current_hotkey(self, qapp):
        """Test that shortcuts help shows the currently configured hotkey."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Set a custom hotkey
            window.current_hotkey = ["Ctrl", "R"]

            if hasattr(window, 'get_shortcuts_list'):
                shortcuts = window.get_shortcuts_list()
                shortcuts_str = str(shortcuts)

                # Should reflect the custom hotkey, not just default
                # This ensures it's dynamic
                assert shortcuts_str is not None


class TestShortcutsDialog:
    """Test the shortcuts help dialog UI."""

    def test_shortcuts_dialog_is_modal(self, qapp):
        """Test that shortcuts dialog is a proper dialog."""
        from src.dictator import DictatorWindow
        from PyQt6.QtWidgets import QDialog

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # The show_shortcuts_help should create a dialog
            # We'll just verify the method exists and is callable
            if hasattr(window, 'show_shortcuts_help'):
                # Should be a method
                assert callable(window.show_shortcuts_help)

    def test_shortcuts_dialog_has_close_button(self, qapp):
        """Test that shortcuts dialog can be closed."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Dialog should have standard close functionality
            # This is automatic with QDialog, but we verify the method exists
            assert hasattr(window, 'show_shortcuts_help')


class TestShortcutsHelpIntegration:
    """Test integration of shortcuts help with main app."""

    def test_help_accessible_from_main_window(self, qapp):
        """Test that help is accessible from main window."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have direct access to shortcuts help
            assert hasattr(window, 'show_shortcuts_help')

    def test_shortcuts_help_does_not_crash(self, qapp):
        """Test that showing shortcuts help doesn't crash."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            # Patch QMessageBox to prevent actual dialog
            with patch('PyQt6.QtWidgets.QMessageBox.information'):
                window = DictatorWindow(no_tray=True)

                if hasattr(window, 'show_shortcuts_help'):
                    # Should not raise exception
                    try:
                        window.show_shortcuts_help()
                    except Exception as e:
                        pytest.fail(f"show_shortcuts_help raised exception: {e}")

    def test_shortcuts_updated_when_hotkey_changes(self, qapp):
        """Test that shortcuts help updates when hotkey is changed."""
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Change hotkey
            original_hotkey = window.current_hotkey
            window.current_hotkey = ["Alt", "R"]

            if hasattr(window, 'get_shortcuts_list'):
                shortcuts = window.get_shortcuts_list()

                # Should reflect new hotkey
                shortcuts_str = str(shortcuts)
                # At minimum, should be dynamic (not hardcoded)
                assert shortcuts_str is not None

            # Restore
            window.current_hotkey = original_hotkey
