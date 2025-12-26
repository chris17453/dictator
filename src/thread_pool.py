"""
Thread Pool Management for DICTATOR

Centralized thread pool for short-lived background tasks.
Long-lived threads (monitoring, watchdog) remain dedicated.
Short-lived tasks (downloads, recordings, tests) use this pool.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any

try:
    from logger import get_logger
except ImportError:
    from .logger import get_logger

log = get_logger(__name__)


class ThreadPoolManager:
    """
    Centralized thread pool for short-lived background tasks.

    Manages a pool of worker threads for executing tasks asynchronously.
    Prevents unlimited thread creation and provides better resource control.

    Usage:
        pool = ThreadPoolManager(max_workers=4)
        future = pool.submit(my_function, arg1, arg2)
        result = future.result()  # Wait for completion
        pool.shutdown()  # Clean shutdown
    """

    def __init__(self, max_workers: int = 4):
        """
        Initialize thread pool manager.

        Args:
            max_workers: Maximum number of concurrent worker threads (default: 4)
        """
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="dictator-pool-"
        )
        self._active_tasks = {}  # Future -> task info
        self._lock = threading.Lock()
        self._shutdown = False

        log.info(f"Thread pool initialized with {max_workers} workers")

    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        """
        Submit a task to the thread pool for execution.

        Args:
            fn: Callable to execute in background thread
            *args: Positional arguments to pass to fn
            **kwargs: Keyword arguments to pass to fn

        Returns:
            Future object representing the task execution

        Raises:
            RuntimeError: If pool has been shutdown

        Example:
            future = pool.submit(download_model, "tiny")
            result = future.result(timeout=60)
        """
        if self._shutdown:
            raise RuntimeError("Cannot submit tasks to shutdown pool")

        log.debug(f"Submitting task: {fn.__name__}")

        future = self._executor.submit(fn, *args, **kwargs)

        # Track active task
        with self._lock:
            self._active_tasks[future] = {
                'function': fn.__name__,
                'submitted_at': threading.current_thread().name
            }

        # Add callback to remove from tracking when done
        def cleanup(f):
            with self._lock:
                self._active_tasks.pop(f, None)

        future.add_done_callback(cleanup)

        return future

    def shutdown(self, wait: bool = True):
        """
        Shutdown the thread pool.

        Args:
            wait: If True, wait for all tasks to complete before returning.
                  If False, return immediately (tasks may still be running).

        Note:
            After shutdown(), submit() will raise RuntimeError.
        """
        log.info(f"Shutting down thread pool (wait={wait})")

        self._shutdown = True
        self._executor.shutdown(wait=wait)

        if wait:
            log.info("Thread pool shutdown complete")
        else:
            log.info("Thread pool shutdown initiated (not waiting)")

    def active_count(self) -> int:
        """
        Get count of currently active tasks.

        Returns:
            Number of tasks currently executing or queued
        """
        with self._lock:
            return len(self._active_tasks)

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - shutdown pool"""
        self.shutdown(wait=True)
        return False

    def __del__(self):
        """Cleanup on deletion"""
        if not self._shutdown:
            self.shutdown(wait=False)
