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

Run:  python -m backend.eeg.select_subject
"""
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


def main():
    config = Config()
    files = sorted(glob.glob(os.path.join(config.eeg_data_dir, 'A0*T.gdf')))
    if not files:
        print(f"No T-session GDFs in {config.eeg_data_dir}")
        return
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


if __name__ == '__main__':
    main()
