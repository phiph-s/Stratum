import numpy as np
import math
from typing import List, Dict, Tuple, Any

def clamp01(x: float) -> float:
    """Clamp value to [0, 1] range."""
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def alpha_from_thickness(h: float, td_eff: float) -> float:
    """Map layer thickness to opacity using fitted curve from original implementation."""
    if td_eff <= 0:
        return 1.0

    # Constants from original implementation
    o = -1.2416557e-02
    A = 9.6407950e-01
    k = 3.4103447e01
    b = -4.1554203e00

    thick_ratio = h / td_eff
    alpha = o + (A * math.log1p(k * thick_ratio) + b * thick_ratio)
    return clamp01(alpha)


def composite_colors(base_rgb: Tuple[int, int, int],
                    top_rgb: Tuple[int, int, int],
                    alpha: float) -> Tuple[int, int, int]:
    """Composite top color over base with given alpha using proper blending."""
    return tuple(
        int(round(base_rgb[i] * (1.0 - alpha) + top_rgb[i] * alpha))
        for i in range(3)
    )


def color_distance(color1: Tuple[int, int, int], color2: Tuple[int, int, int]) -> float:
    """Calculate Euclidean distance between two RGB colors."""
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(color1, color2)))


def simulate_color_blend(base_color: Tuple[int, int, int],
                        filament_color: Tuple[int, int, int],
                        filament_alpha: float) -> Tuple[int, int, int]:
    """Simulate what color results from blending a filament over a base."""
    return composite_colors(base_color, filament_color, filament_alpha)


def calculate_color_sequence(target_rgb: Tuple[int, int, int],
                           available_filaments: Dict[str, Dict[str, Any]],
                           base_filament: str = None,
                           layer_height: float = 0.1,
                           max_layers: int = 5) -> List[str]:
    """
    Determine the sequence of filament colors to build up the target color.
    Uses dynamic color matching based on available filaments.

    Args:
        target_rgb: Target color to achieve
        available_filaments: Dict of filament_name -> {'color': (r,g,b), 'td': float}
        base_filament: Name of base filament (substrate), must be in available_filaments
        layer_height: Height of each layer for alpha calculation
        max_layers: Maximum number of layers to use

    Returns:
        List of filament names in the order they should be applied
    """
    if not available_filaments:
        return []

    # Calculate alpha values for each filament
    filament_alphas = {
        name: alpha_from_thickness(layer_height, filament['td'])
        for name, filament in available_filaments.items()
    }

    # Ensure base filament is valid and in available_filaments
    if base_filament is None or base_filament not in available_filaments:
        base_filament = max(available_filaments.keys(),
                          key=lambda name: sum(available_filaments[name]['color']))

    # Start with base color (substrate)
    current_color = available_filaments[base_filament]['color']
    sequence = []

    # For very bright colors, check if starting with white gives better results
    # but only if white is different from the base filament
    target_brightness = int(target_rgb[0]) + int(target_rgb[1]) + int(target_rgb[2])
    if (target_brightness > 600 and 'white' in available_filaments and
        base_filament != 'white'):
        white_start_distance = color_distance(target_rgb, available_filaments['white']['color'])
        base_start_distance = color_distance(target_rgb, current_color)
        if white_start_distance < base_start_distance:
            current_color = available_filaments['white']['color']
            sequence.append('white')  # Add white as first layer over base

    # Calculate average transparency to adapt stopping criteria
    avg_alpha = sum(filament_alphas.values()) / len(filament_alphas)
    # More transparent filaments (higher TD, lower alpha) need more lenient stopping
    min_improvement = 0.5 if avg_alpha < 0.6 else (0.8 if avg_alpha < 0.8 else 1.0)

    # Iteratively find best filament to get closer to target
    for layer in range(max_layers - len(sequence)):  # Account for any layers already added
        best_filament = None
        best_distance = float('inf')
        best_result_color = current_color

        # Try each available filament (including the base filament again)
        for filament_name, filament_data in available_filaments.items():
            filament_color = filament_data['color']
            alpha = filament_alphas[filament_name]

            # Simulate blending this filament over current color
            result_color = simulate_color_blend(current_color, filament_color, alpha)
            distance = color_distance(target_rgb, result_color)

            # Check if this gets us closer to target
            if distance < best_distance:
                best_distance = distance
                best_filament = filament_name
                best_result_color = result_color

        # Stop if we're already very close or not making progress
        current_distance = color_distance(target_rgb, current_color)
        improvement = current_distance - best_distance
        if current_distance < 2 or improvement < min_improvement:
            break

        # Add best filament to sequence and update current color
        sequence.append(best_filament)
        current_color = best_result_color

    return sequence

def calculate_dither_blend(base_color: Tuple[int, int, int],
                          dither_color: Tuple[int, int, int],
                          dither_alpha: float,
                          dither_ratio: float) -> Tuple[int, int, int]:
    """
    Calculate the effective color when dithering one filament over another.
    This represents the "logical" color that subsequent layers will blend with.

    Args:
        base_color: Color of the base layer
        dither_color: Color of the dithered filament
        dither_alpha: Alpha value of the dithered filament
        dither_ratio: Fraction of area covered by dither (0.0 to 1.0)

    Returns:
        Effective blended color representing the dithered surface
    """
    if dither_ratio <= 0:
        return base_color
    if dither_ratio >= 1:
        return composite_colors(base_color, dither_color, dither_alpha)

    # Calculate color where dither exists
    dithered_color = composite_colors(base_color, dither_color, dither_alpha)

    # Average between base and dithered areas
    effective_color = tuple(
        int(round(base_color[i] * (1.0 - dither_ratio) + dithered_color[i] * dither_ratio))
        for i in range(3)
    )

    return effective_color


def should_use_dithering(target_color: Tuple[int, int, int],
                        best_sequential_color: Tuple[int, int, int],
                        available_filaments: Dict[str, Dict[str, Any]],
                        current_base: Tuple[int, int, int],
                        layer_height: float = 0.1,
                        dither_threshold: float = 5.0) -> bool:
    """
    Determine if dithering could significantly improve color matching.
    Only use dithering when sequential layering isn't good enough.

    Args:
        target_color: The color we're trying to achieve
        best_sequential_color: Best color achievable with sequential layers
        available_filaments: Available filament colors and properties
        current_base: Current base color to dither on
        layer_height: Layer height for alpha calculation
        dither_threshold: Use dithering if it improves error by this amount

    Returns:
        True if dithering should be used
    """
    sequential_error = color_distance(target_color, best_sequential_color)

    # Try dithering with each available filament
    best_dither_error = sequential_error

    for filament_name, filament_data in available_filaments.items():
        filament_color = filament_data['color']
        alpha = alpha_from_thickness(layer_height, filament_data['td'])

        # Try different dither ratios
        for ratio in [0.25, 0.5, 0.75]:
            dithered_result = calculate_dither_blend(current_base, filament_color, alpha, ratio)
            dither_error = color_distance(target_color, dithered_result)
            best_dither_error = min(best_dither_error, dither_error)

    # Use dithering if it provides significant improvement
    improvement = sequential_error - best_dither_error
    return improvement > dither_threshold


def find_best_dither(target_color: Tuple[int, int, int],
                    available_filaments: Dict[str, Dict[str, Any]],
                    current_base: Tuple[int, int, int],
                    layer_height: float = 0.1) -> Tuple[str, float, str]:
    """
    Find the best dithering solution for a target color.

    Args:
        target_color: The color we're trying to achieve
        available_filaments: Available filament colors and properties
        current_base: Current base color to dither on
        layer_height: Layer height for alpha calculation

    Returns:
        Tuple of (best_filament_name, best_ratio, best_pattern_type)
    """
    best_error = float('inf')
    best_filament = None
    best_ratio = 0.0
    best_pattern = 'horizontal'

    for filament_name, filament_data in available_filaments.items():
        filament_color = filament_data['color']
        alpha = alpha_from_thickness(layer_height, filament_data['td'])

        # Try different ratios and patterns
        for ratio in [0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875]:
            for pattern in ['horizontal', 'vertical']:
                dithered_result = calculate_dither_blend(current_base, filament_color, alpha, ratio)
                error = color_distance(target_color, dithered_result)

                if error < best_error:
                    best_error = error
                    best_filament = filament_name
                    best_ratio = ratio
                    best_pattern = pattern

    return best_filament, best_ratio, best_pattern

def calculate_color_sequence_with_dithering(target_rgb: Tuple[int, int, int],
                                           available_filaments: Dict[str, Dict[str, Any]],
                                           base_filament: str = None,
                                           layer_height: float = 0.1,
                                           max_layers: int = 5) -> Dict[str, Any]:
    """
    Enhanced color sequence calculation that uses dithering only when sequential
    layering can't achieve the target color effectively.

    Returns:
        Dict with 'type': 'sequential' or 'dithered', and relevant parameters
    """
    # Ensure base_filament is valid and in available_filaments
    if base_filament is None or base_filament not in available_filaments:
        base_filament = max(available_filaments.keys(),
                          key=lambda name: sum(available_filaments[name]['color']))

    # First, try sequential approach
    sequential_sequence = calculate_color_sequence(
        target_rgb, available_filaments, base_filament, layer_height, max_layers
    )

    # Calculate what color sequential approach achieves (starting from base)
    current_color = available_filaments[base_filament]['color']

    # For very bright colors, check if starting with white gives better results
    # but only if white is different from the base filament
    target_brightness = int(target_rgb[0]) + int(target_rgb[1]) + int(target_rgb[2])
    if (target_brightness > 600 and 'white' in available_filaments and
        base_filament != 'white'):
        white_start_distance = color_distance(target_rgb, available_filaments['white']['color'])
        base_start_distance = color_distance(target_rgb, current_color)
        if white_start_distance < base_start_distance:
            current_color = available_filaments['white']['color']

    # Simulate sequential result
    for filament_name in sequential_sequence:
        if filament_name in available_filaments:
            filament_color = available_filaments[filament_name]['color']
            alpha = alpha_from_thickness(layer_height, available_filaments[filament_name]['td'])
            current_color = composite_colors(current_color, filament_color, alpha)

    sequential_result_color = current_color

    # Check if dithering could improve things significantly
    if should_use_dithering(target_rgb, sequential_result_color, available_filaments, current_color):
        # Find best dithering solution
        best_filament, best_ratio, best_pattern = find_best_dither(
            target_rgb, available_filaments, current_color, layer_height
        )

        return {
            'type': 'dithered',
            'base_sequence': sequential_sequence,
            'dither_filament': best_filament,
            'dither_ratio': best_ratio,
            'dither_pattern': best_pattern,
            'base_color': current_color
        }
    else:
        return {
            'type': 'sequential',
            'sequence': sequential_sequence
        }