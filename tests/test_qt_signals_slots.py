"""
Tests for Qt signals/slots UI update system
Following TDD - RED phase

Tests that UI updates use Qt's native signal/slot mechanism:
- DictatorWindow has Qt signals for all update types
- Signals are properly connected to handler methods
- Background threads can emit signals safely
- Signals trigger handlers on main thread automatically
- Old queue system is removed
"""

import pytest
import sys
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import pyqtSignal, QObject, Qt

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


class TestSignalDefinitions:
    """Test that DictatorWindow defines all required signals"""

    def test_window_has_transcription_complete_signal(self, qapp):
        """
        Test that DictatorWindow has transcriptionComplete signal.
        Replaces "transcription_complete" queue action.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should have Qt signal for transcription
            assert hasattr(window, 'transcriptionComplete'), \
                "Window should have transcriptionComplete signal"
            # Check it's a signal by verifying it has emit and connect methods
            assert hasattr(window.transcriptionComplete, 'emit'), \
                "transcriptionComplete should have emit method (Qt signal)"
            assert hasattr(window.transcriptionComplete, 'connect'), \
                "transcriptionComplete should have connect method (Qt signal)"

    def test_window_has_status_update_signal(self, qapp):
        """
        Test that DictatorWindow has statusUpdate signal.
        Replaces "update_status" queue action.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'statusUpdate'), \
                "Window should have statusUpdate signal"
            assert hasattr(window.statusUpdate, 'emit'), \
                "statusUpdate should have emit method (Qt signal)"

    def test_window_has_history_item_signal(self, qapp):
        """
        Test that DictatorWindow has addHistoryItem signal.
        Replaces "add_history_item" queue action.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'addHistoryItem'), \
                "Window should have addHistoryItem signal"

    def test_window_has_toggle_recording_signal(self, qapp):
        """
        Test that DictatorWindow has toggleRecording signal.
        Replaces "toggle_recording" queue action.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'toggleRecording'), \
                "Window should have toggleRecording signal"

    def test_window_has_clipboard_signal(self, qapp):
        """
        Test that DictatorWindow has copyToClipboard signal.
        Replaces "copy_to_clipboard" queue action.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'copyToClipboard'), \
                "Window should have copyToClipboard signal"

    def test_window_has_type_text_signal(self, qapp):
        """
        Test that DictatorWindow has typeText signal.
        Replaces "type_text" queue action.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            assert hasattr(window, 'typeText'), \
                "Window should have typeText signal"


class TestSignalConnections:
    """Test that signals are properly connected to slots"""

    def test_transcription_signal_connected(self, qapp):
        """
        Test that transcriptionComplete signal is connected to handler.
        Should call _safe_handle_transcription when emitted.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Connect test slot to verify signal emission
            received_args = []

            def test_slot(text, lang):
                received_args.append((text, lang))

            window.transcriptionComplete.connect(test_slot)

            # Emit signal
            window.transcriptionComplete.emit("Test text", "en", None)

            # Process Qt events to ensure signal is delivered
            qapp.processEvents()

            # Should have received signal
            assert len(received_args) == 1, \
                "Signal should be emitted and received"
            assert received_args[0] == ("Test text", "en"), \
                "Signal should carry correct arguments"

    def test_status_signal_connected(self, qapp):
        """
        Test that statusUpdate signal is connected to handler.
        Should call _safe_update_status when emitted.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            received_args = []

            def test_slot(status, style):
                received_args.append((status, style))

            window.statusUpdate.connect(test_slot)
            window.statusUpdate.emit("Test status", "color: red;")
            qapp.processEvents()

            assert len(received_args) == 1
            assert received_args[0] == ("Test status", "color: red;")

    def test_history_signal_connected(self, qapp):
        """
        Test that addHistoryItem signal is connected to handler.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            received_args = []

            def test_slot(text):
                received_args.append(text)

            window.addHistoryItem.connect(test_slot)
            window.addHistoryItem.emit("Test item", None)
            qapp.processEvents()

            assert len(received_args) == 1
            assert received_args[0] == "Test item"


class TestThreadSafeSignalEmission:
    """Test that signals can be safely emitted from background threads"""

    def test_transcription_from_background_thread(self, qapp):
        """
        Test that transcriptionComplete can be emitted from background thread.
        Qt automatically marshals to main thread.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            handler_called = []

            def test_slot(text, lang):
                handler_called.append((text, lang))

            window.transcriptionComplete.connect(test_slot)

            # Emit from background thread
            def background_emit():
                window.transcriptionComplete.emit("BG Test", "en", None)

            thread = threading.Thread(target=background_emit)
            thread.start()
            thread.join(timeout=2.0)

            # Process events to deliver signal
            qapp.processEvents()

            # Should have been called
            assert len(handler_called) == 1, \
                "Signal from background thread should call handler"
            assert handler_called[0] == ("BG Test", "en")

    def test_concurrent_signal_emissions_safe(self, qapp):
        """
        Test that multiple threads can emit signals concurrently.
        Qt's signal/slot mechanism is thread-safe.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            handler_calls = []

            def test_slot(status, style):
                handler_calls.append((status, style))

            window.statusUpdate.connect(test_slot)

            # Emit from multiple threads
            def emit_signal(i):
                window.statusUpdate.emit(f"Status {i}", "")

            threads = [threading.Thread(target=emit_signal, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=2.0)

            # Process all pending events
            qapp.processEvents()

            # Should have received all signals
            assert len(handler_calls) == 10, \
                "All signals from concurrent threads should be delivered"


class TestCallbacksEmitSignals:
    """Test that callbacks emit signals instead of queuing"""

    def test_on_transcription_ready_emits_signal(self, qapp):
        """
        Test that on_transcription_ready emits signal, not queue.
        Background thread callback should use signals.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            handler_called = []

            def test_slot(text, lang):
                handler_called.append((text, lang))

            window.transcriptionComplete.connect(test_slot)

            # Call from background thread
            def call_callback():
                window.on_transcription_ready("Signal test", "en")

            thread = threading.Thread(target=call_callback)
            thread.start()
            thread.join(timeout=2.0)

            # Process events
            qapp.processEvents()

            # Should have called handler via signal
            assert len(handler_called) == 1
            assert handler_called[0] == ("Signal test", "en")


class TestQueueSystemRemoved:
    """Test that old queue-based system is removed"""

    def test_no_ui_update_queue(self, qapp):
        """
        Test that ui_update_queue is removed.
        No longer needed with signals/slots.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should NOT have ui_update_queue
            assert not hasattr(window, 'ui_update_queue'), \
                "ui_update_queue should be removed (using signals now)"

    def test_no_ui_update_timer(self, qapp):
        """
        Test that ui_update_timer is removed.
        Qt handles signal delivery automatically.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should NOT have ui_update_timer
            assert not hasattr(window, 'ui_update_timer'), \
                "ui_update_timer should be removed (Qt handles delivery)"

    def test_no_request_ui_update_method(self, qapp):
        """
        Test that request_ui_update is removed.
        Code should emit signals directly.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should NOT have request_ui_update
            assert not hasattr(window, 'request_ui_update'), \
                "request_ui_update should be removed (emit signals directly)"

    def test_no_process_ui_updates_method(self, qapp):
        """
        Test that process_ui_updates is removed.
        Qt processes signals automatically.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            # Should NOT have process_ui_updates
            assert not hasattr(window, 'process_ui_updates'), \
                "process_ui_updates should be removed (Qt handles this)"


class TestSignalSlotPerformance:
    """Test that signal/slot system performs well"""

    def test_rapid_signal_emissions_no_lag(self, qapp):
        """
        Test that rapid signal emissions don't cause lag.
        Qt's event queue handles backpressure automatically.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            handler_count = [0]

            def test_slot(status, style):
                handler_count[0] += 1

            window.statusUpdate.connect(test_slot)

            # Emit many signals rapidly
            for i in range(100):
                window.statusUpdate.emit(f"Status {i}", "")

            # Process events
            qapp.processEvents()

            # Should have processed all signals
            assert handler_count[0] == 100, \
                "All signals should be processed"


class TestErrorHandling:
    """Test error handling in signal/slot system"""

    def test_exception_in_slot_doesnt_crash(self, qapp):
        """
        Test that exception in slot doesn't crash app.
        Qt handles exceptions in slots gracefully.
        """
        from src.dictator import DictatorWindow

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            window = DictatorWindow(no_tray=True)

            def bad_handler(text, lang):
                raise ValueError("Test error in slot")

            with patch.object(window, '_safe_handle_transcription', bad_handler):
                # Should not crash when emitting
                try:
                    window.transcriptionComplete.emit("Test", "en", None)
                    qapp.processEvents()
                    # If we get here, Qt handled the exception
                    assert True
                except ValueError:
                    pytest.fail("Exception in slot should not propagate to caller")
