"""
AMS Layer Generator Package

A flexible sequential color building algorithm for multi-color 3D printing with AMS systems.
The algorithm dynamically adapts to any set of available filaments and generates layers 
where each layer can contain multiple filament colors, building up complex colors through 
realistic alpha blending.

Key features:
- Dynamic filament support: Works with any set of filaments (CMYK, RGB, custom colors, etc.)
- Intelligent color matching: Uses color distance optimization to find the best layer sequences
- Realistic alpha blending: Simulates actual print appearance with proper transparency
- Flexible substrate: Any filament can serve as the base layer (e.g., white, black, clear)
- Smart dithering: Uses dithering only when sequential layering isn't sufficient
"""

from .core import (
    # Core color functions
    clamp01,
    alpha_from_thickness,
    composite_colors,
    color_distance,
    simulate_color_blend,
    
    # Color sequence calculation
    calculate_color_sequence,
    calculate_color_sequence_with_dithering,
    calculate_color_sequence_with_dithering_cached,
    clear_color_sequence_cache,
    
    # Layer generation
    generate_sequential_layers,
    generate_enhanced_layers,
    
    # Dithering functions
    generate_dither_pattern,
    calculate_dither_blend,
    should_use_dithering,
    find_best_dither,
    
    # Print simulation
    simulate_realistic_print_with_dithering,
)

from .stl_generator import (
    generate_stl_files,
    estimate_print_stats,
    generate_dither_pattern_physical,
    pixel_to_world_coordinates,
)

__version__ = "1.0.0"
__author__ = "AMS Layer Generator"
__all__ = [
    # Core functions
    "clamp01",
    "alpha_from_thickness", 
    "composite_colors",
    "color_distance",
    "simulate_color_blend",
    
    # Color sequence calculation
    "calculate_color_sequence",
    "calculate_color_sequence_with_dithering",
    "calculate_color_sequence_with_dithering_cached",
    "clear_color_sequence_cache",
    
    # Layer generation
    "generate_sequential_layers",
    "generate_enhanced_layers",
    
    # Dithering functions
    "generate_dither_pattern",
    "calculate_dither_blend",
    "should_use_dithering", 
    "find_best_dither",
    
    # Print simulation
    "simulate_realistic_print_with_dithering",
    
    # STL generation
    "generate_stl_files",
    "estimate_print_stats",
    "generate_dither_pattern_physical",
    "pixel_to_world_coordinates",
]
