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
        from src import dictator
        import inspect

        # Verify closeEvent method exists and calls close_application
        source = inspect.getsource(dictator.DictatorWindow.closeEvent)

        # Should call close_application
        assert 'close_application' in source, (
            "closeEvent should call close_application for proper cleanup"
        )

    def test_signal_handler_should_not_force_kill(self):
        """
        Test that signal handlers (SIGTERM, SIGINT, SIGHUP) use graceful shutdown.
        They should call QApplication.quit() not os._exit().
        """
        from src import gui
        import inspect

        # Verify signal_handler uses QApplication.quit, not os._exit
        source = inspect.getsource(gui.signal_handler)

        # Should call QApplication.quit()
        assert 'QApplication.quit()' in source
        # Should NOT call os._exit
        assert 'os._exit' not in source

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
        from src import dictator
        import inspect

        # Verify close_application stops timers
        source = inspect.getsource(dictator.DictatorWindow.close_application)

        # Should stop all timers
        assert 'volume_timer.stop' in source
        assert 'hide_timer.stop' in source
        assert 'recording_timer.stop' in source
        # ui_update_timer no longer exists - replaced with Qt signals/slots

    def test_cleanup_stops_recorder(self):
        """
        Test that close_application() properly stops the recorder.
        """
        from src import dictator
        import inspect

        # Verify close_application stops recorder
        source = inspect.getsource(dictator.DictatorWindow.close_application)

        # Should stop recorder
        assert 'recorder.stop_monitoring' in source
        assert 'recorder.stop_recording' in source

    def test_cleanup_stops_hotkey_manager(self):
        """
        Test that close_application() properly stops the hotkey manager.
        """
        from src import dictator
        import inspect

        # Verify close_application stops hotkey manager
        source = inspect.getsource(dictator.DictatorWindow.close_application)

        # Should stop hotkey manager
        assert 'hotkey_manager.stop' in source


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
        from src import dictator
        import inspect

        # Verify save_config has error handling
        source = inspect.getsource(dictator.DictatorWindow.save_config)

        # Should have try/except
        assert 'try:' in source
        assert 'except' in source
        # Should NOT call os._exit
        assert 'os._exit' not in source
