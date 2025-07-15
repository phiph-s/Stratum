import os
import time
from functools import wraps

# Configuration defaults
OUTPUT_DIR = 'meshes'
SIMPLIFY_TOLERANCE = 0.4  # Simplify tolerance for raw polygons
SMOOTHING_WINDOW = 3  # Window size for contour smoothing
MIN_AREA = 1  # Minimum polygon area to keep


def timed(func):
    """Decorator to print the execution time of a function."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        result = func(*args, **kwargs)
        t1 = time.perf_counter()
        print(f"[TIMING] {func.__name__:25s}: {t1 - t0:0.3f}s")
        return result

    return wrapper


def ensure_dir(path):
    """Ensures that a directory exists, creating it if necessary."""
    if not os.path.exists(path):
        os.makedirs(path)

