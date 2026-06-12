"""
backend/model/template.py — Reference "atlas at home" view.

Renders the Destrieux atlas on the MNI152 template brain it was defined on,
WITHOUT resampling to the subject. This is the ground-truth reference: if a
region (e.g. g_front_sup) sits correctly here but is shifted on the subject
mesh, the error was introduced by the subject<->atlas alignment (registration),
not by the atlas or the gap-filling.
"""

import os

import numpy as np
import open3d as o3d
from skimage.measure import marching_cubes

from .pointcloud import color_vertices_by_region


# Marching-cubes level for the normalised MNI152 T1 template (0..1 intensities).
TEMPLATE_MC_LEVEL = 0.18


def _orient_ras_to_display(verts, faces):
    """
    Re-orient an RAS-indexed mesh (i->R, j->A, k->S) into the same display
    convention the subject mesh uses: +X posterior, +Y superior, +Z right.

        posterior = -A = -j
        superior  = +S = +k
        right     = +R = +i

    The axis permutation flips handedness, so triangle winding is reversed to
    keep normals pointing outward.
    """
    disp = np.column_stack([-verts[:, 1], verts[:, 2], verts[:, 0]])
    disp = disp - disp.mean(axis=0)
    faces_flipped = np.asarray(faces)[:, ::-1]
    return disp, faces_flipped


def generate_template_view(config, id_to_palette_idx, palette):
    """
    Build and export the Destrieux-on-MNI152 reference mesh.

    Uses the SAME palette / id_to_palette_idx as the subject views, so every
    region keeps the same colour across all three views and they can be
    compared directly.

    Returns
    -------
    out_path : str | None — path to the exported PLY (None if datasets missing)
    """
    try:
        from nilearn.datasets import (
            fetch_atlas_destrieux_2009,
            load_mni152_template,
            load_mni152_brain_mask,
        )
        from nilearn.image import resample_to_img
        import nibabel as nib
    except Exception as exc:  # pragma: no cover - environment guard
        print(f"  Template view skipped (nilearn unavailable: {exc})")
        return None

    print("  Building reference view (Destrieux on MNI152 template)...")

    template = load_mni152_template(resolution=1)
    brain_mask = load_mni152_brain_mask(resolution=1)

    atlas = fetch_atlas_destrieux_2009(lateralized=True, verbose=0)
    amaps = atlas["maps"]
    atlas_img = nib.load(amaps) if isinstance(amaps, str) else amaps

    # Atlas onto the template grid (nearest keeps integer labels intact).
    atlas_on_template = resample_to_img(
        atlas_img, template, interpolation="nearest"
    )
    atlas_data = np.asarray(atlas_on_template.dataobj, dtype=np.int32)

    # Skull-strip the template and normalise to [0, 1] over brain voxels.
    mask = np.asarray(brain_mask.dataobj) > 0

    # Gap-fill within the (correctly aligned) template brain, same as the
    # subject "current" view. On a registered brain this only spreads labels to
    # their correct nearest region, giving full, anatomically faithful coverage.
    from backend.regions.atlas import gap_fill_labels
    atlas_data, _ = gap_fill_labels(atlas_data, mask)

    vol = np.asarray(template.dataobj, dtype=np.float64) * mask
    bvals = vol[mask]
    vmin, vmax = float(bvals.min()), float(bvals.max())
    if vmax > vmin:
        vol = (vol - vmin) / (vmax - vmin)
        vol[~mask] = 0.0

    verts, faces, _, _ = marching_cubes(vol, level=TEMPLATE_MC_LEVEL, step_size=1)
    print(f"    Template isosurface: {len(verts):,} verts, {len(faces):,} faces")

    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(verts)
    mesh.triangles = o3d.utility.Vector3iVector(faces)
    if config.mesh_target_faces > 0 and len(faces) > config.mesh_target_faces:
        mesh = mesh.simplify_quadric_decimation(config.mesh_target_faces)
        verts = np.asarray(mesh.vertices)
        faces = np.asarray(mesh.triangles)

    # Label each vertex from the atlas in its native space (no subject resample).
    voxel_ijk = np.round(verts).astype(np.int64)
    for dim in range(3):
        voxel_ijk[:, dim] = np.clip(voxel_ijk[:, dim], 0, atlas_data.shape[dim] - 1)
    region_ids = atlas_data[voxel_ijk[:, 0], voxel_ijk[:, 1], voxel_ijk[:, 2]]
    colors = color_vertices_by_region(region_ids, id_to_palette_idx, palette)

    disp_verts, faces_flipped = _orient_ras_to_display(verts, faces)
    mesh.vertices = o3d.utility.Vector3dVector(disp_verts)
    mesh.triangles = o3d.utility.Vector3iVector(faces_flipped)
    mesh.vertex_colors = o3d.utility.Vector3dVector(colors)
    mesh.compute_vertex_normals()

    os.makedirs(config.brainmapping_export_dir, exist_ok=True)
    out_path = os.path.join(
        config.brainmapping_export_dir, config.template_mesh_ply_filename
    )
    o3d.io.write_triangle_mesh(out_path, mesh)
    n_lab = int(np.sum(region_ids > 0))
    print(f"    Exported reference view -> {out_path}")
    print(f"    {len(disp_verts):,} verts, {100 * n_lab / len(region_ids):.1f}% labelled")
    return out_path
