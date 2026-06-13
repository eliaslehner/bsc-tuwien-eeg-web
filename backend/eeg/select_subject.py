"""
backend/eeg/select_subject.py — rank BCI IV 2a subjects by ERD/ERS cleanliness.

Justifies the default exemplar subject (A03). Applies the PRODUCTION pipeline
(CSD surface-Laplacian reference, mu band) to every T-session GDF found in the
EEG data dir and scores each subject on motor-imagery quality:

  - contralateral hand ERD depth  (left_hand -> C4, right_hand -> C3; the more
    negative, the stronger the genuine sensorimotor desynchronisation)
  - correct-sign central feet ERD (feet should desynchronise at the vertex, Cz<0)
  - artifact load                 (fewer rejected trials = cleaner subject)

This reads the canonical GDF input (the data format the thesis justifies its
processing on); the official .mat artifact flags were only used to cross-check
that our GDF reject counts match (they do) and that A03 replicates on the
held-out E session.

Run:  python -m backend.eeg.select_subject            # print ranking
      python -m backend.eeg.select_subject --plot     # also write benchmark figure + CSV

The --plot output (bsc/figures/subject_selection_benchmark.png + .csv) is a
committable justification artifact: it preserves the ranking for the thesis even
after the non-A03 subject data is removed from the repo.
"""
import argparse
import csv
import glob
import os
import re

import numpy as np

from ..config import Config
from .loader import load_gdf, setup_channels, get_trial_counts, class_for_annotation_key
from .processing import (preprocess_raw, create_epochs,
                         compute_band_normalized_power, get_class_epoch_counts)

MI_WINDOW = (0.5, 3.5)        # motor-imagery window for the summary statistic


def _erders_per_channel(norm_power, times, baseline_tmin, baseline_tmax):
    bl = (times >= baseline_tmin) & (times < baseline_tmax)
    mi = (times >= MI_WINDOW[0]) & (times <= MI_WINDOW[1])
    out = {}
    for cn, arr in norm_power.items():
        mp = arr.mean(axis=0)                     # (n_ch, n_t)
        base = mp[:, bl].mean(axis=1, keepdims=True)
        e = (mp - base) / base * 100
        out[cn] = e[:, mi].mean(axis=1)           # (n_ch,) MI-window mean
    return out


def evaluate_subject(config, gdf_path):
    raw, events, event_id = load_gdf(gdf_path)
    eeg_channels, eog_channels = setup_channels(raw)
    trial_counts = get_trial_counts(events, event_id)
    raw = preprocess_raw(raw, eeg_channels, eog_channels, reference=config.eeg_reference)
    ch = raw.ch_names

    epochs = create_epochs(raw, events, event_id,
                           tmin=config.eeg_epoch_tmin, tmax=config.eeg_epoch_tmax)
    if epochs is None:
        return None
    clean = get_class_epoch_counts(epochs)
    n_drop = sum(trial_counts.values()) - sum(clean.values())

    band_raw = raw.copy().filter(*config.eeg_mu_band, verbose=False)
    norm, times = compute_band_normalized_power(
        band_raw, events, event_id,
        tmin=config.eeg_epoch_tmin, tmax=config.eeg_epoch_tmax,
        baseline_tmin=config.eeg_baseline_tmin, baseline_tmax=config.eeg_baseline_tmax)
    if norm is None:
        return None
    e = _erders_per_channel(norm, times, config.eeg_baseline_tmin, config.eeg_baseline_tmax)

    def v(cn, c):
        return float(e[cn][ch.index(c)]) if cn in e else float('nan')

    lh_c4, lh_c3 = v('left_hand', 'C4'), v('left_hand', 'C3')
    rh_c3, rh_c4 = v('right_hand', 'C3'), v('right_hand', 'C4')
    feet_cz = v('feet', 'Cz')
    lh_contra = lh_c4 < lh_c3          # left hand desync stronger contralaterally (right hemi)
    rh_contra = rh_c3 < rh_c4          # right hand desync stronger contralaterally (left hemi)

    # Lower score = cleaner. Reward deep contralateral hand ERD + feet ERD;
    # penalise wrong lateralisation and a positive (ERS) feet vertex.
    score = lh_c4 + rh_c3
    if not lh_contra:
        score += 50
    if not rh_contra:
        score += 50
    if feet_cz > 0:
        score += 30

    return {
        'lh_c4': lh_c4, 'rh_c3': rh_c3, 'feet_cz': feet_cz,
        'lh_contra': lh_contra, 'rh_contra': rh_contra,
        'n_drop': n_drop, 'clean': sum(clean.values()), 'score': score,
    }


CSV_FIELDS = ['subject', 'score', 'lh_c4', 'rh_c3', 'feet_cz',
              'lh_contra', 'rh_contra', 'clean', 'n_drop']


def export_benchmark(rows, best, out_dir, reference):
    """Write a committable justification artifact: a benchmark PNG + CSV.

    rows: list of (subject, metrics); the PNG shows the cleanliness score per
    subject (sorted, exemplar highlighted) and a table of the key metrics.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(out_dir, exist_ok=True)
    ordered = sorted(rows, key=lambda x: x[1]['score'])

    csv_path = os.path.join(out_dir, 'subject_selection_benchmark.csv')
    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for subj, r in ordered:
            w.writerow({'subject': subj, **{k: r[k] for k in CSV_FIELDS[1:]}})

    subjects = [s for s, _ in ordered]
    scores = [r['score'] for _, r in ordered]
    colors = ['#2ecc71' if s == best else '#888888' for s in subjects]

    fig, (axb, axt) = plt.subplots(
        1, 2, figsize=(12, 4.6), gridspec_kw={'width_ratios': [1.25, 1]})

    y = np.arange(len(subjects))[::-1]   # cleanest at top
    axb.barh(y, scores, color=colors)
    axb.axvline(0, color='k', lw=0.8)
    axb.set_yticks(y)
    axb.set_yticklabels(subjects)
    axb.set_xlabel('cleanliness score  (lower = cleaner)')
    axb.set_title(f'Subject selection — ERD/ERS quality ({reference.upper()}, mu band)')
    for yi, sc in zip(y, scores):
        axb.text(sc, yi, f' {sc:+.0f}', va='center',
                 ha='left' if sc >= 0 else 'right', fontsize=8)

    axt.axis('off')
    col_labels = ['subj', 'L→C4 %', 'R→C3 %', 'feet Cz %', 'contra', 'drop']
    cells = [[s,
              f"{r['lh_c4']:+.0f}", f"{r['rh_c3']:+.0f}", f"{r['feet_cz']:+.0f}",
              ('L✓R✓' if r['lh_contra'] and r['rh_contra']
               else ('L✓R✗' if r['lh_contra'] else 'L✗R✓' if r['rh_contra'] else 'L✗R✗')),
              str(r['n_drop'])]
             for s, r in ordered]
    tbl = axt.table(cellText=cells, colLabels=col_labels, loc='center', cellLoc='center')
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.scale(1, 1.3)
    for j in range(len(col_labels)):                  # highlight exemplar row
        tbl[(subjects.index(best) + 1, j)].set_facecolor('#d8f5e3')
    axt.set_title('Per-subject metrics (sorted by score)')

    fig.tight_layout()
    png_path = os.path.join(out_dir, 'subject_selection_benchmark.png')
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    return png_path, csv_path


def main():
    ap = argparse.ArgumentParser(description='Rank BCI IV 2a subjects by ERD/ERS cleanliness.')
    ap.add_argument('--plot', action='store_true',
                    help='also write a benchmark figure + CSV (justification artifact)')
    ap.add_argument('--out', default='bsc/figures',
                    help='output dir for --plot artifacts (default: bsc/figures)')
    args = ap.parse_args()

    config = Config()
    files = sorted(glob.glob(os.path.join(config.eeg_data_dir, 'A0*T.gdf')))
    if not files:
        print(f"No T-session GDFs in {config.eeg_data_dir}")
        return
    if len(files) < 9:
        print(f"NOTE: only {len(files)} subject(s) present; the ranking needs all 9 "
              f"T-session GDFs to justify the selection. Found: "
              f"{[os.path.basename(f) for f in files]}\n")
    print(f"Ranking {len(files)} subjects with the production pipeline "
          f"(reference={config.eeg_reference}, mu band, MI {MI_WINDOW[0]}-{MI_WINDOW[1]}s)\n")
    print(f"{'subj':5s} {'score':>7s} {'lhC4':>7s} {'rhC3':>7s} {'feetCz':>7s} "
          f"{'L-contra':>8s} {'R-contra':>8s} {'clean':>6s} {'dropped':>7s}")
    print('-' * 74)
    rows = []
    for fp in files:
        subj = re.match(r'(A\d+)', os.path.basename(fp)).group(1)
        r = evaluate_subject(config, fp)
        if r is None:
            continue
        rows.append((subj, r))
    for subj, r in sorted(rows, key=lambda x: x[1]['score']):
        print(f"{subj:5s} {r['score']:+7.1f} {r['lh_c4']:+7.1f} {r['rh_c3']:+7.1f} "
              f"{r['feet_cz']:+7.1f} {str(r['lh_contra']):>8s} {str(r['rh_contra']):>8s} "
              f"{r['clean']:6d} {r['n_drop']:7d}")
    best = min(rows, key=lambda x: x[1]['score'])[0]
    print(f"\nCleanest exemplar -> {best}  (default EEG_SUBJECT)")

    if args.plot:
        png, csv_path = export_benchmark(rows, best, args.out, config.eeg_reference)
        print(f"Benchmark written -> {png}\n                    {csv_path}")


if __name__ == '__main__':
    main()
