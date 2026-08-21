"""A fixed-capacity ring buffer of audio frames.

This is what makes the first word survive. Capture runs continuously, so when
the chord finally registers there is already several hundred milliseconds of
audio in hand — the speech that happened while the user's finger was still
moving (v2.md §4.4, G-09).
"""
from __future__ import annotations

import threading

import numpy as np


class RingBuffer:
    """Lock-protected mono float32 ring buffer.

    Written from the PortAudio callback thread and read from the event loop,
    so every operation takes the lock. The lock is held only for a memcpy,
    which is far cheaper than the callback deadline.
    """

    def __init__(self, capacity_samples: int) -> None:
        if capacity_samples <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = int(capacity_samples)
        self._buffer = np.zeros(self._capacity, dtype=np.float32)
        self._write = 0
        self._filled = 0
        self._lock = threading.Lock()
        #: Total samples ever written, for continuity checks.
        self.total_written = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return self._filled

    def clear(self) -> None:
        with self._lock:
            self._write = 0
            self._filled = 0

    def write(self, samples: np.ndarray) -> None:
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
        count = data.size
        if count == 0:
            return
        with self._lock:
            self.total_written += count
            if count >= self._capacity:
                # A single write larger than the buffer: keep only the tail.
                self._buffer[:] = data[-self._capacity :]
                self._write = 0
                self._filled = self._capacity
                return
            end = self._write + count
            if end <= self._capacity:
                self._buffer[self._write : end] = data
            else:
                split = self._capacity - self._write
                self._buffer[self._write :] = data[:split]
                self._buffer[: count - split] = data[split:]
            self._write = end % self._capacity
            self._filled = min(self._capacity, self._filled + count)

    def read_last(self, count: int) -> np.ndarray:
        """The most recent ``count`` samples, oldest first."""
        with self._lock:
            count = min(int(count), self._filled)
            if count <= 0:
                return np.zeros(0, dtype=np.float32)
            start = (self._write - count) % self._capacity
            if start + count <= self._capacity:
                return self._buffer[start : start + count].copy()
            split = self._capacity - start
            return np.concatenate(
                (self._buffer[start:].copy(), self._buffer[: count - split].copy())
            )

    def read_all(self) -> np.ndarray:
        return self.read_last(self._capacity)
