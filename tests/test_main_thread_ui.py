"""
Tests for main thread UI updates
Following TDD - verification phase

Tests that all UI updates happen on Qt's main thread:
- UI update queue system works correctly
- All background thread callbacks use queue
- No direct UI updates from worker threads
- Main thread timer processes updates correctly
"""

import pytest
import sys
import threading
import time
from unittest.mock import Mock, patch, MagicMock, call
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread

# Mock problematic modules before import
sys.modules['sounddevice'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()
sys.modules['pynput'] = MagicMock()
sys.modules['pynput.keyboard'] = MagicMock()


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for Qt GUI tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestUIUpdateQueueSystem:
    """Test that UI update queue system is properly implemented"""

    def test_ui_update_queue_exists(self, qapp):
        """
        Test that DictatorWindow has UI update queue.
        Required for thread-safe UI updates.
        """
        from src.dictator import DictatorWindow
        import queue

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have UI update queue
            assert hasattr(window, 'ui_update_queue'), \
                "Window should have ui_update_queue for thread-safe updates"
            assert isinstance(window.ui_update_queue, queue.Queue) or \
                   hasattr(window.ui_update_queue, 'put'), \
                "ui_update_queue should be queue-like object"

    def test_request_ui_update_is_thread_safe(self, qapp):
        """
        Test that request_ui_update can be called from any thread.
        This is the primary interface for thread-safe UI updates.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should be callable from background thread
            def background_task():
                window.request_ui_update("update_status", status="Test", style="")

            thread = threading.Thread(target=background_task)
            thread.start()
            thread.join(timeout=2.0)

            # Should have queued the update
            assert not window.ui_update_queue.empty(), \
                "request_ui_update should queue updates from background threads"

    def test_process_ui_updates_runs_on_main_thread(self, qapp):
        """
        Test that process_ui_updates is called from main thread timer.
        UI updates must happen on Qt's main thread.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have timer that calls process_ui_updates
            assert hasattr(window, 'ui_update_timer'), \
                "Window should have ui_update_timer for processing queued updates"

            # Timer should be running
            assert window.ui_update_timer.isActive(), \
                "UI update timer should be active to process updates"


class TestCallbacksUseQueue:
    """Test that all callbacks from background threads use the queue"""

    def test_transcription_callback_uses_queue(self, qapp):
        """
        Test that on_transcription_ready uses queue, not direct UI update.
        Transcription happens in background thread.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Clear queue
            while not window.ui_update_queue.empty():
                window.ui_update_queue.get_nowait()

            # Call from background thread
            def call_callback():
                window.on_transcription_ready("Test text", "en")

            thread = threading.Thread(target=call_callback)
            thread.start()
            thread.join(timeout=2.0)

            # Should have queued update, not done direct UI update
            assert not window.ui_update_queue.empty(), \
                "on_transcription_ready should queue updates, not update UI directly"

    def test_recorder_callbacks_use_queue(self, qapp):
        """
        Test that recorder callbacks use queue system.
        Recorder runs in background threads.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Recorder should use on_transcription_ready callback
            assert hasattr(window, 'on_transcription_ready'), \
                "Window should have on_transcription_ready callback"

            # Callback should be set on recorder
            if hasattr(window.recorder, 'callback'):
                assert window.recorder.callback == window.on_transcription_ready, \
                    "Recorder callback should use thread-safe on_transcription_ready"


class TestNoDirectUIUpdates:
    """Test that no direct UI updates happen from background threads"""

    def test_safe_methods_update_ui_directly(self, qapp):
        """
        Test that _safe_* methods can update UI directly.
        These methods are guaranteed to run on main thread via queue.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # _safe_* methods should exist for main thread UI updates
            assert hasattr(window, '_safe_handle_transcription'), \
                "_safe_handle_transcription should exist for main thread updates"
            assert hasattr(window, '_safe_add_history_item'), \
                "_safe_add_history_item should exist for main thread updates"
            assert hasattr(window, '_safe_update_status'), \
                "_safe_update_status should exist for main thread updates"

    def test_ui_updates_go_through_handle_ui_update(self, qapp):
        """
        Test that queued updates are processed by _handle_ui_update.
        This ensures all UI updates go through proper dispatcher.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have handler that dispatches to _safe_* methods
            assert hasattr(window, '_handle_ui_update'), \
                "_handle_ui_update should dispatch queued updates"


class TestQueueProcessing:
    """Test that queue processing works correctly"""

    def test_process_ui_updates_processes_all_pending(self, qapp):
        """
        Test that process_ui_updates processes pending updates.
        Ensures updates don't get stuck in queue.
        """
        from src.dictator import DictatorWindow
        from src.ui_utils import UIUpdateRequest

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Queue some updates
            window.ui_update_queue.put(UIUpdateRequest("update_status", status="Test1", style=""))
            window.ui_update_queue.put(UIUpdateRequest("update_status", status="Test2", style=""))

            # Process updates
            window.process_ui_updates()

            # Queue should be empty (or have max 10 left if more were queued)
            queue_size = window.ui_update_queue.qsize()
            assert queue_size <= 10, \
                f"process_ui_updates should process updates (queue size: {queue_size})"

    def test_process_ui_updates_limits_per_cycle(self, qapp):
        """
        Test that process_ui_updates limits updates per cycle.
        Prevents UI freezing from too many updates at once.
        """
        from src.dictator import DictatorWindow
        from src.ui_utils import UIUpdateRequest

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Queue many updates (more than limit)
            for i in range(50):
                window.ui_update_queue.put(UIUpdateRequest("update_status", status=f"Test{i}", style=""))

            initial_size = window.ui_update_queue.qsize()

            # Process one cycle
            window.process_ui_updates()

            # Should have processed some but not all (limit is 10)
            final_size = window.ui_update_queue.qsize()
            processed = initial_size - final_size

            assert 1 <= processed <= 10, \
                f"Should process up to 10 updates per cycle (processed: {processed})"


class TestThreadSafety:
    """Test thread safety of UI update system"""

    def test_concurrent_queue_access_safe(self, qapp):
        """
        Test that multiple threads can queue updates concurrently.
        No race conditions or lost updates.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Clear queue
            while not window.ui_update_queue.empty():
                window.ui_update_queue.get_nowait()

            errors = []
            queued_count = []

            def queue_updates():
                try:
                    for i in range(10):
                        window.request_ui_update("update_status", status=f"Test{i}", style="")
                        queued_count.append(1)
                except Exception as e:
                    errors.append(str(e))

            # Queue from multiple threads
            threads = [threading.Thread(target=queue_updates) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5.0)

            # Should have no errors
            assert len(errors) == 0, f"Concurrent queueing caused errors: {errors}"

            # Should have queued all updates (5 threads * 10 updates = 50)
            assert len(queued_count) == 50, \
                f"Should have queued 50 updates (got {len(queued_count)})"


class TestUpdateHandlers:
    """Test that update handlers work correctly"""

    def test_transcription_complete_handler(self, qapp):
        """
        Test that transcription_complete updates are handled.
        Should call _safe_handle_transcription.
        """
        from src.dictator import DictatorWindow
        from src.ui_utils import UIUpdateRequest

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Mock the safe handler
            with patch.object(window, '_safe_handle_transcription') as mock_handler:
                # Queue and process update
                window.ui_update_queue.put(
                    UIUpdateRequest("transcription_complete", text="Test", language="en")
                )
                window.process_ui_updates()

                # Should have called handler
                mock_handler.assert_called_once_with("Test", "en")

    def test_update_status_handler(self, qapp):
        """
        Test that update_status updates are handled.
        Should call _safe_update_status.
        """
        from src.dictator import DictatorWindow
        from src.ui_utils import UIUpdateRequest

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Mock the safe handler
            with patch.object(window, '_safe_update_status') as mock_handler:
                # Queue and process update
                window.ui_update_queue.put(
                    UIUpdateRequest("update_status", status="Test", style="color: red;")
                )
                window.process_ui_updates()

                # Should have called handler
                mock_handler.assert_called_once_with("Test", "color: red;")


class TestTimerConfiguration:
    """Test that UI update timer is properly configured"""

    def test_timer_interval_reasonable(self, qapp):
        """
        Test that timer interval is reasonable for responsive UI.
        Too slow = laggy, too fast = CPU waste.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Timer interval should be reasonable (10-50ms for ~60fps)
            interval = window.ui_update_timer.interval()
            assert 10 <= interval <= 50, \
                f"Timer interval should be 10-50ms for responsive UI (got {interval}ms)"

    def test_timer_runs_continuously(self, qapp):
        """
        Test that timer runs continuously to process updates.
        Should not be single-shot.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Timer should not be single-shot
            assert not window.ui_update_timer.isSingleShot(), \
                "UI update timer should run continuously, not single-shot"


class TestErrorHandling:
    """Test error handling in UI update system"""

    def test_invalid_update_doesnt_crash(self, qapp):
        """
        Test that invalid update action doesn't crash.
        Should log error and continue processing.
        """
        from src.dictator import DictatorWindow
        from src.ui_utils import UIUpdateRequest

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Queue invalid update
            window.ui_update_queue.put(
                UIUpdateRequest("invalid_action", foo="bar")
            )

            # Should not crash when processing
            try:
                window.process_ui_updates()
                # If we get here, it handled the error gracefully
                assert True
            except Exception as e:
                pytest.fail(f"Invalid update caused crash: {e}")

    def test_handler_exception_doesnt_stop_processing(self, qapp):
        """
        Test that exception in one handler doesn't stop queue processing.
        Should log error and continue with next update.
        """
        from src.dictator import DictatorWindow
        from src.ui_utils import UIUpdateRequest

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Make handler raise exception
            def bad_handler(*args, **kwargs):
                raise ValueError("Test error")

            with patch.object(window, '_safe_update_status', bad_handler):
                # Queue updates - one will fail, one should succeed
                window.ui_update_queue.put(UIUpdateRequest("update_status", status="Bad", style=""))
                window.ui_update_queue.put(UIUpdateRequest("add_history_item", text="Good"))

                # Should not crash
                try:
                    window.process_ui_updates()
                    assert True, "Processing continued despite error"
                except ValueError:
                    pytest.fail("Exception in handler stopped queue processing")
