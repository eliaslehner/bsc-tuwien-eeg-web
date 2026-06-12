"""
backend/model/pointcloud.py — Brain mesh generation via Marching Cubes.

Generates a detailed isosurface from the masked T1w volume, assigns
Destrieux atlas region IDs per-vertex (forward carry), and exports
the coloured mesh as PLY.
"""

import os
import shutil

import numpy as np
import open3d as o3d
from skimage.measure import marching_cubes


def assign_vertex_region_ids(vertices_voxel, atlas_volume):
    """Look up atlas region ID for each vertex based on its voxel coordinate."""
    voxel_ijk = np.round(vertices_voxel).astype(np.int64)
    for dim in range(3):
        voxel_ijk[:, dim] = np.clip(voxel_ijk[:, dim], 0, atlas_volume.shape[dim] - 1)
    return atlas_volume[voxel_ijk[:, 0], voxel_ijk[:, 1], voxel_ijk[:, 2]].astype(np.int32)


def fill_unlabelled_from_neighbours(region_ids, faces):
    """
    Propagate region labels to unlabelled (0) vertices via mesh adjacency.

    Uses BFS-like expansion: in each pass, unlabelled vertices adopt the
    most common non-zero label among their direct mesh neighbours.
    Repeats until no further vertices can be filled.
    """
    from collections import defaultdict, Counter

    ids = region_ids.copy()
    unlabelled = set(np.where(ids == 0)[0])
    if not unlabelled:
        return ids

    # Build adjacency from triangle faces
    adj = defaultdict(set)
    for f in faces:
        adj[f[0]].update((f[1], f[2]))
        adj[f[1]].update((f[0], f[2]))
        adj[f[2]].update((f[0], f[1]))

    changed = True
    while changed and unlabelled:
        changed = False
        still_unlabelled = set()
        for v in unlabelled:
            labelled = [ids[n] for n in adj[v] if ids[n] != 0]
            if labelled:
                ids[v] = Counter(labelled).most_common(1)[0][0]
                changed = True
            else:
                still_unlabelled.add(v)
        unlabelled = still_unlabelled

    return ids


def color_vertices_by_region(region_ids, id_to_palette_idx, palette):
    """Assign RGB colour to each vertex based on its region ID."""
    palette_indices = np.array([id_to_palette_idx.get(int(r), 0) for r in region_ids])
    return palette[palette_indices]


def _assemble_and_export(verts_centered, faces_flipped, colors, out_path):
    """Build an Open3D mesh from shared geometry + per-view colours and write it."""
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(verts_centered)
    mesh.triangles = o3d.utility.Vector3iVector(faces_flipped)
    mesh.vertex_colors = o3d.utility.Vector3dVector(colors)
    mesh.compute_vertex_normals()
    o3d.io.write_triangle_mesh(out_path, mesh)
    return mesh


def generate_and_export(config, masked_volume, atlas_production, atlas_volume_raw,
                        id_to_palette_idx, palette, atlas_unregistered=None):
    """
    Full mesh generation pipeline using Marching Cubes.

    One isosurface is extracted and shared between the coloured exports so they
    are geometrically identical and differ ONLY in labelling:

      * production view  — region IDs from *atlas_production* (the registered,
        gap-filled atlas when registration ran, else the affine-only one),
        plus mesh-neighbour fill. Written to the canonical filename the frontend
        loads.
      * pre-gap view     — region IDs from the RAW (un-gap-filled) atlas, no fill.
        Unlabelled vertices stay dark grey, so holes + raw placement are visible.
      * unregistered view (optional) — region IDs from the old affine-only,
        gap-filled atlas. Same geometry; kept as a backup / "before" comparison.

    Returns
    -------
    (production_ids, unregistered_ids) : (list[int], list[int] | None)
        production_ids feed region_metadata.json; unregistered_ids feed the
        backup region_metadata when registration ran.
    """
    os.makedirs(config.brainmapping_export_dir, exist_ok=True)
    mapped_path = config.mapped_mesh_ply_path

    # ── Marching Cubes isosurface (shared by every view) ──
    print("  Running Marching Cubes...")
    verts, faces, _, _ = marching_cubes(
        masked_volume, level=config.mc_level, step_size=config.mc_step_size,
    )
    print(f"  Isosurface: {len(verts):,} vertices, {len(faces):,} faces")

    # ── Build mesh in voxel space ──
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(verts)
    mesh.triangles = o3d.utility.Vector3iVector(faces)

    # ── Optional decimation (in voxel space, before region assignment) ──
    if config.mesh_target_faces > 0 and len(faces) > config.mesh_target_faces:
        print(f"  Decimating: {len(faces):,} -> {config.mesh_target_faces:,} target faces...")
        mesh = mesh.simplify_quadric_decimation(config.mesh_target_faces)
        verts = np.asarray(mesh.vertices)
        faces = np.asarray(mesh.triangles)
        print(f"  After decimation: {len(verts):,} verts, {len(faces):,} faces")
    else:
        verts = np.asarray(mesh.vertices)

    decimated_faces = np.asarray(mesh.triangles)

    def labelled_colours(atlas, fill=True):
        ids = assign_vertex_region_ids(verts, atlas)
        if fill:
            n0 = int(np.sum(ids == 0))
            if n0 > 0:
                ids = fill_unlabelled_from_neighbours(ids, decimated_faces)
        return ids, color_vertices_by_region(ids, id_to_palette_idx, palette)

    # ── Production view (canonical — what the frontend loads) ──
    print("  Assigning region IDs per vertex (production view)...")
    prod_ids, prod_colors = labelled_colours(atlas_production, fill=True)

    # ── Pre-gap view: raw atlas labels, NO filling ──
    pregap_ids, pregap_colors = labelled_colours(atlas_volume_raw, fill=False)
    n_pregap_lab = int(np.sum(pregap_ids > 0))
    print(f"  Pre-gap view: {100 * n_pregap_lab / len(pregap_ids):.1f}% of "
          f"vertices labelled by the raw atlas ({len(pregap_ids) - n_pregap_lab:,} holes)")

    # ── Shared centre + flip Y (faces flipped once to keep normals outward) ──
    centroid = verts.mean(axis=0)
    verts_centered = verts - centroid
    verts_centered[:, 1] = -verts_centered[:, 1]
    faces_flipped = decimated_faces[:, ::-1]

    # ── Export production + pre-gap ──
    _assemble_and_export(verts_centered, faces_flipped, prod_colors, mapped_path)
    print(f"  Exported production view -> {mapped_path}")
    print(f"    {len(verts_centered):,} vertices, {len(faces_flipped):,} faces")

    pregap_path = config.pregap_mesh_ply_path
    _assemble_and_export(verts_centered, faces_flipped, pregap_colors, pregap_path)
    print(f"  Exported pre-gap view    -> {pregap_path}")

    # ── Export unregistered backup (optional, same geometry, old labels) ──
    unreg_ids = None
    if atlas_unregistered is not None:
        unreg_ids, unreg_colors = labelled_colours(atlas_unregistered, fill=True)
        unreg_path = config.unregistered_mesh_ply_path
        _assemble_and_export(verts_centered, faces_flipped, unreg_colors, unreg_path)
        print(f"  Exported unregistered    -> {unreg_path} (backup)")

    if config.copy_mapped_mesh_to_frontend:
        frontend_dir = config.frontend_data_dir
        os.makedirs(frontend_dir, exist_ok=True)
        dest = os.path.join(frontend_dir, config.mapped_mesh_ply_filename)
        shutil.copy2(mapped_path, dest)
        print(f"  Copied to frontend -> {dest}")

    print("  Mesh generation done.")
    return [int(r) for r in prod_ids], (None if unreg_ids is None else [int(r) for r in unreg_ids])
