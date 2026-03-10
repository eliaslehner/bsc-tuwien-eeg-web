import glob
import os
import shutil

import numpy as np
import open3d as o3d

# Base colour for unmapped vertices
BASE_COLOR = np.array([0.75, 0.75, 0.75])


def map_vertices_to_regions(vertices, centroid, atlas_volume, id_to_palette_idx, palette):
    """
    For each vertex in a .ply file, reverse PointCloud.py transforms,
    look up the atlas region, and assign a colour.
    """
    pts = vertices.copy()

    # UN-FLIP Y axis
    pts[:, 1] = -pts[:, 1]

    # UN-CENTER
    pts += centroid

    # Round to nearest voxel index
    voxel_ijk = np.round(pts).astype(np.int64)

    # Clamp to volume bounds
    for dim in range(3):
        voxel_ijk[:, dim] = np.clip(voxel_ijk[:, dim], 0, atlas_volume.shape[dim] - 1)

    # Sample atlas labels
    atlas_labels = atlas_volume[voxel_ijk[:, 0], voxel_ijk[:, 1], voxel_ijk[:, 2]]

    # Assign colours
    n_pts = len(vertices)
    colors = np.full((n_pts, 3), BASE_COLOR, dtype=np.float64)
    for i, label in enumerate(atlas_labels):
        label = int(label)
        pidx = id_to_palette_idx.get(label, 0)
        colors[i] = palette[pidx]

    return colors


def process_ply_file(filepath, centroid, atlas_volume, id_to_palette_idx, palette, output_dir):
    """
    Load a .ply file, map vertices to atlas regions, colour them, and export.
    Handles both raw point clouds and triangle meshes.
    """
    basename = os.path.basename(filepath)
    out_filename = os.path.splitext(basename)[0] + '_destrieux_mapped.ply'
    out_path = os.path.join(output_dir, out_filename)

    if os.path.exists(out_path):
        print(f"    Already exists: {out_filename}")
        return out_path

    # Try loading as mesh first to check for triangles
    mesh = o3d.io.read_triangle_mesh(filepath)
    has_triangles = len(np.asarray(mesh.triangles)) > 0

    if has_triangles:
        vertices = np.asarray(mesh.vertices)
        colors = map_vertices_to_regions(
            vertices, centroid, atlas_volume, id_to_palette_idx, palette
        )
        mesh.vertex_colors = o3d.utility.Vector3dVector(colors)
        mesh.compute_vertex_normals()
        o3d.io.write_triangle_mesh(out_path, mesh)
        print(f"    Exported mesh to {out_filename} ({len(vertices):,} verts)")
    else:
        pcd = o3d.io.read_point_cloud(filepath)
        vertices = np.asarray(pcd.points)
        colors = map_vertices_to_regions(
            vertices, centroid, atlas_volume, id_to_palette_idx, palette
        )
        pcd.colors = o3d.utility.Vector3dVector(colors)
        o3d.io.write_point_cloud(out_path, pcd)
        print(f"    Exported point cloud to {out_filename} ({len(vertices):,} pts)")

    return out_path


def map_all_ply_files(config, centroid, atlas_volume, id_to_palette_idx, palette):
    """
    Process all .ply files from the pointcloud export directory,
    mapping their vertices to atlas regions and exporting coloured versions.
    """
    input_dir = config.pointcloud_export_dir
    output_dir = config.brainmapping_export_dir

    if not os.path.isdir(input_dir):
        print("No point cloud files to process.")
        return []

    ply_files = sorted(glob.glob(os.path.join(input_dir, '*.ply')))
    if not ply_files:
        print("No .ply files found in point cloud export directory.")
        return []

    print(f"Found {len(ply_files)} .ply file(s) in {input_dir}/")
    for f in ply_files:
        print(f"  • {os.path.basename(f)}")

    os.makedirs(output_dir, exist_ok=True)

    output_paths = []
    for ply_path in ply_files:
        out = process_ply_file(
            ply_path, centroid, atlas_volume,
            id_to_palette_idx, palette, output_dir
        )
        output_paths.append(out)

    if config.copy_mapped_mesh_to_frontend:
        frontend_dir = config.frontend_data_dir
        os.makedirs(frontend_dir, exist_ok=True)
        mapped_mesh_path = config.mapped_mesh_ply_path
        if os.path.isfile(mapped_mesh_path):
            dest = os.path.join(frontend_dir, config.mapped_mesh_ply_filename)
            shutil.copy2(mapped_mesh_path, dest)
            print(f"    Copied mapped mesh to {dest}")

    print(f"\nBrain region mapping completed — {len(output_paths)} file(s) processed.")
    return output_paths
