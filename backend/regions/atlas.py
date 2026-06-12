import nibabel as nib
import numpy as np
from nilearn.datasets import fetch_atlas_destrieux_2009
from nilearn.image import resample_to_img
from scipy.ndimage import distance_transform_edt


def fetch_and_resample_atlas(brain_nii_img):
    """
    Fetch the Destrieux 2009 atlas and resample it into the subject's voxel space.

    Returns
    -------
    atlas_volume : np.ndarray (int32) — region labels per voxel
    names_map : dict[int, str] — region ID → human-readable name
    """
    print("Fetching Destrieux 2009 atlas ...")
    atlas = fetch_atlas_destrieux_2009(lateralized=True, verbose=0)

    atlas_maps = atlas["maps"]
    if isinstance(atlas_maps, str):
        atlas_img = nib.load(atlas_maps)
    else:
        atlas_img = atlas_maps

    raw_labels = atlas["labels"]

    resampled = resample_to_img(atlas_img, brain_nii_img, interpolation='nearest')
    atlas_data = np.asarray(resampled.dataobj, dtype=np.int32)

    # Build region name lookup — handles bytes, tuples, and plain strings
    names = {}
    for uid in np.unique(atlas_data):
        uid = int(uid)
        if uid == 0:
            continue
        if uid < len(raw_labels):
            lbl = raw_labels[uid]
            if isinstance(lbl, (bytes, np.bytes_)):
                lbl = lbl.decode('utf-8', errors='replace')
            elif hasattr(lbl, '__iter__') and not isinstance(lbl, str):
                lbl = str(lbl[-1]) if len(lbl) > 1 else str(lbl[0])
            names[uid] = str(lbl)
        else:
            names[uid] = f"Region_{uid}"

    print(f"    Destrieux 2009 — {len(names)} regions, shape {atlas_data.shape}")
    return atlas_data, names


def fetch_destrieux_native():
    """
    Fetch the Destrieux 2009 atlas in its OWN (MNI152) space, un-resampled.

    Used for electrode->region mapping: an electrode's MNI montage position and
    the atlas both live in MNI space, so the region under an electrode is an
    MNI-space question that must NOT go through the (mis-registered) subject grid.

    Returns
    -------
    atlas_data : np.ndarray(int32) — labels in MNI space
    affine     : np.ndarray(4, 4)  — MNI affine
    names_map  : dict[int, str]
    """
    atlas = fetch_atlas_destrieux_2009(lateralized=True, verbose=0)
    amaps = atlas["maps"]
    atlas_img = nib.load(amaps) if isinstance(amaps, str) else amaps
    atlas_data = np.asarray(atlas_img.dataobj, dtype=np.int32)
    raw_labels = atlas["labels"]

    names = {}
    for uid in np.unique(atlas_data):
        uid = int(uid)
        if uid == 0:
            continue
        if uid < len(raw_labels):
            lbl = raw_labels[uid]
            if isinstance(lbl, (bytes, np.bytes_)):
                lbl = lbl.decode('utf-8', errors='replace')
            elif hasattr(lbl, '__iter__') and not isinstance(lbl, str):
                lbl = str(lbl[-1]) if len(lbl) > 1 else str(lbl[0])
            names[uid] = str(lbl)
        else:
            names[uid] = f"Region_{uid}"
    return atlas_data, atlas_img.affine, names


def registration_coverage(atlas_volume_raw, brain_mask):
    """
    Report how well the resampled atlas overlaps the subject brain.

    A correctly registered atlas labels most of the cortical ribbon and keeps
    its labels INSIDE the brain. A large "outside-mask" fraction or low coverage
    means the subject is not aligned to the atlas's space (a registration
    problem), not a gap-filling problem.

    Returns
    -------
    stats : dict
    """
    labelled = atlas_volume_raw > 0
    n_brain = int(brain_mask.sum())
    n_lab_total = int(labelled.sum())
    n_lab_inside = int((labelled & brain_mask).sum())
    n_lab_outside = n_lab_total - n_lab_inside

    coverage = 100 * n_lab_inside / n_brain if n_brain else 0.0
    outside_frac = 100 * n_lab_outside / n_lab_total if n_lab_total else 0.0

    print(f"    Registration check: {coverage:.1f}% of brain voxels labelled "
          f"(cortical ribbon), {outside_frac:.1f}% of atlas labels fall OUTSIDE "
          f"the brain mask")
    # The discriminating signal is outside-mask %, not raw coverage: the
    # volumetric Destrieux atlas only labels the cortical ribbon (~40% of the
    # brain), so low coverage is normal even when alignment is perfect.
    if outside_frac > 15:
        print("    ^ Many labels outside the brain => subject is mis-aligned to "
              "the atlas (registration); gap-fill then smears the misplaced labels.")
    return {
        "coverage_pct": coverage,
        "outside_frac_pct": outside_frac,
        "labelled_inside": n_lab_inside,
        "labelled_outside": n_lab_outside,
        "brain_voxels": n_brain,
    }


def gap_fill_labels(atlas_volume, brain_mask):
    """
    Fill unlabelled brain voxels with the nearest labelled neighbour.

    Returns
    -------
    filled : np.ndarray — gap-filled atlas volume
    stats : dict — {"filled": int, "total": int}
    """
    unlabeled = brain_mask & (atlas_volume == 0)
    n_unlabeled = int(unlabeled.sum())
    n_total = int(brain_mask.sum())

    if n_unlabeled == 0:
        return atlas_volume.copy(), {"filled": 0, "total": n_total}

    labeled_mask = atlas_volume > 0
    _, nearest_idx = distance_transform_edt(
        ~labeled_mask, return_distances=True, return_indices=True
    )

    filled = atlas_volume.copy()
    ul_ijk = np.argwhere(unlabeled)
    ni = nearest_idx[0][ul_ijk[:, 0], ul_ijk[:, 1], ul_ijk[:, 2]]
    nj = nearest_idx[1][ul_ijk[:, 0], ul_ijk[:, 1], ul_ijk[:, 2]]
    nk = nearest_idx[2][ul_ijk[:, 0], ul_ijk[:, 1], ul_ijk[:, 2]]
    filled[ul_ijk[:, 0], ul_ijk[:, 1], ul_ijk[:, 2]] = atlas_volume[ni, nj, nk]

    print(f"    Gap-filled {n_unlabeled:,} unlabelled voxels "
          f"({100 * n_unlabeled / n_total:.1f}% of brain)")
    return filled, {"filled": n_unlabeled, "total": n_total}
