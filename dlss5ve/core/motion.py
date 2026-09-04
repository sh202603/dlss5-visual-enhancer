"""Helpers for the float16 motion fields the native workers consume."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

_THREADS = 4
_pool: ThreadPoolExecutor | None = None
_pool_lock = threading.Lock()


def _executor() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadPoolExecutor(max_workers=_THREADS, thread_name_prefix="motion-f16")
    return _pool


def to_float16(field: np.ndarray) -> np.ndarray:
    """Convert an HxWx2 float32 field to a fresh contiguous float16 array.

    A plain ``astype`` costs ~11 ms for a 1080p field, and ~24 ms inside a
    pipeline where the destination pages are cold. Filling a new buffer from
    four threads (numpy releases the GIL for the copy) brings it to ~3.5 ms
    and keeps page faults off the calling thread's critical path.
    """
    source = np.ascontiguousarray(field, dtype=np.float32)
    output = np.empty(source.shape, dtype=np.float16)
    rows = source.shape[0]
    if rows < 64:
        np.copyto(output, source, casting="unsafe")
        return output
    bounds = [(rows * i) // _THREADS for i in range(_THREADS + 1)]

    def fill(start: int, stop: int) -> None:
        np.copyto(output[start:stop], source[start:stop], casting="unsafe")

    list(_executor().map(lambda span: fill(*span), zip(bounds, bounds[1:])))
    return output
