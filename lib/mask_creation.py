import math

from PIL import Image
import numpy as np
from skimage.color import rgb2lab

from lib.utils import timed

TRANSMISSION_TO_BLEND_FACTOR = 0.1

@timed
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

@timed
def generate_shades_td(
    filament_order,
    td_values,
    max_layer_values,
    layer_height,
):
    """
    Generate printable shades per filament using an internal RGBA stack model.

    For filament i>0:
      - Build a stack of L layers (L = 1..max_layers[i]),
        each layer having thickness=h=layer_height and color=filament_order[i].
      - Convert per-layer thickness to an opacity (alpha) via the fitted curve:
            thick_ratio = h / td_eff
            alpha = clamp(o + (A*log1p(k*thick_ratio) + b*thick_ratio), 0, 1)
        with constants (o,A,k,b) from the reference implementation.
      - Composite L identical RGBA layers (top→bottom) over the starting color
        (the last shade of the previous filament, preserving your original logic).

    Returns:
        list of lists of RGB tuples
        - Filament 0: [base_color] (as in your original function)
        - Filament i>0: [shade@L=1, shade@L=2, ..., shade@L=max_layers[i]]
    """
    # --- validation to mirror the original expectations
    n = len(filament_order)
    assert len(td_values) == n, "td_values must align with filament_order"
    assert len(max_layer_values) == n, "max_layer_values must align with filament_order"
    assert layer_height > 0, "layer_height must be positive"

    # Opacity fit constants (same as your reference):
    o = -1.2416557e-02
    A =  9.6407950e-01
    k =  3.4103447e01
    b = -4.1554203e00

    def clamp01(x: float) -> float:
        return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)

    def alpha_from_thickness(h: float, td_eff: float) -> float:
        """Map one-layer thickness to opacity using the fitted curve."""
        if td_eff <= 0:
            return 1.0  # degenerate: fully opaque immediately
        thick_ratio = h / td_eff
        # alpha = o + (A*log1p(k*ratio) + b*ratio), then clamped to [0,1]
        a = o + (A * math.log1p(k * thick_ratio) + b * thick_ratio)
        return clamp01(a)

    all_shades = []

    for i, cur in enumerate(filament_order):
        cur = tuple(int(c) for c in cur)
        if i == 0:
            # First filament: original behavior — just return the base color.
            all_shades.append([cur])
            continue

        # Starting/background color for this filament = last shade of previous filament
        base_color = all_shades[i - 1][-1]

        # Effective TD using TD/10 (can tweak here if you calibrate differently)
        td_eff = td_values[i]

        # Per-layer opacity (each physical layer is one 'h' thick)
        h = layer_height
        alpha = alpha_from_thickness(h, td_eff)  # constant per layer of this filament

        # Precompute (1 - alpha) since we raise it a lot
        one_minus_alpha = 1.0 - alpha

        shades = []
        max_layers = max_layer_values[i]

        # Build cumulative RGBA compositing for stacks of L=1..max_layers:
        #   For L identical layers over base:
        #     total_top_weight = 1 - (1 - alpha)**L
        #     C_out = base*(1 - total_top_weight) + top*total_top_weight
        for L in range(1, max_layers + 1):
            # Remaining transmission after L identical layers
            remain_after = one_minus_alpha ** L
            w_top = 1.0 - remain_after  # how much the top color contributes after L layers

            shade = tuple(
                int(round(base_color[c] * (1.0 - w_top) + cur[c] * w_top))
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

