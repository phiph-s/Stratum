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

    flat_polys, flat_colors = [], []
    for layer_idx, layer_groups in enumerate(layered_polygons):
        shades = filament_shades[layer_idx]
        for shade_idx, group in enumerate(layer_groups):
            if shade_idx >= len(shades):
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


def render_polygons_to_svg(
        layered_polygons,
        filament_shades,
        image_size,
        max_size=10.0,  # Maximum dimension in cm
        bg_color='white',
        progress_cb=None,
) -> str:
    """
    Renders layered polygons to SVG format with pixel-perfect RGB values.

    Args:
        layered_polygons: List of polygon layers
        filament_shades: RGB color values for each shade
        image_size: Original image size (width, height)
        max_size: The real-world size in cm of the longest dimension
        bg_color: Background color ('white', 'none', or hex color)
        progress_cb: Optional progress callback function

    Returns:
        str: SVG content as a string
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

    # Flatten polygons and colors
    flat_polys, flat_colors = [], []
    for layer_idx, layer_groups in enumerate(layered_polygons):
        shades = filament_shades[layer_idx]
        for shade_idx, group in enumerate(layer_groups):
            if shade_idx >= len(shades):
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

    # Calculate viewBox bounds - use image coordinate system
    view_w_cm = w_px / pixels_per_cm
    view_h_cm = h_px / pixels_per_cm

    # Start building SVG
    svg_parts = []

    # SVG header - use image dimensions for viewBox
    bg_style = ""
    if bg_color != 'none':
        if bg_color.startswith('#'):
            bg_style = f' style="background-color: {bg_color};"'
        else:
            bg_style = f' style="background-color: {bg_color};"'

    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                    f'width="{render_w}" height="{render_h}" '
                    f'viewBox="0 0 {view_w_cm} {view_h_cm}"{bg_style}>')

    # Add background rectangle if needed
    if bg_color != 'none':
        svg_parts.append(f'<rect x="0" y="0" width="{view_w_cm}" height="{view_h_cm}" '
                        f'fill="{bg_color}"/>')

    # Render polygons
    length = len(flat_polys)
    for current, (poly, rgb) in enumerate(zip(flat_polys, flat_colors)):
        # Convert RGB to hex
        hex_color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

        geoms = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
        for geom in geoms:
            # Convert exterior coordinates to cm and flip Y-axis
            exterior_coords = list(geom.exterior.coords)
            exterior_cm = [(x / pixels_per_cm, (h_px - y) / pixels_per_cm) for x, y in exterior_coords]

            # Build path data for exterior
            path_data = f"M {exterior_cm[0][0]},{exterior_cm[0][1]} "
            for x, y in exterior_cm[1:]:
                path_data += f"L {x},{y} "
            path_data += "Z "

            # Add holes (interiors)
            for interior in geom.interiors:
                interior_coords = list(interior.coords)
                interior_cm = [(x / pixels_per_cm, (h_px - y) / pixels_per_cm) for x, y in interior_coords]
                path_data += f"M {interior_cm[0][0]},{interior_cm[0][1]} "
                for x, y in interior_cm[1:]:
                    path_data += f"L {x},{y} "
                path_data += "Z "

            # Add path element
            svg_parts.append(f'<path d="{path_data}" fill="{hex_color}" stroke="none" fill-rule="evenodd"/>')

        if progress_cb and current % 30 == 0:
            progress_cb(0.5 + (current / length) * 0.5)

    # Close SVG
    svg_parts.append('</svg>')

    return '\n'.join(svg_parts)
