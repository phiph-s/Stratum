"""
Core algorithms for AMS layer generation.

This module contains the main functions for color sequence calculation,
layer generation, dithering, and print simulation.
"""

import numpy as np
import math
from typing import List, Dict, Tuple, Any

# Global cache for color sequences to avoid recalculating identical colors
_color_sequence_cache: Dict[Tuple, Dict[str, Any]] = {}

LAYER_HEIGHT=0.08  # Default layer height in mm for realistic blending

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
                           layer_height: float = LAYER_HEIGHT,
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


def generate_sequential_layers(image_array: np.ndarray, 
                              available_filaments: Dict[str, Dict[str, Any]],
                              base_filament: str = None,
                              layer_height: float = LAYER_HEIGHT,
                              max_layers: int = 5) -> List[Dict[str, List[Tuple[int, int]]]]:
    """
    Generate layers using sequential color building approach with dynamic filament selection.
    Each pixel gets assigned to specific layers based on its color sequence from available filaments.
    
    Args:
        image_array: Input image as numpy array
        available_filaments: Dict of filament_name -> {'color': (r,g,b), 'td': float}
        base_filament: Name of base filament (substrate)
        layer_height: Height of each layer for alpha calculation  
        max_layers: Maximum number of layers to generate
    
    Returns:
        List of layer dictionaries with filament assignments
    """
    height, width = image_array.shape[:2]
    layers = [{}] * max_layers
    
    # Initialize layer dictionaries
    for i in range(max_layers):
        layers[i] = {}
    
    # Process each pixel
    for y in range(height):
        for x in range(width):
            target_color = tuple(image_array[y, x])
            color_sequence = calculate_color_sequence(
                target_color, 
                available_filaments, 
                base_filament, 
                layer_height, 
                max_layers
            )
            
            # Assign this pixel to layers based on its sequence
            for layer_idx, filament_name in enumerate(color_sequence):
                if layer_idx < max_layers:
                    if filament_name not in layers[layer_idx]:
                        layers[layer_idx][filament_name] = []
                    layers[layer_idx][filament_name].append((x, y))
    
    return layers


def generate_dither_pattern(width: int, height: int, ratio: float, pattern_type: str = 'horizontal') -> np.ndarray:
    """
    Generate 3D-printer friendly dithering patterns (horizontal or vertical lines).
    
    Args:
        width, height: Pattern dimensions
        ratio: Fraction of pixels that should be True (0.0 to 1.0)
        pattern_type: 'horizontal' or 'vertical'
    
    Returns:
        Boolean array where True means use the dither filament
    """
    pattern = np.zeros((height, width), dtype=bool)
    
    if ratio <= 0:
        return pattern
    if ratio >= 1:
        return np.ones((height, width), dtype=bool)
    
    if pattern_type == 'horizontal':
        # Horizontal line pattern - better for FDM printing
        line_spacing = max(1, int(1.0 / ratio))
        for y in range(0, height, line_spacing):
            pattern[y, :] = True
    elif pattern_type == 'vertical':
        # Vertical line pattern
        line_spacing = max(1, int(1.0 / ratio))
        for x in range(0, width, line_spacing):
            pattern[:, x] = True
    
    return pattern


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
                        layer_height: float = LAYER_HEIGHT,
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
                    layer_height: float = LAYER_HEIGHT) -> Tuple[str, float, str]:
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
                                           layer_height: float = LAYER_HEIGHT,
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


def calculate_color_sequence_with_dithering_cached(target_rgb: Tuple[int, int, int], 
                                                 available_filaments: Dict[str, Dict[str, Any]], 
                                                 base_filament: str = None,
                                                 layer_height: float = LAYER_HEIGHT,
                                                 max_layers: int = 5) -> Dict[str, Any]:
    """
    Cached version of calculate_color_sequence_with_dithering for better performance.
    Uses a global cache to avoid recalculating identical target colors.
    """
    # Create cache key from parameters
    filament_key = tuple(sorted((name, tuple(data['color']), data['td']) 
                               for name, data in available_filaments.items()))
    cache_key = (target_rgb, filament_key, base_filament, layer_height, max_layers)
    
    # Check cache first
    if cache_key in _color_sequence_cache:
        return _color_sequence_cache[cache_key]
    
    # Calculate if not in cache
    result = calculate_color_sequence_with_dithering(
        target_rgb, available_filaments, base_filament, layer_height, max_layers
    )
    
    # Store in cache
    _color_sequence_cache[cache_key] = result
    return result


def clear_color_sequence_cache():
    """Clear the color sequence cache. Call this when switching filament sets."""
    global _color_sequence_cache
    _color_sequence_cache.clear()
    print(f"Color sequence cache cleared")


def generate_enhanced_layers(image_array: np.ndarray, 
                           available_filaments: Dict[str, Dict[str, Any]],
                           base_filament: str = None,
                           layer_height: float = LAYER_HEIGHT,
                           max_layers: int = 5,
                           allow_top_layer_dithering: bool = False,
                           min_layers_between_dithering: int = 0,
                           max_size: float = None,
                           line_width: float = None) -> Tuple[List[Dict[str, List[Tuple[int, int]]]], Dict]:
    """
    Enhanced layer generation with per-pixel dithering constraints and base filament fixes.
    
    Args:
        image_array: Input image as numpy array
        available_filaments: Dict of filament_name -> {'color': (r,g,b), 'td': float}
        base_filament: Name of base filament (must be in available_filaments)
        layer_height: Height of each layer for alpha calculation
        max_layers: Maximum number of layers to generate
        allow_top_layer_dithering: If False, prevents dithering on the topmost layer FOR EACH PIXEL
        min_layers_between_dithering: Minimum number of non-dithered layers between dithered layers FOR EACH PIXEL
        max_size: Maximum size of the longer side in mm (for dither pattern sizing)
        line_width: Minimum line width in mm (for dither pattern sizing)
    
    Returns:
        Tuple of (layers, dither_info) where dither_info contains dithering patterns
    """
    height, width = image_array.shape[:2]
    layers = [{}] * max_layers
    dither_info = {}  # Store dithering information for visualization
    
    # Ensure base_filament is valid and in available_filaments
    if base_filament is None or base_filament not in available_filaments:
        base_filament = max(available_filaments.keys(), 
                          key=lambda name: sum(available_filaments[name]['color']))
        print(f"Using '{base_filament}' as base filament (automatically selected)")
    
    # Calculate appropriate dither pattern size based on physical constraints
    if max_size is not None and line_width is not None:
        # Calculate pixel size in mm based on actual image dimensions
        longer_side = max(width, height)
        pixel_size = max(max_size / longer_side, line_width)
        
        # Calculate minimum pattern size to respect line width
        min_pattern_pixels = max(1, int(line_width / pixel_size))
        # Use a pattern size that's at least the minimum and preferably a power of 2
        pattern_size = max(8, 2 ** int(np.ceil(np.log2(min_pattern_pixels))))
        
        print(f"Physical constraints: pixel_size={pixel_size:.3f}mm, pattern_size={pattern_size}px (image: {width}x{height})")
    else:
        # Default pattern size when no physical constraints provided
        pattern_size = 8
    
    # Track which layers have dithering for each pixel position
    pixel_dithered_layers = {}  # (x,y) -> set of layer indices with dithering
    pixel_top_layers = {}       # (x,y) -> highest layer index used for this pixel
    
    # Initialize layer dictionaries
    for i in range(max_layers):
        layers[i] = {}
    
    # Process each pixel
    for y in range(height):
        for x in range(width):
            target_color = tuple(image_array[y, x])
            pixel_pos = (x, y)
            
            # Get enhanced color solution (sequential or dithered) - using cached version
            solution = calculate_color_sequence_with_dithering_cached(
                target_color, 
                available_filaments, 
                base_filament, 
                layer_height, 
                max_layers
            )
            
            if solution['type'] == 'sequential':
                # Standard sequential approach
                color_sequence = solution['sequence']
                for layer_idx, filament_name in enumerate(color_sequence):
                    if layer_idx < max_layers:
                        if filament_name not in layers[layer_idx]:
                            layers[layer_idx][filament_name] = []
                        layers[layer_idx][filament_name].append((x, y))
                        
                        # Track the highest layer for this pixel
                        pixel_top_layers[pixel_pos] = layer_idx
                        
            elif solution['type'] == 'dithered':
                # First apply base sequence
                base_sequence = solution['base_sequence']
                for layer_idx, filament_name in enumerate(base_sequence):
                    if layer_idx < max_layers:
                        if filament_name not in layers[layer_idx]:
                            layers[layer_idx][filament_name] = []
                        layers[layer_idx][filament_name].append((x, y))
                        
                        # Track the highest layer for this pixel
                        pixel_top_layers[pixel_pos] = layer_idx
                
                # Then apply dithering - place it in a separate intermediate layer ABOVE the base sequence
                dither_filament = solution['dither_filament']
                dither_ratio = solution['dither_ratio']
                dither_pattern = solution['dither_pattern']
                
                # Calculate the base layer where the sequence ends for this pixel
                base_end_layer = len(base_sequence) - 1
                current_pixel_top = pixel_top_layers.get(pixel_pos, -1)
                
                # Find an intermediate layer for dithering (between base sequence and top)
                best_dither_layer = None
                
                # Strategy: Place dithering in the next available layer AFTER the base sequence
                # but ensure it's not the topmost layer if constraint is enabled
                candidate_layer = base_end_layer + 1
                
                if candidate_layer < max_layers:
                    can_place_here = True
                    
                    # Top layer constraint: prevent dithering if it would be the topmost layer FOR THIS PIXEL
                    if not allow_top_layer_dithering:
                        # We need to ensure there's room for at least one more layer on top
                        if candidate_layer + 1 >= max_layers:
                            can_place_here = False
                    
                    # Spacing constraint: check for consecutive dithering AT THIS PIXEL POSITION
                    if can_place_here and min_layers_between_dithering > 0:
                        pixel_dithered = pixel_dithered_layers.get(pixel_pos, set())
                        for existing_dither_layer in pixel_dithered:
                            if abs(candidate_layer - existing_dither_layer) <= min_layers_between_dithering:
                                can_place_here = False
                                break
                    
                    if can_place_here:
                        best_dither_layer = candidate_layer
                        
                        # If we're not allowing top layer dithering, add a protective layer on top
                        if not allow_top_layer_dithering and len(base_sequence) > 0:
                            protective_layer = candidate_layer + 1
                            if protective_layer < max_layers:
                                # Use the last filament from base sequence as protective layer
                                protective_filament = base_sequence[-1]
                                if protective_filament not in layers[protective_layer]:
                                    layers[protective_layer][protective_filament] = []
                                layers[protective_layer][protective_filament].append((x, y))
                                
                                # Update the pixel's top layer
                                pixel_top_layers[pixel_pos] = protective_layer
                
                # Apply dithering if we found a valid layer
                if best_dither_layer is not None:
                    # Track dithering for this pixel position
                    if pixel_pos not in pixel_dithered_layers:
                        pixel_dithered_layers[pixel_pos] = set()
                    pixel_dithered_layers[pixel_pos].add(best_dither_layer)
                    
                    # Generate dither pattern for this specific region
                    local_pattern = generate_dither_pattern(
                        pattern_size, pattern_size, dither_ratio, dither_pattern
                    )
                    
                    # Check if this pixel should get the dither filament
                    pattern_x = x % pattern_size
                    pattern_y = y % pattern_size
                    
                    if local_pattern[pattern_y, pattern_x]:
                        if dither_filament not in layers[best_dither_layer]:
                            layers[best_dither_layer][dither_filament] = []
                        layers[best_dither_layer][dither_filament].append((x, y))
                        
                        # Store dither info for visualization
                        pixel_key = f"{x},{y}"
                        dither_info[pixel_key] = {
                            'layer': best_dither_layer,
                            'filament': dither_filament,
                            'ratio': dither_ratio,
                            'pattern': dither_pattern,
                            'target_color': target_color
                        }
    
    return layers, dither_info


def simulate_realistic_print_with_dithering(layers: List[Dict[str, List[Tuple[int, int]]]], 
                                          dither_info: Dict,
                                          image_shape: Tuple[int, int],
                                          available_filaments: Dict[str, Dict[str, Any]],
                                          base_filament: str = None,
                                          layer_height: float = LAYER_HEIGHT,
                                          final_only: bool = False) -> List[np.ndarray]:
    """
    Ultra-optimized realistic print simulation using vectorized operations.
    Significant performance improvement for high-resolution images.
    
    Args:
        layers: Layer assignments for each filament
        dither_info: Dithering information 
        image_shape: (height, width) of the image
        available_filaments: Dict of filament properties
        base_filament: Name of base filament (substrate)
        layer_height: Height of each layer
        final_only: If True, returns only the final result for speed
    """
    height, width = image_shape[:2]
    
    # Pre-calculate alpha values
    filament_alphas = {
        name: alpha_from_thickness(layer_height, filament['td'])
        for name, filament in available_filaments.items()
    }
    
    # Determine base color
    if base_filament is None or base_filament not in available_filaments:
        base_filament = max(available_filaments.keys(), 
                          key=lambda name: sum(available_filaments[name]['color']))
    
    base_color = np.array(available_filaments[base_filament]['color'], dtype=np.float32)
    current_result = np.full((height, width, 3), base_color, dtype=np.float32)
    cumulative_results = [] if not final_only else None
    
    for layer_idx, layer_assignment in enumerate(layers):
        if not layer_assignment:  # Skip empty layers
            if not final_only:
                cumulative_results.append(np.round(current_result).astype(np.uint8))
            continue
        
        # Create layer mask for all filaments at once
        layer_mask = np.zeros((height, width), dtype=bool)
        layer_colors = np.zeros((height, width, 3), dtype=np.float32)
        layer_alphas = np.zeros((height, width), dtype=np.float32)
        
        # Process all filaments in this layer
        for filament_name, positions in layer_assignment.items():
            if not positions or filament_name not in available_filaments:
                continue
            
            filament_color = np.array(available_filaments[filament_name]['color'], dtype=np.float32)
            alpha = filament_alphas[filament_name]
            
            # Convert positions to arrays
            if positions:
                pos_array = np.array(positions)
                xs, ys = pos_array[:, 0], pos_array[:, 1]
                
                # Set mask and colors for these positions
                layer_mask[ys, xs] = True
                layer_colors[ys, xs] = filament_color
                layer_alphas[ys, xs] = alpha
        
        # Apply blending only where there are pixels to blend
        if np.any(layer_mask):
            # Vectorized blending for all affected pixels at once
            affected_pixels = current_result[layer_mask]
            filament_pixels = layer_colors[layer_mask]
            alphas = layer_alphas[layer_mask, np.newaxis]  # Broadcast for RGB
            
            blended = affected_pixels * (1.0 - alphas) + filament_pixels * alphas
            current_result[layer_mask] = blended
        
        if not final_only:
            cumulative_results.append(np.round(current_result).astype(np.uint8))
    
    if final_only:
        return [np.round(current_result).astype(np.uint8)]
    else:
        return cumulative_results
