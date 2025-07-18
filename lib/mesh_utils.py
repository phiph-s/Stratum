import trimesh
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from .utils import timed


def generate_layer_mesh(polygons, thickness):
    """Generates an extruded 3D mesh from a list of 2D polygons."""
    if not isinstance(polygons, list):
        polygons = [polygons]

    flat_polys = []
    for geom in polygons:
        if isinstance(geom, MultiPolygon):
            flat_polys.extend(geom.geoms)
        else:
            flat_polys.append(geom)

    meshes = []
    for poly in flat_polys:
        if not poly.is_valid or poly.is_empty:
            continue
        m = trimesh.creation.extrude_polygon(poly, thickness)
        meshes.append(m)
    return trimesh.util.concatenate(meshes) if meshes else trimesh.Trimesh()


@timed
def merge_layers_downward(meshes_list):
    """
    Performs an in-place cumulative union of meshes, from top to bottom.
    """
    last = None
    for i, meshes in enumerate(meshes_list[::-1]):
        if i == len(meshes_list) - 1:
            continue
        for j, mesh in enumerate(meshes[::-1]):
            if last is None:
                last = mesh
            else:
                last = trimesh.util.concatenate(last, mesh)
                meshes_list[-(i + 1)][-(j + 1)] = last


@timed
def merge_polys_downward(polys_list):
    """
    Performs an in-place cumulative union of polygons, from top to bottom.
    """
    accumulated = None
    for i in range(len(polys_list) - 1, -1, -1):
        layer = polys_list[i]
        for j in range(len(layer) - 1, -1, -1):
            group = layer[j]
            if isinstance(group, list):
                poly = unary_union(group) if group else None
            else:
                poly = group

            if poly is None or poly.is_empty:
                continue

            accumulated = poly if accumulated is None else accumulated.union(poly)
            polys_list[i][j] = accumulated

    return polys_list


def _generate_base_mesh(segmented_image, layer_height=0.2, base_layers=4, target_max_cm=10):
    """Generates the solid base mesh for the model."""
    base_height = layer_height * base_layers
    w_px, h_px = segmented_image.size
    scale_xy = (target_max_cm * 10) / max(w_px, h_px)

    from shapely.geometry import Polygon
    from .mesh_utils import generate_layer_mesh
    from .mask_utils import flip_polygons_vertically

    base_rect = Polygon([(0, 0), (w_px, 0), (w_px, h_px), (0, h_px)])
    base_poly = flip_polygons_vertically([base_rect], h_px)
    base_mesh = generate_layer_mesh(base_poly, base_height)
    if base_mesh and len(base_mesh.vertices) > 0:
        base_mesh.apply_scale([scale_xy, scale_xy, 1])
        return base_mesh, base_height
    return trimesh.Trimesh(), 0
