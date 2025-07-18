import numpy as np
import multiprocessing as mp
from .utils import ensure_dir, OUTPUT_DIR, MIN_AREA, SIMPLIFY_TOLERANCE
from .mask_utils import extract_color_masks, mask_to_polygons, flip_polygons_vertically
from .utils import timed


def process_mask(task):
    """Worker function for parallel polygon extraction."""
    (fi, L), mask, h_px, min_area, simplify_tol, marching_squares_level = task
    if not mask.any():
        return (fi, L, [])
    polys = mask_to_polygons(mask, min_area=min_area, simplify_tol=simplify_tol, marching_squares_level=marching_squares_level)
    flipped = flip_polygons_vertically(polys, h_px)
    return (fi, L, flipped)


@timed
def create_layered_polygons_parallel(
        segmented_image,
        shades,
        progress_cb=None,
        min_area=MIN_AREA,
        simplify_tol=SIMPLIFY_TOLERANCE,
        marching_squares_level=0.5
):
    """
    Creates layered polygons from a segmented image in parallel.
    """
    ensure_dir(OUTPUT_DIR)
    seg_arr = np.array(segmented_image.convert("RGBA"))

    masks = extract_color_masks(seg_arr, shades)
    counts_map = {}
    for fi in range(len(shades)):
        cnt = np.zeros(seg_arr.shape[:2], dtype=int)
        for si in range(len(shades[fi])):
            m = masks.get((fi, si))
            if m is not None:
                cnt[m] = si + 1
        counts_map[fi] = cnt

    h_px = seg_arr.shape[0]
    tasks = []
    for fi in range(len(shades)):
        cnt = counts_map[fi]
        for L in range(1, len(shades[fi]) + 1):
            mask_L = cnt >= L
            tasks.append(((fi, L), mask_L, h_px, min_area, simplify_tol, marching_squares_level))

    if not tasks:
        if progress_cb: progress_cb(1.0)
        return []

    total = len(tasks)
    results = []
    with mp.Pool(processes=mp.cpu_count()) as pool:
        for i, (fi, L, polys) in enumerate(pool.imap_unordered(process_mask, tasks)):
            results.append((fi, L, polys))
            if progress_cb:
                progress_cb((i + 1) / total * 0.5)

    polys_map = {}
    for fi, L, polys in results:
        polys_map.setdefault(fi, {})[L] = polys

    polys_list = []
    for fi in range(len(shades)):
        poly_list = [polys_map.get(fi, {}).get(L, []) for L in range(1, len(shades[fi]) + 1)]
        polys_list.append(poly_list)

    return polys_list

