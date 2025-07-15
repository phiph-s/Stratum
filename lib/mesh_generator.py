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
    alpha = img_arr[..., 3:]
    masks = {}

    used_shades = set()  # to track used shades, prevent duplicates
    for fi, shades in enumerate(filament_shades):
        for si, shade in enumerate(shades):
            if shade in used_shades:
                print(f"Skipping duplicate shade {shade} for filament {fi}, shade {si}")
                continue
            # exact match on RGB channels
            if fi != 0: m = np.all(rgb == shade, axis=2)
            else: m = np.all(alpha != 0, axis=2)
            masks[(fi, si)] = m
            used_shades.add(shade)

    alpha_mask = img_arr[..., 3] == 0
    for key in list(masks.keys()):
        masks[key] = masks[key] & ~alpha_mask

    return masks


@timed
def mask_to_polygons(mask, min_area=100, simplify_tol=1.0, marching_squares_level=0.5):
    """
    Converts a boolean mask to a list of Shapely polygons using marching squares.
    """
    padded = np.pad(mask.astype(float), 1, constant_values=0)

    # Convert every *ring* returned by marching-squares into a LineString
    rings = [
        LineString([(p[1], p[0]) for p in c])  # shift because of the 1-pixel pad
        for c in measure.find_contours(padded, marching_squares_level)  # skimage marching squares
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
        if i == len(meshes_list) - 1: continue
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
        marching_squares_level= 0.5
):
    """
    Creates layered polygons from a segmented image in parallel.
    The progress callback is called directly and is not tied to any GUI framework.
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
        for L in range(1, len(np.unique(cnt)) + 1):
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
                # Callback is called directly. The calling application is responsible
                # for handling thread safety if updating a GUI.
                progress_cb((i + 1) / total * 0.5)  # This process is the first half.

    polys_map = {}
    for fi, L, polys in results:
        polys_map.setdefault(fi, {})[L] = polys

    polys_list = []
    for fi in range(len(shades)):
        poly_list = [polys_map.get(fi, {}).get(L, []) for L in range(1, len(shades[fi]) + 1)]
        if any(poly_list):
            polys_list.append(poly_list)

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

    w_px, h_px = segmented_image.size
    meshes = []
    scale_xy = (target_max_cm * 10) / max(w_px, h_px)
    current_z0 = 0

    for i, layer in enumerate(meshes_list):

        z_scale = 1.0
        if i == 0:
            z_scale = base_layers

        for m in layer:
            m.apply_translation([0, 0, current_z0])
            if not m.is_empty:
                current_z0 += layer_height * z_scale

        combined = trimesh.util.concatenate(layer)
        combined.apply_scale([scale_xy, scale_xy, z_scale])
        meshes.append(combined)

    if progress_cb: progress_cb(1.0)
    return meshes


@timed
def render_polygons_to_pil_image(
        layered_polygons,
        filament_shades,
        image_size,
        max_size=10.0,  # Maximum dimension in cm
        bg_color='none',  # Use solid background for pixel-perfect RGB
        font_color=(1, 1, 1),
        progress_cb=None,
) -> Image.Image:
    """
    Renders layered polygons to a PIL Image using Matplotlib with pixel-perfect RGB values.
    Always renders the longest side to 1024 pixels without axes or labels.

    Args:
        max_size: The real-world size in cm of the longest dimension
    """
    # Always render longest side to 1024
    target_pixels = 2048
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

    # Set solid background for pixel-perfect RGB
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
            # Use exact RGB values normalized to 0-1 range for matplotlib
            exact_color = (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
            patch = PathPatch(path, facecolor=exact_color, edgecolor='none', linewidth=0, fill=True, antialiased=False)
            ax.add_patch(patch)

        if progress_cb and current % 30 == 0:
            progress_cb(0.5 + (current / length) * 0.5)

    # Export to PNG without any compression or antialiasing for pixel-perfect RGB
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0,
                facecolor=bg_color, edgecolor='none', transparent=bg_color == 'none')
    plt.close(fig)
    buf.seek(0)

    img = Image.open(buf)

    # Convert to RGB mode to ensure exact RGB values
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # Ensure the image has the exact target dimensions by resizing if needed
    if img.size != (render_w, render_h):
        img = img.resize((render_w, render_h), Image.Resampling.NEAREST)  # Use NEAREST for pixel-perfect

    return img

def analyze_position_rgb(image_x, image_y, rendered_image, filament_shades):
    """
    Simplified position analysis using direct RGB value lookup in the shade map.

    Args:
        image_x, image_y: Click coordinates in the rendered image
        rendered_image: The PIL Image that was rendered
        filament_shades: The filament shades data structure

    Returns:
        dict: Analysis results containing layer count, colors, etc.
    """
    # Get RGB value at clicked position
    try:
        rgb_at_position = rendered_image.getpixel((int(image_x), int(image_y)))
        # Ensure we have RGB tuple (in case of RGBA or other modes)
        if len(rgb_at_position) > 3:
            rgb_at_position = rgb_at_position[:3]
    except (IndexError, ValueError):
        return {
            'position_px': (image_x, image_y),
            'rgb_value': None,
            'total_layers': 0,
            'layers': [],
            'has_material': False,
            'error': 'Click outside image bounds'
        }

    # Build RGB to shade mapping
    rgb_to_shade = {}
    for layer_idx, shades in enumerate(filament_shades):

        for shade_idx, rgb in enumerate(shades):
            # Ensure RGB is a tuple for consistent hashing
            rgb_tuple = tuple(rgb) if isinstance(rgb, (list, tuple)) else rgb
            # if already exists, only overwrite if lower index
            if (not rgb_tuple in rgb_to_shade) or layer_idx < rgb_to_shade[rgb_tuple]['layer_index']:
                # Store the layer index, shade index, and RGB color
                rgb_to_shade[rgb_tuple] = {
                    'layer_index': layer_idx,
                    'shade_index': shade_idx,
                    'color': rgb_tuple
                }


    # Look up the RGB value
    shade_info = rgb_to_shade.get(rgb_at_position)

    if shade_info:
        layer_at_position = {
            'layer_index': shade_info['layer_index'],
            'filaments': [{
                'shade_index': shade_info['shade_index'],
                'color': shade_info['color'],
                'rgb': shade_info['color']
            }]
        }
        total_layers = 1
        has_material = True
    else:
        layer_at_position = None
        total_layers = 0
        has_material = False

    return {
        'position_px': (image_x, image_y),
        'rgb_value': rgb_at_position,
        'total_layers': total_layers,
        'layer': layer_at_position,
        'has_material': has_material
    }

