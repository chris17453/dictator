"""
Tests for crash handling and graceful shutdown functionality
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Mock problematic modules before import
sys.modules['sounddevice'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()
sys.modules['pynput'] = MagicMock()
sys.modules['pynput.keyboard'] = MagicMock()


class TestGracefulShutdown:
    """Test proper shutdown behavior without force-killing"""

    def test_should_not_use_os_exit_for_shutdown(self):
        """
        CRITICAL: Application should never use os._exit() for normal shutdown.
        os._exit() bypasses cleanup, signal handlers, and atexit functions.
        This test ensures we use proper shutdown mechanisms.
        """
        # This test will fail until we remove os._exit() from gui.py
        from src import gui

        # Read the gui.py source code
        gui_source = open(os.path.join(os.path.dirname(gui.__file__), 'gui.py')).read()

        # Check that os._exit is NOT used (should fail initially)
        assert 'os._exit' not in gui_source, (
            "gui.py must not use os._exit() - it bypasses cleanup and causes data loss. "
            "Use sys.exit() or QApplication.quit() instead."
        )

    def test_window_close_should_trigger_cleanup(self):
        """
        Test that closing the window triggers proper cleanup sequence.
        Should call close_application() method which handles resource cleanup.
        """
        with patch('src.gui.QApplication') as mock_qapp, \
             patch('src.gui.DictatorWindow') as mock_window:

            # Setup mock window instance
            window_instance = Mock()
            window_instance.close_application = Mock()
            window_instance.is_closing = False
            mock_window.return_value = window_instance

            # Simulate window close event
            close_event = Mock()

            # Import after patching
            from src.dictator import DictatorWindow

            # Create window and trigger close
            window = DictatorWindow()
            window.closeEvent(close_event)

            # Verify close_application was called
            window.close_application.assert_called_once()

    def test_signal_handler_should_not_force_kill(self):
        """
        Test that signal handlers (SIGTERM, SIGINT, SIGHUP) use graceful shutdown.
        They should call QApplication.quit() not os._exit().
        """
        with patch('src.gui.QApplication') as mock_qapp:
            mock_app_instance = Mock()
            mock_qapp.return_value = mock_app_instance

            # Import signal handler
            from src.gui import signal_handler

            # Call signal handler
            signal_handler(15, None)  # SIGTERM

            # Should call quit, not exit
            mock_app_instance.quit.assert_called_once()

    def test_monitor_thread_removed_or_non_destructive(self):
        """
        Test that the monitor thread is either removed or made non-destructive.
        If it exists, it should NOT call os._exit().
        """
        from src import gui

        # Check if monitor_main_thread function exists
        if hasattr(gui, 'monitor_main_thread'):
            # Read the function source
            import inspect
            source = inspect.getsource(gui.monitor_main_thread)

            # Should NOT contain os._exit
            assert 'os._exit' not in source, (
                "monitor_main_thread must not use os._exit(). "
                "Either remove the monitor thread or make it log errors only."
            )

    def test_cleanup_stops_all_timers(self):
        """
        Test that close_application() stops all QTimer instances.
        This prevents timers from firing after shutdown.
        """
        with patch('src.gui.QApplication'):
            from src.dictator import DictatorWindow

            window = DictatorWindow(no_tray=True)

            # Mock timers
            window.volume_timer = Mock()
            window.hide_timer = Mock()
            window.ui_update_timer = Mock()
            window.recording_timer = Mock()

            # Call cleanup
            window.close_application()

            # Verify all timers stopped
            window.volume_timer.stop.assert_called()
            window.hide_timer.stop.assert_called()
            window.ui_update_timer.stop.assert_called()
            window.recording_timer.stop.assert_called()

    def test_cleanup_stops_recorder(self):
        """
        Test that close_application() properly stops the recorder.
        """
        with patch('src.gui.QApplication'):
            from src.dictator import DictatorWindow

            window = DictatorWindow(no_tray=True)

            # Mock recorder
            window.recorder = Mock()

            # Call cleanup
            window.close_application()

            # Verify recorder cleanup
            window.recorder.stop_monitoring.assert_called()
            window.recorder.stop_recording.assert_called()

    def test_cleanup_stops_hotkey_manager(self):
        """
        Test that close_application() properly stops the hotkey manager.
        """
        with patch('src.gui.QApplication'):
            from src.dictator import DictatorWindow

            window = DictatorWindow(no_tray=True)

            # Mock hotkey manager
            window.hotkey_manager = Mock()

            # Call cleanup
            window.close_application()

            # Verify hotkey manager stopped
            window.hotkey_manager.stop.assert_called()


class TestResourceCleanup:
    """Test proper resource cleanup on shutdown"""

    def test_no_force_exit_in_close_application(self):
        """
        Test that close_application() does not use os._exit().
        It should use sys.exit() or allow Qt event loop to exit naturally.
        """
        from src import dictator
        import inspect

        # Get source of close_application method
        source = inspect.getsource(dictator.DictatorWindow.close_application)

        # Should NOT use os._exit
        assert 'os._exit' not in source, (
            "close_application() must not use os._exit(). "
            "Use sys.exit() or QApplication.quit() instead."
        )


class TestErrorRecovery:
    """Test that errors don't cause force-kills"""

    def test_config_save_error_should_not_crash_app(self):
        """
        Test that config save errors are handled gracefully.
        Should log error but not kill the application.
        """
        with patch('src.gui.QApplication'):
            from src.dictator import DictatorWindow

            window = DictatorWindow(no_tray=True)

            # Mock config path to cause write error
            with patch('builtins.open', side_effect=PermissionError("Access denied")):
                # Should not raise exception or call os._exit
                try:
                    window.save_config()
                    # If we get here, error was handled (good)
                    handled = True
                except SystemExit:
                    # os._exit would raise SystemExit
                    handled = False

                assert handled, "save_config should handle errors gracefully"
