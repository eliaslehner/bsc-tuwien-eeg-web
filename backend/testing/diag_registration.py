"""
Diagnostic: measure how the Destrieux atlas aligns to the subject brain.

Answers the question: does the shift in g_front_sup come from the atlas->subject
resampling (registration), or from gap-filling?

Run:  .venv/bin/python -m backend.testing.diag_registration
"""
import numpy as np
import nibabel as nib
from nilearn.datasets import fetch_atlas_destrieux_2009
from nilearn.image import resample_to_img

from backend.config import Config


def com_world(data_bool, affine):
    """Center of mass of a boolean volume, in world (mm) coordinates."""
    ijk = np.argwhere(data_bool)
    c_ijk = ijk.mean(axis=0)
    c_world = affine @ np.append(c_ijk, 1.0)
    return c_world[:3], c_ijk


def main():
    cfg = Config()

    # ---- Subject ----
    brain = nib.load(cfg.brain_nii_path)
    mask = nib.load(cfg.brain_mask_nii_path)
    brain_aff = brain.affine
    mask_data = np.asarray(mask.dataobj) > 0

    print("=" * 70)
    print("SUBJECT (individual NFBS brain)")
    print("=" * 70)
    print("file        :", cfg.brain_nii_path)
    print("shape       :", brain.shape)
    print("axcodes     :", nib.aff2axcodes(brain_aff))
    print("affine:\n", np.array2string(brain_aff, precision=2, suppress_small=True))
    det = np.linalg.det(brain_aff[:3, :3])
    print("det(3x3)    : %.3f  (%s-handed)" % (det, "right" if det > 0 else "left"))
    sc, s_ijk = com_world(mask_data, brain_aff)
    print("brain-mask COM (voxel ijk):", np.round(s_ijk, 1))
    print("brain-mask COM (world mm) :", np.round(sc, 1))
    # world bounding box of mask
    ijk = np.argwhere(mask_data)
    corners = np.array([[ijk[:, 0].min(), ijk[:, 1].min(), ijk[:, 2].min()],
                        [ijk[:, 0].max(), ijk[:, 1].max(), ijk[:, 2].max()]])
    wc = np.array([brain_aff @ np.append(c, 1.0) for c in corners])[:, :3]
    print("brain-mask world bbox     : x[%.0f,%.0f] y[%.0f,%.0f] z[%.0f,%.0f]"
          % (wc[:, 0].min(), wc[:, 0].max(), wc[:, 1].min(), wc[:, 1].max(),
             wc[:, 2].min(), wc[:, 2].max()))

    # ---- Atlas (native MNI space) ----
    atlas = fetch_atlas_destrieux_2009(lateralized=True, verbose=0)
    amaps = atlas["maps"]
    atlas_img = nib.load(amaps) if isinstance(amaps, str) else amaps
    atlas_aff = atlas_img.affine
    atlas_data = np.asarray(atlas_img.dataobj).astype(np.int32)

    print("\n" + "=" * 70)
    print("ATLAS (Destrieux 2009, native space)")
    print("=" * 70)
    print("shape       :", atlas_img.shape)
    print("axcodes     :", nib.aff2axcodes(atlas_aff))
    print("affine:\n", np.array2string(atlas_aff, precision=2, suppress_small=True))
    det_a = np.linalg.det(atlas_aff[:3, :3])
    print("det(3x3)    : %.3f  (%s-handed)" % (det_a, "right" if det_a > 0 else "left"))
    ac, a_ijk = com_world(atlas_data > 0, atlas_aff)
    print("labelled COM (voxel ijk)  :", np.round(a_ijk, 1))
    print("labelled COM (world mm)   :", np.round(ac, 1))
    aijk = np.argwhere(atlas_data > 0)
    acorners = np.array([[aijk[:, 0].min(), aijk[:, 1].min(), aijk[:, 2].min()],
                         [aijk[:, 0].max(), aijk[:, 1].max(), aijk[:, 2].max()]])
    awc = np.array([atlas_aff @ np.append(c, 1.0) for c in acorners])[:, :3]
    print("labelled world bbox       : x[%.0f,%.0f] y[%.0f,%.0f] z[%.0f,%.0f]"
          % (awc[:, 0].min(), awc[:, 0].max(), awc[:, 1].min(), awc[:, 1].max(),
             awc[:, 2].min(), awc[:, 2].max()))

    # ---- World-space offset between the two brains ----
    print("\n" + "=" * 70)
    print("WORLD-SPACE ALIGNMENT (subject brain COM vs atlas-cortex COM)")
    print("=" * 70)
    offset = sc - ac
    print("COM offset (subject - atlas), mm:", np.round(offset, 1))
    print("COM offset magnitude, mm        : %.1f" % np.linalg.norm(offset))
    print("  (A few mm = registered. Tens of mm = the subject is NOT in the")
    print("   atlas's space, so affine-only resampling misplaces labels.)")

    # ---- What the pipeline actually does: resample atlas onto subject grid ----
    resampled = resample_to_img(atlas_img, brain, interpolation="nearest")
    res_data = np.asarray(resampled.dataobj).astype(np.int32)
    labelled_in_brain = (res_data > 0) & mask_data
    n_brain = int(mask_data.sum())
    n_lab = int(labelled_in_brain.sum())
    n_lab_total = int((res_data > 0).sum())
    print("\n" + "=" * 70)
    print("AFTER resample_to_img ONTO SUBJECT GRID")
    print("=" * 70)
    print("labelled voxels total           : {:,}".format(n_lab_total))
    print("labelled voxels INSIDE mask     : {:,}".format(n_lab))
    print("labelled voxels OUTSIDE mask    : {:,}".format(n_lab_total - n_lab))
    print("brain voxels                    : {:,}".format(n_brain))
    print("coverage (labelled inside / brain): {:.1f}%".format(100 * n_lab / n_brain))
    print("FRACTION OF ATLAS LABELS THAT LAND OUTSIDE THE BRAIN MASK: {:.1f}%"
          .format(100 * (n_lab_total - n_lab) / max(n_lab_total, 1)))
    print("  (If a large fraction of atlas labels fall OUTSIDE the brain mask,")
    print("   the atlas is mis-registered to the subject.)")

    # COM of resampled labels inside brain, in world space, vs subject COM
    rc, _ = com_world(labelled_in_brain, brain_aff)
    print("resampled-label COM (world mm)  :", np.round(rc, 1))
    print("subject brain  COM (world mm)   :", np.round(sc, 1))
    print("resampled-label vs brain offset : %.1f mm"
          % np.linalg.norm(rc - sc))

    # ---- Left/right sanity: where do L_* and R_* labels land along subject x? ----
    print("\n" + "=" * 70)
    print("HEMISPHERE CHECK (do L_ regions sit on one side, R_ on the other?)")
    print("=" * 70)
    raw_labels = atlas["labels"]
    def lname(uid):
        lbl = raw_labels[uid]
        if isinstance(lbl, (bytes, np.bytes_)):
            lbl = lbl.decode("utf-8", "replace")
        elif hasattr(lbl, "__iter__") and not isinstance(lbl, str):
            lbl = str(lbl[-1]) if len(lbl) > 1 else str(lbl[0])
        return str(lbl)

    # subject world x of each labelled voxel
    lab_ijk = np.argwhere(labelled_in_brain)
    lab_ids = res_data[lab_ijk[:, 0], lab_ijk[:, 1], lab_ijk[:, 2]]
    world = (brain_aff @ np.c_[lab_ijk, np.ones(len(lab_ijk))].T).T[:, :3]
    wx = world[:, 0]
    # group by L_/R_ prefix
    l_x, r_x = [], []
    for uid in np.unique(lab_ids):
        nm = lname(int(uid))
        m = lab_ids == uid
        if nm.startswith("L "):
            l_x.append(wx[m].mean())
        elif nm.startswith("R "):
            r_x.append(wx[m].mean())
    if l_x and r_x:
        print("mean world-x of L_ regions: %.1f mm" % np.mean(l_x))
        print("mean world-x of R_ regions: %.1f mm" % np.mean(r_x))
        print("  (These should be cleanly separated and on opposite sides of 0.")
        print("   Overlap / same sign => hemispheres collapsed onto each other.)")

    # ---- g_front_sup specifically ----
    print("\n" + "=" * 70)
    print("g_front_sup SPECIFIC (the reported problem region)")
    print("=" * 70)
    for uid in np.unique(lab_ids):
        nm = lname(int(uid))
        if "front_sup" in nm.lower():
            m = lab_ids == uid
            xs = wx[m]
            print("  [%3d] %-22s  n=%6d  world-x mean=%7.1f  range[%.0f,%.0f]"
                  % (uid, nm, m.sum(), xs.mean(), xs.min(), xs.max()))


if __name__ == "__main__":
    main()
