# mesh_generator.py - Aggregator module for mesh generation components
# noqa imports for re-export
from .utils import timed, ensure_dir, OUTPUT_DIR, SIMPLIFY_TOLERANCE, MIN_AREA  # noqa: F401
from .mask_utils import extract_color_masks, mask_to_polygons, flip_polygons_vertically  # noqa: F401
from .mesh_utils import generate_layer_mesh, merge_layers_downward, merge_polys_downward, _generate_base_mesh  # noqa: F401
from .parallel_polygons import create_layered_polygons_parallel, process_mask  # noqa: F401
from .parallel_meshes import polygons_to_meshes_parallel, process_generate_layer_mesh  # noqa: F401
from .render_utils import render_polygons_to_pil_image, analyze_position_rgb  # noqa: F401
from .mask_creation import segment_to_shades, generate_shades_td  # noqa: F401

__all__ = [
    'timed', 'ensure_dir', 'OUTPUT_DIR', 'SIMPLIFY_TOLERANCE', 'MIN_AREA',
    'extract_color_masks', 'mask_to_polygons', 'flip_polygons_vertically',
    'generate_layer_mesh', 'merge_layers_downward', 'merge_polys_downward', '_generate_base_mesh',
    'create_layered_polygons_parallel', 'process_mask',
    'polygons_to_meshes_parallel', 'process_generate_layer_mesh',
    'render_polygons_to_pil_image', 'analyze_position_rgb',
    'segment_to_shades', 'generate_shades_td'
]
