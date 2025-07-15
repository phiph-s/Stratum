import numpy as np
import geopandas as gpd
from skimage import measure
from shapely.geometry import LineString
from shapely import affinity
from shapely.ops import unary_union


def extract_color_masks(img_arr, filament_shades):
    """
    Extracts boolean masks for each shade of each filament from an image array.
    """
    rgb = img_arr[..., :3]
    alpha = img_arr[..., 3:]
    masks = {}

    used_shades = set()
    for fi, shades in enumerate(filament_shades):
        for si, shade in enumerate(shades):
            if shade in used_shades:
                print(f"Skipping duplicate shade {shade} for filament {fi}, shade {si}")
                continue
            if fi != 0:
                m = np.all(rgb == shade, axis=2)
            else:
                m = np.all(alpha != 0, axis=2)
            masks[(fi, si)] = m
            used_shades.add(shade)

    alpha_mask = img_arr[..., 3] == 0
    for key in list(masks.keys()):
        masks[key] = masks[key] & ~alpha_mask

    return masks


def mask_to_polygons(mask, min_area=1, simplify_tol=0.4, marching_squares_level=0.5):
    """
    Converts a boolean mask to a list of Shapely polygons using marching squares.
    """
    padded = np.pad(mask.astype(float), 1, constant_values=0)
    rings = [
        LineString([(p[1], p[0]) for p in c])
        for c in measure.find_contours(padded, marching_squares_level)
    ]

    if not rings:
        return []

    polys = gpd.GeoSeries(rings).build_area()
    polys = polys.buffer(0)
    polys = polys.simplify(simplify_tol)
    polys = polys[polys.area >= min_area]

    return list(polys.geometry)


def flip_polygons_vertically(polygons, height_px):
    """Flips a list of Shapely polygons vertically within a given height."""
    flipped = [affinity.scale(poly, xfact=1, yfact=-1, origin=(0, 0)) for poly in polygons]
    return [affinity.translate(poly, yoff=height_px) for poly in flipped]
