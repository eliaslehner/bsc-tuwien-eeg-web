import nibabel as nib
import numpy as np
import torch


def load_nii_image(filepath):
    """Load a NIfTI file and return the nibabel image object."""
    print(f"Loading NIfTI image: {filepath}")
    return nib.load(filepath)


def load_nii_to_tensor(filepath, device='cpu'):
    """Load a NIfTI file, normalise to [0,1] and return as a torch tensor."""
    print(f"Loading NIfTI tensor: {filepath}")
    nii_img = nib.load(filepath)
    data = nii_img.get_fdata()
    tensor_data = torch.tensor(data, dtype=torch.float32, device=device)
    tensor_data = (tensor_data - tensor_data.min()) / (tensor_data.max() - tensor_data.min())
    return tensor_data


def compute_pointcloud_centroid(vol_tensor, threshold):
    """
    Compute the mean centroid of all brain-tissue voxels above the threshold.
    This replicates the centering logic used during point cloud generation,
    so downstream modules can reverse the transform.
    """
    indices = torch.nonzero(vol_tensor > threshold)
    centroid = indices.float().mean(dim=0).cpu().numpy()
    print(f"  Computed centroid (threshold={threshold}): {centroid}")
    return centroid


def compute_brain_mask(brain_nii, threshold):
    """
    Compute a boolean brain mask from a NIfTI image.
    Normalises intensities to [0,1] and thresholds.
    """
    brain_data = brain_nii.get_fdata()
    brain_norm = (brain_data - brain_data.min()) / (brain_data.max() - brain_data.min())
    return brain_norm > threshold


def load_masked_volume(t1w_path, mask_path):
    """
    Load the full T1w volume and apply the brainmask.
    Normalises brain voxels to [0, 1].  Non-brain voxels are 0.

    Returns
    -------
    t1w_nii : nibabel image object (for affine / header reuse)
    masked  : np.ndarray float64 — normalised masked volume
    mask    : np.ndarray bool     — brain mask
    """
    print(f"  Loading T1w   : {t1w_path}")
    print(f"  Loading mask  : {mask_path}")
    t1w_nii = nib.load(t1w_path)
    mask_nii = nib.load(mask_path)

    t1w_data = t1w_nii.get_fdata().astype(np.float64)
    mask = mask_nii.get_fdata() > 0

    masked = t1w_data * mask
    brain_vals = masked[mask]
    vmin, vmax = float(brain_vals.min()), float(brain_vals.max())
    if vmax > vmin:
        masked = (masked - vmin) / (vmax - vmin)
        masked[~mask] = 0.0

    print(f"  Masked volume shape: {masked.shape}, brain voxels: {int(mask.sum()):,}")
    return t1w_nii, masked, mask
