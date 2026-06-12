import json
import os

import mne
import numpy as np
import open3d as o3d


def get_electrode_mni_coords(channel_names):
    """
    Get scalp positions for each channel from MNE's standard_1020 montage.

    NOTE: these are scalp-surface points in MNE's head/fsaverage frame (in
    metres), NOT cortical MNI coordinates — they sit ~10-25 mm outside the
    cortical ribbon and are projected inward onto the cortex in
    map_electrodes_to_regions.

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


def map_electrodes_to_regions(channel_coords, atlas_volume, affine, names_map,
                              shell_voxels=6):
    """
    Project each scalp electrode radially inward onto the cortical surface and
    read its Destrieux region.

    The montage positions are scalp-surface points (MNE standard_1020, head /
    fsaverage frame) that sit ~10-25 mm OUTSIDE the cortical ribbon. We march
    from the electrode voxel toward the centroid of the labelled cortex and take
    the first cortical voxel along that inward ray — i.e. the gyral crown beneath
    the electrode. The ribbon is first dilated by a thin *shell_voxels* shell of
    nearest-cortex labels so the ray reliably catches the crown (and so a truly
    midline electrode lands on the medial crown, e.g. paracentral, instead of
    plunging down the interhemispheric fissure into cingulate).

    CAVEAT: a truly midline electrode (Cz, Fz, Pz, FCz, CPz, POz) sits over the
    longitudinal fissure, so its HEMISPHERE is inherently ambiguous in a
    lateralised atlas — the region (e.g. paracentral) is meaningful but L-vs-R is
    not reliable. Lateral electrodes (C3/C4, ...) are unambiguous.

    Pass the NATIVE Destrieux atlas + its affine (electrode->region is an
    atlas-space question). Passing a subject-space atlas + the subject affine
    reproduces the old mis-registered placement.

    Returns
    -------
    electrode_mappings : list[dict] — one entry per electrode
    """
    from scipy.ndimage import distance_transform_edt

    labelled = atlas_volume > 0
    shape = atlas_volume.shape

    # Thin shell of nearest-cortex labels around the ribbon, so the inward ray
    # has a crown to hit at the cortical surface.
    dist, nearest_idx = distance_transform_edt(
        ~labelled, return_distances=True, return_indices=True
    )
    filled = atlas_volume.copy()
    shell = (dist > 0) & (dist <= shell_voxels)
    filled[shell] = atlas_volume[
        nearest_idx[0][shell], nearest_idx[1][shell], nearest_idx[2][shell]
    ]
    filled_labelled = filled > 0

    centroid = np.argwhere(labelled).mean(axis=0)

    mappings = []
    for ch_name, mni_pos in channel_coords.items():
        start = np.round(mni_to_voxel(mni_pos, affine)).astype(np.float64)
        direction = centroid - start
        length = float(np.linalg.norm(direction))
        if length > 0:
            direction = direction / length

        region_id = 0
        hit_voxel = np.clip(start, 0, np.array(shape) - 1).astype(np.int64)
        for step in np.arange(0, length, 0.5):
            idx = np.round(start + direction * step).astype(np.int64)
            for dim in range(3):
                idx[dim] = np.clip(idx[dim], 0, shape[dim] - 1)
            if filled_labelled[idx[0], idx[1], idx[2]]:
                region_id = int(filled[idx[0], idx[1], idx[2]])
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

        print(f"  {ch_name:>4s}  ->  voxel {hit_voxel}  ->  [{region_id}] {region_name}")

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
                           vertex_region_ids=None, output_path=None,
                           electrode_atlas=None, electrode_affine=None,
                           electrode_names=None):
    """
    Full electrode mapping pipeline: map electrodes, label mesh vertices,
    build JSON, and write to disk.

    If *vertex_region_ids* is provided (forward-carried from mesh generation),
    the expensive reverse-transform re-mapping is skipped. *output_path* defaults
    to the canonical region_metadata.json; pass a path to write a backup.

    Electrode->region is mapped against *electrode_atlas* using *electrode_affine*
    and *electrode_names* (default: the subject atlas + subject affine). Pass the
    native Destrieux atlas + its affine + its names for the correct, atlas-space
    mapping that is independent of the subject registration.
    """
    out_path = output_path or config.output_json_path
    e_atlas = electrode_atlas if electrode_atlas is not None else atlas_volume
    e_affine = (electrode_affine if electrode_affine is not None
                else brain_nii.header.get_best_affine())
    e_names = electrode_names if electrode_names is not None else names_map

    # Get electrode scalp positions (MNE standard_1020, head/fsaverage frame)
    print("\nLoading standard 10-20 montage...")
    channel_coords = get_electrode_mni_coords(config.eeg_channels)

    # Map electrodes to atlas regions
    print("\nMapping electrodes to Destrieux regions:")
    electrode_mappings = map_electrodes_to_regions(
        channel_coords, e_atlas, e_affine, e_names
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

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nExported -> {out_path}")
    print(f"  {len(output['electrodes'])} electrodes")
    print(f"  {len(output['regions'])} regions")
    print(f"  {len(output['region_electrodes'])} regions with electrodes")
    print(f"  {len(output.get('vertex_region_ids', []))} vertex region IDs")

    return output
