import multiprocessing as mp
import trimesh
from .mesh_utils import generate_layer_mesh, merge_layers_downward
from .utils import timed


def process_generate_layer_mesh(task):
    """Worker function for parallel mesh generation."""
    idx, idy, sublayer, layer_height = task
    try:
        m = generate_layer_mesh(sublayer, layer_height)
        return (idx, idy, m)
    except Exception as e:
        print(f"Error in generate_layer_mesh for layer {idx}, shade {idy}: {e}")
        return (idx, idy, None)


@timed
def polygons_to_meshes_parallel(
    segmented_image,
    polys_list,
    layer_height=0.2,
    base_layers=4,
    target_max_cm=10,
    progress_cb=None
):
    """
    Converts layered polygons to a list of 3D meshes in parallel.
    """
    tasks = []
    for idx, polys in enumerate(polys_list):
        for idy, sublayer in enumerate(polys):
            tasks.append((idx, idy, sublayer, layer_height))
    total = len(tasks)
    if total == 0:
        if progress_cb: progress_cb(1.0)
        return []

    results = []
    with mp.Pool(processes=mp.cpu_count()) as pool:
        for n, triple in enumerate(pool.imap(process_generate_layer_mesh, tasks), start=1):
            results.append(triple)
            if progress_cb:
                progress_cb(n / total)

    meshes_dict = {}
    for idx, idy, mesh in results:
        if mesh:
            meshes_dict.setdefault(idx, {})[idy] = mesh

    meshes_list = []
    for idx in sorted(meshes_dict):
        shade_dict = meshes_dict[idx]
        sublayers = [shade_dict[i] for i in sorted(shade_dict)]
        if sublayers:
            meshes_list.append(sublayers)

    #merge_layers_downward(meshes_list)

    w_px, h_px = segmented_image.size
    meshes = []
    scale_xy = (target_max_cm * 10) / max(w_px, h_px)
    current_z0 = 0

    for i, layer in enumerate(meshes_list):
        z_scale = 1.0
        if i == 0:
            z_scale = base_layers

        for m in layer:
            m.apply_translation([0, 0, current_z0])
            if not m.is_empty:
                current_z0 += layer_height * z_scale

        combined = trimesh.util.concatenate(layer)
        combined.apply_scale([scale_xy, scale_xy, z_scale])
        meshes.append(combined)

    if progress_cb: progress_cb(1.0)
    return meshes

