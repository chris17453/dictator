# Thread Pool Management Design

## Current Thread Usage Analysis

### Threads Created in Codebase

1. **Model Download Thread** (`settings_ui.py:875`)
   - Type: Short-lived
   - Duration: Minutes (downloading model)
   - Nature: I/O bound
   - Frequency: Rare (user-initiated)
   - **Verdict**: Use thread pool

2. **Recording Worker Thread** (`recorder.py:273`)
   - Type: Short-lived
   - Duration: Seconds to minutes (while recording)
   - Nature: CPU bound (Whisper transcription)
   - Frequency: Frequent (every recording)
   - **Verdict**: Use thread pool

3. **Monitoring Thread** (`recorder.py:320`)
   - Type: Long-lived
   - Duration: Entire app lifetime
   - Nature: Event-driven
   - Frequency: Once at startup
   - **Verdict**: Keep dedicated thread

4. **Watchdog Thread** (`ui_utils.py:25`)
   - Type: Long-lived
   - Duration: Entire app lifetime
   - Nature: Monitoring/polling
   - Frequency: Once at startup
   - **Verdict**: Keep dedicated thread

5. **Hotkey Test Thread** (`hotkey_manager.py:198`)
   - Type: Very short-lived
   - Duration: Milliseconds
   - Nature: Testing input
   - Frequency: Rare (settings change)
   - **Verdict**: Use thread pool

## Proposed Architecture

### ThreadPool Manager

Use Python's `concurrent.futures.ThreadPoolExecutor` with a wrapper class:

```python
from concurrent.futures import ThreadPoolExecutor, Future
import threading

class ThreadPoolManager:
    """
    Centralized thread pool for short-lived background tasks.

    Long-lived threads (monitoring, watchdog) remain dedicated.
    Short-lived tasks (downloads, recordings, tests) use this pool.
    """

    def __init__(self, max_workers=4):
        """
        Args:
            max_workers: Maximum concurrent threads (default 4)
        """
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="dictator-pool-"
        )
        self._active_tasks = {}  # Track running tasks
        self._lock = threading.Lock()

    def submit(self, fn, *args, **kwargs) -> Future:
        """Submit a task to the pool"""

    def shutdown(self, wait=True):
        """Shutdown pool gracefully"""
```

### Benefits

1. **Resource Control**: Limits concurrent threads (prevents resource exhaustion)
2. **Cleaner Code**: No manual thread creation/management
3. **Better Error Handling**: Future-based exceptions
4. **Graceful Shutdown**: Proper cleanup on app exit
5. **Monitoring**: Can track active tasks

### Implementation Plan

1. Create `src/thread_pool.py` with `ThreadPoolManager` class
2. Add comprehensive tests (TDD)
3. Refactor short-lived thread usage:
   - Model download
   - Recording worker
   - Hotkey test
4. Keep long-lived threads as dedicated (monitoring, watchdog)
5. Add shutdown to `close_application()`

### Thread Categorization

**Use Thread Pool:**
- Model downloads (I/O bound, infrequent)
- Recording workers (CPU bound, frequent)
- Hotkey tests (very short, rare)

**Keep Dedicated:**
- Audio monitoring (long-lived, event-driven)
- UI watchdog (long-lived, polling)

### Pool Size

Start with `max_workers=4`:
- 1-2 for recordings (usually only one at a time)
- 1 for downloads (rare)
- 1 spare for hotkey tests or future tasks

Can be increased if needed, but 4 is conservative and safe.
