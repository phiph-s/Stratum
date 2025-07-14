import io
import time
import os
import multiprocessing as mp
from itertools import product
from functools import wraps

import numpy as np
import trimesh
import geopandas as gpd
from skimage import measure
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely import affinity
from shapely.ops import unary_union
from PIL import Image

# Matplotlib is used for rendering polygons to an image
import matplotlib

matplotlib.use('Agg')  # Use a non-interactive backend suitable for scripts/servers
from matplotlib import pyplot as plt
from matplotlib.path import Path
from matplotlib.patches import PathPatch

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


def extract_color_masks(img_arr, filament_shades):
    """
    Extracts boolean masks for each shade of each filament from an image array.

    Args:
        img_arr (numpy.array): HxWx4 (RGBA) numpy array of the image.
        filament_shades (list): A nested list where filament_shades[f][s] is an RGB tuple.

    Returns:
        dict: A dictionary mapping (filament_index, shade_index) to a boolean mask.
    """
    rgb = img_arr[..., :3]
    masks = {}

    used_shades = set()  # to track used shades, prevent duplicates
    for fi, shades in enumerate(filament_shades):
        for si, shade in enumerate(shades):
            if shade in used_shades:
                print(f"Skipping duplicate shade {shade} for filament {fi}, shade {si}")
                continue
            # exact match on RGB channels
            m = np.all(rgb == shade, axis=2)
            if m.any():
                masks[(fi, si)] = m
                used_shades.add(shade)
    return masks


@timed
def mask_to_polygons(mask, min_area=100, simplify_tol=1.0):
    """
    Converts a boolean mask to a list of Shapely polygons using marching squares.
    """
    padded = np.pad(mask.astype(float), 1, constant_values=0)

    # Convert every *ring* returned by marching-squares into a LineString
    rings = [
        LineString([(p[1], p[0]) for p in c])  # shift because of the 1-pixel pad
        for c in measure.find_contours(padded, 0.5)  # skimage marching squares
    ]

    if not rings:
        return []

    # Build polygons *with holes* at C speed using GEOS/JTS build-area algorithm
    polys = gpd.GeoSeries(rings).build_area()

    # Optional smoothing / simplification
    polys = polys.buffer(0)  # ensure valid shells after build-area
    polys = polys.simplify(simplify_tol)

    # Filter out tiny blobs and return plain Shapely objects
    polys = polys[polys.area >= min_area]

    return list(polys.geometry)


def flip_polygons_vertically(polygons, height_px):
    """Flips a list of Shapely polygons vertically within a given height."""
    polys = [affinity.scale(poly, xfact=1, yfact=-1, origin=(0, 0)) for poly in polygons]
    return [affinity.translate(poly, yoff=height_px) for poly in polys]


@timed
def generate_layer_mesh(polygons, thickness):
    """Generates an extruded 3D mesh from a list of 2D polygons."""
    if not isinstance(polygons, list):
        polygons = [polygons]

    flat_polys = []
    for geom in polygons:
        if isinstance(geom, MultiPolygon):
            flat_polys.extend(geom.geoms)
        else:
            flat_polys.append(geom)

    meshes = []
    for poly in flat_polys:
        if not poly.is_valid or poly.is_empty:
            continue
        m = trimesh.creation.extrude_polygon(poly, thickness)
        meshes.append(m)
    return trimesh.util.concatenate(meshes) if meshes else None


@timed
def merge_layers_downward(meshes_list):
    """
    Performs an in-place cumulative union of meshes, from top to bottom.
    """
    last = None
    for i, meshes in enumerate(meshes_list[::-1]):
        for j, mesh in enumerate(meshes[::-1]):
            if last is None:
                last = mesh
            else:
                last = trimesh.util.concatenate(last, mesh)
                meshes_list[-(i + 1)][-(j + 1)] = last


@timed
def merge_polys_downward(polys_list):
    """
    Performs an in-place cumulative union of polygons, from top to bottom.
    """
    accumulated = None

    # Walk layers from top (last index) down to 0
    for i in range(len(polys_list) - 1, -1, -1):
        layer = polys_list[i]
        # Walk shades from last to first
        for j in range(len(layer) - 1, -1, -1):
            group = layer[j]
            # 1) flatten the small list-of-polygons into one geometry
            if isinstance(group, list):
                poly = unary_union(group) if group else None
            else:
                poly = group

            if poly is None or poly.is_empty:
                continue

            # 2) merge into accumulated
            accumulated = poly if accumulated is None else accumulated.union(poly)

            # 3) write back the running union as a single geometry
            polys_list[i][j] = accumulated

    return polys_list


def _generate_base_mesh(segmented_image, layer_height=0.2, base_layers=4,
                        target_max_cm=10):
    """Generates the solid base mesh for the model."""
    base_height = layer_height * base_layers
    w_px, h_px = segmented_image.size
    scale_xy = (target_max_cm * 10) / max(w_px, h_px)

    # Base layer
    base_rect = Polygon([(0, 0), (w_px, 0), (w_px, h_px), (0, h_px)])
    base_poly = flip_polygons_vertically([base_rect], h_px)
    base_mesh = generate_layer_mesh(base_poly, base_height)
    if base_mesh:
        base_mesh.apply_scale([scale_xy, scale_xy, 1])
        return base_mesh, base_height
    return None, 0


def process_mask(task):
    """Worker function for parallel polygon extraction."""
    (fi, L), mask, h_px, min_area, simplify_tol = task
    if not mask.any():
        return (fi, L, [])
    polys = mask_to_polygons(mask, min_area=min_area, simplify_tol=simplify_tol)
    flipped = flip_polygons_vertically(polys, h_px)
    return (fi, L, flipped)


@timed
def create_layered_polygons_parallel(
        segmented_image,
        shades,
        progress_cb=None,
        min_area=MIN_AREA,
        simplify_tol=SIMPLIFY_TOLERANCE
):
    """
    Creates layered polygons from a segmented image in parallel.
    The progress callback is called directly and is not tied to any GUI framework.
    """
    ensure_dir(OUTPUT_DIR)
    w_px, h_px = segmented_image.size
    seg_arr = np.array(segmented_image.convert("RGBA"))

    masks = extract_color_masks(seg_arr, shades)
    counts_map = {}
    for fi in range(1, len(shades)):
        cnt = np.zeros(seg_arr.shape[:2], dtype=int)
        for si in range(len(shades[fi])):
            m = masks.get((fi, si))
            if m is not None:
                cnt[m] = si + 1
        counts_map[fi] = cnt

    h_px = seg_arr.shape[0]
    tasks = []
    for fi in range(1, len(shades)):
        cnt = counts_map[fi]
        for L in range(1, len(np.unique(cnt)) + 1):
            mask_L = cnt >= L
            tasks.append(((fi, L), mask_L, h_px, min_area, simplify_tol))

    if not tasks:
        if progress_cb: progress_cb(1.0)
        return []

    total = len(tasks)
    results = []
    with mp.Pool(processes=mp.cpu_count()) as pool:
        for i, (fi, L, polys) in enumerate(pool.imap_unordered(process_mask, tasks)):
            results.append((fi, L, polys))
            if progress_cb:
                # Callback is called directly. The calling application is responsible
                # for handling thread safety if updating a GUI.
                progress_cb((i + 1) / total * 0.5)  # This process is the first half.

    polys_map = {}
    for fi, L, polys in results:
        polys_map.setdefault(fi, {})[L] = polys

    polys_list = []
    for fi in range(1, len(shades)):
        poly_list = [polys_map.get(fi, {}).get(L, []) for L in range(1, len(shades[fi]) + 1)]
        if any(poly_list):
            polys_list.append(poly_list)

    base = Polygon([(0, 0), (w_px, 0), (w_px, h_px), (0, h_px)])
    base = flip_polygons_vertically([base], h_px)[0]
    polys_list.insert(0, [[base]])

    return polys_list


def process_generate_layer_mesh(task):
    """Worker function for parallel mesh generation."""
    idx, idy, sublayer, layer_height = task
    try:
        m = generate_layer_mesh(sublayer, layer_height)
        return (idx, idy, m)
    except Exception as e:
        print(f"Error in generate_layer_mesh for layer {idx}, shade {idy}: {e}")
        return (idx, idy, None)


@timed
def polygons_to_meshes_parallel(segmented_image,
                                polys_list,
                                layer_height=0.2,
                                base_layers=4,
                                target_max_cm=10,
                                progress_cb=None):
    """
    Converts layered polygons to a list of 3D meshes in parallel.
    """
    tasks = []
    for idx, polys in enumerate(polys_list):
        for idy, sublayer in enumerate(polys):
            tasks.append((idx, idy, sublayer, layer_height))
    total = len(tasks)
    if total == 0:
        if progress_cb: progress_cb(1.0)
        return []

    results = []
    with mp.Pool(processes=mp.cpu_count()) as pool:
        for n, triple in enumerate(pool.imap(process_generate_layer_mesh, tasks), start=1):
            results.append(triple)
            if progress_cb:
                progress_cb(n / total)

    meshes_dict = {}
    for idx, idy, mesh in results:
        if mesh:
            meshes_dict.setdefault(idx, {})[idy] = mesh

    meshes_list = []
    for idx in sorted(meshes_dict):
        shade_dict = meshes_dict[idx]
        sublayers = [shade_dict[i] for i in sorted(shade_dict)]
        if sublayers:
            meshes_list.append(sublayers)

    merge_layers_downward(meshes_list)
    base_mesh, base_height = _generate_base_mesh(
        segmented_image, layer_height, base_layers, target_max_cm
    )

    w_px, h_px = segmented_image.size
    scale_xy = (target_max_cm * 10) / max(w_px, h_px)
    meshes = [base_mesh] if base_mesh else []
    current_z0 = base_height
    for layer in meshes_list:
        for m in layer:
            m.apply_translation([0, 0, current_z0])
            if not m.is_empty:
                current_z0 += layer_height

        combined = trimesh.util.concatenate(layer)
        combined.apply_scale([scale_xy, scale_xy, 1])
        meshes.append(combined)

    if progress_cb: progress_cb(1.0)
    return meshes


@timed
def render_polygons_to_pil_image(
        layered_polygons,
        filament_shades,
        image_size,
        max_size=10.0,  # Maximum dimension in cm
        bg_color='transparent',
        font_color=(1, 1, 1),
        progress_cb=None,
) -> Image.Image:
    """
    Renders layered polygons to a PIL Image using Matplotlib.
    Always renders the longest side to 1024 pixels without axes or labels.

    Args:
        max_size: The real-world size in cm of the longest dimension
    """
    # Always render longest side to 1024
    target_pixels = 1024
    if image_size[0] > image_size[1]:
        render_w = target_pixels
        render_h = int((image_size[1] / image_size[0]) * target_pixels)
    else:
        render_h = target_pixels
        render_w = int((image_size[0] / image_size[1]) * target_pixels)

    w_px, h_px = image_size
    pixels_per_cm = target_pixels / max_size

    # Set DPI and figure size to get exact pixel dimensions
    dpi = 100
    fig_w_inch = render_w / dpi
    fig_h_inch = render_h / dpi

    flat_polys, flat_colors = [], []
    for layer_idx, layer_groups in enumerate(layered_polygons):
        shades = filament_shades[layer_idx]
        for shade_idx, group in enumerate(layer_groups):
            color = shades[shade_idx] if shade_idx < len(shades) else shades[-1]
            if isinstance(group, (Polygon, MultiPolygon)):
                geoms = [group]
            else:
                geoms = list(group)
            for poly in geoms:
                if not getattr(poly, "is_empty", False):
                    flat_polys.append(poly)
                    flat_colors.append(color)

    fig = plt.figure(figsize=(fig_w_inch, fig_h_inch), dpi=dpi)
    ax = fig.add_subplot(111)
    ax.set_aspect('equal')

    # Remove all axes, labels, and ticks
    ax.set_axis_off()

    if bg_color == 'transparent':
        fig.patch.set_alpha(0.0)
        ax.patch.set_alpha(0.0)
    else:
        fig.patch.set_facecolor(bg_color)
        ax.set_facecolor(bg_color)

    if flat_polys:
        all_polys_union = unary_union(flat_polys)
        minx, miny, maxx, maxy = all_polys_union.bounds

        # Convert pixel coordinates to cm for display
        minx_cm = minx / pixels_per_cm
        miny_cm = miny / pixels_per_cm
        maxx_cm = maxx / pixels_per_cm
        maxy_cm = maxy / pixels_per_cm

        ax.set_xlim(minx_cm, maxx_cm)
        ax.set_ylim(miny_cm, maxy_cm)
    else:
        # Default limits if no polygons
        w_cm = w_px / pixels_per_cm
        h_cm = h_px / pixels_per_cm
        ax.set_xlim(0, w_cm)
        ax.set_ylim(0, h_cm)

    length = len(flat_polys)
    for current, (poly, rgb) in enumerate(zip(flat_polys, flat_colors)):
        geoms = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
        for geom in geoms:
            verts = list(geom.exterior.coords)
            # Convert polygon coordinates to cm
            verts_cm = [(x / pixels_per_cm, y / pixels_per_cm) for x, y in verts]
            codes = [Path.MOVETO] + [Path.LINETO] * (len(verts) - 2) + [Path.CLOSEPOLY]

            for interior in geom.interiors:
                icoords = list(interior.coords)
                icoords_cm = [(x / pixels_per_cm, y / pixels_per_cm) for x, y in icoords]
                verts_cm += icoords_cm
                codes += [Path.MOVETO] + [Path.LINETO] * (len(icoords) - 2) + [Path.CLOSEPOLY]

            path = Path(verts_cm, codes)
            patch = PathPatch(path, facecolor=np.array(rgb) / 255.0, linewidth=0, fill=True)
            ax.add_patch(patch)

        if progress_cb and current % 30 == 0:
            progress_cb(0.5 + (current / length) * 0.5)

    # Export to PNG in memory with exact dimensions, no padding
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0,
                transparent=(bg_color == 'transparent'))
    plt.close(fig)
    buf.seek(0)

    img = Image.open(buf)

    # Ensure the image has the exact target dimensions by resizing if needed
    if img.size != (render_w, render_h):
        img = img.resize((render_w, render_h), Image.Resampling.LANCZOS)

    return img


def image_coords_to_real_coords(image_x, image_y, image_size, rendered_image_size, max_size, layered_polygons):
    """
    Convert image coordinates (from UI click) to real-world coordinates in cm.

    Args:
        image_x, image_y: Click coordinates in the rendered image
        image_size: Original image size (w_px, h_px)
        rendered_image_size: Size of the rendered image (render_w, render_h)
        max_size: Maximum dimension in cm
        layered_polygons: The layered polygons data structure

    Returns:
        (real_x_cm, real_y_cm): Real-world coordinates in centimeters
    """
    w_px, h_px = image_size
    render_w, render_h = rendered_image_size

    # Calculate pixels per cm (same as in render_polygons_to_pil_image)
    target_pixels = 1024
    pixels_per_cm = target_pixels / max_size

    # Get the bounds of all polygons to understand the coordinate system
    flat_polys = []
    for layer_idx, layer_groups in enumerate(layered_polygons):
        for shade_idx, group in enumerate(layer_groups):
            if isinstance(group, (Polygon, MultiPolygon)):
                geoms = [group]
            else:
                geoms = list(group)
            for poly in geoms:
                if not getattr(poly, "is_empty", False):
                    flat_polys.append(poly)

    if flat_polys:
        all_polys_union = unary_union(flat_polys)
        minx, miny, maxx, maxy = all_polys_union.bounds

        # Convert to cm
        minx_cm = minx / pixels_per_cm
        miny_cm = miny / pixels_per_cm
        maxx_cm = maxx / pixels_per_cm
        maxy_cm = maxy / pixels_per_cm
    else:
        # Default bounds
        minx_cm = 0
        miny_cm = 0
        maxx_cm = w_px / pixels_per_cm
        maxy_cm = h_px / pixels_per_cm

    # Convert image coordinates to real coordinates
    # Note: matplotlib y-axis is flipped compared to image coordinates
    real_x_cm = minx_cm + (image_x / render_w) * (maxx_cm - minx_cm)
    real_y_cm = maxy_cm - (image_y / render_h) * (maxy_cm - miny_cm)

    return real_x_cm, real_y_cm


def analyze_position(real_x_cm, real_y_cm, layered_polygons, filament_shades, max_size):
    """
    Analyze what's at a specific real-world position.

    Args:
        real_x_cm, real_y_cm: Real-world coordinates in cm
        layered_polygons: The layered polygons data structure
        filament_shades: The filament shades data structure
        max_size: Maximum dimension in cm

    Returns:
        dict: Analysis results containing layer count, colors, etc.
    """
    # Calculate pixels per cm
    target_pixels = 1024
    pixels_per_cm = target_pixels / max_size

    # Convert cm coordinates back to pixel coordinates for polygon testing
    real_x_px = real_x_cm * pixels_per_cm
    real_y_px = real_y_cm * pixels_per_cm

    from shapely.geometry import Point
    point = Point(real_x_px, real_y_px)

    layers_at_position = []
    total_layer_count = 0

    for layer_idx, layer_groups in enumerate(layered_polygons):
        shades = filament_shades[layer_idx]
        layer_info = {
            'layer_index': layer_idx,
            'filaments': []
        }

        for shade_idx, group in enumerate(layer_groups):
            color = shades[shade_idx] if shade_idx < len(shades) else shades[-1]

            if isinstance(group, (Polygon, MultiPolygon)):
                geoms = [group]
            else:
                geoms = list(group)

            for poly in geoms:
                if not getattr(poly, "is_empty", False) and poly.contains(point):
                    layer_info['filaments'].append({
                        'shade_index': shade_idx,
                        'color': color,
                        'rgb': color
                    })
                    total_layer_count += 1
                    break  # Only count once per shade per layer

        if layer_info['filaments']:
            layers_at_position.append(layer_info)

    return {
        'position_cm': (real_x_cm, real_y_cm),
        'total_layers': total_layer_count,
        'layers': layers_at_position,
        'has_material': total_layer_count > 0
    }
