import math

from PIL import Image
import numpy as np
from skimage.color import rgb2lab

TRANSMISSION_TO_BLEND_FACTOR = 0.1

def segment_to_shades(source_image: Image, filament_shades):
    # Convert to RGBA to handle transparency
    rgba = np.asarray(source_image.convert('RGBA'), dtype=float)
    rgb = rgba[..., :3] / 255.0  # RGB channels normalized to [0,1]
    alpha = rgba[..., 3]  # Alpha channel (0-255)

    # Create transparency mask (alpha = 0 means fully transparent)
    transparent_mask = alpha == 0

    lab = rgb2lab(rgb)  # (H, W, 3)

    h, w, _ = lab.shape
    lab_flat = lab.reshape(-1, 3)  # (H*W, 3)
    transparent_flat = transparent_mask.reshape(-1)  # (H*W,)

    flat_shades = [shade for shade_list in filament_shades for shade in shade_list]
    print(f"Total shades: {len(flat_shades)}")
    shade_rgb = np.array(flat_shades, dtype=float)  # (N, 3), still 0–255

    shade_rgb_norm = shade_rgb / 255.0
    shade_lab = rgb2lab(shade_rgb_norm.reshape(1, -1, 3)).reshape(-1, 3)  # (N, 3)

    dists = np.linalg.norm(lab_flat[:, None, :] - shade_lab[None, :, :], axis=2)

    nearest = np.argmin(dists, axis=1)  # (H*W,)

    seg_flat_rgb = shade_rgb[nearest].astype(np.uint8)  # (H*W, 3)
    seg_rgb = seg_flat_rgb.reshape(h, w, 3)

    # Create alpha channel for output
    seg_alpha = np.where(transparent_mask, 0, 255).astype(np.uint8)

    # Combine RGB and Alpha channels
    seg_rgba = np.dstack([seg_rgb, seg_alpha])

    print(f"Shades used: {np.unique(nearest)}")
    print(f"Transparent pixels preserved: {np.sum(transparent_mask)}")

    return Image.fromarray(seg_rgba, mode='RGBA')


def generate_shades_td(filament_order, td_values, max_layer_values, layer_height):
    """
    Generate printable shades for a sequence of filaments using Transmission Distance (TD).

    Each filament after the first blends with the last shade of the previous filament.
    Blending factor per layer is calculated via exponential attenuation:
        blend = 1 - exp(-h / TD)
    where h = layer_count * layer_height.

    Args:
        filament_order (list of (R, G, B)): List of filament base colors.
        td_values (list of float): Transmission Distance per filament (in mm). Index 0 unused.
        max_layer_values (list of int): Max layers per filament. Index 0 unused.
        layer_height (float): Height of one printing layer (in mm).

    Returns:
        list of lists of RGB tuples: Shades per filament.
    """
    all_shades = []

    for i, cur in enumerate(filament_order):
        if i == 0:
            # First filament: no blending, just the base color
            all_shades.append([tuple(cur)])
        else:
            prev_shades = all_shades[i - 1]
            base_color = prev_shades[-1]  # last shade of previous filament
            print (f"Base color for filament {i}: {base_color}")
            td = td_values[i] * TRANSMISSION_TO_BLEND_FACTOR
            max_layers = max_layer_values[i]
            shades = []

            for L in range(1, max_layers + 1):
                h = L * layer_height
                blend = 1 - math.exp(-h / td)
                shade = tuple(
                    int(round(base_color[c] * (1 - blend) + cur[c] * blend))
                    for c in range(3)
                )
                shades.append(shade)

            all_shades.append(shades)

    return all_shades

# Test TD function
if __name__ == "__main__":
    filament_order = [(0, 0, 0), (255, 255, 255)]
    td_values = [None, 7.5]
    max_layer_values = [None, 5, 3]
    layer_height = 0.2

    shades = generate_shades_td(filament_order, td_values, max_layer_values, layer_height)
    for i, s in enumerate(shades):
        print(f"Filament {i} Shades:")
        for layers, color in zip(range(len(s)), s,):
            print(f"  {layers+1} Schicht(en) → RGB{color}")

    print(shades)