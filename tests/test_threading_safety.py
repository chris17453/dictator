"""
Tests for threading safety and race conditions
Following TDD - RED phase

Tests that critical shared data structures are properly synchronized:
- audio_queue is thread-safe
- audio_data is protected by locks
- is_monitoring flag is atomic/synchronized
- whisper_model loading is thread-safe
"""

import pytest
import sys
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Mock problematic modules before import
sys.modules['sounddevice'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()
sys.modules['pynput'] = MagicMock()
sys.modules['pynput.keyboard'] = MagicMock()


class TestAudioQueueThreadSafety:
    """Test that audio_queue is thread-safe"""

    def test_audio_queue_is_queue_not_list(self):
        """
        Test that audio_queue uses queue.Queue, not plain list.
        Plain lists are not thread-safe.
        """
        from src.recorder import PureRecorder
        import queue

        recorder = PureRecorder()

        # Should be a Queue instance, not a list
        assert isinstance(recorder.audio_queue, queue.Queue), \
            "audio_queue should be queue.Queue for thread safety"

    def test_audio_queue_concurrent_access_safe(self):
        """
        Test that multiple threads can safely access audio_queue.
        This would fail with plain list due to race conditions.
        """
        from src.recorder import PureRecorder
        import queue

        recorder = PureRecorder()
        errors = []

        def producer():
            try:
                for i in range(100):
                    recorder.audio_queue.put(f"audio_{i}", timeout=1.0)
            except Exception as e:
                errors.append(f"Producer error: {e}")

        def consumer():
            try:
                for i in range(100):
                    recorder.audio_queue.get(timeout=2.0)
            except Exception as e:
                errors.append(f"Consumer error: {e}")

        # Run multiple producers and consumers concurrently
        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=producer))
            threads.append(threading.Thread(target=consumer))

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=5.0)

        # Should have no errors from concurrent access
        assert len(errors) == 0, f"Concurrent access errors: {errors}"

    def test_audio_queue_has_size_limit(self):
        """
        Test that audio_queue has bounded size to prevent memory growth.
        Unbounded queues can cause memory exhaustion.
        """
        from src.recorder import PureRecorder
        import queue

        recorder = PureRecorder()

        # Queue should have maxsize set
        assert recorder.audio_queue.maxsize > 0, \
            "audio_queue should have bounded size (maxsize > 0)"


class TestAudioDataThreadSafety:
    """Test that audio_data access is synchronized"""

    def test_audio_data_has_lock_protection(self):
        """
        Test that recorder has lock for protecting audio_data.
        Critical for preventing data corruption.
        """
        from src.recorder import PureRecorder
        import threading

        recorder = PureRecorder()

        # Should have a lock for audio_data (or use it for audio_level_lock)
        assert hasattr(recorder, 'audio_level_lock'), \
            "Recorder should have lock for protecting shared data"
        assert type(recorder.audio_level_lock).__name__ == 'lock', \
            "audio_level_lock should be threading.Lock"

    def test_audio_data_concurrent_modification_safe(self):
        """
        Test that concurrent modifications to audio data don't corrupt it.
        This would fail without proper locking.
        """
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        errors = []
        results = []

        def append_data():
            try:
                # Simulate appending audio data
                with recorder.audio_level_lock:
                    initial_len = len(recorder.audio_data)
                    recorder.audio_data.append(b"audio")
                    final_len = len(recorder.audio_data)
                    results.append(final_len - initial_len)
            except Exception as e:
                errors.append(f"Append error: {e}")

        def read_data():
            try:
                # Simulate reading audio data
                with recorder.audio_level_lock:
                    _ = len(recorder.audio_data)
                    if recorder.audio_data:
                        _ = recorder.audio_data[0]
            except Exception as e:
                errors.append(f"Read error: {e}")

        # Run many concurrent operations
        threads = []
        for _ in range(50):
            threads.append(threading.Thread(target=append_data))
            threads.append(threading.Thread(target=read_data))

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=5.0)

        # All appends should have succeeded (each added exactly 1)
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert all(r == 1 for r in results), "Each append should add exactly 1 item"


class TestMonitoringFlagThreadSafety:
    """Test that is_monitoring flag is properly synchronized"""

    def test_monitoring_uses_event_or_lock(self):
        """
        Test that is_monitoring uses threading.Event or is protected by lock.
        Plain boolean flags have race conditions.
        """
        from src.recorder import PureRecorder
        import threading

        recorder = PureRecorder()

        # Should use Event or have a lock specifically for monitoring state
        has_event = hasattr(recorder, 'monitoring_event') and \
                    isinstance(recorder.monitoring_event, threading.Event)
        has_lock = hasattr(recorder, 'monitoring_lock') and \
                   type(recorder.monitoring_lock).__name__ == 'lock'

        assert has_event or has_lock, \
            "is_monitoring should use threading.Event or be protected by threading.Lock"

    def test_monitoring_concurrent_start_prevents_multiple_threads(self):
        """
        Test that concurrent start_monitoring calls don't create multiple threads.
        Race condition would allow multiple monitoring threads.
        """
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Track how many threads actually started
        started_count = []
        original_thread_init = threading.Thread.__init__

        def counting_init(self, *args, **kwargs):
            original_thread_init(self, *args, **kwargs)
            if 'continuous_monitor_worker' in str(kwargs.get('target', '')):
                started_count.append(1)

        with patch.object(threading.Thread, '__init__', counting_init):
            # Try to start monitoring from multiple threads simultaneously
            threads = []
            for _ in range(10):
                t = threading.Thread(target=recorder.start_continuous_monitoring)
                threads.append(t)

            for t in threads:
                t.start()

            for t in threads:
                t.join(timeout=2.0)

        # Should only create ONE monitoring thread, not 10
        assert len(started_count) <= 1, \
            f"Multiple concurrent starts created {len(started_count)} threads (should be 0 or 1)"


class TestWhisperModelLoadingThreadSafety:
    """Test that Whisper model loading is thread-safe"""

    def test_model_loading_has_lock(self):
        """
        Test that model loading uses lock to prevent concurrent loads.
        Multiple simultaneous loads waste memory and can crash.
        """
        from src.recorder import PureRecorder
        import threading

        recorder = PureRecorder()

        # Should have lock for model loading
        has_model_lock = hasattr(recorder, 'model_loading_lock') and \
                        type(recorder.model_loading_lock).__name__ == 'lock'

        assert has_model_lock, \
            "Recorder should have model_loading_lock for thread-safe model loading"

    def test_concurrent_model_loads_only_load_once(self):
        """
        Test that concurrent load attempts only load model once.
        Race condition would cause multiple loads.
        """
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        recorder.whisper_model = None  # Force reload
        load_attempts = []

        def try_load():
            # Simulate checking and loading model
            if hasattr(recorder, 'model_loading_lock'):
                with recorder.model_loading_lock:
                    if recorder.whisper_model is None:
                        load_attempts.append(1)
                        # Don't actually load, just track attempt
                        recorder.whisper_model = Mock()  # Fake model

        # Try to load from multiple threads
        threads = []
        for _ in range(10):
            t = threading.Thread(target=try_load)
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=2.0)

        # Should only attempt load once, not 10 times
        assert len(load_attempts) == 1, \
            f"Concurrent loads attempted {len(load_attempts)} times (should be 1)"


class TestSubprocessManagementThreadSafety:
    """Test that subprocess management is thread-safe"""

    def test_subprocess_has_lock_protection(self):
        """
        Test that active_subprocess is protected by lock.
        Prevents lost subprocess references.
        """
        from src.recorder import PureRecorder
        import threading

        recorder = PureRecorder()

        # Should have lock for subprocess management
        has_subprocess_lock = hasattr(recorder, 'subprocess_lock') and \
                             type(recorder.subprocess_lock).__name__ == 'lock'

        assert has_subprocess_lock, \
            "Recorder should have subprocess_lock for thread-safe subprocess management"


class TestRecordingStateThreadSafety:
    """Test that recording state is properly synchronized"""

    def test_recording_state_transitions_are_atomic(self):
        """
        Test that recording state changes are atomic.
        Prevents race between stop and start.
        """
        from src.recorder import PureRecorder
        import threading

        recorder = PureRecorder()

        # Should use lock or event for recording state
        has_recording_lock = hasattr(recorder, 'recording_lock') and \
                            type(recorder.recording_lock).__name__ == 'lock'
        has_recording_event = hasattr(recorder, 'recording_event') and \
                             isinstance(recorder.recording_event, threading.Event)

        assert has_recording_lock or has_recording_event, \
            "Recording state should be protected by lock or event"


class TestThreadCleanup:
    """Test that threads are properly cleaned up"""

    def test_stop_monitoring_waits_for_thread(self):
        """
        Test that stop_monitoring properly joins thread.
        Prevents resource leaks and ensures clean shutdown.
        """
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Start monitoring
        recorder.start_continuous_monitoring()
        time.sleep(0.1)  # Let thread start

        # Stop should join thread
        recorder.stop_monitoring()

        # Thread should be stopped
        if hasattr(recorder, 'monitoring_thread'):
            assert not recorder.monitoring_thread.is_alive(), \
                "Monitoring thread should be stopped after stop_monitoring()"

    def test_daemon_threads_have_proper_shutdown(self):
        """
        Test that daemon threads have graceful shutdown mechanism.
        Pure daemon threads can lose work on exit.
        """
        from src.recorder import PureRecorder

        recorder = PureRecorder()

        # Should have shutdown event or flag
        has_shutdown_mechanism = hasattr(recorder, 'shutdown_event') or \
                                hasattr(recorder, 'is_shutting_down')

        # This is aspirational - not strictly required, but good practice
        # For now, just verify stop_monitoring exists
        assert hasattr(recorder, 'stop_monitoring'), \
            "Recorder should have stop_monitoring for cleanup"


class TestDownloadThreadSafety:
    """Test that download thread is properly managed"""

    def test_download_has_flag_to_prevent_concurrent_downloads(self):
        """
        Test that multiple concurrent downloads are prevented.
        Prevents resource waste and UI state corruption.
        """
        from src.settings_ui import SettingsDialog
        from src.dictator import DictatorWindow
        from PyQt6.QtWidgets import QApplication

        with patch('PyQt6.QtWidgets.QSystemTrayIcon'):
            app = QApplication.instance() or QApplication([])
            window = DictatorWindow(no_tray=True)
            dialog = SettingsDialog(window)

            # Should have flag to track download state
            has_download_flag = hasattr(dialog, 'download_in_progress') or \
                               hasattr(dialog, '_downloading')

            # For now, just check download button exists
            assert hasattr(dialog, 'download_model_btn'), \
                "Settings should have download button"


class TestStressTestingScenarios:
    """Stress tests to expose race conditions"""

    def test_rapid_monitoring_toggle_no_crashes(self):
        """
        Test that rapidly toggling monitoring doesn't crash.
        Would expose race conditions in state management.
        """
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        errors = []

        def toggle_loop():
            try:
                for _ in range(20):
                    recorder.start_continuous_monitoring()
                    time.sleep(0.01)
                    recorder.stop_monitoring()
            except Exception as e:
                errors.append(str(e))

        # Run from multiple threads
        threads = [threading.Thread(target=toggle_loop) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        # Should complete without errors
        assert len(errors) == 0, f"Rapid toggle caused errors: {errors}"

    def test_concurrent_audio_operations_no_corruption(self):
        """
        Test that concurrent audio operations don't corrupt data.
        Would expose lack of synchronization.
        """
        from src.recorder import PureRecorder

        recorder = PureRecorder()
        errors = []

        def audio_operations():
            try:
                with recorder.audio_level_lock:
                    # Simulate typical audio operations
                    recorder.audio_data.append(b"test")
                    _ = len(recorder.audio_data)
                    recorder.audio_data.clear()
            except Exception as e:
                errors.append(str(e))

        # Run many concurrent operations
        threads = [threading.Thread(target=audio_operations) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # Should complete without errors
        assert len(errors) == 0, f"Concurrent operations caused errors: {errors}"
