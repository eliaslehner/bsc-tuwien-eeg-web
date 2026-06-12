import argparse
import glob
import os
import sys

import numpy as np
import open3d as o3d

from backend.config import Config

# Suppress verbose output from open3d
o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)


def load_ply(filepath):
    """Load a .ply file as a mesh if it has triangles, otherwise as a point cloud."""
    mesh = o3d.io.read_triangle_mesh(filepath)
    if len(np.asarray(mesh.triangles)) > 0:
        mesh.compute_vertex_normals()
        n_verts = len(np.asarray(mesh.vertices))
        n_tris = len(np.asarray(mesh.triangles))
        print(f"  Loaded mesh: {os.path.basename(filepath)} ({n_verts:,} verts, {n_tris:,} tris)")
        return mesh, "mesh"
    else:
        pcd = o3d.io.read_point_cloud(filepath)
        n_pts = len(np.asarray(pcd.points))
        print(f"  Loaded point cloud: {os.path.basename(filepath)} ({n_pts:,} pts)")
        return pcd, "pcd"


def visualize(geometries, window_name="Brain Viewer", point_size=2.0):
    """Open an interactive Open3D viewer window."""
    print(f"\nOpening viewer: {window_name}")
    vis = o3d.visualization.Visualizer()
    vis.create_window(window_name=window_name, width=1400, height=900)

    for g in geometries:
        vis.add_geometry(g)

    opt = vis.get_render_option()
    opt.background_color = np.array([0, 0, 0])
    opt.point_size = point_size
    opt.mesh_show_back_face = True

    vis.run()
    vis.destroy_window()


def collect_ply_files(directory):
    """Return sorted list of .ply files in a directory."""
    if not os.path.isdir(directory):
        return []
    return sorted(glob.glob(os.path.join(directory, '*.ply')))


# Debug comparison views, in display order (left -> right). The registered view
# is only present when registration ran (antspyx + use_registration/show_viewer).
COMPARE_VIEWS = [
    ("pregap_mesh_ply_path", "1. PRE-GAP    (raw atlas, holes = dark grey)"),
    ("mapped_mesh_ply_path", "2. CURRENT    (affine-only resample — what the frontend shows)"),
    ("registered_mesh_ply_path", "3. REGISTERED (ANTs-warped atlas — proper alignment)"),
    ("template_mesh_ply_path", "4. REFERENCE  (Destrieux on MNI152 template = ground truth)"),
]


def compare_views(config, gap_factor=1.35):
    """
    Open one window showing the three debug meshes side by side, in the same
    orientation, so pre-gap vs current isolates the gap-fill effect and
    pre-gap vs reference isolates the registration (alignment) effect.
    """
    meshes = []
    for attr, label in COMPARE_VIEWS:
        path = getattr(config, attr)
        if not os.path.isfile(path):
            print(f"  [skip] missing {label} -> {path}")
            continue
        mesh = o3d.io.read_triangle_mesh(path)
        if len(np.asarray(mesh.triangles)) == 0:
            print(f"  [skip] no triangles in {path}")
            continue
        mesh.compute_vertex_normals()
        meshes.append((mesh, label))

    if not meshes:
        print("No comparison meshes found. Run the pipeline first "
              "(python -m backend.main).")
        return

    # Lay the meshes out left -> right along world X, centred on the origin.
    spacing = gap_factor * max(
        (m.get_axis_aligned_bounding_box().get_extent()[0] for m, _ in meshes),
        default=200.0,
    )
    n = len(meshes)
    print("\nComparison layout (left -> right):")
    for i, (mesh, label) in enumerate(meshes):
        c = mesh.get_center()
        x = (i - (n - 1) / 2.0) * spacing
        mesh.translate((x - c[0], -c[1], -c[2]))
        print(f"  {label}")

    print("\n  Each brain is in the same orientation (+X posterior, +Y superior,"
          "\n  +Z anatomical right). Orbit to inspect g_front_sup along the top.")
    visualize([m for m, _ in meshes],
              window_name="Destrieux mapping — pre-gap | current | reference")


def main():
    config = Config()

    parser = argparse.ArgumentParser(description="Visualize brain .ply exports")
    parser.add_argument('files', nargs='*', help="Specific .ply file(s) to view")
    parser.add_argument('--dir', choices=['pointcloud', 'brainmapping', 'all'],
                        default='all', help="Which export directory to load from")
    parser.add_argument('--compare', action='store_true',
                        help="Show pre-gap | current | reference views side by side")
    parser.add_argument('--point-size', type=float, default=2.0,
                        help="Point size for point cloud rendering")
    args = parser.parse_args()

    if args.compare:
        compare_views(config)
        return

    ply_paths = []

    if args.files:
        for f in args.files:
            if os.path.isfile(f) and f.endswith('.ply'):
                ply_paths.append(f)
            else:
                print(f"Warning: skipping '{f}' (not a .ply file)")
    else:
        if args.dir in ('pointcloud', 'all'):
            ply_paths += collect_ply_files(config.pointcloud_export_dir)
        if args.dir in ('brainmapping', 'all'):
            ply_paths += collect_ply_files(config.brainmapping_export_dir)

    if not ply_paths:
        print("No .ply files found. Run the pipeline first (python -m backend.main).")
        sys.exit(0)

    print(f"Found {len(ply_paths)} .ply file(s):")
    for p in ply_paths:
        print(f"  - {p}")

    if len(ply_paths) == 1:
        geom, kind = load_ply(ply_paths[0])
        visualize([geom], window_name=os.path.basename(ply_paths[0]),
                  point_size=args.point_size)
    else:
        print(f"\nSelect a file to view (1-{len(ply_paths)}), or 'a' to view all at once:")
        for i, p in enumerate(ply_paths):
            print(f"  [{i + 1}] {os.path.basename(p)}")

        choice = input("\n> ").strip().lower()

        if choice == 'a':
            print("\nViewing all files sequentially (close each window to proceed to the next)...")
            for p in ply_paths:
                geom, kind = load_ply(p)
                visualize([geom], window_name=os.path.basename(p),
                          point_size=args.point_size)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(ply_paths):
                    geom, kind = load_ply(ply_paths[idx])
                    visualize([geom], window_name=os.path.basename(ply_paths[idx]),
                              point_size=args.point_size)
                else:
                    print("Invalid selection.")
            except ValueError:
                print("Invalid input.")


if __name__ == "__main__":
    main()
