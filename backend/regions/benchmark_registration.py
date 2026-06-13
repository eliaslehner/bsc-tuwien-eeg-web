"""
backend/regions/benchmark_registration.py — compare atlas->subject registration transforms.

Quantifies how well the MNI152 Destrieux atlas lands on the individual subject
brain under each transform, to justify the configured REGISTRATION_TRANSFORM.
The subject brain is a deliberately arbitrary individual T1 (the method is meant
to generalise to any brain); registration is what places the standard atlas
labels onto that individual's anatomy, so its quality is worth documenting.

Metrics (per transform):
  - outside-mask %  : share of atlas labels landing OUTSIDE the brain mask
                      (the discriminating signal; lower = better aligned)
  - coverage %      : share of brain voxels that receive a cortical label
  - runtime s       : one-time preprocessing cost (registration is not per-frame)

Run:  python -m backend.regions.benchmark_registration            # print table
      python -m backend.regions.benchmark_registration --plot     # + figure & CSV
"""
import argparse
import csv
import os
import time

import numpy as np
import nibabel as nib
from nilearn.datasets import fetch_atlas_destrieux_2009
from nilearn.image import resample_to_img

from ..config import Config
from .atlas import registration_coverage
from .registration import register_atlas_to_subject

METHODS = ['unregistered', 'Affine', 'SyN']
CSV_FIELDS = ['method', 'outside_frac_pct', 'coverage_pct', 'com_offset_mm', 'runtime_s']


def _com_mm(mask_bool, affine):
    ijk = np.argwhere(mask_bool).mean(axis=0)
    return (affine @ np.append(ijk, 1.0))[:3]


def _atlas_for(method, config, brain_nii):
    """Return the atlas volume on the subject grid for the given method."""
    if method == 'unregistered':
        atlas = fetch_atlas_destrieux_2009(lateralized=True, verbose=0)
        amaps = atlas['maps']
        atlas_img = nib.load(amaps) if isinstance(amaps, str) else amaps
        aligned = resample_to_img(atlas_img, brain_nii, interpolation='nearest')
        return np.asarray(aligned.dataobj, dtype=np.int32)
    return register_atlas_to_subject(config, brain_nii, transform=method)


def evaluate(method, config, brain_nii, mask_bool):
    t0 = time.time()
    vol = _atlas_for(method, config, brain_nii)
    runtime = time.time() - t0
    if vol is None:                      # antspyx missing
        return None
    stats = registration_coverage(vol, mask_bool)
    com_off = float(np.linalg.norm(
        _com_mm(vol > 0, brain_nii.affine) - _com_mm(mask_bool, brain_nii.affine)))
    return {
        'outside_frac_pct': stats['outside_frac_pct'],
        'coverage_pct': stats['coverage_pct'],
        'com_offset_mm': com_off,
        'runtime_s': runtime,
    }


def export_benchmark(rows, out_dir, best):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, 'registration_benchmark.csv')
    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for m, r in rows:
            w.writerow({'method': m, **{k: round(r[k], 3) for k in CSV_FIELDS[1:]}})

    methods = [m for m, _ in rows]
    outside = [r['outside_frac_pct'] for _, r in rows]
    colors = ['#888888' if m == 'unregistered' else
              ('#2ecc71' if m == best else '#5dade2') for m in methods]

    fig, (axb, axt) = plt.subplots(
        1, 2, figsize=(11, 4), gridspec_kw={'width_ratios': [1.2, 1]})
    x = np.arange(len(methods))
    axb.bar(x, outside, color=colors)
    axb.set_xticks(x); axb.set_xticklabels(methods)
    axb.set_ylabel('atlas labels outside brain mask (%)')
    axb.set_title('Atlas→subject registration quality (lower = better)')
    for xi, v in zip(x, outside):
        axb.text(xi, v, f' {v:.1f}%', ha='center', va='bottom', fontsize=9)

    axt.axis('off')
    col = ['method', 'outside %', 'coverage %', 'COM mm', 'runtime s']
    cells = [[m, f"{r['outside_frac_pct']:.1f}", f"{r['coverage_pct']:.1f}",
              f"{r['com_offset_mm']:.1f}", f"{r['runtime_s']:.0f}"] for m, r in rows]
    tbl = axt.table(cellText=cells, colLabels=col, loc='center', cellLoc='center')
    tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 1.4)
    for j in range(len(col)):
        tbl[(methods.index(best) + 1, j)].set_facecolor('#d8f5e3')
    axt.set_title('Per-transform metrics')

    fig.tight_layout()
    png = os.path.join(out_dir, 'registration_benchmark.png')
    fig.savefig(png, dpi=150); plt.close(fig)
    return png, csv_path


def main():
    ap = argparse.ArgumentParser(description='Benchmark atlas->subject registration transforms.')
    ap.add_argument('--plot', action='store_true', help='write figure + CSV to bsc/figures')
    ap.add_argument('--out', default='bsc/figures')
    args = ap.parse_args()

    config = Config()
    brain_nii = nib.load(config.brain_nii_path)
    mask_bool = np.asarray(nib.load(config.brain_mask_nii_path).dataobj) > 0

    print(f"Benchmarking registration transforms on {config.brain_nii_path}\n")
    print(f"{'method':14s} {'outside%':>9s} {'coverage%':>10s} {'COM_mm':>7s} {'runtime_s':>10s}")
    print('-' * 54)
    rows = []
    for m in METHODS:
        r = evaluate(m, config, brain_nii, mask_bool)
        if r is None:
            print(f"{m:14s}  (skipped — antspyx unavailable)")
            continue
        rows.append((m, r))
        print(f"{m:14s} {r['outside_frac_pct']:8.1f}% {r['coverage_pct']:9.1f}% "
              f"{r['com_offset_mm']:6.1f} {r['runtime_s']:9.0f}s")

    registered = [(m, r) for m, r in rows if m != 'unregistered']
    best = min(registered, key=lambda x: x[1]['outside_frac_pct'])[0] if registered else None
    if best:
        print(f"\nBest-aligned transform -> {best}")
    if args.plot and rows:
        png, csvp = export_benchmark(rows, args.out, best)
        print(f"Benchmark written -> {png}\n                    {csvp}")


if __name__ == '__main__':
    main()
