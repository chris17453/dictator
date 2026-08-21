"""CUDA and cuDNN discovery, done once and verified.

ctranslate2 links against cuDNN but does not bundle all of it, so a GPU can be
present, visible, and still unusable::

    Unable to load any of {libcudnn_ops.so.9.1.0, libcudnn_ops.so.9, ...}
    Invalid handle. Cannot load symbol cudnnCreateTensorDescriptor

That failure happens inside a native library during the first decode, which
aborts the process — it cannot be caught. So this module does two things
before any model is loaded: it puts the cuDNN directories on the loader path,
and it verifies the whole stack in a *subprocess*, where a crash is an exit
code rather than the end of the daemon.

The old implementation hid this behind a preload hack and a global SSL bypass
in ``__main__``. Detection belongs here, the result is cached, and a machine
without a working GPU falls back to the CPU with a reason it can act on.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..logging import get_logger

log = get_logger(__name__)

#: Where cuDNN turns up, in the order we prefer it.
_SEARCH_HINTS = (
    "nvidia/cudnn/lib",       # nvidia-cudnn-cu12 wheel
    "nvidia/cublas/lib",      # cuBLAS, needed alongside it
    "ctranslate2.libs",       # ctranslate2's own partial bundle
)

_SYSTEM_HINTS = (
    "/usr/lib64",
    "/usr/lib/x86_64-linux-gnu",
    "/usr/local/cuda/lib64",
)


def _site_packages() -> list[Path]:
    out = []
    for entry in sys.path:
        if entry and entry.endswith("site-packages"):
            out.append(Path(entry))
    return out


@lru_cache(maxsize=1)
def library_dirs() -> tuple[str, ...]:
    """Directories holding the CUDA libraries ctranslate2 needs."""
    found: list[str] = []
    for base in _site_packages():
        for hint in _SEARCH_HINTS:
            candidate = base / hint
            if candidate.is_dir():
                found.append(str(candidate))
    for path in _SYSTEM_HINTS:
        candidate = Path(path)
        if candidate.is_dir() and list(candidate.glob("libcudnn*.so*")):
            found.append(str(candidate))
    # Preserve order, drop duplicates.
    return tuple(dict.fromkeys(found))


def prepare_environment() -> dict[str, str]:
    """Put the CUDA libraries where the dynamic loader will find them.

    Returns the environment a subprocess needs. ``LD_LIBRARY_PATH`` is only
    consulted at process start, so setting it here helps children; for this
    process we additionally preload the libraries by hand.
    """
    dirs = library_dirs()
    env = dict(os.environ)
    if dirs:
        existing = env.get("LD_LIBRARY_PATH", "")
        parts = [d for d in dirs if d not in existing.split(os.pathsep)]
        env["LD_LIBRARY_PATH"] = os.pathsep.join(
            [*parts, existing] if existing else parts
        )
    return env


def preload() -> list[str]:
    """Load cuDNN into this process with global symbol visibility.

    ctranslate2 resolves ``cudnnCreateTensorDescriptor`` and friends lazily.
    Loading the libraries RTLD_GLOBAL first means those symbols are already
    present when it looks.
    """
    loaded: list[str] = []
    for directory in library_dirs():
        base = Path(directory)
        # Order matters: the ops and engine libraries depend on the core one.
        for pattern in ("libcudnn.so.9*", "libcudnn_*.so.9*", "libcublas*.so*"):
            for library in sorted(base.glob(pattern)):
                try:
                    ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)
                    loaded.append(library.name)
                except OSError as exc:
                    log.debug("could not preload", library=str(library), error=str(exc))
    if loaded:
        log.debug("preloaded CUDA libraries", count=len(loaded))
    return loaded


@dataclass(frozen=True)
class CudaStatus:
    usable: bool
    reason: str
    device_count: int = 0

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return self.usable


_PROBE = """
import sys
try:
    import ctranslate2
    if ctranslate2.get_cuda_device_count() < 1:
        print("no-devices"); sys.exit(2)
    import numpy as np
    from faster_whisper import WhisperModel
    model = WhisperModel(sys.argv[1], device="cuda", compute_type="int8_float16")
    # A real decode: this is the call that aborts when cuDNN is incomplete.
    list(model.transcribe(np.zeros(16000, dtype=np.float32), beam_size=1)[0])
    print("ok"); sys.exit(0)
except Exception as exc:
    print(f"error: {exc}"); sys.exit(3)
"""


@lru_cache(maxsize=1)
def verify(model_path: str | None = None) -> CudaStatus:
    """Prove CUDA decoding works, in a subprocess that may safely die.

    Without a model to test against we can only report what ctranslate2 claims,
    which is exactly the assumption that produced the crash this module exists
    to prevent — so that case is reported as unverified rather than usable.
    """
    try:
        import ctranslate2

        count = ctranslate2.get_cuda_device_count()
    except Exception as exc:
        return CudaStatus(False, f"ctranslate2 cannot report CUDA support: {exc}")

    if count < 1:
        return CudaStatus(False, "no CUDA devices are visible to ctranslate2")

    if not model_path or not Path(model_path).is_dir():
        return CudaStatus(
            True, f"{count} CUDA device(s) reported, not yet verified by a decode", count
        )

    try:
        result = subprocess.run(
            [sys.executable, "-c", _PROBE, str(model_path)],
            capture_output=True,
            text=True,
            timeout=180,
            env=prepare_environment(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CudaStatus(False, f"could not run the CUDA check: {exc}", count)

    output = (result.stdout or "").strip().splitlines()
    tail = output[-1] if output else (result.stderr or "").strip()[-200:]

    if result.returncode == 0:
        return CudaStatus(True, f"{count} CUDA device(s), decode verified", count)
    if result.returncode < 0:
        return CudaStatus(
            False,
            "the GPU decode crashed, which usually means cuDNN 9 is incomplete "
            f"({tail or 'no output'})",
            count,
        )
    return CudaStatus(False, tail or f"the CUDA check failed (exit {result.returncode})", count)


def remedy() -> str:
    return (
        "Install the matching cuDNN: pip install nvidia-cudnn-cu12 "
        "(or use the CPU: dictator config set model.device cpu)"
    )
