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
    target_pixels = 2048
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

    flat_polys, flat_colors = [], []
    for layer_idx, layer_groups in enumerate(layered_polygons):
        shades = filament_shades[layer_idx]
        for shade_idx, group in enumerate(layer_groups):
            color = shades[shade_idx] if shade_idx < len(shades) else shades[-1]
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


def analyze_position_rgb(image_x, image_y, rendered_image, filament_shades):
    """
    Simplified position analysis using direct RGB value lookup in the shade map.
    """
    try:
        rgb_at_position = rendered_image.getpixel((int(image_x), int(image_y)))
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

    rgb_to_shade = {}
    for layer_idx, shades in enumerate(filament_shades):
        for shade_idx, rgb in enumerate(shades):
            rgb_tuple = tuple(rgb) if isinstance(rgb, (list, tuple)) else rgb
            if (not rgb_tuple in rgb_to_shade) or layer_idx < rgb_to_shade[rgb_tuple]['layer_index']:
                rgb_to_shade[rgb_tuple] = {
                    'layer_index': layer_idx,
                    'shade_index': shade_idx,
                    'color': rgb_tuple
                }

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

