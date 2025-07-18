import io
from PIL import Image
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.path import Path
from matplotlib.patches import PathPatch
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union
from .utils import timed


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
    Always renders the longest side to 2048 pixels without axes or labels.

    Args:
        max_size: The real-world size in cm of the longest dimension
    """
    target_pixels = 4096  # Target pixel size for the longest side
    if image_size[0] > image_size[1]:
        render_w = target_pixels
        render_h = int((image_size[1] / image_size[0]) * target_pixels)
    else:
        render_h = target_pixels
        render_w = int((image_size[0] / image_size[1]) * target_pixels)

    w_px, h_px = image_size
    pixels_per_cm = target_pixels / max_size
    dpi = 100
    fig_w_inch = render_w / dpi
    fig_h_inch = render_h / dpi

    print(f"DEBUG: Total layers: {len(layered_polygons)}")
    print(f"DEBUG: Total filament layers: {len(filament_shades)}")
    for layer_idx, layer_groups in enumerate(layered_polygons):
        shades = filament_shades[layer_idx]
        print(f"DEBUG: Layer {layer_idx}: {len(layer_groups)} layer_groups, {len(shades)} shades")


    flat_polys, flat_colors = [], []
    for layer_idx, layer_groups in enumerate(layered_polygons):
        shades = filament_shades[layer_idx]
        for shade_idx, group in enumerate(layer_groups):
            if shade_idx >= len(shades):
                print(f"WARNING: shade_idx {shade_idx} >= len(shades) {len(shades)} for layer {layer_idx}")
                # Verwende shade_idx modulo len(shades) anstatt shades[-1]
                color = shades[shade_idx % len(shades)]
            else:
                color = shades[shade_idx]

            if isinstance(group, (MultiPolygon)):
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
    ax.set_axis_off()
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    if flat_polys:
        all_polys_union = unary_union(flat_polys)
        minx, miny, maxx, maxy = all_polys_union.bounds
        minx_cm = minx / pixels_per_cm
        miny_cm = miny / pixels_per_cm
        maxx_cm = maxx / pixels_per_cm
        maxy_cm = maxy / pixels_per_cm
        ax.set_xlim(minx_cm, maxx_cm)
        ax.set_ylim(miny_cm, maxy_cm)
    else:
        w_cm = w_px / pixels_per_cm
        h_cm = h_px / pixels_per_cm
        ax.set_xlim(0, w_cm)
        ax.set_ylim(0, h_cm)

    length = len(flat_polys)
    for current, (poly, rgb) in enumerate(zip(flat_polys, flat_colors)):
        geoms = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
        for geom in geoms:
            verts = list(geom.exterior.coords)
            verts_cm = [(x / pixels_per_cm, y / pixels_per_cm) for x, y in verts]
            codes = [Path.MOVETO] + [Path.LINETO] * (len(verts) - 2) + [Path.CLOSEPOLY]

            for interior in geom.interiors:
                icoords = list(interior.coords)
                icoords_cm = [(x / pixels_per_cm, y / pixels_per_cm) for x, y in icoords]
                verts_cm += icoords_cm
                codes += [Path.MOVETO] + [Path.LINETO] * (len(icoords) - 2) + [Path.CLOSEPOLY]

            path = Path(verts_cm, codes)
            exact_color = (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
            patch = PathPatch(path, facecolor=exact_color, edgecolor='none', linewidth=0, fill=True, antialiased=False)
            ax.add_patch(patch)

        if progress_cb and current % 30 == 0:
            progress_cb(0.5 + (current / length) * 0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0,
                facecolor=bg_color, edgecolor='none', transparent=bg_color == 'none')
    plt.close(fig)
    buf.seek(0)

    img = Image.open(buf)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    if img.size != (render_w, render_h):
        img = img.resize((render_w, render_h), Image.Resampling.NEAREST)
    return img
