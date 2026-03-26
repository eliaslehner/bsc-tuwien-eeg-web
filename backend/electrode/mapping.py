import json
import os

import mne
import numpy as np
import open3d as o3d


def get_electrode_mni_coords(channel_names):
    """
    Get MNI coordinates for each channel using MNE's standard_1020 montage.

    Returns
    -------
    coords : dict[str, np.ndarray] — channel name → (x, y, z) in metres
    """
    montage = mne.channels.make_standard_montage('standard_1020')
    all_positions = montage.get_positions()['ch_pos']

    coords = {}
    for ch in channel_names:
        if ch in all_positions:
            coords[ch] = all_positions[ch]
        else:
            print(f"  WARNING: channel '{ch}' not found in standard_1020 montage")

    print(f"  Found MNI coordinates for {len(coords)}/{len(channel_names)} channels")
    return coords


def mni_to_voxel(mni_coords_metres, nii_affine):
    """
    Transform MNI coordinates (in metres) to voxel indices
    using the inverse of the NIfTI affine.
    """
    inv_affine = np.linalg.inv(nii_affine)
    mni_mm = mni_coords_metres * 1000.0
    mni_hom = np.append(mni_mm, 1.0)
    voxel = inv_affine @ mni_hom
    return voxel[:3]


def map_electrodes_to_regions(channel_coords, brain_nii, atlas_volume, names_map):
    """
    For each electrode, transform its MNI coordinate to voxel space,
    then project inward toward the volume centre until a labelled
    region is found (ray-casting from scalp inward).

    Returns
    -------
    electrode_mappings : list[dict] — one entry per electrode
    """
    affine = brain_nii.header.get_best_affine()
    vol_centre = np.array(atlas_volume.shape, dtype=np.float64) / 2.0

    mappings = []
    for ch_name, mni_pos in channel_coords.items():
        voxel = mni_to_voxel(mni_pos, affine)
        voxel_start = np.round(voxel).astype(np.float64)

        # Ray-cast from scalp inward
        direction = vol_centre - voxel_start
        length = np.linalg.norm(direction)
        direction = direction / length

        region_id = 0
        hit_voxel = voxel_start.copy()
        for step in np.arange(0, length, 0.5):
            pos = voxel_start + direction * step
            idx = np.round(pos).astype(np.int64)

            for dim in range(3):
                idx[dim] = np.clip(idx[dim], 0, atlas_volume.shape[dim] - 1)

            label = int(atlas_volume[idx[0], idx[1], idx[2]])
            if label > 0:
                region_id = label
                hit_voxel = idx
                break

        region_name = names_map.get(region_id, "Unlabelled")

        mappings.append({
            "name": ch_name,
            "mni": [round(float(x * 1000), 2) for x in mni_pos],
            "voxel": [int(v) for v in hit_voxel],
            "region_id": region_id,
            "region_name": region_name,
        })

        print(f"  {ch_name:>4s}  ->  voxel {hit_voxel.astype(int)}  ->  [{region_id}] {region_name}")

    return mappings


def map_mesh_vertices_to_regions(mesh_ply_path, centroid, atlas_volume):
    """
    Load the PLY mesh, reverse PointCloud transforms (un-flip Y, un-center)
    to recover voxel coordinates, and look up the region ID at each vertex.

    Returns
    -------
    vertex_region_ids : list[int] — one region ID per vertex
    """
    mesh = o3d.io.read_triangle_mesh(mesh_ply_path)
    vertices = np.asarray(mesh.vertices).copy()

    # Undo transforms
    vertices[:, 1] = -vertices[:, 1]
    vertices += centroid

    voxel_ijk = np.round(vertices).astype(np.int64)

    for dim in range(3):
        voxel_ijk[:, dim] = np.clip(voxel_ijk[:, dim], 0, atlas_volume.shape[dim] - 1)

    atlas_labels = atlas_volume[voxel_ijk[:, 0], voxel_ijk[:, 1], voxel_ijk[:, 2]]
    vertex_region_ids = [int(lbl) for lbl in atlas_labels]

    print(f"  Mapped {len(vertex_region_ids):,} vertices to region IDs")
    return vertex_region_ids


def build_output(electrode_mappings, names_map, palette, sorted_ids, full_names,
                 id_to_palette_idx, vertex_region_ids=None):
    """
    Build the final JSON structure that the browser viewer consumes.
    """
    regions = []
    for rid in sorted_ids:
        if rid == 0:
            continue
        pidx = id_to_palette_idx[rid]
        color = [round(float(c), 4) for c in palette[pidx]]
        regions.append({
            "id": rid,
            "name": full_names[rid],
            "color": color,
        })

    region_electrodes = {}
    for em in electrode_mappings:
        rid_str = str(em["region_id"])
        if rid_str not in region_electrodes:
            region_electrodes[rid_str] = []
        region_electrodes[rid_str].append(em["name"])

    output = {
        "atlas": "Destrieux 2009",
        "regions": regions,
        "electrodes": electrode_mappings,
        "region_electrodes": region_electrodes,
    }

    if vertex_region_ids is not None:
        output["vertex_region_ids"] = vertex_region_ids

    return output


def run_electrode_pipeline(config, brain_nii, atlas_volume, names_map, centroid,
                           sorted_ids, full_names, palette, id_to_palette_idx,
                           vertex_region_ids=None):
    """
    Full electrode mapping pipeline: map electrodes, label mesh vertices,
    build JSON, and write to disk.

    If *vertex_region_ids* is provided (forward-carried from mesh generation),
    the expensive reverse-transform re-mapping is skipped.
    """
    # Get electrode MNI positions
    print("\nLoading standard 10-20 montage...")
    channel_coords = get_electrode_mni_coords(config.eeg_channels)

    # Map electrodes to atlas regions
    print("\nMapping electrodes to Destrieux regions:")
    electrode_mappings = map_electrodes_to_regions(
        channel_coords, brain_nii, atlas_volume, names_map
    )

    # Map mesh vertices to regions (skip if pre-computed)
    if vertex_region_ids is None:
        print("\nMapping PLY mesh vertices to Destrieux regions...")
        vertex_region_ids = map_mesh_vertices_to_regions(
            config.mapped_mesh_ply_path, centroid, atlas_volume
        )
    else:
        print(f"\nUsing {len(vertex_region_ids):,} pre-computed vertex region IDs")

    # Build and export JSON
    output = build_output(
        electrode_mappings, names_map, palette,
        sorted_ids, full_names, id_to_palette_idx,
        vertex_region_ids=vertex_region_ids
    )

    os.makedirs(os.path.dirname(config.output_json_path), exist_ok=True)
    with open(config.output_json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nExported -> {config.output_json_path}")
    print(f"  {len(output['electrodes'])} electrodes")
    print(f"  {len(output['regions'])} regions")
    print(f"  {len(output['region_electrodes'])} regions with electrodes")
    print(f"  {len(output.get('vertex_region_ids', []))} vertex region IDs")

    return output
