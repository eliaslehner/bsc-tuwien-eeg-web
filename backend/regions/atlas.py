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
