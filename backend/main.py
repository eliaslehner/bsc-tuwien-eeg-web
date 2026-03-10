"""
backend/main.py — Single entry point for the brain visualisation pipeline.

Run with:  python -m backend.main
"""

import open3d as o3d

from backend.config import Config
from backend.model.loader import load_nii_image, load_masked_volume
from backend.model.pointcloud import generate_and_export
from backend.regions.atlas import fetch_and_resample_atlas, gap_fill_labels
from backend.regions.palette import build_region_palette
from backend.electrode.mapping import run_electrode_pipeline

# Suppress verbose Open3D output
o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)


def run(config=None):
    if config is None:
        config = Config()

    print("=" * 60)
    print("  Brain Visualisation Pipeline")
    print("=" * 60)
    print(f"  Device : {config.device}")
    print(f"  T1w    : {config.brain_t1w_nii_path}")
    print(f"  Mask   : {config.brain_mask_nii_path}")
    print(f"  Viewer : {'enabled' if config.show_viewer else 'disabled'}")
    print("=" * 60)

    # ── Step 1: Load NIfTI volumes ──
    print("\n[1/5] Loading NIfTI volumes")
    brain_nii = load_nii_image(config.brain_nii_path)
    _, masked_volume, brain_mask = load_masked_volume(
        config.brain_t1w_nii_path, config.brain_mask_nii_path,
    )

    # ── Step 2: Destrieux atlas + gap-fill ──
    print("\n[2/5] Loading Destrieux atlas & gap-filling")
    atlas_volume, names_map = fetch_and_resample_atlas(brain_nii)
    atlas_volume, _ = gap_fill_labels(atlas_volume, brain_mask)

    # ── Step 3: Build region palette ──
    print("\n[3/5] Building region palette")
    sorted_ids, full_names, palette, id_to_palette_idx = build_region_palette(names_map)
    print(f"    {len(full_names)} regions in palette")

    # ── Step 4: Generate mesh (Marching Cubes) with forward-carried region IDs ──
    print("\n[4/5] Mesh generation (Marching Cubes) + region mapping")
    vertex_region_ids = generate_and_export(
        config, masked_volume, atlas_volume, id_to_palette_idx, palette,
    )

    # ── Step 5: Electrode mapping & JSON export ──
    print("\n[5/5] Electrode mapping & JSON export")
    run_electrode_pipeline(
        config, brain_nii, atlas_volume, names_map, None,
        sorted_ids, full_names, palette, id_to_palette_idx,
        vertex_region_ids=vertex_region_ids,
    )

    # ── Optional: Launch viewer ──
    if config.show_viewer:
        print("\nLaunching viewer...")
        from backend.viewer.viewer import main as viewer_main
        viewer_main()

    print("\n" + "=" * 60)
    print("  Pipeline completed successfully.")
    print("=" * 60)


if __name__ == "__main__":
    run()
