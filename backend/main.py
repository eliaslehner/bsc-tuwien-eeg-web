"""
backend/main.py — Single entry point for the brain visualisation pipeline.

Run with:  python -m backend.main
"""

import open3d as o3d
import numpy as np

from backend.config import Config
from backend.model.loader import load_nii_image, load_masked_volume
from backend.model.pointcloud import generate_and_export
from backend.model.template import generate_template_view
from backend.regions.atlas import (
    fetch_and_resample_atlas, gap_fill_labels, registration_coverage,
    fetch_destrieux_native,
)
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
    print("\n[1/6] Loading NIfTI volumes")
    brain_nii = load_nii_image(config.brain_nii_path)
    t1w_nii, masked_volume, brain_mask = load_masked_volume(
        config.brain_t1w_nii_path, config.brain_mask_nii_path,
    )
    if brain_nii.shape != masked_volume.shape:
        raise ValueError(
            f"Brain image shape {brain_nii.shape} does not match "
            f"masked T1w shape {masked_volume.shape}"
        )
    if not np.allclose(brain_nii.affine, t1w_nii.affine):
        raise ValueError("Brain image affine does not match full T1w affine")

    # ── Step 2: Destrieux atlas + gap-fill ──
    print("\n[2/6] Loading Destrieux atlas & gap-filling")
    atlas_volume_raw, names_map = fetch_and_resample_atlas(brain_nii)
    registration_coverage(atlas_volume_raw, brain_mask)
    atlas_volume, _ = gap_fill_labels(atlas_volume_raw, brain_mask)

    # Proper subject<->MNI registration (warp atlas to subject). When it
    # succeeds, the registered atlas becomes the PRODUCTION atlas for the SURFACE
    # (drives the canonical mesh + vertex labels); the old affine-only surface is
    # kept as an *_unregistered backup. If antspyx is missing this degrades to the
    # old affine-only surface. (Electrode placement is independent of this — it is
    # always mapped in native atlas space in step 5.)
    atlas_volume_registered = None
    if config.use_registration:
        from backend.regions.registration import register_atlas_to_subject
        reg_raw = register_atlas_to_subject(config, brain_nii)
        if reg_raw is not None:
            registration_coverage(reg_raw, brain_mask)
            atlas_volume_registered, _ = gap_fill_labels(reg_raw, brain_mask)

    registered = atlas_volume_registered is not None
    atlas_production = atlas_volume_registered if registered else atlas_volume
    print(f"    Production atlas: {'REGISTERED (ANTs)' if registered else 'affine-only resample'}")

    # ── Step 3: Build region palette ──
    print("\n[3/6] Building region palette")
    sorted_ids, full_names, palette, id_to_palette_idx = build_region_palette(names_map)
    print(f"    {len(full_names)} regions in palette")

    # ── Step 4: Generate mesh (Marching Cubes) with forward-carried region IDs ──
    print("\n[4/6] Mesh generation (Marching Cubes) + region mapping")
    vertex_region_ids, unregistered_ids = generate_and_export(
        config, masked_volume, atlas_production, atlas_volume_raw,
        id_to_palette_idx, palette,
        atlas_unregistered=(atlas_volume if registered else None),
    )
    # The MNI-template reference view is more expensive (separate isosurface),
    # so only build it when it will be viewed, or when forced.
    if config.export_debug_views or config.show_viewer:
        generate_template_view(config, id_to_palette_idx, palette)

    # ── Step 5: Electrode mapping & JSON export ──
    print("\n[5/6] Electrode mapping & JSON export")
    # Electrode->region is an atlas-space question (the montage is in MNI/head
    # space): map against the NATIVE Destrieux atlas, independent of the subject
    # and of registration. The subject brain is only the visualisation canvas.
    mni_atlas, mni_affine, mni_names = fetch_destrieux_native()
    electrode_output = run_electrode_pipeline(
        config, brain_nii, atlas_production, names_map, None,
        sorted_ids, full_names, palette, id_to_palette_idx,
        vertex_region_ids=vertex_region_ids,
        electrode_atlas=mni_atlas, electrode_affine=mni_affine,
        electrode_names=mni_names,
    )
    if registered:
        # Backup region_metadata: the OLD (affine-only) surface labels. Electrodes
        # use the same corrected mapping (electrode placement does not depend on
        # the subject registration), so the backup is a clean surface-only "before".
        print("  Writing unregistered region_metadata backup (surface labels)...")
        run_electrode_pipeline(
            config, brain_nii, atlas_production, names_map, None,
            sorted_ids, full_names, palette, id_to_palette_idx,
            vertex_region_ids=unregistered_ids,
            output_path=config.unregistered_json_path,
            electrode_atlas=mni_atlas, electrode_affine=mni_affine,
            electrode_names=mni_names,
        )

    # ── Step 6: EEG processing & export ──
    print("\n[6/6] EEG processing & export")
    from backend.eeg import run_eeg_pipeline
    run_eeg_pipeline(config, electrode_mappings=electrode_output.get('electrodes', []))

    # ── Optional: Launch viewer ──
    if config.show_viewer:
        print("\nLaunching comparison viewer (pre-gap | current | reference)...")
        from backend.viewer.viewer import compare_views
        compare_views(config)

    print("\n" + "=" * 60)
    print("  Pipeline completed successfully.")
    print("=" * 60)


if __name__ == "__main__":
    run()
