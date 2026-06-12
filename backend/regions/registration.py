"""
backend/regions/registration.py — proper subject<->MNI registration.

The default atlas path (regions/atlas.py) aligns the MNI152 Destrieux atlas to
the subject with resample_to_img, which honours ONLY the stored affines. The
NFBS subject is in native scanner space (~36 mm out of MNI), so labels land
sparse and misplaced. This module fixes that by REGISTERING the MNI template to
the subject (ANTs) and warping the atlas into the subject's space, so the
individual brain shape (Marching Cubes) is preserved and only the labels move
to the right place.

Start with an affine transform; switch to nonlinear later by setting
config.registration_transform = 'SyN' (or 'SyNRA') — same single dependency
(antspyx), no code change required here.
"""

import os
import tempfile

import numpy as np
import nibabel as nib
from nilearn.datasets import (
    fetch_atlas_destrieux_2009,
    load_mni152_template,
    load_mni152_brain_mask,
)
from nilearn.image import resample_to_img


def register_atlas_to_subject(config, brain_nii, transform=None):
    """
    Warp the Destrieux atlas into the subject's voxel space via ANTs.

    fixed  = subject skull-stripped brain  (config.brain_nii_path)
    moving = MNI152 template brain          (same space as the atlas)
    The moving->fixed transform is then applied to the atlas (nearest-neighbour),
    and the result is conformed to the subject's nibabel grid so its voxel
    indices line up exactly with masked_volume / the mesh.

    Returns
    -------
    atlas_volume : np.ndarray(int32) on the subject grid, or None if antspyx is
    not installed (caller should skip the registered view).
    """
    try:
        import ants
    except ImportError:
        print("  Registration skipped: antspyx not installed.")
        print("  Install it with:  pip install antspyx   (then set USE_REGISTRATION=true)")
        return None

    transform = transform or config.registration_transform
    print(f"  Registering MNI152 -> subject (ANTs, type_of_transform='{transform}')...")

    fixed = ants.image_read(config.brain_nii_path)

    template = load_mni152_template(resolution=1)
    mask = load_mni152_brain_mask(resolution=1)
    tmpl_brain = nib.Nifti1Image(
        np.asarray(template.dataobj, dtype=np.float32) * (np.asarray(mask.dataobj) > 0),
        template.affine,
    )

    atlas = fetch_atlas_destrieux_2009(lateralized=True, verbose=0)
    amaps = atlas["maps"]

    with tempfile.TemporaryDirectory() as tmp:
        moving_path = os.path.join(tmp, "mni_brain.nii.gz")
        nib.save(tmpl_brain, moving_path)
        moving = ants.image_read(moving_path)

        if isinstance(amaps, str):
            atlas_ants = ants.image_read(amaps)
        else:
            atlas_path = os.path.join(tmp, "atlas.nii.gz")
            nib.save(amaps, atlas_path)
            atlas_ants = ants.image_read(atlas_path)

        reg = ants.registration(
            fixed=fixed, moving=moving, type_of_transform=transform,
        )
        warped = ants.apply_transforms(
            fixed=fixed, moving=atlas_ants,
            transformlist=reg["fwdtransforms"], interpolator="nearestNeighbor",
        )
        warped_nib = ants.to_nibabel_nifti(warped)

    # Conform to the subject's exact nibabel grid (corrects any ANTs<->nibabel
    # index-order difference) so indices match the mesh / masked_volume.
    aligned = resample_to_img(warped_nib, brain_nii, interpolation="nearest")
    return np.asarray(aligned.dataobj, dtype=np.int32)
