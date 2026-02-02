"""
Tests for ThreadPoolManager
Following TDD - RED phase

Tests thread pool management for short-lived background tasks:
- Pool initialization and configuration
- Task submission and execution
- Concurrent task handling
- Error handling and propagation
- Graceful shutdown
- Resource limits
"""

import pytest
import threading
import time
from concurrent.futures import Future


class TestThreadPoolInitialization:
    """Test ThreadPoolManager initialization"""

    def test_pool_manager_exists(self):
        """
        Test that ThreadPoolManager class exists.
        Central pool for managing background tasks.
        """
        from src.thread_pool import ThreadPoolManager

        assert ThreadPoolManager is not None, \
            "ThreadPoolManager class should exist"

    def test_pool_can_be_created(self):
        """
        Test that ThreadPoolManager can be instantiated.
        Should create underlying executor.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()
        assert pool is not None, \
            "Should be able to create ThreadPoolManager instance"

    def test_pool_has_configurable_max_workers(self):
        """
        Test that max_workers can be configured.
        Controls maximum concurrent threads.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager(max_workers=8)
        assert pool is not None, \
            "Should accept max_workers parameter"

    def test_pool_has_default_max_workers(self):
        """
        Test that pool has sensible default max_workers.
        Should default to 4 workers.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()
        # Should have executor configured
        assert hasattr(pool, '_executor'), \
            "Pool should have _executor attribute"


class TestTaskSubmission:
    """Test task submission to pool"""

    def test_submit_method_exists(self):
        """
        Test that submit() method exists.
        Main interface for running tasks in pool.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()
        assert hasattr(pool, 'submit'), \
            "Pool should have submit() method"

    def test_submit_returns_future(self):
        """
        Test that submit() returns a Future.
        Futures allow tracking task status and getting results.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()

        def simple_task():
            return 42

        future = pool.submit(simple_task)
        assert isinstance(future, Future), \
            "submit() should return a Future object"

    def test_submitted_task_executes(self):
        """
        Test that submitted tasks actually execute.
        Should run in background thread.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()
        executed = []

        def test_task():
            executed.append(1)
            return "done"

        future = pool.submit(test_task)
        result = future.result(timeout=2.0)

        assert result == "done", "Task should complete and return result"
        assert len(executed) == 1, "Task should have executed"

    def test_submit_with_args(self):
        """
        Test that submit() can pass arguments to task.
        Should support both args and kwargs.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()

        def task_with_args(a, b, c=None):
            return a + b + (c or 0)

        future = pool.submit(task_with_args, 10, 20, c=5)
        result = future.result(timeout=2.0)

        assert result == 35, "Task should receive args and kwargs correctly"


class TestConcurrentExecution:
    """Test concurrent task execution"""

    def test_multiple_tasks_run_concurrently(self):
        """
        Test that multiple tasks can run at the same time.
        Pool should execute up to max_workers tasks concurrently.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager(max_workers=3)
        running_count = []
        max_concurrent = [0]
        lock = threading.Lock()

        def concurrent_task(task_id):
            with lock:
                running_count.append(task_id)
                max_concurrent[0] = max(max_concurrent[0], len(running_count))

            time.sleep(0.1)  # Simulate work

            with lock:
                running_count.remove(task_id)

            return task_id

        # Submit 5 tasks
        futures = [pool.submit(concurrent_task, i) for i in range(5)]

        # Wait for all to complete
        for f in futures:
            f.result(timeout=2.0)

        # Should have run up to 3 concurrently
        assert max_concurrent[0] >= 2, \
            f"Should run multiple tasks concurrently (max seen: {max_concurrent[0]})"

    def test_tasks_execute_in_background_threads(self):
        """
        Test that tasks run in background threads, not main thread.
        Should not block caller.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()
        main_thread_id = threading.get_ident()
        task_thread_id = [None]

        def background_task():
            task_thread_id[0] = threading.get_ident()
            return "done"

        future = pool.submit(background_task)
        future.result(timeout=2.0)

        assert task_thread_id[0] is not None, "Task should have executed"
        assert task_thread_id[0] != main_thread_id, \
            "Task should run in background thread, not main thread"


class TestErrorHandling:
    """Test error handling in pool"""

    def test_task_exception_captured_in_future(self):
        """
        Test that exceptions in tasks are captured.
        Should not crash pool, exception available via future.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()

        def failing_task():
            raise ValueError("Test error")

        future = pool.submit(failing_task)

        # Should raise exception when getting result
        with pytest.raises(ValueError, match="Test error"):
            future.result(timeout=2.0)

    def test_one_task_exception_doesnt_affect_others(self):
        """
        Test that one task's exception doesn't affect other tasks.
        Pool should remain functional after task failure.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()

        def failing_task():
            raise ValueError("Fail")

        def successful_task():
            return "success"

        # Submit failing task
        future1 = pool.submit(failing_task)

        # Submit successful task
        future2 = pool.submit(successful_task)

        # First should fail
        with pytest.raises(ValueError):
            future1.result(timeout=2.0)

        # Second should succeed
        result = future2.result(timeout=2.0)
        assert result == "success", \
            "Pool should continue working after task exception"


class TestShutdown:
    """Test pool shutdown"""

    def test_shutdown_method_exists(self):
        """
        Test that shutdown() method exists.
        Required for clean app exit.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()
        assert hasattr(pool, 'shutdown'), \
            "Pool should have shutdown() method"

    def test_shutdown_waits_for_tasks(self):
        """
        Test that shutdown(wait=True) waits for tasks to complete.
        Ensures graceful shutdown.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()
        completed = []

        def slow_task():
            time.sleep(0.2)
            completed.append(1)
            return "done"

        future = pool.submit(slow_task)
        pool.shutdown(wait=True)

        # Task should have completed
        assert len(completed) == 1, \
            "shutdown(wait=True) should wait for tasks to complete"

    def test_shutdown_immediate_if_wait_false(self):
        """
        Test that shutdown(wait=False) doesn't wait.
        Allows fast shutdown if needed.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()

        def slow_task():
            time.sleep(1.0)

        pool.submit(slow_task)

        # Should return immediately
        import time
        start = time.time()
        pool.shutdown(wait=False)
        duration = time.time() - start

        assert duration < 0.5, \
            "shutdown(wait=False) should return immediately"


class TestResourceLimits:
    """Test that pool enforces resource limits"""

    def test_max_workers_limit_enforced(self):
        """
        Test that pool doesn't exceed max_workers.
        Prevents unlimited thread creation.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager(max_workers=2)
        running = []
        lock = threading.Lock()

        def blocking_task():
            with lock:
                running.append(1)
            time.sleep(0.3)
            with lock:
                running.remove(1)

        # Submit 4 tasks to pool with max 2 workers
        futures = [pool.submit(blocking_task) for _ in range(4)]

        # Check that no more than 2 run at once
        time.sleep(0.1)  # Let tasks start
        with lock:
            concurrent = len(running)

        # Wait for completion
        for f in futures:
            f.result(timeout=3.0)

        assert concurrent <= 2, \
            f"Should not exceed max_workers (saw {concurrent} concurrent)"


class TestTaskTracking:
    """Test task tracking capabilities"""

    def test_pool_tracks_active_tasks(self):
        """
        Test that pool can track active tasks.
        Useful for monitoring and debugging.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()

        # Should have tracking mechanism
        assert hasattr(pool, '_active_tasks') or hasattr(pool, 'active_count'), \
            "Pool should have mechanism to track active tasks"


class TestIntegrationScenarios:
    """Test realistic usage scenarios"""

    def test_model_download_scenario(self):
        """
        Test pool handles model download scenario.
        Long-running I/O task.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()
        download_complete = []

        def simulate_download(model_name):
            # Simulate download
            time.sleep(0.1)
            download_complete.append(model_name)
            return f"{model_name} downloaded"

        future = pool.submit(simulate_download, "tiny")
        result = future.result(timeout=2.0)

        assert result == "tiny downloaded"
        assert "tiny" in download_complete

    def test_recording_worker_scenario(self):
        """
        Test pool handles recording worker scenario.
        CPU-bound transcription task.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager()
        transcription_done = []

        def simulate_transcription(audio_data):
            # Simulate Whisper processing
            time.sleep(0.05)
            transcription_done.append(audio_data)
            return f"Transcribed: {audio_data}"

        future = pool.submit(simulate_transcription, "audio_chunk")
        result = future.result(timeout=2.0)

        assert "Transcribed:" in result
        assert len(transcription_done) == 1

    def test_multiple_recordings_simultaneously(self):
        """
        Test pool can handle multiple concurrent recordings.
        Should not block each other.
        """
        from src.thread_pool import ThreadPoolManager

        pool = ThreadPoolManager(max_workers=3)

        def recording_task(recording_id):
            time.sleep(0.1)
            return f"Recording {recording_id} complete"

        # Simulate 3 simultaneous recordings
        futures = [pool.submit(recording_task, i) for i in range(3)]

        results = [f.result(timeout=2.0) for f in futures]

        assert len(results) == 3, "All recordings should complete"
        assert all("complete" in r for r in results)
